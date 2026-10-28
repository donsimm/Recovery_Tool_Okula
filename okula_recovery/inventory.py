"""Agent: Inventar des Geräts sammeln – Hardware, Disks, Netzwerk und installiertes Betriebssystem.

Alles nur lesend. Für das Betriebssystem werden Partitionen kurz schreibgeschützt eingehängt;
bei Journal-Dateisystemen ohne Journal-Wiedergabe (ext4 noload, xfs norecovery, btrfs
nologreplay), damit wirklich kein Byte auf die Disk geschrieben wird. Nur stdlib + Werkzeuge
(lsblk, smartctl, hivexget, mount), fehlende Werkzeuge = weniger Angaben, kein Fehler.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from okula_recovery import imaging

DMI_FIELDS = ("sys_vendor", "product_name", "product_version", "product_serial", "product_uuid", "product_sku",
              "product_family", "board_vendor", "board_name", "board_serial", "bios_vendor", "bios_version",
              "bios_date", "chassis_type", "chassis_vendor", "chassis_serial")
# SMBIOS-Gehäusetypen (Auszug)
CHASSIS = {"3": "Desktop", "4": "Desktop (Low Profile)", "6": "Mini-Tower", "7": "Tower", "8": "Tragbar",
           "9": "Laptop", "10": "Notebook", "13": "All-in-One", "14": "Sub-Notebook", "17": "Server",
           "23": "Rack-Server", "30": "Tablet", "31": "Convertible", "32": "Detachable", "35": "Mini-PC"}
# Platzhalter, die Hersteller statt echter Werte eintragen
JUNK = re.compile(r"^(|0+|f+|none|n/a|default string|to be filled.*|system serial number|"
                  r"not specified|not applicable|chassis serial number|123456789|00000000-0000-0000-0000-000000000000|"
                  r"03000200-0400-0500-0006-000700080009|ffffffff-ffff-ffff-ffff-ffffffffffff)$", re.I)
INSPECT_DIR = "/run/okula-inspect"
MIN_OS_PARTITION = 512 * 1024 * 1024  # kleinere Partitionen (EFI, Recovery …) enthalten kein System
# Schreibschutz-Optionen je Dateisystem: kein Journal-Replay, keine Reparatur
RO_OPTIONS = {"ext2": "ro,noload", "ext3": "ro,noload", "ext4": "ro,noload", "xfs": "ro,norecovery",
              "btrfs": "ro,nologreplay", "ntfs": "ro", "vfat": "ro", "exfat": "ro"}


def clean(value: str) -> str:
    value = (value or "").strip()
    return "" if JUNK.match(value) else value


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def dmi(base: Path = Path("/sys/class/dmi/id")) -> dict:
    info = {f: clean(_read(base / f)) for f in DMI_FIELDS}
    info["chassis"] = CHASSIS.get(info.get("chassis_type", ""), "")
    info["product_uuid"] = info["product_uuid"].lower()
    return info


def cpu(cpuinfo: str | None = None) -> dict:
    text = cpuinfo if cpuinfo is not None else _read(Path("/proc/cpuinfo"))
    model = re.search(r"^model name\s*:\s*(.+)$", text, re.M)
    threads = len(re.findall(r"^processor\s*:", text, re.M))
    cores = {(p, c) for p, c in re.findall(r"^physical id\s*:\s*(\d+).*?^core id\s*:\s*(\d+)", text, re.M | re.S)}
    return {"model": re.sub(r"\s+", " ", model.group(1)) if model else "", "threads": threads,
            "cores": len(cores) or threads}


def memory(meminfo: str | None = None) -> int:
    text = meminfo if meminfo is not None else _read(Path("/proc/meminfo"))
    m = re.search(r"^MemTotal:\s*(\d+) kB", text, re.M)
    return int(m.group(1)) * 1024 if m else 0


def batteries(base: Path = Path("/sys/class/power_supply")) -> list[dict]:
    result = []
    for b in sorted(base.glob("BAT*")):
        full = _read(b / "energy_full") or _read(b / "charge_full")
        design = _read(b / "energy_full_design") or _read(b / "charge_full_design")
        health = round(100 * int(full) / int(design)) if full.isdigit() and design.isdigit() and int(design) else None
        result.append({"name": b.name, "manufacturer": _read(b / "manufacturer"), "model": _read(b / "model_name"),
                       "capacity_now": _read(b / "capacity"), "health_percent": health,
                       "cycles": _read(b / "cycle_count")})
    return result


def network(base: Path = Path("/sys/class/net")) -> list[dict]:
    result = []
    for n in sorted(base.iterdir()) if base.is_dir() else []:
        if n.name == "lo" or not (n / "device").exists():
            continue
        result.append({"name": n.name, "mac": _read(n / "address"), "wireless": (n / "wireless").exists(),
                       "driver": Path(os.path.realpath(n / "device" / "driver")).name
                       if (n / "device" / "driver").exists() else ""})
    return result


def smart(path: str) -> dict:
    """SMART-Kurzbefund per smartctl (JSON); leer, wenn nicht verfügbar."""
    if not shutil.which("smartctl"):
        return {}
    try:
        r = subprocess.run(["smartctl", "-H", "-A", "-i", "-j", path], capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    passed = (data.get("smart_status") or {}).get("passed")
    return {"passed": passed, "power_on_hours": (data.get("power_on_time") or {}).get("hours"),
            "temperature": (data.get("temperature") or {}).get("current"),
            "firmware": data.get("firmware_version", "")}


# ---------- Betriebssystem ----------

def windows_version(hive_dir: Path) -> dict:
    """Edition/Version aus dem Registry-Hive SOFTWARE, Computername aus SYSTEM (hivexget)."""
    def get(hive: str, key: str, value: str) -> str:
        if not shutil.which("hivexget"):
            return ""
        try:
            r = subprocess.run(["hivexget", str(hive_dir / hive), key, value], capture_output=True, text=True,
                               timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return r.stdout.strip() if r.returncode == 0 else ""

    cv = r"Microsoft\Windows NT\CurrentVersion"
    product = get("SOFTWARE", cv, "ProductName")
    build = get("SOFTWARE", cv, "CurrentBuild") or get("SOFTWARE", cv, "CurrentBuildNumber")
    display = get("SOFTWARE", cv, "DisplayVersion") or get("SOFTWARE", cv, "ReleaseId")
    edition = get("SOFTWARE", cv, "EditionID")
    if product and build.isdigit() and int(build) >= 22000:
        product = product.replace("Windows 10", "Windows 11")  # Registry nennt auch Windows 11 „Windows 10“
    name = get("SYSTEM", r"ControlSet001\Control\ComputerName\ComputerName", "ComputerName")
    pretty = " ".join(p for p in (product or "Windows", display) if p)
    return {"family": "Windows", "name": pretty, "build": build, "edition": edition, "hostname": name}


def linux_version(root: Path) -> dict:
    text = _read(root / "etc" / "os-release") or _read(root / "usr" / "lib" / "os-release")
    pretty = re.search(r'^PRETTY_NAME="?([^"\n]+)"?', text, re.M)
    return {"family": "Linux", "name": pretty.group(1) if pretty else "Linux", "build": "",
            "edition": "", "hostname": _read(root / "etc" / "hostname")}


def inspect_root(root: Path) -> dict | None:
    """Was für ein Betriebssystem liegt in diesem (eingehängten) Dateisystem?"""
    config = root / "Windows" / "System32" / "config"
    if (config / "SOFTWARE").is_file():
        return windows_version(config)
    if (root / "etc" / "os-release").is_file() or (root / "usr" / "lib" / "os-release").is_file():
        if (root / "bin").exists() or (root / "usr" / "bin").exists():
            return linux_version(root)
    return None


def _mount_ro(dev: str, fstype: str, target: Path) -> bool:
    opts = RO_OPTIONS.get(fstype)
    if not opts:
        return False
    candidates = [["mount", "-t", fstype, "-o", opts, dev, str(target)]]
    if fstype == "ntfs":  # Kernel-Treiber ntfs3, sonst ntfs-3g (beide nur lesend)
        candidates = [["mount", "-t", "ntfs3", "-o", "ro", dev, str(target)],
                      ["mount", "-t", "ntfs-3g", "-o", "ro", dev, str(target)]]
    for cmd in candidates:
        try:
            if subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def probe_fstype(path: str) -> str:
    """Dateisystem direkt per blkid (lsblk kennt es ohne udev-Datenbank nicht)."""
    try:
        r = subprocess.run(["blkid", "-o", "value", "-s", "TYPE", path], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip()


def operating_systems(disks: list[dict], skip: set[str] = frozenset()) -> list[dict]:
    """Installierte Systeme auf allen Partitionen; BitLocker wird erkannt, aber nicht geöffnet.

    skip: Disks (Pfade), auf denen gerade ein Auftrag läuft – dort wird nichts eingehängt.
    """
    found = []
    base = Path(INSPECT_DIR)
    for disk in disks:
        if disk["path"] in skip:
            continue
        for part in disk["partitions"]:
            fs = part.get("fstype") or probe_fstype(part["path"])
            if fs.lower() == "bitlocker":
                found.append({"family": "Windows", "name": "verschlüsselt (BitLocker)", "partition": part["name"],
                              "disk": disk["name"], "build": "", "edition": "", "hostname": ""})
                continue
            if fs not in RO_OPTIONS or part.get("mounted") or part.get("size", 0) < MIN_OS_PARTITION:
                continue  # zu klein für ein Betriebssystem (EFI, Recovery …)
            base.mkdir(parents=True, exist_ok=True)
            target = Path(tempfile.mkdtemp(prefix=f"{part['name']}-", dir=base))
            try:
                if not _mount_ro(part["path"], fs, target):
                    continue
                try:
                    info = inspect_root(target)
                finally:
                    subprocess.run(["umount", str(target)], capture_output=True, timeout=60)
                if info:
                    found.append({**info, "partition": part["name"], "disk": disk["name"]})
            finally:
                try:
                    target.rmdir()
                except OSError:
                    pass
    # Windows vor Linux, BitLocker zuletzt
    found.sort(key=lambda o: (o["family"] != "Windows", "BitLocker" in o["name"]))
    return found


def collect(with_os: bool = True, skip: set[str] = frozenset()) -> dict:
    disks = imaging.list_disks()
    for d in disks:
        d["smart"] = smart(d["path"])
    systems = operating_systems(disks, skip) if with_os else []
    return {"collected": time.strftime("%Y-%m-%dT%H:%M:%S"), "dmi": dmi(), "cpu": cpu(), "memory": memory(),
            "batteries": batteries(), "network": network(), "disks": disks, "systems": systems}
