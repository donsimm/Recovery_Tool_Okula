"""Software installieren (I-020): Katalog der Programme im Ordner Verteilen/Software auf dem NAS – ohne GTK.

Einträge (erscheinen von selbst, sobald sie im Ordner liegen):
- Installer-Dateien direkt in Software/ (.exe, .msi) – ein Programm je Datei;
- Unterordner – ein Programm mit mehreren Dateien (z. B. „Barco Eventmaster Toolset“): einmal festlegen, welche
  Datei der Installer ist, der ganze Ordner kommt mit. Sammelordner (z. B. „System Tools“ mit vielen kleinen
  Werkzeugen) lassen sich als „nur kopieren“ markieren: der Ordner landet auf dem öffentlichen Desktop unter
  Software\\<Ordner> (wie *Ordner senden*), installiert wird nichts.

Zu jedem Eintrag liegt daneben eine versteckte Beschreibung „.<Name>.okula.json“ (Muster oslib): Programmname,
Version, Installer-Typ, Parameter für die stille Installation, erwartete Rückgabewerte, Art (installieren, nur
kopieren, nur von Hand), Grösse und SHA-256 des Installers. Sie entsteht beim ersten Lesen des Ordners.

Erkennung ohne Ausführen (Kennungen in den ersten MB der Datei, Quellen in docs/TECHNIK.md):
- .msi → msiexec /i … /qn /norestart
- NSIS („Nullsoft“) → /S · Inno Setup → /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- ·
  InstallShield → /s /v"/qn /norestart" · WiX Burn (PE-Abschnitt .wixburn) → /quiet /norestart
- Squirrel installiert nur für den angemeldeten Benutzer → „nur von Hand“
- sonst „Parameter fehlt“ – nicht wählbar, bis Parameter hinterlegt sind.

Neue Version: gleicher Programmname (aus dem Datei-/Ordnernamen ohne Version und Architektur, z. B.
vlc-3.0.24-win64.exe ↔ vlc-3.0.23-win64.exe) → Parameter, Art und Rückgabewerte der vorigen Beschreibung werden
übernommen (Hinweis im Katalog). Auch die Beschreibung einer gelöschten alten Version zählt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from okula_recovery import distribute

SOFTWARE_DIR = "Software"
META_SUFFIX = ".okula.json"
META_FORMAT = "okula-software"
META_VERSION = 1
INSTALLER_EXT = (".exe", ".msi")
HEAD_BYTES = 8 * 1024 * 1024          # Kennungen stehen im Programmteil vor den gepackten Daten
MAX_ARGS = 1000
DEFAULT_EXIT_CODES = (0, 3010)
REBOOT_CODES = (3010, 1641)           # ERROR_SUCCESS_REBOOT_REQUIRED, ERROR_SUCCESS_REBOOT_INITIATED

# Art des Eintrags
INSTALL, COPY, MANUAL = "install", "copy", "manual"
MODES = (INSTALL, COPY, MANUAL)
# Status in der Liste (Texte wie in der Oberfläche)
READY, MISSING, HAND, COPY_ONLY = "bereit", "Parameter fehlt", "nur von Hand", "nur kopieren"

# Installer-Typ → (Anzeige, Parameter für die stille Installation)
KINDS: dict[str, tuple[str, str]] = {
    "msi": ("MSI (Windows Installer)", "/qn /norestart"),
    "nsis": ("NSIS", "/S"),
    "inno": ("Inno Setup", "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"),
    "installshield": ("InstallShield", '/s /v"/qn /norestart"'),
    "wix": ("WiX Burn", "/quiet /norestart"),
    "squirrel": ("Squirrel", ""),
    "": ("unbekannt", ""),
}
SQUIRREL_NOTE = "Squirrel installiert nur für den angemeldeten Benutzer – von Hand installieren"
FOLDER_NOTE = "Installer im Ordner wählen"

# Wörter ohne Bedeutung für den Programmnamen (Version, Architektur, „Setup“ …)
NOISE = {"setup", "install", "installer", "installation", "win", "win32", "win64", "windows", "x64", "x86", "x32",
         "amd64", "arm64", "64bit", "32bit", "bit", "full", "offline", "online", "web", "release", "final", "stable",
         "v", "x", "msi", "exe", "x86_64", "64", "32"}


class SoftwareError(Exception):
    pass


# ---------- Erkennung ----------

def _pe_sections(data: bytes) -> list[str]:
    """Namen der PE-Abschnitte (leer, wenn keine Windows-Programmdatei)."""
    if len(data) < 64 or data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        return []
    count, = struct.unpack_from("<H", data, pe + 6)
    opt_size, = struct.unpack_from("<H", data, pe + 20)
    start = pe + 24 + opt_size
    names = []
    for i in range(min(count, 96)):
        off = start + 40 * i
        if off + 40 > len(data):
            break
        names.append(data[off:off + 8].rstrip(b"\0").decode("latin-1"))
    return names


def _has(data: bytes, *texts: str) -> bool:
    """Kennung als ASCII oder UTF-16 (Ressourcen, Versionsinfo) enthalten?"""
    return any(t.encode() in data or t.encode("utf-16-le") in data for t in texts)


VERSION_KEYS = ("ProductName", "ProductVersion", "FileVersion", "FileDescription", "CompanyName")


def version_info(data: bytes) -> dict[str, str]:
    """Texte aus der Versionsinfo (VS_VERSIONINFO → StringFileInfo) – ohne die Datei auszuführen.

    Aufbau je Eintrag: wLength, wValueLength (Zeichen inkl. Abschluss), wType=1, Schlüssel (UTF-16, mit 0),
    Auffüllen auf 32 Bit ab Beginn des Eintrags, Wert (UTF-16, mit 0)."""
    out: dict[str, str] = {}
    for key in VERSION_KEYS:
        pat = key.encode("utf-16-le") + b"\0\0"
        i = data.find(pat)
        while i >= 6 and key not in out:
            length, value_len, kind = struct.unpack_from("<HHH", data, i - 6)
            j = i + len(pat)
            if (j - (i - 6)) % 4:
                j += 2
            if kind == 1 and 0 < value_len < 260 and length >= j - (i - 6):
                raw = data[j:j + 2 * value_len]
                value = raw.decode("utf-16-le", errors="replace").split("\0", 1)[0].strip()
                if value and value.isprintable():
                    out[key] = value
                    break
            i = data.find(pat, i + 1)
    return out


def detect_bytes(data: bytes, filename: str) -> dict:
    """Installer-Typ aus dem Anfang der Datei: {kind, args, mode, note, program, version}."""
    info = {"kind": "", "args": "", "mode": INSTALL, "note": "", "program": "", "version": ""}
    lower = filename.lower()
    if lower.endswith(".msi") or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        info.update(kind="msi", args=KINDS["msi"][1])
        return info
    sections = _pe_sections(data)
    if not sections and data[:2] != b"MZ":
        return info
    vi = version_info(data)
    info["program"] = vi.get("ProductName") or vi.get("FileDescription") or ""
    info["version"] = vi.get("ProductVersion") or vi.get("FileVersion") or ""
    if ".wixburn" in sections:
        kind = "wix"
    elif _has(data, "Inno Setup Setup Data", "JR.Inno.Setup", "Inno Setup"):
        kind = "inno"
    elif _has(data, "Nullsoft.NSIS", "NullsoftInst", "Nullsoft Install System"):
        kind = "nsis"
    elif _has(data, "InstallShield"):
        kind = "installshield"
    elif _has(data, "Squirrel"):
        kind = "squirrel"
    else:
        kind = ""
    info["kind"] = kind
    info["args"] = KINDS[kind][1]
    if kind == "squirrel":
        info.update(mode=MANUAL, note=SQUIRREL_NOTE)
    return info


def detect(path: str | Path) -> dict:
    """Installer-Typ einer Datei (liest nur den Anfang)."""
    path = Path(path)
    try:
        with open(path, "rb") as f:
            data = f.read(HEAD_BYTES)
    except OSError:
        data = b""
    return detect_bytes(data, path.name)


# ---------- Programmname und Version aus dem Namen ----------

VERSION_RE = re.compile(r"\d+(?:[._]\d+)+")
NUMBER_RE = re.compile(r"\d{3,}")


def split_name(name: str) -> tuple[str, str, str]:
    """Datei-/Ordnername → (Programmname, Version, Vergleichsschlüssel).

    „vlc-3.0.24-win64.exe“ → („vlc“, „3.0.24“, „vlc“); „AcroRdrDC2400221005_de_DE.exe“ →
    („AcroRdrDC“, „2400221005“, „acrordrdc-de-de“); „Firefox Setup 120.0.1.exe“ → („Firefox Setup“, „120.0.1“,
    „firefox“). Schlüssel ohne Version, Architektur und „Setup“ – leer bei Namen wie „setup.exe“."""
    stem = name
    if stem.lower().endswith(INSTALLER_EXT):
        stem = stem[:-4]
    m = VERSION_RE.search(stem) or NUMBER_RE.search(stem)
    if m:
        before, version, after = stem[:m.start()], m.group(0).replace("_", "."), stem[m.end():]
    else:
        before, version, after = stem, "", ""
    program = re.sub(r"\s+v$", "", re.sub(r"[\s._-]+", " ", before).strip()).strip() \
        or re.sub(r"[\s._-]+", " ", stem).strip()
    return program, version, name_key(before + " " + after)


def name_key(text: str) -> str:
    """Vergleichsschlüssel: Kleinbuchstaben, ohne Zahlen, Version, Architektur und Füllwörter."""
    tokens = [t for t in re.split(r"[^0-9a-z]+", text.lower()) if t]
    words = [t for t in tokens if t not in NOISE and not t.isdigit() and not re.fullmatch(r"v\d+", t)]
    return "-".join(words)


def _version_tuple(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:6])


# ---------- Beschreibung ----------

def software_dir(nas_root: str | Path) -> Path:
    return distribute.root(nas_root) / SOFTWARE_DIR


def meta_path(entry: Path) -> Path:
    return entry.with_name(f".{entry.name}{META_SUFFIX}")


def _read_meta(path: Path) -> dict | None:
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) and meta.get("format") == META_FORMAT else None


def _write_meta(entry: Path, meta: dict) -> bool:
    """Speichern (atomar); False, wenn der Ordner nicht beschreibbar ist (Liste funktioniert trotzdem)."""
    target = meta_path(entry)
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        return True
    except OSError:
        return False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def parse_exit_codes(text: str) -> list[int]:
    """„0, 3010“ → [0, 3010]; Fehler bei anderem als Zahlen."""
    codes = []
    for part in re.split(r"[\s,;]+", text.strip()):
        if not part:
            continue
        if not re.fullmatch(r"-?\d{1,10}", part) or not -2**31 <= int(part) < 2**32:
            raise SoftwareError(f"Rückgabewert „{part}“ ist keine Zahl")
        codes.append(int(part))
    if not codes:
        raise SoftwareError("Mindestens einen Rückgabewert für „erfolgreich“ angeben (meist 0)")
    return list(dict.fromkeys(codes))


def check_args(args: str) -> str:
    args = args.strip()
    if len(args) > MAX_ARGS:
        raise SoftwareError(f"Parameter zu lang (max. {MAX_ARGS} Zeichen)")
    if any(ord(c) < 32 for c in args):
        raise SoftwareError("Parameter enthalten Steuerzeichen oder Zeilenumbrüche")
    return args


@dataclass
class Entry:
    """Ein Programm im Katalog (Datei oder Ordner unter Software/)."""
    name: str                        # Datei- bzw. Ordnername = Auswahl
    is_dir: bool
    path: Path
    size: int                        # Bytes (Ordner: alle Dateien)
    meta: dict = field(default_factory=dict)
    candidates: list[str] = field(default_factory=list)   # Ordner: mögliche Installer (relativ)

    @property
    def program(self) -> str:
        return str(self.meta.get("program") or self.name)

    @property
    def version(self) -> str:
        return str(self.meta.get("program_version") or "")

    @property
    def kind(self) -> str:
        return str(self.meta.get("kind") or "")

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, KINDS[""])[0] if self.mode != COPY else "Ordner"

    @property
    def args(self) -> str:
        return str(self.meta.get("args") or "")

    @property
    def mode(self) -> str:
        mode = self.meta.get("mode")
        return mode if mode in MODES and (mode != COPY or self.is_dir) else INSTALL

    @property
    def installer(self) -> str:
        """Ordner: gewählte Datei (relativ, „/“); Datei: der Name selbst."""
        return str(self.meta.get("installer") or "") if self.is_dir else self.name

    @property
    def exit_codes(self) -> list[int]:
        codes = self.meta.get("exit_codes")
        return [int(c) for c in codes] if isinstance(codes, list) and codes else list(DEFAULT_EXIT_CODES)

    @property
    def key(self) -> str:
        return str(self.meta.get("key") or "")

    @property
    def adopted_from(self) -> str:
        return str(self.meta.get("adopted_from") or "")

    @property
    def status(self) -> str:
        if self.mode == MANUAL:
            return HAND
        if self.mode == COPY:
            return COPY_ONLY
        if self.is_dir and self.installer not in self.candidates:
            return MISSING
        return READY if self.args.strip() else MISSING

    @property
    def selectable(self) -> bool:
        return self.status in (READY, COPY_ONLY)

    @property
    def note(self) -> str:
        """Hinweis für die Liste (neue Version, Squirrel, Installer wählen)."""
        notes = []
        if self.adopted_from:
            notes.append(f"Parameter von „{self.adopted_from}“ übernommen (neue Version)")
        if self.is_dir and self.mode == INSTALL and self.installer not in self.candidates:
            notes.append(FOLDER_NOTE if self.candidates else "Kein Installer (.exe/.msi) im Ordner")
        if self.meta.get("note"):
            notes.append(str(self.meta["note"]))
        return " · ".join(notes)

    @property
    def label(self) -> str:
        """„VLC media player 3.0.24“ – für Log, Verlauf und Skript."""
        version = self.version
        return f"{self.program} {version}" if version and version not in self.program else self.program


def _folder_info(path: Path) -> tuple[int, list[str], list[tuple[str, os.stat_result]]]:
    """Grösse, Installer-Kandidaten (.exe/.msi, relativ) und alle Dateien eines Ordners (ohne Links)."""
    size, candidates, files = 0, [], []
    for dirpath, dirnames, filenames in os.walk(path):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not (here / d).is_symlink())
        for f in sorted(filenames):
            full = here / f
            try:
                st = full.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or (f.startswith(".") and f.endswith(META_SUFFIX)):
                continue
            rel = full.relative_to(path).as_posix()
            size += st.st_size
            files.append((rel, st))
            if f.lower().endswith(INSTALLER_EXT):
                candidates.append(rel)
    # Installer direkt im Ordner zuerst, dann nach Tiefe und Name
    candidates.sort(key=lambda r: (r.count("/"), r.lower()))
    return size, candidates, files


def _fresh_meta(entry_path: Path, is_dir: bool, candidates: list[str]) -> dict:
    """Neue Beschreibung: Name/Version aus dem Namen, Installer-Typ aus der Datei."""
    program, version, key = split_name(entry_path.name)
    meta = {"format": META_FORMAT, "version": META_VERSION, "program": program, "program_version": version,
            "key": key, "kind": "", "detected": "", "args": "", "exit_codes": list(DEFAULT_EXIT_CODES),
            "mode": INSTALL, "installer": "", "note": "", "adopted_from": "", "edited": False}
    installer = None
    if is_dir:
        top = [c for c in candidates if "/" not in c]
        pick = top[0] if len(top) == 1 else (candidates[0] if len(candidates) == 1 else "")
        meta["installer"] = pick
        installer = entry_path / pick if pick else None
    else:
        installer = entry_path
    if installer is not None:
        _apply_detection(meta, installer)
    return meta


def _apply_detection(meta: dict, installer: Path) -> None:
    found = detect(installer)
    meta.update(kind=found["kind"], detected=found["kind"], args=found["args"], mode=found["mode"],
                note=found["note"])
    if found["program"] and not re.fullmatch(r"[\d.\s]*", found["program"]):
        meta["program"] = found["program"]
    if found["version"] and not meta.get("program_version"):
        meta["program_version"] = found["version"]
    _stamp(meta, installer)


def _stamp(meta: dict, installer: Path | None) -> None:
    """Grösse, Zeit und SHA-256 des Installers (bzw. leer)."""
    if installer is None or not installer.is_file():
        meta.update(size=0, mtime=0, sha256="")
        return
    st = installer.stat()
    if meta.get("size") == st.st_size and meta.get("mtime") == int(st.st_mtime) and meta.get("sha256"):
        return
    try:
        digest = sha256(installer)
    except OSError:
        digest = ""
    meta.update(size=st.st_size, mtime=int(st.st_mtime), sha256=digest)


ADOPT_FIELDS = ("kind", "args", "exit_codes", "mode", "note")


def _adopt(meta: dict, name: str, others: dict[str, dict], candidates: list[str]) -> None:
    """Neue Version: Parameter der vorigen Beschreibung mit gleichem Programmnamen übernehmen."""
    key = meta.get("key") or ""
    prog = name_key(str(meta.get("program") or ""))
    matches = []
    for other_name, other in others.items():
        if other_name == name:
            continue
        same = (key and other.get("key") == key) or (prog and name_key(str(other.get("program") or "")) == prog)
        useful = other.get("mode") in (COPY, MANUAL) or str(other.get("args") or "").strip()
        if same and useful:
            matches.append((_version_tuple(str(other.get("program_version") or "")), other_name, other))
    if not matches:
        return
    _v, source_name, source = max(matches, key=lambda m: (m[0], m[1]))
    for f in ADOPT_FIELDS:
        if f in source:
            meta[f] = source[f]
    old_installer = str(source.get("installer") or "")
    if candidates and old_installer:
        # gleicher Dateiname im neuen Ordner, sonst der gleiche Name ohne Version
        same_name = [c for c in candidates if c == old_installer]
        same_key = [c for c in candidates if name_key(c) == name_key(old_installer) and name_key(c)]
        if same_name or same_key:
            meta["installer"] = (same_name or same_key)[0]
    meta["adopted_from"] = source_name


def scan(nas_root: str | Path, write: bool = True) -> list[Entry]:
    """Alle Programme im Ordner Software (fehlende Beschreibungen werden angelegt, sofern write)."""
    base = software_dir(nas_root)
    try:
        items = sorted(os.scandir(base), key=lambda e: e.name.lower())
    except OSError:
        return []
    metas: dict[str, dict] = {}       # alle Beschreibungen – auch von gelöschten Einträgen (für neue Versionen)
    raw = []
    for e in items:
        if e.name.startswith("."):
            if e.name.endswith(META_SUFFIX) and e.is_file(follow_symlinks=False):
                meta = _read_meta(Path(e.path))
                if meta is not None:
                    metas[e.name[1:-len(META_SUFFIX)]] = meta
            continue
        if e.is_symlink():
            continue
        if e.is_dir(follow_symlinks=False):
            raw.append((e.name, True))
        elif e.is_file(follow_symlinks=False) and e.name.lower().endswith(INSTALLER_EXT):
            raw.append((e.name, False))
    entries = []
    for name, is_dir in raw:
        path = base / name
        if is_dir:
            size, candidates, _files = _folder_info(path)
        else:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            candidates = []
        meta = metas.get(name)
        changed = False
        if meta is None:
            meta = _fresh_meta(path, is_dir, candidates)
            _adopt(meta, name, metas, candidates)
            changed = True
        else:
            if is_dir and not meta.get("installer") and not meta.get("edited") and meta.get("mode") == INSTALL:
                pick = _fresh_meta(path, True, candidates)        # Installer inzwischen eindeutig?
                if pick.get("installer"):
                    meta = {**pick, "program": meta.get("program") or pick["program"],
                            "adopted_from": meta.get("adopted_from", "")}
                    changed = True
            installer = (path / meta["installer"]) if is_dir and meta.get("installer") else (None if is_dir else path)
            before = (meta.get("size"), meta.get("mtime"))
            if installer is not None and installer.is_file():
                st = installer.stat()
                if (st.st_size, int(st.st_mtime)) != before:
                    if not meta.get("edited") and not meta.get("adopted_from"):
                        _apply_detection(meta, installer)      # Datei ersetzt: neu erkennen
                    else:
                        _stamp(meta, installer)                # eigene Parameter bleiben
                    changed = True
        if changed and write:
            _write_meta(path, meta)
        metas[name] = meta
        entries.append(Entry(name, is_dir, path, size, meta, candidates))
    entries.sort(key=lambda x: (x.program.lower(), _version_tuple(x.version), x.name.lower()))
    return entries


def find(entries: list[Entry], name: str) -> Entry | None:
    return next((e for e in entries if e.name == name), None)


def update(nas_root: str | Path, name: str, *, program: str | None = None, version: str | None = None,
           args: str | None = None, exit_codes: str | list[int] | None = None, mode: str | None = None,
           installer: str | None = None) -> Entry:
    """Beschreibung von Hand ändern (Reiter Dateien → Software …) und speichern."""
    entries = scan(nas_root)
    entry = find(entries, name)
    if entry is None:
        raise SoftwareError(f"„{name}“ liegt nicht (mehr) im Ordner Software")
    meta = dict(entry.meta)
    if installer is not None and entry.is_dir:
        if installer and installer not in entry.candidates:
            raise SoftwareError(f"„{installer}“ ist keine .exe/.msi im Ordner")
        if installer != meta.get("installer"):
            meta["installer"] = installer
            if installer:
                keep = {k: meta[k] for k in ("program", "program_version")}
                _apply_detection(meta, entry.path / installer)
                meta.update(keep)
            else:
                _stamp(meta, None)
    if program is not None:
        if not program.strip():
            raise SoftwareError("Programmname fehlt")
        meta["program"] = program.strip()[:120]
    if version is not None:
        meta["program_version"] = version.strip()[:60]
    if args is not None:
        meta["args"] = check_args(args)
    if exit_codes is not None:
        meta["exit_codes"] = parse_exit_codes(exit_codes) if isinstance(exit_codes, str) else \
            parse_exit_codes(",".join(str(c) for c in exit_codes))
    if mode is not None:
        if mode not in MODES or (mode == COPY and not entry.is_dir):
            raise SoftwareError("Ungültige Art")
        meta["mode"] = mode
        if mode == INSTALL and meta.get("kind") == "squirrel":
            meta["note"] = ""
    meta["edited"] = True
    if not _write_meta(entry.path, meta):
        raise SoftwareError("Beschreibung konnte nicht gespeichert werden (Ordner auf dem NAS schreibgeschützt?)")
    entry.meta = meta
    return entry


# ---------- Auswahl → was aufs Gerät kommt ----------

@dataclass
class Plan:
    entries: list[Entry] = field(default_factory=list)
    files: list[tuple] = field(default_factory=list)   # (Typ "dir"/"file", Pfad relativ zu Software, Grösse, mtime,
    #                                                     Quelle) – Aufbau wie distribute.Plan.entries
    bytes: int = 0
    missing: list[str] = field(default_factory=list)            # nicht mehr im Ordner
    blocked: list[tuple[str, str]] = field(default_factory=list)   # (Name, Status) – nicht installierbar
    renamed: list[tuple[str, str]] = field(default_factory=list)   # (gespeichert, neue Version)

    @property
    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def lines(self) -> list[str]:
        """Für das Log des Auftrags."""
        out = [f"{e.label} – {'nur kopieren (Desktop)' if e.mode == COPY else e.kind_label}"
               f" ({_size(e.size)})" for e in self.entries]
        out += [f"{old} → {new} (neue Version)" for old, new in self.renamed]
        out += [f"{n}: fehlt im Ordner Software – übersprungen" for n in self.missing]
        out += [f"{n}: {s} – übersprungen" for n, s in self.blocked]
        return out


def _size(n: int) -> str:
    return f"{n / 1000**3:.1f} GB" if n >= 1000**3 else f"{n / 1000**2:.0f} MB" if n >= 1000**2 \
        else f"{n / 1000:.0f} kB"


def resolve(entries: list[Entry], names: list[str]) -> tuple[list[Entry], list[str], list[tuple[str, str]]]:
    """Gespeicherte Auswahl (z. B. Automatisierung) → Einträge. Fehlt ein Name, gilt die neueste Version mit
    gleichem Programmnamen (die alte Datei wurde durch eine neue ersetzt)."""
    chosen, missing, renamed = [], [], []
    by_name = {e.name: e for e in entries}
    for name in names:
        entry = by_name.get(name)
        if entry is None:
            key = split_name(name)[2]
            same = [e for e in entries if key and (e.key == key or e.adopted_from == name)]
            if same:
                entry = max(same, key=lambda e: (_version_tuple(e.version), e.name))
                renamed.append((name, entry.name))
        if entry is None:
            missing.append(name)
        elif entry not in chosen:
            chosen.append(entry)
    return chosen, missing, renamed


def plan(nas_root: str | Path, names: list[str], entries: list[Entry] | None = None) -> Plan:
    """Dateien der gewählten Programme (Links und Sonderdateien bleiben auf dem NAS)."""
    entries = scan(nas_root) if entries is None else entries
    chosen, missing, renamed = resolve(entries, names)
    p = Plan(missing=missing, renamed=renamed)
    for e in chosen:
        if not e.selectable:
            p.blocked.append((e.name, e.status))
            continue
        p.entries.append(e)
        if not e.is_dir:
            st = e.path.stat()
            p.files.append(("file", e.name, st.st_size, int(st.st_mtime), e.path))
            p.bytes += st.st_size
            continue
        p.files.append(("dir", e.name, 0, 0, None))
        _size_, _cand, files = _folder_info(e.path)
        dirs = set()
        for rel, _st in files:
            dirs.update(str(d) for d in PurePosixPath(rel).parents if str(d) != ".")
        for d in sorted(dirs, key=lambda d: (d.count("/"), d)):
            p.files.append(("dir", f"{e.name}/{d}", 0, 0, None))
        for rel, st in files:
            p.files.append(("file", f"{e.name}/{rel}", st.st_size, int(st.st_mtime), e.path / rel))
            p.bytes += st.st_size
    return p


def total_size(entries: list[Entry]) -> int:
    return sum(e.size for e in entries)


def summary(entries: list[Entry]) -> str:
    """„VLC media player 3.0.24, Adobe Acrobat Reader“ – Verlauf, Auftragsliste."""
    return ", ".join(e.label for e in entries) or "nichts"


def history_text(entries: list[Entry]) -> str:
    return f"Software: {summary(entries)} (wird beim ersten Start installiert)"
