"""Linux direkt auf ein Gerät installieren (Tool-Seite): Ubuntu Desktop (ab 24.04) und Debian.

Gemeinsam: Der Agent legt eine EFI-Partition an (Bootdateien der ISO: signiertes shim + grub, Secure Boot geht),
setzt BootNext darauf und startet neu. Der Platz dahinter bleibt frei – dorthin installiert der offizielle
Installer automatisch.

Ubuntu: Die ISO liegt als Datei auf einer Setup-Partition am Disk-Ende (ext4), GRUB startet sie per Loopback,
        die Autoinstall-Antworten liegen auf einer kleinen Partition „CIDATA“ (cloud-init). Installiert wird
        in die Lücke (layout direct, mode use_gap). Beim ersten Start entfernt okula-cleanup die Setup-
        Partitionen und vergrössert die Systempartition.
Debian: Netzwerk-Installer (Kernel + initrd von deb.debian.org, gegen SHA256SUMS geprüft) mit Preseed,
        Partitionierung im grössten freien Bereich; Pakete aus dem Internet.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import re
import secrets
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from okula_recovery import oslib

SECTOR = 512
ALIGN = 2048                         # 1 MiB
MIB = 1024 * 1024
ESP_MIB = 512
CIDATA_MIB = 16
SETUP_RESERVE = 512 * MIB            # ext4-Verwaltung + Reserve
MIN_GAP = 25 * 1000**3               # Platz für das System
GPT_ESP = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
GPT_LINUX = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
GPT_DATA = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
ESP_LABEL, SETUP_LABEL, CIDATA_LABEL = "OKULAEFI", "OKULASETUP", "CIDATA"
BOOT_LABEL = "Okula Linux-Installation"
ISO_NAME = "ubuntu.iso"
NETBOOT = "https://deb.debian.org/debian/dists/{codename}/main/installer-amd64/current/images"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "okula-recovery" / "netboot"


class LinuxSetupError(Exception):
    pass


@dataclass
class LinuxOptions:
    username: str
    password: str
    hostname: str
    swiss_region: bool = True
    desktop: bool = True             # Debian: GNOME-Desktop (Ubuntu Desktop hat ihn immer)


@dataclass
class BootPlan:
    install_id: str
    table: str
    parts: list[dict]
    files: list[tuple[str, str, int, Path]]             # (Partition, Zielpfad, Grösse, Quelle)
    extra: list[dict] = field(default_factory=list)      # {part, path, text}
    lines: list[str] = field(default_factory=list)       # Beschreibung für das Log
    workdir: tempfile.TemporaryDirectory | None = None   # ausgepackte Bootdateien, lebt bis zum Ende

    def request(self, disk: str) -> dict:
        return {"cmd": "bootprep", "disk": disk, "table": self.table, "parts": self.parts,
                "files": [{"part": p, "path": path, "size": size} for p, path, size, _src in self.files],
                "extra": self.extra, "boot": {"part": 1, "label": BOOT_LABEL}, "reboot": True}

    def cleanup(self) -> None:
        if self.workdir is not None:
            self.workdir.cleanup()


# ---------- Eingaben prüfen ----------

def hostname(name: str) -> str:
    """Gültiger Linux-Hostname: Kleinbuchstaben, Ziffern, Bindestrich, max. 63 Zeichen."""
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "ae"), ("Ö", "oe"), ("Ü", "ue")):
        name = name.replace(a, b)
    cleaned = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:63].strip("-")
    return cleaned or "okula-pc"


def username(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]", "", name.lower())
    if not cleaned or not cleaned[0].isalpha():
        raise LinuxSetupError("Benutzername: Kleinbuchstaben, Ziffern, - und _; beginnt mit einem Buchstaben")
    if cleaned in ("root", "admin", "ubuntu", "debian"):
        raise LinuxSetupError(f"Benutzername „{cleaned}“ ist reserviert")
    return cleaned[:32]


def hash_password(password: str) -> str:
    """SHA-512-crypt wie in /etc/shadow (über openssl, das Passwort geht nicht über die Befehlszeile)."""
    if len(password) < 4:
        raise LinuxSetupError("Passwort: mindestens 4 Zeichen")
    try:
        r = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=password + "\n", capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise LinuxSetupError(f"openssl fehlt: {e}") from None
    if r.returncode != 0 or not r.stdout.startswith("$6$"):
        raise LinuxSetupError(f"Passwort konnte nicht verschlüsselt werden: {r.stderr.strip()}")
    return r.stdout.strip()


def kind(meta: dict) -> str:
    """„ubuntu“, „debian“ oder „“ (nicht direkt installierbar)."""
    lx = meta.get("linux") or {}
    if lx.get("kind") == "casper" and lx.get("distro") == "ubuntu":
        try:
            major, minor = (int(x) for x in (lx.get("version") or "0.0").split(".")[:2])
        except ValueError:
            return ""
        return "ubuntu" if (major, minor) >= (24, 4) else ""
    if lx.get("kind") == "debian-installer" and lx.get("distro") == "debian" and codename(meta):
        return "debian"
    return ""


def codename(meta: dict) -> str:
    m = re.search(r'"([A-Za-z]+)"', (meta.get("linux") or {}).get("info", ""))
    return m.group(1).lower() if m else ""


# ---------- Partitionstabelle ----------

def _align_down(n: int) -> int:
    return n // ALIGN * ALIGN


def table(disk_size: int, setup_size: int = 0) -> tuple[str, list[dict]]:
    """EFI vorne, (Ubuntu:) Setup + CIDATA am Ende, dazwischen frei für das System."""
    sectors = disk_size // SECTOR
    last = sectors - 34                                   # GPT-Kopie am Ende
    esp_end = ALIGN + ESP_MIB * MIB // SECTOR
    lines = ["label: gpt",
             f'start={ALIGN}, size={ESP_MIB * MIB // SECTOR}, type={GPT_ESP}, name="EFI system partition"']
    parts = [{"number": 1, "fs": "fat32", "label": ESP_LABEL, "key": "esp"}]
    gap_end = last
    if setup_size:
        cidata_size = CIDATA_MIB * MIB // SECTOR
        setup_sectors = -(-setup_size // (MIB)) * MIB // SECTOR
        cidata_start = _align_down(last + 1 - cidata_size)
        setup_start = _align_down(cidata_start - setup_sectors)
        lines += [f'start={setup_start}, size={cidata_start - setup_start}, type={GPT_LINUX}, name="Okula Setup"',
                  f'start={cidata_start}, size={cidata_size}, type={GPT_DATA}, name="CIDATA"']
        parts += [{"number": 2, "fs": "ext4", "label": SETUP_LABEL, "key": "setup"},
                  {"number": 3, "fs": "fat32", "label": CIDATA_LABEL, "key": "cidata"}]
        gap_end = setup_start
    if (gap_end - esp_end) * SECTOR < MIN_GAP:
        raise LinuxSetupError(f"Zieldisk zu klein: {disk_size / 1000**3:.0f} GB "
                              f"(mind. {(MIN_GAP + ESP_MIB * MIB + setup_size) / 1000**3:.0f} GB)")
    return "\n".join(lines) + "\n", parts


# ---------- Dateien aus der ISO ----------

def _extract(iso: Path, dest: Path, paths: list[str]) -> None:
    present = {p.lower(): p for p in oslib._xorriso_paths(iso)}
    args = []
    for p in paths:
        real = present.get(p.lower())
        if real:
            args += ["-extract", real, str(dest / real.lstrip("/"))]
    if not args:
        raise LinuxSetupError("Keine Bootdateien im Medium gefunden")
    r = subprocess.run(["xorriso", "-osirrox", "on", "-indev", str(iso), *args], capture_output=True, text=True,
                       timeout=600)
    if r.returncode != 0:
        raise LinuxSetupError(f"xorriso: {r.stderr.strip().splitlines()[-1:]}")
    for f in dest.rglob("*"):
        f.chmod(0o755 if f.is_dir() else 0o644)  # Dateien aus der ISO sind schreibgeschützt


def _tree(root: Path, part: str, prefix: str = "") -> list[tuple[str, str, int, Path]]:
    return [(part, prefix + str(f.relative_to(root)), f.stat().st_size, f)
            for f in sorted(root.rglob("*")) if f.is_file()]


def _grub_copies(cfg: str, part: str = "esp") -> list[dict]:
    """Eigene grub.cfg überall, wo das signierte GRUB der ISO sucht."""
    return [{"part": part, "path": p, "text": cfg}
            for p in ("boot/grub/grub.cfg", "boot/grub/x86_64-efi/grub.cfg", "EFI/boot/grub.cfg",
                      "EFI/BOOT/grub.cfg", "EFI/debian/grub.cfg", "EFI/ubuntu/grub.cfg")]


CLEANUP_SCRIPT = """#!/bin/sh
# Okula Recovery Tool: nach der Direktinstallation die Setup-Partitionen entfernen und / vergrössern
set -u
root=$(findmnt -no SOURCE /)
disk=/dev/$(lsblk -no PKNAME "$root" | head -n1)
for label in OKULASETUP CIDATA; do
    dev=$(blkid -L "$label" 2>/dev/null) || continue
    num=$(cat "/sys/class/block/$(basename "$dev")/partition")
    umount "$dev" 2>/dev/null
    sfdisk --no-reread --delete "$disk" "$num"
