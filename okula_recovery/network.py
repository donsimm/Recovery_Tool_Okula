"""LAN: eigene Netze ermitteln, Ping-Scan, Hostnamen und MAC-Adressen."""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable


@dataclass
class Machine:
    ip: str
    name: str = ""
    mac: str = ""
    online: bool = False
    source: str = "Scan"  # "Scan", "manuell" oder "USB-Agent"
    hardware: str = ""
    disks: str = ""


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def parse_ip_addr(output: str) -> list[ipaddress.IPv4Interface]:
    """Parst `ip -4 -o addr show scope global`."""
    result = []
    for m in re.finditer(r"\binet (\d+\.\d+\.\d+\.\d+/\d+)", output):
        result.append(ipaddress.IPv4Interface(m.group(1)))
    return result


def local_interfaces() -> list[ipaddress.IPv4Interface]:
    return parse_ip_addr(_run(["ip", "-4", "-o", "addr", "show", "scope", "global"]))


def default_scan_network() -> ipaddress.IPv4Network | None:
    """Erstes lokales Netz; grösser als /24 wird auf das eigene /24 begrenzt."""
    for iface in local_interfaces():
        net = iface.network
        if net.prefixlen < 24:
            net = ipaddress.IPv4Interface(f"{iface.ip}/24").network
        return net
    return None


def parse_ip_neigh(output: str) -> dict[str, str]:
    """Parst `ip neigh show` → {ip: mac}."""
    table = {}
    for line in output.splitlines():
        m = re.match(r"(\d+\.\d+\.\d+\.\d+) .*\blladdr ([0-9a-f:]{17})", line)
        if m and "FAILED" not in line and "INCOMPLETE" not in line:
            table[m.group(1)] = m.group(2)
    return table


def neighbours() -> dict[str, str]:
    return parse_ip_neigh(_run(["ip", "neigh", "show"]))


def ping(ip: str, timeout: int = 1) -> bool:
    try:
        r = subprocess.run(["ping", "-c", "1", "-W", str(timeout), "-n", "-q", ip],
                           capture_output=True, timeout=timeout + 2)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve_name(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""


def scan(network: ipaddress.IPv4Network,
         progress: Callable[[int, int], None] | None = None,
         workers: int = 64) -> list[Machine]:
    """Ping-Scan über alle Hosts im Netz, eigene Adressen ausgenommen."""
    own = {str(i.ip) for i in local_interfaces()}
    hosts = [str(h) for h in network.hosts() if str(h) not in own]
    total, done = len(hosts), 0
    alive: list[str] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ip, ok in zip(hosts, pool.map(ping, hosts)):
            done += 1
            if ok:
                alive.append(ip)
            if progress:
                progress(done, total)

        names = list(pool.map(resolve_name, alive))

    macs = neighbours()
    return [Machine(ip=ip, name=name, mac=macs.get(ip, ""), online=True)
            for ip, name in zip(alive, names)]
