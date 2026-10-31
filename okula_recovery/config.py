"""Persistente Einstellungen (JSON unter ~/.config/okula-recovery/config.json)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "okula-recovery" / "config.json"


@dataclass
class NasConfig:
    protocol: str = "smb"  # "smb" oder "nfs"
    host: str = ""
    share: str = ""
    mount_point: str = "/mnt/okula-nas"
    username: str = ""  # Passwort nur in /etc/okula-recovery/nas.cred (root)
    web_scheme: str = "https"  # Weboberfläche des NAS (z. B. Synology DSM)
    web_port: int = 5001       # DSM: https 5001, http 5000


@dataclass
class Config:
    nas: NasConfig = field(default_factory=NasConfig)
    # Manuell hinzugefügte Maschinen: Liste von {"name": ..., "ip": ...}
    machines: list[dict] = field(default_factory=list)
    scan_network: str = ""  # leer = automatisch aus eigener Schnittstelle
    automation_max: int = 2         # höchstens so viele Automatisierungen gleichzeitig
    automation_paused: bool = False  # Hauptschalter: alle Automatisierungen angehalten


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return Config()
    nas = NasConfig(**{k: v for k, v in data.get("nas", {}).items() if k in NasConfig.__dataclass_fields__})
    return Config(
        nas=nas,
        machines=list(data.get("machines", [])),
        scan_network=data.get("scan_network", ""),
        automation_max=max(1, min(10, int(data.get("automation_max") or 2))),
        automation_paused=bool(data.get("automation_paused", False)),
    )


def save(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False))
    tmp.replace(path)