done
partx -u "$disk" 2>/dev/null
num=$(cat "/sys/class/block/$(basename "$root")/partition")
parted -s "$disk" resizepart "$num" 100% && resize2fs "$root"
for b in $(efibootmgr | sed -n 's/^Boot\\([0-9A-Fa-f]\\{4\\}\\)\\*\\{0,1\\} Okula.*/\\1/p'); do efibootmgr -q -B -b "$b"; done
rm -rf /boot/efi/boot /boot/efi/.disk /boot/efi/okula
systemctl disable okula-cleanup.service
rm -f /etc/systemd/system/okula-cleanup.service /usr/local/sbin/okula-cleanup
"""

CLEANUP_SERVICE = """[Unit]
Description=Okula Recovery Tool: Setup-Partitionen entfernen
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/okula-cleanup

[Install]
WantedBy=multi-user.target
"""


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def ubuntu_userdata(opts: LinuxOptions, password_hash: str) -> str:
    """cloud-init/Autoinstall – JSON-Strings sind gültiges YAML (kein Escaping-Ärger)."""
    q = json.dumps
    late = [
        f"echo {_b64(CLEANUP_SCRIPT)} | base64 -d > /target/usr/local/sbin/okula-cleanup",
        "chmod 755 /target/usr/local/sbin/okula-cleanup",
        f"echo {_b64(CLEANUP_SERVICE)} | base64 -d > /target/etc/systemd/system/okula-cleanup.service",
        "curtin in-target -- systemctl enable okula-cleanup.service",
    ]
    lines = ["#cloud-config", "autoinstall:", "  version: 1", "  interactive-sections: []"]
    if opts.swiss_region:
        lines += ['  locale: "de_CH.UTF-8"', "  keyboard:", '    layout: "ch"', '  timezone: "Europe/Zurich"']
    lines += ["  identity:", f"    hostname: {q(hostname(opts.hostname))}", f"    realname: {q(opts.username)}",
              f"    username: {q(username(opts.username))}", f"    password: {q(password_hash)}",
              "  storage:", "    layout:", "      name: direct", "      mode: use_gap",
              "  late-commands:"] + [f"    - {q(c)}" for c in late] + ["  shutdown: reboot"]
    return "\n".join(lines) + "\n"


def debian_preseed(opts: LinuxOptions, password_hash: str, disk: str) -> str:
    user = username(opts.username)
    host = hostname(opts.hostname)
    locale = "de_CH.UTF-8" if opts.swiss_region else "en_US.UTF-8"
    tasks = "standard, gnome-desktop" if opts.desktop else "standard"
    late = ("in-target sh -c 'for b in $(efibootmgr | sed -n \"s/^Boot\\([0-9A-Fa-f]\\{4\\}\\)\\*\\{0,1\\} Okula.*/\\1/p\"); "
            "do efibootmgr -q -B -b $b; done'; rm -rf /target/boot/efi/okula /target/boot/efi/boot "
            "/target/boot/efi/.disk")
    return f"""# Okula Recovery Tool – Debian-Direktinstallation
