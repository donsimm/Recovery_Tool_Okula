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
RESTORE_LABEL = "OKULA-REST"  # Boot-Partition des Restore-Sticks
DATA_LABEL = "OKULADATA"      # ext4-Datenpartition des Restore-Sticks (Image, Dateien > 4 GB)
IMAGE_ROOT = Path("/mnt")     # Images nur von eingehängten Freigaben (sudo-Helfer)
MIN_SIZE = 4 * 1000**3
SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/usr", "/var", "/home", "[SWAP]")
AGENT_MODULES = ("__init__.py", "agent.py", "discovery.py", "filebackup.py", "imaging.py", "inventory.py",
                 "network.py", "wininstall.py", "wire.py")
# Werkzeuge, die dem Live-Image fehlen; werden samt fehlender Abhängigkeiten aus den
# Debian-Paketen des Servers (gleiche Release) in den Agent-Layer entpackt
# lz4/lzop/pigz/bzip2: zum Zurückspielen von Clonezilla-Images
# smartmontools/libhivex-bin/ntfs-3g: Geräte-Erfassung (SMART, Windows-Version, NTFS lesend)
BUNDLED_PACKAGES = ("partclone", "zstd", "pigz", "lz4", "lzop", "bzip2", "xz-utils",
                    "smartmontools", "libhivex-bin", "ntfs-3g",
                    "efibootmgr", "dosfstools", "wimtools")  # Windows-Direktinstallation
# Ohne Paketliste des ISO nie überlagern (Basis jedes Systems)
NEVER_BUNDLE = ("libc6", "libgcc-s1", "libstdc++6", "gcc-")
PACKAGE_DIR = Path(__file__).resolve().parent
SERVICE_FILE = PACKAGE_DIR.parent / "packaging" / "okula-agent.service"
GRUB_THEME_DIR = PACKAGE_DIR / "assets" / "grub"
BIOS_GRUB_DIR = Path("/usr/lib/grub/i386-pc")
RESTORE_MODULES = AGENT_MODULES + ("agentclient.py", "clonezilla.py", "config.py", "standalone.py")
RESTORE_SERVICE_FILE = PACKAGE_DIR.parent / "packaging" / "okula-restore.service"

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
# Mitgelieferte Bibliotheken (partclone) bekannt machen
ldconfig 2>/dev/null || true

cd /opt/okula-recovery || exit 1
exec python3 -m okula_recovery.agent --console /dev/tty1 $AGENT_ARGS
"""

START_RESTORE_SCRIPT = """#!/bin/sh
# Startet die Bildschirmführung des Restore-Sticks auf tty1.
ldconfig 2>/dev/null || true
if ! command -v python3 >/dev/null 2>&1; then
    echo "OKULA: python3 fehlt im Live-System - Restore nicht möglich"
    exec sleep infinity
fi
cd /opt/okula-recovery || exit 1
exec python3 -m okula_recovery.standalone --console /dev/tty1
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

menuentry "{title}" {{
    linux /live/{kernel} {params}
    initrd /live/{initrd}
}}

