"""Image prüfen (I-007): Okula- und Clonezilla-Images auf dem Server prüfen – nur auf Knopfdruck, kein Zeitplan.

- Okula-Image: SHA256 jeder Datei gegen okula-image.json (agentclient.verify_image).
- Clonezilla-Image: jedes Partitions-Image entpacken und mit partclone.chkimg bzw. der CRC der Kompression prüfen
  (clonezilla.verify).
- Gelesen wird nur; geschrieben wird allein das Ergebnis: bei Okula-Images das Feld „check“ in okula-image.json,
  bei Clonezilla-Images die Datei okula-check.json im Image-Ordner.
Kein GTK hier.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from okula_recovery import agentclient, clonezilla, nas

CHECK_FILE = nas.CHECK_FILE           # Ergebnis bei Clonezilla-Images
OK, BROKEN, UNCHECKABLE = "ok", "broken", "uncheckable"
LABEL = {OK: "in Ordnung", BROKEN: "beschädigt", UNCHECKABLE: "nicht prüfbar"}
SYMBOL = {OK: "✔", BROKEN: "✖", UNCHECKABLE: "–"}
COLOR = {OK: "#2e7d32", BROKEN: "#c62828", UNCHECKABLE: "#757575"}

Progress = Callable[[float, str], None]     # (Anteil 0–1 dieses Images, Datei)


class Cancelled(Exception):
    pass


def kind_of(path: str | Path) -> str:
    """okula | clonezilla | "" (Image-Datei ohne Prüfsummen: nicht prüfbar)."""
    p = Path(path)
    if p.is_dir() and (p / agentclient.IMAGE_META).is_file():
        return "okula"
    if p.is_dir() and clonezilla.is_clonezilla(p):
        return "clonezilla"
    return ""


def _result(status: str, file: str = "", message: str = "", seconds: float = 0.0) -> dict:
    return {"status": status, "date": datetime.now().isoformat(timespec="seconds"), "file": file,
            "message": message, "seconds": round(seconds, 1)}


def _broken_file(message: str) -> str:
    """Dateiname aus „Prüfsumme von X stimmt nicht“ bzw. „Image beschädigt: sda1 (…)“."""
    m = re.search(r"Prüfsumme von (\S+) stimmt nicht", message) or re.search(r"beschädigt: (\S+)", message)
    return m.group(1) if m else ""


def check(path: str | Path, progress: Progress | None = None, cancel: threading.Event | None = None) -> dict:
    """Prüft ein Image und gibt das Ergebnis zurück (speichert nicht). Cancelled bei Abbruch."""
    path = Path(path)
    cancel = cancel or threading.Event()
    report = progress or (lambda _f, _n: None)
    started = time.monotonic()
    kind = kind_of(path)

    def on_event(ev: dict, base: float = 0.0, share: float = 1.0) -> None:
        if ev.get("phase") == "verify":
            report(base + share * float(ev.get("fraction", 0.0)), str(ev.get("file", "")))

    try:
        if kind == "okula":
            try:
                raw = json.loads((path / agentclient.IMAGE_META).read_text())
            except (OSError, ValueError) as e:
                return _result(BROKEN, agentclient.IMAGE_META, f"Beschreibung unlesbar: {e}", time.monotonic() - started)
            missing = [str(f.get("name")) for f in raw.get("files", []) if isinstance(f, dict)
                       and not (path / str(f.get("name"))).is_file()]
            if missing:
                return _result(BROKEN, missing[0], f"Datei fehlt: {missing[0]}", time.monotonic() - started)
            meta = agentclient.load_image(path)
            agentclient.verify_image(path, meta, on_event, cancel)
        elif kind == "clonezilla":
            disks = clonezilla.disks(path)
            if not disks:
                return _result(UNCHECKABLE, "", "Clonezilla-Image ohne Disk", time.monotonic() - started)
            for i, disk in enumerate(disks):
                source = clonezilla.build(path, disk)
                clonezilla.verify(source, lambda ev, i=i: on_event(ev, i / len(disks), 1 / len(disks)), cancel)
        else:
            return _result(UNCHECKABLE, "", "Image-Datei ohne Prüfsummen – nur Okula- und Clonezilla-Images "
                                            "lassen sich prüfen", time.monotonic() - started)
    except (agentclient.AgentError, clonezilla.ClonezillaError) as e:
        if cancel.is_set():
            raise Cancelled() from None
        message = str(e)
        if "beschädigt" in message:
            return _result(BROKEN, _broken_file(message), message, time.monotonic() - started)
        return _result(UNCHECKABLE, "", message, time.monotonic() - started)
    except OSError as e:
        if cancel.is_set():
            raise Cancelled() from None
        name = Path(getattr(e, "filename", "") or "").name
        return _result(BROKEN, name, f"Lesefehler: {e.strerror or e}", time.monotonic() - started)
    if cancel.is_set():
        raise Cancelled()
    report(1.0, "")
    return _result(OK, seconds=time.monotonic() - started)


# ---------- Ergebnis speichern / lesen ----------

def _write_json(target: Path, data: dict) -> None:
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, target)


def save(path: str | Path, result: dict) -> None:
    """Okula: Feld „check“ in okula-image.json (Rest unverändert); Clonezilla: okula-check.json."""
    path = Path(path)
    kind = kind_of(path)
    if kind == "okula":
        meta_file = path / agentclient.IMAGE_META
        meta = json.loads(meta_file.read_text())
        meta["check"] = result
        _write_json(meta_file, meta)
    elif kind == "clonezilla":
        _write_json(path / CHECK_FILE, result)


def load(path: str | Path) -> dict | None:
    path = Path(path)
    try:
        if (path / agentclient.IMAGE_META).is_file():
            return json.loads((path / agentclient.IMAGE_META).read_text()).get("check")
        if (path / CHECK_FILE).is_file():
            return json.loads((path / CHECK_FILE).read_text())
    except (OSError, ValueError, AttributeError):
        return None
    return None


# ---------- Anzeige ----------

def short_date(result: dict | None) -> str:
    try:
        return datetime.fromisoformat((result or {}).get("date", "")).strftime("%d.%m.%Y")
    except ValueError:
        return ""


def cell(result: dict | None) -> str:
    """Pango-Markup für die Spalte „Geprüft“: ✔ 31.10.2026 (grün), ✖ beschädigt (rot), leer = nie geprüft."""
    if not result or result.get("status") not in LABEL:
        return ""
    status = result["status"]
    text = f"{SYMBOL[status]} {short_date(result)}" if status == OK else f"{SYMBOL[status]} {LABEL[status]}"
    return f'<span foreground="{COLOR[status]}">{text}</span>'


def tooltip(result: dict | None) -> str:
    if not result or result.get("status") not in LABEL:
        return "Noch nie geprüft – Rechtsklick → „Image prüfen …“"
    lines = [f"Geprüft am {short_date(result)}: {LABEL[result['status']]}"]
    if result.get("file"):
        lines.append(f"Datei: {result['file']}")
    if result.get("message") and result["status"] != OK:
        lines.append(result["message"])
    return "\n".join(lines)


def warning(result: dict | None) -> str:
    """Hinweis beim Zurückspielen bzw. in der Automatisierung, wenn die letzte Prüfung „beschädigt“ ergab."""
    if not result or result.get("status") != BROKEN:
        return ""
    where = f" ({result['file']})" if result.get("file") else ""
    return (f"⚠ Letzte Prüfung am {short_date(result)}: Image beschädigt{where}. Zurückspielen ist möglich – "
            "vor dem Schreiben wird nochmals geprüft und bei einem Fehler abgebrochen.")


def summary(results: list[dict], cancelled: bool = False) -> str:
    """„12 Images geprüft: 11 ✔, 1 ✖“ (+ nicht prüfbar, abgebrochen)."""
    n = len(results)
    counts = {s: sum(1 for r in results if r.get("status") == s) for s in (OK, BROKEN, UNCHECKABLE)}
    text = f"{n} Image{'s' if n != 1 else ''} geprüft: {counts[OK]} ✔, {counts[BROKEN]} ✖"
    if counts[UNCHECKABLE]:
        text += f", {counts[UNCHECKABLE]} nicht prüfbar"
    return text + (" – abgebrochen" if cancelled else "")


def checkable(info: nas.ImageInfo) -> bool:
    return info.kind in ("Disk-Image", "Clonezilla")


# ---------- mehrere Images nacheinander ----------

def run(paths: list[str], on_progress: Callable[[int, int, float, str, str], None],
        on_result: Callable[[str, dict], None], cancel: threading.Event, store: bool = True) -> tuple[list, bool]:
    """Prüft die Images nacheinander. on_progress(i, n, Gesamtanteil, Image, Datei); on_result(Pfad, Ergebnis).
    Gibt (Ergebnisse, abgebrochen) zurück. Gespeichert wird jedes Ergebnis sofort (store=True)."""
    sizes = []
    for p in paths:
        try:
            sizes.append(max(1, nas._dir_size(Path(p))))
        except OSError:
            sizes.append(1)
    total = sum(sizes) or 1
    done = 0
    results = []
    for i, (path, size) in enumerate(zip(paths, sizes)):
        if cancel.is_set():
            return results, True
        name = Path(path).name

        def progress(frac: float, file: str, base=done, size=size, i=i, name=name) -> None:
            on_progress(i, len(paths), (base + frac * size) / total, name, file)

        try:
            res = check(path, progress, cancel)
        except Cancelled:
            return results, True
        if store:
            try:
                save(path, res)
            except OSError as e:
                res = dict(res, message=(res.get("message") + " · " if res.get("message") else "")
                           + f"Ergebnis nicht gespeichert: {e}")
        results.append(res)
        on_result(path, res)
        done += size
    return results, False
