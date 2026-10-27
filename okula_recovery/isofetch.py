"""Debian-Live-ISO (Variante „standard“) herunterladen und per SHA512SUMS prüfen."""

from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from pathlib import Path
from typing import Callable

BASE_URL = os.environ.get("OKULA_DEBIAN_LIVE_URL",
                          "https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/")
FLAVOUR = "standard"

Progress = Callable[[float, str], None]


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "okula-recovery" / "iso"


def parse_sums(text: str, flavour: str = FLAVOUR) -> tuple[str, str]:
    pattern = re.compile(rf"^debian-live-[\d.]+-amd64-{re.escape(flavour)}\.iso$")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and pattern.match(parts[1].lstrip("*")):
            return parts[1].lstrip("*"), parts[0].lower()
    raise ValueError(f"Kein debian-live-…-amd64-{flavour}.iso in SHA512SUMS")


def sha512_file(path: Path) -> str:
    h = hashlib.sha512()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def cached_isos() -> list[Path]:
    d = cache_dir()
    return sorted(d.glob("debian-live-*.iso"), reverse=True) if d.is_dir() else []


def fetch(progress: Progress, base_url: str = BASE_URL, dest: Path | None = None) -> Path:
    dest = dest or cache_dir()
    dest.mkdir(parents=True, exist_ok=True)
    progress(0.0, "Lade Prüfsummen")
    with urllib.request.urlopen(base_url + "SHA512SUMS", timeout=30) as r:
        name, digest = parse_sums(r.read().decode())

    target = dest / name
    if target.is_file():
        progress(0.0, f"Prüfe vorhandenes {name}")
        if sha512_file(target) == digest:
            progress(1.0, f"{name} ist aktuell")
            return target

    part = target.with_suffix(".iso.part")
    with urllib.request.urlopen(base_url + name, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1024 * 1024):
            f.write(chunk)
            done += len(chunk)
            if total:
                progress(done / total * 0.95, f"Lade {name}: {done // 2**20} / {total // 2**20} MiB")
    progress(0.96, "Prüfe SHA512")
    if sha512_file(part) != digest:
        part.unlink(missing_ok=True)
        raise ValueError("SHA512 stimmt nicht – Download verworfen")
    part.replace(target)
    progress(1.0, f"{name} heruntergeladen")
    return target
