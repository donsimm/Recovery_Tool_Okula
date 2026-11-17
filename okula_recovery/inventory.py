"""Agent: Inventar des Geräts sammeln – Hardware, Disks, Netzwerk und installiertes Betriebssystem.

Alles nur lesend. Für das Betriebssystem werden Partitionen kurz schreibgeschützt eingehängt;
bei Journal-Dateisystemen ohne Journal-Wiedergabe (ext4 noload, xfs norecovery, btrfs
nologreplay), damit wirklich kein Byte auf die Disk geschrieben wird. Nur stdlib + Werkzeuge
(lsblk, smartctl, hivexget, mount, lspci), fehlende Werkzeuge = weniger Angaben, kein Fehler.
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


# ---------- Grafikkarten (I-037) ----------

SYS_PCI = Path("/sys/bus/pci/devices")
PCI_IDS = (Path("/usr/share/misc/pci.ids"), Path("/usr/share/hwdata/pci.ids"))
# Kurzname je Hersteller-ID statt langer Firmennamen („NVIDIA Corporation“ → „NVIDIA“)
GPU_VENDORS = {"10de": "NVIDIA", "1002": "AMD", "1022": "AMD", "8086": "Intel", "102b": "Matrox",
               "1a03": "ASPEED", "15ad": "VMware", "1234": "QEMU", "1b36": "Red Hat", "1af4": "Red Hat",
               "80ee": "VirtualBox", "1414": "Microsoft"}
_NAME_ID = re.compile(r"^(.*?)\s*\[([0-9a-fA-F]{4})\]$")


def _name_id(value: str) -> tuple[str, str]:
    """„NVIDIA Corporation [10de]“ → („NVIDIA Corporation“, „10de“); ohne Datenbank heisst es nur „Device [0fc8]“."""
    m = _NAME_ID.match(value.strip())
    if not m:
        return value.strip(), ""
    name = m.group(1).strip()
    return ("" if name in ("Device", "Vendor") else name), m.group(2).lower()


def _gpu(slot: str, cls: str, vendor: str, device: str, sub_vendor: str = "", sub_device: str = "",
         vendor_name: str = "", device_name: str = "", sub_vendor_name: str = "", sub_name: str = "",
         driver: str = "") -> dict:
    return {"slot": slot, "class": cls, "vendor": vendor, "device": device, "vendor_name": vendor_name,
            "device_name": device_name, "subsystem_vendor": sub_vendor, "subsystem_device": sub_device,
            "subsystem_vendor_name": sub_vendor_name, "subsystem_name": sub_name, "driver": driver}


def parse_lspci(text: str) -> list[dict]:
    """Grafikgeräte (PCI-Klasse 03xx: VGA, 3D, Display) aus `lspci -vmm -nn -D -k`; HDMI-Audio (04xx) nicht."""
    found = []
    for block in re.split(r"\n\s*\n", text or ""):
        fields = {}
        for line in block.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() not in fields:
                fields[key.strip()] = value.strip()
        _cls_name, cls = _name_id(fields.get("Class", ""))
        if not cls.startswith("03") or not fields.get("Slot"):
            continue
        vendor_name, vendor = _name_id(fields.get("Vendor", ""))
        device_name, device = _name_id(fields.get("Device", ""))
        sub_vendor_name, sub_vendor = _name_id(fields.get("SVendor", ""))
        sub_name, sub_device = _name_id(fields.get("SDevice", ""))
        found.append(_gpu(fields["Slot"], cls, vendor, device, sub_vendor, sub_device, vendor_name, device_name,
                          sub_vendor_name, sub_name, fields.get("Driver", "")))
    return found


def pci_names(ids_file: Path, wanted: set[tuple[str, str]]) -> tuple[dict, dict, dict]:
    """Namen aus der pci.ids-Datenbank: Hersteller {id: Name}, Geräte {(v, d): Name},
    Subsysteme {(v, d, sv, sd): Name} – nur für die gesuchten (Hersteller, Gerät)."""
    vendors, devices, subs = {}, {}, {}
    want_vendors = {v for v, _d in wanted}
    try:
        lines = ids_file.read_text(errors="replace").splitlines()
    except OSError:
        return vendors, devices, subs
    vendor = device = ""
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if line.startswith("C "):             # Klassenliste am Ende der Datei
            break
        if not line.startswith("\t"):
            vendor, _sp, name = line.partition("  ")
            vendor, device = vendor.lower(), ""
            vendors[vendor] = name.strip()
        elif line.startswith("\t\t"):
            if (vendor, device) in wanted:
                ids, _sp, name = line.strip().partition("  ")
                sv, _s, sd = ids.partition(" ")
                subs[(vendor, device, sv.lower(), sd.lower())] = name.strip()
        elif vendor in want_vendors:
            device, _sp, name = line.strip().partition("  ")
            device = device.lower()
            if (vendor, device) in wanted:
                devices[(vendor, device)] = name.strip()
    return vendors, devices, subs


def _hex(path: Path) -> str:
    value = _read(path).lower()
    return value[2:] if value.startswith("0x") else value


def _driver(dev: Path) -> str:
    link = dev / "driver"
    return Path(os.path.realpath(link)).name if link.exists() else ""


def gpus_sysfs(base: Path = SYS_PCI, ids_files=PCI_IDS) -> list[dict]:
    """Ohne lspci: IDs aus /sys/bus/pci/devices, Namen aus pci.ids (falls vorhanden), sonst nur die IDs."""
    found = []
    for dev in sorted(base.iterdir()) if base.is_dir() else []:
        cls = _hex(dev / "class")
        if not cls.startswith("03"):
            continue
        found.append(_gpu(dev.name, cls[:4], _hex(dev / "vendor"), _hex(dev / "device"),
                          _hex(dev / "subsystem_vendor"), _hex(dev / "subsystem_device"), driver=_driver(dev)))
    ids_file = next((Path(p) for p in ids_files if Path(p).is_file()), None)
    if found and ids_file:
        vendors, devices, subs = pci_names(ids_file, {(g["vendor"], g["device"]) for g in found})
        for g in found:
            g["vendor_name"] = vendors.get(g["vendor"], "")
            g["device_name"] = devices.get((g["vendor"], g["device"]), "")
            g["subsystem_vendor_name"] = vendors.get(g["subsystem_vendor"], "")
            g["subsystem_name"] = subs.get((g["vendor"], g["device"], g["subsystem_vendor"],
                                            g["subsystem_device"]), "")
    return found


def _lspci() -> str:
    if not shutil.which("lspci"):
        return ""
    try:
        r = subprocess.run(["lspci", "-vmm", "-nn", "-D", "-k"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def gpus(lspci_out: str | None = None, base: Path = SYS_PCI, ids_files=PCI_IDS) -> list[dict]:
    """Grafikkarten nach PCI-Adresse: Namen über lspci, ohne lspci aus /sys (+ pci.ids); fehlt alles → []."""
    text = _lspci() if lspci_out is None else lspci_out
    found = parse_lspci(text) if text.strip() else gpus_sysfs(base, ids_files)
    for g in found:
        if not g["driver"]:
            g["driver"] = _driver(base / g["slot"])
    return sorted(found, key=lambda g: g["slot"])


def gpu_model(name: str) -> str:
    """pci.ids schreibt „Chip [Verkaufsname]“: „GK107 [GeForce GT 740]“ → „GeForce GT 740 (GK107)“."""
    m = re.match(r"^(.*?)\s*\[([^\]]+)\]$", (name or "").strip())
    if not m:
        return (name or "").strip()
    return f"{m.group(2)} ({m.group(1)})" if m.group(1) else m.group(2)


def _company(name: str) -> str:
    return re.sub(r"[ ,]+(Corporation|Corp\.?|Inc\.?|Co\.?,? Ltd\.?|Ltd\.?|GmbH|AG|Limited)$", "", name or "").strip()


def gpu_text(g: dict) -> str:
    """Anzeige „NVIDIA GeForce GT 740 (GK107)“; ohne Namen „PCI 10de:0fc8“."""
    vendor = GPU_VENDORS.get(g.get("vendor", "")) or _company(g.get("vendor_name", ""))
    model = gpu_model(g.get("device_name", ""))
    if not model:
        ids = f"PCI {g.get('vendor', '?')}:{g.get('device', '?')}"
        return f"{vendor} ({ids})" if vendor else ids
    return model if not vendor or model.lower().startswith(vendor.lower()) else f"{vendor} {model}"


def gpu_rows(inv: dict) -> list[tuple[str, str, str]]:
    """Zeilen für die Übersicht: („Grafikkarte“ bzw. „Grafikkarte 1“ …, Text, Tooltip). Altes Inventar → keine."""
    if "gpus" not in (inv or {}):
        return []
    cards = sorted(inv.get("gpus") or [], key=lambda g: g.get("slot", ""))
    if not cards:
        return [("Grafikkarte", "", "")]
    rows = []
    for i, g in enumerate(cards, 1):
        label = "Grafikkarte" if len(cards) == 1 else f"Grafikkarte {i}"
        card = _company(g.get("subsystem_vendor_name", ""))
        tip = " · ".join(p for p in (f"PCI-Adresse {g.get('slot', '')}",
                                     f"IDs {g.get('vendor', '')}:{g.get('device', '')}",
                                     f"Karte von {card}" if card else "",
                                     f"Treiber {g['driver']}" if g.get("driver") else "Kein Treiber geladen") if p)
        rows.append((label, f"{gpu_text(g)}  ({g.get('slot', '')})", tip))
    return rows


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


KEY_RE = re.compile(r"^[0-9A-Z]{5}(-[0-9A-Z]{5}){4}$")


def oem_key(path: Path = Path("/sys/firmware/acpi/tables/MSDM")) -> str:
    """Windows-Produktschlüssel aus dem BIOS (ACPI-Tabelle MSDM, ab Windows 8 bei OEM-Geräten)."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    key = data[56:85].decode("ascii", errors="replace") if len(data) >= 85 else ""
    return key if KEY_RE.match(key) else ""


