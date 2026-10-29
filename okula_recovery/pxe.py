"""Netzwerkstart (PXE) des Agents – nur für registrierte, freigeschaltete Geräte.

Ablauf am Gerät: Firmware fragt per DHCP nach einem Netzwerkstart. Der normale DHCP-Server vergibt wie immer die
IP; zusätzlich antwortet dnsmasq als *Proxy-DHCP* – aber nur, wenn die MAC in der Freigabeliste steht. Danach:
UEFI: shim → grub (signiert, Secure Boot geht) → Kernel/initrd per TFTP; BIOS: pxelinux. Das initrd ist das des
Debian-Live-ISO plus ein kleines Skript (9999-okula), damit live-boot neben dem Live-System auch den Agent-Teil
(mit Schlüssel) per HTTP lädt. Der HTTP-Dienst liefert nur feste Dateien und nur an freigeschaltete MACs
(Abgleich über die ARP-Tabelle). Fremde Rechner bekommen nie eine Antwort; IP-Adressen vergibt das Tool keine.

Root-Helfer (gleiche sudo-Regel wie der Stick):
    sudo okula-make-stick pxe prepare --iso <Debian-Live-ISO> --server <IP>   (Schlüssel hex über stdin)
    sudo okula-make-stick pxe start --server <IP> | stop
    sudo okula-make-stick pxe allow                                           (MACs über stdin, eine pro Zeile)
Dienste (install.sh): okula-pxe.service (dnsmasq), okula-pxe-http.service (python3 -m okula_recovery.pxe serve)
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from okula_recovery import linuxsetup, stick
from okula_recovery.stick import StickError

PXE_DIR = Path("/var/lib/okula-recovery/pxe")
DNSMASQ_CONF = Path("/etc/okula-recovery/pxe-dnsmasq.conf")
HTTP_PORT = 47813
UNITS = ("okula-pxe.service", "okula-pxe-http.service")
HTTP_FILES = ("filesystem.squashfs", stick.AGENT_LAYER)       # nur diese liefert der HTTP-Dienst aus
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
BOOT_PACKAGES = ("shim-signed", "grub-efi-amd64-signed", "pxelinux", "syslinux-common")
SHIM_CANDIDATES = ("usr/lib/shim/shimx64.efi.signed", "usr/lib/shim/shimx64.efi.signed.latest",
                   "usr/lib/shim/shimx64.efi.dualsigned")
GRUBNET = "usr/lib/grub/x86_64-efi-signed/grubnetx64.efi.signed"
PXELINUX = "usr/lib/PXELINUX/pxelinux.0"
LDLINUX = "usr/lib/syslinux/modules/bios/ldlinux.c32"
# Wo signierte grub-Netzwerk-Images ihre grub.cfg suchen (Debian bzw. Ubuntu)
GRUB_CFG_PATHS = ("debian-installer/amd64/grub/grub.cfg", "grub/grub.cfg", "boot/grub/grub.cfg")

Emit = Callable[[str, str], None]

# live-boot liest alle /lib/live/boot/????-* – dieses Skript kommt zuletzt und ersetzt den HTTP-Download so,
# dass zusätzlich der Agent-Teil (okula.layer=URL) neben das Live-System gelegt wird. Wie beim Stick lädt
# live-boot dann beide Images (alphabetisch: filesystem, okula-agent).
LIVE_BOOT_HOOK = r"""# Okula Recovery Tool: Netzwerkstart lädt neben dem Live-System den Agent-Teil (okula.layer=URL)
OKULA_LAYER=""
for _okula_arg in $(cat "${OKULA_CMDLINE:-/proc/cmdline}"); do
	case "${_okula_arg}" in
		okula.layer=*) OKULA_LAYER="${_okula_arg#okula.layer=}" ;;
	esac
done

