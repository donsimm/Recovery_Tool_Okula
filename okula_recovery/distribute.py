"""Ordner an Geräte senden: vordefinierte Ordner auf dem NAS → öffentlicher Desktop des Geräts.

Ablage auf dem NAS (im Reiter Dateien anpassbar):
    Verteilen/Software/        fix – wird als ganzer Ordner gesendet
    Verteilen/Test Files/      fix – wird als ganzer Ordner gesendet
    Verteilen/Content/<Projekt>/   Auswahl – nur gewählte Projekte, auf dem Desktop unter Content/<Projekt>
Auf dem Gerät: C:/Users/Public/Desktop/… (für alle Benutzer); erneut senden ersetzt den Ordner.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

DIST_DIR = "Verteilen"
FIXED = ("Software", "Test Files")
CONTENT = "Content"


class DistributeError(Exception):
    pass


def root(nas_root: str | Path) -> Path:
    return Path(nas_root) / DIST_DIR


def ensure(nas_root: str | Path) -> Path:
    """Ordnerstruktur anlegen, falls sie fehlt (vorhandene Inhalte bleiben)."""
    base = root(nas_root)
    for name in (*FIXED, CONTENT):
        (base / name).mkdir(parents=True, exist_ok=True)
    return base


def projects(nas_root: str | Path) -> list[str]:
    """Projekte unter Content (Ordner, ohne versteckte und Links), alphabetisch."""
    content = root(nas_root) / CONTENT
    try:
        return sorted((e.name for e in os.scandir(content)
                       if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")), key=str.lower)
    except OSError:
        return []


def items_for(software: bool, testfiles: bool, chosen: list[str]) -> list[str]:
    """Auswahl → Ordner relativ zu Verteilen (= Pfad auf dem Desktop)."""
    out = [name for name, on in zip(FIXED, (software, testfiles)) if on]
    out += [f"{CONTENT}/{p}" for p in chosen]
    return out


def describe(items: list[str]) -> str:
    fixed = [i for i in items if "/" not in i]
    proj = [i.split("/", 1)[1] for i in items if "/" in i]
    parts = fixed + ([f"Content: {', '.join(proj)}"] if proj else [])
    return ", ".join(parts) or "nichts"


@dataclass
class Plan:
    items: list[str]
    entries: list[tuple] = field(default_factory=list)   # (Typ, Pfad auf dem Desktop, Grösse, mtime, Quelle)
    files: int = 0
    bytes: int = 0
    missing: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)      # Links und Sonderdateien


def plan(nas_root: str | Path, items: list[str]) -> Plan:
    """Alle Dateien der gewählten Ordner; Links werden nie verfolgt (bleiben auf dem NAS)."""
    base = root(nas_root)
    p = Plan(items=list(items))
    for item in items:
        rel = PurePosixPath(item)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts or len(rel.parts) > 2 \
                or (len(rel.parts) == 2 and rel.parts[0] != CONTENT) or (len(rel.parts) == 1 and item not in FIXED):
            raise DistributeError(f"Ungültiger Ordner: {item}")
        src = base.joinpath(*rel.parts)
        if src.is_symlink() or not src.is_dir():
            p.missing.append(item)
            continue
        p.entries.append(("dir", item, 0, 0, None))
        for dirpath, dirnames, filenames in os.walk(src):
            here = Path(dirpath)
            for d in sorted(dirnames):
                full = here / d
                if full.is_symlink():
                    p.skipped.append(str(full.relative_to(base)))
                    continue
                p.entries.append(("dir", str(PurePosixPath(item) / full.relative_to(src).as_posix()), 0, 0, None))
            dirnames[:] = [d for d in sorted(dirnames) if not (here / d).is_symlink()]
            for f in sorted(filenames):
                full = here / f
                try:
                    st = full.lstat()
                except OSError:
                    p.skipped.append(str(full.relative_to(base)))
                    continue
                if not stat.S_ISREG(st.st_mode):
                    p.skipped.append(str(full.relative_to(base)))
                    continue
                p.entries.append(("file", str(PurePosixPath(item) / full.relative_to(src).as_posix()), st.st_size,
                                  int(st.st_mtime), full))
                p.files += 1
                p.bytes += st.st_size
    if p.missing and len(p.missing) == len(items):
        raise DistributeError(f"Ordner fehlen auf dem NAS: {', '.join(p.missing)}")
    p.items = [i for i in items if i not in p.missing]
    return p
