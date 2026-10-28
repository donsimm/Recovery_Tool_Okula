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

from okula_recovery import __version__, discovery, imaging, inventory, network, wire


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


# ---------- Fortschritt am Bildschirm ----------

def format_eta(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return "< 1 min"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


class ConsoleBar:
    """Einzeiliger Fortschrittsbalken auf dem Terminal der Zielmaschine (nur ASCII)."""

    WIDTH = 30

    def __init__(self, path: str, title: str):
        self.path = path
        self.started = time.monotonic()
        self.last = 0.0
        self._write(f"\n  {title}\n")

    @classmethod
    def render(cls, fraction: float, label: str, transferred: int, elapsed: float) -> str:
        f = max(0.0, min(1.0, fraction))
        filled = int(f * cls.WIDTH)
        bar = "=" * filled + (">" + " " * (cls.WIDTH - filled - 1) if filled < cls.WIDTH else "")
        rate = transferred / elapsed if elapsed > 0 else 0
        line = f"  [{bar}] {f * 100:3.0f} %  {label}"
        if transferred > 0:
            line += f"  {rate / 1e6:.0f} MB/s"
        if 0.02 < f < 1 and elapsed > 10:
            line += f"  noch ca. {format_eta(elapsed * (1 - f) / f)}"
        return line

    def __call__(self, fraction: float, label: str, transferred: int) -> None:
        now = time.monotonic()
        if now - self.last < 1.0:
            return
        self.last = now
        self._write("\r\033[K" + self.render(fraction, label, transferred, now - self.started))

    def finish(self, text: str) -> None:
        self._write(f"\r\033[K  {text}\n")

    def _write(self, text: str) -> None:
        try:
            with open(self.path, "a") as tty:
                tty.write(text)
        except OSError:
            pass


def power_action(action: str) -> None:
    subprocess.run(["systemctl", action], capture_output=True)


# ---------- Steuerdienst (Tool → Agent) ----------

KEY_FILE = "/etc/okula-agent.key"
class DiskLocks:
    """Pro Disk höchstens ein Auftrag; verschiedene Disks (und Geräte) laufen parallel."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active: dict[str, str] = {}  # Disk → Auftragsart

    def acquire(self, disk: str, kind: str) -> bool:
        with self._lock:
            if disk in self._active:
                return False
            self._active[disk] = kind
            return True

    def release(self, disk: str) -> None:
        with self._lock:
            self._active.pop(disk, None)

    def active(self) -> dict[str, str]:
        with self._lock:
            return dict(self._active)

    def busy(self) -> bool:
        return bool(self.active())


disk_locks = DiskLocks()
inspect_lock = threading.Lock()  # Inventar hängt Partitionen kurz ein – Aufträge warten darauf


class Inventory:
    """Inventar des Geräts: einmal beim Start gesammelt, nach einem Restore und auf Wunsch neu."""

    def __init__(self):
        self.data: dict | None = None
        self.version = 0

    def collect(self) -> dict:
        with inspect_lock:
            data = inventory.collect(with_os=os.geteuid() == 0, skip=set(disk_locks.active()))
            self.data, self.version = data, self.version + 1
        log(f"Inventar gesammelt (Version {self.version})")
        return data

    def get(self, refresh: bool = False) -> dict:
        if not refresh and self.data is None:
            with inspect_lock:  # das Sammeln beim Start läuft evtl. noch – darauf warten statt doppelt
                pass
        return self.collect() if refresh or self.data is None else self.data


inventory_state = Inventory()


class JobState:
    """Was gerade läuft – für die Beacons (Status-Spalte im Tool) und den Bildschirm.

    Aufträge laufen hier (Image, Zurückspielen; mehrere parallel) oder werden im Tool
    vorbereitet (Image-Prüfung, per „notify“ gemeldet). Meldungen aus dem Tool verfallen
    nach NOTICE_TTL, damit ein abgestürztes Tool keinen ewigen Status hinterlässt.
    """

    NOTICE_TTL = 30

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[int, tuple[str, float | None]] = {}
        self.notice_text = ""
        self.notice_fraction: float | None = None
        self.updated = 0.0
        self.bar: ConsoleBar | None = None
        self.bar_title = ""

    def update(self, job: int, kind: str, fraction: float | None) -> None:
        with self.lock:
            self.jobs[job] = (kind, fraction)

    def finish(self, job: int) -> None:
        with self.lock:
            self.jobs.pop(job, None)

    def set_notice(self, text: str, fraction: float | None) -> None:
        with self.lock:
            self.notice_text, self.notice_fraction, self.updated = text, fraction, time.monotonic()

    def clear_notice(self) -> None:
        with self.lock:
            self.notice_text, self.notice_fraction = "", None

    def beacon(self) -> dict:
        with self.lock:
            if len(self.jobs) == 1:
                kind, fraction = next(iter(self.jobs.values()))
                return {"job": kind, "progress": fraction}
            if self.jobs:
                return {"job": f"{len(self.jobs)} Aufträge", "progress": None}
            if self.notice_text and time.monotonic() - self.updated <= self.NOTICE_TTL:
                return {"job": self.notice_text, "progress": self.notice_fraction}
            return {"job": "", "progress": None}

    # Bildschirm für Meldungen aus dem Tool (eigene Aufträge haben ihren eigenen Balken)
    def notice(self, title: str, fraction: float | None, label: str, result: str = "") -> None:
        if not console:
            return
        if self.bar is None or self.bar_title != title:
            self.end_notice("")
            self.bar = ConsoleBar(console, title)
            self.bar_title = title
        if result:
            self.end_notice(result)
        elif fraction is not None:
            self.bar(fraction, label, 0)

    def end_notice(self, result: str) -> None:
        if self.bar is not None:
            self.bar.finish(f"» {result}" if result else "")
            self.bar = None
            self.bar_title = ""


job_state = JobState()
_job_ids = iter(range(1, 1 << 62))


def run_job(tls, addr, req: dict, kind: str) -> None:
    """Disk-Image („image“) oder Zurückspielen („restore“) – parallel zu Aufträgen auf anderen Disks."""
    disk = str(req.get("disk") or "")
    label = "Disk-Image" if kind == "image" else "Zurückspielen"
    if not disk_locks.acquire(disk, kind):
        wire.send_json(tls, {"type": "error", "message": f"Auf {disk} läuft bereits ein Auftrag"})
        return
    job = next(_job_ids)
    ok = False
    bar = None
    try:
        with inspect_lock:
            pass  # läuft gerade das Inventar, erst danach beginnen
        alone = len(disk_locks.active()) == 1
        if kind == "restore":
            job_state.end_notice("Image im Tool geprüft – Zurückspielen startet")
            job_state.clear_notice()
        title = (f"Disk-Image von {disk} läuft" if kind == "image"
                 else f"Image wird auf {disk} zurückgespielt") + " – Maschine nicht ausschalten"
        # Mehrere parallele Aufträge: keine Balken (würden sich überschreiben), nur Meldungen
        bar = ConsoleBar(console, title) if console and alone else None
        job_state.update(job, label, 0.0)
        log(f"{label} auf {disk} für {addr[0]} gestartet", show=not bar)

        def report(fraction: float, part: str, transferred: int) -> None:
            job_state.update(job, label, fraction)
            if bar:
                bar(fraction, part, transferred)

        if kind == "image":
            imaging.stream_disk_image(tls, disk, log, report)
        else:
            imaging.restore_disk(tls, req, log, report)
        ok = True
        log(f"{label} auf {disk} fertig", show=not bar)
    except imaging.ImagingError as e:
        log(f"{label} auf {disk} fehlgeschlagen: {e}", show=not bar)
        wire.send_json(tls, {"type": "error", "message": str(e)})
    finally:
        if bar:
            result = ("fertig" if kind == "image" else "zurückgespielt – Stick abziehen und neu starten") if ok \
                else ("abgebrochen" if kind == "image" else "abgebrochen – Disk ist unvollständig")
            bar.finish(f"» {label} auf {disk}: {result}")
        job_state.finish(job)
        disk_locks.release(disk)
    if ok and kind == "restore":
        threading.Thread(target=inventory_state.collect, daemon=True).start()  # neues Betriebssystem erfassen


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
                                     "busy": disk_locks.busy(), "active": disk_locks.active()})
            elif cmd in ("image", "restore"):
                run_job(tls, addr, req, cmd)
            elif cmd == "inventory":
                if req.get("refresh") and disk_locks.busy():
                    wire.send_json(tls, {"type": "error", "message": "Während eines Auftrags nicht möglich"})
                else:
                    data = inventory_state.get(bool(req.get("refresh")))
                    wire.send_json(tls, {"type": "inventory", "data": data, "version": inventory_state.version})
            elif cmd == "notify":
                # Das Tool bereitet einen Auftrag vor (z. B. Image-Prüfung) – am Bildschirm zeigen
                title = str(req.get("title") or "Auftrag wird im Tool vorbereitet")[:120]
                job = str(req.get("job") or "")[:40]
                result = str(req.get("result") or "")[:200]
                try:
                    fraction = float(req["fraction"]) if req.get("fraction") is not None else None
                except (TypeError, ValueError):
                    fraction = None
                if result:
                    job_state.clear_notice()
                    log(result)
                else:
                    job_state.set_notice(job, fraction)
                job_state.notice(title, fraction, str(req.get("label") or "")[:40], result)
                wire.send_json(tls, {"type": "ok"})
            elif cmd == "power":
                action = req.get("action")
                if action not in ("poweroff", "reboot"):
                    wire.send_json(tls, {"type": "error", "message": f"Unbekannte Aktion: {action}"})
                elif disk_locks.busy():
                    wire.send_json(tls, {"type": "error", "message": "Agent ist beschäftigt – nicht herunterfahren"})
                else:
                    delay = max(0, min(60, int(req.get("delay") or 0)))
                    wire.send_json(tls, {"type": "ok"})
                    what = "heruntergefahren" if action == "poweroff" else "neu gestartet"
                    log(f"Maschine wird in {delay} s {what} (Tool {addr[0]})", show=True)
                    threading.Timer(delay, power_action, args=(action,)).start()
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
        threading.Thread(target=inventory_state.collect, daemon=True).start()  # Geräte-Erfassung
    else:
        log(f"Kein Schlüssel in {args.key_file} – nur Anmeldung, keine Images möglich", show=True)
    extra = lambda: {"control": args.control_port if key else 0,  # noqa: E731
                     "busy": disk_locks.busy(), "inv": inventory_state.version, **job_state.beacon()}

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
