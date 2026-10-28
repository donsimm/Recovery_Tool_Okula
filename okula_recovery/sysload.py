"""Auslastung des Servers (CPU, RAM, LAN) direkt aus /proc und /sys – ohne Zusatzpakete."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Load:
    cpu: float = 0.0             # 0–1 seit der letzten Messung, alle Kerne zusammen
    cores: int = 1
    loadavg: str = ""            # „0.52 0.40 0.31“ (1/5/15 min)
    mem_used: int = 0            # Bytes, ohne Cache (MemTotal − MemAvailable)
    mem_total: int = 0
    swap_used: int = 0
    iface: str = ""              # Netzwerkkarte der Standardroute
    rx: float = 0.0              # Bytes/s empfangen
    tx: float = 0.0              # Bytes/s gesendet
    link: int = 0                # Verbindungsgeschwindigkeit in Mbit/s, 0 = unbekannt

    @property
    def mem(self) -> float:
        return self.mem_used / self.mem_total if self.mem_total else 0.0

    @property
    def lan(self) -> float:
        """Auslastung der Verbindung 0–1 (stärkere Richtung); ohne bekannte Geschwindigkeit 0."""
        return min(1.0, max(self.rx, self.tx) * 8 / (self.link * 1e6)) if self.link else 0.0


def mbit(rate: float) -> str:
    """Bytes/s → „94.2 Mbit/s“."""
    bits = rate * 8
    if bits >= 1e9:
        return f"{bits / 1e9:.2f} Gbit/s"
    if bits >= 1e6:
        return f"{bits / 1e6:.1f} Mbit/s"
    return f"{bits / 1e3:.0f} kbit/s"


def rates(rx: float, tx: float) -> str:
    """Empfangen/gesendet mit gemeinsamer Einheit: „↓ 94.2 ↑ 3.8 Mbit/s“ (kurz genug für die Leiste)."""
    top = max(rx, tx) * 8
    div, unit, fmt = (1e9, "Gbit/s", ".2f") if top >= 1e9 else (1e6, "Mbit/s", ".1f") if top >= 1e5 else (1e3, "kbit/s", ".0f")
    return f"↓ {rx * 8 / div:{fmt}}  ↑ {tx * 8 / div:{fmt}} {unit}"


def gib(n: int) -> str:
    return f"{n / 2**30:.1f}"


class Sampler:
    """Jeder Aufruf von sample() misst seit dem vorherigen (CPU-Anteil, Netzwerk-Rate)."""

    def __init__(self, proc: str | Path = "/proc", sysfs: str | Path = "/sys"):
        self.proc, self.sysfs = Path(proc), Path(sysfs)
        self._cpu: tuple[int, int] | None = None
        self._net: tuple[float, int, int] | None = None
        self._iface = ""

    def _read(self, rel: str) -> str:
        try:
            return (self.proc / rel).read_text()
        except OSError:
            return ""

    def _cpu_times(self) -> tuple[int, int]:
        """(beschäftigt, gesamt) in Jiffies aus der Zeile „cpu“ von /proc/stat."""
        for line in self._read("stat").splitlines():
            if line.startswith("cpu "):
                v = [int(x) for x in line.split()[1:9]]
                idle = v[3] + v[4]  # idle + iowait
                return sum(v) - idle, sum(v)
        return 0, 0

    def _meminfo(self) -> dict[str, int]:
        info = {}
        for line in self._read("meminfo").splitlines():
            key, _, rest = line.partition(":")
            parts = rest.split()
            if parts and parts[0].isdigit():
                info[key] = int(parts[0]) * 1024
        return info

    def default_iface(self) -> str:
        """Karte der Standardroute; sonst die mit dem meisten Verkehr (ohne lo)."""
        for line in self._read("net/route").splitlines()[1:]:
            f = line.split()
            if len(f) > 2 and f[1] == "00000000":
                return f[0]
        counters = self._net_counters()
        best = max((k for k in counters if k != "lo"), key=lambda k: sum(counters[k]), default="")
        return best

    def _net_counters(self) -> dict[str, tuple[int, int]]:
        out = {}
        for line in self._read("net/dev").splitlines()[2:]:
            name, _, rest = line.partition(":")
            f = rest.split()
            if len(f) >= 9:
                out[name.strip()] = (int(f[0]), int(f[8]))
        return out

    def _link(self, iface: str) -> int:
        try:
            speed = int((self.sysfs / "class/net" / iface / "speed").read_text().strip())
        except (OSError, ValueError):
            return 0
        return speed if speed > 0 else 0

    def sample(self) -> Load:
        load = Load(cores=os.cpu_count() or 1)
        busy, total = self._cpu_times()
        if self._cpu and total > self._cpu[1]:
            load.cpu = max(0.0, min(1.0, (busy - self._cpu[0]) / (total - self._cpu[1])))
        self._cpu = (busy, total)
        load.loadavg = " ".join(self._read("loadavg").split()[:3])

        mem = self._meminfo()
        load.mem_total = mem.get("MemTotal", 0)
        load.mem_used = max(0, load.mem_total - mem.get("MemAvailable", mem.get("MemFree", 0)))
        load.swap_used = max(0, mem.get("SwapTotal", 0) - mem.get("SwapFree", 0))

        iface = self.default_iface()
        if iface != self._iface:
            self._iface, self._net = iface, None
        load.iface, load.link = iface, self._link(iface) if iface else 0
        rx, tx = self._net_counters().get(iface, (0, 0))
        now = time.monotonic()
        if self._net and now > self._net[0] and rx >= self._net[1] and tx >= self._net[2]:
            dt = now - self._net[0]
            load.rx, load.tx = (rx - self._net[1]) / dt, (tx - self._net[2]) / dt
        self._net = (now, rx, tx)
        return load