d-i debian-installer/locale string {locale}
d-i localechooser/supported-locales multiselect {locale}
d-i keyboard-configuration/xkb-keymap select {"ch" if opts.swiss_region else "us"}
d-i hw-detect/load_firmware boolean true
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string {host}
d-i netcfg/hostname string {host}
d-i netcfg/get_domain string
d-i mirror/country string manual
d-i mirror/http/hostname string deb.debian.org
d-i mirror/http/directory string /debian
d-i mirror/http/proxy string
d-i passwd/root-login boolean false
d-i passwd/user-fullname string {opts.username}
d-i passwd/username string {user}
d-i passwd/user-password-crypted password {password_hash}
d-i clock-setup/utc boolean true
d-i time/zone string {"Europe/Zurich" if opts.swiss_region else "UTC"}
d-i clock-setup/ntp boolean true
d-i partman-auto/disk string {disk}
d-i partman-auto/init_automatically_partition select biggest_free
d-i partman-auto/method string regular
d-i partman-auto/choose_recipe select atomic
d-i partman-efi/non_efi_system boolean true
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true
d-i apt-setup/non-free-firmware boolean true
d-i apt-setup/cdrom/set-first boolean false
tasksel tasksel/first multiselect {tasks}
d-i pkgsel/upgrade select full-upgrade
popularity-contest popularity-contest/participate boolean false
d-i grub-installer/only_debian boolean true
d-i grub-installer/bootdev string {disk}
d-i finish-install/reboot_in_progress note
d-i preseed/late_command string {late}
"""


def cpio_newc(files: dict[str, bytes]) -> bytes:
    """Minimales cpio (newc) – wird als zweites initrd an den Debian-Installer gehängt (/preseed.cfg)."""
    out = bytearray()
    ino = 1

    def entry(name: str, data: bytes, mode: int) -> None:
        nonlocal ino
        raw = name.encode() + b"\0"
        header = "070701" + "".join(f"{v:08X}" for v in (ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(raw), 0))
        out.extend(header.encode() + raw)
        out.extend(b"\0" * (-len(out) % 4))
        out.extend(data)
        out.extend(b"\0" * (-len(out) % 4))
        ino += 1

    for name, data in files.items():
        entry(name, data, 0o100644)
    entry("TRAILER!!!", b"", 0)
    return bytes(out)


# ---------- Debian-Netzwerk-Installer ----------

def netboot(code: str, progress=lambda done, total: None) -> tuple[Path, Path]:
    """Kernel und initrd des Debian-Netzwerk-Installers (einmal laden, dann aus dem Zwischenspeicher)."""
    base = NETBOOT.format(codename=code)
    target = CACHE / code
    target.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(f"{base}/SHA256SUMS", timeout=30) as r:
            sums = r.read().decode()
    except OSError as e:
        raise LinuxSetupError(f"Debian-Installer nicht erreichbar ({base}): {e}") from None
    files = []
    for name in ("linux", "initrd.gz"):
        rel = f"./netboot/debian-installer/amd64/{name}"
        m = re.search(rf"^([0-9a-f]{{64}})\s+{re.escape(rel)}$", sums, re.M)
        if not m:
            raise LinuxSetupError(f"{rel} fehlt in SHA256SUMS")
        path = target / name
        if not (path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == m.group(1)):
            tmp = path.with_suffix(".part")
            with urllib.request.urlopen(f"{base}/{rel[2:]}", timeout=60) as r, open(tmp, "wb") as out:
                total, done = int(r.headers.get("Content-Length") or 0), 0
                while chunk := r.read(1024 * 1024):
                    out.write(chunk)
                    done += len(chunk)
                    progress(done, total)
            if hashlib.sha256(tmp.read_bytes()).hexdigest() != m.group(1):
                tmp.unlink()
                raise LinuxSetupError(f"Prüfsumme von {name} stimmt nicht – Download beschädigt")
            tmp.replace(path)
        files.append(path)
    return files[0], files[1]


# ---------- Pläne ----------

def plan(iso: str | Path, meta: dict, disk: str, disk_size: int, opts: LinuxOptions) -> BootPlan:
    which = kind(meta)
    if not which:
        raise LinuxSetupError("Dieses Medium lässt sich nicht direkt installieren (Ubuntu ab 24.04 oder Debian)")
    iso = Path(iso)
    pw = hash_password(opts.password)
    install_id = secrets.token_hex(4)
    work = tempfile.TemporaryDirectory(prefix="okula-linux-")
    root = Path(work.name)
    try:
        boot = root / "iso"
        if which == "ubuntu":
            _extract(iso, boot, ["/EFI", "/boot/grub", "/.disk"])
            paths = {p.lower() for p in oslib._xorriso_paths(iso)}
            kernel = next((k for k in ("/casper/vmlinuz", "/casper/hwe-vmlinuz") if k in paths), None)
            initrd = next((k for k in ("/casper/initrd", "/casper/hwe-initrd", "/casper/initrd.gz") if k in paths),
                          None)
            if not kernel or not initrd:
                raise LinuxSetupError("Kernel/initrd (casper) nicht im Medium gefunden")
            size = iso.stat().st_size
            tbl, parts = table(disk_size, size + SETUP_RESERVE)
            cfg = f"""# Okula Recovery Tool – Ubuntu-Direktinstallation ({install_id})
