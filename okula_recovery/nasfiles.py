"""Dateiverwaltung auf dem NAS: auflisten, Ordner anlegen, umbenennen, löschen, hineinkopieren.

Alle Pfade sind relativ zum Einhängepunkt und werden gegen ihn geprüft; nichts
ausserhalb kann angesprochen werden, Symlinks werden nie verfolgt.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

# Zeichen, die SMB/Windows in Namen nicht erlaubt
FORBIDDEN_CHARS = set('/\\:*?"<>|\0')


class FileError(Exception):
    pass


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int
    mtime: datetime
    is_link: bool = False


def validate_name(name: str) -> str:
    name = name.strip()
    if not name or name in (".", ".."):
        raise FileError("Name fehlt")
    bad = sorted(c for c in set(name) if c in FORBIDDEN_CHARS)
    if bad:
        raise FileError(f"Nicht erlaubte Zeichen: {' '.join(bad)}")
    if name.endswith((" ", ".")):
        raise FileError("Name darf nicht mit Leerzeichen oder Punkt enden")
    if len(name.encode()) > 255:
        raise FileError("Name ist zu lang")
    return name


def resolve(root: str | Path, rel: str) -> Path:
    """Ordnerpfad rel unterhalb von root. „..“, absolute Pfade und Symlinks im Pfad werden abgewiesen."""
    root_path = Path(root).resolve()
    rp = PurePosixPath(rel or "")
    if rp.is_absolute() or ".." in rp.parts:
        raise FileError(f"Ungültiger Pfad: {rel}")
    path = root_path
    for part in rp.parts:
        if part == ".":
            continue
        path = path / part
        if path.is_symlink():
            raise FileError(f"Pfad enthält einen Link: {rel}")
    return path


def _entry_path(root: str | Path, rel: str, name: str) -> Path:
    """Eintrag name im Ordner rel; der Eintrag selbst darf ein Link sein (wird nie verfolgt)."""
    return resolve(root, rel) / validate_name(name)


def list_dir(root: str | Path, rel: str = "") -> list[Entry]:
    path = resolve(root, rel)
    if not path.is_dir():
        raise FileError(f"Kein Ordner: {rel or '/'}")
    entries = []
    for e in os.scandir(path):
        if e.name.startswith(".") and e.name.endswith(".okula.json"):
            continue  # Beschreibung einer ISO (Betriebssysteme) – gehört zur ISO, nicht in die Liste
        try:
            st = e.stat(follow_symlinks=False)
            is_dir = e.is_dir(follow_symlinks=False)
            entries.append(Entry(e.name, is_dir, 0 if is_dir else st.st_size,
                                 datetime.fromtimestamp(st.st_mtime), e.is_symlink()))
        except OSError:
            continue
    entries.sort(key=lambda x: (not x.is_dir, x.name.lower()))
    return entries


def make_dir(root: str | Path, rel: str, name: str) -> Path:
    path = _entry_path(root, rel, name)
    if path.exists() or path.is_symlink():
        raise FileError(f"„{name}“ existiert bereits")
    path.mkdir()
    return path


def rename(root: str | Path, rel: str, old: str, new: str) -> Path:
    src = _entry_path(root, rel, old)
    dst = _entry_path(root, rel, new)
    if not (src.exists() or src.is_symlink()):
        raise FileError(f"„{old}“ existiert nicht")
    if dst.exists() or dst.is_symlink():
        raise FileError(f"„{new}“ existiert bereits")
    src.rename(dst)
    return dst


def measure(root: str | Path, rel: str, names: list[str]) -> tuple[int, int]:
    """(Anzahl Dateien, Bytes) der gewählten Einträge – für die Rückfrage vor dem Löschen."""
    files = size = 0
    for name in names:
        p = _entry_path(root, rel, name)
        if p.is_dir() and not p.is_symlink():
            for base, _dirs, fnames in os.walk(p):
                for f in fnames:
                    files += 1
                    try:
                        size += os.lstat(os.path.join(base, f)).st_size
                    except OSError:
                        pass
        else:
            files += 1
            try:
                size += p.lstat().st_size
            except OSError:
                pass
    return files, size


def delete(root: str | Path, rel: str, names: list[str]) -> int:
    """Löscht Dateien/Ordner (rekursiv, Symlinks nur als Link). Gibt die Anzahl Einträge zurück."""
    root_path = Path(root).resolve()
    count = 0
    for name in names:
        p = _entry_path(root, rel, name)
        if p == root_path:
            raise FileError("Der NAS-Stamm kann nicht gelöscht werden")
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
        else:
            raise FileError(f"„{name}“ existiert nicht")
        count += 1
    return count


def parent(rel: str) -> str:
    p = PurePosixPath(rel or ".").parent
    return "" if str(p) == "." else str(p)


def join(rel: str, name: str) -> str:
    return str(PurePosixPath(rel) / name) if rel else name


# ---------- Hineinkopieren (Dateien/Ordner vom Server, z. B. Clonezilla-Images) ----------

COPY_CHUNK = 8 * 1024 * 1024
SPACE_RESERVE = 1024**3


@dataclass
class CopyPlan:
    sources: list[Path]
    files: int = 0
    bytes: int = 0
    skipped: list[str] = field(default_factory=list)    # Links, Sonderdateien


def plan_copy(sources: list[str | Path]) -> CopyPlan:
    """Umfang ermitteln und Namen prüfen, bevor etwas geschrieben wird."""
    plan = CopyPlan([Path(s) for s in sources])
    if not plan.sources:
        raise FileError("Nichts zum Kopieren")
    for src in plan.sources:
        if src.is_symlink() or not src.exists():
            raise FileError(f"„{src.name}“ ist kein normaler Ordner bzw. keine Datei")
        validate_name(src.name)
        if src.is_file():
            plan.files += 1
            plan.bytes += src.stat().st_size
            continue
        for base, dirs, files in os.walk(src):
            for name in dirs + files:
                try:
                    validate_name(name)
                except FileError as e:
                    raise FileError(f"{os.path.join(base, name)}: {e} – auf dem NAS nicht möglich") from None
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(base, d))]
            for name in files:
                p = os.path.join(base, name)
                if os.path.islink(p) or not os.path.isfile(p):
                    plan.skipped.append(os.path.relpath(p, src.parent))
                    continue
                plan.files += 1
                plan.bytes += os.lstat(p).st_size
    return plan


def free_name(folder: Path, name: str) -> Path:
    """„name“, sonst „name (2)“ … – bestehende Daten werden nie überschrieben."""
    target = folder / name
    if not (target.exists() or target.is_symlink()):
        return target
    stem, suffix = (name, "") if (folder / name).is_dir() else (Path(name).stem, Path(name).suffix)
    for i in range(2, 1000):
        candidate = folder / f"{stem} ({i}){suffix}"
        if not (candidate.exists() or candidate.is_symlink()):
            return candidate
    raise FileError(f"Kein freier Name für „{name}“")


def copy_in(root: str | Path, rel: str, plan: CopyPlan,
            progress: Callable[[int, int, str], None], cancel: threading.Event) -> list[str]:
    """Quellen in den NAS-Ordner rel kopieren. Jede Quelle entsteht zuerst als „.name.partial“ und wird erst
    vollständig umbenannt – ein Abbruch hinterlässt nichts Halbes. Gibt die Namen auf dem NAS zurück."""
    dest = resolve(root, rel)
    if not dest.is_dir():
        raise FileError(f"Kein Ordner: {rel or '/'}")
    free = shutil.disk_usage(dest).free
    if free < plan.bytes + SPACE_RESERVE:
        raise FileError(f"Zu wenig Platz auf dem NAS: {free / 1000**3:.1f} GB frei, nötig {plan.bytes / 1000**3:.1f} GB")
    done = 0
    last = 0.0
    created = []

    def copy_file(src: str, dst: Path, shown: str) -> None:
        nonlocal done, last
        with open(src, "rb") as fin, open(dst, "xb") as fout:
            while chunk := fin.read(COPY_CHUNK):
                if cancel.is_set():
                    raise FileError("Abgebrochen")
                fout.write(chunk)
                done += len(chunk)
                if time.monotonic() - last >= 0.3:
                    last = time.monotonic()
                    progress(done, plan.bytes, shown)
            fout.flush()
            os.fsync(fout.fileno())
        st = os.stat(src)
        os.utime(dst, (st.st_atime, st.st_mtime))

    for src in plan.sources:
        target = free_name(dest, src.name)
        partial = dest / f".{target.name}.partial"
        if partial.exists() or partial.is_symlink():
            delete(dest, "", [partial.name])  # Rest eines früheren Abbruchs
        try:
            if src.is_file():
                copy_file(str(src), partial, src.name)
            else:
                partial.mkdir()
                for base, dirs, files in os.walk(src):
                    dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(base, d)))
                    rel_dir = os.path.relpath(base, src)
                    out_dir = partial if rel_dir == "." else partial / rel_dir
                    for d in dirs:
                        (out_dir / d).mkdir()
                    for name in sorted(files):
                        p = os.path.join(base, name)
                        if os.path.islink(p) or not os.path.isfile(p):
                            continue
                        copy_file(p, out_dir / name, os.path.join(src.name, os.path.relpath(p, src)))
            partial.rename(target)
        except BaseException:
            if partial.is_dir() and not partial.is_symlink():
                shutil.rmtree(partial, ignore_errors=True)
            else:
                partial.unlink(missing_ok=True)
            raise
        created.append(target.name)
    progress(plan.bytes, plan.bytes, "")
    return created
