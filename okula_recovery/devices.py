"""Geräteverwaltung im Tool: erfasste Geräte, Wiedererkennung, Ordner, Verlauf, Notizen.

Ablage lokal auf dem Server (XDG_DATA_HOME, Standard ~/.local/share/okula-recovery/geraete):
    geraete/<Geräte-ID>.json                       → „Neu / nicht einsortiert“
    geraete/Kunde A/Standort Zürich/<ID>.json      → einsortiert (max. 3 Ordnerebenen)
Die Datei heisst nach der ID, damit Umbenennen nur den Anzeigenamen ändert.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from okula_recovery import nasfiles

MAX_DEPTH = 3
MAX_HISTORY = 500
STRONG = ("uuid:", "sn:")  # eindeutige Schlüssel; MAC/Disk sind nur Hinweise


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
    history: list[dict] = field(default_factory=list)
    folder: str = ""                   # nicht gespeichert: ergibt sich aus dem Ablageort

    @property
    def os_name(self) -> str:
        systems = self.inventory.get("systems") or []
        return systems[0]["name"] if systems else ""

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
        if s.get("hostname"):
            return s["hostname"]  # Windows-Computername bzw. Linux-Hostname
    d = (inv or {}).get("dmi") or {}
    hw = " ".join(p for p in (d.get("sys_vendor"), d.get("product_name")) if p)
    return hw or fallback or "Unbekanntes Gerät"


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

    def update(self, dev: Device, name: str | None = None, notes: str | None = None) -> None:
        with self.lock:
            if name is not None and name.strip():
                dev.name = name.strip()
            if notes is not None:
                dev.notes = notes
            self.save(dev)

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
        rel = str(PurePosixPath(parent) / nasfiles.validate_name(name)) if parent else nasfiles.validate_name(name)
        path = self._folder(rel)
        if path.exists():
            raise DeviceError(f"„{path.name}“ existiert bereits")
        path.mkdir()
        self.load()
        return rel

    def rename_folder(self, rel: str, new_name: str) -> str:
        src = self._folder(rel)
        parent = str(PurePosixPath(rel).parent)
        new_rel = str(PurePosixPath(parent) / nasfiles.validate_name(new_name)) if parent != "." \
            else nasfiles.validate_name(new_name)
        dst = self._folder(new_rel)
        if not rel or not src.is_dir():
            raise DeviceError("Ordner nicht gefunden")
        if dst.exists():
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


def short_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return ""
