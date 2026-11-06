"""Virtuelle Maschinen (I-001): Hardware-Profil → libvirt-VM, Aktionen über virsh (ohne GTK).

Konzept und Profile: docs/VM.md. Grundsätze:
- Nur Standard-Hardware (SATA/NVMe, Intel e1000e/e1000, Realtek rtl8139), keine virtio-Geräte – ein Image aus der VM
  soll auf echten Geräten laufen.
- Netzwerk über die Brücke br0 (okula-bridge), VMs sind im LAN sichtbar; Agent über den Netzwerkstart.
- virsh -c qemu:///system als Benutzer (Gruppe libvirt), Disks als qcow2 im Speicherpool „okula“.
  In der VM steht die Disk als Datei (type="file"), nicht als Pool-Volume: Nur für Dateien legt virt-aa-helper
  die AppArmor-Freigabe an, sonst bricht der Start mit „Permission denied“ ab. Angelegt, vergrössert und
  gelöscht wird sie weiterhin über den Pool (vol-create-as/vol-resize/vol-delete).
- Das Profil liegt als JSON in den Metadaten der VM; damit lässt es sich später wieder lesen und ändern.

libvirt in Debian 13 ist 11.3: Der Disk-Bus „nvme“ kommt erst mit 11.5. Eine NVMe-Disk wird darum als SATA-Disk
definiert (libvirt verwaltet Rechte und AppArmor) und per <qemu:override> zum QEMU-Gerät „nvme“ umgebaut.
QEMU 10.0 kennt für NVMe keinen Modellnamen – dort bleibt „QEMU NVMe Ctrl“. Der CPU-Name wird per -global gesetzt.
Gehäusetyp (SMBIOS Typ 3) lässt sich weder in libvirt noch in QEMU setzen; er steht nur im Profil.
"""

from __future__ import annotations

import copy
import json
import os
import random
import re
import subprocess
import tempfile
import uuid as uuidlib
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field, fields
from typing import Callable

URI = "qemu:///system"
POOL = "okula"
POOL_DIR = "/var/lib/libvirt/images/okula"
BRIDGE = "br0"
QEMU_NS = "http://libvirt.org/schemas/domain/qemu/1.0"
OKULA_NS = "https://okula.ch/recovery/vm/1"
NVME_ADDR = "0x1b"          # PCI-Steckplatz der NVMe-Disk (libvirt belegt Steckplätze ab 0x2 aufsteigend)
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
MAC_RE = re.compile(r"^52:54:00(:[0-9a-f]{2}){3}$")

FIRMWARES = ("uefi-sb", "uefi", "bios")
CHIPSETS = ("q35", "i440fx")
DISK_BUSES = ("nvme", "sata")
# e1000e (Intel 82574L) und e1000 (Intel 82540EM): Treiber in Windows enthalten.
# rtl8139: in Windows 10/11 ohne mitgelieferten Treiber – nur für Linux sinnvoll.
NIC_MODELS = ("e1000e", "e1000", "rtl8139")
START_MODES = ("normal", "pxe", "iso")

ET.register_namespace("qemu", QEMU_NS)
ET.register_namespace("okula", OKULA_NS)


class VmError(Exception):
    """Fehler mit verständlicher deutscher Meldung (für die Oberfläche)."""


# ---------- Profil ----------

@dataclass
class DiskSpec:
    bus: str = "sata"          # nvme | sata
    size_gb: int = 64          # dezimal wie auf dem Etikett (1 GB = 10^9 Byte)
    model: str = ""
    serial: str = ""           # leer = beim Erstellen erzeugen
    rpm: int = 0               # Drehzahl bei HDD, 0 = SSD


@dataclass
class NicSpec:
    model: str = "e1000e"      # e1000e | e1000 | rtl8139
    mac: str = ""              # leer = beim Erstellen erzeugen (52:54:00:…)


@dataclass
class CpuSpec:
    cores: int = 2
    threads: int = 1           # pro Kern
    name: str = ""             # leer = Name der Server-CPU