if [ -n "${OKULA_LAYER}" ]; then
do_httpmount ()
{
	dest="${mountpoint}/${LIVE_MEDIA_PATH}"
	mount -t ramfs ram "${mountpoint}"
	mkdir -p "${dest}"
	rc=0
	for _okula_url in ${FETCH} ${OKULA_LAYER}; do
		log_begin_msg "Okula: lade ${_okula_url}"
		wget "${_okula_url}" -O "${dest}/$(basename "${_okula_url}")" || rc=1
		log_end_msg
	done
	if [ ${rc} != 0 ]; then
		echo "OKULA: Netzwerkstart fehlgeschlagen - Geraet im Tool freigeschaltet? Tool gestartet?" > /dev/console
		umount "${mountpoint}"
	fi
	return ${rc}
}
fi
"""

GRUB_CFG = """# Okula Recovery Tool – Netzwerkstart (nur ASCII)
set timeout=3
set default=0
menuentry "Okula Recovery Agent (Netzwerk)" {{
    linux /okula/vmlinuz {params}
    initrd /okula/initrd.img
}}
menuentry "Okula Recovery Agent (Netzwerk, nomodeset)" {{
    linux /okula/vmlinuz {params} nomodeset
    initrd /okula/initrd.img
}}
menuentry "Von der Festplatte starten" {{
    exit
}}
"""

PXELINUX_CFG = """# Okula Recovery Tool – Netzwerkstart (BIOS)
DEFAULT okula
TIMEOUT 30
PROMPT 0
LABEL okula
    KERNEL okula/vmlinuz
    INITRD okula/initrd.img
    APPEND {params}
LABEL local
    LOCALBOOT 0
"""


class PxeError(StickError):
    pass


# ---------- Bausteine (ohne root, testbar) ----------

def kernel_params(server: str) -> str:
    base = f"http://{server}:{HTTP_PORT}"
    return (f"{stick.BOOT_PARAMS} fetch={base}/filesystem.squashfs okula.layer={base}/{stick.AGENT_LAYER}")


def normalize_macs(lines: list[str]) -> list[str]:
    macs = []
    for line in lines:
        mac = line.strip().lower().replace("-", ":")
        if not mac:
            continue
        if not MAC_RE.match(mac):
            raise PxeError(f"Ungültige MAC-Adresse: {line.strip()}")
        macs.append(mac)
    return sorted(set(macs))


def hosts_file(macs: list[str]) -> str:
    """dnsmasq-dhcp-hostsfile: nur diese MACs bekommen das Merkmal „okula“ (und damit eine PXE-Antwort)."""
    return "".join(f"{m},set:okula\n" for m in macs)


def read_allowed(base: Path = PXE_DIR) -> set[str]:
    try:
        return {line.split(",")[0] for line in (base / "allowed").read_text().splitlines() if line.strip()}
    except OSError:
        return set()


def interface_for(server: str) -> tuple[str, ipaddress.IPv4Interface]:
    """Netzwerkkarte und Netz zur Server-IP (ip -o -4 addr)."""
    out = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "inet":
            iface = ipaddress.IPv4Interface(parts[3])
            if str(iface.ip) == server:
                return parts[1], iface
    raise PxeError(f"Keine Netzwerkkarte mit der IP {server} gefunden")


def dnsmasq_conf(iface: str, network: ipaddress.IPv4Network, base: Path = PXE_DIR) -> str:
    return f"""# Okula Recovery Tool – Netzwerkstart. Erzeugt vom Tool, nicht von Hand ändern.
