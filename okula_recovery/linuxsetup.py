"""Linux direkt auf ein Gerät installieren (Tool-Seite): Ubuntu (ab 24.04), Debian, Fedora/Anaconda.

Gemeinsam: Der Agent legt eine EFI-Partition an (Bootdateien der ISO: signiertes shim + grub, Secure Boot geht),
setzt BootNext darauf und startet neu. Der Platz dahinter bleibt frei – dorthin installiert der offizielle
Installer automatisch.

Ubuntu: Die ISO liegt als Datei auf einer Setup-Partition am Disk-Ende (ext4), GRUB startet sie per Loopback,
        die Autoinstall-Antworten liegen auf einer kleinen Partition „CIDATA“ (cloud-init). Installiert wird
        in die Lücke (layout direct, mode use_gap). Beim ersten Start entfernt okula-cleanup die Setup-
        Partitionen und vergrössert die Systempartition.
Debian: Netzwerk-Installer (Kernel + initrd von deb.debian.org, gegen SHA256SUMS geprüft) mit Preseed,
        Partitionierung im grössten freien Bereich; Pakete aus dem Internet.
Fedora (und Anaconda-Abkömmlinge wie Rocky/Alma): Kernel/initrd der ISO auf der EFI-Partition, die ISO als
        Datei auf der Setup-Partition (inst.repo/inst.stage2=hd:…), Kickstart (autopart in den freien Platz).
        Live-Medien (Fedora Workstation Live, Nobara mit Calamares) haben keinen automatisierbaren Installer.
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
    desktop: bool = True             # Fedora: Workstation; Debian: siehe desktop_env (Ubuntu Desktop hat ihn immer)
    desktop_env: str = "gnome"       # Debian: gnome, kde, xfce, cinnamon, mate, lxde, lxqt ("" = ohne Desktop)
    standard: bool = True            # Debian: Standard-Systemwerkzeuge
    ssh: bool = False                # SSH-Server (alle)
    web: bool = False                # Debian: Webserver (Apache)
    root_password: str = ""          # Debian: Root-Konto mit Passwort (leer = gesperrt, Benutzer mit sudo)
    packages: list[str] = field(default_factory=list)   # zusätzliche Pakete (alle)

    @property
    def debian_desktop(self) -> str:
        return self.desktop_env if self.desktop and self.desktop_env in DESKTOPS else ""


# Debian-Desktops (tasksel-Aufgabe „<name>-desktop“) – wie die Softwareauswahl im Debian-Installer
DESKTOPS = {"gnome": "GNOME", "kde": "KDE Plasma", "xfce": "Xfce", "cinnamon": "Cinnamon", "mate": "MATE",
            "lxde": "LXDE", "lxqt": "LXQt"}
PACKAGE_RE = re.compile(r"^@?\^?[A-Za-z0-9][A-Za-z0-9+._:-]*$")


def parse_packages(text: str) -> list[str]:
    """„htop, curl vim“ → [htop, curl, vim]; nur gültige Paketnamen (kommen in Preseed/Kickstart/YAML)."""
    names = [n for n in re.split(r"[\s,;]+", text.strip()) if n]
    bad = [n for n in names if not PACKAGE_RE.match(n) or len(n) > 100]
    if bad:
        raise LinuxSetupError(f"Ungültiger Paketname: {', '.join(bad)}")
    return list(dict.fromkeys(names))


def software_lines(opts: LinuxOptions, which: str) -> list[str]:
    """Kurzbeschreibung der Softwareauswahl fürs Log."""
    parts = []
    if which == "debian":
        parts.append(f"Desktop: {DESKTOPS[opts.debian_desktop]}" if opts.debian_desktop else "ohne Desktop")
        if opts.standard:
            parts.append("Standard-Systemwerkzeuge")
        if opts.web:
            parts.append("Webserver")
    if opts.ssh:
        parts.append("SSH-Server")
    if opts.packages:
        parts.append("zusätzlich: " + " ".join(opts.packages))
    out = ["Software: " + ", ".join(parts)] if parts else []
    if which == "debian" and opts.root_password:
        out.append("Root-Konto mit eigenem Passwort (Benutzer bleibt in sudo)")
    return out


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
    """„ubuntu“, „debian“, „fedora“ (Anaconda) oder „“ (nicht direkt installierbar) – Grund siehe reason()."""
    if reason(meta):
        return ""
    return {"casper": "ubuntu", "debian-installer": "debian", "anaconda": "fedora"}[(meta.get("linux") or {})["kind"]]


def _version(lx: dict) -> tuple[int, int]:
    try:
        major, minor = (int(x) for x in (lx.get("version") or "0.0").split(".")[:2])
    except ValueError:
        return (0, 0)
    return major, minor


def reason(meta: dict) -> str:
    """Warum ein Linux-Medium nicht direkt installierbar ist („“ = geht)."""
    lx = meta.get("linux") or {}
    name = meta.get("title") or "Dieses Medium"
    info = (lx.get("info") or "").strip()
    if lx.get("kind") == "casper":
        # nur das echte Ubuntu (Desktop/Server) hat den Installer mit Autoinstall; Abkömmlinge (Zorin, Mint,
        # Kubuntu …) nutzen Ubiquity oder Calamares
        if not info.startswith("Ubuntu "):
            return f"{name}: Installer ohne automatische Installation (Ubiquity/Calamares)"
        if _version(lx) < (24, 4):
            return "Ubuntu älter als 24.04 – Installer ohne Autoinstall"
        return ""
    if lx.get("kind") == "debian-installer" and lx.get("distro") == "debian":
        return "" if codename(meta) else "Debian-Version (Codename) nicht erkannt"
    if lx.get("kind") == "anaconda":
        if not (lx.get("kernel") and lx.get("initrd")):
            return f"{name}: Kernel/initrd (images/pxeboot) nicht gefunden"
        if not lx.get("repo") and lx.get("distro") != "fedora":
            return f"{name}: Netzwerk-Installer – bitte die DVD-ISO verwenden (Pakete auf der ISO)"
        return ""
    if lx.get("kind") == "fedora-live":
        if lx.get("calamares") or lx.get("distro") == "nobara":
            return f"{name}: Live-Medium mit Calamares-Installer – keine automatische Installation"
        return (f"{name}: Live-Medium (Installer läuft im Live-System) – für die Direktinstallation die "
                "Fedora-Everything- oder Server-ISO verwenden")
    return f"{name}: kein unterstützter Installer erkannt"


def codename(meta: dict) -> str:
    m = re.search(r'"([A-Za-z]+)"', (meta.get("linux") or {}).get("info", ""))
    return m.group(1).lower() if m else ""


# ---------- Partitionstabelle ----------

def _align_down(n: int) -> int:
    return n // ALIGN * ALIGN


def table(disk_size: int, setup_size: int = 0, cidata: bool = True) -> tuple[str, list[dict]]:
    """EFI vorne, (Ubuntu/Fedora:) Setup (+ CIDATA) am Ende, dazwischen frei für das System."""
    sectors = disk_size // SECTOR
    last = sectors - 34                                   # GPT-Kopie am Ende
    esp_end = ALIGN + ESP_MIB * MIB // SECTOR
    lines = ["label: gpt",
             f'start={ALIGN}, size={ESP_MIB * MIB // SECTOR}, type={GPT_ESP}, name="EFI system partition"']
    parts = [{"number": 1, "fs": "fat32", "label": ESP_LABEL, "key": "esp"}]
    gap_end = last
    if setup_size:
        cidata_size = CIDATA_MIB * MIB // SECTOR if cidata else 0
        setup_sectors = -(-setup_size // (MIB)) * MIB // SECTOR
        cidata_start = _align_down(last + 1 - cidata_size)
        setup_start = _align_down(cidata_start - setup_sectors)
        lines.append(f'start={setup_start}, size={cidata_start - setup_start}, type={GPT_LINUX}, name="Okula Setup"')
        parts.append({"number": 2, "fs": "ext4", "label": SETUP_LABEL, "key": "setup"})
        if cidata:
            lines.append(f'start={cidata_start}, size={cidata_size}, type={GPT_DATA}, name="CIDATA"')
            parts.append({"number": 3, "fs": "fat32", "label": CIDATA_LABEL, "key": "cidata"})
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
    # auto_chmod_on: Debian-ISOs haben schreibgeschützte Ordner (r-x); ohne das scheitert der zweite Pfad unter dest
    r = subprocess.run(["xorriso", "-osirrox", "on:auto_chmod_on", "-indev", str(iso), *args], capture_output=True,
                       text=True, timeout=600)
    if r.returncode != 0:
        lines = [ln.strip() for ln in r.stderr.splitlines() if ln.strip()]
        failed = [ln for ln in lines if ": FAILURE :" in ln or ": SORRY :" in ln] or lines
        reason = failed[-1].split(" : ", 2)[-1] if failed else f"Fehlercode {r.returncode}"
        raise LinuxSetupError(f"xorriso: {reason}")
    for f in [dest, *dest.rglob("*")]:
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
root=$(findmnt -no SOURCE / | sed 's/\\[.*\\]$//')   # btrfs: „/dev/sda4[/root]“
fstype=$(findmnt -no FSTYPE /)
disk=/dev/$(lsblk -no PKNAME "$root" | head -n1)
for label in OKULASETUP CIDATA; do
    dev=$(blkid -L "$label" 2>/dev/null) || continue
    num=$(cat "/sys/class/block/$(basename "$dev")/partition")
    umount "$dev" 2>/dev/null
    sfdisk --no-reread --delete "$disk" "$num"
done
partx -u "$disk" 2>/dev/null
num=$(cat "/sys/class/block/$(basename "$root")/partition")
# Systempartition bis zum Disk-Ende vergrössern (Tabelle, dann dem Kernel melden), danach das Dateisystem
echo ", +" | sfdisk --no-reread -N "$num" "$disk"
resizepart "$disk" "$num" "$(partx -g -o SECTORS -n "$num" "$disk" | tr -d ' ')"
case "$fstype" in
    ext4) resize2fs "$root" ;;
    btrfs) btrfs filesystem resize max / ;;
    xfs) xfs_growfs / ;;
esac
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
              "  storage:", "    layout:", "      name: direct", "      mode: use_gap"]
    if opts.ssh:
        lines += ["  ssh:", "    install-server: true", "    allow-pw: true"]
    if opts.packages:  # einzeln, unbekannte überspringen – sonst bricht die Installation ab
        late.append("curtin in-target -- sh -c 'for p in " + " ".join(opts.packages)
                    + "; do apt-get install -y $p || true; done'")
    lines += ["  late-commands:"] + [f"    - {q(c)}" for c in late] + ["  shutdown: reboot"]
    return "\n".join(lines) + "\n"


def debian_tasks(opts: LinuxOptions) -> str:
    """tasksel-Aufgaben wie in der Softwareauswahl des Debian-Installers."""
    tasks = ["standard"] if opts.standard else []
    if opts.debian_desktop:
        tasks += ["desktop", f"{opts.debian_desktop}-desktop"]
    if opts.web:
        tasks.append("web-server")
    if opts.ssh:
        tasks.append("ssh-server")
    return ", ".join(tasks)


def debian_preseed(opts: LinuxOptions, password_hash: str, disk: str, root_hash: str = "") -> str:
    user = username(opts.username)
    host = hostname(opts.hostname)
    locale = "de_CH.UTF-8" if opts.swiss_region else "en_US.UTF-8"
    tasks = debian_tasks(opts)
    late = ("in-target sh -c 'for b in $(efibootmgr | sed -n \"s/^Boot\\([0-9A-Fa-f]\\{4\\}\\)\\*\\{0,1\\} Okula.*/\\1/p\"); "
            "do efibootmgr -q -B -b $b; done'; rm -rf /target/boot/efi/okula /target/boot/efi/boot "
            "/target/boot/efi/.disk")
    if root_hash:  # mit Root-Konto legt der Installer den Benutzer nicht in sudo – hier nachholen
        late += f"; in-target apt-get install -y sudo; in-target usermod -aG sudo {user}"
        root = f"d-i passwd/root-login boolean true\nd-i passwd/root-password-crypted password {root_hash}"
    else:
        root = "d-i passwd/root-login boolean false"
    if opts.packages:  # einzeln am Schluss: ein Tippfehler darf die automatische Installation nicht anhalten
        late += f"; in-target sh -c 'for p in {' '.join(opts.packages)}; do apt-get install -y $p || true; done'"
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
{root}
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


FEDORA_MIRROR = "https://mirrors.fedoraproject.org/mirrorlist?repo={repo}$releasever&arch=$basearch"


def kickstart(opts: LinuxOptions, password_hash: str, disk: str, meta: dict) -> str:
    """Kickstart für Anaconda (Fedora, Rocky, Alma …): Installation in den freien Platz der Zieldisk."""
    lx = meta.get("linux") or {}
    fedora = lx.get("distro") == "fedora"
    online = fedora and (opts.desktop or not lx.get("repo"))   # Netzwerk-Installer oder Desktop: aus dem Internet
    if opts.desktop:
        env = "workstation-product-environment"
    else:
        env = "server-product-environment" if fedora else "minimal-environment"
    if online:
        source = (f'url --mirrorlist="{FEDORA_MIRROR.format(repo="fedora-")}"\n'
                  f'repo --name=updates --mirrorlist="{FEDORA_MIRROR.format(repo="updates-released-f")}"')
    else:
        source = "# Pakete von der ISO (inst.repo)"
    post = "\n".join([
        f"echo {_b64(CLEANUP_SCRIPT)} | base64 -d > /usr/local/sbin/okula-cleanup",
        "chmod 755 /usr/local/sbin/okula-cleanup",
        f"echo {_b64(CLEANUP_SERVICE)} | base64 -d > /etc/systemd/system/okula-cleanup.service",
        "systemctl enable okula-cleanup.service"])
    name = username(opts.username)
    extra = (["openssh-server"] if opts.ssh else []) + list(opts.packages)
    packages = "".join(f"{n}\n" for n in dict.fromkeys(extra))
    services = "services --enabled=sshd\nfirewall --enabled --service=ssh\n" if opts.ssh else ""
    return f"""# Okula Recovery Tool – Anaconda-Direktinstallation