menuentry "{title} (nomodeset)" {{
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


def grub_cfg(kernel: str, initrd: str, label: str = LABEL, title: str = "Okula Recovery Agent") -> str:
    return GRUB_CFG.format(label=label, kernel=kernel, initrd=initrd, params=BOOT_PARAMS, title=title)


def partition_path(device: str, number: int = 1) -> str:
    return f"{device}p{number}" if device[-1].isdigit() else f"{device}{number}"


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


def read_installed_packages(path: Path) -> set[str] | None:
    """Paketliste des Live-Systems (live/filesystem.packages im ISO): „name[:arch]<TAB>version“."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    return {line.split()[0].split(":")[0] for line in lines if line.strip()}


def parse_apt_depends(output: str) -> list[str]:
    """Paketnamen aus `apt-cache depends --recurse …` (eingerückte Zeilen und <virtuelle> weg)."""
    names = []
    for line in output.splitlines():
        if not line or line[0].isspace() or line.startswith("<"):
            continue
        name = line.strip().split(":")[0]
        if name not in names:
            names.append(name)
    return names


def packages_to_bundle(packages: tuple[str, ...], installed: set[str] | None) -> list[str]:
    r = subprocess.run(["apt-cache", "depends", "--recurse", "--no-recommends", "--no-suggests",
                        "--no-conflicts", "--no-breaks", "--no-replaces", "--no-enhances", *packages],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise StickError(f"apt-cache: {r.stderr.strip()}")
    names = parse_apt_depends(r.stdout)
    if installed is not None:
        return [n for n in names if n not in installed]
    return [n for n in names if not n.startswith(NEVER_BUNDLE)]


MERGED_USR_DIRS = ("bin", "sbin", "lib", "lib32", "lib64", "libx32")


def merge_usr(tree: Path) -> None:
    """Verschiebt /bin, /lib … der Pakete nach /usr/….

    Im Live-System sind /bin, /lib usw. Symlinks nach usr/ (merged /usr). Ein echtes
    Verzeichnis gleichen Namens im oberen Layer würde den Symlink verdecken und das
    System unbrauchbar machen.
    """
    for name in MERGED_USR_DIRS:
        src = tree / name
        if src.is_symlink() or not src.is_dir():
            continue
        for root, _dirs, files in os.walk(src, topdown=False):
            rel = Path(root).relative_to(src)
            dst_dir = tree / "usr" / name / rel
            dst_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                os.replace(Path(root) / f, dst_dir / f)
            for d in _dirs:
                p = Path(root) / d
                if p.is_symlink():
                    os.replace(p, dst_dir / d)
            Path(root).rmdir()


def bundle_packages(names: list[str], tree: Path) -> None:
    """Lädt die .deb-Dateien und entpackt sie in den Agent-Layer (ohne Installation)."""
    with tempfile.TemporaryDirectory(prefix="okula-debs-") as tmp:
        r = subprocess.run(["apt-get", "download", "-o", "APT::Sandbox::User=root", *names],
                           cwd=tmp, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise StickError(f"apt-get download: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
        for deb in sorted(Path(tmp).glob("*.deb")):
            _run(["dpkg-deb", "-x", str(deb), str(tree)])
    merge_usr(tree)


def build_agent_tree(tree: Path, server_ip: str = "", key: bytes | None = None, mode: str = "agent") -> None:
    """Dateibaum, der als oberste Schicht über dem Live-System liegt (mode: agent | restore)."""
    app = tree / "opt" / "okula-recovery"
    pkg = app / "okula_recovery"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in RESTORE_MODULES if mode == "restore" else AGENT_MODULES:
        (pkg / name).write_bytes((PACKAGE_DIR / name).read_bytes())
    etc = tree / "etc"
    units = etc / "systemd" / "system"
    wants = units / "multi-user.target.wants"
    wants.mkdir(parents=True, exist_ok=True)

    if mode == "restore":
        (app / "start-restore.sh").write_text(START_RESTORE_SCRIPT)
        (app / "start-restore.sh").chmod(0o755)
        (units / "okula-restore.service").write_bytes(RESTORE_SERVICE_FILE.read_bytes())
        (wants / "okula-restore.service").symlink_to("/etc/systemd/system/okula-restore.service")
        # tty1 gehört der Bildschirmführung: Autologin-Konsole dort abschalten
        (units / "getty@tty1.service").symlink_to("/dev/null")
        (etc / "issue").write_bytes((PACKAGE_DIR / "assets" / "issue-restore").read_bytes())
        return

    (app / "start-agent.sh").write_text(START_SCRIPT)
    (app / "start-agent.sh").chmod(0o755)
    (units / "okula-agent.service").write_bytes(SERVICE_FILE.read_bytes())
    (wants / "okula-agent.service").symlink_to("/etc/systemd/system/okula-agent.service")
    args = f"--server {server_ip}" if server_ip else ""
    (etc / "okula-agent.conf").write_text(f'AGENT_ARGS="{args}"\n')
    (etc / "issue").write_bytes((PACKAGE_DIR / "assets" / "issue").read_bytes())
    if key:
        fd = os.open(etc / "okula-agent.key", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key.hex() + "\n")


def install_agent(root: Path, server_ip: str = "", key: bytes | None = None,
                  installed: set[str] | None = None, bundle: bool = False,
                  emit: Emit | None = None, mode: str = "agent") -> None:
    """Legt /live/okula-agent.squashfs auf den Stick (braucht mksquashfs).

    bundle=True: partclone/zstd mitliefern; installed = Pakete des Live-Systems (None = unbekannt).
    """
    live = root / "live"
    live.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="okula-layer-") as tmp:
        tree = Path(tmp) / "tree"
        build_agent_tree(tree, server_ip, key, mode)
        if bundle:
            try:
                names = packages_to_bundle(BUNDLED_PACKAGES, installed)
                if names:
                    bundle_packages(names, tree)
                if emit:
                    emit("WARN" if installed is None else "INFO",
                         f"Mitgeliefert: {', '.join(names) or 'nichts nötig'}"
                         + (" (Paketliste des ISO fehlt)" if installed is None else ""))
            except (StickError, OSError, subprocess.TimeoutExpired) as e:
                if emit:
                    emit("WARN", f"partclone nicht mitgeliefert – Disk-Images nicht möglich: {e}")
        _run(["mksquashfs", str(tree), str(live / AGENT_LAYER), "-noappend", "-all-root", "-no-progress"])
    # Gibt es eine .module-Datei, lädt live-boot nur die dort gelisteten Images
    for module in (live / "filesystem.module", live / "filesystem.filesystem.module"):
        if module.is_file():
            names = module.read_text().split()
            if AGENT_LAYER not in names:
                module.write_text("\n".join(names + [AGENT_LAYER]) + "\n")


def write_boot_config(root: Path, kernel: str, initrd: str, label: str = LABEL,
                      title: str = "Okula Recovery Agent") -> None:
    grub = root / "boot" / "grub"
    theme = grub / "themes" / "okula"
    theme.mkdir(parents=True, exist_ok=True)
    for f in GRUB_THEME_DIR.iterdir():
        (theme / f.name).write_bytes(f.read_bytes())
    (grub / "grub.cfg").write_text(grub_cfg(kernel, initrd, label, title))


def _run(cmd: list[str], input: str | None = None) -> None:
    r = subprocess.run(cmd, input=input, capture_output=True, text=True)
    if r.returncode != 0:
        raise StickError(f"{' '.join(cmd)}: {(r.stderr or r.stdout).strip()}")


MIB = 1024 * 1024


def tree_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def check_image(image: str, source_disk: str | None) -> tuple[Path, dict]:
    """Image für den Restore-Stick: nur unter /mnt (NAS), muss sich als Okula/Clonezilla laden lassen."""
    from okula_recovery import agentclient  # erst hier: der Agent-Stick braucht es nicht

    path = Path(image).resolve()
    if not path.is_relative_to(IMAGE_ROOT) or not path.is_dir():
        raise StickError(f"Image muss ein Ordner unter {IMAGE_ROOT} sein: {image}")
    try:
        src = agentclient.image_source(path, source_disk)
    except agentclient.AgentError as e:
        raise StickError(f"Image nicht verwendbar: {e}") from None
    return path, src


def restore_need(iso_size: int, image_size: int) -> tuple[int, int]:
    """(Boot-Partition in MiB, nötige Stickgrösse in Byte) für einen Restore-Stick."""
    boot_mib = max(1536, (iso_size + 512 * MIB) // MIB + 1)
    return boot_mib, boot_mib * MIB + int(image_size * 1.03) + 256 * MIB  # ext4-Verwaltung + Reserve


def restore_layout(iso_size: int, image_size: int, stick_size: int) -> tuple[int, str]:
    """(Grösse Boot-Partition in MiB, sfdisk-Skript); Fehler, wenn das Image nicht passt."""
    boot_mib, need = restore_need(iso_size, image_size)
    if stick_size < need:
        raise StickError(f"Stick zu klein: {stick_size / 1000**3:.1f} GB, nötig sind {need / 1000**3:.1f} GB")
    return boot_mib, f"label: dos\nstart=2048, size={boot_mib}MiB, type=c, bootable\nstart=, type=83\n"


def restore_config(src: dict, image: Path, source_disk: str | None) -> dict:
    from okula_recovery import __version__
    return {"format": src.get("format", "okula"), "image_name": image.name,
            "label": src.get("label") or image.name, "source_disk": source_disk,
            "created": time.strftime("%Y-%m-%d %H:%M"), "tool_version": __version__}


def prepare(device: str, iso: str, server_ip: str, emit: Emit, key: bytes | None = None,
            image: str | None = None, source_disk: str | None = None) -> None:
    """Agent-Stick (image=None) oder Restore-Stick mit einem Image erstellen."""
    def progress(frac: float, msg: str) -> None:
        emit("PROGRESS", f"{frac:.3f} {msg}")

    restore = image is not None
    label = RESTORE_LABEL if restore else LABEL
    title = "Okula Restore-Stick" if restore else "Okula Recovery Agent"

    progress(0.01, "Prüfe Stick und ISO")
    disk = {d.path: d for d in list_usb_disks()}.get(device)
    if disk is None:
        raise StickError(f"{device} ist kein auswählbarer USB-Stick")
    if disk.size < MIN_SIZE:
        raise StickError(f"{device} ist zu klein (mind. {MIN_SIZE // 1000**3} GB)")
    iso_path = Path(iso)
    if not iso_path.is_file():
        raise StickError(f"ISO nicht gefunden: {iso}")
    missing = [t for t in ("mksquashfs", "sfdisk", "mkfs.vfat", "wipefs") + (("mkfs.ext4",) if restore else ())
               if not shutil.which(t)]
    if missing:
        raise StickError(f"Werkzeuge fehlen: {', '.join(missing)} – install.sh erneut ausführen")
    table = "label: dos\nstart=2048, type=c, bootable\n"
    if restore:
        progress(0.02, "Prüfe Image")
        image_path, src = check_image(image, source_disk)
        image_size = tree_size(image_path)
        _boot_mib, table = restore_layout(iso_path.stat().st_size, image_size, disk.size)

    for mp in sorted(disk.mountpoints, reverse=True):
        progress(0.02, f"Hänge {mp} aus")
        _run(["umount", mp])

    progress(0.04, "Partitioniere Stick")
    _run(["wipefs", "-a", device])
    _run(["sfdisk", "--wipe", "always", device], input=table)
    # Kernel die neue Tabelle sicher einlesen lassen (sfdisk scheitert damit still, wenn das Gerät kurz belegt ist)
    subprocess.run(["partx", "-u", device], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)
    part = partition_path(device)
    data_part = partition_path(device, 2) if restore else None
    for _ in range(50):
        if all(Path(p).exists() for p in (part, data_part) if p):
            break
        time.sleep(0.2)
    else:
        raise StickError(f"Partition {part} erscheint nicht")

    progress(0.07, "Formatiere FAT32")
    _run(["mkfs.vfat", "-F", "32", "-n", label, part])
    if data_part:
        progress(0.08, "Formatiere Datenpartition (ext4)")
        _run(["mkfs.ext4", "-q", "-F", "-L", DATA_LABEL, "-m", "0", data_part])
    iso_share = 0.25 if restore else 0.78

    with tempfile.TemporaryDirectory(prefix="okula-iso-") as iso_mnt, \
            tempfile.TemporaryDirectory(prefix="okula-stick-") as stick_mnt:
        _run(["mount", "-o", "loop,ro", str(iso_path), iso_mnt])
        try:
            _run(["mount", part, stick_mnt])
            try:
                kernel, initrd = find_kernel(Path(iso_mnt) / "live")
                copy_tree(Path(iso_mnt), Path(stick_mnt),
                          lambda d, t: progress(0.10 + iso_share * d / t, f"Kopiere Live-System ({d * 100 // t} %)"))
                at = 0.10 + iso_share
                progress(at, "Schreibe Boot-Konfiguration")
                write_boot_config(Path(stick_mnt), kernel, initrd, label, title)
                progress(at + 0.01, "Lade partclone/zstd und baue Layer")
                installed = read_installed_packages(Path(iso_mnt) / "live" / "filesystem.packages")
                install_agent(Path(stick_mnt), server_ip, key if not restore else None, installed, bundle=True,
                              emit=emit, mode="restore" if restore else "agent")
                if BIOS_GRUB_DIR.is_dir() and shutil.which("grub-install"):
                    progress(0.91, "Installiere BIOS-Bootloader")
                    _run(["grub-install", "--target=i386-pc", f"--boot-directory={stick_mnt}/boot", device])
                else:
                    emit("WARN", "grub-pc-bin/grub2-common fehlt: Stick bootet nur per UEFI")
                if restore:
                    copy_image_to_data(data_part, image_path, src, source_disk, progress)
                progress(0.97, "Schreibe Daten auf den Stick (sync)")
                _run(["sync"])
            finally:
                subprocess.run(["umount", stick_mnt], capture_output=True)
        finally:
            subprocess.run(["umount", iso_mnt], capture_output=True)

    progress(1.0, "Fertig")
    what = f"Restore-Stick mit „{Path(image).name}“" if restore else "Agent-Stick"
    emit("DONE", f"{what} auf {device} ist bereit und kann abgezogen werden")


def copy_image_to_data(data_part: str, image: Path, src: dict, source_disk: str | None,
                       progress: Callable[[float, str], None]) -> None:
    """Image auf die ext4-Datenpartition kopieren und die Beschreibung für den Stick schreiben."""
    with tempfile.TemporaryDirectory(prefix="okula-data-") as data_mnt:
        _run(["mount", data_part, data_mnt])
        try:
            install_image(Path(data_mnt), image, src, source_disk,
                          lambda d, t: progress(0.40 + 0.56 * d / t,
                                                f"Kopiere Image ({d // 1000**2} / {t // 1000**2} MB)"))
            _run(["sync"])
        finally:
            subprocess.run(["umount", data_mnt], capture_output=True)


def install_image(data_root: Path, image: Path, src: dict, source_disk: str | None,
                  progress: Callable[[int, int], None]) -> None:
    from okula_recovery import standalone

    copy_tree(image, data_root / standalone.IMAGE_DIR, progress)
    (data_root / standalone.CONFIG_FILE).write_text(
        json.dumps(restore_config(src, image, source_disk), indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["iso-stick"]:  # Boot-Stick aus ISO (gleicher Root-Helfer, gleiche sudo-Regel)
        from okula_recovery import isostick
        return isostick.main(argv[1:])
    if argv[:1] in (["usb-clone"], ["usb-format"]):  # Tools → USB klonen / formatieren
        from okula_recovery import usbtools
        return usbtools.main(argv)
    if argv[:1] == ["pxe"]:  # Netzwerkstart vorbereiten / ein / aus / Freigabeliste
        from okula_recovery import pxe
        return pxe.main(argv[1:])
    ap = argparse.ArgumentParser(description="Okula Agent-USB-Stick erstellen (löscht den Stick!)")
    ap.add_argument("--device", required=True, help="z. B. /dev/sdb")
    ap.add_argument("--iso", required=True, help="Debian-Live-ISO")
    ap.add_argument("--server", default="", help="IP des Recovery-Tools (zusätzlich zum Broadcast)")
    ap.add_argument("--key-stdin", action="store_true", help="Agent-Schlüssel (hex) von stdin lesen")
    ap.add_argument("--image", help="Restore-Stick: Image-Ordner (Okula oder Clonezilla) unter /mnt")
    ap.add_argument("--source-disk", help="Restore-Stick, Clonezilla mit mehreren Disks: welche")
    args = ap.parse_args(argv)

    def emit(kind: str, text: str) -> None:
        print(f"{kind} {text}", flush=True)

    if os.geteuid() != 0:
        emit("ERROR", "Muss als root laufen (sudo okula-make-stick …)")
        return 1
    try:
        if args.server:
            ipaddress.IPv4Address(args.server)
        key = None
        if args.key_stdin:
            key = bytes.fromhex(sys.stdin.readline().strip())
            if len(key) != 32:
                raise ValueError("Schlüssel muss 32 Bytes lang sein")
        prepare(args.device, args.iso, args.server, emit, key, args.image, args.source_disk)
    except (StickError, ValueError, OSError) as e:
        emit("ERROR", str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