# Kein DNS, keine IP-Vergabe: nur Proxy-DHCP (Startinfo) und TFTP – und nur für freigeschaltete MACs.
port=0
interface={iface}
bind-interfaces
dhcp-range={network.network_address},proxy,{network.netmask}
dhcp-hostsfile={base}/allowed
dhcp-ignore=tag:!okula
pxe-prompt=tag:okula,"Okula Recovery",1
pxe-service=tag:okula,x86PC,"Okula Recovery Agent",pxelinux
pxe-service=tag:okula,X86-64_EFI,"Okula Recovery Agent",bootx64.efi
pxe-service=tag:okula,BC_EFI,"Okula Recovery Agent",bootx64.efi
enable-tftp
tftp-root={base}/tftp
log-dhcp
"""


def overlay_cpio() -> bytes:
    """Zusatz-cpio fürs initrd (wird hinten angehängt; der Kernel entpackt alle Teile nacheinander)."""
    return linuxsetup.cpio_newc({"lib/live/boot/9999-okula": LIVE_BOOT_HOOK.encode()})


def combine_initrd(original: bytes) -> bytes:
    """Original-initrd + Zusatz-cpio. Der Kernel verlangt, dass ein angehängtes (unkomprimiertes) cpio an einer
    durch 4 teilbaren Stelle beginnt – sonst „Initramfs unpacking failed: broken padding“. Nullen dazwischen
    überspringt er."""
    return original + b"\0" * (-len(original) % 4) + overlay_cpio()


def mac_of(ip: str, arp: str = "/proc/net/arp") -> str:
    """MAC zu einer IP aus der ARP-Tabelle (nur vollständige Einträge)."""
    try:
        lines = Path(arp).read_text().splitlines()[1:]
    except OSError:
        return ""
    for line in lines:
        f = line.split()
        if len(f) >= 4 and f[0] == ip and f[2] != "0x0":
            return f[3].lower()
    return ""


# ---------- HTTP-Dienst (läuft als okula-pxe-http.service) ----------

class Handler(BaseHTTPRequestHandler):
    server_version = "OkulaPXE"
    base: Path = PXE_DIR
    arp: str = "/proc/net/arp"

    def _allowed(self) -> bool:
        return mac_of(self.client_address[0], self.arp) in read_allowed(self.base)

    def do_GET(self) -> None:
        self._serve(head=False)

    def do_HEAD(self) -> None:
        self._serve(head=True)

    def _serve(self, head: bool) -> None:
        name = self.path.lstrip("/").split("?")[0]
        if name not in HTTP_FILES:
            self.send_error(404)
            return
        if not self._allowed():
            self.log_message("abgewiesen: %s ist nicht freigeschaltet", self.client_address[0])
            self.send_error(403, "Geraet nicht fuer den Netzwerkstart freigeschaltet")
            return
        path = self.base / "http" / name
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404)
            return
        with f:
            size = os.fstat(f.fileno()).st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            if not head:
                self.wfile.flush()
                self.connection.sendfile(f)


def serve(bind: str, base: Path = PXE_DIR) -> None:
    Handler.base = base
    httpd = ThreadingHTTPServer((bind, HTTP_PORT), Handler)
    httpd.daemon_threads = True
    signal.signal(signal.SIGTERM, lambda *_a: sys.exit(0))
    httpd.serve_forever()


# ---------- Vorbereiten (root) ----------

def _run(cmd: list[str], input: str | None = None, cwd: str | None = None) -> str:
    r = subprocess.run(cmd, input=input, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise PxeError(f"{Path(cmd[0]).name}: {(r.stderr or r.stdout).strip()[-500:]}")
    return r.stdout


def fetch_bootloaders(dest: Path, emit: Emit) -> None:
    """Signierte Bootlader aus den Paketquellen des Servers – nur herunterladen und auspacken, nicht
    installieren (der Bootlader des Servers bleibt unberührt). apt prüft die Pakete gegen die Paketsignatur."""
    with tempfile.TemporaryDirectory(prefix="okula-pxe-deb-") as tmp:
        os.chmod(tmp, 0o755)  # apt lädt als Benutzer _apt herunter
        _run(["apt-get", "download", *BOOT_PACKAGES], cwd=tmp)
        root = Path(tmp) / "x"
        for deb in Path(tmp).glob("*.deb"):
            _run(["dpkg-deb", "-x", str(deb), str(root)])
        shim = next((root / c for c in SHIM_CANDIDATES if (root / c).is_file()), None)
        if shim is None:
            raise PxeError("shim (shimx64.efi.signed) nicht im Paket shim-signed gefunden")
        for src, name in ((shim, "bootx64.efi"), (root / GRUBNET, "grubx64.efi"),
                          (root / PXELINUX, "pxelinux.0"), (root / LDLINUX, "ldlinux.c32")):
            if not src.is_file():
                raise PxeError(f"{src.name} fehlt im Paket")
            shutil.copyfile(src, dest / name)
    emit("INFO", "Bootlader: shim, grub (signiert, Secure Boot), pxelinux aus den Paketquellen des Servers")


def prepare(iso: str, server: str, key: bytes, emit: Emit, base: Path = PXE_DIR,
            bootloaders: Callable[[Path, Emit], None] = fetch_bootloaders) -> dict:
    def progress(frac: float, msg: str) -> None:
        emit("PROGRESS", f"{frac:.3f} {msg}")

    ipaddress.IPv4Address(server)
    iso_path = Path(iso).resolve()
    if not iso_path.is_file():
        raise PxeError(f"ISO nicht gefunden: {iso}")
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o755)
    new = base / ".neu"
    if new.exists():
        shutil.rmtree(new)
    tftp, http = new / "tftp", new / "http"
    (tftp / "okula").mkdir(parents=True)
    (tftp / "pxelinux.cfg").mkdir()
    http.mkdir()
    os.chmod(http, 0o700)   # enthält den Agent-Schlüssel – nur root (HTTP-Dienst)
    try:
        progress(0.02, "Lese Live-System aus der ISO (gut 1 GB)")
        live = new / "live"
        _run(["xorriso", "-osirrox", "on", "-indev", str(iso_path), "-extract", "/live", str(live)])
        for p in [live, *live.rglob("*")]:
            p.chmod(0o755 if p.is_dir() else 0o644)
        kernel, initrd = stick.find_kernel(live)
        if not (live / "filesystem.squashfs").is_file():
            raise PxeError("filesystem.squashfs fehlt – ist das ein Debian-Live-ISO?")
        progress(0.45, "Baue Agent-Teil (mit Schlüssel und partclone)")
        installed = stick.read_installed_packages(live / "filesystem.packages")
        stick.install_agent(new, server, key, installed, bundle=True, emit=emit)
        progress(0.75, "Hole Bootlader")
        bootloaders(tftp, emit)
        progress(0.85, "Lege Startdateien an")
        shutil.move(str(live / kernel), tftp / "okula" / "vmlinuz")
        (tftp / "okula" / "initrd.img").write_bytes(combine_initrd((live / initrd).read_bytes()))
        shutil.move(str(live / "filesystem.squashfs"), http / "filesystem.squashfs")
        shutil.move(str(live / stick.AGENT_LAYER), http / stick.AGENT_LAYER)
        for f in http.iterdir():
            f.chmod(0o600)
        params = kernel_params(server)
        for rel in GRUB_CFG_PATHS:
            (tftp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tftp / rel).write_text(GRUB_CFG.format(params=params))
        (tftp / "pxelinux.cfg" / "default").write_text(PXELINUX_CFG.format(params=params))
        for p in [tftp, *tftp.rglob("*")]:
            p.chmod(0o755 if p.is_dir() else 0o644)   # dnsmasq liest als eigener Benutzer
        shutil.rmtree(live)
        # alte Dateien ersetzen (Freigabeliste bleibt)
        for name in ("tftp", "http"):
            old = base / name
            if old.exists():
                shutil.rmtree(old)
            (new / name).rename(old)
        state = {"server": server, "iso": iso_path.name, "prepared": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "kernel": kernel}
        (base / "state.json").write_text(json.dumps(state, indent=2))
        os.chmod(base / "state.json", 0o644)
        if not (base / "allowed").exists():
            (base / "allowed").write_text("")
        os.chmod(base / "allowed", 0o644)
    finally:
        if new.exists():
            shutil.rmtree(new, ignore_errors=True)
    progress(1.0, "Fertig")
    return state


def read_state(base: Path = PXE_DIR) -> dict:
    try:
        return json.loads((base / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def is_active() -> bool:
    r = subprocess.run(["systemctl", "is-active", "--quiet", UNITS[0]], capture_output=True)
    return r.returncode == 0


def write_allowed(macs: list[str], base: Path = PXE_DIR) -> None:
    base.mkdir(parents=True, exist_ok=True)
    tmp = base / "allowed.tmp"
    tmp.write_text(hosts_file(macs))
    os.chmod(tmp, 0o644)
    tmp.replace(base / "allowed")


def start(server: str, emit: Emit, base: Path = PXE_DIR) -> None:
    state = read_state(base)
    if not state:
        raise PxeError("Netzwerkstart ist noch nicht vorbereitet")
    if state.get("server") != server:
        raise PxeError(f"Vorbereitet für {state.get('server')} – mit der aktuellen Server-IP {server} neu vorbereiten")
    iface, net = interface_for(server)
    DNSMASQ_CONF.parent.mkdir(parents=True, exist_ok=True)
    DNSMASQ_CONF.write_text(dnsmasq_conf(iface, net.network, base))
    if not (base / "allowed").exists():
        write_allowed([], base)
    (base / "bind").write_text(server + "\n")
    _run(["systemctl", "enable", "--now", *UNITS])
    _run(["systemctl", "restart", *UNITS])
    emit("INFO", f"Netzwerkstart aktiv auf {iface} ({net.network}) – nur für freigeschaltete Geräte")


def stop(emit: Emit) -> None:
    _run(["systemctl", "disable", "--now", *UNITS])
    emit("INFO", "Netzwerkstart ausgeschaltet")


def allow(macs: list[str], emit: Emit, base: Path = PXE_DIR) -> None:
    write_allowed(macs, base)
    if is_active():
        subprocess.run(["systemctl", "reload", UNITS[0]], capture_output=True)
    emit("INFO", f"{len(macs)} MAC-Adressen freigeschaltet")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="okula-make-stick pxe")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("prepare")
    p.add_argument("--iso", required=True)
    p.add_argument("--server", required=True)
    s = sp.add_parser("start")
    s.add_argument("--server", required=True)
    sp.add_parser("stop")
    sp.add_parser("allow")
    v = sp.add_parser("serve")  # vom systemd-Dienst
    v.add_argument("--bind", default="")
    args = ap.parse_args(argv)

    def emit(kind: str, text: str) -> None:
        print(f"{kind} {text}", flush=True)

    if args.cmd == "serve":
        bind = args.bind or (PXE_DIR / "bind").read_text().strip()
        ipaddress.IPv4Address(bind)
        serve(bind)
        return 0
    if os.geteuid() != 0:
        emit("ERROR", "Muss als root laufen (sudo okula-make-stick pxe …)")
        return 1
    try:
        if args.cmd == "prepare":
            key = bytes.fromhex(sys.stdin.readline().strip())
            if len(key) != 32:
                raise ValueError("Schlüssel muss 32 Bytes lang sein")
            state = prepare(args.iso, args.server, key, emit)
            emit("DONE", f"Netzwerkstart vorbereitet ({state['iso']}, Server {state['server']})")
        elif args.cmd == "start":
            ipaddress.IPv4Address(args.server)
            start(args.server, emit)
            emit("DONE", "Netzwerkstart eingeschaltet")
        elif args.cmd == "stop":
            stop(emit)
            emit("DONE", "Netzwerkstart ausgeschaltet")
        elif args.cmd == "allow":
            allow(normalize_macs(sys.stdin.read().splitlines()), emit)
            emit("DONE", "Freigabeliste aktualisiert")
    except (StickError, ValueError, OSError) as e:
        emit("ERROR", str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