@dataclass
class Smbios:
    # Typ 0 – BIOS
    bios_vendor: str = "Okula"
    bios_version: str = "1.0"
    bios_date: str = "11/06/2026"    # MM/DD/YYYY
    # Typ 1 – System
    manufacturer: str = "Okula"
    product: str = ""
    version: str = "1.0"
    sku: str = ""
    family: str = "Okula VM"
    serial: str = ""                  # leer = beim Erstellen erzeugen
    uuid: str = ""                    # leer = beim Erstellen erzeugen (= UUID der VM)
    # Typ 2 – Board
    board_vendor: str = "Okula"
    board_product: str = ""
    board_version: str = "1.0"
    board_serial: str = ""
    # Typ 3 – Gehäuse (Typ-Nummer nach SMBIOS: 3 Desktop, 10 Notebook)
    chassis_vendor: str = "Okula"
    chassis_type: int = 3


@dataclass
class VmProfile:
    name: str
    firmware: str = "uefi"            # uefi-sb | uefi | bios
    tpm: bool = False
    chipset: str = "q35"              # q35 | i440fx
    disk: DiskSpec = field(default_factory=DiskSpec)
    nic: NicSpec = field(default_factory=NicSpec)
    cpu: CpuSpec = field(default_factory=CpuSpec)
    ram_mb: int = 4096
    smbios: Smbios = field(default_factory=Smbios)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict) -> "VmProfile":
        def build(kind, values):
            known = {f.name for f in fields(kind)}
            return kind(**{k: v for k, v in (values or {}).items() if k in known})
        top = {k: v for k, v in data.items() if k in {f.name for f in fields(cls)}}
        for key, kind in (("disk", DiskSpec), ("nic", NicSpec), ("cpu", CpuSpec), ("smbios", Smbios)):
            top[key] = build(kind, top.get(key))
        return cls(**top)

    def validate(self) -> None:
        if not NAME_RE.match(self.name):
            raise VmError(f"Ungültiger VM-Name „{self.name}“ (Buchstaben, Ziffern, . _ -, höchstens 48 Zeichen)")
        checks = ((self.firmware, FIRMWARES, "Firmware"), (self.chipset, CHIPSETS, "Chipsatz"),
                  (self.disk.bus, DISK_BUSES, "Disk-Anschluss"), (self.nic.model, NIC_MODELS, "Netzwerkkarte"))
        for value, allowed, what in checks:
            if value not in allowed:
                raise VmError(f"{what} „{value}“ nicht möglich (erlaubt: {', '.join(allowed)})")
        if self.firmware == "uefi-sb" and self.chipset != "q35":
            raise VmError("Secure Boot braucht den Chipsatz Q35")
        if self.disk.size_gb < 1 or self.cpu.cores < 1 or self.cpu.threads < 1 or self.ram_mb < 256:
            raise VmError("Disk, CPU oder RAM zu klein")
        if self.nic.mac and not MAC_RE.match(self.nic.mac):
            raise VmError(f"MAC-Adresse {self.nic.mac} ungültig (erwartet 52:54:00:xx:xx:xx)")
        if len(self.disk.serial) > 20 or len(self.disk.model) > 40:
            raise VmError("Seriennummer der Disk höchstens 20, Modellname höchstens 40 Zeichen")


def _profile(name, firmware, tpm, chipset, bus, size, model, rpm, nic, cores, ram_gb, chassis) -> VmProfile:
    return VmProfile(name=name, firmware=firmware, tpm=tpm, chipset=chipset,
                     disk=DiskSpec(bus=bus, size_gb=size, model=model, rpm=rpm),
                     nic=NicSpec(model=nic), cpu=CpuSpec(cores=cores, threads=1), ram_mb=ram_gb * 1024,
                     smbios=Smbios(product=name, sku=name, board_product=f"{name}-Board", chassis_type=chassis))


# Vorlagen laut docs/VM.md
PROFILES: dict[str, VmProfile] = {p.name: p for p in (
    _profile("VM-Win11", "uefi-sb", True, "q35", "nvme", 128, "Okula NVMe SSD 128GB", 0, "e1000e", 4, 8, 10),
    _profile("VM-Legacy", "bios", False, "i440fx", "sata", 80, "Okula SATA HDD 80GB", 7200, "e1000", 2, 4, 3),
    _profile("VM-Klein", "uefi", False, "q35", "sata", 64, "Okula SATA SSD 64GB", 0, "e1000e", 2, 4, 3),
)}


def profile(name: str) -> VmProfile:
    """Kopie einer Vorlage (die Vorlagen selbst bleiben unverändert)."""
    try:
        return copy.deepcopy(PROFILES[name])
    except KeyError:
        raise VmError(f"Unbekanntes Profil „{name}“") from None


