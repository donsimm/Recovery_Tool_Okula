"""Auto-Erkennung: Agent auf dem USB-Stick meldet sich per UDP-Broadcast beim Tool.

Ablauf: Agent sendet alle paar Sekunden ein JSON-Beacon an Port PORT (Broadcast).
Das Tool antwortet per Unicast mit einem Ack, damit der Agent weiss, welcher
Server ihn sieht (Anzeige auf der Konsole der Zielmaschine).
Nur stdlib, damit der Agent ohne GTK auf dem Stick läuft.
"""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PORT = 47811
MAX_PACKET = 8192
PROTOCOL_VERSION = 1
BEACON_TYPE = "okula-agent"
ACK_TYPE = "okula-server"


@dataclass
class Disk:
    name: str
    size: int
    model: str = ""
    serial: str = ""
    transport: str = ""  # sata, nvme, usb …


@dataclass
class AgentInfo:
    agent_id: str
    hostname: str
    ip: str
    mac: str = ""
    vendor: str = ""
    product: str = ""
    disks: list[Disk] = field(default_factory=list)
    version: str = ""
    control_port: int = 0  # 0 = Agent ohne Steuerdienst (alter Stick)
    busy: bool = False
    job: str = ""                   # was gerade läuft, z. B. „Zurückspielen“
    inventory_version: int = 0      # ändert sich, wenn der Agent das Inventar neu gesammelt hat
    progress: float | None = None   # 0..1
    last_seen: float = 0.0   # time.monotonic() des letzten Beacons (Timeout unabhängig von Uhr-Korrekturen)

    @property
    def status(self) -> str:
        if not self.job:
            return "beschäftigt" if self.busy else "bereit"
        return f"{self.job} {self.progress * 100:.0f} %" if self.progress is not None else self.job

    @property
    def hardware(self) -> str:
        return " ".join(p for p in (self.vendor, self.product) if p)


# ---------- Beacon erzeugen (Agent-Seite) ----------

def _read(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def parse_lsblk(output: str) -> list[Disk]:
    """Parst `lsblk -J -b -d -o NAME,SIZE,MODEL,SERIAL,TYPE,TRAN`, nur echte Disks."""
    try:
        devices = json.loads(output).get("blockdevices", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    disks = []
    for d in devices:
        if d.get("type") != "disk" or str(d.get("name", "")).startswith(("loop", "zram", "ram")):
            continue
        disks.append(Disk(name=d["name"], size=int(d.get("size") or 0),
                          model=(d.get("model") or "").strip(), serial=(d.get("serial") or "").strip(),
                          transport=d.get("tran") or ""))
    return disks


def local_disks() -> list[Disk]:
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-d", "-o", "NAME,SIZE,MODEL,SERIAL,TYPE,TRAN"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_lsblk(out)


def machine_id() -> str:
    """Stabile ID der Hardware (Board-UUID), Fallback: erste MAC."""
    return _read("/sys/class/dmi/id/product_uuid") or primary_mac() or socket.gethostname()


def primary_mac() -> str:
    for iface in sorted(Path("/sys/class/net").glob("*")):
        if iface.name == "lo" or not (iface / "device").exists():
            continue
        mac = _read(str(iface / "address"))
        if mac and mac != "00:00:00:00:00:00":
            return mac
    return ""


def build_beacon(ip: str, version: str, extra: dict | None = None) -> dict:
    return {
        **(extra or {}),
        "type": BEACON_TYPE,
        "proto": PROTOCOL_VERSION,
        "id": machine_id(),
        "hostname": socket.gethostname(),
        "ip": ip,
        "mac": primary_mac(),
        "vendor": _read("/sys/class/dmi/id/sys_vendor"),
        "product": _read("/sys/class/dmi/id/product_name"),
        "disks": [d.__dict__ for d in local_disks()],
        "version": version,
    }


# ---------- Beacon auswerten (Tool-Seite) ----------

def parse_beacon(data: bytes, sender_ip: str) -> AgentInfo | None:
    """Validiert ein Beacon. Als IP zählt die Absenderadresse, nicht die Angabe im Paket."""
    if len(data) > MAX_PACKET:
        return None
    try:
        msg = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict) or msg.get("type") != BEACON_TYPE or msg.get("proto") != PROTOCOL_VERSION:
        return None
    disks = []
    for d in msg.get("disks") or []:
        if isinstance(d, dict) and d.get("name"):
            try:
                disks.append(Disk(name=str(d["name"]), size=int(d.get("size") or 0),
                                  model=str(d.get("model") or ""), serial=str(d.get("serial") or ""),
                                  transport=str(d.get("transport") or "")))
            except (TypeError, ValueError):
                continue
    return AgentInfo(agent_id=str(msg.get("id") or sender_ip), hostname=str(msg.get("hostname") or ""),
                     ip=sender_ip, mac=str(msg.get("mac") or ""), vendor=str(msg.get("vendor") or ""),
                     product=str(msg.get("product") or ""), disks=disks, version=str(msg.get("version") or ""),
                     control_port=_int(msg.get("control")), busy=bool(msg.get("busy")),
                     job=str(msg.get("job") or "")[:40], progress=_fraction(msg.get("progress")),
                     inventory_version=_int(msg.get("inv")),
                     last_seen=time.monotonic())


def _fraction(v) -> float | None:
    try:
        return None if v is None else max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def _int(v) -> int:
    try:
        return max(0, min(65535, int(v or 0)))
    except (TypeError, ValueError):
        return 0


class Listener:
    """Empfängt Beacons im Hintergrund und ruft on_agent(AgentInfo) auf (aus dem Empfangs-Thread)."""

    def __init__(self, on_agent: Callable[[AgentInfo], None], port: int = PORT, server_name: str = ""):
        self.on_agent = on_agent
        self.port = port
        self.server_name = server_name or socket.gethostname()
        self._sock: socket.socket | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", self.port))
        sock.settimeout(1.0)
        self._sock = sock
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        assert self._sock
        ack = json.dumps({"type": ACK_TYPE, "proto": PROTOCOL_VERSION, "name": self.server_name}).encode()
        while not self._stop.is_set():
            try:
                data, (ip, port) = self._sock.recvfrom(MAX_PACKET + 1)
            except TimeoutError:
                continue
            except OSError:
                break
            info = parse_beacon(data, ip)
            if info is None:
                continue
            # Agent ohne DHCP (169.254.x.x) ist per Unicast meist nicht routbar → zusätzlich Broadcast
            targets = [(ip, port)]
            if ip.startswith("169.254."):
                targets.append(("255.255.255.255", port))
            for target in targets:
                try:
                    self._sock.sendto(ack, target)
                except OSError:
                    pass
            self.on_agent(info)
        self._sock.close()
