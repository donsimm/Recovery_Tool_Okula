"""Externe Systemwerkzeuge finden – auch in sbin-Ordnern, die nicht im PATH stehen.

Debian-Benutzer (ohne root) haben /usr/sbin nicht im PATH; sfdisk, partclone, wipefs … liegen dort.
Auf dem Agent (root) steht sbin ohnehin im PATH – dort ändert die Suche nichts.
Läuft auf Agent und Server (nur stdlib).
"""

from __future__ import annotations

import os
import shutil

SBIN_DIRS = ("/usr/local/sbin", "/usr/sbin", "/sbin")


def find_tool(name: str) -> str | None:
    """Pfad eines Programms: zuerst PATH, danach die sbin-Ordner; None = nicht vorhanden."""
    dirs = [d for d in os.environ.get("PATH", os.defpath).split(os.pathsep) if d]
    return shutil.which(name, path=os.pathsep.join([*dirs, *SBIN_DIRS]))


def resolve(argv: list[str]) -> list[str]:
    """Befehl mit vollem Pfad zum Programm; unbekannt → unverändert (Fehler kommt dann vom Aufruf)."""
    return [find_tool(argv[0]) or argv[0], *argv[1:]]