# ---------- Identität ----------

def new_mac(existing: set[str] | list[str], rng: random.Random | None = None) -> str:
    """Zufällige MAC 52:54:00:xx:xx:xx, die keine bestehende VM hat."""
    rng = rng or random.SystemRandom()
    taken = {m.lower() for m in existing}
    for _ in range(1000):
        mac = "52:54:00:" + ":".join(f"{rng.randrange(256):02x}" for _ in range(3))
        if mac not in taken:
            return mac
    raise VmError("Keine freie MAC-Adresse gefunden")


def _serial(prefix: str, rng: random.Random, length: int = 10) -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return prefix + "".join(rng.choice(chars) for _ in range(length))


def fill_identity(p: VmProfile, existing_macs: set[str] | list[str] = (),
                  rng: random.Random | None = None) -> VmProfile:
    """Fehlende MAC, UUID und Seriennummern ergänzen (gibt eine Kopie zurück)."""
    rng = rng or random.SystemRandom()
    p = copy.deepcopy(p)
    if not p.nic.mac:
        p.nic.mac = new_mac(existing_macs, rng)
    if not p.smbios.uuid:
        p.smbios.uuid = str(uuidlib.UUID(int=rng.getrandbits(128), version=4))
    if not p.smbios.serial:
        p.smbios.serial = _serial("VM-", rng)
    if not p.smbios.board_serial:
        p.smbios.board_serial = p.smbios.serial + "-B"
    if not p.disk.serial:
        p.disk.serial = _serial("OKVM", rng, 12)
    return p


# ---------- libvirt-XML ----------

def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
    el = ET.SubElement(parent, tag, {k.rstrip("_").replace("__", "-"): str(v) for k, v in attrs.items()})
    if text is not None:
        el.text = str(text)
    return el


def _entries(parent: ET.Element, tag: str, values: dict[str, str]) -> None:
    items = [(k, v) for k, v in values.items() if v]
    if items:
        block = _sub(parent, tag)
        for k, v in items:
            _sub(block, "entry", v, name=k)


def _escape_global(value: str) -> str:
    return value.replace(",", ",,")


