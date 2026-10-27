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


@dataclass
class Config:
    nas: NasConfig = field(default_factory=NasConfig)
    # Manuell hinzugefügte Maschinen: Liste von {"name": ..., "ip": ...}
    machines: list[dict] = field(default_factory=list)
    scan_network: str = ""  # leer = automatisch aus eigener Schnittstelle


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
    )


def save(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False))
    tmp.replace(path)
