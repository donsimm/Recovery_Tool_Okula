"""Geräteverwaltung im Tool: erfasste Geräte, Wiedererkennung, Ordner, Verlauf, Notizen.

Ablage lokal auf dem Server (XDG_DATA_HOME, Standard ~/.local/share/okula-recovery/geraete):
    geraete/<Geräte-ID>.json                       → „Neu / nicht einsortiert“
    geraete/Zürich/Buchhaltung/<ID>.json           → einsortiert (max. 3 Ordnerebenen)
Die Datei heisst nach der ID, damit Umbenennen nur den Anzeigenamen ändert.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from okula_recovery import nasfiles, textnorm

MAX_DEPTH = 3
MAX_HISTORY = 500
STRONG = ("uuid:", "sn:")  # eindeutige Schlüssel; MAC/Disk sind nur Hinweise
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


# Kennungen, die ab Werk auf vielen Geräten gleich sind (B-001) – nie als Identität verwenden
PLACEHOLDER_UUIDS = {"03000200-0400-0500-0006-000700080009", "12345678-1234-5678-90ab-cddeefaabbcc",
                     "4c4c4544-0000-2010-8020-80c04f202020"}
PLACEHOLDER_SERIALS = {"default string", "to be filled by o.e.m.", "to be filled by oem", "system serial number",
                       "not specified", "not applicable", "none", "null", "n/a", "na", "oem", "o.e.m.", "invalid",
                       "chassis serial number", "base board serial number", "serial", "serial number", "unknown",
                       "123456789", "0123456789", "1234567890", "default", "empty", "type1productconfigid"}
AMBIGUOUS_FILE = "mehrdeutig.ids"
VM_FOLDER = "Virtuelle Maschinen"   # fester Ordner für die VMs des Tools (I-001): keine Unterordner, nicht umbenennbar   # Kennungen, die an zwei Geräten gleichzeitig gesehen wurden (JSON-Liste)


def placeholder_uuid(value: str) -> bool:
    v = (value or "").strip().lower()
    return not v or v in PLACEHOLDER_UUIDS or len(set(v.replace("-", ""))) <= 2


def placeholder_serial(value: str) -> bool:
    v = (value or "").strip().lower()
    return len(v) < 4 or v in PLACEHOLDER_SERIALS or len(set(v)) <= 1 or bool(re.fullmatch(r"(0x)?0+", v))


def real_mac(mac: str) -> bool:
    """Feste Hardware-MAC: nicht leer, nicht 00…, nicht lokal vergeben (zufällige MACs, USB-Tethering, VMs)."""
    m = (mac or "").lower()
    try:
        return bool(m) and m != "00:00:00:00:00:00" and not int(m.split(":")[0], 16) & 0x02
    except ValueError:
        return False


class DeviceError(Exception):
    pass


def default_base() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "okula-recovery" / "geraete"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Device:
    id: str
    key: str = ""                      # Identität: uuid:… / sn:… / mac:…
    name: str = ""
    first_seen: str = ""
    last_seen: str = ""
    last_ip: str = ""
    agent_ids: list[str] = field(default_factory=list)
    macs: list[str] = field(default_factory=list)
    disk_serials: list[str] = field(default_factory=list)
    inventory: dict = field(default_factory=dict)
    notes: str = ""
    product_key: str = ""              # Windows-Schlüssel von Hand (Retail/Volumen); OEM kommt aus dem Inventar
    netboot: bool = False              # darf den Agent per Netzwerk (PXE) starten – nur mit dieser Freigabe
    netfirst: bool = False             # UEFI-Startreihenfolge: Netzwerk zuerst (Fernsteuerung), ohne Auftrag lokal
    boot_request: bool = False         # beim nächsten Start einmal den Agent laden
    boot_saved: list[str] = field(default_factory=list)   # Startreihenfolge vor „Netzwerk zuerst“ (zum Zurückstellen)
    boot_status: dict = field(default_factory=dict)       # zuletzt vom Agent gemeldet (netfirst, network, labels, …)
    automation: dict = field(default_factory=dict)        # Einstellungen der Automatisierung (automation.Settings)
    warranty: dict = field(default_factory=dict)          # Garantie (warranty.result/manual): until, source, checked …
    bios: dict = field(default_factory=dict)              # zuletzt gelesenes BIOS (biosread, I-032) – zum Vergleichen
    hwtests: list = field(default_factory=list)           # Hardware-Tests (I-023), neuester zuerst, höchstens 10
    win11_unsupported: str = ""        # Datum: Windows 11 trotz „nicht tauglich“ installiert (keine Update-Garantie)
    vm: dict = field(default_factory=dict)  # virtuelle Maschine des Tools: {"name": libvirt-Name, "profile": …}
    history: list[dict] = field(default_factory=list)
    folder: str = ""                   # nicht gespeichert: ergibt sich aus dem Ablageort

    @property
    def os_name(self) -> str:
        systems = self.inventory.get("systems") or []
        return systems[0]["name"] if systems else ""

    @property
    def windows_key(self) -> tuple[str, str]:
        """(Schlüssel, Herkunft): von Hand hinterlegt hat Vorrang vor dem OEM-Schlüssel aus dem BIOS."""
        if self.product_key:
            return self.product_key, "hinterlegt"
        oem = self.inventory.get("oem_key") or ""
        return (oem, "BIOS (OEM)") if oem else ("", "")

    @property
    def windows_edition(self) -> str:
        """Edition des zuletzt erkannten Windows (z. B. Professional, Core) – passt meist zur Lizenz."""
        return next((s.get("edition", "") for s in self.inventory.get("systems") or []
                     if s.get("family") == "Windows" and s.get("edition")), "")

    @property
    def is_vm(self) -> bool:
        """VM des Tools: Einschalten/Ausschalten über libvirt statt Wake-on-LAN."""
        return bool(self.vm.get("name"))

    @property
    def hardware(self) -> str:
        d = self.inventory.get("dmi") or {}
        return " ".join(p for p in (d.get("sys_vendor"), d.get("product_name")) if p)


def identity(inv: dict, agent_id: str = "", mac: str = "", ambiguous: set[str] | frozenset = frozenset()) -> str:
    """Eindeutiger Schlüssel: System-UUID, sonst Hersteller+Seriennummer, sonst MAC.
    Platzhalter ab Werk und Kennungen, die schon an zwei Geräten gleichzeitig auftauchten, zählen nicht (B-001)."""
    d = (inv or {}).get("dmi") or {}
    uuid = "uuid:" + (d.get("product_uuid") or "").lower()
    if not placeholder_uuid(d.get("product_uuid") or "") and uuid not in ambiguous:
        return uuid
    sn = f"sn:{(d.get('sys_vendor') or '').lower()}:{(d.get('product_serial') or '').lower()}"
    if not placeholder_serial(d.get("product_serial") or "") and sn not in ambiguous:
        return sn
    macs = sorted(n["mac"].lower() for n in (inv or {}).get("network", []) if n.get("mac"))
    real = [m for m in macs if real_mac(m)]
    if real or macs:
        return "mac:" + (real or macs)[0]
    if mac:
        return "mac:" + mac.lower()
    return "agent:" + agent_id.lower() if agent_id else ""


def default_name(inv: dict, fallback: str = "") -> str:
    for s in (inv or {}).get("systems") or []:
        if textnorm.clean(s.get("hostname") or ""):
            return textnorm.clean(s["hostname"])  # Windows-Computername bzw. Linux-Hostname (ohne Steuerzeichen)
    d = (inv or {}).get("dmi") or {}
    hw = " ".join(p for p in (d.get("sys_vendor"), d.get("product_name")) if p)
    return textnorm.clean(hw or fallback) or "Unbekanntes Gerät"


class DeviceStore:
    def __init__(self, base: Path | None = None):
        self.base = Path(base or default_base())
        self.base.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.devices: dict[str, Device] = {}
        self.folders: list[str] = []
        self.ambiguous: set[str] = self._load_ambiguous()
        self.splits: list[str] = []        # Geräte, von denen ein zweites abgetrennt wurde (Inventar neu holen)
        self.load()

    def _load_ambiguous(self) -> set[str]:
        try:
            return {str(x) for x in json.loads((self.base / AMBIGUOUS_FILE).read_text())}
        except (OSError, ValueError, TypeError):
            return set()

    def _mark_ambiguous(self, ids: set[str]) -> None:
        new = {i for i in ids if i} - self.ambiguous
        if new:
            self.ambiguous |= new
            (self.base / AMBIGUOUS_FILE).write_text(json.dumps(sorted(self.ambiguous), indent=1))

    def _unique_disks(self, inv: dict | None) -> set[str]:
        return {d["serial"] for d in (inv or {}).get("disks", []) if d.get("serial")
                and not placeholder_serial(d["serial"]) and "disk:" + d["serial"] not in self.ambiguous}

    # ---------- Laden/Speichern ----------

    def load(self) -> None:
        with self.lock:
            # bekannte Geräte behalten ihr Objekt (offene Fenster, Aufträge) – nur der Ordner wird nachgeführt
            known, self.devices, self.folders = self.devices, {}, []

            def walk(path: Path, rel: str) -> None:
                for e in sorted(os.scandir(path), key=lambda e: e.name.lower()):
                    p = Path(e.path)
                    if e.is_dir(follow_symlinks=False) and len(PurePosixPath(rel).parts) < MAX_DEPTH:
                        sub = str(PurePosixPath(rel) / e.name) if rel else e.name
                        self.folders.append(sub)
                        walk(p, sub)
                    elif e.is_file(follow_symlinks=False) and e.name.endswith(".json"):
                        try:
                            data = json.loads(p.read_text())
                            fields = {k: v for k, v in data.items() if k in Device.__dataclass_fields__}
                            dev = Device(**fields)
                        except (OSError, ValueError, TypeError):
                            continue
                        dev = known.get(dev.id, dev)
                        dev.folder = rel
                        self.devices[dev.id] = dev
            walk(self.base, "")

    def _path(self, dev: Device) -> Path:
        folder = nasfiles.resolve(self.base, dev.folder) if dev.folder else self.base
        return folder / f"{dev.id}.json"

    def save(self, dev: Device) -> None:
        with self.lock:
            data = asdict(dev)
            data.pop("folder")
            path = self._path(dev)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            tmp.replace(path)

    # ---------- Erkennen/Erfassen ----------

    def match(self, agent_id: str = "", mac: str = "", inv: dict | None = None,
              online: dict[str, str] | None = None, conflicts: list | None = None) -> Device | None:
        """Bekanntes Gerät zu einem Agent finden. online = {Geräte-ID: Agent-ID} der gerade verbundenen Geräte:
        Ein Gerät, das gerade über einen anderen Agent verbunden ist, ist sicher ein anderes (B-001) – es landet
        in conflicts, und die gemeinsamen Kennungen gelten fortan als mehrdeutig."""
        with self.lock:
            key = identity(inv, agent_id, mac, self.ambiguous) if inv else ""
            serials = self._unique_disks(inv)
            macs = {n["mac"].lower() for n in (inv or {}).get("network", []) if real_mac(n.get("mac", ""))}
            if real_mac(mac):
                macs.add(mac.lower())
            strong = key.startswith(STRONG)
            online = online or {}

            def same(d: Device) -> bool:
                # nicht, wenn beide eine eigene UUID/Seriennummer haben – z. B. derselbe USB-Netzwerkadapter
                return not (strong and d.key.startswith(STRONG) and d.key != key)

            def busy(d: Device) -> bool:
                other = online.get(d.id)
                return bool(other) and other != agent_id

            for test in (lambda d: key and d.key == key and d.key not in self.ambiguous,
                         lambda d: agent_id and agent_id in d.agent_ids and same(d),
                         lambda d: macs & set(d.macs) and same(d),
                         lambda d: serials & set(d.disk_serials)):  # Board getauscht, Disk geblieben
                for dev in self.devices.values():
                    if not test(dev):
                        continue
                    if busy(dev):
                        if conflicts is not None and dev not in conflicts:
                            conflicts.append(dev)
                        shared = {"disk:" + s for s in serials & set(dev.disk_serials)}
                        if key and key == dev.key:
                            shared.add(key)
                        self._mark_ambiguous(shared)
                        continue
                    return dev
            return None

    def register(self, agent_id: str, ip: str, mac: str, inv: dict, fallback_name: str = "",
                 online: dict[str, str] | None = None) -> tuple[Device, bool]:
        """Gerät anlegen oder mit neuem Inventar aktualisieren. Gibt (Gerät, neu?) zurück.
        online wie bei match: verhindert, dass zwei gleichzeitig verbundene Geräte ein Eintrag werden."""
        with self.lock:
            conflicts: list[Device] = []
            dev = self.match(agent_id, mac, inv, online, conflicts)
            new = dev is None
            if new:
                name = default_name(inv, fallback_name)
                taken = {d.name for d in self.devices.values()}
                if name in taken:                       # baugleiche Geräte: „CompactPlayer 1 (2)“
                    n = 2
                    while f"{name} ({n})" in taken:
                        n += 1
                    name = f"{name} ({n})"
                dev = Device(id=secrets.token_hex(6), first_seen=now(), name=name)
                self.devices[dev.id] = dev
                for other in conflicts:
                    self._split(other, dev, agent_id, mac, inv)
            dev.key = identity(inv, agent_id, mac, self.ambiguous) or dev.key
            changed = bool(inv) and _content(inv) != _content(dev.inventory)
            dev.inventory = inv or dev.inventory
            dev.last_seen, dev.last_ip = now(), ip
            if agent_id and agent_id not in dev.agent_ids:
                dev.agent_ids.append(agent_id)
            for m in [n["mac"].lower() for n in (inv or {}).get("network", []) if n.get("mac")] + \
                     ([mac.lower()] if mac else []):
                if m not in dev.macs:
                    dev.macs.append(m)
            for s in [d["serial"] for d in (inv or {}).get("disks", []) if d.get("serial")]:
                if s not in dev.disk_serials:
                    dev.disk_serials.append(s)
            if new or changed:
                self.add_history(dev, "erfasst" if new else "inventar",
                                 ("Erstmals erfasst" if new else "Inventar aktualisiert")
                                 + (f" – {dev.os_name}" if dev.os_name else ""), save=False)
            self.save(dev)
            return dev, new

    def register_vm(self, name: str, inv: dict, profile: str = "", twin_of: str = "") -> Device:
        """Geräteeintrag für eine neue VM im Ordner „Virtuelle Maschinen“ mit Vor-Inventar aus dem Profil.
        Identität = SMBIOS-UUID der VM (auch als Agent-ID): Der Agent meldet beim ersten Start genau diese UUID,
        darum erkennt match() den Eintrag wieder, und es entsteht kein zweites Gerät. Netzwerkstart ist frei,
        „Netzwerkstart zuerst“ an (feste Startreihenfolge der VM). twin_of = Geräte-ID des Originals, wenn die VM
        ein digitaler Zwilling ist (I-001 Auftrag 3)."""
        with self.lock:
            uuid = ((inv.get("dmi") or {}).get("product_uuid") or "").lower()
            if not uuid:
                raise DeviceError("VM ohne UUID")
            if any(d.key == "uuid:" + uuid for d in self.devices.values()):
                raise DeviceError(f"Ein Gerät mit der UUID {uuid} gibt es schon")
            self.ensure_vm_folder()
            taken = {d.name for d in self.devices.values()}
            label, count = name, 2
            while label in taken:
                label, count = f"{name} ({count})", count + 1
            dev = Device(id=secrets.token_hex(6), key="uuid:" + uuid, name=label, first_seen=now(),
                         agent_ids=[uuid], inventory=inv, netboot=True, netfirst=True,
                         macs=[nic["mac"].lower() for nic in inv.get("network") or [] if nic.get("mac")],
                         disk_serials=[d["serial"] for d in inv.get("disks") or [] if d.get("serial")],
                         vm={"name": name, "profile": profile, **({"twin_of": twin_of} if twin_of else {})},
                         folder=VM_FOLDER)
            self.devices[dev.id] = dev
            what = f" (Profil {profile})" if profile else " (Zwilling)" if twin_of else ""
            self.add_history(dev, "erfasst", "Virtuelle Maschine angelegt" + what, save=False)
            self.save(dev)
            return dev

    def vm_devices(self) -> list[Device]:
        return sorted((d for d in self.devices.values() if d.is_vm), key=lambda d: d.name.lower())

    def vm_device(self, name: str) -> Device | None:
        return next((d for d in self.devices.values() if d.vm.get("name") == name), None)

    def ensure_vm_folder(self) -> None:
        path = self.base / VM_FOLDER
        if not path.is_dir():
            path.mkdir()
            self.load()

    def _split(self, other: Device, new: Device, agent_id: str, mac: str, inv: dict) -> None:
        """Früher fälschlich vereinten Eintrag bereinigen: Kennungen des neuen Geräts dort entfernen (B-001)."""
        mine_macs = {n["mac"].lower() for n in (inv or {}).get("network", []) if n.get("mac")}
        if mac:
            mine_macs.add(mac.lower())
        mine_disks = {d["serial"] for d in (inv or {}).get("disks", []) if d.get("serial")}
        other.macs = [m for m in other.macs if m not in mine_macs]
        other.agent_ids = [a for a in other.agent_ids if a != agent_id]
        other.disk_serials = [s for s in other.disk_serials if s not in mine_disks]
        if other.key in self.ambiguous or other.key in (identity(inv, agent_id, mac),
                                                         identity(inv, agent_id, mac, self.ambiguous)):
            other.key = identity(other.inventory, "", "", self.ambiguous)
            if other.key == identity(inv, agent_id, mac, self.ambiguous) or not other.key:   # Inventar war vom neuen
                real = sorted(m for m in other.macs if real_mac(m))
                other.key = "mac:" + real[0] if real else ""
        self._mark_ambiguous({"disk:" + s for s in mine_disks & set(other.disk_serials)})
        self.add_history(other, "getrennt", f"„{new.name}“ ist ein eigenes Gerät (gleiche Kennung ab Werk) – "
                                           "Einträge getrennt", save=False)
        self.save(other)
        self.splits.append(other.id)
        self.add_history(new, "getrennt", f"Von „{other.name}“ getrennt (gleiche Kennung ab Werk)", save=False)

    def add_history(self, dev: Device, kind: str, text: str, ok: bool | None = None, save: bool = True) -> None:
        with self.lock:
            dev.history.append({"time": now(), "kind": kind, "text": text, "ok": ok})
            del dev.history[:-MAX_HISTORY]
            if save:
                self.save(dev)

    def touch(self, dev: Device, ip: str, connected: bool) -> None:
        """Verbunden/getrennt: Zeitpunkt merken und im Verlauf eintragen."""
        with self.lock:
            dev.last_seen = now()
            if ip:
                dev.last_ip = ip
            self.add_history(dev, "verbunden" if connected else "getrennt",
                             f"Verbunden ({ip})" if connected else "Getrennt")

    def update(self, dev: Device, name: str | None = None, notes: str | None = None,
               product_key: str | None = None, netboot: bool | None = None) -> None:
        with self.lock:
            if netboot is not None:
                dev.netboot = bool(netboot)
            if name is not None and textnorm.clean(name):
                dev.name = textnorm.clean(name)          # NFC, ohne unsichtbare Steuerzeichen
            if notes is not None:
                dev.notes = notes
            if product_key is not None:
                dev.product_key = normalize_key(product_key)
            self.save(dev)

    def merge(self, keep: Device, other: Device) -> None:
        """Zwei Einträge desselben Geräts vereinen: keep behält ID, Name und Ordner, other verschwindet.
        Inventar und „zuletzt gesehen“ kommen vom zuletzt gesehenen Eintrag, Verlauf und Kennungen von beiden."""
        with self.lock:
            if keep.id == other.id:
                raise DeviceError("Ein Gerät kann nicht mit sich selbst zusammengeführt werden")
            if other.last_seen > keep.last_seen:
                keep.inventory = other.inventory or keep.inventory
                keep.last_seen, keep.last_ip = other.last_seen, other.last_ip or keep.last_ip
                keep.boot_status = other.boot_status or keep.boot_status
            if other.key.startswith(STRONG) and not keep.key.startswith(STRONG):
                keep.key = other.key
            keep.first_seen = min((t for t in (keep.first_seen, other.first_seen) if t), default="")
            for attr in ("agent_ids", "macs", "disk_serials"):
                values = getattr(keep, attr)
                values += [v for v in getattr(other, attr) if v not in values]
            if other.notes.strip() and other.notes.strip() not in keep.notes:
                keep.notes = f"{keep.notes.rstrip()}\n\n{other.notes.strip()}".strip()
            keep.product_key = keep.product_key or other.product_key
            keep.warranty = keep.warranty or other.warranty
            keep.bios = keep.bios if keep.bios.get("read", "") >= other.bios.get("read", "") else other.bios
            keep.hwtests = sorted(keep.hwtests + other.hwtests, key=lambda r: r.get("started", ""), reverse=True)[:10]
            keep.win11_unsupported = keep.win11_unsupported or other.win11_unsupported
            keep.vm = keep.vm or other.vm
            keep.netboot = keep.netboot or other.netboot
            keep.boot_request = keep.boot_request or other.boot_request
            if other.netfirst and not keep.netfirst:
                keep.netfirst, keep.boot_saved = True, other.boot_saved
            keep.history = sorted(keep.history + other.history, key=lambda h: str(h.get("time", "")))
            self.add_history(keep, "zusammengeführt", f"Mit „{other.name}“ zusammengeführt", save=False)
            self._path(other).unlink(missing_ok=True)
            self.devices.pop(other.id, None)
            self.save(keep)

    def duplicates(self) -> list[tuple[Device, Device]]:
        """Einträge, die sicher dasselbe Gerät sind: gleiche Board-UUID/Seriennummer oder gleiche Agent-ID
        (= Board-UUID). Paare (behalten, auflösen): einsortiert vor „Neu“, sonst der zuerst erfasste."""
        def usable(key: str) -> bool:
            if key in self.ambiguous:
                return False
            if key.startswith("uuid:"):
                return not placeholder_uuid(key[5:])
            if key.startswith("sn:"):
                return not placeholder_serial(key.split(":", 2)[2] if key.count(":") >= 2 else "")
            return True

        def same(a: Device, b: Device) -> bool:
            if a.key.startswith(STRONG) and b.key.startswith(STRONG):
                return a.key == b.key and usable(a.key)
            return any(UUID_RE.match(x) and not placeholder_uuid(x) and "uuid:" + x.lower() not in self.ambiguous
                       for x in set(a.agent_ids) & set(b.agent_ids))

        with self.lock:
            devs = sorted(self.devices.values(), key=lambda d: (not d.folder, d.first_seen or "~", d.id))
            pairs, gone = [], set()
            for i, a in enumerate(devs):
                if a.id in gone:
                    continue
                for b in devs[i + 1:]:
                    if b.id not in gone and same(a, b):
                        pairs.append((a, b))
                        gone.add(b.id)
            return pairs

    def merge_duplicates(self) -> list[str]:
        """Doppelte Einträge (z. B. nach einem Import) zusammenführen; gibt die Namen der behaltenen zurück."""
        with self.lock:
            merged = []
            for keep, other in self.duplicates():
                self.merge(keep, other)
                merged.append(keep.name)
            return merged

    def delete(self, dev: Device) -> None:
        with self.lock:
            self._path(dev).unlink(missing_ok=True)
            self.devices.pop(dev.id, None)

    # ---------- Ordner ----------

    def _folder(self, rel: str) -> Path:
        if len(PurePosixPath(rel).parts) > MAX_DEPTH:
            raise DeviceError(f"Mehr als {MAX_DEPTH} Ebenen sind nicht möglich")
        return nasfiles.resolve(self.base, rel) if rel else self.base

    @staticmethod
    def _vm_rel(rel: str) -> bool:
        """Liegt rel im Ordner „Virtuelle Maschinen“ (oder ist es der Ordner selbst)?"""
        return rel == VM_FOLDER or rel.startswith(VM_FOLDER + "/")

    def make_folder(self, parent: str, name: str) -> str:
        if self._vm_rel(parent):
            raise DeviceError(f"Im Ordner „{VM_FOLDER}“ sind keine Unterordner möglich")
        rel = str(PurePosixPath(parent) / nasfiles.validate_name(name, new=True)) if parent \
            else nasfiles.validate_name(name, new=True)
        if rel.lower() == VM_FOLDER.lower():
            raise DeviceError(f"„{VM_FOLDER}“ ist für die VMs des Tools reserviert")
        path = self._folder(rel)
        if nasfiles.name_taken(path):
            raise DeviceError(f"„{path.name}“ existiert bereits")
        path.mkdir()
        self.load()
        return rel

    def rename_folder(self, rel: str, new_name: str) -> str:
        if self._vm_rel(rel):
            raise DeviceError(f"Der Ordner „{VM_FOLDER}“ lässt sich nicht umbenennen")
        if not ("/" in rel) and new_name.strip().lower() == VM_FOLDER.lower():
            raise DeviceError(f"„{VM_FOLDER}“ ist für die VMs des Tools reserviert")
        src = self._folder(rel)
        parent = str(PurePosixPath(rel).parent)
        new_rel = str(PurePosixPath(parent) / nasfiles.validate_name(new_name, new=True)) if parent != "." \
            else nasfiles.validate_name(new_name, new=True)
        dst = self._folder(new_rel)
        if not rel or not src.is_dir():
            raise DeviceError("Ordner nicht gefunden")
        if nasfiles.name_taken(dst, ignore=src):
            raise DeviceError(f"„{dst.name}“ existiert bereits")
        with self.lock:
            src.rename(dst)
            self.load()
        return new_rel

    def delete_folder(self, rel: str) -> None:
        if self._vm_rel(rel):
            raise DeviceError(f"Der Ordner „{VM_FOLDER}“ lässt sich nicht löschen")
        path = self._folder(rel)
        if not rel or not path.is_dir():
            raise DeviceError("Ordner nicht gefunden")
        if any(path.iterdir()):
            raise DeviceError(f"„{path.name}“ ist nicht leer – zuerst Geräte und Unterordner verschieben")
        path.rmdir()
        self.load()

    def move_device(self, dev: Device, folder: str) -> None:
        if dev.is_vm and folder != VM_FOLDER:
            raise DeviceError(f"VMs bleiben im Ordner „{VM_FOLDER}“")
        if not dev.is_vm and self._vm_rel(folder):
            raise DeviceError(f"Im Ordner „{VM_FOLDER}“ stehen nur die VMs des Tools")
        with self.lock:
            target = self._folder(folder)
            if folder and not target.is_dir():
                raise DeviceError("Zielordner nicht gefunden")
            src = self._path(dev)
            dev.folder = folder
            src.rename(self._path(dev))

    def move_folder(self, rel: str, dest: str) -> str:
        if self._vm_rel(rel):
            raise DeviceError(f"Der Ordner „{VM_FOLDER}“ lässt sich nicht verschieben")
        if self._vm_rel(dest):
            raise DeviceError(f"Im Ordner „{VM_FOLDER}“ sind keine Unterordner möglich")
        src = self._folder(rel)
        if not rel or not src.is_dir():
            raise DeviceError("Ordner nicht gefunden")
        if dest == rel or dest.startswith(rel + "/"):
            raise DeviceError("Ein Ordner kann nicht in sich selbst verschoben werden")
        height = 1 + max((len(PurePosixPath(f).parts) - len(PurePosixPath(rel).parts)
                          for f in self.folders if f.startswith(rel + "/")), default=0)
        if (len(PurePosixPath(dest).parts) if dest else 0) + height > MAX_DEPTH:
            raise DeviceError(f"Mehr als {MAX_DEPTH} Ebenen sind nicht möglich")
        target = self._folder(dest) / src.name
        if target.exists():
            raise DeviceError(f"„{src.name}“ existiert im Ziel bereits")
        with self.lock:
            shutil.move(str(src), str(target))
            self.load()
        return str(PurePosixPath(dest) / src.name) if dest else src.name

    def in_folder(self, rel: str) -> list[Device]:
        return sorted((d for d in self.devices.values() if d.folder == rel), key=lambda d: d.name.lower())


def _content(inv: dict) -> dict:
    """Inventar ohne Zeitstempel – zum Vergleichen, ob sich etwas geändert hat."""
    return {k: v for k, v in (inv or {}).items() if k != "collected"}


def normalize_key(key: str) -> str:
    """„xxxxx xxxxx …“ → „XXXXX-XXXXX-XXXXX-XXXXX-XXXXX“; leer = löschen. Ungültig → DeviceError."""
    raw = "".join(c for c in key.upper() if c.isalnum())
    if not raw:
        return ""
    if len(raw) != 25:
        raise DeviceError("Windows-Schlüssel hat 25 Zeichen (5 × 5, mit Bindestrichen)")
    return "-".join(raw[i:i + 5] for i in range(0, 25, 5))


def mask_key(key: str) -> str:
    return f"XXXXX-XXXXX-XXXXX-XXXXX-{key[-5:]}" if key else ""


def short_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return ""


def boot_mode(dev: Device) -> str:
    """Startart beim Netzwerkstart: always (F12 → Netzwerk = Agent), local (Netzwerk zuerst, ohne Auftrag von der
    Festplatte), once (Netzwerk zuerst, beim nächsten Start einmal der Agent)."""
    if not dev.netfirst:
        return "always"
    return "once" if dev.boot_request else "local"


def netboot_modes(store_devices) -> dict[str, str]:
    """{MAC: Startart} aller freigeschalteten Geräte (nur Kabel-Netzwerkkarten)."""
    modes = {}
    for dev in store_devices:
        if dev.netboot:
            for mac in netboot_macs([dev]):
                modes[mac] = boot_mode(dev)
    return dict(sorted(modes.items()))


def nic_kind(nic: dict) -> str:
    """„WLAN“, „Mobilfunk“ (wwan…) oder „Kabel“."""
    if nic.get("wireless"):
        return "WLAN"
    return "Mobilfunk" if str(nic.get("name", "")).startswith("ww") else "Kabel"


def netboot_macs(store_devices) -> list[str]:
    """MAC-Adressen aller für den Netzwerkstart freigeschalteten Geräte: Kabel-Karten aus dem Inventar (auch VMs mit
    lokal vergebener MAC) und früher gesehene feste MACs. WLAN und Mobilfunk können kein PXE/Wake-on-LAN."""
    macs = set()
    for dev in store_devices:
        if not dev.netboot:
            continue
        nics = [n for n in (dev.inventory.get("network") or []) if n.get("mac")]
        cable = {n["mac"].lower() for n in nics if nic_kind(n) == "Kabel"}     # aktuelle Kabel-Karten: immer
        listed = {n["mac"].lower() for n in nics}
        # früher gesehene MACs ohne Karte im Inventar nur, wenn fest (zufällige MACs ändern sich)
        macs |= {m.lower() for m in dev.macs if m.lower() in cable or (m.lower() not in listed and real_mac(m))}
    return sorted(macs)


def bios_mode(dev: "Device") -> bool:
    """Startet das Gerät im BIOS-Modus (Legacy)? Laut Inventar (bei jedem Start neu), sonst letzte Prüfung der
    Startreihenfolge. Nach dem Umstellen im BIOS auf UEFI stimmt es nach dem nächsten Start wieder."""
    uefi = (dev.inventory.get("platform") or {}).get("uefi")
    if uefi is not None:
        return uefi is False
    return (dev.boot_status or {}).get("uefi") is False
