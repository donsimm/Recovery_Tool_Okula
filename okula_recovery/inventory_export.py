"""Inventar-Export (I-013): Geräte als CSV (Excel) und PDF je Ordner oder alle in einem PDF.

- Umfang: alle Geräte, ein Ordner (mit Unterordnern) oder markierte Geräte.
- CSV: UTF-8 mit BOM, Semikolon – öffnet sich in Excel (de-CH) direkt richtig.
- PDF: eine Datei je Ordner (Name wie in der Geräteliste) oder alle gewählten Geräte in einer Datei; Kopf mit
  Ordnername und Datum, Tabelle (reportlab, Debian-Paket python3-reportlab, in install.sh).
- Windows-Schlüssel: standardmässig gar nicht, sonst nur maskiert (XXXXX-…-ABCDE). Passwörter und Schlüssel des Tools
  (NAS, Garantie, Agent) kommen nie in den Export.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from okula_recovery import devices, textnorm, warranty, win11

COLUMNS = ("Name", "Ordner", "Hersteller", "Modell", "Seriennummer", "CPU", "RAM", "Disks", "OS",
           "Win-11-tauglich", "Garantie bis", "Zuletzt verbunden", "Letztes Image", "Letztes Backup")
KEY_COLUMN = "Windows-Schlüssel (maskiert)"
UNSORTED = "Neu / nicht einsortiert"
WIN11_TEXT = {"ok": "ja", "no": "nein", "unknown": "unbekannt"}


@dataclass
class Latest:
    """Letztes Image bzw. Backup eines Geräts: Name und Zeitpunkt."""
    name: str
    when: datetime

    def text(self) -> str:
        return f"{self.when.strftime('%d.%m.%Y')} – {self.name}"


# ---------- Auswahl ----------

def select(store_devices, scope: str = "all", folder: str = "", ids: set[str] | None = None) -> list[devices.Device]:
    """scope: all | folder (inkl. Unterordner; "" = nicht einsortiert) | marked (ids)."""
    devs = list(store_devices)
    if scope == "folder":
        devs = [d for d in devs if d.folder == folder or (folder and d.folder.startswith(folder + "/"))]
    elif scope == "marked":
        devs = [d for d in devs if d.id in (ids or set())]
    return sorted(devs, key=lambda d: (d.folder.lower(), d.name.lower()))


def folder_title(rel: str) -> str:
    """Ordnername wie in der Geräteliste (letzte Ebene), „Neu / nicht einsortiert“ ohne Ordner."""
    return PurePosixPath(rel).name if rel else UNSORTED


def folder_path(rel: str) -> str:
    """„Zürich › Buchhaltung“ – voller Ort für Kopfzeile."""
    return " › ".join(PurePosixPath(rel).parts) if rel else UNSORTED


# ---------- Zeilen ----------

def _size(n) -> str:
    if not n:
        return ""
    return f"{n / 1000**4:.1f} TB" if n >= 1000**4 else f"{n / 1000**3:.0f} GB"


def disks_text(inv: dict) -> list[str]:
    """Je Disk „Modell, Grösse, SMART ok/FEHLER“."""
    out = []
    for d in inv.get("disks") or []:
        passed = (d.get("smart") or {}).get("passed")
        smart = {True: "SMART ok", False: "SMART FEHLER"}.get(passed, "SMART –")
        out.append(", ".join(p for p in (d.get("model") or d.get("name", ""), _size(d.get("size")), smart) if p))
    return out


def ram_text(inv: dict) -> str:
    return f"{inv['memory'] / 1024**3:.0f} GB" if inv.get("memory") else ""


def win11_text(inv: dict, installed: str = "") -> str:
    r = win11.check(inv)
    text = WIN11_TEXT.get(r.status, r.status)
    # Grund kurz, ohne Modellangabe in Klammern: „nein (Prozessor nicht unterstützt)“
    reasons = [re.sub(r"\s*\(.*\)$", "", x) if x.startswith("Prozessor") else x for x in r.reasons]
    text = f"{text} ({'; '.join(reasons)})" if r.status == "no" and reasons else text
    if installed:
        when = devices.short_time(installed + "T00:00")[:10] or installed
        text += f" – trotzdem installiert {when}, Updates nicht garantiert"
    return text


def warranty_text(w: dict) -> str:
    level, text = warranty.status(w)
    return "" if level == "unknown" else text


def row(dev: devices.Device, image: Latest | None = None, backup: Latest | None = None,
        with_key: bool = False) -> dict:
    inv = dev.inventory or {}
    d, cpu = inv.get("dmi") or {}, inv.get("cpu") or {}
    r = {
        "Name": dev.name,
        "Ordner": dev.folder or UNSORTED,
        "Hersteller": d.get("sys_vendor", ""),
        "Modell": " ".join(p for p in (d.get("product_name"), d.get("product_version")) if p),
        "Seriennummer": d.get("product_serial", ""),
        "CPU": cpu.get("model", ""),
        "RAM": ram_text(inv),
        "Disks": disks_text(inv),
        "OS": "; ".join(s["name"] for s in inv.get("systems") or [] if s.get("name")),
        "Win-11-tauglich": win11_text(inv, dev.win11_unsupported),
        "Garantie bis": warranty_text(dev.warranty),
        "Zuletzt verbunden": devices.short_time(dev.last_seen),
        "Letztes Image": image.text() if image else "",
        "Letztes Backup": backup.text() if backup else "",
    }
    if with_key:
        r[KEY_COLUMN] = devices.mask_key(dev.windows_key[0])
    return r


def columns(with_key: bool) -> tuple[str, ...]:
    return COLUMNS + ((KEY_COLUMN,) if with_key else ())


# ---------- Letztes Image / Backup ----------

def latest_images(root: Path | None, devs: list[devices.Device], scan=None) -> dict[str, Latest]:
    """{Geräte-ID: letztes Disk-Image} aus den Okula-Metadaten auf dem NAS (ohne NAS: leer)."""
    if root is None:
        return {}
    from okula_recovery import archive, nas
    by_agent = {a: d.id for d in devs for a in d.agent_ids}
    ids = {d.id for d in devs}
    found: dict[str, Latest] = {}
    for img in (scan or archive.scan)(root).all_images():
        if img.kind != "Disk-Image":
            continue
        try:
            src = json.loads((img.path / nas.OKULA_META).read_text()).get("source") or {}
        except (OSError, ValueError):
            continue
        dev_id = src.get("device_id") if src.get("device_id") in ids else by_agent.get(src.get("agent_id", ""))
        if dev_id and (dev_id not in found or img.mtime > found[dev_id].when):
            found[dev_id] = Latest(img.name, img.mtime)
    return found


def latest_backups(saved, devs: list[devices.Device]) -> dict[str, Latest]:
    """{Geräte-ID: letztes Backup} aus den Backups auf dem NAS (BackupInfo: manifest, device, created, note)."""
    by_name = {d.name: d.id for d in devs}
    ids = {d.id for d in devs}
    found: dict[str, Latest] = {}
    for b in saved:
        dev_id = b.manifest.get("device_id") if b.manifest.get("device_id") in ids else by_name.get(b.device)
        if dev_id and (dev_id not in found or b.created > found[dev_id].when):
            name = " ".join((b.note or "").split()) or b.summary.split(" · ")[0] or b.path.name
            found[dev_id] = Latest(name, b.created)
    return found


def build(devs: list[devices.Device], images: dict[str, Latest], backups: dict[str, Latest],
          with_key: bool = False) -> list[dict]:
    return [row(d, images.get(d.id), backups.get(d.id), with_key) for d in devs]


# ---------- Dateien ----------

def safe_name(text: str) -> str:
    text = textnorm.clean(text)     # NFC vor dem Kürzen: kein halbes „ü“ (u + Trema) am Ende
    text = re.sub(r"[^\w.\- ]+", "_", text, flags=re.UNICODE).strip(" ._")
    return re.sub(r"[\s_]+", "_", text)[:60].strip("_") or "Inventar"


def file_stem(label: str, day: date | None = None) -> str:
    return f"Inventar_{safe_name(label)}_{(day or date.today()).isoformat()}"


def cell_text(value, sep: str = " | ") -> str:
    return sep.join(value) if isinstance(value, list) else str(value or "")


def write_csv(path: Path, rows: list[dict], with_key: bool = False) -> Path:
    """UTF-8 mit BOM, Semikolon, Disks mit „ | “ getrennt."""
    cols = columns(with_key)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([cell_text(r.get(c, "")) for c in cols])
    return path


def pdf_available() -> bool:
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return False
    return True


def group_by_folder(devs: list[devices.Device], rows: list[dict]) -> dict[str, list[dict]]:
    """{Ordner-rel: Zeilen} – jeder Ordner für sich (Unterordner eigene Gruppe), „nicht einsortiert“ zuletzt."""
    groups: dict[str, list[dict]] = {}
    for dev, r in zip(devs, rows):
        groups.setdefault(dev.folder, []).append(r)
    return dict(sorted(groups.items(), key=lambda kv: (kv[0] == "", kv[0].lower())))


def write_pdf(path: Path, title: str, rows: list[dict], with_key: bool = False, day: date | None = None,
              place: str = "") -> Path:
    """A4 quer: Kopf (Ordnername, Datum, Anzahl, ggf. voller Ort), Tabelle mit allen Spalten, Seitenzahl unten."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    day = day or date.today()
    cols = columns(with_key)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=6.5, leading=7.8)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=19)
    meta = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#555555"))

    # relative Breiten, Summe 1 (Disks, CPU, OS breiter)
    weights = {"Name": 1.0, "Ordner": 0.95, "Hersteller": 0.75, "Modell": 1.0, "Seriennummer": 1.15, "CPU": 1.25,
               "RAM": 0.55, "Disks": 2.1, "OS": 1.0, "Win-11-tauglich": 1.15, "Garantie bis": 0.85,
               "Zuletzt verbunden": 0.8, "Letztes Image": 1.1, "Letztes Backup": 1.0, KEY_COLUMN: 1.5}
    page_w, _page_h = landscape(A4)
    usable = page_w - 20 * mm
    total = sum(weights[c] for c in cols)
    widths = [usable * weights[c] / total for c in cols]

    def para(value, style=cell):
        return Paragraph(escape(cell_text(value, "\n")).replace("\n", "<br/>"), style)

    data = [[para(c, head) for c in cols]] + [[para(r.get(c, "")) for c in cols] for r in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3a3a3a")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
             ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
             ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
    style += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f2f2f2")) for i in range(2, len(data), 2)]
    # Garantie farbig wie im Tool: gelb ≤ 90 Tage, rot abgelaufen
    gcol = cols.index("Garantie bis")
    for i, r in enumerate(rows, start=1):
        text = r.get("Garantie bis", "")
        if "abgelaufen" in text:
            style.append(("BACKGROUND", (gcol, i), (gcol, i), colors.HexColor("#f4c7c3")))
        elif "läuft in" in text:
            style.append(("BACKGROUND", (gcol, i), (gcol, i), colors.HexColor("#fff3b0")))
    table.setStyle(TableStyle(style))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(10 * mm, 7 * mm, f"Okula Recovery Tool · Inventar {title} · {day.strftime('%d.%m.%Y')}")
        canvas.drawRightString(page_w - 10 * mm, 7 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=13 * mm, title=f"Inventar {title}",
                            author="Okula Recovery Tool")
    story = [Paragraph(escape(f"Inventar – {title}"), h1),
             Paragraph(escape(" · ".join(p for p in (
                 f"Stand: {day.strftime('%d.%m.%Y')}", f"{len(rows)} Gerät{'e' if len(rows) != 1 else ''}",
                 f"Ordner: {place}" if place and place != title else "",
                 "Windows-Schlüssel maskiert" if with_key else "") if p)), meta),
             Spacer(1, 4 * mm), table]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def export(target_dir: Path, devs: list[devices.Device], rows: list[dict], label: str, fmt_csv: bool = True,
           fmt_pdf: bool = True, with_key: bool = False, day: date | None = None,
           pdf_single: bool = False) -> list[Path]:
    """Schreibt CSV (alle gewählten Geräte) und PDF – je Ordner eine Datei oder (pdf_single) alle in einer.
    label: Titel für CSV und Einzel-PDF, z. B. „Alle Geräte“ oder der Ordnername. Gibt die Dateien zurück."""
    target_dir.mkdir(parents=True, exist_ok=True)
    written = []
    if fmt_csv:
        written.append(write_csv(target_dir / f"{file_stem(label, day)}.csv", rows, with_key))
    if fmt_pdf and pdf_single:
        written.append(write_pdf(target_dir / f"{file_stem(label, day)}.pdf", label, rows, with_key, day))
    elif fmt_pdf:
        for rel, group in group_by_folder(devs, rows).items():
            # Dateiname mit vollem Pfad, damit zwei „Buchhaltung“ in verschiedenen Ordnern sich nicht überschreiben
            written.append(write_pdf(target_dir / f"{file_stem(rel or UNSORTED, day)}.pdf", folder_title(rel),
                                     group, with_key, day, folder_path(rel)))
    return written