text
lang {"de_CH.UTF-8" if opts.swiss_region else "en_US.UTF-8"}
keyboard --xlayouts='{"ch" if opts.swiss_region else "us"}'
timezone {"Europe/Zurich" if opts.swiss_region else "UTC"} --utc
network --bootproto=dhcp --activate --hostname={hostname(opts.hostname)}
{source}
rootpw --lock
user --name={name} --gecos="{opts.username}" --groups=wheel --iscrypted --password={password_hash}
ignoredisk --only-use={disk.removeprefix("/dev/")}
clearpart --none
autopart
bootloader --boot-drive={disk.removeprefix("/dev/")}
firstboot --disable
{services}%packages --ignoremissing
@^{env}
{packages}%end
%post
{post}
%end
reboot
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
                     "Platz (use_gap)", *software_lines(opts, "ubuntu"),
                     f"Benutzer {username(opts.username)}, Computername {hostname(opts.hostname)}"]
        elif which == "fedora":
            lx = meta["linux"]
            _extract(iso, boot, ["/EFI"])
            pxe = root / "pxe"
            _extract(iso, pxe, [lx["kernel"], lx["initrd"]])
            kernel = next(pxe.rglob("vmlinuz"))
            initrd = next(pxe.rglob("initrd.img"))
            size = iso.stat().st_size
            tbl, parts = table(disk_size, size + SETUP_RESERVE, cidata=False)
            ks = kickstart(opts, pw, disk, meta)
            source = f"hd:LABEL={SETUP_LABEL}:/fedora.iso"
            repo = f"inst.repo={source}" if lx.get("repo") and "url --mirrorlist" not in ks else f"inst.stage2={source}"
            cfg = f"""# Okula Recovery Tool – Anaconda-Direktinstallation ({install_id})
set timeout=3
set default=0
search --no-floppy --label --set=root {ESP_LABEL}
menuentry "Okula: {meta.get('title') or 'Fedora'} automatisch installieren" {{
    linux /okula/vmlinuz {repo} inst.ks=hd:LABEL={ESP_LABEL}:/okula/ks.cfg inst.text quiet
    initrd /okula/initrd.img
}}
"""
            files = _tree(boot, "esp") + [("esp", "okula/vmlinuz", kernel.stat().st_size, kernel),
                                          ("esp", "okula/initrd.img", initrd.stat().st_size, initrd),
                                          ("setup", "fedora.iso", size, iso)]
            extra = _grub_copies(cfg) + [{"part": "esp", "path": "okula/ks.cfg", "text": ks}]
            online = "url --mirrorlist" in ks
            lines = [f"{meta.get('title') or 'Fedora'}: Anaconda mit Kickstart, Partitionen im freien Platz"
                     + (" – Pakete aus dem Internet (Gerät braucht Internet)" if online else " – Pakete von der ISO"),
                     "Desktop: Workstation (GNOME)" if opts.desktop else "ohne Desktop",
                     *software_lines(opts, "fedora"),
                     f"Benutzer {username(opts.username)} (Administrator), Computername {hostname(opts.hostname)}"]
        else:
            _extract(iso, boot, ["/EFI", "/boot/grub", "/.disk"])
            linux, initrd = netboot(codename(meta))
            root_pw = hash_password(opts.root_password) if opts.root_password else ""
            preseed = gzip.compress(cpio_newc({"preseed.cfg": debian_preseed(opts, pw, disk, root_pw).encode()}))
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
                     "das Gerät braucht Internet", *software_lines(opts, "debian"),
                     f"Benutzer {username(opts.username)}, Computername {hostname(opts.hostname)}"]
        if opts.swiss_region:
            lines.append("Region Schweiz: de_CH.UTF-8, Tastatur Schweiz, Zeitzone Zürich")
        return BootPlan(install_id, tbl, parts, files, extra, lines, work)
    except BaseException:
        work.cleanup()
        raise
