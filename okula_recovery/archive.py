"""Ordnerstruktur für Images auf dem NAS („Archiv“, selbst angelegt, max. 3 Ebenen).

    <NAS>/Archiv/Kunde A/Standort Zürich/PC-Buchhaltung/<Image>
    <NAS>/images/…  und alles andere ausserhalb von Archiv = „Nicht einsortiert“

Verschieben ist ein Umbenennen auf derselben Freigabe – auch grosse Images sofort.
Alle Pfade werden gegen den Einhängepunkt geprüft (nasfiles), Links nie verfolgt.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from okula_recovery import nas, nasfiles, oslib

ARCHIVE_DIR = "Archiv"
UNSORTED_DIR = "images"  # Ziel für „zurück zu Nicht einsortiert“, hier legt das Tool auch neue Images ab
MAX_DEPTH = 3


class ArchiveError(Exception):
    pass


@dataclass
class Folder:
    name: str
    rel: str                       # relativ zu Archiv, z. B. „Kunde A/Standort Zürich“
    folders: list["Folder"] = field(default_factory=list)
    images: list[nas.ImageInfo] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(PurePosixPath(self.rel).parts)

    def count(self) -> int:
        return len(self.images) + sum(f.count() for f in self.folders)

    def size(self) -> int:
        return sum(i.size for i in self.images) + sum(f.size() for f in self.folders)


@dataclass
class Tree:
    unsorted: list[nas.ImageInfo]
    folders: list[Folder]

    def all_images(self) -> list[nas.ImageInfo]:
        result = list(self.unsorted)

        def walk(fs: list[Folder]) -> None:
            for f in fs:
                result.extend(f.images)
                walk(f.folders)
        walk(self.folders)
        return result


def display_name(info: nas.ImageInfo) -> str:
    """Kurzer Name im Archiv: bei Okula-Images Maschine + Ordnername, sonst Ordner-/Dateiname."""
    if info.kind == "Disk-Image":
        try:
            meta = json.loads((info.path / nas.OKULA_META).read_text())
        except (OSError, ValueError):
            meta = {}
        machine = meta.get("machine") or ""
        model = (meta.get("disk") or {}).get("model") or ""
        name = info.path.name if not machine or machine in info.path.name else f"{machine} – {info.path.name}"
        return f"{name}  ({model})" if model else name
    return info.path.name


def _archive(root: str | Path) -> Path:
    return nasfiles.resolve(root, ARCHIVE_DIR)


def _folder_path(root: str | Path, rel: str) -> Path:
    if len(PurePosixPath(rel).parts) > MAX_DEPTH:
        raise ArchiveError(f"Mehr als {MAX_DEPTH} Ebenen sind nicht möglich")
    return nasfiles.resolve(root, str(PurePosixPath(ARCHIVE_DIR) / rel) if rel else ARCHIVE_DIR)


def scan(root: str | Path) -> Tree:
    root = Path(root)
    unsorted = nas.list_images(root, exclude=(ARCHIVE_DIR, oslib.OS_DIR))
    for info in unsorted:
        info.name = display_name(info)  # einheitlich „Maschine – Ordner (Modell)“, auch nach dem Zurückschieben
    archive = root / ARCHIVE_DIR

    def read(path: Path, rel: str) -> Folder:
        folder = Folder(path.name, rel)
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except OSError:
            return folder
        for e in entries:
            if e.name.startswith("."):
                continue
            p = Path(e.path)
            info = nas.image_at(p, root)
            if info:
                info.name = display_name(info)
                folder.images.append(info)
            elif e.is_dir(follow_symlinks=False) and not e.name.endswith(".partial") \
                    and len(PurePosixPath(rel).parts) < MAX_DEPTH:
                folder.folders.append(read(p, str(PurePosixPath(rel) / e.name) if rel else e.name))
        folder.images.sort(key=lambda i: i.mtime, reverse=True)
        return folder

    folders = read(archive, "").folders if archive.is_dir() and not archive.is_symlink() else []
    return Tree(unsorted, folders)


def make_folder(root: str | Path, parent_rel: str, name: str) -> str:
    rel = str(PurePosixPath(parent_rel) / nasfiles.validate_name(name)) if parent_rel \
        else nasfiles.validate_name(name)
    if len(PurePosixPath(rel).parts) > MAX_DEPTH:
        raise ArchiveError(f"Mehr als {MAX_DEPTH} Ebenen sind nicht möglich")
    _archive(root).mkdir(exist_ok=True)
    target = _folder_path(root, rel)
    if target.exists() or target.is_symlink():
        raise ArchiveError(f"„{target.name}“ existiert bereits")
    target.mkdir()
    return rel


def rename_folder(root: str | Path, rel: str, new_name: str) -> str:
    src = _folder_path(root, rel)
    if not rel or not src.is_dir():
        raise ArchiveError("Ordner nicht gefunden")
    parent = str(PurePosixPath(rel).parent)
    new_rel = str(PurePosixPath(parent) / nasfiles.validate_name(new_name)) if parent != "." \
        else nasfiles.validate_name(new_name)
    dst = _folder_path(root, new_rel)
    if dst.exists() or dst.is_symlink():
        raise ArchiveError(f"„{dst.name}“ existiert bereits")
    src.rename(dst)
    return new_rel


def delete_folder(root: str | Path, rel: str) -> None:
    path = _folder_path(root, rel)
    if not rel or not path.is_dir():
        raise ArchiveError("Ordner nicht gefunden")
    if any(path.iterdir()):
        raise ArchiveError(f"„{path.name}“ ist nicht leer – zuerst Images und Unterordner verschieben")
    path.rmdir()


def _height(path: Path) -> int:
    """Ordnerebenen in path inklusive path selbst (Images zählen nicht)."""
    best = 0
    for e in os.scandir(path):
        p = Path(e.path)
        if e.is_dir(follow_symlinks=False) and not nas.image_at(p, path.parent):
            best = max(best, _height(p))
    return best + 1


def _free_name(dest_dir: Path, name: str) -> Path:
    """Freier Name im Ziel: „X (2)“, bei Dateien vor den Endungen („sda (2).img.zst“)."""
    stem, dot, ext = name.partition(".")
    candidate, n = dest_dir / name, 2
    while candidate.exists() or candidate.is_symlink():
        candidate = dest_dir / f"{stem} ({n}){dot}{ext}"
        n += 1
    return candidate


def _checked_image(root: str | Path, image_path: str | Path) -> Path:
    root_path = Path(root).resolve()
    p = Path(image_path)
    rel = os.path.relpath(p, root_path)
    if rel.startswith("..") or os.path.isabs(rel):
        raise ArchiveError("Image liegt nicht auf dem NAS")
    src = nasfiles.resolve(root_path, nasfiles.parent(rel)) / p.name
    if not nas.image_at(src, root_path):
        raise ArchiveError(f"„{p.name}“ ist kein Image")
    return src


def _remove_empty_parents(path: Path, stop: Path) -> None:
    """Leere Ordner unter images/ nach dem Verschieben aufräumen (z. B. images/<Maschine>/)."""
    while path != stop and stop in path.parents:
        try:
            path.rmdir()
        except OSError:
            return
        path = path.parent


def move_image(root: str | Path, image_path: str | Path, dest_rel: str | None) -> Path:
    """Image in den Archiv-Ordner dest_rel verschieben; None = zurück zu „Nicht einsortiert“."""
    root_path = Path(root).resolve()
    src = _checked_image(root_path, image_path)
    if dest_rel is None:
        dest_dir = nasfiles.resolve(root_path, UNSORTED_DIR)
        dest_dir.mkdir(exist_ok=True)
    else:
        dest_dir = _folder_path(root_path, dest_rel)
        if not dest_rel or not dest_dir.is_dir():
            raise ArchiveError("Zielordner nicht gefunden")
    if src.parent == dest_dir:
        return src
    target = _free_name(dest_dir, src.name)
    old_parent = src.parent
    src.rename(target)
    _remove_empty_parents(old_parent, root_path / UNSORTED_DIR)
    return target


def move_folder(root: str | Path, rel: str, dest_rel: str) -> str:
    """Ordner rel (samt Inhalt) in dest_rel verschieben; "" = oberste Ebene."""
    src = _folder_path(root, rel)
    if not rel or not src.is_dir():
        raise ArchiveError("Ordner nicht gefunden")
    if dest_rel == rel or dest_rel.startswith(rel + "/"):
        raise ArchiveError("Ein Ordner kann nicht in sich selbst verschoben werden")
    dest_dir = _folder_path(root, dest_rel)
    if not dest_dir.is_dir():
        raise ArchiveError("Zielordner nicht gefunden")
    dest_depth = len(PurePosixPath(dest_rel).parts) if dest_rel else 0
    if dest_depth + _height(src) > MAX_DEPTH:
        raise ArchiveError(f"Mehr als {MAX_DEPTH} Ebenen sind nicht möglich")
    target = dest_dir / src.name
    if target.exists() or target.is_symlink():
        raise ArchiveError(f"„{src.name}“ existiert im Ziel bereits")
    src.rename(target)
    return str(PurePosixPath(dest_rel) / src.name) if dest_rel else src.name
