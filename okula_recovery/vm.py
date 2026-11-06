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
import shutil
import subprocess
import tempfile
import uuid as uuidlib
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field, fields
from typing import Callable

from okula_recovery import devices, textnorm
from okula_recovery.inventory import CHASSIS

URI = "qemu:///system"
POOL = "okula"
POOL_DIR = "/var/lib/libvirt/images/okula"
BRIDGE = "br0"
QEMU_NS = "http://libvirt.org/schemas/domain/qemu/1.0"
OKULA_NS = "https://okula.ch/recovery/vm/1"
DISK_ALIAS, NIC_ALIAS = "ua-disk0", "ua-net0"   # feste Namen der Geräte in QEMU (NVMe-Umbau, Startreihenfolge)
NVME_ADDR = "0x1b"          # PCI-Steckplatz der NVMe-Disk (libvirt belegt Steckplätze ab 0x2 aufsteigend)
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
MAC_RE = re.compile(r"^52:54:00(:[0-9a-f]{2}){3}$")

FIRMWARES = ("uefi-sb", "uefi", "bios")
CHIPSETS = ("q35", "i440fx")
DISK_BUSES = ("nvme", "sata")
# e1000e (Intel 82574L) und e1000 (Intel 82540EM): Treiber in Windows enthalten.
# rtl8139: in Windows 10/11 ohne mitgelieferten Treiber – nur für Linux sinnvoll.
NIC_MODELS = ("e1000e", "e1000", "rtl8139")
# Startarten: normal = Disk → Netzwerk; agent = einmal Netzwerk zuerst (Agent per Netzwerkstart); iso = einmal CD.
# Nicht fest „Netzwerk zuerst“ wie bei echten Geräten: Beendet sich grub mit „von der Festplatte starten“ (exit),
# zeigt OVMF (UEFI) das Setup-Menü statt den nächsten Eintrag zu starten – am Server geprüft (06.11.2026). Darum
# stellt das Tool die Reihenfolge der laufenden VM um (set_boot_runtime), sobald der Agent verbunden ist.
START_MODES = ("normal", "agent", "iso")
MIN_FREE_GB = 20            # so viel muss auf dem Server mindestens frei bleiben
RAM_RESERVE_MB = 2048       # für den Server selbst

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
    chassis_serial: str = ""          # leer = Seriennummer des Systems (Typ 1)


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
    """libvirt-Domain-XML zum Profil. boot: normal (Disk → Netzwerk), agent (Netzwerk → Disk), iso (CD → Disk →
    Netzwerk). Gespeichert ist immer „normal“; agent/iso gelten nur für einen Start (siehe Virsh.start)."""
    if boot not in START_MODES:
        raise VmError(f"Unbekannte Startart „{boot}“")
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
    _entries(sysinfo, "chassis", {"manufacturer": s.chassis_vendor, "version": s.version,
                                  "serial": s.chassis_serial or s.serial})

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

    order = {"normal": (1, 2, 0), "agent": (2, 1, 0), "iso": (2, 3, 1)}[boot]   # Disk, Netzwerk, CD
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
    _sub(disk, "alias", name=DISK_ALIAS)

    if boot == "iso":
        if not iso:
            raise VmError("Kein ISO angegeben")
        cd = _sub(dev, "disk", type="file", device="cdrom")
        _sub(cd, "driver", name="qemu", type="raw")
        src = _sub(cd, "source", file=iso)
        # ISO meist auf dem NAS (CIFS): libvirt darf die Datei nicht umbesitzen (chown geht dort nicht)
        _sub(src, "seclabel", model="dac", relabel="no")
        _sub(cd, "target", dev="sdb" if q35 else "hdc", bus="sata" if q35 else "ide")
        _sub(cd, "readonly")
        _sub(cd, "boot", order=order[2])

    nic = _sub(dev, "interface", type="bridge")
    _sub(nic, "mac", address=p.nic.mac)
    _sub(nic, "source", bridge=BRIDGE)
    _sub(nic, "model", type=p.nic.model)
    _sub(nic, "boot", order=order[1])
    _sub(nic, "alias", name=NIC_ALIAS)

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
        qdev = ET.SubElement(ov, f"{{{QEMU_NS}}}device", {"alias": DISK_ALIAS})
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


