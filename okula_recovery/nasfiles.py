"""Dateiverwaltung auf dem NAS: auflisten, Ordner anlegen, umbenennen, löschen.

Alle Pfade sind relativ zum Einhängepunkt und werden gegen ihn geprüft; nichts
ausserhalb kann angesprochen werden, Symlinks werden nie verfolgt.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

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
