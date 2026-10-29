"""Agent-Seite: Gerät nach dem Zurückspielen anpassen, Ordner auf den Desktop legen, Countdown am Bildschirm.

- customize: Windows-Master-Image (mit Sysprep generalisiert) bekommt eine Antwortdatei
  Windows/Panther/unattend.xml (Computername, Key, Region …, vom Tool erstellt); Linux bekommt den Hostnamen.
- deliver: Ordner (Software, Test Files, Content/Projekt …) auf den öffentlichen Desktop
  (Users/Public/Desktop); vorhandene Ordner gleichen Namens werden ersetzt – erst wenn alles da ist.
- countdown: „Automatisierung startet in 30 s – Esc zum Abbrechen“ am Bildschirm; Esc direkt von der
  Tastatur (/dev/input), unabhängig davon, was auf tty1 läuft.
"""

from __future__ import annotations

import glob
import os
import re
import secrets
import select
import shutil
import struct
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Callable

from okula_recovery import filebackup, imaging, inventory, wire

ImagingError = imaging.ImagingError
Report = Callable[[float, str, int], None]

GENERALIZED = "IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE"
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
STAGE_PREFIX = ".okula-"
MAX_UNATTEND = 256 * 1024


# ---------- Hilfen ----------

def find_ci(root: Path, rel: str) -> Path | None:
    """Pfad ohne Rücksicht auf Gross-/Kleinschreibung (NTFS über ntfs-3g unterscheidet sie)."""
    cur = root
    for part in PurePosixPath(rel).parts:
        if (cur / part).exists():
            cur = cur / part
            continue
        try:
            match = next((p for p in cur.iterdir() if p.name.lower() == part.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        cur = match
    return cur


def _read_text(path: Path) -> str:
    data = path.read_bytes()[:65536]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8", errors="replace")


def windows_state(root: Path) -> str:
    """„generalized“ (Sysprep, startet in die Ersteinrichtung), „installed“ oder „“ (kein Windows)."""
    if find_ci(root, "Windows/System32/config/SYSTEM") is None:
        return ""
    ini = find_ci(root, "Windows/Setup/State/State.ini")
    try:
        text = _read_text(ini) if ini else ""
    except OSError:
        text = ""
    return "generalized" if GENERALIZED in text.upper() else "installed"


def _candidates(disk: str) -> list[dict]:
    """Partitionen der Disk, die ein Betriebssystem enthalten können (gross genug, lesbares Dateisystem)."""
    disks = {d["path"]: d for d in imaging.list_disks()}
    if disk not in disks:
        raise ImagingError(f"Disk {disk} nicht gefunden")
    out = []
    for part in disks[disk]["partitions"]:
        fs = part.get("fstype") or inventory.probe_fstype(part["path"])
        if fs.lower() == "bitlocker":
            raise ImagingError(f"{part['path']} ist mit BitLocker verschlüsselt – nicht beschreibbar")
        if fs in inventory.RO_OPTIONS and part.get("size", 0) >= inventory.MIN_OS_PARTITION:
            out.append({**part, "fstype": fs})
    return out


# ---------- Anpassen ----------

def set_linux_hostname(root: Path, name: str) -> str:
    """/etc/hostname und die 127.0.1.1-Zeile in /etc/hosts; gibt den alten Namen zurück."""
    if not HOSTNAME_RE.match(name):
        raise ImagingError(f"Ungültiger Hostname: {name}")
    hostfile = root / "etc" / "hostname"
    if hostfile.is_symlink():
        raise ImagingError("/etc/hostname ist ein Link – nicht angepasst")
    old = hostfile.read_text().strip() if hostfile.is_file() else ""
    hostfile.write_text(name + "\n")
    hosts = root / "etc" / "hosts"
    if hosts.is_file() and not hosts.is_symlink():
        lines, found = [], False
        for line in hosts.read_text().splitlines():
            fields = line.split()
            if fields and fields[0] == "127.0.1.1":
                line, found = f"127.0.1.1\t{name}", True
            elif old and old in fields[1:] and not fields[0].startswith("#"):
                line = "\t".join([fields[0]] + [name if f == old else f for f in fields[1:]])
            lines.append(line)
        if not found:
            lines.append(f"127.0.1.1\t{name}")
        hosts.write_text("\n".join(lines) + "\n")
    return old


def write_unattend(root: Path, xml: str) -> Path:
    """Windows/Panther/unattend.xml – wird beim ersten Start nach Sysprep vor allen anderen gelesen."""
    windir = find_ci(root, "Windows")
    if windir is None:
        raise ImagingError("Kein Windows-Ordner gefunden")
    panther = find_ci(windir, "Panther") or windir / "Panther"
    if panther.is_symlink():
        raise ImagingError("Windows/Panther ist ein Link – nicht angepasst")
    panther.mkdir(exist_ok=True)
    target = find_ci(panther, "unattend.xml") or panther / "unattend.xml"
    tmp = panther / ".unattend.okula-tmp"
    tmp.write_text(xml, encoding="utf-8")
    tmp.replace(target)
    return target


def customize(req: dict, log: Callable[[str], None] = print) -> dict:
    """Alle Systeme auf der Disk anpassen. Ergebnis je Partition: was gemacht wurde (oder warum nicht)."""
    disk = str(req.get("disk") or "")
    xml = str(req.get("unattend") or "")
    hostname = str(req.get("hostname") or "")
    if len(xml) > MAX_UNATTEND:
        raise ImagingError("Antwortdatei zu gross")
    results = []
    with filebackup.Mounts(write=True) as m:
        for part in _candidates(disk):
            try:
                root = m.get(part["path"])
            except ImagingError as e:
                results.append({"part": part["path"], "system": "", "action": "error", "detail": str(e)})
                continue
            state = windows_state(root)
            if state == "generalized":
                if xml:
                    write_unattend(root, xml)
                    results.append({"part": part["path"], "system": "windows", "action": "unattend"})
                else:
                    results.append({"part": part["path"], "system": "windows", "action": "none"})
            elif state == "installed":
                results.append({"part": part["path"], "system": "windows", "action": "not_generalized"})
            elif (root / "etc" / "os-release").is_file() or (root / "usr" / "lib" / "os-release").is_file():
                if hostname:
                    old = set_linux_hostname(root, hostname)
                    results.append({"part": part["path"], "system": "linux", "action": "hostname", "old": old})
                else:
                    results.append({"part": part["path"], "system": "linux", "action": "none"})
        subprocess.run(["sync"])
    for r in results:
        log(f"Anpassen {r['part']}: {r['system'] or '–'} → {r['action']}")
    return {"type": "done", "results": results}


# ---------- Ordner auf den Desktop ----------

def public_desktop(root: Path) -> Path | None:
    users = find_ci(root, "Users")
    if users is None or find_ci(root, "Windows") is None:
        return None
    public = find_ci(users, "Public")
    if public is None:
        return None
    desktop = find_ci(public, "Desktop")
    if desktop is None:
        desktop = public / "Desktop"
        desktop.mkdir()
    return desktop


def _windows_root(m: filebackup.Mounts, disk: str) -> Path:
    found = []
    for part in _candidates(disk):
        if part["fstype"] != "ntfs":
            continue
        try:
            root = m.get(part["path"])
        except ImagingError as e:
            if "Ruhezustand" in str(e):
                raise
            continue
        if windows_state(root) and public_desktop(root) is not None:
            found.append(root)
    if not found:
        raise ImagingError(f"Kein Windows mit öffentlichem Desktop auf {disk} gefunden")
    if len(found) > 1:
        raise ImagingError(f"Mehrere Windows-Installationen auf {disk} – nicht eindeutig")
    return found[0]


def _item_name(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or any(x.startswith(STAGE_PREFIX) for x in p.parts) \
            or len(p.parts) > 2:
        raise ImagingError(f"Ungültiger Ordnername: {name}")
    return p


def deliver(sock, req: dict, log: Callable[[str], None] = print, report: Report | None = None) -> None:
    """Ordner vom Tool empfangen und auf den öffentlichen Desktop legen.

    Ablauf: alles in einen versteckten Zwischenordner auf demselben Laufwerk schreiben; erst am Ende
    wird pro Ordner der alte Stand durch den neuen ersetzt. Bricht etwas ab, bleibt der alte Stand."""
    report = report or (lambda f, p, n: None)
    items = [_item_name(str(i)) for i in req.get("items") or []]
    if not items:
        raise ImagingError("Keine Ordner gewählt")
    total = int(req.get("bytes") or 0) or 1
    with filebackup.Mounts(write=True) as m:
        desktop = public_desktop(_windows_root(m, str(req.get("disk") or "")))
        stage = desktop / f"{STAGE_PREFIX}{secrets.token_hex(4)}"
        stage.mkdir()
        try:
            for item in items:
                (stage / item).mkdir(parents=True, exist_ok=True)
            wire.send_json(sock, {"type": "ready"})
            received = files = 0
            while True:
                msg = wire.recv_json(sock)
                kind = msg.get("type")
                if kind == "end":
                    break
                rel = PurePosixPath(str(msg.get("path") or ""))
                if not any(rel == i or i in rel.parents for i in items):
                    raise ImagingError(f"Pfad gehört zu keinem gewählten Ordner: {rel}")
                dest = filebackup._safe(stage, str(rel))
                if kind == "dir":
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                if kind != "file":
                    raise ImagingError(f"Unerwartete Nachricht: {kind}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as out:
                    for chunk in imaging._frames(sock, {"file": str(rel)}):
                        out.write(chunk)
                        received += len(chunk)
                        report(min(1.0, received / total), str(rel), received)
                mtime = int(msg.get("mtime") or 0)
                if mtime:
                    os.utime(dest, (mtime, mtime))
                files += 1
            # Alles angekommen: pro Ordner alten Stand weg, neuen an seinen Platz
            for item in items:
                final = desktop / item
                if final.is_symlink():
                    raise ImagingError(f"{item} auf dem Desktop ist ein Link – nicht ersetzt")
                final.parent.mkdir(parents=True, exist_ok=True)
                old = stage / f"{STAGE_PREFIX}alt-{len(item.parts)}-{secrets.token_hex(3)}"
                if final.exists():
                    final.rename(old)
                (stage / item).rename(final)
                shutil.rmtree(old, ignore_errors=True)
            subprocess.run(["sync"])
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    wire.send_json(sock, {"type": "done", "files": files, "bytes": received})
    log(f"Ordner auf den Desktop gelegt: {', '.join(map(str, items))} ({files} Dateien)")


# ---------- Countdown am Bildschirm ----------

EV_KEY, KEY_ESC = 1, 1
EVENT = struct.Struct("llHHi")


def esc_pressed(fds: list[int]) -> bool:
    """Liest anstehende Tastatur-Ereignisse; True, wenn Esc gedrückt wurde."""
    for fd in fds:
        try:
            data = os.read(fd, EVENT.size * 64)
        except (BlockingIOError, OSError):
            continue
        for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _s, _us, etype, code, value = EVENT.unpack_from(data, off)
            if etype == EV_KEY and code == KEY_ESC and value == 1:
                return True
    return False


def open_keyboards(pattern: str = "/dev/input/event*") -> list[int]:
    fds = []
    for path in sorted(glob.glob(pattern)):
        try:
            fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
        except OSError:
            continue
    return fds


def countdown(sock, req: dict, console: str, log: Callable[[str], None] = print,
              keyboards: list[int] | None = None) -> str:
    """Zählt herunter; Ergebnis „start“, „esc“ (am Gerät abgebrochen) oder „tool“ (Tool hat abgebrochen)."""
    seconds = max(1, min(600, int(req.get("seconds") or 30)))
    title = str(req.get("title") or "Automatisierung")[:120]
    fds = open_keyboards() if keyboards is None else keyboards
    own = keyboards is None
    esc_pressed(fds)  # alte Tastendrücke verwerfen

    def show(text: str) -> None:
        if console:
            try:
                with open(console, "a") as tty:
                    tty.write(text)
            except OSError:
                pass

    show(f"\n  {title}\n")
    result = "start"
    end = time.monotonic() + seconds
    try:
        while (left := end - time.monotonic()) > 0:
            show(f"\r\033[K  >> startet in {int(left + 0.999):2d} s – Esc zum Abbrechen")
            ready, _w, _x = select.select([sock, *fds], [], [], min(1.0, left))
            if sock in ready:  # Tool hat abgebrochen (Verbindung zu) oder schickt etwas
                result = "tool"
                break
            if ready and esc_pressed([fd for fd in ready if fd is not sock]):
                result = "esc"
                break
    finally:
        if own:
            for fd in fds:
                os.close(fd)
    show("\r\033[K  " + {"start": ">> startet jetzt – Maschine nicht ausschalten",
                         "esc": ">> mit Esc abgebrochen – Gerät bleibt im normalen Agent-Betrieb",
                         "tool": ">> im Tool abgebrochen"}[result] + "\n")
    log(f"Countdown „{title}“: {result}")
    return result


def banner(console: str, lines: list[str], error: bool = False) -> None:
    """Gut sichtbarer Block am Bildschirm, z. B. wenn die Automatisierung fehlgeschlagen ist."""
    if not console:
        return
    bar = "!" * 64 if error else "=" * 64
    text = "\n".join(f"  {line[:200]}" for line in lines)
    try:
        with open(console, "a") as tty:
            tty.write(f"\n  {bar}\n{text}\n  {bar}\n")
    except OSError:
        pass