set timeout=3
set default=0
search --no-floppy --label --set=okula {SETUP_LABEL}
loopback loop ($okula)/{ISO_NAME}
menuentry "Okula: Ubuntu automatisch installieren" {{
    linux (loop){kernel} iso-scan/filename=/{ISO_NAME} autoinstall quiet splash ---
    initrd (loop){initrd}
}}
"""
            files = _tree(boot, "esp") + [("setup", ISO_NAME, size, iso)]
            extra = _grub_copies(cfg) + [
                {"part": "cidata", "path": "user-data", "text": ubuntu_userdata(opts, pw)},
                {"part": "cidata", "path": "meta-data", "text": f"instance-id: okula-{install_id}\n"}]
            lines = [f"Ubuntu: ISO ({size / 1000**3:.1f} GB) auf die Setup-Partition, Autoinstall in den freien "
                     "Platz (use_gap)", f"Benutzer {username(opts.username)}, Computername {hostname(opts.hostname)}"]
        else:
            _extract(iso, boot, ["/EFI", "/boot/grub", "/.disk"])
            linux, initrd = netboot(codename(meta))
            preseed = gzip.compress(cpio_newc({"preseed.cfg": debian_preseed(opts, pw, disk).encode()}))
            pre = root / "preseed.cpio.gz"
            pre.write_bytes(preseed)
            tbl, parts = table(disk_size)
            locale = "de_CH.UTF-8" if opts.swiss_region else "en_US.UTF-8"
            cfg = f"""# Okula Recovery Tool – Debian-Direktinstallation ({install_id})
