"""Agent-USB-Stick: Debian-Live-ISO auf einen USB-Stick bringen und den Agent einbauen.

Läuft als root (über /usr/local/sbin/okula-make-stick). Fortschritt als Zeilen auf stdout:
    PROGRESS <0..1> <Text>  |  WARN <Text>  |  ERROR <Text>  |  DONE <Text>

Aufbau des Sticks: MBR, eine FAT32-Partition mit dem Inhalt des Live-ISO, eigene
grub.cfg (UEFI über den GRUB des ISO, BIOS über grub-install) und ein zusätzliches
Squashfs-Image /live/okula-agent.squashfs. live-boot legt alle *.squashfs in /live
alphabetisch übereinander (spätere oben), so landen Agent, systemd-Dienst und
Banner direkt im Live-System – ohne live-config-Hooks.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

LABEL = "OKULAAGENT"  # FAT-Label, max. 11 Zeichen
MIN_SIZE = 4 * 1000**3
SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/usr", "/var", "/home", "[SWAP]")
AGENT_MODULES = ("__init__.py", "agent.py", "discovery.py", "network.py")
PACKAGE_DIR = Path(__file__).resolve().parent
SERVICE_FILE = PACKAGE_DIR.parent / "packaging" / "okula-agent.service"
GRUB_THEME_DIR = PACKAGE_DIR / "assets" / "grub"
BIOS_GRUB_DIR = Path("/usr/lib/grub/i386-pc")

Emit = Callable[[str, str], None]

AGENT_LAYER = "okula-agent.squashfs"

START_SCRIPT = """#!/bin/sh
# Startet den Okula-Agent im Live-System (aus okula-agent.squashfs des Agent-Sticks).

