"""Unicode sicher behandeln: Namen vergleichen, ASCII-Umschrift, unsichtbare Zeichen.

- NFC: „ü“ kann als ein Zeichen (NFC) oder als „u“ + Trema (NFD, z. B. von macOS über SMB) ankommen. Gleich
  aussehende Namen werden so verschieden – vor Vergleich und Speichern immer nach NFC.
- Umschrift für Computernamen (NetBIOS/Hostname nur ASCII): ä→ae, ß→ss, é→e, ø→oe … statt Zeichen zu verlieren.
- Unsichtbare/gefährliche Zeichen in Namen (Steuerzeichen, Rechts-nach-links-Umschaltung U+202E, Null-Breite):
  damit lässt sich „Rechnung<U+202E>fdp.exe“ als „Rechnungexe.pdf“ anzeigen – in Ordner- und Dateinamen abgelehnt,
  aus Gerätenamen (vom Gerät gemeldet) entfernt.
"""

from __future__ import annotations

import unicodedata

# Deutsch/Skandinavisch zuerst, sonst nur Akzent weg (é→e). Gross/klein getrennt, damit „Ä“ → „Ae“ bleibt.
TRANSLIT = {
    "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "ẞ": "SS",
    "æ": "ae", "Æ": "Ae", "ø": "oe", "Ø": "Oe", "œ": "oe", "Œ": "Oe", "å": "aa", "Å": "Aa",
    "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ı": "i",
}

# Unicode-Kategorien, die in Namen nichts verloren haben: Steuerzeichen, Format (Bidi, Null-Breite, BOM),
# Zeilen-/Absatztrenner, private Nutzung, nicht vergeben, Surrogate
UNSAFE_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Co", "Cn", "Cs"}


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def same_name(a: str, b: str) -> bool:
    """Gleicher Name, wie ihn ein Mensch (und ein Windows-/SMB-NAS) sieht: NFC, Gross/klein egal."""
    return nfc(a).casefold() == nfc(b).casefold()


def unsafe_chars(text: str) -> list[str]:
    """Unsichtbare/gefährliche Zeichen als „U+202E“-Liste (leer = in Ordnung)."""
    return sorted({f"U+{ord(c):04X}" for c in nfc(text) if unicodedata.category(c) in UNSAFE_CATEGORIES})


def clean(text: str) -> str:
    """NFC und unsichtbare Zeichen entfernen (Tabulator/Zeilenumbruch → Leerzeichen) – für gemeldete Namen."""
    out = []
    for c in nfc(text):
        if c in "\t\r\n":
            out.append(" ")
        elif unicodedata.category(c) not in UNSAFE_CATEGORIES:
            out.append(c)
    return " ".join("".join(out).split())


def to_ascii(text: str) -> str:
    """„Büro Straße Café Øster“ → „Buero Strasse Cafe Oester“; Zeichen ohne Umschrift fallen weg."""
    text = "".join(TRANSLIT.get(c, c) for c in nfc(text))
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if c.isascii() and not unicodedata.combining(c))