set timeout=3
set default=0
search --no-floppy --label --set=root {ESP_LABEL}
menuentry "Okula: Debian automatisch installieren" {{
    linux /okula/linux priority=critical locale={locale} keyboard-configuration/xkb-keymap={"ch" if opts.swiss_region else "us"} netcfg/get_hostname={hostname(opts.hostname)} --- quiet
    initrd /okula/initrd.gz /okula/preseed.cpio.gz
}}
"""
            files = _tree(boot, "esp") + [("esp", "okula/linux", linux.stat().st_size, linux),
                                          ("esp", "okula/initrd.gz", initrd.stat().st_size, initrd),
                                          ("esp", "okula/preseed.cpio.gz", len(preseed), pre)]
            extra = _grub_copies(cfg)
            lines = [f"Debian {codename(meta)}: Netzwerk-Installer mit Preseed, Partitionen im freien Platz – "
                     "das Gerät braucht Internet", "Desktop: GNOME" if opts.desktop else "ohne Desktop",
                     f"Benutzer {username(opts.username)}, Computername {hostname(opts.hostname)}"]
        if opts.swiss_region:
            lines.append("Region Schweiz: de_CH.UTF-8, Tastatur Schweiz, Zeitzone Zürich")
        return BootPlan(install_id, tbl, parts, files, extra, lines, work)
    except BaseException:
        work.cleanup()
        raise