def unique_name(base: str, taken) -> str:
    """Name für eine neue VM: Vorschlag (Profilname), sonst „VM-Klein-2“, „VM-Klein-3“ …"""
    taken = {t.lower() for t in taken}
    if base.lower() not in taken:
        return base
    n = 2
    while f"{base}-{n}".lower() in taken:
        n += 1
    return f"{base}-{n}"


def disk_name(p: VmProfile) -> str:
    """Name der Disk, wie der Agent sie in der VM sieht."""
    return "nvme0n1" if p.disk.bus == "nvme" else "sda"


def pre_inventory(p: VmProfile, collected: str = "") -> dict:
    """Vorläufiges Inventar aus dem Profil (Format wie inventory.collect), bis der Agent in der VM das echte
    meldet. Enthält die Kabel-Netzwerkkarte mit der VM-MAC: Lokal vergebene MACs (52:54:00:…) nimmt der
    Netzwerkstart nur aus dem Inventar (devices.netboot_macs) – sonst bekäme die VM keine Antwort."""
    if not p.nic.mac or not p.smbios.uuid:
        raise VmError("MAC und UUID fehlen (fill_identity aufrufen)")
    s, uefi = p.smbios, p.firmware.startswith("uefi")
    dmi = {"sys_vendor": s.manufacturer, "product_name": s.product, "product_version": s.version,
           "product_serial": s.serial, "product_uuid": s.uuid.lower(), "product_sku": s.sku,
           "product_family": s.family, "board_vendor": s.board_vendor, "board_name": s.board_product,
           "board_serial": s.board_serial, "bios_vendor": s.bios_vendor, "bios_version": s.bios_version,
           "bios_date": s.bios_date, "chassis_type": str(s.chassis_type), "chassis_vendor": s.chassis_vendor,
           "chassis_serial": s.chassis_serial or s.serial, "chassis": CHASSIS.get(str(s.chassis_type), "")}
    nvme = p.disk.bus == "nvme"
    disk = {"name": disk_name(p), "path": f"/dev/{disk_name(p)}", "size": p.disk.size_gb * 10**9,
            "model": "QEMU NVMe Ctrl" if nvme else p.disk.model, "serial": p.disk.serial,
            "transport": "nvme" if nvme else "sata", "pttype": "", "fstype": "", "partitions": []}
    return {"collected": collected, "provisional": "VM-Profil",
            "dmi": dmi, "cpu": {"model": p.cpu.name or "Prozessor des Servers (virtuell)",
                                "cores": p.cpu.cores, "threads": p.cpu.cores * p.cpu.threads},
            "memory": p.ram_mb * 1024 * 1024, "batteries": [],
            "network": [{"name": "eth0", "mac": p.nic.mac.lower(), "wireless": False, "driver": p.nic.model}],
            "disks": [disk], "systems": [],
            "platform": {"tpm": "2.0" if p.tpm else "", "uefi": uefi,
                         "secure_boot": (p.firmware == "uefi-sb") if uefi else None},
            "oem_key": ""}


def describe(p: VmProfile) -> str:
    """Hardware in einer Zeile, z. B. „UEFI + Secure Boot + TPM 2.0 · Q35 · NVMe 128 GB · Intel e1000e · …“."""
    fw = {"uefi-sb": "UEFI + Secure Boot", "uefi": "UEFI", "bios": "BIOS (Legacy)"}[p.firmware]
    if p.tpm:
        fw += " + TPM 2.0"
    disk = ("NVMe" if p.disk.bus == "nvme" else "SATA-HDD" if p.disk.rpm else "SATA-SSD") + f" {p.disk.size_gb} GB"
    nic = {"e1000e": "Intel e1000e", "e1000": "Intel e1000", "rtl8139": "Realtek rtl8139"}[p.nic.model]
    ram = p.ram_mb / 1024
    ram_text = f"{ram:.0f} GB" if ram == int(ram) else f"{ram:.1f} GB"
    return " · ".join((fw, "Q35" if p.chipset == "q35" else "i440FX", disk, nic,
                       f"{p.cpu.cores * p.cpu.threads} Kern{'e' if p.cpu.cores * p.cpu.threads != 1 else ''}",
                       f"{ram_text} RAM"))


