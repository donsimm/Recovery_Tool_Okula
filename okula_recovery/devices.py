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
    win11_unsupported: str = ""        # Datum: Windows 11 trotz „nicht tauglich“ installiert (keine Update-Garantie)
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
    def hardware(self) -> str:
        d = self.inventory.get("dmi") or {}
        return " ".join(p for p in (d.get("sys_vendor"), d.get("product_name")) if p)


def identity(inv: dict, agent_id: str = "", mac: str = "") -> str:
    """Eindeutiger Schlüssel: System-UUID, sonst Hersteller+Seriennummer, sonst MAC."""
    d = (inv or {}).get("dmi") or {}
    if d.get("product_uuid"):
        return "uuid:" + d["product_uuid"].lower()
    if d.get("product_serial"):
        return f"sn:{d.get('sys_vendor', '').lower()}:{d['product_serial'].lower()}"
    macs = sorted(n["mac"].lower() for n in (inv or {}).get("network", []) if n.get("mac"))
    if macs:
        return "mac:" + macs[0]
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
        self.load()

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

    def match(self, agent_id: str = "", mac: str = "", inv: dict | None = None) -> Device | None:
        with self.lock:
            key = identity(inv, agent_id, mac) if inv else ""
            serials = {d.get("serial") for d in (inv or {}).get("disks", []) if d.get("serial")}
            macs = {n["mac"].lower() for n in (inv or {}).get("network", []) if n.get("mac")}
            if mac:
                macs.add(mac.lower())
            strong = key.startswith(STRONG)

            def same(d: Device) -> bool:
                # nicht, wenn beide eine eigene UUID/Seriennummer haben – z. B. derselbe USB-Netzwerkadapter
                # oder eine Dummy-UUID an zwei Geräten
                return not (strong and d.key.startswith(STRONG) and d.key != key)

            for test in (lambda d: key and d.key == key,
                         lambda d: agent_id and agent_id in d.agent_ids and same(d),
                         lambda d: macs & set(d.macs) and same(d),
                         lambda d: serials & set(d.disk_serials)):  # Board getauscht, Disk geblieben
                for dev in self.devices.values():
                    if test(dev):
                        return dev
            return None

    def register(self, agent_id: str, ip: str, mac: str, inv: dict, fallback_name: str = "") -> tuple[Device, bool]:
        """Gerät anlegen oder mit neuem Inventar aktualisieren. Gibt (Gerät, neu?) zurück."""
        with self.lock:
            dev = self.match(agent_id, mac, inv)
            new = dev is None
            if new:
                dev = Device(id=secrets.token_hex(6), first_seen=now(), name=default_name(inv, fallback_name))
                self.devices[dev.id] = dev
            dev.key = identity(inv, agent_id, mac) or dev.key
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
            keep.win11_unsupported = keep.win11_unsupported or other.win11_unsupported
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
        def same(a: Device, b: Device) -> bool:
            if a.key.startswith(STRONG) and b.key.startswith(STRONG):
                return a.key == b.key
            return any(UUID_RE.match(x) for x in set(a.agent_ids) & set(b.agent_ids))

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

    def make_folder(self, parent: str, name: str) -> str:
        rel = str(PurePosixPath(parent) / nasfiles.validate_name(name, new=True)) if parent \
            else nasfiles.validate_name(name, new=True)
        path = self._folder(rel)
        if nasfiles.name_taken(path):
            raise DeviceError(f"„{path.name}“ existiert bereits")
        path.mkdir()
        self.load()
        return rel

    def rename_folder(self, rel: str, new_name: str) -> str:
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
        path = self._folder(rel)
        if not rel or not path.is_dir():
            raise DeviceError("Ordner nicht gefunden")
        if any(path.iterdir()):
            raise DeviceError(f"„{path.name}“ ist nicht leer – zuerst Geräte und Unterordner verschieben")
        path.rmdir()
        self.load()

    def move_device(self, dev: Device, folder: str) -> None:
        with self.lock:
            target = self._folder(folder)
            if folder and not target.is_dir():
                raise DeviceError("Zielordner nicht gefunden")
            src = self._path(dev)
            dev.folder = folder
            src.rename(self._path(dev))

    def move_folder(self, rel: str, dest: str) -> str:
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
        raise DeviceError("Produktschlüssel hat 25 Zeichen (5 × 5, mit Bindestrichen)")
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


def netboot_macs(store_devices) -> list[str]:
    """MAC-Adressen aller für den Netzwerkstart freigeschalteten Geräte (kabelgebundene zuerst; WLAN kann kein PXE)."""
    macs = set()
    for dev in store_devices:
        if not dev.netboot:
            continue
        wireless = {n["mac"].lower() for n in (dev.inventory.get("network") or []) if n.get("wireless") and n.get("mac")}
        macs |= {m.lower() for m in dev.macs if m and m.lower() not in wireless}
    return sorted(macs)