# Eindeutiger Hostname aus der MAC, damit mehrere Maschinen unterscheidbar sind
for i in /sys/class/net/*; do
    [ -e "$i/device" ] || continue
    MAC=$(tr -d ':' < "$i/address")
    break
done
if [ -n "$MAC" ]; then
    NAME="okula-$(echo "$MAC" | tail -c 7)"
    if [ "$(hostname)" != "$NAME" ]; then
        echo "$NAME" > /etc/hostname
        hostname "$NAME"
        grep -q "$NAME" /etc/hosts || echo "127.0.1.1 $NAME" >> /etc/hosts
    fi
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "OKULA AGENT: python3 fehlt im Live-System - Agent kann nicht starten" > /dev/console
    exec sleep infinity
fi
cd /opt/okula-recovery || exit 1
exec python3 -m okula_recovery.agent $AGENT_ARGS
"""

GRUB_CFG = """# Okula Recovery Agent - erzeugt vom Okula Recovery Tool (nur ASCII)
set timeout=3
set default=0
insmod all_video
insmod part_msdos
insmod fat
search --no-floppy --label --set=root {label}

# Grafisches Menue mit Okula-Logo; ohne Font/Grafik bleibt das Textmenue.
# GRUB-Skript kennt keinen Oder-Operator, daher if/elif
# (font.pf2 aus dem ISO bzw. fonts/unicode.pf2 von grub-install).
if loadfont /boot/grub/font.pf2; then
    set okula_font=1
elif loadfont unicode; then
    set okula_font=1
fi
if [ -n "$okula_font" ]; then
    insmod gfxterm
    insmod gfxmenu
    insmod png
    set gfxmode=auto
    terminal_output gfxterm
    set theme=/boot/grub/themes/okula/theme.txt
fi
set menu_color_normal=dark-gray/black
set menu_color_highlight=white/black

menuentry "Okula Recovery Agent" {{
    linux /live/{kernel} {params}
    initrd /live/{initrd}
}}

menuentry "Okula Recovery Agent (nomodeset)" {{
    linux /live/{kernel} {params} nomodeset
    initrd /live/{initrd}
}}
"""

BOOT_PARAMS = ("boot=live components "
               "locales=de_CH.UTF-8 keyboard-layouts=ch timezone=Europe/Zurich quiet")


class StickError(Exception):
    pass


@dataclass
class UsbDisk:
    path: str
    size: int
    model: str = ""
    vendor: str = ""
    transport: str = ""
    mountpoints: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        name = " ".join(p for p in (self.vendor, self.model) if p) or "USB-Datenträger"
        return f"{self.path} – {name} ({self.size / 1000**3:.1f} GB)"


def _flag(v) -> bool:
    return v in (True, 1, "1", "true")


def _mounts(dev: dict) -> list[str]:
    result = [m for m in dev.get("mountpoints") or [] if m]
    for child in dev.get("children") or []:
        result += _mounts(child)
    return result


def parse_lsblk_disks(output: str) -> list[UsbDisk]:
    """Wechseldatenträger aus `lsblk -J -b -o ...`; Disks mit Systempartitionen fallen weg."""
    try:
        devices = json.loads(output).get("blockdevices", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    disks = []
    for d in devices:
        if d.get("type") != "disk":
            continue
        if not (d.get("tran") == "usb" or _flag(d.get("rm")) or _flag(d.get("hotplug"))):
            continue
        mounts = _mounts(d)
        if any(m in SYSTEM_MOUNTS for m in mounts):
            continue
        disks.append(UsbDisk(path=d.get("path") or f"/dev/{d['name']}", size=int(d.get("size") or 0),
                             model=(d.get("model") or "").strip(), vendor=(d.get("vendor") or "").strip(),
                             transport=d.get("tran") or "", mountpoints=mounts))
    return disks


def list_usb_disks() -> list[UsbDisk]:
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,MODEL,VENDOR,TRAN,RM,HOTPLUG,TYPE,MOUNTPOINTS"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_lsblk_disks(out)


def find_kernel(live_dir: Path) -> tuple[str, str]:
    """Kernel und initrd im live-Ordner des ISO; ohne Versionsnummer bevorzugt."""
    def pick(prefix: str) -> str:
        names = sorted(p.name for p in live_dir.glob(prefix + "*") if p.is_file())
        if not names:
            raise StickError(f"{prefix} nicht im ISO gefunden – ist es ein Debian-Live-ISO?")
        return prefix if prefix in names else names[-1]
    return pick("vmlinuz"), pick("initrd.img")


def grub_cfg(kernel: str, initrd: str) -> str:
    return GRUB_CFG.format(label=LABEL, kernel=kernel, initrd=initrd, params=BOOT_PARAMS)


def partition_path(device: str) -> str:
    return f"{device}p1" if device[-1].isdigit() else f"{device}1"


def copy_tree(src: Path, dst: Path, progress: Callable[[int, int], None]) -> None:
    """Kopiert src nach dst und folgt dabei Symlinks (FAT32 kennt keine)."""
    files = []
    for root, _dirs, names in os.walk(src):
        for n in names:
            p = Path(root) / n
            try:
                files.append((p, p.stat().st_size))
            except OSError:
                continue  # defekter Symlink
    total = sum(s for _p, s in files) or 1
    done = 0
    for p, size in files:
        target = dst / p.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "rb") as fin, open(target, "wb") as fout:
            while chunk := fin.read(4 * 1024 * 1024):
                fout.write(chunk)
                done += len(chunk)
                progress(done, total)
            if size > 64 * 1024 * 1024:
                fout.flush()
                os.fsync(fout.fileno())  # damit der Fortschritt dem echten Schreiben folgt


def build_agent_tree(tree: Path, server_ip: str = "") -> None:
    """Dateibaum, der als oberste Schicht über dem Live-System liegt."""
    app = tree / "opt" / "okula-recovery"
    pkg = app / "okula_recovery"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in AGENT_MODULES:
        (pkg / name).write_bytes((PACKAGE_DIR / name).read_bytes())
    (app / "start-agent.sh").write_text(START_SCRIPT)
    (app / "start-agent.sh").chmod(0o755)

    etc = tree / "etc"
    units = etc / "systemd" / "system"
    wants = units / "multi-user.target.wants"
    wants.mkdir(parents=True, exist_ok=True)
    (units / "okula-agent.service").write_bytes(SERVICE_FILE.read_bytes())
    (wants / "okula-agent.service").symlink_to("/etc/systemd/system/okula-agent.service")
    args = f"--server {server_ip}" if server_ip else ""
    (etc / "okula-agent.conf").write_text(f'AGENT_ARGS="{args}"\n')
    (etc / "issue").write_bytes((PACKAGE_DIR / "assets" / "issue").read_bytes())


def install_agent(root: Path, server_ip: str = "") -> None:
    """Legt /live/okula-agent.squashfs auf den Stick (braucht mksquashfs)."""
    live = root / "live"
    live.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="okula-layer-") as tmp:
        tree = Path(tmp) / "tree"
        build_agent_tree(tree, server_ip)
        _run(["mksquashfs", str(tree), str(live / AGENT_LAYER), "-noappend", "-all-root", "-no-progress"])
    # Gibt es eine .module-Datei, lädt live-boot nur die dort gelisteten Images
    for module in (live / "filesystem.module", live / "filesystem.filesystem.module"):
        if module.is_file():
            names = module.read_text().split()
            if AGENT_LAYER not in names:
                module.write_text("\n".join(names + [AGENT_LAYER]) + "\n")


def write_boot_config(root: Path, kernel: str, initrd: str) -> None:
    grub = root / "boot" / "grub"
    theme = grub / "themes" / "okula"
    theme.mkdir(parents=True, exist_ok=True)
    for f in GRUB_THEME_DIR.iterdir():
        (theme / f.name).write_bytes(f.read_bytes())
    (grub / "grub.cfg").write_text(grub_cfg(kernel, initrd))


def _run(cmd: list[str], input: str | None = None) -> None:
    r = subprocess.run(cmd, input=input, capture_output=True, text=True)
    if r.returncode != 0:
        raise StickError(f"{' '.join(cmd)}: {(r.stderr or r.stdout).strip()}")


def prepare(device: str, iso: str, server_ip: str, emit: Emit) -> None:
    def progress(frac: float, msg: str) -> None:
        emit("PROGRESS", f"{frac:.3f} {msg}")

    progress(0.01, "Prüfe Stick und ISO")
    disk = {d.path: d for d in list_usb_disks()}.get(device)
    if disk is None:
        raise StickError(f"{device} ist kein auswählbarer USB-Stick")
    if disk.size < MIN_SIZE:
        raise StickError(f"{device} ist zu klein (mind. {MIN_SIZE // 1000**3} GB)")
    iso_path = Path(iso)
    if not iso_path.is_file():
        raise StickError(f"ISO nicht gefunden: {iso}")
    missing = [t for t in ("mksquashfs", "sfdisk", "mkfs.vfat", "wipefs") if not shutil.which(t)]
    if missing:
        raise StickError(f"Werkzeuge fehlen: {', '.join(missing)} – install.sh erneut ausführen")

    for mp in sorted(disk.mountpoints, reverse=True):
        progress(0.02, f"Hänge {mp} aus")
        _run(["umount", mp])

    progress(0.04, "Partitioniere Stick")
    _run(["wipefs", "-a", device])
    _run(["sfdisk", "--wipe", "always", device], input="label: dos\nstart=2048, type=c, bootable\n")
    # Kernel die neue Tabelle sicher einlesen lassen (sfdisk scheitert damit still, wenn das Gerät kurz belegt ist)
    subprocess.run(["partx", "-u", device], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)
    part = partition_path(device)
    for _ in range(50):
        if Path(part).exists():
            break
        time.sleep(0.2)
    else:
        raise StickError(f"Partition {part} erscheint nicht")

    progress(0.07, "Formatiere FAT32")
    _run(["mkfs.vfat", "-F", "32", "-n", LABEL, part])

    with tempfile.TemporaryDirectory(prefix="okula-iso-") as iso_mnt, \
            tempfile.TemporaryDirectory(prefix="okula-stick-") as stick_mnt:
        _run(["mount", "-o", "loop,ro", str(iso_path), iso_mnt])
        try:
            _run(["mount", part, stick_mnt])
            try:
                kernel, initrd = find_kernel(Path(iso_mnt) / "live")
                copy_tree(Path(iso_mnt), Path(stick_mnt),
                          lambda d, t: progress(0.10 + 0.78 * d / t, f"Kopiere Live-System ({d * 100 // t} %)"))
                progress(0.89, "Schreibe Boot-Konfiguration und Agent")
                write_boot_config(Path(stick_mnt), kernel, initrd)
                install_agent(Path(stick_mnt), server_ip)
                if BIOS_GRUB_DIR.is_dir() and shutil.which("grub-install"):
                    progress(0.91, "Installiere BIOS-Bootloader")
                    _run(["grub-install", "--target=i386-pc", f"--boot-directory={stick_mnt}/boot", device])
                else:
                    emit("WARN", "grub-pc-bin/grub2-common fehlt: Stick bootet nur per UEFI")
                progress(0.94, "Schreibe Daten auf den Stick (sync)")
                _run(["sync"])
            finally:
                subprocess.run(["umount", stick_mnt], capture_output=True)
        finally:
            subprocess.run(["umount", iso_mnt], capture_output=True)

    progress(1.0, "Fertig")
    emit("DONE", f"Agent-Stick auf {device} ist bereit und kann abgezogen werden")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Okula Agent-USB-Stick erstellen (löscht den Stick!)")
    ap.add_argument("--device", required=True, help="z. B. /dev/sdb")
    ap.add_argument("--iso", required=True, help="Debian-Live-ISO")
    ap.add_argument("--server", default="", help="IP des Recovery-Tools (zusätzlich zum Broadcast)")
    args = ap.parse_args(argv)

    def emit(kind: str, text: str) -> None:
        print(f"{kind} {text}", flush=True)

    if os.geteuid() != 0:
        emit("ERROR", "Muss als root laufen (sudo okula-make-stick …)")
        return 1
    try:
        if args.server:
            ipaddress.IPv4Address(args.server)
        prepare(args.device, args.iso, args.server, emit)
    except (StickError, ValueError, OSError) as e:
        emit("ERROR", str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
