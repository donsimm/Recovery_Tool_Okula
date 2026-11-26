"""Farbe für Ordner in der Geräteliste und im Archiv (I-043).

Die Farbe steht in einer kleinen versteckten Datei im Ordner selbst ({"color": "<Schlüssel>"}). So wandert sie
beim Umbenennen und Verschieben automatisch mit. Unbekannte Schlüssel oder eine kaputte Datei gelten als „keine
Farbe“ – nie als Fehler. Die Datei beginnt mit einem Punkt und zählt nirgends als Inhalt des Ordners.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

FILE = ".okula-ordner.json"


@dataclass(frozen=True)
class Color:
    key: str
    name: str       # deutscher Name im Menü
    light: str      # Farbwert im hellen Design
    dark: str       # Farbwert im dunklen Design


COLORS: tuple[Color, ...] = (
    Color("rot", "Rot", "#c62828", "#ef5350"),
    Color("orange", "Orange", "#e65100", "#ffa726"),
    Color("gelb", "Gelb", "#f9a825", "#ffee58"),
    Color("gruen", "Grün", "#2e7d32", "#66bb6a"),
    Color("tuerkis", "Türkis", "#00838f", "#26c6da"),
    Color("blau", "Blau", "#1565c0", "#42a5f5"),
    Color("violett", "Violett", "#6a1b9a", "#ba68c8"),
    Color("grau", "Grau", "#616161", "#bdbdbd"),
)
BY_KEY = {c.key: c for c in COLORS}
NONE_LABEL = "Keine Farbe"


def is_color_file(name: str) -> bool:
    return name == FILE


def get_color(folder: str | Path) -> str | None:
    """Schlüssel der Farbe des Ordners oder None (keine Datei, kaputt, unbekannter Schlüssel)."""
    path = Path(folder) / FILE
    try:
        if path.is_symlink():
            return None
        data = json.loads(path.read_text())
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    key = data.get("color") if isinstance(data, dict) else None
    return key if isinstance(key, str) and key in BY_KEY else None


def set_color(folder: str | Path, key: str | None) -> None:
    """Farbe setzen (atomar: tmp + rename); None = Farbe entfernen (Datei löschen)."""
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        raise OSError(f"Ordner nicht gefunden: {folder.name}")
    path = folder / FILE
    if key is None:
        path.unlink(missing_ok=True)
        return
    if key not in BY_KEY:
        raise ValueError(f"Unbekannte Farbe: {key}")
    tmp = folder / (FILE + ".tmp")
    tmp.write_text(json.dumps({"color": key}) + "\n")
    os.replace(tmp, path)


def only_color_file(folder: str | Path) -> bool:
    """Enthält der Ordner nichts ausser der Farbdatei (bzw. ist ganz leer)? Gilt dann als leer."""
    with os.scandir(folder) as it:
        return all(e.name in (FILE, FILE + ".tmp") for e in it)


def remove_empty(folder: str | Path) -> None:
    """Leeren Ordner löschen – eine Farbdatei darin wird mitgelöscht. Nicht leer → OSError."""
    folder = Path(folder)
    if only_color_file(folder):
        for name in (FILE, FILE + ".tmp"):
            (folder / name).unlink(missing_ok=True)
    folder.rmdir()


def hex_for(key: str | None, dark: bool) -> str:
    color = BY_KEY.get(key or "")
    if color is None:
        return ""
    return color.dark if dark else color.light
