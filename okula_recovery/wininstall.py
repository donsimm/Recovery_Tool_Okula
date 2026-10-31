"""Windows-Direktinstallation – Agent-Seite: Zieldisk vorbereiten und Setup-Partition füllen.

Layout (GPT):  1 EFI (FAT32)  ·  2 MSR  ·  3 Windows (NTFS + Marker)  ·  4 Setup (FAT32, am Ende)
Die Dateien kommen vom Tool (Steuerverbindung, SHA-256 je Datei). Danach zeigt BootNext einmalig auf die
Setup-Partition; dort installiert die Windows-Setup-Umgebung per dism/bcdboot (siehe winsetup.py im Tool).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Callable

from okula_recovery import imaging, wire

EFI_DIR = Path("/sys/firmware/efi")
WORK = Path("/run/okula-install")
MIB = 1024 * 1024
ESP_MIB, MSR_MIB = 260, 16
GPT_ESP = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
GPT_MSR = "E3C9E316-0B5C-4DB8-817D-F92DF00215AE"
GPT_DATA = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
SETUP_LABEL = "OKULASETUP"
MIN_WIN_MIB = 20 * 1024                  # Platz für Windows selbst

Report = Callable[[float, str, int], None]
ImagingError = imaging.ImagingError


def layout(disk_size: int, setup_size: int, min_disk: int) -> str:
    """sfdisk-Skript; die Setup-Partition liegt am Ende, damit Windows sie später an C: anhängen kann."""
    if disk_size < min_disk:
        raise ImagingError(f"Zieldisk zu klein: {disk_size / 1000**3:.0f} GB (mind. {min_disk / 1000**3:.0f} GB)")
    setup_mib = -(-setup_size // MIB)
    win_mib = disk_size // MIB - 1 - ESP_MIB - MSR_MIB - setup_mib - 2  # Start bei 1 MiB, GPT-Kopie am Ende
    if win_mib < MIN_WIN_MIB:
        raise ImagingError("Zieldisk zu klein für Windows und die Setup-Dateien")
    return (f"label: gpt\n"
            f'start=2048, size={ESP_MIB}MiB, type={GPT_ESP}, name="EFI system partition"\n'
            f'size={MSR_MIB}MiB, type={GPT_MSR}, name="Microsoft reserved partition"\n'
            f'size={win_mib}MiB, type={GPT_DATA}, name="Windows"\n'
            f'type={GPT_DATA}, name="Okula Setup"\n')


def _run(cmd: list[str], input: str | None = None) -> str:
    r = subprocess.run(cmd, input=input, capture_output=True, text=True)
    if r.returncode != 0:
        raise ImagingError(f"{os.path.basename(cmd[0])}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
    return r.stdout


# Einzeln austauschbar (Tests ohne FAT/NTFS im Kernel)
def _mkfat(part: str, label: str) -> None:
    _run(["mkfs.vfat", "-F", "32", "-n", label, part])


def _mkntfs(part: str, label: str) -> None:
    _run(["mkntfs", "-Q", "-F", "-L", label, part])


def _mkstage(part: str) -> None:
    _run(["mkfs.ext4", "-q", "-F", "-L", "OKULASTAGE", part])


def _mount(part: str, where: Path, ntfs: bool = False) -> None:
    where.mkdir(parents=True, exist_ok=True)
    _run(["ntfs-3g", part, str(where)] if ntfs else ["mount", part, str(where)])


def _umount(where: Path) -> None:
    subprocess.run(["umount", str(where)], capture_output=True)


def efibootmgr(*args: str) -> str:
    return _run(["efibootmgr", *args])


# ---------- Startreihenfolge: Netzwerkstart zuerst (Fernsteuerung über das Tool) ----------

BOOT_LINE = re.compile(r"^Boot([0-9A-Fa-f]{4})(\*?)\s+(.*)$")
NET_LABEL = re.compile(r"PXE|\bIPv?4\b|\bNetwork\b|\bNIC\b|\bLAN\b", re.I)  # nicht „Generic“ o. ä.
NOT_NET = re.compile(r"IPv6|IPV6|IP6|HTTP|Uri\(", re.I)


def parse_boot(out: str) -> dict:
    """efibootmgr -v → {current, order, entries: {nummer: (aktiv, text)}}."""
    info = {"current": "", "order": [], "entries": {}}
    for line in out.splitlines():
        if line.startswith("BootCurrent:"):
            info["current"] = line.split(":", 1)[1].strip()
        elif line.startswith("BootOrder:"):
            info["order"] = [n.strip().upper() for n in line.split(":", 1)[1].split(",") if n.strip()]
        else:
            m = BOOT_LINE.match(line.strip())
            if m:
                info["entries"][m.group(1).upper()] = (m.group(2) == "*", m.group(3))
    return info


def network_entry(info: dict) -> str:
    """Starteintrag für den Netzwerkstart per IPv4 (PXE), sonst ""; kein IPv6/HTTP-Boot."""
    candidates = []
    for num, (active, text) in info["entries"].items():
        if NOT_NET.search(text):
            continue
        if ("MAC(" in text and "IPv4(" in text) or NET_LABEL.search(text.split("\t")[0]):
            candidates.append((0 if "IPv4(" in text else 1, 0 if active else 1, num))
    return min(candidates)[2] if candidates else ""


def boot_status() -> dict:
    """Für das Tool: UEFI? Netzwerkeintrag? Steht er an erster Stelle?"""
    if not Path("/sys/firmware/efi").is_dir():
        return {"uefi": False, "message": "Gerät startet im BIOS-Modus – Startreihenfolge nur im BIOS-Setup änderbar"}
    info = parse_boot(efibootmgr("-v"))
    net = network_entry(info)
    labels = {n: t.split("\t")[0].split("  ")[0][:60] for n, (_a, t) in info["entries"].items()}
    return {"uefi": True, "order": info["order"], "network": net, "labels": labels,
            "netfirst": bool(net) and bool(info["order"]) and info["order"][0] == net}


def set_netfirst(on: bool, saved: list[str] | None = None) -> dict:
    """Netzwerkstart an die erste Stelle (on) bzw. zurück: gespeicherte Reihenfolge oder Netzwerk ans Ende."""
    status = boot_status()
    if not status["uefi"]:
        raise ImagingError(status["message"])
    net, order = status["network"], status["order"]
    if not net:
        raise ImagingError("Kein Netzwerk-Starteintrag (PXE IPv4) – im BIOS/UEFI-Setup den Netzwerkstart "
                           "(Network Stack, PXE) aktivieren")
    if on:
        new = [net] + [n for n in order if n != net]
    elif saved and set(saved) == set(order) and saved[0] != net:
        new = list(saved)
    else:
        new = [n for n in order if n != net] + [net]
    efibootmgr("--bootorder", ",".join(new))
    if on:
        efibootmgr("--active", "--bootnum", net)
    result = boot_status()
    result["previous"] = order
    return result


def set_bootnext(disk: str, part: int, label: str) -> str:
    """Starteintrag für die Setup-Partition anlegen und nur für den nächsten Start wählen."""
    before = set(re.findall(r"^Boot([0-9A-Fa-f]{4})", efibootmgr(), re.M))
    out = efibootmgr("--create-only", "--disk", disk, "--part", str(part),
                     "--loader", "\\EFI\\BOOT\\BOOTX64.EFI", "--label", label)
    new = [n for n in re.findall(r"^Boot([0-9A-Fa-f]{4})", out or efibootmgr(), re.M) if n not in before]
    if not new:
        raise ImagingError("Starteintrag für die Setup-Partition wurde nicht angelegt (efibootmgr)")
    efibootmgr("--bootnext", new[0])
    return new[0]


def _safe(root: Path, rel: str) -> Path:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ImagingError(f"Ungültiger Pfad: {rel}")
    return root.joinpath(*p.parts)


def _split(wim: Path, dest: Path, size_mb: int, total: int, progress: Callable[[float], None]) -> None:
    if not shutil.which("wimlib-imagex"):
        raise ImagingError("wimlib-imagex fehlt auf dem Agent-Stick – Stick mit aktuellem Tool neu erstellen")
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["wimlib-imagex", "split", str(wim), str(dest), str(size_mb)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tail = []

    def drain() -> None:  # Fortschrittsausgabe mitlesen, sonst läuft die Pipe voll
        while chunk := proc.stdout.read1(65536):
            tail[:] = [chunk[-4096:]]

    t = threading.Thread(target=drain, daemon=True)
    t.start()
    while proc.poll() is None:
        written = sum(p.stat().st_size for p in dest.parent.glob(dest.stem + "*.swm"))
        progress(min(1.0, written / max(total, 1)))
        time.sleep(1)
    t.join()
    proc.stdout.close()
    if proc.returncode != 0:
        msg = tail[0].decode(errors="replace").replace("\r", "\n").strip().splitlines() if tail else []
        raise ImagingError(f"wimlib-imagex split: {msg[-1] if msg else proc.returncode}")


def install(sock, req: dict, log: Callable[[str], None] = print, report: Report | None = None) -> str:
    """Zieldisk vorbereiten, Dateien empfangen, BootNext setzen. Gibt die Boot-Nummer zurück."""
    target = imaging._find_target(str(req.get("disk") or ""))
    disk = target["path"]
    mounted = [p["path"] for p in target["partitions"] if p["mounted"]]
    if mounted:
        raise ImagingError(f"Partition der Zieldisk ist eingehängt: {', '.join(mounted)}")
    if not EFI_DIR.is_dir():
        raise ImagingError("Gerät ist im BIOS-Modus gestartet – Direktinstallation braucht UEFI. "
                           "Im BIOS auf UEFI umstellen oder einen Boot-Stick verwenden.")
    files = req.get("files") or []
    split = req.get("split") or None
    table = layout(int(target["size"]), int(req.get("setup_size") or 0), int(req.get("min_disk") or 0))
    report = report or (lambda f, p, n: None)

    log(f"{disk} wird für die Windows-Installation partitioniert …")
    _run(["wipefs", "-a", disk])
    _run(["sfdisk", "--wipe", "always", disk], input=table)
    subprocess.run(["partx", "-u", disk], capture_output=True)
    parts = [imaging.partition_device(disk, n) for n in (1, 2, 3, 4)]
    imaging._wait_for(parts)
    esp, _msr, win, setup = parts
    _mkfat(esp, "SYSTEM")
    _mkfat(setup, SETUP_LABEL)
    setup_dir, stage_dir, win_dir = WORK / "setup", WORK / "stage", WORK / "windows"
    if split:
        _mkstage(win)  # grosse install.wim zuerst hier ablegen, dann geteilt auf die Setup-Partition
    _mount(setup, setup_dir)
    staged = None
    try:
        if split:
            _mount(win, stage_dir)
        wire.send_json(sock, {"type": "ready"})
        by_path = {f["path"]: int(f["size"]) for f in files}
        total = sum(by_path.values()) or 1
        received = 0
        while True:
            msg = wire.recv_json(sock)
            if msg.get("type") == "end":
                break
            path = str(msg.get("path") or "")
            if msg.get("type") != "file" or path not in by_path:
                raise ImagingError(f"Unerwartete Datei: {path}")
            dest = stage_dir / "install.wim" if split and path == split["path"] else _safe(setup_dir, path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            before = received
            with open(dest, "wb") as out:
                for chunk in imaging._frames(sock, {"file": path}):
                    out.write(chunk)
                    received += len(chunk)
                    report(0.85 * received / total, path, received)
                if by_path[path] > 64 * MIB:
                    out.flush()
                    os.fsync(out.fileno())
            if dest.name == "install.wim" and split:
                staged = dest
            received = before + by_path[path]
            wire.send_json(sock, {"type": "file_done", "path": path})
        if split:
            if staged is None:
                raise ImagingError("install.wim wurde nicht übertragen")
            log("install.wim wird in install.swm-Teile aufgeteilt …")
            swm = _safe(setup_dir, str(PurePosixPath(split["path"]).with_name("install.swm")))
            wim_size = staged.stat().st_size

            def split_progress(f: float) -> None:
                report(0.85 + 0.12 * f, "install.swm", received)
                wire.send_json(sock, {"type": "progress", "stage": "split", "fraction": f})

            _split(staged, swm, int(split.get("mb") or 3800), wim_size, split_progress)
        for rel, text in (req.get("extra") or {}).items():
            p = _safe(setup_dir, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        subprocess.run(["sync"])
    finally:
        _umount(setup_dir)
        if split:
            _umount(stage_dir)

    report(0.98, "Windows-Partition", received)
    _mkntfs(win, "OKULAWIN")
    _mount(win, win_dir, ntfs=True)
    try:
        (win_dir / str(req.get("target_marker") or "okula.target")).write_text("Okula Recovery Tool\n")
    finally:
        subprocess.run(["sync"])
        _umount(win_dir)
    entry = set_bootnext(disk, 4, str(req.get("boot_label") or "Okula Windows-Installation"))
    log(f"Setup-Partition bereit, nächster Start: Boot{entry}")
    report(1.0, "bereit", received)
    return entry


# ---------- Allgemein: Disk für eine Installation vorbereiten (Linux) ----------

FS_TYPES = ("fat32", "ext4")


def _mkext4(part: str, label: str) -> None:
    _run(["mkfs.ext4", "-q", "-F", "-L", label, part])


def bootprep(sock, req: dict, log: Callable[[str], None] = print, report: Report | None = None) -> str:
    """Partitionstabelle (vom Tool berechnet, GPT), Dateisysteme, Dateien je Partition, BootNext.

    req: table (sfdisk), parts [{number, fs, label, key}], files [{part, path, size}],
         extra [{part, path, text}], boot {part, loader, label}
    """
    target = imaging._find_target(str(req.get("disk") or ""))
    disk = target["path"]
    mounted = [p["path"] for p in target["partitions"] if p["mounted"]]
    if mounted:
        raise ImagingError(f"Partition der Zieldisk ist eingehängt: {', '.join(mounted)}")
    if not EFI_DIR.is_dir():
        raise ImagingError("Gerät ist im BIOS-Modus gestartet – Direktinstallation braucht UEFI. "
                           "Im BIOS auf UEFI umstellen oder einen Boot-Stick verwenden.")
    table = str(req.get("table") or "")
    if not table.startswith("label: gpt\n"):
        raise ImagingError("Ungültige Partitionstabelle")
    parts = req.get("parts") or []
    if not parts or any(p.get("fs") not in FS_TYPES for p in parts):
        raise ImagingError("Ungültige Partitionsangaben")
    boot = req.get("boot") or {}
    report = report or (lambda f, p, n: None)

    log(f"{disk} wird für die Installation partitioniert …")
    _run(["wipefs", "-a", disk])
    _run(["sfdisk", "--wipe", "always", disk], input=table)
    subprocess.run(["partx", "-u", disk], capture_output=True)
    devs = {p["key"]: imaging.partition_device(disk, int(p["number"])) for p in parts}
    imaging._wait_for(sorted(devs.values()))
    dirs = {}
    for p in parts:
        (_mkfat if p["fs"] == "fat32" else _mkext4)(devs[p["key"]], str(p.get("label") or "OKULA"))
    try:
        for p in parts:
            dirs[p["key"]] = WORK / p["key"]
            _mount(devs[p["key"]], dirs[p["key"]])
        wire.send_json(sock, {"type": "ready"})
        expected = {(f["part"], f["path"]): int(f["size"]) for f in req.get("files") or []}
        total = sum(expected.values()) or 1
        received = 0
        while True:
            msg = wire.recv_json(sock)
            if msg.get("type") == "end":
                break
            key = (str(msg.get("part") or ""), str(msg.get("path") or ""))
            if msg.get("type") != "file" or key not in expected or key[0] not in dirs:
                raise ImagingError(f"Unerwartete Datei: {key[1]}")
            dest = _safe(dirs[key[0]], key[1])
            dest.parent.mkdir(parents=True, exist_ok=True)
            before = received
            with open(dest, "wb") as out:
                for chunk in imaging._frames(sock, {"file": key[1]}):
                    out.write(chunk)
                    received += len(chunk)
                    report(0.97 * received / total, key[1], received)
                if expected[key] > 64 * MIB:
                    out.flush()
                    os.fsync(out.fileno())
            received = before + expected[key]
            wire.send_json(sock, {"type": "file_done", "path": key[1]})
        for x in req.get("extra") or []:
            if x.get("part") not in dirs:
                raise ImagingError(f"Unbekannte Partition für {x.get('path')}")
            p = _safe(dirs[x["part"]], str(x.get("path") or ""))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(x.get("text") or ""), encoding="utf-8")
        subprocess.run(["sync"])
    finally:
        for d in dirs.values():
            _umount(d)
    entry = set_bootnext(disk, int(boot.get("part") or 1), str(boot.get("label") or "Okula Installation"))
    log(f"Installation vorbereitet, nächster Start: Boot{entry}")
    report(1.0, "bereit", received)
    return entry
