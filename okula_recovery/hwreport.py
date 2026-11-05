"""Hardware-Test (I-023) im Tool: Ergebnis zusammenfassen, beim Gerät speichern, PDF-Prüfprotokoll.

Bericht vom Agent (hwtest.run): {"level", "started", "finished", "results": [{id, title, status, summary, details}]}
Status: ok / warn / fail / skip. Kein GTK hier.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
SYMBOL = {OK: "✔", WARN: "⚠", FAIL: "✖", SKIP: "–"}
LABEL = {OK: "in Ordnung", WARN: "Achtung", FAIL: "Fehler", SKIP: "nicht geprüft"}
COLOR = {OK: "#2e7d32", WARN: "#b26a00", FAIL: "#c62828", SKIP: "#757575"}
LEVEL = {"quick": "Schnelltest", "thorough": "Gründlich"}
DURATION = {"quick": "≈ 5 min", "thorough": "≈ 1–3 h"}
MAX_KEEP = 10            # so viele Berichte bleiben je Gerät gespeichert


def short_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return ""


def counts(report: dict) -> dict[str, int]:
    c = {OK: 0, WARN: 0, FAIL: 0, SKIP: 0}
    for r in report.get("results") or []:
        c[r.get("status") if r.get("status") in c else SKIP] += 1
    return c


def overall(report: dict) -> str:
    c = counts(report)
    return FAIL if c[FAIL] else WARN if c[WARN] else OK if c[OK] else SKIP


def headline(report: dict) -> str:
    """„Schnelltest 05.11.2026 14:30: 5 ✔, 1 ⚠, 0 ✖“ (+ nicht geprüft)."""
    c = counts(report)
    text = (f"{LEVEL.get(report.get('level'), 'Test')} {short_time(report.get('finished') or report.get('started', ''))}"
            f": {c[OK]} ✔, {c[WARN]} ⚠, {c[FAIL]} ✖")
    return text + (f", {c[SKIP]} nicht geprüft" if c[SKIP] else "")


def verdict(report: dict) -> str:
    return {OK: "Alles in Ordnung", WARN: "In Ordnung, aber mit Hinweisen",
            FAIL: "Fehler gefunden – Gerät nicht ohne Reparatur weitergeben", SKIP: "Nichts prüfbar"}[overall(report)]


def store(dev, report: dict) -> None:
    """Neuester Bericht zuerst, höchstens MAX_KEEP."""
    dev.hwtests = ([report] + list(dev.hwtests or []))[:MAX_KEEP]


def device_lines(dev) -> list[tuple[str, str]]:
    inv = dev.inventory or {}
    dmi = inv.get("dmi") or {}
    cpu = inv.get("cpu") or {}
    mem = inv.get("memory") or 0
    mem = mem.get("total", 0) if isinstance(mem, dict) else mem       # Inventar: Bytes
    disks = ", ".join(f"{d.get('model') or d.get('name')} ({(d.get('size') or 0) / 1e9:.0f} GB)"
                      for d in inv.get("disks") or [] if d.get("transport") != "usb")
    return [("Gerät", dev.name),
            ("Hersteller / Modell", " ".join(x for x in (dmi.get("sys_vendor"), dmi.get("product_name")) if x) or "–"),
            ("Seriennummer", dmi.get("product_serial") or "–"),
            ("BIOS", " ".join(x for x in (dmi.get("bios_version"), dmi.get("bios_date")) if x) or "–"),
            ("Prozessor", cpu.get("model") or "–"),
            ("Arbeitsspeicher", f"{mem / 2**30:.0f} GB" if mem else "–"),
            ("Disks", disks or "–")]


def write_pdf(path: Path, dev, report: dict) -> None:
    """A4 hoch: Gerät, Testart, Gesamtergebnis, Tabelle je Bereich, Unterschriftsfeld, Fusszeile."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, leading=20)
    meta = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#555555"))
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10.5)
    bold = ParagraphStyle("bold", parent=cell, fontName="Helvetica-Bold")
    big = ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=12, leading=15)
    page_w, _ = A4

    def para(text, style=cell):
        return Paragraph(escape(text or "").replace("\n", "<br/>"), style)

    status = overall(report)
    info = Table([[para(k, bold), para(v)] for k, v in device_lines(dev)], colWidths=[40 * mm, None])
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    rows = [[para("Bereich", bold), para("Ergebnis", bold), para("Befund", bold)]]
    styles = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
              ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    for r in report.get("results") or []:
        st = r.get("status") if r.get("status") in LABEL else SKIP
        rows.append([para(r.get("title", "")),
                     Paragraph(f'<font color="{COLOR[st]}">{escape(LABEL[st])}</font>', bold),
                     para("\n".join([r.get("summary", "")] + [f"· {d}" for d in r.get("details") or []]))])
    table = Table(rows, colWidths=[48 * mm, 24 * mm, None], repeatRows=1)
    table.setStyle(TableStyle(styles))
    sign = Table([[para("Geprüft von:"), para(""), para("Datum / Unterschrift:"), para("")]],
                 colWidths=[25 * mm, 55 * mm, 35 * mm, None])
    sign.setStyle(TableStyle([("LINEBELOW", (1, 0), (1, 0), 0.5, colors.black),
                              ("LINEBELOW", (3, 0), (3, 0), 0.5, colors.black)]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(15 * mm, 8 * mm, f"Okula Recovery Tool · Hardware-Prüfprotokoll {dev.name}")
        canvas.drawRightString(page_w - 15 * mm, 8 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title=f"Hardware-Prüfprotokoll {dev.name}", author="Okula Recovery Tool")
    story = [Paragraph("Hardware-Prüfprotokoll", h1),
             para(f"{LEVEL.get(report.get('level'), 'Test')} · Beginn {short_time(report.get('started', ''))} · "
                  f"Ende {short_time(report.get('finished', ''))} · nur lesend, Daten unverändert", meta),
             Spacer(1, 4 * mm), info, Spacer(1, 4 * mm),
             Paragraph(f'Gesamtergebnis: <font color="{COLOR[status]}">{escape(verdict(report))}</font>', big),
             para(headline(report).replace("✔", "OK").replace("⚠", "Achtung").replace("✖", "Fehler"), meta),
             Spacer(1, 3 * mm), table, Spacer(1, 4 * mm),
             para("Der Arbeitsspeicher wird im laufenden System teilweise geprüft (freier Bereich). Ein Test ohne "
                  "Befund schliesst spätere Defekte nicht aus.", meta),
             Spacer(1, 12 * mm), sign]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
