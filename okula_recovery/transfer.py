"""Einstellungen exportieren/importieren – für den Umzug des Tools auf einen anderen Rechner.

NAS-Export (NAS-Fenster): kleine JSON-Datei mit Protokoll, Host, Freigabe, Benutzer, Einhängepunkt.
Gesamt-Export (Menü): ZIP-Datei mit
    manifest.json        Art, Datum, Quellrechner, Inhalt
    config.json          Einstellungen (NAS, Maschinen, Netz, Automatisierung)
    automatisierung-vorlagen.json   Vorlagen der Automatisierung
    agent.key            Schlüssel der Agent-/Restore-Sticks (optional; ohne ihn alle Sticks neu erstellen)
    geraete/…            Geräteverzeichnis mit Ordnern, Verlauf, Notizen, Windows-Schlüsseln
Nicht enthalten: Images, Backups, ISOs (liegen auf dem NAS), NAS-Passwort (nur root lesbar, wird nach dem
Import einmal eingegeben), heruntergeladene Debian-ISOs (Cache).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from okula_recovery import __version__, agentclient, config, devices, wire

NAS_FORMAT = "okula-nas"
EXPORT_FORMAT = "okula-export"
VERSION = 1
MAX_FILE = 16 * 1024 * 1024        # einzelne Datei im Archiv (Geräte-JSON mit Inventar und Verlauf)
MAX_FILES = 20000


class TransferError(Exception):
    pass


def _write_private(path: Path, data: bytes) -> None:
    """Datei nur für den Benutzer lesbar anlegen (enthält Schlüssel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def default_name(kind: str) -> str:
    host = "".join(c if c.isalnum() or c in "-_" else "_" for c in socket.gethostname()) or "server"
    stamp = time.strftime("%Y-%m-%d")
    return f"okula-nas-{host}-{stamp}.json" if kind == "nas" else f"okula-recovery-{host}-{stamp}.okula.zip"


# ---------- NAS ----------

def nas_to_dict(nas: config.NasConfig) -> dict:
    return {"format": NAS_FORMAT, "version": VERSION, "created": datetime.now().isoformat(timespec="seconds"),
            "source": socket.gethostname(), "nas": asdict(nas)}


def export_nas(nas: config.NasConfig, path: str | Path) -> None:
    _write_private(Path(path), json.dumps(nas_to_dict(nas), indent=2, ensure_ascii=False).encode())


def _nas_from(data: dict) -> config.NasConfig:
    raw = data.get("nas") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        raise TransferError("Keine NAS-Einstellungen in der Datei")
    fields = {k: str(v) for k, v in raw.items() if k in config.NasConfig.__dataclass_fields__ and v is not None}
    try:
        fields["web_port"] = int(fields.get("web_port") or 0) or config.NasConfig.web_port
    except ValueError:
        fields.pop("web_port")
    nas = config.NasConfig(**fields)
    if nas.protocol not in ("smb", "nfs"):
        raise TransferError(f"Unbekanntes Protokoll: {nas.protocol}")
    if not nas.mount_point.startswith("/"):
        raise TransferError("Einhängepunkt muss ein absoluter Pfad sein")
    return nas


def read_nas(path: str | Path) -> config.NasConfig:
    """NAS-Einstellungen aus einem NAS-Export (.json) oder einem Gesamt-Export (.zip)."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        return _nas_from(read_export(path).config)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise TransferError(f"Datei nicht lesbar: {e}") from None
    if data.get("format") != NAS_FORMAT:
        raise TransferError("Keine Okula-NAS-Exportdatei")
    return _nas_from(data)


# ---------- Gesamt ----------

def _device_files(base: Path) -> list[tuple[str, Path]]:
    """(relativer Pfad, Datei) aller Geräte-JSONs, Ordner bis MAX_DEPTH; Links werden nicht verfolgt."""
    out = []
    if not base.is_dir():
        return out
    for root, dirs, files in os.walk(base, followlinks=False):
        rel_root = Path(root).relative_to(base)
        if len(rel_root.parts) >= devices.MAX_DEPTH:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for name in files:
            p = Path(root) / name
            if name.endswith(".json") and not p.is_symlink():
                out.append(((rel_root / name).as_posix(), p))
    return sorted(out)


def _device_folders(base: Path) -> list[str]:
    """Auch leere Ordner mitnehmen (Struktur bleibt erhalten)."""
    out = []
    for root, dirs, _files in os.walk(base, followlinks=False):
        rel_root = Path(root).relative_to(base)
        if len(rel_root.parts) >= devices.MAX_DEPTH:
            dirs[:] = []
            continue
        for d in dirs:
            if not (Path(root) / d).is_symlink():
                out.append((rel_root / d).as_posix())
    return sorted(out)


def summary_counts(base: Path | None = None) -> dict:
    base = Path(base or devices.default_base())
    return {"devices": len(_device_files(base)), "folders": len(_device_folders(base))}


def export_all(path: str | Path, include_key: bool = True, include_devices: bool = True,
               include_config: bool = True) -> dict:
    """Gesamt-Export schreiben; gibt das Manifest zurück."""
    key_path, base = agentclient.key_path(), devices.default_base()
    contents: list[str] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = {"format": EXPORT_FORMAT, "version": VERSION, "created": datetime.now().isoformat(timespec="seconds"),
                    "source": socket.gethostname(), "tool_version": __version__}
        if include_config:
            z.writestr("config.json", json.dumps(asdict(config.load()), indent=2, ensure_ascii=False))
            contents.append("config")
            from okula_recovery import automation
            templates = automation.load_templates()
            if templates:
                z.writestr("automatisierung-vorlagen.json", json.dumps(templates, indent=2, ensure_ascii=False))
                manifest["templates"] = len(templates)
        if include_key and key_path.is_file():
            z.writestr("agent.key", key_path.read_text().strip() + "\n")
            contents.append("agent_key")
        if include_devices:
            for folder in _device_folders(base):
                z.writestr(f"geraete/{folder}/", "")
            files = _device_files(base)
            for rel, p in files:
                z.write(p, f"geraete/{rel}")
            manifest["devices"] = len(files)
            contents.append("devices")
        manifest["contents"] = contents
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    _write_private(Path(path), buf.getvalue())
    return manifest


@dataclass
class ExportFile:
    manifest: dict
    config: dict = field(default_factory=dict)
    key: bytes | None = None
    device_files: dict[str, bytes] = field(default_factory=dict)   # rel → Inhalt
    folders: list[str] = field(default_factory=list)
    templates: dict[str, dict] = field(default_factory=dict)   # Vorlagen der Automatisierung

    def describe(self) -> list[str]:
        m = self.manifest
        lines = [f"Erstellt: {m.get('created', '?').replace('T', ' ')} auf „{m.get('source', '?')}“"
                 f" (Tool {m.get('tool_version', '?')})"]
        nas = self.config.get("nas") or {}
        if self.config:
            where = f"{nas.get('host', '')}/{str(nas.get('share', '')).strip('/')}" if nas.get("host") else "–"
            lines.append(f"NAS-Einstellungen: {where} ({str(nas.get('protocol', '')).upper()})")
        if self.key is not None:
            lines.append("Agent-Schlüssel: enthalten (bestehende Agent- und Restore-Sticks funktionieren weiter)")
        if self.device_files or self.folders:
            lines.append(f"Geräte: {len(self.device_files)} (in {len(self.folders)} Ordnern)")
        if self.templates:
            lines.append(f"Vorlagen der Automatisierung: {', '.join(sorted(self.templates))}")
        return lines


def _safe_rel(name: str) -> str:
    """Pfad unter geraete/ prüfen: keine absoluten Pfade, kein .., höchstens MAX_DEPTH Ordner."""
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in ("", ".", "..") or "\\" in part for part in p.parts):
        raise TransferError(f"Ungültiger Pfad in der Datei: {name}")
    return p.as_posix()


def read_export(path: str | Path) -> ExportFile:
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        raise TransferError(f"Keine gültige Exportdatei: {e}") from None
    with z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise TransferError("Exportdatei enthält zu viele Einträge")

        def read(name: str) -> bytes:
            info = z.getinfo(name)
            if info.file_size > MAX_FILE:
                raise TransferError(f"{name} ist zu gross")
            return z.read(info)

        names = {i.filename for i in infos}
        if "manifest.json" not in names:
            raise TransferError("Keine Okula-Exportdatei (manifest.json fehlt)")
        try:
            manifest = json.loads(read("manifest.json"))
        except ValueError:
            raise TransferError("manifest.json ist beschädigt") from None
        if manifest.get("format") != EXPORT_FORMAT:
            raise TransferError("Keine Okula-Exportdatei")
        if int(manifest.get("version") or 0) > VERSION:
            raise TransferError("Exportdatei stammt von einer neueren Tool-Version – Tool zuerst aktualisieren")
        result = ExportFile(manifest)
        if "config.json" in names:
            try:
                result.config = json.loads(read("config.json"))
            except ValueError:
                raise TransferError("config.json ist beschädigt") from None
        if "automatisierung-vorlagen.json" in names:
            try:
                data = json.loads(read("automatisierung-vorlagen.json"))
            except ValueError:
                raise TransferError("automatisierung-vorlagen.json ist beschädigt") from None
            if not isinstance(data, dict):
                raise TransferError("automatisierung-vorlagen.json ist beschädigt")
            result.templates = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        if "agent.key" in names:
            try:
                key = bytes.fromhex(read("agent.key").decode().strip())
            except ValueError:
                raise TransferError("agent.key ist beschädigt") from None
            if len(key) != wire.KEY_LEN:
                raise TransferError("agent.key hat die falsche Länge")
            result.key = key
        for info in infos:
            if not info.filename.startswith("geraete/") or info.filename == "geraete/":
                continue
            rel = _safe_rel(info.filename[len("geraete/"):].rstrip("/"))
            parts = PurePosixPath(rel).parts
            if info.is_dir():
                if len(parts) > devices.MAX_DEPTH:
                    raise TransferError(f"Zu tief verschachtelter Ordner: {rel}")
                result.folders.append(rel)
                continue
            if not rel.endswith(".json") or len(parts) - 1 > devices.MAX_DEPTH:
                raise TransferError(f"Unerwartete Datei: {info.filename}")
            data = read(info.filename)
            try:
                dev = json.loads(data)
            except ValueError:
                raise TransferError(f"{info.filename} ist beschädigt") from None
            if not isinstance(dev, dict) or not dev.get("id") or PurePosixPath(rel).stem != dev["id"]:
                raise TransferError(f"{info.filename} ist kein Gerät")
            result.device_files[rel] = data
        return result


@dataclass
class ImportResult:
    config: bool = False
    key: str = ""                 # "", "gleich", "ersetzt", "neu"
    added: int = 0
    updated: int = 0
    kept: int = 0                 # vorhandenes Gerät war neuer
    merged: list[str] = field(default_factory=list)   # doppelt (gleiche Hardware, andere ID) → zusammengeführt
    backup_dir: str = ""

    def lines(self) -> list[str]:
        out = []
        if self.config:
            out.append("NAS-Einstellungen übernommen")
        if self.key:
            out.append({"gleich": "Agent-Schlüssel war schon gleich", "ersetzt": "Agent-Schlüssel ersetzt",
                        "neu": "Agent-Schlüssel übernommen"}[self.key])
        if self.added or self.updated or self.kept:
            out.append(f"Geräte: {self.added} neu, {self.updated} aktualisiert"
                       + (f", {self.kept} vorhandene waren neuer und bleiben" if self.kept else ""))
        if self.merged:
            out.append(f"Doppelt erfasst und zusammengeführt: {', '.join(self.merged)}")
        if self.backup_dir:
            out.append(f"Bisherige Daten gesichert in {self.backup_dir}")
        return out


def _existing_devices(base: Path) -> dict[str, Path]:
    return {Path(rel).stem: p for rel, p in _device_files(base)}


def import_all(export: ExportFile, use_config: bool = True, use_key: bool = True,
               use_devices: bool = True) -> ImportResult:
    """Übernehmen. Vorher wird alles, was überschrieben werden könnte, in einen Sicherungsordner kopiert.
    Geräte werden zusammengeführt: gleiche ID → das zuletzt gesehene gewinnt, sonst neu dazu."""
    result = ImportResult()
    cfg_path, key_path, base = config.config_path(), agentclient.key_path(), devices.default_base()
    backup = cfg_path.parent / "import-sicherung" / time.strftime("%Y-%m-%d_%H%M%S")

    def save_old(src: Path, rel: str) -> None:
        if src.exists():
            dst = backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
            result.backup_dir = str(backup)

    if use_config and export.config:
        save_old(cfg_path, "config.json")
        old = config.load()
        new = export.config
        old.nas = _nas_from(new)
        old.machines = list(new.get("machines") or old.machines)
        old.scan_network = str(new.get("scan_network") or old.scan_network)
        try:
            old.automation_max = max(1, min(10, int(new.get("automation_max") or old.automation_max)))
        except (TypeError, ValueError):
            pass
        config.save(old)
        result.config = True
        if export.templates:
            from okula_recovery import automation
            path = automation.templates_path()
            save_old(path, path.name)
            merged = {**automation.load_templates(), **{k: {f: v[f] for f in automation.TEMPLATE_FIELDS if f in v}
                                                        for k, v in export.templates.items()}}
            automation._save_templates(merged)
    if use_key and export.key is not None:
        current = None
        try:
            current = bytes.fromhex(key_path.read_text().strip())
        except (OSError, ValueError):
            pass
        if current == export.key:
            result.key = "gleich"
        else:
            save_old(key_path, "agent.key")
            _write_private(key_path, export.key.hex().encode() + b"\n")
            result.key = "ersetzt" if current else "neu"
    if use_devices and (export.device_files or export.folders):
        save_old(base, "geraete")
        existing = _existing_devices(base)
        for folder in export.folders:
            (base / folder).mkdir(parents=True, exist_ok=True)
        for rel, data in export.device_files.items():
            dev_id = PurePosixPath(rel).stem
            new = json.loads(data)
            old_path = existing.get(dev_id)
            if old_path is not None:
                try:
                    old = json.loads(old_path.read_text())
                except (OSError, ValueError):
                    old = {}
                if str(old.get("last_seen") or "") > str(new.get("last_seen") or ""):
                    result.kept += 1
                    continue
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
            if old_path is not None and old_path.resolve() != target.resolve():
                old_path.unlink(missing_ok=True)   # Gerät liegt jetzt im Ordner aus dem Export
            if old_path is None:
                result.added += 1
            else:
                result.updated += 1
        # dasselbe Gerät schon hier erfasst (andere ID, z. B. vor dem Import mit dem Stick gestartet)
        result.merged = devices.DeviceStore(base).merge_duplicates()
    return result