def domain_xml(p: VmProfile, boot: str = "normal", iso: str = "") -> str:
    """libvirt-Domain-XML zum Profil. boot: normal (Disk → Netzwerk), pxe (Netzwerk zuerst), iso (CD zuerst)."""
    p.validate()
    if not p.nic.mac or not p.smbios.uuid:
        raise VmError("MAC und UUID fehlen (fill_identity aufrufen)")
    q35 = p.chipset == "q35"
    s = p.smbios
    dom = ET.Element("domain", {"type": "kvm"})
    _sub(dom, "name", p.name)
    _sub(dom, "uuid", s.uuid)
    meta = _sub(dom, "metadata")
    ET.SubElement(meta, f"{{{OKULA_NS}}}profile").text = p.to_json()
    _sub(dom, "memory", p.ram_mb, unit="MiB")
    _sub(dom, "currentMemory", p.ram_mb, unit="MiB")
    _sub(dom, "vcpu", p.cpu.cores * p.cpu.threads, placement="static")

    sysinfo = _sub(dom, "sysinfo", type="smbios")
    _entries(sysinfo, "bios", {"vendor": s.bios_vendor, "version": s.bios_version, "date": s.bios_date})
    _entries(sysinfo, "system", {"manufacturer": s.manufacturer, "product": s.product, "version": s.version,
                                 "serial": s.serial, "uuid": s.uuid, "sku": s.sku, "family": s.family})
    _entries(sysinfo, "baseBoard", {"manufacturer": s.board_vendor, "product": s.board_product,
                                    "version": s.board_version, "serial": s.board_serial})
    _entries(sysinfo, "chassis", {"manufacturer": s.chassis_vendor, "version": s.version, "serial": s.serial})

    os_el = _sub(dom, "os", **({"firmware": "efi"} if p.firmware.startswith("uefi") else {}))
    _sub(os_el, "type", "hvm", arch="x86_64", machine="q35" if q35 else "pc")
    if p.firmware.startswith("uefi"):
        sb = "yes" if p.firmware == "uefi-sb" else "no"
        fw = _sub(os_el, "firmware")
        _sub(fw, "feature", enabled=sb, name="enrolled-keys")
        _sub(fw, "feature", enabled=sb, name="secure-boot")
        if sb == "yes":
            _sub(os_el, "loader", secure="yes")
    _sub(os_el, "smbios", mode="sysinfo")

    feats = _sub(dom, "features")
    _sub(feats, "acpi")
    _sub(feats, "apic")
    if p.firmware == "uefi-sb":
        _sub(feats, "smm", state="on")
    _sub(feats, "vmport", state="off")

    cpu = _sub(dom, "cpu", mode="host-passthrough", check="none", migratable="on")
    _sub(cpu, "topology", sockets=1, dies=1, cores=p.cpu.cores, threads=p.cpu.threads)
    clock = _sub(dom, "clock", offset="localtime")
    _sub(clock, "timer", name="rtc", tickpolicy="catchup")
    _sub(clock, "timer", name="pit", tickpolicy="delay")
    _sub(clock, "timer", name="hpet", present="no")
    _sub(dom, "on_poweroff", "destroy")
    _sub(dom, "on_reboot", "restart")
    _sub(dom, "on_crash", "destroy")
    if p.firmware == "uefi-sb":
        pm = _sub(dom, "pm")
        _sub(pm, "suspend-to-mem", enabled="no")
        _sub(pm, "suspend-to-disk", enabled="no")

    order = {"normal": (1, 2, 0), "pxe": (2, 1, 0), "iso": (2, 3, 1)}[boot]   # Disk, Netzwerk, CD
    dev = _sub(dom, "devices")
    disk = _sub(dev, "disk", type="file", device="disk")        # Datei statt Pool-Volume: AppArmor (siehe oben)
    _sub(disk, "driver", name="qemu", type="qcow2", discard="unmap")
    _sub(disk, "source", file=volume_path(p.name))
    target = {"dev": "sda", "bus": "sata"}
    if p.disk.bus == "sata":
        target["rotation_rate"] = str(p.disk.rpm or 1)       # 1 = SSD
    _sub(disk, "target", **target)
    _sub(disk, "serial", p.disk.serial)
    if p.disk.model and p.disk.bus == "sata":
        _sub(disk, "product", p.disk.model)
    _sub(disk, "boot", order=order[0])
    _sub(disk, "alias", name="ua-disk0")

    if boot == "iso":
        if not iso:
            raise VmError("Kein ISO angegeben")
        cd = _sub(dev, "disk", type="file", device="cdrom")
        _sub(cd, "driver", name="qemu", type="raw")
        _sub(cd, "source", file=iso)
        _sub(cd, "target", dev="sdb" if q35 else "hdc", bus="sata" if q35 else "ide")
        _sub(cd, "readonly")
        _sub(cd, "boot", order=order[2])

    nic = _sub(dev, "interface", type="bridge")
    _sub(nic, "mac", address=p.nic.mac)
    _sub(nic, "source", bridge=BRIDGE)
    _sub(nic, "model", type=p.nic.model)
    _sub(nic, "boot", order=order[1])

    if p.tpm:
        tpm = _sub(dev, "tpm", model="tpm-crb")
        _sub(tpm, "backend", type="emulator", version="2.0")
    gfx = _sub(dev, "graphics", type="spice", autoport="yes")
    _sub(gfx, "listen", type="address", address="127.0.0.1")
    video = _sub(dev, "video")
    _sub(video, "model", type="vga", vram="16384", heads="1", primary="yes")
    _sub(dev, "input", type="tablet", bus="usb")
    _sub(dev, "memballoon", model="none")     # sonst legt libvirt ein virtio-Gerät an

    extra_args = []
    if p.cpu.name:
        extra_args += ["-global", f"driver=host-x86_64-cpu,property=model-id,value={_escape_global(p.cpu.name)}"]
    if extra_args:
        cl = ET.SubElement(dom, f"{{{QEMU_NS}}}commandline")
        for arg in extra_args:
            ET.SubElement(cl, f"{{{QEMU_NS}}}arg", {"value": arg})
    if p.disk.bus == "nvme":
        ov = ET.SubElement(dom, f"{{{QEMU_NS}}}override")
        qdev = ET.SubElement(ov, f"{{{QEMU_NS}}}device", {"alias": "ua-disk0"})
        front = ET.SubElement(qdev, f"{{{QEMU_NS}}}frontend")
        for name, typ, value in (("driver", "string", "nvme"), ("bus", "string", "pcie.0" if q35 else "pci.0"),
                                 ("addr", "string", NVME_ADDR), ("model", "remove", None),
                                 ("rotation_rate", "remove", None)):
            attrs = {"name": name, "type": typ}
            if value is not None:
                attrs["value"] = value
            ET.SubElement(front, f"{{{QEMU_NS}}}property", attrs)
    ET.indent(dom)
    return ET.tostring(dom, encoding="unicode") + "\n"


