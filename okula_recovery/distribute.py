"""Ordner an Geräte senden: vordefinierte Ordner auf dem NAS → öffentlicher Desktop des Geräts.

Ablage auf dem NAS (im Reiter Dateien anpassbar):
    Verteilen/Software/<Eintrag>   Auswahl (Ä-051) – jeder Unterordner und jede Datei einzeln, auf dem Desktop
                                   unter Software/<Eintrag>; „Software“ allein = „Alle“: der ganze Ordner (Ä-053)
    Verteilen/Test Files/          fix – wird als ganzer Ordner gesendet
    Verteilen/Content/<Projekt>/   Auswahl – nur gewählte Projekte, auf dem Desktop unter Content/<Projekt>
Auf dem Gerät: C:/Users/Public/Desktop/… (für alle Benutzer); erneut senden ersetzt die gewählten Einträge –
bei „Alle“ den ganzen Ordner Software (alter Inhalt weg, Ä-053).
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

DIST_DIR = "Verteilen"
SOFTWARE = "Software"
TESTFILES = "Test Files"
FIXED = (SOFTWARE, TESTFILES)       # Ordner, die immer da sind (Software seit Ä-051 mit Auswahl der Einträge)
CONTENT = "Content"
SELECTABLE = (SOFTWARE, CONTENT)    # Ordner mit Einträgen zur Auswahl: <Ordner>/<Eintrag>
SHOW = 4                            # describe: so viele Namen je Ordner, danach „und N weitere“


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


def software_entries(nas_root: str | Path) -> list[str]:
    """Ä-051: Einträge direkt unter Software – Ordner zuerst, dann Dateien, je alphabetisch
    (ohne versteckte Einträge, Links und Sonderdateien)."""
    dirs, files = [], []
    try:
        with os.scandir(root(nas_root) / SOFTWARE) as it:
            for e in it:
                if e.name.startswith(".") or e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    dirs.append(e.name)
                elif e.is_file(follow_symlinks=False):
                    files.append(e.name)
    except OSError:
        return []
    return sorted(dirs, key=str.lower) + sorted(files, key=str.lower)


def items_for(software: bool, testfiles: bool, chosen: list[str], software_items: list[str] | None = None) -> list[str]:
    """Auswahl → Einträge relativ zu Verteilen (= Pfad auf dem Desktop).

    software_items leer bzw. None bei software=True: „Alle“ = der ganze Ordner Software (Ä-053: auf dem Gerät ganz
    ersetzt, auch später hinzugekommene Einträge) – so verhält sich auch die alte Einstellung „Software“ ohne Liste."""
    out = []
    if software:
        out += [f"{SOFTWARE}/{e}" for e in software_items] if software_items else [SOFTWARE]
    if testfiles:
        out.append(TESTFILES)
    out += [f"{CONTENT}/{p}" for p in chosen]
    return out


def software_choice(entries: list[str], all_on: bool, chosen: list[str]) -> tuple[bool, list[str]]:
    """Auswahl unter Software → (software, software_items) wie in den Einstellungen; (True, []) = „Alle“.

    Ä-053: Sind alle vorhandenen Einträge einzeln angehakt, gilt das als „Alle“ (ganzer Ordner ersetzt)."""
    if all_on or (entries and set(entries) <= set(chosen)):
        return True, []
    return bool(chosen), list(chosen)


def _short(names: list[str]) -> str:
    if len(names) <= SHOW:
        return ", ".join(names)
    return f"{', '.join(names[:SHOW - 1])} und {len(names) - SHOW + 1} weitere"


def describe(items: list[str]) -> str:
    """Kurztext für Verlauf, Log und Auftragsliste, z. B. „Software: Browser, Nvidia, Test Files, Content: A“."""
    sub = {name: [i.split("/", 1)[1] for i in items if i.startswith(f"{name}/")] for name in SELECTABLE}
    parts = []
    if SOFTWARE in items:
        parts.append(f"{SOFTWARE}: alle (Ordner ersetzt)")
    elif sub[SOFTWARE]:
        parts.append(f"{SOFTWARE}: {_short(sub[SOFTWARE])}")
    if TESTFILES in items:
        parts.append(TESTFILES)
    if sub[CONTENT]:
        parts.append(f"{CONTENT}: {_short(sub[CONTENT])}")
    return ", ".join(parts) or "nichts"


@dataclass
class Plan:
    items: list[str]                                      # was das Gerät ersetzt („Software“ = ganzer Ordner)
    entries: list[tuple] = field(default_factory=list)   # (Typ, Pfad auf dem Desktop, Grösse, mtime, Quelle)
    files: int = 0
    bytes: int = 0
    missing: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)      # Links und Sonderdateien
    requested: list[str] = field(default_factory=list)    # Auswahl ohne Fehlendes (für describe)


def _check(item: str) -> PurePosixPath:
    rel = PurePosixPath(item)
    ok = not rel.is_absolute() and ".." not in rel.parts and (
        (len(rel.parts) == 1 and item in FIXED)
        or (len(rel.parts) == 2 and rel.parts[0] in SELECTABLE and not rel.parts[1].startswith(".")))
    if not ok:
        raise DistributeError(f"Ungültiger Ordner: {item}")
    return rel


def plan(nas_root: str | Path, items: list[str], strict: bool = True) -> Plan:
    """Alle Dateien der gewählten Einträge; Links werden nie verfolgt (bleiben auf dem NAS).

    „Software“ allein („Alle“) bleibt der ganze Ordner: das Gerät ersetzt Desktop/Software komplett (Ä-053, wie vor
    Ä-051); einzelne Einträge Software/<Eintrag> ersetzen nur diese (Ä-051). Ein leerer Ordner Software wird nicht
    gesendet (sonst wäre der Ordner auf dem Gerät danach leer). Fehlende Einträge landen in missing; fehlt alles,
    gibt es bei strict einen Fehler, sonst einen leeren Plan (Automatisierung: Hinweis im Log, Rest läuft)."""
    base = root(nas_root)
    p = Plan(items=[])
    targets: dict[str, None] = {}
    whole = SOFTWARE in items
    for item in items:
        _check(item)
        if whole and item.startswith(f"{SOFTWARE}/"):
            continue                    # im ganzen Ordner enthalten
        if item == SOFTWARE and not software_entries(nas_root):
            p.missing.append(f"{SOFTWARE} (leer)")
            continue
        targets.setdefault(item)
    for item in targets:
        rel = _check(item)
        src = base.joinpath(*rel.parts)
        if src.is_symlink():
            p.missing.append(item)
            continue
        if src.is_dir():
            _add_dir(p, base, src, item)
        elif rel.parts[0] == SOFTWARE and len(rel.parts) == 2 and src.is_file():
            st = src.lstat()      # Ä-051: einzelne Datei direkt unter Software → Desktop/Software/<Datei>
            p.entries.append(("file", item, st.st_size, int(st.st_mtime), src))
            p.files += 1
            p.bytes += st.st_size
        else:
            p.missing.append(item)
            continue
        p.items.append(item)
    p.requested = list(p.items)
    if strict and not p.items and p.missing:
        raise DistributeError(f"Ordner fehlen auf dem NAS: {', '.join(p.missing)}")
    return p


def _add_dir(p: Plan, base: Path, src: Path, item: str) -> None:
    p.entries.append(("dir", item, 0, 0, None))
    for dirpath, dirnames, filenames in os.walk(src):
        here = Path(dirpath)
        if item == SOFTWARE and here == src:
            # Ä-053: „Alle“ = genau die Einträge aus der Liste (software_entries) – versteckte bleiben auf dem NAS
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            filenames = [f for f in filenames if not f.startswith(".")]
        for d in sorted(dirnames):
            full = here / d
            if full.is_symlink():
                p.skipped.append(str(full.relative_to(base)))
                continue
            p.entries.append(("dir", str(PurePosixPath(item) / full.relative_to(src).as_posix()), 0, 0, None))
        dirnames[:] = [d for d in sorted(dirnames) if not (here / d).is_symlink()]
        for f in sorted(filenames):
            if f.startswith(".") and f.endswith(".okula.json"):
                continue      # Beschreibung eines Programms (Software installieren, I-020) – bleibt auf dem NAS
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
