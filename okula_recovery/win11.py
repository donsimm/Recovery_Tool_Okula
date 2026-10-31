"""Windows-11-Tauglichkeit aus dem Inventar bewerten (auf dem Server; der Agent erfasst nur die Rohdaten).

Anforderungen (Microsoft, „Windows 11 specifications“): TPM 2.0, UEFI mit Secure Boot (fähig), RAM ≥ 4 GB,
Speicher ≥ 64 GB, Prozessor in Microsofts Liste der unterstützten Prozessoren (→ data/win11_cpus.txt).
Ergebnis: ok (✔), no (✖) oder unknown (?) mit Gründen in einfacher Sprache.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

CPU_RULES = Path(__file__).resolve().parent / "data" / "win11_cpus.txt"
MIN_RAM = 3.5 * 1024**3        # 4 GB Arbeitsspeicher (das System meldet etwas weniger)
MIN_DISK = 64 * 1000**3
SYMBOL = {"ok": "✔", "no": "✖", "unknown": "?"}


@dataclass
class Result:
    status: str                                # ok | no | unknown
    reasons: list[str] = field(default_factory=list)   # warum ✖ bzw. ?
    notes: list[str] = field(default_factory=list)     # erfüllt, aber gut zu wissen

    @property
    def symbol(self) -> str:
        return SYMBOL[self.status]

    def text(self) -> str:
        if self.status == "ok":
            return "✔ Windows 11 tauglich" + (f" – {'; '.join(self.notes)}" if self.notes else "")
        return f"{self.symbol} " + "; ".join(self.reasons)


@lru_cache(maxsize=1)
def _rules() -> list[tuple[bool, re.Pattern]]:
    rules = []
    for line in CPU_RULES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        verdict, _, pattern = line.partition(" ")
        rules.append((verdict == "ja", re.compile(pattern.strip(), re.I)))
    return rules


def cpu_supported(model: str) -> bool | None:
    """True/False laut Liste, None = Prozessor nicht erfasst."""
    for ok, pattern in _rules():
        if pattern.search(model or ""):
            return ok
    return None


def unsupported_note(installed: str) -> str:
    """Vermerk, wenn Windows 11 trotz „nicht tauglich“ installiert wurde (Datum JJJJ-MM-TT)."""
    if not installed:
        return ""
    try:
        when = date.fromisoformat(installed).strftime("%d.%m.%Y")
    except ValueError:
        when = installed
    return f"\n⚠ Am {when} trotzdem installiert (auf Wunsch) – nicht unterstützt, Updates nicht garantiert"


def check(inv: dict | None) -> Result:
    inv = inv or {}
    platform = inv.get("platform")
    if not isinstance(platform, dict):
        return Result("unknown", ["Inventar ohne TPM/Secure-Boot-Angaben (älterer Agent) – Agent-Stick neu erstellen "
                                  "und Inventar neu einlesen"])
    no, unknown, notes = [], [], []
    tpm = platform.get("tpm") or ""
    if tpm == "2.0":
        pass
    elif tpm:
        no.append(f"TPM {tpm} (2.0 nötig)")
    else:
        no.append("kein TPM gefunden (evtl. im BIOS ausgeschaltet: „TPM“, „PTT“ oder „fTPM“ einschalten)")
    if platform.get("uefi") is False:
        unknown.append("im BIOS-Modus gestartet – UEFI im BIOS einschalten und neu prüfen")
    elif platform.get("secure_boot") is False:
        notes.append("Secure Boot ist aus (einschalten empfohlen)")
    memory = int(inv.get("memory") or 0)
    if not memory:
        unknown.append("Arbeitsspeicher unbekannt")
    elif memory < MIN_RAM:
        no.append(f"nur {memory / 1024**3:.0f} GB RAM (4 GB nötig)")
    disks = [int(d.get("size") or 0) for d in inv.get("disks") or []]
    if disks and max(disks) < MIN_DISK:
        no.append(f"Festplatte nur {max(disks) / 1000**3:.0f} GB (64 GB nötig)")
    cpu = (inv.get("cpu") or {}).get("model") or ""
    supported = cpu_supported(cpu)
    if supported is False:
        no.append(f"Prozessor nicht unterstützt ({cpu.strip()})")
    elif supported is None:
        unknown.append(f"Prozessor nicht in der Liste – bitte prüfen ({cpu.strip() or 'unbekannt'})")
    if no:
        return Result("no", no + unknown, notes)
    if unknown:
        return Result("unknown", unknown, notes)
    return Result("ok", [], notes)
