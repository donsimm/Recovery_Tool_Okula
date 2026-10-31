"""Bandbreite begrenzen (I-030): ein gemeinsamer Token-Bucket für alle Datenströme Tool ↔ Agent.

- Nur das Tool setzt einen Limiter (wire.set_limiter); der Agent und die Tests ohne Limiter bleiben unverändert.
- Gezählt werden die Daten-Frames in wire.send_data/recv_frame. Beim Empfangen bremst das verzögerte Lesen den
  Absender über TCP – der Agent muss nichts davon wissen.
- Gerecht verteilt: jeder Strom reserviert Zeitscheiben in kleinen Portionen (QUANTUM) der Reihe nach; laufen
  mehrere Aufträge, wechseln sie sich ab und teilen sich die Grenze.
- Die Grenze wird bei jeder Portion neu gelesen (rate_fn): Änderungen in den Einstellungen und das Zeitfenster
  wirken sofort, auch auf laufende Aufträge.
- NAS-Zugriffe des Servers selbst (Dateien kopieren, Image prüfen) laufen nicht über wire und bleiben unbegrenzt.
Kein GTK hier.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

MIN_MBIT, MAX_MBIT, DEFAULT_MBIT = 10, 10_000, 300
DEFAULT_FROM, DEFAULT_TO = "07:00", "18:00"
DEFAULT_DAYS = [0, 1, 2, 3, 4]                     # Mo–Fr (datetime.weekday)
DAY_NAMES = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
QUANTUM = 128 * 1024                               # Portion je Reservierung (Fairness zwischen Strömen)
STEP = 0.25                                        # so oft prüft ein wartender Strom, ob sich die Grenze änderte


@dataclass
class Settings:
    enabled: bool = False                          # Standard: unbegrenzt
    mbit: int = DEFAULT_MBIT
    window: bool = False                           # nur im Zeitfenster begrenzen
    start: str = DEFAULT_FROM
    end: str = DEFAULT_TO
    days: list[int] = field(default_factory=lambda: list(DEFAULT_DAYS))


def _hhmm(value, default: str) -> str:
    try:
        h, m = str(value).strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return f"{h:02d}:{m:02d}"
    except (ValueError, AttributeError):
        pass
    return default


def clean(data: dict | None) -> Settings:
    """Werte aus config.json bzw. einem Export mit Grenzen übernehmen (Unsinn → Standard)."""
    data = data if isinstance(data, dict) else {}
    try:
        mbit = max(MIN_MBIT, min(MAX_MBIT, int(data.get("mbit") or DEFAULT_MBIT)))
    except (TypeError, ValueError):
        mbit = DEFAULT_MBIT
    days = data.get("days", DEFAULT_DAYS)
    if isinstance(days, list):
        days = sorted({d for d in days if isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6})
    else:
        days = list(DEFAULT_DAYS)
    return Settings(enabled=bool(data.get("enabled", False)), mbit=mbit, window=bool(data.get("window", False)),
                    start=_hhmm(data.get("start"), DEFAULT_FROM), end=_hhmm(data.get("end"), DEFAULT_TO), days=days)


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_window(s: Settings, now: datetime) -> bool:
    """Liegt now im Zeitfenster? Über Mitternacht (z. B. 22:00–06:00) zählt der Morgen zum Starttag;
    von = bis heisst ganzer Tag."""
    t, a, b = now.hour * 60 + now.minute, _minutes(s.start), _minutes(s.end)
    today = now.weekday() in s.days
    if a == b:
        return today
    if a < b:
        return today and a <= t < b
    yesterday = (now - timedelta(days=1)).weekday() in s.days
    return (today and t >= a) or (yesterday and t < b)


def active_mbit(s: Settings, now: datetime | None = None) -> int | None:
    """Grenze in Mbit/s, die jetzt gilt – None = unbegrenzt."""
    if not s.enabled:
        return None
    if s.window and not in_window(s, now or datetime.now()):
        return None
    return s.mbit


def fmt_mbit(mbit: int) -> str:
    return f"{mbit:,}".replace(",", "'") + " Mbit/s"


def fmt_mbyte(mbit: int) -> str:
    """Mbit/s → MB/s (1 MB = 10⁶ Byte), z. B. 300 → „37.5 MB/s“."""
    value = mbit / 8
    return (f"{value:,.0f}" if value >= 100 else f"{value:.1f}".rstrip("0").rstrip(".")).replace(",", "'") + " MB/s"


def window_text(s: Settings) -> str:
    """„Mo–Fr 07:00–18:00“ bzw. „Mo, Mi 22:00–06:00“."""
    days = sorted(s.days)
    if not days:
        names = "an keinem Tag"
    elif days == list(range(days[0], days[-1] + 1)) and len(days) > 2:
        names = f"{DAY_NAMES[days[0]]}–{DAY_NAMES[days[-1]]}"
    else:
        names = ", ".join(DAY_NAMES[d] for d in days)
    return f"{names} {s.start}–{s.end}"


def describe(s: Settings, now: datetime | None = None) -> str:
    """Zeile fürs Auftrags-Log; leer, wenn nichts begrenzt ist."""
    if not s.enabled:
        return ""
    mbit = active_mbit(s, now)
    if mbit is None:
        return f"Bandbreite: unbegrenzt (ausserhalb des Zeitfensters {window_text(s)})"
    return f"Bandbreite begrenzt auf {fmt_mbit(mbit)}" + (f" ({window_text(s)})" if s.window else "") + \
        " – gilt für alle Aufträge zusammen"


class Limiter:
    """Gemeinsamer Token-Bucket. rate_fn() liefert die Grenze in Bit/s oder None (unbegrenzt).
    on_rate_change(neu) wird aufgerufen, wenn sich die geltende Grenze ändert (z. B. Restzeiten neu rechnen)."""

    def __init__(self, rate_fn: Callable[[], float | None],
                 on_rate_change: Callable[[float | None], None] | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.rate_fn = rate_fn
        self.on_rate_change = on_rate_change
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.next = 0.0              # ab wann die nächste Portion frei ist
        self.rate: float | None = None
        self.total = 0               # gezählte Bytes (Tests, Anzeige)

    def _current(self) -> float | None:
        try:
            rate = self.rate_fn()
        except Exception:  # Einstellungen kaputt → lieber nicht bremsen als Auftrag abbrechen
            rate = None
        rate = rate if rate and rate > 0 else None
        if rate != self.rate:
            self.rate = rate
            self.next = self.clock()           # neue Grenze gilt ab jetzt, alte Reservierungen verfallen
            if self.on_rate_change:
                try:
                    self.on_rate_change(rate)
                except Exception:
                    pass
        return rate

    def take(self, nbytes: int) -> None:
        """Wartet, bis nbytes übertragen werden dürfen (in Portionen, abwechselnd mit anderen Strömen)."""
        left = nbytes
        while left > 0:
            part = min(left, QUANTUM)
            self._take_part(part)
            left -= part

    def _take_part(self, n: int) -> None:
        while True:
            with self.lock:
                rate = self._current()
                if rate is None:
                    self.total += n
                    return
                now = self.clock()
                start = max(now, self.next)
                self.next = start + n * 8 / rate
                reserved = rate
            # bis zum Beginn der eigenen Zeitscheibe warten; dabei Änderungen der Grenze bemerken
            while True:
                wait = start - self.clock()
                if wait <= 0:
                    with self.lock:
                        self.total += n
                    return
                self.sleep(min(wait, STEP))
                with self.lock:
                    changed = self._current() != reserved
                if changed:
                    break    # neu reservieren mit der neuen Grenze (bzw. sofort weiter, wenn unbegrenzt)
