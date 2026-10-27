"""Agent für den USB-Stick: meldet die Maschine beim Okula Recovery Tool im LAN an.

Start: python3 -m okula_recovery.agent   (auf dem Stick als systemd-Dienst)
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import time

from okula_recovery import __version__, discovery, network


BANNER = """\
  ####   #   #  #   #  #       ###
 #    #  #  #   #   #  #      #   #
 #    #  ###    #   #  #      #####
 #    #  #  #   #   #  #      #   #
  ####   #   #   ###   #####  #   #   Recovery Agent
"""


def broadcast_targets() -> list[str]:
    targets = {"255.255.255.255"}
    for iface in network.local_interfaces():
        targets.add(str(iface.network.broadcast_address))
    return sorted(targets)


def primary_ip(server: str | None = None) -> str:
    """Quell-IP der Route Richtung Server (bzw. ins LAN); es wird nichts gesendet."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect((server or "10.255.255.255", 9))
            ip = s.getsockname()[0]
        except OSError:
            ip = ""
    if ip and ip != "0.0.0.0":
        return ip
    ifaces = network.local_interfaces()
    return str(ifaces[0].ip) if ifaces else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Okula Recovery Agent")
    ap.add_argument("--port", type=int, default=discovery.PORT)
    ap.add_argument("--interval", type=float, default=3.0, help="Sekunden zwischen Beacons")
    ap.add_argument("--server", help="IP des Tools, zusätzlich zum Broadcast (z. B. anderes Subnetz)")
    ap.add_argument("--no-broadcast", action="store_true", help="nur an --server senden")
    args = ap.parse_args(argv)
    if args.server:
        ipaddress.IPv4Address(args.server)
    elif args.no_broadcast:
        ap.error("--no-broadcast braucht --server")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(args.interval)

    server = None
    print(BANNER, flush=True)
    print(f"Okula Recovery Agent {__version__} – suche Recovery-Tool im LAN …", flush=True)
    while True:
        ip = primary_ip(args.server)
        if not ip:
            print("Keine Netzwerkadresse, warte auf DHCP …", flush=True)
            time.sleep(args.interval)
            continue
        beacon = json.dumps(discovery.build_beacon(ip, __version__)).encode()
        targets = [] if args.no_broadcast else broadcast_targets()
        if args.server:
            targets.append(args.server)
        for target in targets:
            try:
                sock.sendto(beacon, (target, args.port))
            except OSError as e:
                print(f"Senden an {target} fehlgeschlagen: {e}", file=sys.stderr, flush=True)

        deadline = time.monotonic() + args.interval
        while (left := deadline - time.monotonic()) > 0:
            sock.settimeout(left)
            try:
                data, (sip, _p) = sock.recvfrom(discovery.MAX_PACKET)
            except (TimeoutError, OSError):
                break
            try:
                msg = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(msg, dict) and msg.get("type") == discovery.ACK_TYPE and server != sip:
                server = sip
                print(f"Verbunden: {ip} ist im Tool sichtbar (Server {msg.get('name', '')} / {sip})", flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
