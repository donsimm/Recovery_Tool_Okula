"""Agent-Seite: Gerät nach dem Zurückspielen anpassen, Ordner auf den Desktop legen, Countdown am Bildschirm.

- customize: Windows-Master-Image (mit Sysprep generalisiert) bekommt eine Antwortdatei
  Windows/Panther/unattend.xml (Computername, Key, Region …, vom Tool erstellt); Linux bekommt den Hostnamen.
  Ä-040: auf Wunsch die Taskleiste des Administrators als LayoutModification.xml ins Standardprofil (winprofile).
- deliver: Ordner (Software, Test Files, Content/Projekt …) auf den öffentlichen Desktop
  (Users/Public/Desktop); vorhandene Ordner gleichen Namens werden ersetzt – erst wenn alles da ist.
- tweak: „Windows anpassen“ (I-039) – ein vom Tool erzeugtes PowerShell-Skript als einmaliges Startskript der
  lokalen Gruppenrichtlinie ablegen (System32/GroupPolicy); vorhandene Richtlinien bleiben, das Skript stellt den
  vorherigen Stand beim Start selbst wieder her.
- software: „Software installieren“ (I-020) – Installer nach ProgramData/Okula/Software und ein Startskript
  (wie tweak), das sie beim nächsten Windows-Start als SYSTEM still installiert.
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

from okula_recovery import filebackup, imaging, inventory, winprofile, wire

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


def adopt_taskbar(root: Path) -> dict:
    """Ä-040: Taskleiste des Administrators ins Standardprofil (winprofile) – Fehler werden gemeldet, nie geworfen:
    Name und Key sind dann schon gesetzt, das Anpassen gilt als gelungen."""
    try:
        return winprofile.adopt_taskbar(root)
    except (OSError, winprofile.ProfileError) as e:
        return {"profile": "", "pins": [], "order": "", "written": [], "copied": [], "reason": "",
                "error": str(e)}


def customize_root(root: Path, xml: str, hostname: str, copy_profile: bool = False) -> dict | None:
    """Ein eingehängtes System anpassen. Ergebnis {system, action, …} oder None (kein Betriebssystem)."""
    state = windows_state(root)
    if state == "generalized":
        if not xml:
            return {"system": "windows", "action": "none"}
        write_unattend(root, xml)
        result = {"system": "windows", "action": "unattend"}
        if copy_profile:
            result["taskbar"] = adopt_taskbar(root)
        return result
    if state == "installed":
        return {"system": "windows", "action": "not_generalized"}
    if (root / "etc" / "os-release").is_file() or (root / "usr" / "lib" / "os-release").is_file():
        if hostname:
            return {"system": "linux", "action": "hostname", "old": set_linux_hostname(root, hostname)}
        return {"system": "linux", "action": "none"}
    return None


def customize(req: dict, log: Callable[[str], None] = print) -> dict:
    """Alle Systeme auf der Disk anpassen. Ergebnis je Partition: was gemacht wurde (oder warum nicht).
    copy_profile (Ä-040): zusätzlich die Taskleiste des Administrators ins Standardprofil (Ergebnis „taskbar“)."""
    disk = str(req.get("disk") or "")
    xml = str(req.get("unattend") or "")
    hostname = str(req.get("hostname") or "")
    copy_profile = bool(req.get("copy_profile"))
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
            result = customize_root(root, xml, hostname, copy_profile)
            if result is not None:
                results.append({"part": part["path"], **result})
        subprocess.run(["sync"])
    for r in results:
        log(f"Anpassen {r['part']}: {r['system'] or '–'} → {r['action']}")
        bar = r.get("taskbar")
        if bar:
            log(f"Anpassen {r['part']}: Taskleiste aus Profil „{bar.get('profile') or '–'}“: "
                + (", ".join(bar.get("pins") or []) or bar.get("error") or bar.get("reason") or "–"))
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


def _receive_into(sock, stage: Path, items: list[PurePosixPath], total: int, report: Report) -> tuple[int, int]:
    """Ordner/Dateien vom Tool in den Zwischenordner (nur unterhalb der gewählten Einträge). (Dateien, Bytes)."""
    wire.send_json(sock, {"type": "ready"})
    received = files = 0
    while True:
        msg = wire.recv_json(sock)
        kind = msg.get("type")
        if kind == "end":
            return files, received
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
            files, received = _receive_into(sock, stage, items, total, report)
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


# ---------- Windows anpassen (I-039): einmaliges Startskript der lokalen Gruppenrichtlinie ----------
#
# Ablage (alles unter Windows/System32/GroupPolicy):
#   Machine/Scripts/Startup/okula-windows-anpassen.cmd   – Startskript (ruft PowerShell auf, Notfall-Aufräumen)
#   Machine/Scripts/Startup/okula-windows-anpassen.ps1   – Einstellungen (vom Tool erzeugt, wintweaks.py)
#   Machine/Scripts/scripts.ini                           – Eintrag [Startup] NCmdLine=okula-windows-anpassen.cmd
#   gpt.ini                                               – Scripts-Erweiterung ergänzt, Version +1
#   gpt.ini.okula-nachher, Machine/Scripts/scripts.ini.okula-nachher
#                                                         – Stand für nach dem Lauf (Original, gpt.ini mit Version
#                                                           +2); fehlt die Datei, gab es das Original nicht
# Das Skript legt beim Start zuerst diese Dateien zurück (bzw. löscht gpt.ini/scripts.ini, wenn es sie vorher nicht
# gab), entfernt seine Einträge unter HKLM\…\Group Policy\Scripts und löscht sich – danach erst die Einstellungen.

TWEAK_NAME = "okula-windows-anpassen"
TWEAK_CMD = TWEAK_NAME + ".cmd"
TWEAK_PS1 = TWEAK_NAME + ".ps1"
TWEAK_AFTER = ".okula-nachher"
TWEAK_LOG = r"C:\Windows\Temp\okula-windows-anpassen.log"
MAX_SCRIPT = 512 * 1024
SCRIPTS_CSE = "{42B5FAAE-6536-11D2-AE5A-0000F87571E3}"     # Client-Erweiterung „Scripts“
SCRIPTS_TOOL = "{40B6664F-4972-11D1-A7CA-0000F87571E3}"    # Snap-in „Skripts (Start/Herunterfahren)“, Computer
GUID_RE = re.compile(r"\{[0-9A-Fa-f-]{36}\}")
# B-019: Richtlinie „Beim Neustart des Computers und bei der Anmeldung immer auf das Netzwerk warten“ (Logon.admx,
# SyncForegroundPolicy) im Hive SOFTWARE – während ein Okula-Startskript aussteht; Stand von vorher in
# GroupPolicy/SyncForegroundPolicy.okula-nachher („fehlt“ bzw. „dword:<Zahl>“). Details bei set_sync_policy.
SYNC_KEY = r"Policies\Microsoft\Windows NT\CurrentVersion\Winlogon"
SYNC_VALUE = "SyncForegroundPolicy"
SYNC_SAVED = SYNC_VALUE + TWEAK_AFTER
SYNC_ABSENT = "fehlt"

def startup_cmd_text(name: str, title: str, args: str = "", what: str = "Einstellungen") -> str:
    """Startskript (.cmd) für <name>.ps1 im selben Ordner.

    Nur ASCII (cmd liest die Datei in der OEM-Codepage). Die zweite Hälfte läuft nur, wenn PowerShell das Skript nicht
    gestartet hat – sonst hat das Skript beide Dateien schon gelöscht und cmd findet die nächste Zeile nicht mehr.
    Steht noch ein anderes Okula-Startskript aus (I-020: Software und Windows anpassen gleichzeitig), stellt erst
    dieses die Gruppenrichtlinie wieder her – und (B-019) SyncForegroundPolicy wie vorher (reg add bzw. reg delete)."""
    return "\r\n".join((
        "@echo off",
        f"rem Okula Recovery Tool - {title}: einmaliges Startskript (entfernt sich selbst)",
        '"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -NonInteractive '
        f'-ExecutionPolicy Bypass -File "%~dp0{name}.ps1"' + (f" {args}" if args else ""),
        "rem Nur erreicht, wenn PowerShell das Skript nicht gestartet hat: aufraeumen, damit nichts erneut laeuft",
        f'del /f /q "%~dp0{name}.ps1" >nul 2>&1',
        f'>>"%SystemRoot%\\Temp\\{name}.log" echo %DATE% %TIME%  FEHLER  PowerShell-Skript nicht gestartet '
        f"- {what} nicht umgesetzt",
        'set "OKULA_ANDERE="',
        'for %%F in ("%~dp0okula-*.cmd") do if /i not "%%~nxF"=="%~nx0" set "OKULA_ANDERE=1"',
        "if defined OKULA_ANDERE goto ende",
        'set "OKULA_GP=%SystemRoot%\\System32\\GroupPolicy"',
        'for %%F in ("%OKULA_GP%\\Machine\\Scripts\\scripts.ini" "%OKULA_GP%\\gpt.ini") do (',
        '  attrib -r -h -s "%%~F" >nul 2>&1',
        '  del /f /q "%%~F" >nul 2>&1',
        f'  if exist "%%~F{TWEAK_AFTER}" move /y "%%~F{TWEAK_AFTER}" "%%~F" >nul',
        ")",
        f'if not exist "%OKULA_GP%\\{SYNC_SAVED}" goto ende',
        'set "OKULA_SYNC="',
        f'set /p OKULA_SYNC=<"%OKULA_GP%\\{SYNC_SAVED}"',
        f'set "OKULA_KEY=HKLM\\SOFTWARE\\{SYNC_KEY}"',
        f'if /i "%OKULA_SYNC:~0,6%"=="dword:" reg add "%OKULA_KEY%" /v {SYNC_VALUE} /t REG_DWORD '
        '/d %OKULA_SYNC:~6% /f >nul 2>&1',
        f'if /i not "%OKULA_SYNC:~0,6%"=="dword:" reg delete "%OKULA_KEY%" /v {SYNC_VALUE} /f >nul 2>&1',
        f'del /f /q "%OKULA_GP%\\{SYNC_SAVED}" >nul 2>&1',
        ":ende",
        'del /f /q "%~f0" >nul 2>&1',
        ""))


TWEAK_CMD_TEXT = startup_cmd_text(TWEAK_NAME, "Windows anpassen")

# I-020 Software installieren: Startskript wie oben, Installer unter ProgramData\Okula\Software
SOFTWARE_NAME = "okula-software"
SOFTWARE_LOG = r"C:\Windows\Temp\okula-software.log"
SOFTWARE_REL = "ProgramData/Okula/Software"
SOFTWARE_CMD_TEXT = startup_cmd_text(SOFTWARE_NAME, "Software installieren", "-Mode Start", "Software")


def ini_decode(data: bytes) -> tuple[str, str]:
    """Text und Kodierung einer INI-Datei (scripts.ini schreibt Windows als UTF-16, gpt.ini als ANSI)."""
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", errors="replace"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def ini_encode(text: str, encoding: str) -> bytes:
    if encoding == "utf-16":
        return b"\xff\xfe" + text.encode("utf-16-le")
    return text.encode(encoding, errors="replace")


def merge_extensions(value: str, cse: str = SCRIPTS_CSE, tool: str = SCRIPTS_TOOL) -> str:
    """gPCMachineExtensionNames um [{CSE}{Tool}] ergänzen – vorhandene Einträge bleiben, Reihenfolge nach GUID."""
    groups = [GUID_RE.findall(g) for g in re.findall(r"\[([^\]]*)\]", value)]
    groups = [g for g in groups if g]
    for g in groups:
        if g[0].upper() == cse.upper():
            if tool.upper() not in (x.upper() for x in g[1:]):
                g.append(tool)
            break
    else:
        groups.append([cse, tool])
    out = []
    for g in sorted(groups, key=lambda g: g[0].upper()):
        rest = sorted({x.upper(): x for x in g[1:]}.values(), key=str.upper)
        out.append("[" + g[0] + "".join(rest) + "]")
    return "".join(out)


def bump_version(version: int, step: int) -> int:
    """gpt.ini: Version = Benutzer-Teil (obere 16 Bit) · Computer-Teil (untere 16 Bit); Computer-Teil erhöhen."""
    machine = (version & 0xFFFF) + step
    if machine > 0xFFFF:
        machine = step
    return (version & 0xFFFF0000) | machine


def gpt_edit(text: str, step: int, add_scripts: bool) -> tuple[str, int]:
    """gpt.ini mit erhöhter Version (und auf Wunsch der Scripts-Erweiterung); übrige Zeilen bleiben."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().lower() == "[general]"), None)
    if start is None:
        lines = ["[General]"] + lines
        start = 0
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
    found: dict[str, int] = {}
    for i in range(start + 1, end):
        key = lines[i].split("=", 1)[0].strip().lower()
        if "=" in lines[i] and key in ("version", "gpcmachineextensionnames"):
            found[key] = i
    try:
        old = int(lines[found["version"]].split("=", 1)[1].strip()) if "version" in found else 0
    except ValueError:
        old = 0
    version = bump_version(old, step)
    new = {"version": f"Version={version}"}
    if add_scripts:
        current = lines[found["gpcmachineextensionnames"]].split("=", 1)[1] if "gpcmachineextensionnames" in found \
            else ""
        new["gpcmachineextensionnames"] = f"gPCMachineExtensionNames={merge_extensions(current)}"
    insert = []
    for key, line in new.items():
        if key in found:
            lines[found[key]] = line
        else:
            insert.append(line)
    if not text.strip():
        insert = ["gPCFunctionalityVersion=2"] + insert
    lines[end:end] = insert
    return "\r\n".join(lines) + "\r\n", version


