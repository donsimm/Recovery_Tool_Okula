"""Spaltenbreiten der Listen merken (Geräte, Images, Dateien, Backups) – lokal je Rechner, nicht im Export.

Ablage: ~/.config/okula-recovery/spalten.json  {"geraete": {"Gerät": 260, "Status": 340, …}, …}
Kein GTK hier.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from okula_recovery import config

FILE = "spalten.json"
MIN_WIDTH, MAX_WIDTH = 24, 2000


def path() -> Path:
    return config.config_path().parent / FILE


def load() -> dict[str, dict[str, int]]:
    """Gespeicherte Breiten; Unsinn (kein dict, keine Zahl) wird ignoriert, Werte auf 24–2000 px begrenzt."""
    try:
        data = json.loads(path().read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[str, int]] = {}
    if not isinstance(data, dict):
        return out
    for view, cols in data.items():
        if isinstance(cols, dict):
            out[str(view)] = {str(t): max(MIN_WIDTH, min(MAX_WIDTH, int(w))) for t, w in cols.items()
                              if isinstance(w, (int, float)) and not isinstance(w, bool)}
    return out


def save(view: str, widths: dict[str, int]) -> None:
    """Breiten einer Liste schreiben (andere Listen bleiben unverändert)."""
    data = load()
    data[view] = {t: max(MIN_WIDTH, min(MAX_WIDTH, int(w))) for t, w in widths.items() if w > 0}
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{FILE}.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, target)
