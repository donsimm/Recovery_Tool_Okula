"""Bestehende Clonezilla-Images lesen und für das Zurückspielen aufbereiten.

Format (Clonezilla „savedisk“, ein Ordner pro Image), geprüft am Clonezilla-Quellcode:
    disk                         Namen der gesicherten Disks, z. B. „sda“
    parts                        gesicherte Partitionen, z. B. „sda1 sda2 sda5“
    sda-pt.sf                    Partitionstabelle (sfdisk -d)
    sda-pt.parted                parted -s … unit s print (Disk-Grösse)
    sda-mbr                      erste 512 Byte
    sda-hidden-data-after-mbr    Sektor 1 bis vor die erste Partition (MBR-Disks)
    sda1.ntfs-ptcl-img.gz.aa …   partclone-Image, komprimiert, evtl. gesplittet (.aa/.ab bzw. .aaa)
    sda2.dd-ptcl-img.zst         Rohkopie (partclone.dd)
    swappt-sda5.info             UUID/LABEL einer Swap-Partition
Nicht unterstützt: LVM, alte ntfsclone/partimage-Images (*.ntfs-img, *.ext4-img).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

COMPRESSION = {"gz": "gzip", "zst": "zstd", "bz2": "bzip2", "xz": "xz", "lzma": "xz", "lz4": "lz4",
               "lzo": "lzop", "uncomp": ""}
# Entpacker zum Prüfen auf dem Server (Clonezilla legt keine Prüfsummen ab)
DECOMPRESS = {"gzip": ["gzip", "-d", "-c"], "zstd": ["zstd", "-d", "-q", "-c"], "bzip2": ["bzip2", "-d", "-c"],
              "xz": ["xz", "-d", "-c"], "lz4": ["lz4", "-d", "-c"], "lzop": ["lzop", "-d", "-c"]}
PART_RE = re.compile(r"^(?P<part>[A-Za-z0-9_-]+?)\.(?P<fs>[a-z0-9+]+)-ptcl-img\.(?P<comp>[a-z0-9]+)"
                     r"(?:\.(?P<split>[a-z]{2,4}))?$")
OLD_FORMAT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[a-z0-9+]+-img(\.|$)")

Progress = Callable[[dict], None]

# Debian-Benutzer haben /usr/sbin nicht im PATH; partclone liegt dort
SBIN_DIRS = ("/usr/local/sbin", "/usr/sbin", "/sbin")


def find_tool(name: str) -> str | None:
    path = os.pathsep.join([os.environ.get("PATH", ""), *SBIN_DIRS])
    return shutil.which(name, path=path)


class ClonezillaError(Exception):
    pass


def is_clonezilla(path: Path) -> bool:
    return (path / "disk").is_file() and (path / "parts").is_file()


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def disks(path: Path) -> list[str]:
    return _read(path / "disk").split()


def partition_images(path: Path) -> dict[str, dict]:
    """part → {fs, compression, pieces[]} aus den Dateinamen."""
    result: dict[str, dict] = {}
    for f in sorted(path.iterdir()):
        m = PART_RE.match(f.name)
        if not m:
            continue
        comp = m.group("comp")
        if comp not in COMPRESSION:
            raise ClonezillaError(f"Kompression „{comp}“ wird nicht unterstützt ({f.name})")
        entry = result.setdefault(m.group("part"), {"fs": m.group("fs"), "compression": COMPRESSION[comp],
                                                    "pieces": []})
        entry["pieces"].append(f)
    for entry in result.values():
        # .aa < .ab < … und .aaa < .aab – sortiert nach Länge, dann alphabetisch
        entry["pieces"].sort(key=lambda p: (len(p.suffix), p.name))
    return result


def swap_info(path: Path, part: str) -> dict:
    text = _read(path / f"swappt-{part}.info")
    uuid = re.search(r'UUID="([^"]+)"', text)
    label = re.search(r'LABEL="([^"]+)"', text)
    return {"uuid": uuid.group(1) if uuid else "", "label": label.group(1) if label else ""}


def disk_size(path: Path, disk: str, sfdisk: str) -> int:
    """Grösse der Quelldisk: aus *-pt.parted, sonst Ende der letzten Partition (+ GPT-Backup)."""
    parted = _read(path / f"{disk}-pt.parted")
    sectors = re.search(r"^Disk /dev/\S+:\s*(\d+)s", parted, re.M)
    sector_size = re.search(r"Sector size \(logical/physical\):\s*(\d+)B", parted)
    if sectors:
        return int(sectors.group(1)) * int(sector_size.group(1) if sector_size else 512)
    ends = [int(s) + int(n) for s, n in re.findall(r"start=\s*(\d+),\s*size=\s*(\d+)", sfdisk)]
    return (max(ends) + 34) * 512 if ends else 0


def build(path: str | Path, disk: str) -> dict:
    """Quelle + Schritte für restore_image (Format wie bei Okula-Images, plus „pieces“)."""
    path = Path(path)
    if not is_clonezilla(path):
        raise ClonezillaError("Kein Clonezilla-Image (Dateien „disk“/„parts“ fehlen)")
    if disk not in disks(path):
        raise ClonezillaError(f"Disk {disk} ist nicht im Image")
    if any(path.glob("lvm_*")):
        raise ClonezillaError("Image enthält LVM – wird (noch) nicht unterstützt")
    parts = [p for p in _read(path / "parts").split() if p.startswith(disk)]
    images = partition_images(path)
    sfdisk = _read(path / f"{disk}-pt.sf")
    pttype = (re.search(r"^label:\s*(\S+)", sfdisk, re.M) or [None, ""])[1]

    steps, partitions, missing = [], [], []
    for part in parts:
        if (path / f"swappt-{part}.info").is_file():
            steps.append({"kind": "swap", "part": part, **swap_info(path, part)})
            partitions.append({"name": part, "fstype": "swap"})
            continue
        img = images.get(part)
        if img is None:
            if any(OLD_FORMAT_RE.match(f.name) for f in path.glob(f"{part}.*")):
                raise ClonezillaError(f"{part}: altes Clonezilla-Format (ntfsclone/partimage) wird nicht unterstützt")
            missing.append(part)
            continue
        kind = "dd" if img["fs"] == "dd" else "pcl"
        steps.append({"kind": kind, "variant": img["fs"], "part": part,
                      "file": f"{part}.{img['fs']}-ptcl-img", "compression": img["compression"],
                      "size": sum(p.stat().st_size for p in img["pieces"]), "pieces": img["pieces"]})
        partitions.append({"name": part, "fstype": "" if kind == "dd" else img["fs"]})
    if missing:
        raise ClonezillaError(f"Kein Image für Partition(en) {', '.join(missing)}")
    if not steps:
        raise ClonezillaError("Keine Partitions-Images gefunden")

    mbr = (path / f"{disk}-mbr")
    head = mbr.read_bytes()[:512] if mbr.is_file() else b""
    if len(head) < 440:
        raise ClonezillaError(f"{disk}-mbr fehlt")
    hidden = path / f"{disk}-hidden-data-after-mbr"
    if pttype == "dos" and hidden.is_file():
        head = head.ljust(512, b"\0") + hidden.read_bytes()

    source = {"name": disk, "size": disk_size(path, disk, sfdisk), "pttype": pttype, "model": "",
              "partitions": partitions}
    return {"source": source, "steps": steps, "sfdisk": sfdisk, "head": head, "format": "clonezilla",
            "label": f"Clonezilla {path.name} ({disk})"}


class _Tail(threading.Thread):
    """Liest stderr laufend mit (partclone schreibt ständig Fortschritt) und behält nur das Ende.

    Ohne Mitlesen läuft die Pipe (64 KB) voll, der Prüfer blockiert und die Prüfung hängt.
    """

    KEEP = 8192

    def __init__(self, stream):
        super().__init__(daemon=True)
        self.stream, self.tail = stream, b""
        self.start()

    def run(self) -> None:
        while chunk := self.stream.read1(65536):
            self.tail = (self.tail + chunk)[-self.KEEP:]

    def text(self) -> str:
        self.join()
        return self.tail.decode(errors="replace").replace("\r", "\n").strip()


def verify(source: dict, progress: Progress, cancel: threading.Event) -> None:
    """Entpackt jedes Partitions-Image auf dem Server und prüft es (partclone.chkimg bzw. Entpacker-CRC)."""
    steps = [s for s in source["steps"] if s.get("pieces")]
    total = sum(s["size"] for s in steps) or 1
    done = 0
    chkimg = find_tool("partclone.chkimg")
    if not chkimg and any(s["kind"] == "pcl" for s in steps):
        progress({"phase": "note", "message": "partclone.chkimg nicht gefunden – prüfe nur die Kompression (CRC)"})
    for s in steps:
        comp = s["compression"]
        cmds = [list(DECOMPRESS[comp])] if comp else []
        if s["kind"] == "pcl" and chkimg:
            cmds.append([chkimg, "-s", "-", "-L", "/dev/null"])
        elif comp:
            cmds[-1] = [cmds[-1][0], "-t"]  # nur Integrität der Kompression
        if not cmds:
            done += s["size"]
            continue
        procs = []
        stdin = subprocess.PIPE
        for i, argv in enumerate(cmds):
            argv = [find_tool(argv[0]) or argv[0], *argv[1:]]
            try:
                p = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE if i < len(cmds) - 1 else
                                     subprocess.DEVNULL, stderr=subprocess.PIPE)
            except FileNotFoundError:
                raise ClonezillaError(f"{os.path.basename(argv[0])} fehlt auf dem Server – "
                                      "install.sh erneut ausführen") from None
            if i > 0:
                procs[-1].stdout.close()
            procs.append(p)
            stdin = p.stdout
        tails = [_Tail(p.stderr) for p in procs]
        last = 0.0
        try:
            for piece in s["pieces"]:
                with open(piece, "rb") as fh:
                    while chunk := fh.read(1024 * 1024):
                        if cancel.is_set():
                            raise ClonezillaError("Abgebrochen")
                        procs[0].stdin.write(chunk)
                        done += len(chunk)
                        if time.monotonic() - last >= 0.5:
                            last = time.monotonic()
                            progress({"phase": "verify", "file": s["file"], "fraction": done / total})
        except BrokenPipeError:
            pass  # Prüfer ist ausgestiegen – Exit-Code unten
        finally:
            try:
                procs[0].stdin.close()
            except BrokenPipeError:
                pass
            for p in procs:
                if p.poll() is None and cancel.is_set():
                    p.kill()
        errors = [(p.args[0], p.wait(), t.text()) for p, t in zip(procs, tails)]
        for p in procs:
            p.stderr.close()
        failed = [(a, msg) for a, code, msg in errors if code]
        if failed:
            tool, msg = failed[-1]
            raise ClonezillaError(f"Image beschädigt: {s['part']} ({tool}: {msg.splitlines()[-1] if msg else 'Fehler'})")
