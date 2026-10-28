"""NAS: Verbindungstest, Einhängen und Auflisten gespeicherter Images."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from okula_recovery.config import NasConfig

PORTS = {"smb": 445, "nfs": 2049}

# Zugangsdaten für SMB, nur für root lesbar (vom Root-Helfer geschrieben)
CRED_FILE = Path("/etc/okula-recovery/nas.cred")
MOUNT_HELPER = "/usr/local/sbin/okula-nas-mount"
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Typische Fehlermeldungen von mount.cifs / mount.nfs → Hinweis für den Benutzer
MOUNT_HINTS = (
    ("error(13)", "Benutzer oder Passwort falsch, oder der Benutzer hat keinen Zugriff auf die Freigabe"),
    ("Permission denied", "Benutzer oder Passwort falsch, oder der Benutzer hat keinen Zugriff auf die Freigabe"),
    ("error(2)", "Freigabe existiert nicht – Namen prüfen („Freigaben suchen“)"),
    ("error(112)", "SMB-Version passt nicht – im NAS SMB2/SMB3 aktivieren"),
    ("Host is down", "SMB-Version passt nicht – im NAS SMB2/SMB3 aktivieren"),
    ("access denied by server", "NFS-Freigabe erlaubt diese IP nicht – NFS-Berechtigung im NAS setzen"),
    ("NT_STATUS_LOGON_FAILURE", "Benutzer oder Passwort falsch"),
    ("NT_STATUS_ACCESS_DENIED", "Benutzer hat keinen Zugriff"),
    ("NT_STATUS_ACCOUNT_DISABLED", "NAS-Benutzer ist deaktiviert"),
    ("NT_STATUS_IO_TIMEOUT", "NAS antwortet nicht – IP und SMB-Dienst prüfen"),
    ("NT_STATUS_CONNECTION_REFUSED", "SMB-Dienst auf dem NAS nicht aktiv"),
    ("NT_STATUS_HOST_UNREACHABLE", "NAS nicht erreichbar – IP und Netzwerk prüfen"),
    ("not supported by the system", "CIFS fehlt im System – install.sh ausführen (cifs-utils)"),
    ("wrong fs type", "Mount-Werkzeug fehlt – install.sh ausführen (cifs-utils/nfs-common)"),
    ("bad option", "Mount-Werkzeug fehlt – install.sh ausführen (cifs-utils/nfs-common)"),
)

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
        checks.append(Check("Eingehängt", False, f"{mp} ist nicht eingehängt – „Einhängen“ klicken"))
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


LOW_SPACE = 100 * 1000**3  # unter 100 GB frei: Warnung im Hauptfenster


@dataclass
class Status:
    """Kurzstatus für das Hauptfenster (ohne Schreibtest, für regelmässige Abfragen)."""
    state: str           # "ok", "fail", "unconfigured"
    reason: str = ""
    free: int = 0
    total: int = 0

    @property
    def low_space(self) -> bool:
        return self.state == "ok" and self.free < LOW_SPACE


def quick_status(cfg: NasConfig, auto_mount: bool = False) -> Status:
    """Eingehängt? Wie viel Platz frei? Optional mit gespeicherten Zugangsdaten einhängen."""
    if not cfg.host or not cfg.share:
        return Status("unconfigured", "nicht eingerichtet")
    if not os.path.ismount(cfg.mount_point):
        if not auto_mount:
            return Status("fail", "nicht eingehängt")
        if cfg.protocol == "smb" and not has_credentials():
            return Status("fail", "nicht eingehängt – Zugangsdaten fehlen")
        ok, msg = mount(cfg)
        if not ok:
            return Status("fail", msg)
    try:
        st = os.statvfs(cfg.mount_point)
    except OSError as e:
        return Status("fail", f"nicht lesbar: {e.strerror or e}")
    return Status("ok", "", st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize)


def format_gb(n: int) -> str:
    """Dezimale Angabe wie auf Disks und NAS (GB/TB)."""
    return f"{n / 1000**4:.2f} TB" if n >= 1000**4 else f"{n / 1000**3:.0f} GB"


def mount_error_hint(message: str) -> str:
    for needle, hint in MOUNT_HINTS:
        if needle in message:
            return hint
    return ""


def has_credentials() -> bool:
    return CRED_FILE.exists()


def _helper(args: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return [sys.executable, "-m", "okula_recovery.nasmount", *args]
    if not Path(MOUNT_HELPER).exists():
        raise FileNotFoundError(f"{MOUNT_HELPER} fehlt – bitte install.sh erneut ausführen")
    return ["sudo", "-n", MOUNT_HELPER, *args]


def _call_helper(args: list[str], stdin: str | None = None) -> tuple[bool, str]:
    try:
        r = subprocess.run(_helper(args), input=stdin, capture_output=True, text=True, timeout=90,
                           cwd=PROJECT_DIR)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("OK ", "ERROR "))]
    if lines:
        kind, _, msg = lines[-1].partition(" ")
        return kind == "OK" and r.returncode == 0, msg
    return False, (r.stderr or r.stdout).strip() or f"Hilfsprogramm: Exit-Code {r.returncode}"


def mount(cfg: NasConfig, password: str = "") -> tuple[bool, str]:
    """Hängt die Freigabe über den Root-Helfer ein; leeres Passwort = gespeicherte Zugangsdaten."""
    args = ["mount", "--protocol", cfg.protocol, "--host", cfg.host, "--share", cfg.share,
            "--mount-point", cfg.mount_point, "--user", cfg.username]
    if password:
        args.append("--password-stdin")
    return _call_helper(args, stdin=password + "\n" if password else None)


def umount(cfg: NasConfig) -> tuple[bool, str]:
    return _call_helper(["umount", "--mount-point", cfg.mount_point])


def parse_smbclient_shares(output: str) -> list[str]:
    """Parst `smbclient -L … -g`: Zeilen „Disk|Name|Kommentar“, versteckte ($) weggelassen."""
    shares = []
    for line in output.splitlines():
        parts = line.split("|")
        if len(parts) >= 2 and parts[0] == "Disk" and not parts[1].endswith("$"):
            shares.append(parts[1])
    return sorted(shares, key=str.lower)


def list_smb_shares(host: str, user: str, password: str) -> list[str]:
    """Freigaben des NAS über smbclient; Zugangsdaten über eine temporäre 0600-Datei, nicht über argv."""
    with tempfile.NamedTemporaryFile("w", prefix="okula-auth-") as auth:
        auth.write(f"username={user}\npassword={password}\n")
        auth.flush()
        try:
            r = subprocess.run(["smbclient", "-L", f"//{host}", "-A", auth.name, "-g"],
                               capture_output=True, text=True, timeout=20)
        except FileNotFoundError:
            raise RuntimeError("smbclient fehlt – install.sh erneut ausführen") from None
    shares = parse_smbclient_shares(r.stdout)
    if not shares:
        lines = (r.stderr or r.stdout).strip().splitlines()
        msg = lines[-1] if lines else "Keine Freigaben gefunden"
        hint = mount_error_hint(msg)
        raise RuntimeError(f"{hint} ({msg})" if hint else msg)
    return shares


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


OKULA_META = "okula-image.json"


def _okula_image(path: Path, root: Path) -> ImageInfo | None:
    """Ordner eines Okula-Disk-Images (Metadaten mit Dateiliste)."""
    try:
        meta = json.loads((path / OKULA_META).read_text())
        size = sum(int(f.get("size", 0)) for f in meta.get("files", []))
        mtime = datetime.fromisoformat(meta["completed"]) if meta.get("completed") \
            else datetime.fromtimestamp(path.stat().st_mtime)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    name = str(path.relative_to(root))
    if name.startswith("images/"):
        name = name[len("images/"):]
    disk = meta.get("disk") or {}
    model = disk.get("model") or ""
    return ImageInfo(f"{name}  ({model})" if model else name, path, "Disk-Image", size, mtime)


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
                    if e.name.endswith(".partial"):
                        continue  # Image wird gerade geschrieben oder ist abgebrochen
                    if (p / OKULA_META).is_file():
                        info = _okula_image(p, root)
                        if info:
                            found.append(info)
                    elif _is_clonezilla_dir(p):
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