def profile_from_xml(xml: str) -> VmProfile | None:
    """Profil aus den Metadaten einer VM (None = keine VM des Tools)."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    el = root.find(f"metadata/{{{OKULA_NS}}}profile")
    if el is None or not el.text:
        return None
    try:
        return VmProfile.from_dict(json.loads(el.text))
    except (ValueError, TypeError):
        return None


def macs_in_xml(xml: str) -> set[str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return set()
    return {m.get("address", "").lower() for m in root.iter("mac") if m.get("address")}


def volume_name(name: str) -> str:
    return f"{name}.qcow2"


def volume_path(name: str) -> str:
    """Pfad der Disk-Datei im Pool-Verzeichnis (so steht sie in der VM)."""
    return os.path.join(POOL_DIR, volume_name(name))


# ---------- virsh ----------

Run = Callable[[list[str], "str | None"], subprocess.CompletedProcess]

_HINTS = (
    ("failed to connect to the hypervisor", "libvirt nicht erreichbar – installiert (sudo ./install.sh) und nach "
                                            "der Installation einmal ab- und wieder angemeldet?"),
    ("spice graphics are not supported", "Bildschirm (SPICE) fehlt – sudo ./install.sh erneut ausführen"),
    ("could not open '" + POOL_DIR, "Disk-Datei der VM nicht lesbar – sudo ./install.sh erneut ausführen"),
    ("permission denied", "Keine Berechtigung für libvirt – nach der Installation einmal ab- und wieder anmelden"),
    ("storage pool not found", f"Speicherpool „{POOL}“ fehlt – sudo ./install.sh erneut ausführen"),
    ("cannot get interface mtu on 'br0'", "Netzwerkbrücke br0 fehlt – sudo ./install.sh am Server ausführen"),
    ("br0", "Netzwerkbrücke br0 fehlt oder ist nicht aktiv – sudo ./install.sh am Server ausführen"),
    ("domain not found", "VM nicht gefunden"),
    ("domain is already running", "VM läuft bereits"),
    ("domain is not running", "VM ist ausgeschaltet"),
    ("not enough", "Zu wenig Platz oder Speicher auf dem Server"),
)


def _default_run(cmd: list[str], input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=120)


class Virsh:
    """Aktionen auf den VMs. Alle Fehler kommen als VmError mit deutschem Text."""

    def __init__(self, run: Run = _default_run, uri: str = URI):
        self._run, self.uri = run, uri

    def virsh(self, *args: str, input_text: str | None = None, check: bool = True) -> str:
        cmd = ["virsh", "-c", self.uri, *args]
        try:
            r = self._run(cmd, input_text)
        except FileNotFoundError:
            raise VmError("virsh nicht gefunden – Pakete mit sudo ./install.sh installieren") from None
        except (OSError, subprocess.SubprocessError) as e:
            raise VmError(f"virsh {args[0]}: {e}") from None
        if r.returncode != 0 and check:
            raise VmError(self._message(args[0], (r.stderr or r.stdout or "").strip()))
        return r.stdout

    @staticmethod
    def _message(action: str, err: str) -> str:
        low = err.lower()
        for needle, text in _HINTS:
            if needle in low:
                return f"{text} ({err.splitlines()[0] if err else action})"
        return f"virsh {action} fehlgeschlagen: {err or 'unbekannter Fehler'}"

    # --- Abfragen ---

    def names(self) -> list[str]:
        return [n for n in self.virsh("list", "--all", "--name").split() if n]

    def xml(self, name: str, inactive: bool = True) -> str:
        return self.virsh("dumpxml", *(["--inactive"] if inactive else []), name)

    def list(self) -> list[dict]:
        """VMs des Tools: [{name, state, profile}]."""
        result = []
        for name in self.names():
            p = profile_from_xml(self.xml(name))
            if p:
                result.append({"name": name, "state": self.state(name), "profile": p})
        return result

    def state(self, name: str) -> str:
        """running | shut off | paused | … (wie virsh domstate)."""
        return self.virsh("domstate", name).strip()

    def get_profile(self, name: str) -> VmProfile:
        p = profile_from_xml(self.xml(name))
        if not p:
            raise VmError(f"„{name}“ ist keine VM des Recovery-Tools")
        return p

    def used_macs(self) -> set[str]:
        macs: set[str] = set()
        for name in self.names():
            macs |= macs_in_xml(self.xml(name))
        return macs

    # --- Aktionen ---

    def _define(self, xml: str) -> None:
        fd, path = tempfile.mkstemp(prefix="okula-vm-", suffix=".xml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(xml)
            self.virsh("define", path)
        finally:
            os.unlink(path)

    def create(self, p: VmProfile, name: str | None = None) -> VmProfile:
        """Neue VM aus Profil: Disk im Pool anlegen, VM definieren. Gibt das vervollständigte Profil zurück."""
        p = copy.deepcopy(p)
        if name:
            p.name = name
        p.validate()
        if p.name in self.names():
            raise VmError(f"Eine VM „{p.name}“ gibt es schon")
        used = self.used_macs()
        if p.nic.mac and p.nic.mac in used:
            raise VmError(f"MAC-Adresse {p.nic.mac} hat schon eine andere VM")
        p = fill_identity(p, used)
        xml = domain_xml(p)
        self.virsh("vol-create-as", POOL, volume_name(p.name), str(p.disk.size_gb * 10**9), "--format", "qcow2")
        try:
            self._define(xml)
        except VmError:
            self.virsh("vol-delete", "--pool", POOL, volume_name(p.name), check=False)
            raise
        return p

    def start(self, name: str, mode: str = "normal", iso: str = "") -> None:
        """normal; pxe = einmal Netzwerkstart zuerst; iso = ISO als CD einlegen und einmal davon starten."""
        if mode not in START_MODES:
            raise VmError(f"Unbekannte Startart „{mode}“")
        if mode == "iso" and not (iso and os.path.isfile(iso)):
            raise VmError(f"ISO-Datei nicht gefunden: {iso or '(keine)'}")
        p = self.get_profile(name)
        if self.state(name) == "running":
            raise VmError("VM läuft bereits")
        if mode == "normal":
            self.virsh("start", name)
            return
        # Startreihenfolge nur für diesen Start ändern: definieren, starten, wieder normal definieren
        self._define(domain_xml(p, boot=mode, iso=iso))
        try:
            self.virsh("start", name)
        finally:
            self._define(domain_xml(p))

    def shutdown(self, name: str) -> None:
        self.virsh("shutdown", name, "--mode", "acpi")

    def poweroff(self, name: str) -> None:
        self.virsh("destroy", name)

    def delete(self, name: str) -> None:
        """VM mit Disk, NVRAM und TPM-Zustand löschen (Rückfrage ist Sache der Oberfläche)."""
        self.get_profile(name)          # nur VMs des Tools
        if self.state(name) != "shut off":
            self.virsh("destroy", name, check=False)
        self.virsh("undefine", name, "--nvram", "--tpm", "--remove-all-storage")
        self.virsh("vol-delete", "--pool", POOL, volume_name(name), check=False)

    def set_profile(self, name: str, p: VmProfile) -> VmProfile:
        """Hardware einer ausgeschalteten VM ändern. Disk lässt sich nur vergrössern; Name bleibt."""
        old = self.get_profile(name)
        if self.state(name) != "shut off":
            raise VmError("Hardware lässt sich nur bei ausgeschalteter VM ändern")
        p = copy.deepcopy(p)
        p.name = name
        p.smbios.uuid = old.smbios.uuid                 # UUID der VM bleibt
        p.nic.mac = p.nic.mac or old.nic.mac
        if p.nic.mac != old.nic.mac and p.nic.mac in self.used_macs():
            raise VmError(f"MAC-Adresse {p.nic.mac} hat schon eine andere VM")
        if p.disk.size_gb < old.disk.size_gb:
            raise VmError("Disk lässt sich nicht verkleinern")
        p = fill_identity(p)
        xml = domain_xml(p)
        if p.disk.size_gb > old.disk.size_gb:
            self.virsh("vol-resize", "--pool", POOL, volume_name(name), str(p.disk.size_gb * 10**9))
        self._define(xml)
        return p
