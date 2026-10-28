"""Datei-Backup – Agent-Seite: Partitionen lesend einhängen, Dateien zum Tool schicken bzw. zurückschreiben.

Quellen kommen vom Tool als Liste {part: "/dev/sda3", path: "Users/Anna/Documents"} (path darf Platzhalter
enthalten, z. B. „Users/Anna/AppData/Local/Google/Chrome/User Data/*/Bookmarks“; leer = ganze Partition).
Pagefile, Ruhezustand, Papierkorb, Temp-Ordner und Caches werden übersprungen, Links nie verfolgt.

Zurückschreiben hängt die Zielpartition schreibend ein (NTFS über ntfs-3g – Windows muss vollständig
heruntergefahren sein, ohne Schnellstart/Ruhezustand).
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Callable

from okula_recovery import imaging, inventory, wire

WORK = Path("/run/okula-backup")
SKIP_NAMES = {"pagefile.sys", "hiberfil.sys", "swapfile.sys", "$recycle.bin", "system volume information",
              "thumbs.db", "$windows.~bt", "$windows.~ws", "$sysreset", "lost+found"}
SKIP_PATHS = ("appdata/local/temp", "appdata/local/microsoft/windows/inetcache", "appdata/local/crashdumps",
              ".cache", ".local/share/trash", "windows/temp", "windows/softwaredistribution/download")
SKIP_PATTERNS = ("~$*", "*.tmp")
WIN_SKIP_USERS = {"public", "default", "default user", "all users", "defaultuser0", "defaultuser100000"}
MAX_BROWSE = 5000

Report = Callable[[float, str, int], None]
ImagingError = imaging.ImagingError


# ---------- Einhängen ----------

class Mounts:
    """Partitionen bei Bedarf einhängen (lesend oder schreibend), am Ende alles wieder aushängen."""

    def __init__(self, write: bool = False):
        self.write = write
        self.points: dict[str, Path] = {}

    def __enter__(self) -> "Mounts":
        return self

    def __exit__(self, *_exc) -> None:
        for target in self.points.values():
            subprocess.run(["umount", str(target)], capture_output=True, timeout=120)
            try:
                target.rmdir()
            except OSError:
                pass

    def get(self, dev: str) -> Path:
        if dev in self.points:
            return self.points[dev]
        known = {p["path"]: p for d in imaging.list_disks() for p in d["partitions"]}
        part = known.get(dev)
        if part is None:
            raise ImagingError(f"Partition {dev} nicht gefunden")
        if part.get("mounted"):
            raise ImagingError(f"{dev} ist bereits eingehängt")
        fs = part.get("fstype") or inventory.probe_fstype(dev)
        if fs.lower() == "bitlocker":
            raise ImagingError(f"{dev} ist mit BitLocker verschlüsselt – nicht lesbar")
        WORK.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix=f"{Path(dev).name}-", dir=WORK))
        ok = _mount_rw(dev, fs, target) if self.write else inventory._mount_ro(dev, fs, target)
        if not ok:
            target.rmdir()
            raise ImagingError(f"{dev} ({fs or 'unbekannt'}) lässt sich nicht einhängen")
        self.points[dev] = target
        return target


def _mount_rw(dev: str, fs: str, target: Path) -> bool:
    if fs == "ntfs":
        r = subprocess.run(["ntfs-3g", "-o", "rw", dev, str(target)], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            msg = (r.stderr or r.stdout).lower()
            if "hibernat" in msg or "unclean" in msg or "fast restart" in msg:
                raise ImagingError("Windows ist im Ruhezustand bzw. Schnellstart – Windows starten und vollständig "
                                   "herunterfahren (Shift + Herunterfahren), dann erneut versuchen")
            return False
        return True
    if fs in ("ext2", "ext3", "ext4", "xfs", "btrfs", "vfat", "exfat"):
        return subprocess.run(["mount", "-t", fs, dev, str(target)], capture_output=True, timeout=60).returncode == 0
    return False


# ---------- Übersicht ----------

def _users(root: Path) -> tuple[str, list[dict]]:
    """(Art, Benutzer) – Windows: Users/*, Linux: home/* oder eine eigene /home-Partition."""
    win = next((p for p in root.iterdir() if p.name.lower() == "users" and p.is_dir()), None) \
        if root.is_dir() else None
    if win and (root / "Windows").is_dir():
        users = [{"name": p.name, "path": f"{win.name}/{p.name}"} for p in sorted(win.iterdir())
                 if p.is_dir() and not p.is_symlink() and p.name.lower() not in WIN_SKIP_USERS]
        return "windows", users
    if (root / "home").is_dir() and (root / "etc").is_dir():
        return "linux", [{"name": p.name, "path": f"home/{p.name}"} for p in sorted((root / "home").iterdir())
                         if p.is_dir() and not p.is_symlink() and p.name != "lost+found"]
    homes = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and
             any((p / f).exists() for f in (".bashrc", ".profile", ".config"))]
    if homes:  # eigene /home-Partition
        return "home", [{"name": p.name, "path": p.name} for p in sorted(homes)]
    return "", []


def profiles(busy: set[str] = frozenset()) -> list[dict]:
    """Alle lesbaren Partitionen interner Disks mit Betriebssystem und Benutzerprofilen."""
    result = []
    with Mounts() as m:
        for disk in imaging.list_disks():
            if disk["path"] in busy:
                continue
            for part in disk["partitions"]:
                fs = part.get("fstype") or inventory.probe_fstype(part["path"])
                entry = {"part": part["path"], "name": part["name"], "disk": disk["path"], "fstype": fs,
                         "size": part["size"], "label": part.get("label", ""), "os": "", "kind": "", "users": []}
                if fs.lower() == "bitlocker":
                    entry["error"] = "BitLocker – nicht lesbar"
                elif fs in inventory.RO_OPTIONS and not part.get("mounted"):
                    try:
                        root = m.get(part["path"])
                        info = inventory.inspect_root(root) or {}
                        entry["os"] = info.get("name", "")
                        entry["kind"], entry["users"] = _users(root)
                    except (ImagingError, OSError) as e:
                        entry["error"] = str(e)
                else:
                    continue
                result.append(entry)
    return result


def browse(dev: str, rel: str) -> list[dict]:
    """Inhalt eines Ordners (für „eigene Ordner“) – Ordner zuerst, Links werden nicht verfolgt."""
    with Mounts() as m:
        root = m.get(dev)
        path = _safe(root, rel) if rel else root
        entries = []
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISLNK(st.st_mode):
                        continue
                    entries.append({"name": e.name, "dir": stat.S_ISDIR(st.st_mode),
                                    "size": 0 if stat.S_ISDIR(st.st_mode) else st.st_size, "mtime": int(st.st_mtime)})
                    if len(entries) >= MAX_BROWSE:
                        break
        except OSError as e:
            raise ImagingError(f"Ordner nicht lesbar: {e}") from None
    entries.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return entries


# ---------- Dateien sammeln ----------

def _safe(root: Path, rel: str) -> Path:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ImagingError(f"Ungültiger Pfad: {rel}")
    return root.joinpath(*p.parts) if p.parts else root


def skipped_by_rule(rel: str) -> bool:
    low = rel.lower()
    parts = low.split("/")
    if any(p in SKIP_NAMES for p in parts):
        return True
    if any(low == s or low.startswith(s + "/") or f"/{s}/" in f"/{low}/" for s in SKIP_PATHS):
        return True
    return any(fnmatch.fnmatch(parts[-1], pat) for pat in SKIP_PATTERNS)


def _expand(root: Path, spec: str) -> list[Path]:
    if not spec:
        return [root]
    if any(c in spec for c in "*?["):
        return sorted(p for p in root.glob(spec) if not p.is_symlink())
    p = _safe(root, spec)
    return [p] if p.exists() and not p.is_symlink() else []


def collect(sources: list[dict], mounts: Mounts) -> tuple[list[tuple], list[tuple[str, str]]]:
    """Dateien aller Quellen: [(Gerät, Partitionsname, absoluter Pfad, rel. Pfad, Grösse, mtime)], [(Pfad, Grund)]."""
    files, skipped, seen = [], [], set()
    for src in sources:
        dev = str(src.get("part") or "")
        root = mounts.get(dev)
        name = Path(dev).name
        for start in _expand(root, str(src.get("path") or "")):
            if start.is_file():
                stack = [start]
                walk_dirs = False
            else:
                stack = [start]
                walk_dirs = True
            while stack:
                p = stack.pop()
                rel = str(p.relative_to(root))
                if rel != "." and skipped_by_rule(rel):
                    continue
                try:
                    st = p.lstat()
                except OSError as e:
                    skipped.append((f"{name}/{rel}", str(e)))
                    continue
                if stat.S_ISLNK(st.st_mode):
                    continue
                if stat.S_ISDIR(st.st_mode) and walk_dirs:
                    try:
                        stack.extend(sorted(p.iterdir(), reverse=True))
                    except OSError as e:
                        skipped.append((f"{name}/{rel}", str(e)))
                elif stat.S_ISREG(st.st_mode) and (dev, rel) not in seen:
                    seen.add((dev, rel))
                    files.append((dev, name, p, rel, st.st_size, int(st.st_mtime)))
    return files, skipped


def estimate(sources: list[dict]) -> dict:
    with Mounts() as m:
        files, skipped = collect(sources, m)
    return {"type": "estimate", "files": len(files), "bytes": sum(f[4] for f in files), "skipped": len(skipped)}


# ---------- Sichern ----------

def backup(sock, req: dict, log: Callable[[str], None] = print, report: Report | None = None) -> None:
    """Dateien der Quellen zum Tool schicken (je Datei SHA-256); Lesefehler werden gemeldet, nicht abgebrochen."""
    report = report or (lambda f, p, n: None)
    with Mounts() as m:
        files, skipped = collect(req.get("sources") or [], m)
        total = sum(f[4] for f in files) or 1
        wire.send_json(sock, {"type": "plan", "files": len(files), "bytes": total, "skipped": len(skipped)})
        log(f"Backup: {len(files)} Dateien, {total / 1000**3:.1f} GB")
        sent, done = 0, 0
        for dev, name, path, rel, size, mtime in files:
            try:
                fh = open(path, "rb")
            except OSError as e:
                skipped.append((f"{name}/{rel}", str(e)))
                continue
            with fh:
                wire.send_json(sock, {"type": "file", "path": f"{name}/{rel}", "size": size, "mtime": mtime})
                h = hashlib.sha256()
                n = 0
                error = ""
                try:
                    while chunk := fh.read(wire.CHUNK):
                        wire.send_data(sock, chunk)
                        h.update(chunk)
                        n += len(chunk)
                        sent += len(chunk)
                        report(min(1.0, sent / total), rel, sent)
                except OSError as e:  # defekter Sektor o. ä.: Datei als fehlerhaft melden, weitermachen
                    error = str(e)
                    skipped.append((f"{name}/{rel}", error))
                wire.send_json(sock, {"type": "file_end", "size": n, "sha256": h.hexdigest(), "error": error})
                done += 0 if error else 1
        wire.send_json(sock, {"type": "done", "files": done, "bytes": sent,
                              "skipped": [{"path": p, "reason": r} for p, r in skipped[:500]],
                              "skipped_count": len(skipped)})


# ---------- Zurückschreiben ----------

def _owner(root: Path, user: str) -> tuple[int, int] | None:
    try:
        for line in (root / "etc" / "passwd").read_text().splitlines():
            parts = line.split(":")
            if len(parts) > 3 and parts[0] == user:
                return int(parts[2]), int(parts[3])
    except (OSError, ValueError):
        pass
    return None


def _free_target(path: Path) -> Path:
    if not path.exists():
        return path
    n = 1
    while True:
        cand = path.with_name(f"{path.stem} (wiederhergestellt{'' if n == 1 else f' {n}'}){path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def restore_files(sock, req: dict, log: Callable[[str], None] = print, report: Report | None = None) -> None:
    """Dateien vom Tool auf eine Partition schreiben. Vorhandene Dateien bleiben (Kopie mit Zusatz), ausser
    overwrite. Linux: Besitzer = owner aus /etc/passwd der Partition."""
    report = report or (lambda f, p, n: None)
    total = int(req.get("bytes") or 0) or 1
    with Mounts(write=True) as m:
        root = m.get(str(req.get("part") or ""))
        owner = _owner(root, str(req.get("owner") or "")) if req.get("owner") else None
        overwrite = bool(req.get("overwrite"))
        wire.send_json(sock, {"type": "ready"})
        written = renamed = received = 0
        while True:
            msg = wire.recv_json(sock)
            if msg.get("type") == "end":
                break
            if msg.get("type") != "file":
                raise ImagingError(f"Unerwartete Nachricht: {msg.get('type')}")
            rel = str(msg.get("path") or "")
            dest = _safe(root, rel)
            if dest.is_symlink() or any(p.is_symlink() for p in dest.parents if root in p.parents):
                raise ImagingError(f"Ziel enthält einen Link: {rel}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            final = dest if overwrite else _free_target(dest)
            renamed += final != dest
            tmp = final.with_name(f".{final.name}.okula-tmp")
            with open(tmp, "wb") as out:
                for chunk in imaging._frames(sock, {"file": rel}):
                    out.write(chunk)
                    received += len(chunk)
                    report(min(1.0, received / total), rel, received)
            tmp.replace(final)
            mtime = int(msg.get("mtime") or 0)
            if mtime:
                os.utime(final, (mtime, mtime))
            if owner:
                os.chown(final, *owner)
                for parent in final.parents:
                    if parent == root or root not in parent.parents:
                        break
                    if parent.stat().st_uid == 0:
                        os.chown(parent, *owner)
            written += 1
        subprocess.run(["sync"])
    wire.send_json(sock, {"type": "done", "files": written, "renamed": renamed})
    log(f"Zurückgeschrieben: {written} Dateien ({renamed} mit Zusatz „wiederhergestellt“)")