def scripts_ini_has(text: str, cmdline: str = TWEAK_CMD) -> bool:
    """Steht das Startskript schon in [Startup]?"""
    section = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            section = s.lower()
        elif section == "[startup]" and re.match(r"^\d+cmdline\s*=", s, re.IGNORECASE):
            if s.split("=", 1)[1].strip().lower().endswith(cmdline.lower()):
                return True
    return False


def scripts_ini_add(text: str, cmdline: str = TWEAK_CMD, parameters: str = "") -> str:
    """Startskript hinten in [Startup] anhängen (nächste freie Nummer); andere Skripte bleiben."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().lower() == "[startup]"), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["[Startup]"]
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
    numbers = [int(m.group(1)) for line in lines[start + 1:end]
               if (m := re.match(r"^\s*(\d+)CmdLine\s*=", line, re.IGNORECASE))]
    n = max(numbers) + 1 if numbers else 0
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:end] = [f"{n}CmdLine={cmdline}", f"{n}Parameters={parameters}"]
    return "\r\n".join(lines) + "\r\n"


def _dir_ci(parent: Path, name: str) -> Path:
    path = find_ci(parent, name) or parent / name
    if path.is_symlink():
        raise ImagingError(f"{path.name} ist ein Link – nicht angepasst")
    return path


def _write_file(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise ImagingError(f"{path.name} ist ein Link – nicht angepasst")
    tmp = path.with_name(f".{path.name}.okula-tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def install_startup_script(root: Path, script: str, name: str = TWEAK_NAME, cmd_text: str | None = None) -> dict:
    """Skript als einmaliges Startskript der lokalen Gruppenrichtlinie ablegen (root = Windows-Partition).

    Ist schon ein noch nicht gelaufenes Okula-Startskript gleichen Namens da, wird nur das Skript ersetzt (die
    gesicherten Originale bleiben). Steht ein anderes Okula-Startskript aus (I-020: Software und Windows anpassen),
    kommt nur der Eintrag in scripts.ini dazu – Originale und Version bleiben, das letzte Skript stellt sie her.
    Ergebnis: {"replaced", "gpo" (gab es vorher eine lokale Richtlinie), "version"} (+ "shared": True)."""
    cmd_name, ps1_name = name + ".cmd", name + ".ps1"
    windir = find_ci(root, "Windows")
    sys32 = find_ci(windir, "System32") if windir else None
    if sys32 is None:
        raise ImagingError("Kein Windows-Ordner gefunden")
    gp = _dir_ci(sys32, "GroupPolicy")
    machine = _dir_ci(gp, "Machine")
    scripts = _dir_ci(machine, "Scripts")
    startup = _dir_ci(scripts, "Startup")
    startup.mkdir(parents=True, exist_ok=True)
    gpt = find_ci(gp, "gpt.ini") or gp / "gpt.ini"
    ini = find_ci(scripts, "scripts.ini") or scripts / "scripts.ini"
    ini_bytes = ini.read_bytes() if ini.is_file() else b""
    ini_text, ini_enc = ini_decode(ini_bytes) if ini_bytes else ("", "utf-16")
    gpt_bytes = gpt.read_bytes() if gpt.is_file() else b""
    gpt_text, gpt_enc = ini_decode(gpt_bytes) if gpt_bytes else ("", "latin-1")
    # Skript zuerst: PowerShell 5.1 liest UTF-8 nur mit BOM richtig
    _write_file(startup / ps1_name, b"\xef\xbb\xbf" + script.replace("\r\n", "\n").replace("\n", "\r\n")
                .encode("utf-8"))
    _write_file(startup / cmd_name, (cmd_text or startup_cmd_text(name, name)).encode("ascii"))
    has_cse = SCRIPTS_CSE.lower() in gpt_text.lower()
    saved_gpt = (find_ci(gp, gpt.name + TWEAK_AFTER) or gp / (gpt.name + TWEAK_AFTER)).exists()
    if scripts_ini_has(ini_text, cmd_name) and has_cse:
        return {"replaced": True, "gpo": saved_gpt, "version": gpt_edit(gpt_text, 0, False)[1]}
    others = [p.name for p in startup.iterdir() if p.name.lower().startswith("okula-")
              and p.name.lower().endswith(".cmd") and p.name.lower() != cmd_name.lower()
              and scripts_ini_has(ini_text, p.name)]
    if others and has_cse:
        _write_file(ini, ini_encode(scripts_ini_add(ini_text, cmd_name), ini_enc))
        return {"replaced": False, "gpo": saved_gpt, "version": gpt_edit(gpt_text, 0, False)[1], "shared": True}
    # Stand für nach dem Lauf: Originale (gpt.ini mit Version +2, damit Windows die Richtlinie neu verarbeitet)
    after_gpt, after_ini = gp / (gpt.name + TWEAK_AFTER), scripts / (ini.name + TWEAK_AFTER)
    if gpt_bytes:
        _write_file(after_gpt, ini_encode(gpt_edit(gpt_text, 2, False)[0], gpt_enc))
    elif after_gpt.exists():
        after_gpt.unlink()
    if ini_bytes:
        _write_file(after_ini, ini_bytes)
    elif after_ini.exists():
        after_ini.unlink()
    # Erst gpt.ini, dann scripts.ini (scripts.ini mit Eintrag = „wartet auf den Start“)
    new_gpt, version = gpt_edit(gpt_text, 1, True)
    _write_file(gpt, ini_encode(new_gpt, gpt_enc))
    _write_file(ini, ini_encode(scripts_ini_add(ini_text, cmd_name), ini_enc))
    return {"replaced": False, "gpo": bool(gpt_bytes), "version": version}


# ---------- B-019: Startskripte vor der Anmeldung (SyncForegroundPolicy offline setzen) ----------
#
# Auf Clients verarbeitet Windows die Gruppenrichtlinie beim Start standardmässig nicht synchron (Microsoft Learn,
# Policy CSP ADMX_Logon/SyncForegroundPolicy; „Schnelle Anmeldung“): Die Anmeldung erscheint, bevor die
# Startskripte gelaufen sind (Befund 24.11.2026: Okula-Skript beginnt 15 s nach der Anmeldung). Mit der Richtlinie
# „Beim Neustart des Computers und bei der Anmeldung immer auf das Netzwerk warten“ (SyncForegroundPolicy = 1)
# läuft die Verarbeitung synchron – die Anmeldung wartet, bis die Startskripte fertig sind (höchstens
# MaxGPOScriptWait, Standard 600 s für alle Skripte zusammen). Windows liest den Wert beim Start, bevor ein Skript
# läuft – darum setzt ihn der Agent offline im Hive SOFTWARE (hivexsh aus libhivex-bin, auf dem Agent-Stick):
#   Kopie (SOFTWARE.okula-tmp neben dem Original) → hivexsh -w → mit dem eigenen Leser prüfen → zurückschreiben.
# Bei einem Fehler bleibt der Hive unverändert; das Startskript läuft dann wie bisher (nach der Anmeldung).
# hivexsh „setval“ ersetzt alle Werte des Schlüssels – die übrigen Werte werden darum unverändert (hex:<Typ>:…)
# mitgeschrieben und danach verglichen.

REG_DWORD = 4
SYNC_ON = (REG_DWORD, b"\x01\x00\x00\x00")
_REG_NAME_RE = re.compile(r"^[\x21-\x7e](?:[\x20-\x7e]*[\x21-\x7e])?$")   # druckbares ASCII, kein Rand-Leerzeichen
_SAMPLE = (r"Microsoft\Windows NT\CurrentVersion", "CurrentBuild")         # Stichprobe: bleibt gleich


class SyncError(ImagingError):
    """SyncForegroundPolicy nicht gesetzt – Hive unverändert (Startskript läuft dann nach der Anmeldung)."""


def sync_saved_text(old: tuple[int, bytes] | None) -> str:
    """Stand von vorher für SyncForegroundPolicy.okula-nachher: „fehlt“ oder „dword:<Zahl>“."""
    if old is None:
        return SYNC_ABSENT
    kind, data = old
    if kind != REG_DWORD or len(data) != 4:
        raise SyncError(f"{SYNC_VALUE} ist schon vorhanden, aber kein DWORD (Typ {kind}) – nicht geändert")
    return f"dword:{struct.unpack('<I', data)[0]}"


def hivexsh_commands(present: list[str], missing: list[str], values: list[tuple[str, int, bytes]]) -> str:
    """Eingabe für hivexsh -w: zum Schlüssel wechseln (fehlende Teile anlegen), alle Werte setzen, speichern."""
    lines = ["cd \\" + "\\".join(present)] if present else []
    for part in missing:
        lines += [f"add {part}", f"cd {part}"]
    lines.append(f"setval {len(values)}")
    for name, kind, data in values:
        lines += [name or "@", f"hex:{kind}:" + ",".join(f"{b:02x}" for b in data)]
    lines.append("commit")
    return "\n".join(lines) + "\n"


def _value_set(values) -> list[tuple[str, int, bytes]]:
    return sorted((n.lower(), k, d) for n, k, d in values or [] if n.lower() != SYNC_VALUE.lower())


def _check_sync_hive(before: winprofile.Hive, data: bytes) -> None:
    """Geschriebene Kopie prüfen: Wert = 1, übrige Werte des Schlüssels und Stichprobe gleich, Kopf sauber."""
    try:
        after = winprofile.Hive(data)
        ok = after.value(SYNC_KEY, SYNC_VALUE) == SYNC_ON
        same = _value_set(after.values(SYNC_KEY)) == _value_set(before.values(SYNC_KEY))
        sample = after.value(*_SAMPLE) == before.value(*_SAMPLE)
    except (winprofile.ProfileError, struct.error, IndexError) as e:
        raise SyncError(f"geschriebene Kopie nicht lesbar ({e}) – nicht geändert") from None
    if not ok:
        raise SyncError(f"{SYNC_VALUE} fehlt in der geschriebenen Kopie – nicht geändert")
    if not same or not sample:
        raise SyncError("geschriebene Kopie weicht ab (andere Werte verändert) – nicht geändert")
    if not after.clean():
        raise SyncError("geschriebene Kopie nicht sauber abgeschlossen – nicht geändert")


def _write_back(path: Path, new: bytes, orig: bytes) -> None:
    """Geprüfte Kopie ins Original schreiben (dieselbe Datei – Rechte bleiben); bei einem Fehler das Original."""
    try:
        with open(path, "r+b") as f:
            f.write(new)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        if path.read_bytes() != new:
            raise OSError("Inhalt nach dem Schreiben anders")
    except OSError as e:
        try:
            with open(path, "r+b") as f:
                f.write(orig)
                f.truncate()
        except OSError as e2:
            raise SyncError(f"Registrierung SOFTWARE nicht geschrieben ({e}) und Original nicht zurückgelegt "
                            f"({e2}) – Windows startet so evtl. nicht") from None
        raise SyncError(f"Registrierung SOFTWARE nicht geschrieben ({e}) – Original zurückgelegt") from None


def set_sync_policy(root: Path, run: Callable | None = None) -> dict:
    """SyncForegroundPolicy = 1 im Hive SOFTWARE setzen, Stand von vorher sichern (root = Windows-Partition).

    Ist der Stand schon gesichert (anderes bzw. ersetztes Okula-Startskript steht noch aus), bleibt die Sicherung –
    sie gibt den Stand vor dem ersten Startskript wieder. Ergebnis {"sync": "set"} bzw. {"sync": "kept"}; jeder
    Fehler als SyncError, der Hive bleibt dann unverändert."""
    config = find_ci(root, "Windows/System32/config")
    hive_path = find_ci(config, "SOFTWARE") if config else None
    gp = find_ci(root, "Windows/System32/GroupPolicy")
    if hive_path is None or not hive_path.is_file() or gp is None:
        raise SyncError("Registrierung SOFTWARE nicht gefunden")
    saved = find_ci(gp, SYNC_SAVED) or gp / SYNC_SAVED
    orig = hive_path.read_bytes()
    try:
        hive = winprofile.Hive(orig)
        current = hive.value(SYNC_KEY, SYNC_VALUE)
        before = hive.values(SYNC_KEY)
        parts = SYNC_KEY.split("\\")
        present: list[str] = []                    # vorhandener Anfang des Pfads, der Rest wird angelegt
        for part in parts:
            if hive.find_key("\\".join(present + [part])) is None:
                break
            present.append(part)
    except (winprofile.ProfileError, struct.error, IndexError) as e:
        raise SyncError(f"Registrierung SOFTWARE nicht lesbar ({e})") from None
    if current == SYNC_ON:
        if not saved.is_file():                    # war schon an (eigene Richtlinie) – nur den Stand sichern
            _write_file(saved, (sync_saved_text(current) + "\r\n").encode("ascii"))
            return {"sync": "set"}
        return {"sync": "kept"}
    if not hive.clean():
        raise SyncError("Registrierung SOFTWARE nicht sauber geschlossen (Windows nicht ganz heruntergefahren?) – "
                        "nicht geändert")
    note = None if saved.is_file() else sync_saved_text(current)
    others = [(n, k, d) for n, k, d in before or [] if n.lower() != SYNC_VALUE.lower()]
    for name, _k, _d in others:
        if name and (name == "@" or not _REG_NAME_RE.match(name)):
            raise SyncError(f"Wert „{name}“ unter {SYNC_KEY} lässt sich nicht sicher mitschreiben – nicht geändert")
    if not shutil.which("hivexsh"):
        raise SyncError("hivexsh fehlt auf dem Agent (Paket libhivex-bin) – Agent-Stick neu erstellen")
    commands = hivexsh_commands(present, parts[len(present):], others + [(SYNC_VALUE, *SYNC_ON)])
    work = hive_path.with_name(hive_path.name + ".okula-tmp")
    if note is not None:
        _write_file(saved, (note + "\r\n").encode("ascii"))
    try:
        work.write_bytes(orig)
        try:
            r = (run or subprocess.run)(["hivexsh", "-w", str(work)], input=commands, capture_output=True,
                                        text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            raise SyncError(f"hivexsh nicht ausgeführt ({e}) – nicht geändert") from None
        if r.returncode != 0:
            raise SyncError(f"hivexsh: {(r.stderr or r.stdout or '').strip()[:200]} – nicht geändert")
        new = work.read_bytes()
        _check_sync_hive(hive, new)
        _write_back(hive_path, new, orig)
    except Exception:
        if note is not None:
            saved.unlink(missing_ok=True)
        raise
    finally:
        work.unlink(missing_ok=True)
    return {"sync": "set"}


def sync_result(root: Path, log: Callable[[str], None]) -> dict:
    """set_sync_policy für tweak/software: Fehler nur als Hinweis (das Startskript liegt schon)."""
    try:
        return set_sync_policy(root)
    except Exception as e:      # nie den Auftrag abbrechen – das Startskript liegt schon
        why = str(e) if isinstance(e, ImagingError) else f"{type(e).__name__}: {e}"
        log(f"Hinweis: {SYNC_VALUE} nicht gesetzt – {why}")
        return {"sync_error": why}


def _windows_system(m: filebackup.Mounts, disk: str) -> tuple[str, Path]:
    """(Partition, Wurzel) des einzigen Windows auf der Disk – Ruhezustand/Schnellstart wird gemeldet."""
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
        if windows_state(root):
            found.append((part["path"], root))
    if not found:
        raise ImagingError(f"Kein Windows auf {disk} gefunden – nichts geändert")
    if len(found) > 1:
        raise ImagingError(f"Mehrere Windows-Installationen auf {disk} – nicht eindeutig, nichts geändert")
    return found[0]


def tweak(req: dict, log: Callable[[str], None] = print) -> dict:
    """Windows anpassen: Skript vom Tool als einmaliges Startskript ablegen (Inhalt wird nie protokolliert)."""
    disk = str(req.get("disk") or "")
    script = str(req.get("script") or "")
    if not script.strip():
        raise ImagingError("Keine Einstellungen gewählt")
    if len(script) > MAX_SCRIPT:
        raise ImagingError("Skript zu gross")
    with filebackup.Mounts(write=True) as m:
        part, root = _windows_system(m, disk)
        state = windows_state(root)
        result = install_startup_script(root, script)
        result.update(sync_result(root, log))           # B-019: Anmeldung wartet auf das Startskript
        subprocess.run(["sync"])
    log(f"Windows anpassen {part}: Startskript " + ("ersetzt" if result["replaced"] else "abgelegt") +
        (" (lokale Gruppenrichtlinie ergänzt)" if result["gpo"] else "") +
        (f", {SYNC_VALUE} gesetzt" if result.get("sync") else ""))
    return {"type": "done", "part": part, "state": state, **result}


# ---------- Software installieren (I-020): Installer nach ProgramData, Startskript ----------

def _software_item(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if not name or len(p.parts) != 1 or p.is_absolute() or name in (".", "..") or name.startswith(".") \
            or name.lower() == SOFTWARE_NAME + ".ps1":
        raise ImagingError(f"Ungültiger Eintrag: {name}")
    return p


def software_dir(root: Path) -> Path:
    """ProgramData/Okula/Software auf der Windows-Partition (angelegt; Links werden abgelehnt)."""
    cur = root
    for part in PurePosixPath(SOFTWARE_REL).parts:
        cur = _dir_ci(cur, part)
        cur.mkdir(exist_ok=True)
    return cur


def software(sock, req: dict, log: Callable[[str], None] = print, report: Report | None = None) -> None:
    """Gewählte Installer empfangen, nach ProgramData/Okula/Software legen und das Startskript ablegen.

    Erst wenn alles angekommen ist, ersetzt die neue Auswahl eine noch nicht installierte von vorher (deren Reste
    werden gelöscht – das neue Skript kennt sie nicht). Das Skript (vom Tool, software.build_script) installiert beim
    nächsten Windows-Start als SYSTEM."""
    report = report or (lambda f, p, n: None)
    items = [_software_item(str(i)) for i in req.get("items") or []]
    script = str(req.get("script") or "")
    if not items:
        raise ImagingError("Keine Software gewählt")
    if not script.strip() or len(script) > MAX_SCRIPT:
        raise ImagingError("Installationsskript fehlt oder ist zu gross")
    total = int(req.get("bytes") or 0) or 1
    with filebackup.Mounts(write=True) as m:
        part, root = _windows_system(m, str(req.get("disk") or ""))
        state = windows_state(root)
        target = software_dir(root)
        stage = target / f"{STAGE_PREFIX}{secrets.token_hex(4)}"
        stage.mkdir()
        try:
            files, received = _receive_into(sock, stage, items, total, report)
            for old in list(target.iterdir()):
                if old == stage:
                    continue
                if old.is_dir() and not old.is_symlink():
                    shutil.rmtree(old)
                else:
                    old.unlink()
            for item in items:
                src = stage / item
                if not src.exists():
                    raise ImagingError(f"{item} wurde nicht übertragen")
                src.rename(target / item)
            result = install_startup_script(root, script, SOFTWARE_NAME, SOFTWARE_CMD_TEXT)
            result.update(sync_result(root, log))       # B-019: Anmeldung wartet auf das Startskript
            subprocess.run(["sync"])
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    wire.send_json(sock, {"type": "done", "part": part, "state": state, "files": files, "bytes": received,
                          **result})
    log(f"Software {part}: {len(items)} Einträge ({files} Dateien) nach {SOFTWARE_REL}, Startskript "
        + ("ersetzt" if result["replaced"] else "abgelegt"))


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
