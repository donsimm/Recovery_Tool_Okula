"""BIOS-Reiter im Gerätefenster (I-032): Daten vom Agent (biosread) aufbereiten, vergleichen, exportieren.

Der letzte Stand wird beim Gerät gespeichert (Device.bios) – so lassen sich zwei Geräte auch vergleichen, wenn nur
eines verbunden ist (z. B. „funktioniert“ gegen „funktioniert nicht“).
Kein GTK hier.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime

DRIVER = {"hp-bioscfg": "HP (hp-bioscfg)", "dell-wmi-sysman": "Dell (dell-wmi-sysman)",
          "thinklmi": "Lenovo (think-lmi)", "think-lmi": "Lenovo (think-lmi)"}
# Für Netzwerkstart, Stick-Start und Secure Boot wichtige Einstellungen – im Vergleich zuerst und fett
IMPORTANT = re.compile(r"boot|pxe|ipv4|ipv6|network|lan|wake|usb|secure|csm|legacy|uefi|tpm|fast|virtual", re.I)


def short_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return ""


def _yesno(v) -> str:
    return "–" if v is None else ("an" if v else "aus")


NAME_OK = re.compile(r"^[\w][\w .,:;()/+&'\-–]{2,}$")
ROLE_NAMES = {"SPM": "Secure Platform Management (HP)"}


def plausible(name: str) -> bool:
    """Lesbarer Name? hp-bioscfg liefert auf älteren HP-BIOS (z. B. EliteBook 850 G1) kaputte Namen wie „\\r“, „Î“
    oder Steuerzeichen – solche Einträge sind keine echten Einstellungen (B-006)."""
    return bool(name) and not any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 for c in name) and bool(NAME_OK.match(name))


def usable(data: dict) -> tuple[list[dict], int]:
    """(lesbare Einstellungen, Anzahl unlesbare)."""
    good, bad = [], 0
    for a in data.get("attributes") or []:
        if plausible(a.get("display") or "") or plausible(a.get("name") or ""):
            good.append(a)
        else:
            bad += 1
    return good, bad


def interface_text(data: dict) -> str:
    names = ", ".join(DRIVER.get(i, i) for i in data.get("interfaces") or [])
    if not names:
        return "keine – dieses Modell meldet seine Einstellungen nicht an Linux (nur Grundangaben)"
    good, bad = usable(data)
    if bad and len(good) <= bad:
        return (f"{names} – liefert auf diesem BIOS unlesbare Daten ({bad} von {bad + len(good)} Einträgen); "
                "Einstellungen nur im BIOS-Setup ansehen")
    return names + (f" ({bad} unlesbare Einträge ausgeblendet)" if bad else "")


def basics(data: dict) -> list[tuple[str, str]]:
    """Grundangaben, die jedes Gerät liefert (auch ohne BIOS-Schnittstelle)."""
    b, p = data.get("bios") or {}, data.get("platform") or {}
    auth = {k: v for k, v in (data.get("auth") or {}).items() if k not in ROLE_NAMES and plausible(k)}
    pw = ", ".join(f"{k}: {'gesetzt' if v else 'nicht gesetzt'}" for k, v in sorted(auth.items())) or "unbekannt"
    spm = {ROLE_NAMES[k]: v for k, v in (data.get("auth") or {}).items() if k in ROLE_NAMES}
    secure = "– (nur im UEFI-Modus)" if p.get("uefi") is False else _yesno(p.get("secure_boot"))
    rows = [("BIOS", " · ".join(x for x in (b.get("vendor"), b.get("version"), b.get("date")) if x) or "–"),
            ("Boot-Modus", "UEFI" if p.get("uefi") else ("BIOS-Modus (Legacy/CSM)" if p.get("uefi") is False else "–")),
            ("Secure Boot", secure),
            ("TPM", p.get("tpm") or "keines gefunden"),
            ("BIOS-Passwort", pw)]
    rows += [(k, "eingerichtet" if v else "nicht eingerichtet") for k, v in spm.items()]
    return rows + [("Schnittstelle", interface_text(data)),
                   ("Änderungen", "warten auf Neustart" if data.get("pending_reboot") else "keine offen")]


def boot_rows(data: dict) -> list[tuple[str, str]]:
    """UEFI-Startreihenfolge: (Position, Eintrag). Im BIOS-Modus eine erklärende Zeile."""
    boot = data.get("boot") or {}
    if not (data.get("platform") or {}).get("uefi"):
        return [("–", "Im BIOS-Modus lässt sich die Startreihenfolge nur im BIOS-Setup sehen")]
    if not boot.get("order"):
        return [("–", boot.get("message") or "Startreihenfolge nicht lesbar")]
    labels = boot.get("labels") or {}
    rows = []
    for i, num in enumerate(boot["order"], 1):
        mark = "  ← Netzwerkstart" if num == boot.get("network") else ""
        rows.append((str(i), f"{labels.get(num, 'Boot' + num)}{mark}"))
    return rows


def boot_text(data: dict) -> str:
    return " → ".join(r[1].replace("  ← Netzwerkstart", "") for r in boot_rows(data))


def settings(data: dict) -> dict[str, dict]:
    """Einstellungen nach Anzeigename (Treiber-Name als Rückfall)."""
    out = {}
    for a in usable(data)[0]:
        name = a.get("display") if plausible(a.get("display") or "") else a.get("name", "")
        out[name] = a
    return out


def possible_text(a: dict) -> str:
    if a.get("possible"):
        return " | ".join(a["possible"])
    if a.get("type") == "integer" and (a.get("min") or a.get("max")):
        return f"{a.get('min', '?')} … {a.get('max', '?')}"
    if a.get("type") == "string":
        return f"Text, max. {a['max_length']} Zeichen" if str(a.get("max_length") or "0") != "0" else "Text"
    return ""


def compare(a: dict, b: dict | None, only_diff: bool = False, text: str = "") -> list[dict]:
    """Zeilen für die Tabelle: Einstellung, Wert hier, Wert beim Vergleichsgerät, Unterschied?
    Grundangaben und Startreihenfolge zuerst, dann wichtige Einstellungen, dann der Rest (alphabetisch)."""
    rows = []

    def add(name, va, vb, kind, attr=None):
        diff = b is not None and (va or "") != (vb or "")
        rows.append({"name": name, "here": va or "", "other": vb if b is not None else "", "diff": diff,
                     "kind": kind, "attr": attr, "important": kind != "setting" or bool(IMPORTANT.search(name))})

    ba = dict(basics(a))
    bb = dict(basics(b)) if b is not None else {}
    for name in ("BIOS", "Boot-Modus", "Secure Boot", "TPM", "BIOS-Passwort", "Schnittstelle"):
        add(name, ba.get(name), bb.get(name), "basic")
    add("UEFI-Startreihenfolge", boot_text(a), boot_text(b) if b is not None else "", "basic")
    sa, sb = settings(a), settings(b) if b is not None else {}
    names = sorted(set(sa) | set(sb), key=lambda n: (not IMPORTANT.search(n), n.lower()))
    for name in names:
        va = (sa.get(name) or {}).get("value") if name in sa else ("fehlt" if b is not None else "")
        vb = ((sb.get(name) or {}).get("value") if name in sb else "fehlt") if b is not None else ""
        add(name, va or "–", (vb or "–") if b is not None else "", "setting", sa.get(name))
    words = [w.lower() for w in text.split() if w]
    out = []
    for r in rows:
        if only_diff and b is not None and not r["diff"]:
            continue
        hay = f"{r['name']} {r['here']} {r['other']}".lower()
        if words and not all(w in hay for w in words):
            continue
        out.append(r)
    return out


def summary(a: dict, b: dict | None = None, b_name: str = "") -> str:
    n = len(settings(a))
    text = f"Gelesen am {short_time(a.get('read', ''))} · {n} Einstellung{'en' if n != 1 else ''}"
    if not a.get("interfaces"):
        text += " · nur Grundangaben (Modell ohne BIOS-Schnittstelle unter Linux)"
    elif not n:
        text += " · nur Grundangaben (BIOS-Schnittstelle liefert unlesbare Daten)"
    if b is not None:
        diffs = sum(1 for r in compare(a, b) if r["diff"])
        text += f" · Vergleich mit {b_name} (gelesen {short_time(b.get('read', ''))}): {diffs} Unterschied" + \
            ("e" if diffs != 1 else "")
    return text


def to_csv(rows: list[dict], here: str, other: str = "") -> str:
    """CSV für Excel (Semikolon, mit BOM)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Einstellung", here] + ([other, "Unterschied"] if other else []))
    for r in rows:
        w.writerow([r["name"], r["here"]] + ([r["other"], "ja" if r["diff"] else ""] if other else []))
    return "﻿" + buf.getvalue()


def risky(name: str) -> str:
    """Warnung vor dem Setzen, wenn die Einstellung das Starten verhindern kann."""
    if re.search(r"boot mode|csm|legacy|uefi", name, re.I):
        return ("Der Boot-Modus bestimmt, ob das installierte System noch startet (Windows im Legacy-Modus startet "
                "nicht mehr im UEFI-Modus und umgekehrt).")
    if re.search(r"secure ?boot", name, re.I):
        return "Ändern von Secure Boot verlangt bei HP beim nächsten Start eine Bestätigung am Gerät (Code eintippen)."
    if re.search(r"tpm|bitlocker", name, re.I):
        return "TPM-Änderungen können BitLocker-Wiederherstellung auslösen – Wiederherstellungsschlüssel bereithalten."
    return ""
