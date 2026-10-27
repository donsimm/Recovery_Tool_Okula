"""Agent für den USB-Stick: meldet die Maschine beim Okula Recovery Tool im LAN an.

Start: python3 -m okula_recovery.agent   (auf dem Stick als systemd-Dienst)
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path

from okula_recovery import __version__, discovery, imaging, network, wire


# So lange ohne IPv4, dann DHCP nachfassen bzw. Link-Local-Adresse setzen
LINK_LOCAL_AFTER = 25
DHCP_CLIENTS = (
    ["dhcpcd", "-1", "-4", "-t", "15"],
    ["dhclient", "-1", "-4"],
    ["udhcpc", "-n", "-q", "-t", "5", "-i"],
)


# Terminal der Zielmaschine für die wichtigsten Meldungen (ohne systemd-Präfix); leer = keins
console = ""


def log(msg: str, show: bool = False) -> None:
    """Protokoll ins Journal; show=True zusätzlich kurz und ohne Präfix auf den Bildschirm."""
    print(msg, flush=True)
    if show and console:
        try:
            with open(console, "a") as tty:
                tty.write(f"\n  » {msg}\n")
        except OSError:
            pass


def wired_interfaces(net_dir: Path = Path("/sys/class/net")) -> list[str]:
    result = []
    for iface in sorted(net_dir.iterdir()):
        if iface.name == "lo" or not (iface / "device").exists() or (iface / "wireless").exists():
            continue
        result.append(iface.name)
    return result


def link_local_address(mac: str) -> str:
    """Feste 169.254.x.y aus der MAC (RFC 3927: 169.254.1.0–169.254.254.255)."""
    b = [int(x, 16) for x in mac.split(":")]
    return f"169.254.{1 + b[4] % 254}.{b[5]}"


def _try(cmd: list[str], timeout: int = 40) -> None:
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        pass


def ensure_network(server: str | None) -> None:
    """Kein DHCP-Lease: Interfaces hochfahren, DHCP nachfassen, sonst Link-Local.

    Der Agent funktioniert damit in jedem Netz, auch ohne DHCP-Server; das Tool
    findet ihn über den Broadcast an 255.255.255.255, egal welche IP er hat.
    """
    ifaces = wired_interfaces()
    for name in ifaces:
        _try(["ip", "link", "set", name, "up"], timeout=5)
    time.sleep(3)
    for name in ifaces:
        try:
            carrier = Path(f"/sys/class/net/{name}/carrier").read_text().strip()
        except OSError:
            carrier = ""
        if carrier != "1":
            continue  # kein Kabel
        for cmd in DHCP_CLIENTS:
            if shutil.which(cmd[0]):
                log(f"Keine IP – frage DHCP mit {cmd[0]} auf {name} an …")
                _try([*cmd, name])
                break
        if primary_ip(server):
            return
        addr = link_local_address(Path(f"/sys/class/net/{name}/address").read_text().strip())
        log(f"Kein DHCP im Netz – verwende Link-Local-Adresse {addr} auf {name}", show=True)
        _try(["ip", "addr", "add", f"{addr}/16", "dev", name], timeout=5)
        # Ohne Route ist der Broadcast an 255.255.255.255 nicht sendbar
        _try(["ip", "route", "add", "default", "dev", name, "metric", "9999"], timeout=5)
        return


# ---------- Steuerdienst (Tool → Agent) ----------

KEY_FILE = "/etc/okula-agent.key"
job_lock = threading.Lock()


def load_key(path: str) -> bytes | None:
    try:
        key = bytes.fromhex(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None
    return key if len(key) == wire.KEY_LEN else None


def handle_connection(ctx: ssl.SSLContext, conn: socket.socket, addr) -> None:
    try:
        with ctx.wrap_socket(conn, server_side=True) as tls:
            tls.settimeout(900)
            req = wire.recv_json(tls)
            cmd = req.get("cmd")
            if cmd == "info":
                wire.send_json(tls, {"type": "info", "hostname": socket.gethostname(), "version": __version__,
                                     "disks": imaging.list_disks(), "tools": imaging.tool_status(),
                                     "busy": job_lock.locked()})
            elif cmd == "image":
                if not job_lock.acquire(blocking=False):
                    wire.send_json(tls, {"type": "error", "message": "Agent ist mit einem anderen Auftrag beschäftigt"})
                    return
                disk = str(req.get("disk") or "")
                try:
                    log(f"Disk-Image von {disk} läuft (Tool {addr[0]}) – Maschine nicht ausschalten", show=True)
                    imaging.stream_disk_image(tls, disk, log)
                    log(f"Disk-Image von {disk} fertig", show=True)
                except imaging.ImagingError as e:
                    log(f"Disk-Image von {disk} fehlgeschlagen: {e}", show=True)
                    wire.send_json(tls, {"type": "error", "message": str(e)})
                finally:
                    job_lock.release()
            elif cmd == "restore":
                if not job_lock.acquire(blocking=False):
                    wire.send_json(tls, {"type": "error", "message": "Agent ist mit einem anderen Auftrag beschäftigt"})
                    return
                disk = str(req.get("disk") or "")
                try:
                    log(f"Image wird auf {disk} zurückgespielt (Tool {addr[0]}) – Maschine nicht ausschalten", show=True)
                    imaging.restore_disk(tls, req, log)
                    log(f"Image auf {disk} zurückgespielt – Stick abziehen und neu starten", show=True)
                except imaging.ImagingError as e:
                    log(f"Zurückspielen auf {disk} fehlgeschlagen: {e}", show=True)
                    wire.send_json(tls, {"type": "error", "message": str(e)})
                finally:
                    job_lock.release()
            else:
                wire.send_json(tls, {"type": "error", "message": f"Unbekannter Befehl: {cmd}"})
    except ssl.SSLError:
        log(f"Verbindung von {addr[0]} abgelehnt (falscher Schlüssel – Stick von anderem Tool?)", show=True)
    except (OSError, wire.ProtocolError) as e:
        log(f"Verbindung zu {addr[0]} beendet: {e}")


def serve_control(key: bytes, port: int) -> None:
    ctx = wire.server_context(key)
    try:
        server = socket.create_server(("", port))
    except OSError as e:
        log(f"Steuerdienst kann TCP {port} nicht öffnen: {e}")
        return
    log(f"Steuerdienst bereit (TCP {port})")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_connection, args=(ctx, conn, addr), daemon=True).start()


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
    ap.add_argument("--key-file", default=KEY_FILE, help="Schlüssel für den Steuerdienst (hex)")
    ap.add_argument("--control-port", type=int, default=wire.PORT)
    ap.add_argument("--console", default="", help="Terminal für Statusmeldungen, z. B. /dev/tty1")
    args = ap.parse_args(argv)
    if args.server:
        ipaddress.IPv4Address(args.server)
    elif args.no_broadcast:
        ap.error("--no-broadcast braucht --server")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(args.interval)

    global console
    console = args.console
    key = load_key(args.key_file)
    if key:
        threading.Thread(target=serve_control, args=(key, args.control_port), daemon=True).start()
    else:
        log(f"Kein Schlüssel in {args.key_file} – nur Anmeldung, keine Images möglich", show=True)
    extra = lambda: {"control": args.control_port if key else 0, "busy": job_lock.locked()}  # noqa: E731

    server = None
    no_ip_since = time.monotonic()
    network_fixed = False
    waiting_shown = False
    log(f"Okula Recovery Agent {__version__} – suche Recovery-Tool im LAN …")
    while True:
        ip = primary_ip(args.server)
        if not ip:
            waited = time.monotonic() - no_ip_since
            if waited > LINK_LOCAL_AFTER and not network_fixed and os.geteuid() == 0:
                network_fixed = True
                ensure_network(args.server)
                continue
            log("Keine Netzwerkadresse, warte auf DHCP … (Netzwerkkabel eingesteckt?)", show=not waiting_shown)
            waiting_shown = True
            time.sleep(args.interval)
            continue
        no_ip_since = time.monotonic()
        beacon = json.dumps(discovery.build_beacon(ip, __version__, extra())).encode()
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
            if isinstance(msg, dict) and msg.get("type") == discovery.ACK_TYPE:
                name = str(msg.get("name") or sip)
                if server != name:  # pro Server nur einmal melden (Ack kommt per Uni- und Broadcast)
                    server = name
                    log(f"Verbunden: {ip} ist im Tool sichtbar (Server {name} / {sip})", show=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