# Kurzbeschreibung der Profile (docs/VM.md) für den Dialog „Neue virtuelle Maschine“
PROFILE_NOTES = {
    "VM-Win11": "Moderner Business-Laptop – Master-Image bauen, Windows 11, Automatisierung",
    "VM-Legacy": "Älteres Gerät mit BIOS – BIOS-Netzwerkstart, Windows 10, alte Hardware",
    "VM-Klein": "Gerät mit kleiner Disk – Zurückspielen auf kleinere Disk, Linux",
}


# ---------- Digitaler Zwilling: Hardware von einem Gerät übernehmen (I-001 Auftrag 3) ----------

TWIN_UUID_PREFIX = "0c1a0000"    # ersetzt die ersten 8 Hex-Stellen der System-UUID (Kennzeichen „Zwilling“)
SMBIOS_MAX = 64                  # Länge der SMBIOS-Texte (Seriennummern) in der VM
SERVER_CORES_FREE = 2            # so viele Kerne bleiben dem Server
TWIN_RAM_RESERVE_MB = 4096       # so viel RAM bleibt dem Server beim Zwilling frei
BIOS_DATE_RE = re.compile(r"^\d{2}/\d{2}/(\d{2}|\d{4})$")   # libvirt verlangt MM/DD/YY bzw. MM/DD/YYYY
# Ergebnis-Zeichen der Vorschau: genau übernommen, angepasst, nicht übernommen
EXACT, ADAPTED, SKIPPED = "✔", "~", "✖"


@dataclass
class ServerInfo:
    """Was der Server für einen Zwilling hergibt (in der Oberfläche aus os.cpu_count() und ram_mb())."""
    cores: int = 8
    ram_free_mb: int = 16384
    taken_names: tuple = ()      # VM- und Gerätenamen, die es schon gibt
    taken_uuids: tuple = ()      # UUIDs (klein geschrieben), die es schon gibt


def system_disk(inv: dict) -> dict:
    """Disk mit installiertem System (inventory.systems[].disk), sonst die erste Disk ({} ohne Disk)."""
    disks = (inv or {}).get("disks") or []
    for s in (inv or {}).get("systems") or []:
        for d in disks:
            if s.get("disk") and d.get("name") == s.get("disk"):
                return d
    return disks[0] if disks else {}


def wired_nic(inv: dict) -> dict:
    nics = (inv or {}).get("network") or []
    return next((n for n in nics if not n.get("wireless")), nics[0] if nics else {})


def nic_vendor(driver: str) -> str:
    """Hersteller der echten Netzwerkkarte aus dem Linux-Treiber (für die Vorschau)."""
    d = (driver or "").lower()
    if d.startswith(("r81", "rtl", "8139")):
        return "Realtek"
    if d.startswith(("e1000", "igb", "igc", "ixgb", "ice", "i40e")):
        return "Intel"
    if d.startswith(("tg3", "bnx")):
        return "Broadcom"
    if d.startswith(("atl", "alx")):
        return "Qualcomm Atheros"
    return ""


