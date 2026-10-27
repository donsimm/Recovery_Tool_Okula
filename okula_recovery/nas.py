"""NAS: Verbindungstest, Einhängen und Auflisten gespeicherter Images."""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from okula_recovery.config import NasConfig

PORTS = {"smb": 445, "nfs": 2049}

# Endungen von Roh-/partclone-Images, optional komprimiert
IMAGE_SUFFIXES = (".img", ".raw", ".dd", ".pcl", ".partclone", ".qcow2", ".vhdx")
COMPRESS_SUFFIXES = (".gz", ".zst", ".xz", ".lz4", ".bz2")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class ImageInfo:
    name: str
    path: Path
    kind: str
    size: int
    mtime: datetime


def test_connection(cfg: NasConfig, timeout: float = 3.0) -> list[Check]:
    """Prüft Schritt für Schritt: Auflösung, Port, Einhängepunkt, Lese-/Schreibrecht.

    Bricht nach dem ersten Fehler ab, damit die Ursache eindeutig bleibt.
    """
    checks: list[Check] = []

    if not cfg.host:
        return [Check("Host", False, "Kein NAS-Host konfiguriert")]
    try:
        addr = socket.gethostbyname(cfg.host)
        checks.append(Check("Namensauflösung", True, f"{cfg.host} → {addr}"))
    except OSError as e:
        checks.append(Check("Namensauflösung", False, f"{cfg.host}: {e}"))
        return checks

    port = PORTS.get(cfg.protocol, 445)
    try:
        with socket.create_connection((addr, port), timeout=timeout):
            pass
        checks.append(Check("Netzwerk", True, f"{cfg.protocol.upper()}-Port {port} erreichbar"))
    except OSError as e:
        checks.append(Check("Netzwerk", False, f"Port {port} nicht erreichbar: {e}"))
        return checks

    mp = Path(cfg.mount_point)
    if not os.path.ismount(mp):
        checks.append(Check("Eingehängt", False, f"{mp} ist nicht eingehängt"))
        return checks
    checks.append(Check("Eingehängt", True, str(mp)))

    if not os.access(mp, os.R_OK | os.X_OK):
        checks.append(Check("Lesen", False, f"Keine Leserechte auf {mp}"))
        return checks
    checks.append(Check("Lesen", True, "OK"))

    try:
        with tempfile.NamedTemporaryFile(dir=mp, prefix=".okula-write-test-"):
            pass
        checks.append(Check("Schreiben", True, "OK"))
    except OSError as e:
        checks.append(Check("Schreiben", False, str(e)))

    try:
        st = os.statvfs(mp)
        free = st.f_bavail * st.f_frsize
        total = st.f_blocks * st.f_frsize
        checks.append(Check("Speicher", True, f"{format_size(free)} frei von {format_size(total)}"))
    except OSError:
        pass

    return checks


def mount(cfg: NasConfig) -> tuple[bool, str]:
    """Hängt den Einhängepunkt über /etc/fstab ein (Eintrag mit Option 'user' nötig)."""
    if os.path.ismount(cfg.mount_point):
        return True, "Bereits eingehängt"
    try:
        r = subprocess.run(["mount", cfg.mount_point], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or f"mount Exit-Code {r.returncode}"
    return True, "Eingehängt"


def _image_kind(name: str) -> str | None:
    lower = name.lower()
    for c in COMPRESS_SUFFIXES:
        if lower.endswith(c):
            lower = lower[: -len(c)]
            break
    for s in IMAGE_SUFFIXES:
        if lower.endswith(s):
            return s.lstrip(".").upper()
    return None


def _is_clonezilla_dir(path: Path) -> bool:
    return (path / "disk").is_file() and (path / "parts").is_file()


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def list_images(root: str | Path, max_depth: int = 2) -> list[ImageInfo]:
    """Sucht Images unter root (Dateien nach Endung, Clonezilla-Ordner), neueste zuerst."""
    root = Path(root)
    found: list[ImageInfo] = []

    def walk(d: Path, depth: int) -> None:
        try:
            entries = list(os.scandir(d))
        except OSError:
            return
        for e in entries:
            if e.name.startswith("."):
                continue
            p = Path(e.path)
            try:
                if e.is_dir(follow_symlinks=False):
                    if _is_clonezilla_dir(p):
                        found.append(ImageInfo(str(p.relative_to(root)), p, "Clonezilla",
                                               _dir_size(p), datetime.fromtimestamp(e.stat().st_mtime)))
                    elif depth < max_depth:
                        walk(p, depth + 1)
                elif e.is_file(follow_symlinks=False):
                    kind = _image_kind(e.name)
                    if kind:
                        st = e.stat()
                        found.append(ImageInfo(str(p.relative_to(root)), p, kind,
                                               st.st_size, datetime.fromtimestamp(st.st_mtime)))
            except OSError:
                continue

    walk(root, 0)
    found.sort(key=lambda i: i.mtime, reverse=True)
    return found


def format_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"
