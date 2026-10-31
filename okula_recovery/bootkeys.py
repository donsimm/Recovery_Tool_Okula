"""Boot-Menü- und BIOS-Taste je Hersteller – für den Stick-Dialog, die Hilfe und das Gerätefenster.

Die Tasten gelten für die meisten Modelle; einzelne Geräte weichen ab. Taste direkt nach dem Einschalten
wiederholt antippen (nicht gedrückt halten), bis das Menü erscheint.

Quellen (geprüft 31.10.2026):
- HP: support.hp.com/document/c04201984 (Esc → Startmenü, F9 Boot-Optionen, F10 Computer Setup)
- Microsoft Surface: support.microsoft.com/help/4023511 „Boot Surface from a USB device“
  (Leiser halten + Ein; UEFI: Lauter halten + Ein)
- Apple (Intel-Mac): support.apple.com/102603 „Mac startup key combinations“ (Option/Alt → Startmanager)
- Fujitsu: LifeBook-BIOS-Handbücher („<F12>:Boot Menu / <F2>:BIOS Setup“ beim Fujitsu-Logo)
- Medion: Akoya-Handbücher (F2 BIOS), MEDION-Community (F10 Boot-Menü, teils F8/F11)
- Dell, Lenovo, Asus, Acer, MSI, Gigabyte, Toshiba/Dynabook: Herstellerhandbücher und Übersichten
  (z. B. kb.wisc.edu/58779, killdisk.com/faq/authoring/hot-key-uefi.html)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BootKeys:
    vendor: str          # Anzeige, z. B. „Lenovo ThinkPad“
    boot: str            # Boot-Menü (einmalig vom Stick/Netzwerk starten)
    bios: str            # BIOS/UEFI-Setup
    hint: str = ""       # Besonderheit in einfacher Sprache


# Reihenfolge = Anzeige in der Tabelle (Stick-Dialog, Hilfe)
TABLE: dict[str, BootKeys] = {
    "hp": BootKeys("HP", "F9 (oder Esc, dann F9)", "F10 (oder Esc, dann F10)",
                   "Bei manchen Notebooks zusätzlich Fn drücken"),
    "dell": BootKeys("Dell", "F12", "F2"),
    "thinkpad": BootKeys("Lenovo ThinkPad / ThinkCentre", "F12 (oder Enter, dann F12)", "F1 (oder Enter, dann F1)"),
    "lenovo": BootKeys("Lenovo IdeaPad / Yoga / Legion", "F12 bzw. Fn+F12", "F2 bzw. Fn+F2",
                       "Klappt keine Taste: Novo-Knopf (kleines Loch neben dem Ein-Knopf, mit Büroklammer) → Boot Menu"),
    "asus-notebook": BootKeys("Asus Notebook", "Esc", "F2"),
    "asus-desktop": BootKeys("Asus Desktop / Mainboard", "F8", "Del (Entf)"),
    "acer": BootKeys("Acer", "F12", "F2",
                     "F12-Boot-Menü ist ab Werk aus: im BIOS (F2) → Main → „F12 Boot Menu“ einschalten"),
    "msi": BootKeys("MSI", "F11", "Del (Entf)"),
    "gigabyte": BootKeys("Gigabyte", "F12", "Del (Entf)"),
    "fujitsu": BootKeys("Fujitsu LifeBook / Esprimo", "F12", "F2", "Taste drücken, solange das Fujitsu-Logo steht"),
    "medion": BootKeys("Medion", "F10 (teils F8 oder F11)", "F2"),
    "toshiba": BootKeys("Toshiba / Dynabook", "F12", "F2 (ältere Modelle F1 oder Esc)"),
    "surface": BootKeys("Microsoft Surface", "Lautstärke leiser halten + Ein-Knopf drücken",
                        "Lautstärke lauter halten + Ein-Knopf drücken",
                        "Ausgeschaltet starten; Knopf halten, bis das Logo erscheint. Secure Boot darf an bleiben"),
    "apple": BootKeys("Apple Mac (Intel)", "Option (Alt) halten", "–",
                      "Nur Intel-Macs. Mit T2-Chip zuerst im Startsicherheitsdienstprogramm „Start von externen "
                      "Medien“ erlauben"),
}

# Hersteller aus DMI (sys_vendor bzw. board_vendor) – Schreibweisen der Hersteller
VENDOR_PATTERNS = (
    (r"hewlett|^hp\b|\bhp inc", "hp"),
    (r"^dell", "dell"),
    (r"lenovo", "lenovo"),
    (r"asus", "asus"),
    (r"^acer|gateway|packard bell", "acer"),
    (r"micro-star|^msi\b", "msi"),
    (r"gigabyte", "gigabyte"),
    (r"fujitsu", "fujitsu"),
    (r"medion", "medion"),
    (r"toshiba|dynabook", "toshiba"),
    (r"microsoft", "surface"),
    (r"^apple", "apple"),
)
NOTEBOOK_CHASSIS = {"Tragbar", "Laptop", "Notebook", "Sub-Notebook", "Convertible", "Detachable", "Tablet"}
GENERIC = re.compile(r"^(|system manufacturer|to be filled.*|default string|o\.e\.m\.?|oem)$", re.I)


def lookup(dmi: dict | None) -> BootKeys | None:
    """Tasten für ein Gerät aus seinen DMI-Daten (Inventar); None = Hersteller unbekannt."""
    d = dmi or {}
    vendor = (d.get("sys_vendor") or "").strip()
    if GENERIC.match(vendor):  # Eigenbau: Mainboard-Hersteller zählt (Asus, MSI, Gigabyte …)
        vendor = (d.get("board_vendor") or "").strip()
        own_build = True
    else:
        own_build = False
    key = next((k for pattern, k in VENDOR_PATTERNS if re.search(pattern, vendor, re.I)), None)
    if key is None:
        return None
    model = " ".join(d.get(f) or "" for f in ("product_family", "product_version", "product_name")).lower()
    if key == "lenovo" and re.search(r"think(pad|centre|station|book)", model):
        key = "thinkpad"
    elif key == "asus":
        notebook = d.get("chassis") in NOTEBOOK_CHASSIS and not own_build
        key = "asus-notebook" if notebook else "asus-desktop"
    elif key == "surface" and "surface" not in model:
        return None  # Microsoft-VM (Hyper-V) o. Ä. – kein Surface
    return TABLE[key]


def short(keys: BootKeys | None) -> str:
    """„Boot-Menü: F9 · BIOS: F10“ für Gerätefenster/Übersicht."""
    if keys is None:
        return ""
    return f"Boot-Menü: {keys.boot} · BIOS: {keys.bios}" + (f" – {keys.hint}" if keys.hint else "")