SECURE_BOOT_VAR = "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"


def platform(sys_root: Path = Path("/sys")) -> dict:
    """Für die Windows-11-Prüfung: TPM-Version, UEFI- oder BIOS-Start, Secure Boot an/aus (None = unbekannt)."""
    tpm = ""
    tpm_dir = sys_root / "class" / "tpm" / "tpm0"
    if tpm_dir.exists():
        major = _read(tpm_dir / "tpm_version_major")
        tpm = {"2": "2.0", "1": "1.2"}.get(major, "?")
    efi = sys_root / "firmware" / "efi"
    uefi = efi.is_dir()
    secure_boot = None
    if uefi:
        try:
            data = (efi / "efivars" / SECURE_BOOT_VAR).read_bytes()
            secure_boot = len(data) >= 5 and data[4] == 1   # 4 Byte Attribute, dann der Wert
        except OSError:
            secure_boot = None
    return {"tpm": tpm, "uefi": uefi, "secure_boot": secure_boot}


def collect(with_os: bool = True, skip: set[str] = frozenset()) -> dict:
    disks = imaging.list_disks()
    for d in disks:
        d["smart"] = smart(d["path"])
    systems = operating_systems(disks, skip) if with_os else []
    return {"collected": time.strftime("%Y-%m-%dT%H:%M:%S"), "dmi": dmi(), "cpu": cpu(), "memory": memory(),
            "batteries": batteries(), "network": network(), "gpus": gpus(), "disks": disks, "systems": systems,
            "platform": platform(),
            "oem_key": oem_key()}