def twin_name(device_name: str, taken=()) -> str:
    """„VM-<Gerätename>“ mit erlaubten Zeichen (NAME_RE), höchstens 48 Zeichen, eindeutig."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", textnorm.to_ascii(device_name or "")).strip("-._")
    base = re.sub(r"-{2,}", "-", base)
    name = ("VM-" + base if base else "VM-Zwilling")[:44].rstrip("-._")
    return unique_name(name, taken)


def _twin_serial(value: str, prefix: str = "VM-", limit: int = SMBIOS_MAX) -> str:
    """Seriennummer mit Kennzeichen; Platzhalter ab Werk → "" (wird wie bei neuen VMs erzeugt)."""
    if devices.placeholder_serial((value or "").strip()):
        return ""
    v = re.sub(r"\s+", "", value)
    return (prefix + v)[:limit] if not devices.placeholder_serial(v) else ""


def _twin_uuid(value: str, taken=()) -> str:
    """Erste 8 Hex-Stellen → 0c1a0000 (Rest gleich). Gibt es die schon (zweiter Zwilling), 0c1a0001 … .
    Platzhalter oder ungültig → "" (wird neu erzeugt)."""
    if devices.placeholder_uuid(value or ""):
        return ""
    try:
        rest = str(uuidlib.UUID(value.strip()))[8:]
    except (ValueError, AttributeError):
        return ""
    taken = {t.lower() for t in taken} | {value.strip().lower()}
    for n in range(0x10000):
        candidate = f"{TWIN_UUID_PREFIX[:4]}{n:04x}{rest}"
        if candidate not in taken:
            return candidate
    return ""


def _disk_serial(value: str) -> str:
    v = re.sub(r"[^A-Za-z0-9_.-]+", "", value or "")
    if devices.placeholder_serial((value or "").strip()) or devices.placeholder_serial(v):
        return ""
    return "VM" + v[-18:]                     # QEMU: höchstens 20 Zeichen; das Ende unterscheidet Disks meist


def _gb_text(mb: int) -> str:
    gb = mb / 1024
    return f"{gb:.0f} GB" if abs(gb - round(gb)) < 0.05 else f"{gb:.1f} GB"


def profile_from_inventory(inv: dict, server: ServerInfo, device_name: str = "") -> tuple[VmProfile, list[str]]:
    """VM-Profil mit der Hardware eines Geräts (digitaler Zwilling) und Hinweise zu jeder Abweichung.
    Übernahme laut docs/VM.md „Hardware von einem Gerät übernehmen“. Identität abgewandelt (VM-…, UUID 0c1a…,
    Disk-Seriennummer VM…), MAC immer neu – sonst führt das Tool VM und Gerät zusammen. Kein GTK, kein virsh."""
    inv = inv or {}
    d = inv.get("dmi") or {}
    plat = inv.get("platform") or {}
    notes: list[str] = []
    disk = system_disk(inv)

    # Firmware aus der Partitionstabelle der Systemdisk (so ist das System installiert)
    pttype = (disk.get("pttype") or "").lower()
    uefi = pttype == "gpt" if pttype in ("gpt", "dos") else bool(plat.get("uefi"))
    if not pttype:
        notes.append("Disk ohne Partitionstabelle – Firmware wie beim Gerät gestartet ("
                     + ("UEFI" if uefi else "BIOS") + ")")
    firmware = ("uefi-sb" if plat.get("secure_boot") else "uefi") if uefi else "bios"
    chipset = "q35" if uefi else "i440fx"
    tpm_dev = str(plat.get("tpm") or "")
    tpm = bool(tpm_dev)
    if tpm and tpm_dev != "2.0":
        notes.append(f"TPM {tpm_dev} → TPM 2.0 (QEMU bildet nur 2.0 nach)")

    # Disk
    size = int(disk.get("size") or 0)
    size_gb = max(1, -(-size // 10**9)) if size else 64
    if not size:
        notes.append("Disk-Grösse unbekannt – 64 GB")
    bus = "nvme" if (disk.get("transport") or "").lower() == "nvme" else "sata"
    if disk and (disk.get("transport") or "").lower() not in ("nvme", "sata", ""):
        notes.append(f"Disk-Anschluss {disk.get('transport')} → SATA")
    model = re.sub(r"\s+", " ", disk.get("model") or "").strip()
    if len(model) > 40:
        notes.append("Modellname der Disk auf 40 Zeichen gekürzt")
        model = model[:40].rstrip()
    if bus == "nvme" and model:
        notes.append(f"Modellname der NVMe-Disk bleibt „QEMU NVMe Ctrl“ (statt {model})")
    rpm = int(disk.get("rpm") or disk.get("rotation_rate") or 0)
    disk_spec = DiskSpec(bus=bus, size_gb=size_gb, model=model, serial=_disk_serial(disk.get("serial") or ""),
                         rpm=rpm if bus == "sata" and rpm > 1 else 0)

    # CPU: Name und Anzahl wie im Gerät, höchstens Server-Kerne − 2
    c = inv.get("cpu") or {}
    cores = max(1, int(c.get("cores") or 0) or 2)
    threads_total = max(cores, int(c.get("threads") or 0) or cores)
    per_core = max(1, threads_total // cores)
    limit = max(1, int(server.cores or 1) - SERVER_CORES_FREE)
    if cores * per_core > limit:
        old = f"{cores} Kerne / {cores * per_core} Threads"
        if per_core > limit:
            per_core = 1
        cores = max(1, limit // per_core)
        notes.append(f"Prozessor {old} → {cores} Kerne / {cores * per_core} Threads (Server)")
    cpu_name = re.sub(r"\s+", " ", c.get("model") or "").strip()

    # RAM: wie im Gerät (Inventar = Arbeitsspeicher ohne Reservat → auf ganze GB), höchstens freier RAM − 4 GB
    mem = int(inv.get("memory") or 0)
    ram = max(1024, -(-mem // 2**30) * 1024) if mem else 4096
    if not mem:
        notes.append("Arbeitsspeicher unbekannt – 4 GB")
    cap = (int(server.ram_free_mb or 0) - TWIN_RAM_RESERVE_MB) // 512 * 512
    if server.ram_free_mb and ram > cap:
        new = max(1024, cap)
        notes.append(f"RAM {_gb_text(ram)} → {_gb_text(new)} (Server)")
        ram = new

    # Netzwerkkarte: immer Intel (Treiber in Windows), MAC immer eigene
    nic_model = "e1000e" if chipset == "q35" else "e1000"
    real = wired_nic(inv)
    driver = real.get("driver") or ""
    if driver and driver != nic_model:
        vendor = nic_vendor(driver)
        notes.append(f"Netzwerkkarte {(vendor + ' ') if vendor else ''}{driver} → Intel {nic_model}")
    notes.append("MAC-Adresse neu (eigene MAC der VM)")

    # SMBIOS genau, Identität abgewandelt; fehlende Werte leer (keine Okula-Vorgaben)
    def text(key: str) -> str:
        return re.sub(r"\s+", " ", str(d.get(key) or "")).strip()[:SMBIOS_MAX]

    bios_date = text("bios_date")
    if bios_date and not BIOS_DATE_RE.match(bios_date):
        notes.append(f"BIOS-Datum „{bios_date}“ nicht übernehmbar (Format MM/TT/JJJJ)")
        bios_date = ""
    try:
        chassis_type = int(d.get("chassis_type") or 0)
    except (TypeError, ValueError):
        chassis_type = 0
    chassis_type = chassis_type if 1 <= chassis_type <= 36 else 2          # 2 = „Unknown“ nach SMBIOS
    if d.get("chassis") or d.get("chassis_type"):
        notes.append("Gehäusetyp nur im Profil (in der VM nicht einstellbar)")
    serial = _twin_serial(d.get("product_serial") or "")
    uid = _twin_uuid(d.get("product_uuid") or "", server.taken_uuids)
    if not serial:
        notes.append("Seriennummer des Geräts fehlt oder ist ein Platzhalter – neue erzeugt")
    if not uid:
        notes.append("System-UUID des Geräts fehlt oder ist ein Platzhalter – neue erzeugt")
    smbios = Smbios(bios_vendor=text("bios_vendor"), bios_version=text("bios_version"), bios_date=bios_date,
                    manufacturer=text("sys_vendor"), product=text("product_name"), version=text("product_version"),
                    sku=text("product_sku"), family=text("product_family"), serial=serial, uuid=uid,
                    board_vendor=text("board_vendor"), board_product=text("board_name"),
                    board_version=text("board_version"), board_serial=_twin_serial(d.get("board_serial") or ""),
                    chassis_vendor=text("chassis_vendor"), chassis_type=chassis_type,
                    chassis_serial=_twin_serial(d.get("chassis_serial") or ""))
    if smbios.serial and not smbios.board_serial:
        smbios.board_serial = smbios.serial + "-B"     # sonst erzeugt fill_identity eine eigene
    if inv.get("oem_key"):
        notes.append("OEM-Key nicht übernommen – Windows bleibt „nicht aktiviert“")

    p = VmProfile(name=twin_name(device_name or " ".join(x for x in (text("sys_vendor"), text("product_name"))
                                                         if x), server.taken_names),
                  firmware=firmware, tpm=tpm, chipset=chipset, disk=disk_spec,
                  nic=NicSpec(model=nic_model), cpu=CpuSpec(cores=cores, threads=per_core, name=cpu_name),
                  ram_mb=ram, smbios=smbios)
    p.validate()
    return p, notes


def twin_rows(inv: dict, p: VmProfile) -> list[tuple[str, str, str, str]]:
    """Vorschau Gerät → VM: (Merkmal, Gerät, VM, Zeichen ✔ ~ ✖) laut Tabelle in docs/VM.md."""
    inv = inv or {}
    d, plat, c = inv.get("dmi") or {}, inv.get("platform") or {}, inv.get("cpu") or {}
    s = p.smbios
    rows: list[tuple[str, str, str, str]] = []

    def join(*parts) -> str:
        return " ".join(str(x) for x in parts if x)

    def same(label: str, dev: str, vmv: str) -> None:
        rows.append((label, dev or "–", vmv or "–", EXACT if dev == vmv else ADAPTED))

    same("Hersteller / Modell", join(d.get("sys_vendor"), d.get("product_name")), join(s.manufacturer, s.product))
    same("Version / SKU / Familie", " · ".join(x for x in (d.get("product_version"), d.get("product_sku"),
                                                           d.get("product_family")) if x),
         " · ".join(x for x in (s.version, s.sku, s.family) if x))
    same("Mainboard", join(d.get("board_vendor"), d.get("board_name")), join(s.board_vendor, s.board_product))
    same("BIOS", join(d.get("bios_vendor"), d.get("bios_version"), d.get("bios_date")),
         join(s.bios_vendor, s.bios_version, s.bios_date))
    rows.append(("Gehäusetyp", d.get("chassis") or "–", (CHASSIS.get(str(s.chassis_type), "") or "–")
                 + " (nur im Profil)", ADAPTED))
    rows.append(("Seriennummer", d.get("product_serial") or "–", s.serial or "neu", ADAPTED))
    rows.append(("System-UUID", d.get("product_uuid") or "–", s.uuid or "neu", ADAPTED))
    disk = system_disk(inv)
    pt = (disk.get("pttype") or "").lower()
    dev_fw = {"gpt": "UEFI (GPT)", "dos": "BIOS (MBR)"}.get(pt, "UEFI" if plat.get("uefi") else "BIOS")
    if plat.get("secure_boot"):
        dev_fw += " · Secure Boot"
    vm_fw = {"uefi-sb": "UEFI · Secure Boot", "uefi": "UEFI", "bios": "BIOS (Legacy)"}[p.firmware]
    rows.append(("Firmware", dev_fw, vm_fw + (" · Q35" if p.chipset == "q35" else " · i440FX"), EXACT))
    tpm = str(plat.get("tpm") or "")
    rows.append(("TPM", tpm or "keins", "2.0" if p.tpm else "keins", EXACT if (tpm or "keins") ==
                 ("2.0" if p.tpm else "keins") else ADAPTED))
    dev_cpu = f"{c.get('model', '')} ({c.get('cores', '?')} Kerne / {c.get('threads', '?')} Threads)" if c else "–"
    vm_threads = p.cpu.cores * p.cpu.threads
    vm_cpu = f"{p.cpu.name} ({p.cpu.cores} Kerne / {vm_threads} Threads)"
    exact = c and int(c.get("cores") or 0) == p.cpu.cores and int(c.get("threads") or 0) == vm_threads
    rows.append(("Prozessor", dev_cpu, vm_cpu + " · Leistung der Server-CPU", EXACT if exact else ADAPTED))
    mem = int(inv.get("memory") or 0)
    rows.append(("Arbeitsspeicher", _gb_text(mem // 2**20) if mem else "–", _gb_text(p.ram_mb),
                 EXACT if mem and -(-mem // 2**30) * 1024 == p.ram_mb else ADAPTED))
    dev_disk = join(f"{int(disk.get('size') or 0) / 10**9:.0f} GB" if disk.get("size") else "",
                    (disk.get("transport") or "").upper(), disk.get("model")) if disk else "–"
    vm_disk = join(f"{p.disk.size_gb} GB", p.disk.bus.upper(),
                   "QEMU NVMe Ctrl" if p.disk.bus == "nvme" else p.disk.model)
    rows.append(("Disk", dev_disk, vm_disk, EXACT if p.disk.bus == "sata" and
                 (disk.get("model") or "").strip() == p.disk.model else ADAPTED))
    rows.append(("Disk-Seriennummer", disk.get("serial") or "–", p.disk.serial or "neu", ADAPTED))
    nic = wired_nic(inv)
    vendor = nic_vendor(nic.get("driver", ""))
    rows.append(("Netzwerkkarte", join(vendor, nic.get("driver")) or "–",
                 f"Intel {p.nic.model} · eigene MAC", ADAPTED))
    rows.append(("Windows-Schlüssel (OEM)", "vorhanden" if inv.get("oem_key") else "keiner",
                 "nicht übernommen – Windows „nicht aktiviert“", SKIPPED))
    rows.append(("Akku, WLAN, Grafik, Sound, SMART", "", "nicht nachbildbar", SKIPPED))
    return rows


# Verlaufseinträge, nach denen auf der Disk einer VM ein System sein kann (Ä-036)
SYSTEM_KINDS = ("install", "linux", "restore", "auto")


def blank_disk(inv: dict, history: list[dict]) -> bool:
    """Ä-036: Hatte die VM noch nie ein System? Ja, wenn keine Disk im Inventar Partitionen bzw. eine
    Partitionstabelle hat und im Verlauf weder eine Installation noch ein Zurückspielen noch ein Start von ISO
    steht (von ISO lässt sich in der VM von Hand installieren)."""
    disks = (inv or {}).get("disks") or []
    if any(d.get("partitions") or d.get("pttype") for d in disks):
        return False
    for h in history or []:
        if h.get("kind") in SYSTEM_KINDS and h.get("ok") is not False:
            return False
        if h.get("kind") == "vm" and (h.get("text") or "").startswith("VM von ISO gestartet"):
            return False
    return True


def free_disk(path: str = POOL_DIR) -> int:
    """Freier Platz (Byte) für die Disk-Dateien; Pool-Ordner fehlt → übergeordneter Ordner."""
    while path and not os.path.isdir(path):
        path = os.path.dirname(path)
    try:
        return shutil.disk_usage(path or "/").free
    except OSError:
        return 0


def ram_mb(meminfo: str | None = None) -> tuple[int, int]:
    """(RAM gesamt, verfügbar) des Servers in MiB."""
    if meminfo is None:
        try:
            with open("/proc/meminfo") as f:
                meminfo = f.read()
        except OSError:
            return 0, 0
    values = dict(re.findall(r"^(MemTotal|MemAvailable):\s*(\d+) kB", meminfo, re.M))
    return int(values.get("MemTotal", 0)) // 1024, int(values.get("MemAvailable", 0)) // 1024


def check_resources(p: VmProfile, free_bytes: int, total_mb: int, available_mb: int,
                    planned: list[VmProfile] = ()) -> tuple[list[str], list[str]]:
    """(Fehler, Hinweise) vor dem Erstellen. Die Disk-Datei wächst mit dem belegten Platz – darum ist zu wenig
    Platz für die volle Grösse nur ein Hinweis; unter MIN_FREE_GB ist Schluss. planned = bestehende VMs."""
    errors, notes = [], []
    gb = 10**9
    if free_bytes < MIN_FREE_GB * gb:
        errors.append(f"Nur {free_bytes / gb:.0f} GB frei auf dem Server – mindestens {MIN_FREE_GB} GB nötig")
    else:
        full = p.disk.size_gb * gb + sum(o.disk.size_gb * gb for o in planned)
        if free_bytes < full:
            notes.append(f"{free_bytes / gb:.0f} GB frei – reicht nicht, wenn alle VM-Disks ganz gefüllt werden "
                         f"({full / gb:.0f} GB)")
    if total_mb and p.ram_mb > total_mb - RAM_RESERVE_MB:
        errors.append(f"{p.ram_mb // 1024} GB RAM sind zu viel – der Server hat {total_mb / 1024:.0f} GB")
    elif available_mb and p.ram_mb > available_mb - RAM_RESERVE_MB:
        notes.append(f"Zurzeit nur {available_mb / 1024:.1f} GB RAM frei – vor dem Einschalten andere VMs "
                     "herunterfahren")
    return errors, notes


def viewer_command(name: str, uri: str = URI) -> list[str]:
    """Bildschirm der VM im eigenen Fenster; wartet, bis die VM läuft, und verbindet nach Neustarts neu."""
    return ["virt-viewer", "-c", uri, "--wait", "--reconnect", name]


def available() -> bool:
    """libvirt-Werkzeuge installiert? (Ordner „Virtuelle Maschinen“ zeigen)"""
    return shutil.which("virsh") is not None


STATE_TEXT = {"running": "läuft", "shut off": "aus", "paused": "angehalten", "in shutdown": "fährt herunter",
              "crashed": "abgestürzt", "pmsuspended": "Standby", "idle": "läuft", "blocked": "läuft"}


def state_text(state: str) -> str:
    """virsh-Zustand → Anzeige („aus“, „läuft“ …); leer/unbekannt → „Zustand unbekannt“."""
    return STATE_TEXT.get(state, "Zustand unbekannt" if not state else state)


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

    def states(self) -> dict[str, str]:
        """Zustand aller VMs mit einem Aufruf (virsh list --all) – für die Anzeige alle 5 s."""
        result = {}
        for line in self.virsh("list", "--all").splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[0] != "Id" and not parts[0].startswith("-" * 3):
                result[parts[1]] = parts[2].strip()
        return result

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
        """normal = von der Disk; agent = einmal Netzwerk zuerst (Agent per Netzwerkstart); iso = ISO als CD
        einlegen und einmal davon starten. Die geänderte Reihenfolge gilt bis zum Ausschalten bzw. bis
        set_boot_runtime sie umstellt; gespeichert bleibt „normal“."""
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

    def reboot(self, name: str) -> None:
        self.virsh("reboot", name, "--mode", "acpi")

    def _qmp(self, name: str, command: str, **arguments) -> object:
        out = self.virsh("qemu-monitor-command", name, json.dumps({"execute": command, "arguments": arguments}))
        try:
            return json.loads(out).get("return")
        except (ValueError, AttributeError):
            raise VmError(f"Unerwartete Antwort von QEMU: {out.strip()[:200]}") from None

    def set_boot_runtime(self, name: str, network_first: bool) -> bool:
        """Startreihenfolge einer laufenden VM für den nächsten Neustart umstellen (QEMU liest sie bei jedem
        Neustart neu, OVMF und SeaBIOS richten sich danach). Ausgeschaltet: nichts zu tun (False).
        Neue Nummern über den bisherigen, weil QEMU doppelte Nummern ablehnt."""
        if self.state(name) != "running":
            return False
        paths = {alias: f"/machine/peripheral/{alias}" for alias in (DISK_ALIAS, NIC_ALIAS)}
        current = [self._qmp(name, "qom-get", path=path, property="bootindex") for path in paths.values()]
        base = max([c for c in current if isinstance(c, int)] + [0]) + 1
        order = (NIC_ALIAS, DISK_ALIAS) if network_first else (DISK_ALIAS, NIC_ALIAS)
        for i, alias in enumerate(order):
            self._qmp(name, "qom-set", path=paths[alias], property="bootindex", value=base + i)
        return True

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
