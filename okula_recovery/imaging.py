"""Agent-Seite: Disks erkennen und ein Disk-Image an das Tool streamen.

Ein Image besteht aus mehreren Dateien (werden vom Tool in einen Ordner geschrieben):
    <disk>.sfdisk          Partitionstabelle (sfdisk -d)
    <disk>-head.img        erstes MiB (MBR/GPT, Bootloader-Lücke)
    <disk>-tail.img        letztes MiB (GPT-Backup)
    <part>.<fs>.pcl[.zst]  partclone, nur belegte Blöcke
    <part>.dd.img[.zst]    unbekanntes/verschlüsseltes Dateisystem: alle Blöcke
Swap wird nicht gesichert, nur seine UUID/Label notiert.
Nur stdlib + externe Werkzeuge (lsblk, sfdisk, partclone, optional zstd).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Callable

from okula_recovery import wire

LIVE_MEDIUM = "/run/live/medium"
HEAD_TAIL = 1024 * 1024

# lsblk-FSTYPE → partclone-Variante
PARTCLONE = {
    "ext2": "extfs", "ext3": "extfs", "ext4": "extfs",
    "ntfs": "ntfs", "vfat": "fat", "exfat": "exfat",
    "btrfs": "btrfs", "xfs": "xfs", "hfsplus": "hfsp", "f2fs": "f2fs",
}
PROGRESS_RE = re.compile(rb"Completed:\s*([\d.]+)%")


class ImagingError(Exception):
    pass


def _flatten_mounts(dev: dict) -> list[str]:
    result = [m for m in dev.get("mountpoints") or [] if m]
    for child in dev.get("children") or []:
        result += _flatten_mounts(child)
    return result


def _partition(d: dict) -> dict:
    return {
        "name": d["name"], "path": d.get("path") or f"/dev/{d['name']}", "size": int(d.get("size") or 0),
        "fstype": d.get("fstype") or "", "label": d.get("label") or "", "uuid": d.get("uuid") or "",
        "parttype": d.get("parttype") or "", "mounted": bool([m for m in d.get("mountpoints") or [] if m]),
    }


def parse_disks(output: str) -> list[dict]:
    """Disks mit Partitionen aus `lsblk -J -b -o …`; der Boot-Stick selbst fällt weg."""
    try:
        devices = json.loads(output).get("blockdevices", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    disks = []
    for d in devices:
        if d.get("type") != "disk" or d["name"].startswith(("loop", "zram", "ram", "sr")):
            continue
        if any(m.startswith(LIVE_MEDIUM) for m in _flatten_mounts(d)):
            continue  # davon läuft das Live-System
        parts = [_partition(c) for c in d.get("children") or [] if c.get("type") == "part"]
        disks.append({
            "name": d["name"], "path": d.get("path") or f"/dev/{d['name']}", "size": int(d.get("size") or 0),
            "model": (d.get("model") or "").strip(), "serial": (d.get("serial") or "").strip(),
            "transport": d.get("tran") or "", "pttype": d.get("pttype") or "",
            "fstype": d.get("fstype") or "", "partitions": parts,
        })
    return disks


def list_disks() -> list[dict]:
    out = subprocess.run(["lsblk", "-J", "-b", "-o",
                          "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,PARTTYPE,MODEL,SERIAL,TRAN,PTTYPE,MOUNTPOINTS"],
                         capture_output=True, text=True, timeout=15).stdout
    return parse_disks(out)


def tool_status() -> dict:
    return {"partclone": bool(shutil.which("partclone.dd")), "zstd": bool(shutil.which("zstd")),
            "sfdisk": bool(shutil.which("sfdisk"))}


def partition_command(part: dict) -> tuple[str, list[str]] | None:
    """(Dateiendung, Befehl) für eine Partition; None = nicht sichern (Swap)."""
    fs = part["fstype"]
    if fs == "swap":
        return None
    variant = PARTCLONE.get(fs)
    if variant and shutil.which(f"partclone.{variant}"):
        return f"{fs}.pcl", [f"partclone.{variant}", "-c", "-s", part["path"], "-o", "-"]
    # unbekannt, verschlüsselt (BitLocker/LUKS), LVM …: Rohkopie aller Blöcke
    return "dd.img", ["partclone.dd", "-s", part["path"], "-o", "-"]


def make_plan(disk: dict, compress: bool) -> list[dict]:
    if not shutil.which("partclone.dd"):
        raise ImagingError("partclone fehlt auf dem Agent-Stick – Stick mit aktuellem Tool neu erstellen")
    mounted = [p["path"] for p in disk["partitions"] if p["mounted"]]
    if mounted:
        raise ImagingError(f"Partition ist eingehängt: {', '.join(mounted)}")
    name, path = disk["name"], disk["path"]
    plan: list[dict] = [
        {"file": f"{name}.sfdisk", "kind": "command", "cmd": ["sfdisk", "-d", path], "optional": True},
        {"file": f"{name}-head.img", "kind": "range", "path": path, "offset": 0, "length": HEAD_TAIL},
        {"file": f"{name}-tail.img", "kind": "range", "path": path,
         "offset": max(0, disk["size"] - HEAD_TAIL), "length": HEAD_TAIL},
    ]
    parts = disk["partitions"] or ([{**disk, "label": "", "uuid": "", "parttype": "", "mounted": False}]
                                   if disk["fstype"] else [])
    for p in parts:
        cmd = partition_command(p)
        if cmd is None:
            plan.append({"file": None, "kind": "skip", "part": p["name"], "reason": "swap",
                         "uuid": p.get("uuid", ""), "label": p.get("label", "")})
            continue
        ext, argv = cmd
        suffix = ".zst" if compress else ""
        plan.append({"file": f"{p['name']}.{ext}{suffix}", "kind": "pipe", "part": p["name"],
                     "size": p["size"], "fstype": p["fstype"], "cmds": [argv] +
                     ([["zstd", "-1", "-T0", "-q", "-c"]] if compress else [])})
    return plan


class _Progress:
    """Liest stderr von partclone mit und merkt sich den letzten Prozentwert."""

    def __init__(self, stream):
        self.pct: float | None = None
        self.tail = b""
        self._thread = threading.Thread(target=self._read, args=(stream,), daemon=True)
        self._thread.start()

    def _read(self, stream) -> None:
        while chunk := stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096):
            self.tail = (self.tail + chunk)[-4096:]
            matches = PROGRESS_RE.findall(chunk)
            if matches:
                self.pct = float(matches[-1])

    def join(self) -> None:
        self._thread.join(timeout=5)


def _send_file(sock, name: str, chunks, info: dict, on_tick: Callable[[int], dict],
               check: Callable[[], None] | None = None) -> None:
    """Sendet eine Datei; check() läuft nach den Daten und vor file_end (Exit-Codes prüfen)."""
    wire.send_json(sock, {"type": "file", "file": name, **info})
    h = hashlib.sha256()
    size = 0
    last = time.monotonic()
    for chunk in chunks:
        h.update(chunk)
        size += len(chunk)
        wire.send_data(sock, chunk)
        if time.monotonic() - last >= 1.0:
            last = time.monotonic()
            wire.send_json(sock, {"type": "progress", "file": name, "bytes": size, **on_tick(size)})
    if check:
        check()
    wire.send_json(sock, {"type": "file_end", "file": name, "size": size, "sha256": h.hexdigest()})


def _read_range(path: str, offset: int, length: int):
    with open(path, "rb") as f:
        f.seek(offset)
        yield f.read(length)


def _run_pipe(cmds: list[list[str]]):
    procs = []
    stdin = None
    for i, argv in enumerate(cmds):
        p = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE if i == 0 else subprocess.DEVNULL)
        if stdin is not None:
            stdin.close()  # nur der nächste Prozess hält die Pipe
        stdin = p.stdout
        procs.append(p)
    return procs


def stream_disk_image(sock, disk_path: str, log: Callable[[str], None] = print) -> None:
    disk = {d["path"]: d for d in list_disks()}.get(disk_path)
    if disk is None:
        raise ImagingError(f"Disk {disk_path} nicht gefunden")
    compress = bool(shutil.which("zstd"))
    plan = make_plan(disk, compress)
    wire.send_json(sock, {"type": "begin", "disk": disk, "plan": plan, "compression": "zstd" if compress else ""})

    for step in plan:
        if step["kind"] == "skip":
            continue
        name = step["file"]
        if step["kind"] == "range":
            _send_file(sock, name, _read_range(step["path"], step["offset"], step["length"]), {}, lambda n: {})
        elif step["kind"] == "command":
            r = subprocess.run(step["cmd"], capture_output=True, timeout=60)
            if r.returncode != 0:
                if step.get("optional"):
                    continue
                raise ImagingError(r.stderr.decode(errors="replace").strip())
            _send_file(sock, name, [r.stdout], {}, lambda n: {})
        else:
            log(f"Sichere {step['part']} ({step['fstype'] or 'unbekannt'}) …")
            procs = _run_pipe(step["cmds"])
            progress = _Progress(procs[0].stderr)
            out = procs[-1].stdout

            def chunks():
                while chunk := out.read(wire.CHUNK):
                    yield chunk

            def check():
                codes = [p.wait() for p in procs]
                progress.join()
                if any(codes):
                    msg = progress.tail.decode(errors="replace").replace("\r", "\n").strip().splitlines()
                    raise ImagingError(f"{step['cmds'][0][0]} für {step['part']} fehlgeschlagen: "
                                       f"{msg[-1] if msg else codes}")

            try:
                _send_file(sock, name, chunks(), {"part": step["part"], "total": step["size"]},
                           lambda n: {"part": step["part"], "pct": progress.pct}, check)
            finally:
                for p in procs:
                    if p.poll() is None:
                        p.kill()
                    p.wait()
                progress.join()
                for p in procs:
                    for stream in (p.stdout, p.stderr):
                        if stream:
                            stream.close()
    wire.send_json(sock, {"type": "end"})
