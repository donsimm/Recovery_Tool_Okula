"""Wake-on-LAN: ausgeschaltete Geräte über das Netzwerk einschalten (Magic Packet).

Das Paket geht als Broadcast in jedes Netz des Servers (Subnetz-Broadcast) und an 255.255.255.255, auf UDP 9 und 7.
Am Gerät muss Wake-on-LAN im BIOS/UEFI aktiv sein, und es muss per Kabel am Netz hängen. Router leiten
Broadcasts nicht weiter – das Gerät muss im selben Netz wie der Server sein.
"""

from __future__ import annotations

import ipaddress
import re
import socket

from okula_recovery import network

MAC_RE = re.compile(r"^[0-9a-f]{2}([:-]?[0-9a-f]{2}){5}$", re.I)
PORTS = (9, 7)


def magic_packet(mac: str) -> bytes:
    if not MAC_RE.match(mac.strip()):
        raise ValueError(f"Ungültige MAC-Adresse: {mac}")
    raw = bytes.fromhex(re.sub(r"[:-]", "", mac.strip()))
    return b"\xff" * 6 + raw * 16


def targets(interfaces: list[ipaddress.IPv4Interface] | None = None) -> list[str]:
    """Broadcast-Adressen aller Netze des Servers (ohne Loopback) plus 255.255.255.255."""
    out = []
    for iface in network.local_interfaces() if interfaces is None else interfaces:
        if iface.ip.is_loopback or iface.network.prefixlen >= 31:
            continue
        out.append(str(iface.network.broadcast_address))
    return list(dict.fromkeys(out + ["255.255.255.255"]))


def wake(macs: list[str], interfaces: list[ipaddress.IPv4Interface] | None = None) -> int:
    """Magic Packets senden; gibt die Anzahl gesendeter Pakete zurück."""
    packets = [magic_packet(m) for m in macs]
    sent = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for addr in targets(interfaces):
            for port in PORTS:
                for packet in packets:
                    try:
                        sock.sendto(packet, (addr, port))
                        sent += 1
                    except OSError:
                        continue
    return sent
