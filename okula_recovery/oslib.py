"""Betriebssysteme auf dem NAS: ISO-Dateien hochladen, erkennen, ordnen.

    <NAS>/OS/Windows/…    Windows-Installationsmedien
    <NAS>/OS/Linux/…      Linux-Installations- und Live-Medien
    <NAS>/OS/Sonstige/…   alles andere (Rettungs-CDs, FreeDOS, Hersteller-Tools, Disk-Abbilder)

Unter jeder Kategorie sind eigene Ordner möglich (insgesamt max. 3 Ebenen). Zu jeder ISO liegt
eine versteckte Beschreibung „.<Name>.okula.json“ daneben: erkanntes OS, Editionen, Prüfsumme.

Erkennung ohne Einhängen und ohne root: Windows über das UDF-Dateisystem und die XML-Beschreibung
der install.wim/esd, Linux über xorriso (ISO9660/Rock Ridge).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from okula_recovery import nasfiles, udf

OS_DIR = "OS"
CATEGORIES = {"windows": "Windows", "linux": "Linux", "other": "Sonstige"}
MAX_DEPTH = 3                      # Kategorie + 2 eigene Ebenen
SUFFIXES = (".iso", ".img", ".img.xz", ".img.gz", ".img.zst", ".img.bz2")
META_SUFFIX = ".okula.json"
META_VERSION = 3                   # erhöhen, wenn sich die Erkennung ändert → neu prüfen

# Build-Nummer → Version (Installationsmedien tragen die Basis-Build)
WINDOWS_RELEASES = {10240: "1507", 10586: "1511", 14393: "1607", 15063: "1703", 16299: "1709", 17134: "1803",
                    17763: "1809", 18362: "1903", 18363: "1909", 19041: "2004", 19042: "20H2", 19043: "21H1",
                    19044: "21H2", 19045: "22H2", 22000: "21H2", 22621: "22H2", 22631: "23H2", 26100: "24H2",
                    26200: "25H2"}
WIM_ARCH = {0: "x86", 5: "arm", 9: "amd64", 12: "arm64"}

Progress = Callable[[int, int], None]


class OsLibError(Exception):
    pass


# ---------- Erkennung ----------

def is_iso_name(name: str) -> bool:
    return name.lower().endswith(SUFFIXES) and not name.startswith(".")


def _boot_sector(fh) -> tuple[bool, bool]:
    """(hybrid, gpt): Partitionstabelle im Systembereich → per DD auf den Stick schreibbar."""
    fh.seek(0)
    head = fh.read(1024)
    if len(head) < 1024:
        return False, False
    gpt = head[512:520] == b"EFI PART"
    mbr = head[510:512] == b"\x55\xaa" and any(head[446 + 16 * i + 4] for i in range(4))
    return mbr or gpt, gpt


def _volume_id(fh) -> str:
    fh.seek(16 * 2048)
    pvd = fh.read(2048)
    if pvd[1:6] != b"CD001":
        return ""
    return pvd[40:72].decode("ascii", errors="replace").strip()


def wim_xml(read: Callable[[int, int], bytes]) -> str:
    """XML-Beschreibung einer WIM/ESD-Datei; read(offset, länge) liest aus der Datei."""
    header = read(0, 208)
    if header[:8] != b"MSWIM\0\0\0":
        raise OsLibError("Keine WIM-Datei")
    size = int.from_bytes(header[0x48:0x4F], "little")
    offset = struct.unpack_from("<Q", header, 0x50)[0]
    if not size or size > 64 * 1024 * 1024:
        raise OsLibError("WIM ohne XML-Beschreibung")
    data = read(offset, size)
    return data.decode("utf-16-le", errors="replace").lstrip("\ufeff")


def parse_wim_xml(text: str) -> list[dict]:
    root = ET.fromstring(text)
    editions = []
    for img in root.findall("IMAGE"):
        win = img.find("WINDOWS")

        def val(path: str, base=win) -> str:
            node = base.find(path) if base is not None else None
            return (node.text or "").strip() if node is not None else ""

        build = int(val("VERSION/BUILD") or 0)
        editions.append({"index": int(img.get("INDEX", "0") or 0),
                         "name": val("DISPLAYNAME", img) or val("NAME", img),
                         "edition_id": val("EDITIONID"), "build": build,
                         "major": int(val("VERSION/MAJOR") or 0),
                         "arch": WIM_ARCH.get(int(val("ARCH") or -1), val("ARCH")),
                         "language": val("LANGUAGES/DEFAULT")})
    return editions


def windows_title(editions: list[dict]) -> tuple[str, str]:
    """(Produkt, Version), z. B. („Windows 11“, „24H2“)."""
    if not editions:
        return "Windows", ""
    build, major = editions[0]["build"], editions[0]["major"]
    if major == 10 or build >= 10240:
        product = "Windows 11" if build >= 22000 else "Windows 10"
    elif major == 6:
        product = "Windows 8.1" if build >= 9600 else "Windows 8" if build >= 9200 else "Windows 7"
    else:
        product = "Windows"
    return product, WINDOWS_RELEASES.get(build, str(build) if build else "")


def _inspect_windows(path: Path) -> dict | None:
    try:
        with udf.UdfImage.open(str(path)) as img:
            wim = next((e for e in (img.lookup(f"/sources/install.{x}") for x in ("wim", "esd", "swm")) if e), None)
            if wim is None:
                return None
            xml = wim_xml(lambda off, n: img.read(wim, off, n))
            editions = parse_wim_xml(xml)
            uefi = img.lookup("/efi/boot/bootx64.efi") is not None or img.lookup("/efi/boot/bootaa64.efi") is not None
            bios = img.lookup("/bootmgr") is not None
            name = wim.name
    except (udf.UdfError, OsLibError, ET.ParseError, OSError):
        return None
    product, version = windows_title(editions)
    langs = sorted({e["language"] for e in editions if e["language"]})
    arch = editions[0]["arch"] if editions else ""
    title = " ".join(p for p in (product, version) if p) + (f" ({', '.join(langs)})" if langs else "")
    return {"family": "windows", "title": title, "uefi": uefi, "bios": bios, "format": "udf",
            "windows": {"product": product, "version": version, "arch": arch, "languages": langs,
                        "wim": name, "wim_size": wim.size, "editions": editions}}


def _xorriso_paths(path: Path) -> list[str]:
    try:
        r = subprocess.run(["xorriso", "-indev", str(path), "-find", "/"], capture_output=True, text=True,
                           timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return []
    result = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if len(line) >= 2 and line[0] == line[-1] == "'":
            result.append(line[1:-1].replace("'\"'\"'", "'"))
    return result


def _xorriso_read(path: Path, inner: str, limit: int = 65536) -> str:
    with tempfile.TemporaryDirectory(prefix="okula-osinfo-") as tmp:
        out = Path(tmp) / "f"
        try:
            subprocess.run(["xorriso", "-osirrox", "on", "-indev", str(path), "-extract", inner, str(out)],
                           capture_output=True, timeout=60)
            return out.read_bytes()[:limit].decode("utf-8", errors="replace") if out.is_file() else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""


def linux_title(info: str) -> str:
    """„Ubuntu 24.04.1 LTS "Noble Numbat" - Release amd64 (…)“ → „Ubuntu 24.04.1 LTS“."""
    first = info.strip().splitlines()[0] if info.strip() else ""
    name = re.sub(r'\s*"[^"]*"', "", first.split(" - ")[0]).strip()
    extra = first.split(" - ", 1)[1] if " - " in first else ""
    for word, label in (("NETINST", "Netinstall"), ("DVD", "DVD"), ("live", "Live"), ("Live", "Live"),
                        ("server", "Server"), ("Server", "Server")):
        if word in extra and label not in name:
            return f"{name} ({label})"
    return name


def _inspect_linux(path: Path) -> dict | None:
    paths = _xorriso_paths(path)
    if not paths:
        return None
    lower = {p.lower() for p in paths}
    uefi = any(p.startswith("/efi/boot/boot") and p.endswith(".efi") for p in lower)
    bios = any(p.startswith(("/isolinux/", "/syslinux/", "/boot/grub/i386-pc")) for p in lower)
    info, distro, kind, version = "", "", "", ""
    if "/.disk/info" in lower:
        info = _xorriso_read(path, next(p for p in paths if p.lower() == "/.disk/info"))
    if "/casper" in lower:
        kind = "casper"
    elif "/install.amd" in lower or "/install" in lower and "/dists" in lower:
        kind = "debian-installer"
    elif "/live" in lower:
        kind = "debian-live"
    elif "/images/install.img" in lower:
        kind = "anaconda"  # Fedora Everything/Server, Rocky, Alma … – Installer mit Kickstart
    elif "/liveos/squashfs.img" in lower:
        kind = "fedora-live"  # Live-Medium (Fedora Workstation Live, Nobara …): Installer im Live-System
    extra = {}
    if kind in ("anaconda", "fedora-live"):
        tree = _xorriso_read(path, next((p for p in paths if p.lower() == "/.treeinfo"), "/.treeinfo"))
        names = dict(re.findall(r"^(name|version)\s*=\s*(.+)$", tree, re.M))
        if names:
            info = info or f"{names.get('name', '')} {names.get('version', '')}".strip()
        info = info or _volume_name(path)
        extra = {"repo": any(p.endswith("/repodata") for p in lower),  # DVD: Pakete auf der ISO
                 "kernel": next((p for p in paths if p.lower() == "/images/pxeboot/vmlinuz"), ""),
                 "initrd": next((p for p in paths if p.lower() == "/images/pxeboot/initrd.img"), ""),
                 "calamares": any("calamares" in p for p in lower)}
    low = info.lower()
    for d in ("ubuntu", "kubuntu", "xubuntu", "debian", "nobara", "fedora", "linux mint", "rocky", "almalinux",
              "red hat", "centos", "opensuse", "proxmox", "kali"):
        if d in low:
            distro = d
            break
    if kind == "casper" and not distro:
        distro = "ubuntu"
    m = re.search(r"\b(\d+(?:\.\d+)+)\b", info)
    version = m.group(1) if m else ""
    linux_like = kind or distro or "/boot/grub/grub.cfg" in lower or "/isolinux/isolinux.cfg" in lower
    if not linux_like:
        return {"family": "other", "title": "", "uefi": uefi, "bios": bios, "format": "iso9660"}
    return {"family": "linux", "title": linux_title(info) if info else "", "uefi": uefi, "bios": bios,
            "format": "iso9660", "linux": {"distro": distro, "kind": kind, "version": version, "info": info.strip(),
                                           **extra}}


def _volume_name(path: Path) -> str:
    """Volume-ID lesbar: „Fedora-E-dvd-x86_64-42“ → „Fedora E dvd x86_64 42“."""
    with open(path, "rb") as fh:
        return _volume_id(fh).replace("-", " ").replace("_", " ").strip()


def inspect(path: str | Path) -> dict:
    """Was ist das für ein Medium? Liest nur wenige MB, auch bei grossen ISOs."""
    path = Path(path)
    name = path.name.lower()
    meta: dict = {"version": META_VERSION, "size": path.stat().st_size, "mtime": int(path.stat().st_mtime),
                  "inspected": datetime.now().isoformat(timespec="seconds")}
    if not name.endswith(".iso"):
        # Disk-Abbild (.img, auch komprimiert): wird 1:1 auf den Stick geschrieben
        meta.update(family="other", title="Disk-Abbild", hybrid=True, uefi=False, bios=False, format="img",
                    compression=next((c for c in ("xz", "gz", "zst", "bz2") if name.endswith("." + c)), ""))
        return meta
    with open(path, "rb") as fh:
        hybrid, gpt = _boot_sector(fh)
        volume = _volume_id(fh)
    meta.update(hybrid=hybrid, gpt=gpt, volume_id=volume)
    found = _inspect_windows(path) or _inspect_linux(path) or {"family": "other", "title": "", "uefi": False,
                                                               "bios": False, "format": ""}
    meta.update(found)
    if not meta.get("title"):
        meta["title"] = volume or path.stem
    return meta


def installable(meta: dict) -> bool:
    """Lässt sich direkt aus dem Tool auf ein Gerät installieren (Windows 10/11, Ubuntu, Debian)."""
    return not install_reason(meta)


def install_reason(meta: dict) -> str:
    """Warum ein Medium nicht direkt installierbar ist („“ = geht) – für Dialog und Details."""
    if meta.get("family") == "windows":
        w = meta.get("windows") or {}
        if w.get("product") not in ("Windows 10", "Windows 11"):
            return f"{w.get('product') or 'Windows'}: nur Windows 10/11 lassen sich direkt installieren"
        if w.get("arch") != "amd64":
            return f"{w.get('arch') or 'unbekannte'} Architektur – direkt nur 64-Bit (x64)"
        return ""
    if meta.get("family") == "linux":
        from okula_recovery import linuxsetup  # Ubuntu ab 24.04 (Autoinstall), Debian mit Netzwerk-Installer
        return linuxsetup.reason(meta)
    return "Kein erkanntes Betriebssystem – nur als Boot-Stick"


def stick_modes(meta: dict) -> list[str]:
    """Mögliche Schreibarten für einen Boot-Stick, empfohlene zuerst."""
    modes = []
    if meta.get("family") == "windows":
        modes.append("windows")
    if meta.get("hybrid"):
        modes.append("dd")
    if meta.get("family") != "windows" and meta.get("uefi") and meta.get("format") == "iso9660":
        modes.append("files")
    return modes


def describe(meta: dict) -> str:
    """Kurzbeschreibung für die Typ-Spalte."""
    fam = meta.get("family")
    if fam == "windows":
        n = len(meta["windows"].get("editions") or [])
        return f"Windows-ISO · {n} Edition{'en' if n != 1 else ''}" if n else "Windows-ISO"
    if fam == "linux":
        return "Linux-ISO" + (" · Live" if meta["linux"].get("kind") in ("casper", "debian-live") else "")
    if meta.get("format") == "img":
        return "Disk-Abbild"
    return "ISO" + (" · bootfähig" if meta.get("hybrid") or meta.get("uefi") else "")


# ---------- Ablage ----------

@dataclass
class IsoInfo:
    path: Path
    rel: str                         # Ordner relativ zu OS/, z. B. „Windows/Kunde A“
    size: int
    mtime: datetime
    meta: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def family(self) -> str:
        return self.meta.get("family", "other")

    @property
    def title(self) -> str:
        return self.meta.get("title") or self.path.stem

    @property
    def display(self) -> str:
        """Name in der Übersicht: selbst vergebener Name (Umbenennen), sonst das erkannte Medium."""
        return self.meta.get("label") or self.title


@dataclass
class OsFolder:
    name: str
    rel: str
    folders: list["OsFolder"] = field(default_factory=list)
    isos: list[IsoInfo] = field(default_factory=list)

    def count(self) -> int:
        return len(self.isos) + sum(f.count() for f in self.folders)

    def size(self) -> int:
        return sum(i.size for i in self.isos) + sum(f.size() for f in self.folders)

    def all_isos(self) -> list[IsoInfo]:
        return self.isos + [i for f in self.folders for i in f.all_isos()]


def meta_path(iso: Path) -> Path:
    return iso.with_name(f".{iso.name}{META_SUFFIX}")


def load_meta(iso: Path) -> dict | None:
    """Gespeicherte Beschreibung, wenn sie noch zur Datei passt (Grösse, Zeit, Erkennungsversion)."""
    try:
        meta = json.loads(meta_path(iso).read_text())
        st = iso.stat()
    except (OSError, ValueError):
        return None
    if meta.get("version") != META_VERSION or meta.get("size") != st.st_size or meta.get("mtime") != int(st.st_mtime):
        return None
    return meta


def save_meta(iso: Path, meta: dict) -> None:
    tmp = meta_path(iso).with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    tmp.replace(meta_path(iso))


def ensure_layout(root: str | Path) -> Path:
    """OS-Ordner mit den Kategorien anlegen (beim Verbinden des NAS)."""
    base = nasfiles.resolve(root, OS_DIR)
    base.mkdir(exist_ok=True)
    for name in CATEGORIES.values():
        nasfiles.resolve(root, f"{OS_DIR}/{name}").mkdir(exist_ok=True)
    return base


def _dir(root: str | Path, rel: str) -> Path:
    if len(PurePosixPath(rel).parts) > MAX_DEPTH:
        raise OsLibError(f"Mehr als {MAX_DEPTH} Ebenen sind nicht möglich")
    return nasfiles.resolve(root, f"{OS_DIR}/{rel}" if rel else OS_DIR)


def scan(root: str | Path, inspect_missing: bool = True) -> list[OsFolder]:
    """Kategorien mit Unterordnern und ISOs; fehlende Beschreibungen werden erstellt (dauert kurz)."""
    base = _dir(root, "")
    if not base.is_dir():
        return []

    def read(path: Path, rel: str) -> OsFolder:
        folder = OsFolder(path.name, rel)
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except OSError:
            return folder
        for e in entries:
            if e.name.startswith("."):
                continue
            p = Path(e.path)
            if e.is_dir(follow_symlinks=False):
                if len(PurePosixPath(rel).parts) < MAX_DEPTH:
                    folder.folders.append(read(p, f"{rel}/{e.name}"))
            elif e.is_file(follow_symlinks=False) and is_iso_name(e.name):
                st = e.stat(follow_symlinks=False)
                meta = load_meta(p)
                if meta is None and inspect_missing:
                    try:
                        meta = inspect(p)
                        old = _old_meta(p)
                        if old.get("size") == meta["size"]:  # Prüfsumme und eigener Name bleiben erhalten
                            meta.update({k: old[k] for k in ("sha256", "label") if old.get(k)})
                        save_meta(p, meta)
                    except OSError:
                        meta = {}
                folder.isos.append(IsoInfo(p, rel, st.st_size, datetime.fromtimestamp(st.st_mtime), meta or {}))
        folder.isos.sort(key=lambda i: i.name.lower())
        return folder

    result = []
    for name in CATEGORIES.values():
        p = base / name
        if p.is_dir() and not p.is_symlink():
            result.append(read(p, name))
    return result


def _old_meta(iso: Path) -> dict:
    try:
        return json.loads(meta_path(iso).read_text())
    except (OSError, ValueError):
        return {}


def find(root: str | Path, iso_path: str | Path) -> tuple[Path, str]:
    """ISO-Pfad prüfen: muss unter NAS/OS liegen. Gibt (Pfad, Ordner-rel) zurück."""
    base = _dir(root, "").resolve()
    p = Path(iso_path)
    try:
        rel = p.parent.resolve().relative_to(base)
    except ValueError:
        raise OsLibError("ISO liegt nicht im OS-Ordner des NAS") from None
    if not is_iso_name(p.name) or not p.is_file() or p.is_symlink():
        raise OsLibError(f"„{p.name}“ ist keine ISO-Datei")
    return p, str(rel)


def make_folder(root: str | Path, parent: str, name: str) -> str:
    if not parent:
        raise OsLibError("Eigene Ordner bitte innerhalb von Windows, Linux oder Sonstige anlegen")
    rel = f"{parent}/{nasfiles.validate_name(name, new=True)}"
    path = _dir(root, rel)
    if nasfiles.name_taken(path):
        raise OsLibError(f"„{path.name}“ existiert bereits")
    path.mkdir()
    return rel


def rename_folder(root: str | Path, rel: str, new_name: str) -> str:
    if "/" not in rel:
        raise OsLibError("Die Kategorien Windows, Linux und Sonstige bleiben bestehen")
    new_rel = f"{rel.rsplit('/', 1)[0]}/{nasfiles.validate_name(new_name, new=True)}"
    src, dst = _dir(root, rel), _dir(root, new_rel)
    if nasfiles.name_taken(dst, ignore=src):
        raise OsLibError(f"„{dst.name}“ existiert bereits")
    src.rename(dst)
    return new_rel


def delete_folder(root: str | Path, rel: str) -> None:
    if "/" not in rel:
        raise OsLibError("Die Kategorien Windows, Linux und Sonstige bleiben bestehen")
    path = _dir(root, rel)
    entries = list(path.iterdir())
    if any(not e.name.startswith(".") for e in entries):
        raise OsLibError(f"„{path.name}“ ist nicht leer")
    for e in entries:  # verwaiste Beschreibungen
        e.unlink()
    path.rmdir()


def _free_name(dest: Path, name: str) -> Path:
    stem, dot, ext = name.partition(".")
    candidate, n = dest / name, 2
    while candidate.exists() or candidate.is_symlink():
        candidate = dest / f"{stem} ({n}){dot}{ext}"
        n += 1
    return candidate


def move_iso(root: str | Path, iso_path: str | Path, dest_rel: str) -> Path:
    src, rel = find(root, iso_path)
    if rel == dest_rel:
        return src
    dest = _dir(root, dest_rel)
    if not dest.is_dir():
        raise OsLibError("Zielordner nicht gefunden")
    target = _free_name(dest, src.name)
    meta = meta_path(src)
    src.rename(target)
    if meta.exists():
        meta.rename(meta_path(target))
    return target


def rename_iso(root: str | Path, iso_path: str | Path, new_name: str) -> Path:
    src, _rel = find(root, iso_path)
    new_name = nasfiles.validate_name(new_name, new=True)
    if not is_iso_name(new_name):
        new_name += "".join(s for s in SUFFIXES if src.name.lower().endswith(s))[-8:] or ".iso"
    target = src.with_name(new_name)
    if nasfiles.name_taken(target, ignore=src):
        raise OsLibError(f"„{new_name}“ existiert bereits")
    old_meta = _old_meta(src)
    meta = meta_path(src)
    src.rename(target)
    if meta.exists():
        meta.rename(meta_path(target))
    if old_meta:  # der neue Name erscheint in der Übersicht (statt des erkannten Titels)
        old_meta["label"] = _strip_suffix(new_name)
        save_meta(target, old_meta)
    return target


def _strip_suffix(name: str) -> str:
    low = name.lower()
    for s in sorted(SUFFIXES, key=len, reverse=True):
        if low.endswith(s):
            return name[:-len(s)]
    return name


def delete_iso(root: str | Path, iso_path: str | Path) -> None:
    src, _rel = find(root, iso_path)
    src.unlink()
    meta_path(src).unlink(missing_ok=True)


# ---------- Hochladen und Prüfsummen ----------

def add_iso(root: str | Path, source: str | Path, dest_rel: str | None, progress: Progress,
            cancel: threading.Event) -> Path:
    """ISO aufs NAS kopieren (SHA256 nebenbei) und beschreiben. dest_rel None = Kategorie automatisch."""
    source = Path(source)
    if not source.is_file() or not is_iso_name(source.name):
        raise OsLibError(f"„{source.name}“ ist keine ISO- oder IMG-Datei")
    meta = inspect(source)
    rel = dest_rel or CATEGORIES[meta["family"]]
    ensure_layout(root)
    dest = _dir(root, rel)
    if not dest.is_dir():
        raise OsLibError("Zielordner nicht gefunden")
    size = source.stat().st_size
    free = shutil.disk_usage(dest).free
    if free < size + 1024**3:
        raise OsLibError(f"Zu wenig Platz auf dem NAS: {free / 1000**3:.1f} GB frei, nötig {size / 1000**3:.1f} GB")
    target = _free_name(dest, source.name)
    partial = target.with_name(f".{target.name}.partial")
    h = hashlib.sha256()
    done = 0
    try:
        with open(source, "rb") as fin, open(partial, "wb") as fout:
            while chunk := fin.read(8 * 1024 * 1024):
                if cancel.is_set():
                    raise OsLibError("Abgebrochen")
                fout.write(chunk)
                h.update(chunk)
                done += len(chunk)
                progress(done, size)
            fout.flush()
            os.fsync(fout.fileno())
        os.utime(partial, (source.stat().st_atime, source.stat().st_mtime))
        partial.rename(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    st = target.stat()
    meta.update(size=st.st_size, mtime=int(st.st_mtime), sha256=h.hexdigest())
    save_meta(target, meta)
    return target


def checksums(path: str | Path, progress: Progress, cancel: threading.Event) -> dict[str, str]:
    """MD5, SHA-1, SHA-256 und SHA-512 in einem Durchgang; SHA-256 wird in der Beschreibung gemerkt."""
    path = Path(path)
    hashes = {n: hashlib.new(n) for n in ("md5", "sha1", "sha256", "sha512")}
    size, done = path.stat().st_size, 0
    with open(path, "rb") as fh:
        while chunk := fh.read(8 * 1024 * 1024):
            if cancel.is_set():
                raise OsLibError("Abgebrochen")
            for h in hashes.values():
                h.update(chunk)
            done += len(chunk)
            progress(done, size)
    result = {n: h.hexdigest() for n, h in hashes.items()}
    meta = load_meta(path)
    if meta is not None:
        meta["sha256"] = result["sha256"]
        try:
            save_meta(path, meta)
        except OSError:
            pass
    return result
