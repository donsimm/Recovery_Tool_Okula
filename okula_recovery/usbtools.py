"""USB-Datenträger klonen und formatieren (Menü Tools). Läuft als root über den Stick-Helfer:

    sudo okula-make-stick usb-clone --source /dev/sdb --target /dev/sdc --mode smart [--verify]
    sudo okula-make-stick usb-format --device /dev/sdb --fs exfat --scheme mbr --label DATEN [--prep quick]

Klonen:
- smart: Partitionstabelle übernehmen, je Partition nur belegte Blöcke (partclone -b, Gerät → Gerät);
  unbekannte Dateisysteme werden 1:1 kopiert. Das Ziel darf kleiner sein, solange alle Partitionen passen.
- raw: ganzer Datenträger Sektor für Sektor (auch verschlüsselt oder unbekannt), optional Lesevergleich.
Bei GPT auf einem grösseren Ziel wird die Reserve-Tabelle ans Ende verschoben.

Formatieren: FAT32, FAT16, exFAT, NTFS, ext4/3/2, Btrfs, XFS, F2FS, HFS+, UDF oder nur leeren; MBR, GPT oder
ohne Partitionstabelle. Vorher wahlweise Schnelltest (gefälschte Sticks), Nullen schreiben oder badblocks.

Nur Datenträger aus stick.list_usb_disks() (USB/Wechseldatenträger, keine Systemdisk).
Ausgabe zeilenweise: PROGRESS <0..1> <Text> / WARN / DONE / ERROR. Abbrechen: Zeile „CANCEL“ auf stdin.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from okula_recovery import stick
from okula_recovery.stick import StickError

Emit = Callable[[str, str], None]
Progress = Callable[[float, str], None]

CHUNK = 4 * 1024 * 1024
SBIN = ("/usr/sbin", "/sbin", "/usr/bin", "/bin")
GPT_BASIC_DATA = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
GPT_LINUX = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
GPT_HFSPLUS = "48465300-0000-11AA-AA11-00306543ECAC"
MBR_LIMIT = 2 * 1024**4  # MBR adressiert mit 512-Byte-Sektoren höchstens 2 TiB

# lsblk-FSTYPE → partclone-Variante (gleich wie beim Disk-Image)
PARTCLONE = {"ext2": "extfs", "ext3": "extfs", "ext4": "extfs", "ntfs": "ntfs", "vfat": "fat", "exfat": "exfat",
             "btrfs": "btrfs", "xfs": "xfs", "hfsplus": "hfsp", "f2fs": "f2fs"}
PARTCLONE_RE = re.compile(rb"Completed:\s*([\d.]+)%")
EXTENDED_TYPES = {"5", "f", "85"}


def find_tool(name: str) -> str | None:
    """Auch in /usr/sbin suchen – der Benutzer hat das oft nicht im PATH."""
    return shutil.which(name) or shutil.which(name, path=os.pathsep.join(SBIN))


# ---------- Dateisysteme ----------

@dataclass(frozen=True)
class FsSpec:
    key: str
    title: str
    tool: str               # mkfs-Programm (Verfügbarkeit)
    package: str            # Debian-Paket
    label_max: int          # Länge des Datenträgernamens
    mbr_type: str
    gpt_type: str
    note: str               # wofür, in einfacher Sprache
    upper: bool = False     # Name nur in Grossbuchstaben (FAT)
    linux: bool = False     # Besitzer des Wurzelordners auf den Benutzer setzen
    max_size: int = 0       # grösster sinnvoller Datenträger (0 = egal)
    min_size: int = 0


FILESYSTEMS: dict[str, FsSpec] = {s.key: s for s in (
    FsSpec("fat32", "FAT32", "mkfs.vfat", "dosfstools", 11, "c", GPT_BASIC_DATA,
           "Läuft fast überall: Windows, Mac, Linux, TV, Auto, Drucker. Einzelne Dateien höchstens 4 GB.",
           upper=True, min_size=33 * 1024**2),
    FsSpec("exfat", "exFAT", "mkfs.exfat", "exfatprogs", 15, "7", GPT_BASIC_DATA,
           "Für grosse Dateien über 4 GB; Windows, Mac, Linux und viele neuere TVs. Gut für Sticks und "
           "externe Festplatten zum Austauschen."),
    FsSpec("ntfs", "NTFS", "mkfs.ntfs", "ntfs-3g", 32, "7", GPT_BASIC_DATA,
           "Windows-Standard für Festplatten. Mac kann nur lesen, Linux lesen und schreiben."),
    FsSpec("ext4", "ext4", "mkfs.ext4", "e2fsprogs", 16, "83", GPT_LINUX,
           "Linux-Standard. Windows und Mac können es ohne Zusatzprogramm nicht lesen.", linux=True),
    FsSpec("btrfs", "Btrfs", "mkfs.btrfs", "btrfs-progs", 255, "83", GPT_LINUX,
           "Modernes Linux-Dateisystem mit Prüfsummen und Schnappschüssen. Nur Linux.", linux=True,
           min_size=128 * 1024**2),
    FsSpec("xfs", "XFS", "mkfs.xfs", "xfsprogs", 12, "83", GPT_LINUX,
           "Linux-Dateisystem für sehr grosse Festplatten und Dateien. Nur Linux.", linux=True,
           min_size=300 * 1024**2),
    FsSpec("f2fs", "F2FS", "mkfs.f2fs", "f2fs-tools", 512, "83", GPT_LINUX,
           "Für Flash-Speicher unter Linux und Android (z. B. SD-Karten). Nur Linux/Android.", linux=True),
    FsSpec("ext3", "ext3", "mkfs.ext3", "e2fsprogs", 16, "83", GPT_LINUX,
           "Älteres Linux-Dateisystem, für alte Linux-Geräte.", linux=True),
    FsSpec("ext2", "ext2", "mkfs.ext2", "e2fsprogs", 16, "83", GPT_LINUX,
           "Sehr altes Linux-Dateisystem ohne Journal, z. B. für Boot-Partitionen.", linux=True),
    FsSpec("hfsplus", "HFS+ (Mac OS Extended)", "mkfs.hfsplus", "hfsprogs", 255, "af", GPT_HFSPLUS,
           "Ältere Macs und Time Machine auf alten macOS-Versionen. Windows liest es nicht."),
    FsSpec("udf", "UDF", "mkudffs", "udftools", 30, "7", GPT_BASIC_DATA,
           "Für grosse Dateien; Windows, Mac und Linux lesen und schreiben (Windows erst ab Vista).",
           ),
    FsSpec("fat16", "FAT16", "mkfs.vfat", "dosfstools", 11, "e", GPT_BASIC_DATA,
           "Für sehr alte Geräte (alte Kameras, BIOS-Updates). Datenträger höchstens 4 GB.",
           upper=True, max_size=4 * 1024**3),
    FsSpec("none", "Kein Dateisystem – nur leeren", "wipefs", "util-linux", 0, "", "",
           "Löscht Partitionstabelle und Dateisystem-Kennungen. Der Datenträger ist danach leer und "
           "muss vor dem Gebrauch neu formatiert werden."),
)}


def available(spec: FsSpec) -> bool:
    return find_tool(spec.tool) is not None


def clean_label(spec: FsSpec, label: str) -> str:
    """Datenträgername passend machen: Länge, bei FAT Grossbuchstaben ohne Sonderzeichen."""
    label = label.strip()
    if spec.upper:
        label = re.sub(r"[^A-Z0-9 _-]", "_", label.upper())
    return label[:spec.label_max] if spec.label_max else ""


def mkfs_command(spec: FsSpec, part: str, label: str) -> list[str]:
    tool = find_tool(spec.tool) or spec.tool
    lbl = clean_label(spec, label)
    if spec.key in ("fat32", "fat16"):
        return [tool, "-F", spec.key[3:], "-I", *(["-n", lbl] if lbl else []), part]
    if spec.key == "exfat":
        return [tool, *(["-L", lbl] if lbl else []), part]
    if spec.key == "ntfs":
        return [tool, "-Q", "-F", *(["-L", lbl] if lbl else []), part]
    if spec.key in ("ext4", "ext3", "ext2"):
        return [tool, "-F", "-q", *(["-L", lbl] if lbl else []), part]
    if spec.key in ("btrfs", "xfs"):
        return [tool, "-f", *(["-L", lbl] if lbl else []), part]
    if spec.key == "f2fs":
        return [tool, "-f", "-q", *(["-l", lbl] if lbl else []), part]
    if spec.key == "hfsplus":
        return [tool, *(["-v", lbl] if lbl else []), part]
    if spec.key == "udf":
        return [tool, "--utf8", "--media-type=hd", *([f"--label={lbl}", f"--vid={lbl}"] if lbl else []), part]
    raise StickError(f"Unbekanntes Dateisystem: {spec.key}")


def partition_table(spec: FsSpec, scheme: str) -> str | None:
    """sfdisk-Eingabe für eine Partition über den ganzen Datenträger; None = ohne Partitionstabelle."""
    if scheme == "none":
        return None
    if scheme == "gpt":
        return f"label: gpt\nstart=2048, type={spec.gpt_type}\n"
    return f"label: dos\nstart=2048, type={spec.mbr_type}\n"


# ---------- gemeinsame Bausteine ----------

def _run(cmd: list[str], input: str | None = None) -> str:
    r = subprocess.run(cmd, input=input, capture_output=True, text=True)
    if r.returncode != 0:
        raise StickError(f"{Path(cmd[0]).name}: {(r.stderr or r.stdout).strip()[-600:]}")
    return r.stdout


def _settle(device: str) -> None:
    subprocess.run(["partx", "-u", device], capture_output=True)  # bestehende anpassen, entfernte löschen
    subprocess.run(["partx", "-a", device], capture_output=True)  # neue (auch logische) anlegen
    subprocess.run(["udevadm", "settle"], capture_output=True)


def _wait_for(path: str) -> None:
    for _ in range(50):
        if Path(path).exists():
            return
        time.sleep(0.2)
    raise StickError(f"{path} erscheint nicht")


def _usb_disk(device: str) -> stick.UsbDisk:
    disk = {d.path: d for d in stick.list_usb_disks()}.get(device)
    if disk is None:
        raise StickError(f"{device} ist kein auswählbarer USB-Datenträger (Systemdisk oder nicht eingesteckt)")
    return disk


def _unmount(disk: stick.UsbDisk, progress: Progress) -> None:
    for mp in sorted(disk.mountpoints, reverse=True):
        progress(0.0, f"{mp} wird ausgehängt")
        r = subprocess.run(["umount", mp], capture_output=True, text=True)
        if r.returncode != 0:
            raise StickError(f"{mp} lässt sich nicht aushängen (noch geöffnet?): {r.stderr.strip()}")


def sector_size(device: str) -> int:
    try:
        return int(_run(["blockdev", "--getss", device]).strip())
    except (StickError, ValueError):
        return 512


def device_size(device: str) -> int:
    fd = os.open(device, os.O_RDONLY)
    try:
        return os.lseek(fd, 0, os.SEEK_END)
    finally:
        os.close(fd)


def _drop(fd: int) -> None:
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    except (AttributeError, OSError):
        pass


def rate_text(done: int, total: int, started: float) -> str:
    """„1.2 / 32.0 GB · 85 MB/s · noch 6 min“."""
    elapsed = max(time.monotonic() - started, 0.001)
    speed = done / elapsed
    text = f"{done / 1000**3:.1f} / {total / 1000**3:.1f} GB · {speed / 1000**2:.0f} MB/s"
    if speed > 0 and done < total and elapsed > 3:
        rest = (total - done) / speed
        text += f" · noch {rest / 60:.0f} min" if rest >= 90 else f" · noch {rest:.0f} s"
    return text


def copy_range(src: str, dst: str, length: int, progress: Progress, what: str,
               src_off: int = 0, dst_off: int = 0) -> None:
    """length Bytes von src (ab src_off) nach dst (ab dst_off) kopieren, Cache laufend freigeben."""
    fin, fout = os.open(src, os.O_RDONLY), os.open(dst, os.O_WRONLY)
    try:
        done, started, last, since_sync = 0, time.monotonic(), 0.0, 0
        while done < length:
            n = min(CHUNK, length - done)
            data = os.pread(fin, n, src_off + done)
            if len(data) != n:
                raise StickError(f"Lesefehler bei {(src_off + done) / 1000**3:.2f} GB auf {src}")
            view = memoryview(data)
            while view:
                written = os.pwrite(fout, view, dst_off + done + (n - len(view)))
                view = view[written:]
            done += n
            since_sync += n
            if since_sync >= 256 * 1024**2:  # nicht Gigabytes im RAM stauen (ehrlicher Fortschritt)
                os.fdatasync(fout)
                _drop(fout)
                _drop(fin)
                since_sync = 0
            if time.monotonic() - last >= 0.5 or done == length:
                last = time.monotonic()
                progress(done / length, f"{what} · {rate_text(done, length, started)}")
        os.fsync(fout)
        _drop(fout)
    finally:
        os.close(fin)
        os.close(fout)


def compare_range(src: str, dst: str, length: int, progress: Progress) -> None:
    fa, fb = os.open(src, os.O_RDONLY), os.open(dst, os.O_RDONLY)
    try:
        _drop(fb)
        done, started, last = 0, time.monotonic(), 0.0
        while done < length:
            n = min(CHUNK, length - done)
            if os.pread(fa, n, done) != os.pread(fb, n, done):
                raise StickError(f"Vergleich fehlgeschlagen bei {done / 1000**3:.2f} GB – Ziel ist fehlerhaft "
                                 "(defekter Datenträger oder Wackelkontakt)")
            done += n
            if done % (256 * 1024**2) == 0:
                _drop(fa)
                _drop(fb)
            if time.monotonic() - last >= 0.5 or done == length:
                last = time.monotonic()
                progress(done / length, f"Vergleich · {rate_text(done, length, started)}")
    finally:
        os.close(fa)
        os.close(fb)


def write_zeros(device: str, size: int, progress: Progress) -> None:
    fd = os.open(device, os.O_WRONLY)
    zero = bytes(CHUNK)
    try:
        done, started, last, since_sync = 0, time.monotonic(), 0.0, 0
        while done < size:
            n = min(CHUNK, size - done)
            os.pwrite(fd, zero[:n], done)
            done += n
            since_sync += n
            if since_sync >= 256 * 1024**2:
                os.fdatasync(fd)
                _drop(fd)
                since_sync = 0
            if time.monotonic() - last >= 0.5 or done == size:
                last = time.monotonic()
                progress(done / size, f"Überschreiben mit Nullen · {rate_text(done, size, started)}")
        os.fsync(fd)
    finally:
        os.close(fd)


class _Child:
    """Unterprozess, dessen stderr laufend gelesen wird (Fortschritt von partclone, kein Pipe-Stau)."""

    def __init__(self, cmd: list[str]):
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.pct: float | None = None
        self.tail = b""
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        while chunk := self.proc.stderr.read1(4096):
            self.tail = (self.tail + chunk)[-4096:]
            found = PARTCLONE_RE.findall(chunk)
            if found:
                self.pct = float(found[-1])

    def wait(self, progress: Progress, what: str) -> int:
        try:
            while self.proc.poll() is None:
                time.sleep(0.5)
                if self.pct is not None:
                    progress(self.pct / 100, f"{what} · {self.pct:.0f} %")
            self.thread.join(timeout=5)
            return self.proc.returncode
        finally:
            if self.proc.poll() is None:  # Abbruch: partclone nicht weiterschreiben lassen
                self.proc.kill()
                self.proc.wait()
            self.proc.stderr.close()

    def error(self) -> str:
        return self.tail.decode(errors="replace").replace("\r", "\n").strip().splitlines()[-1:][0] \
            if self.tail.strip() else ""


# ---------- Klonen ----------

@dataclass
class Part:
    node: str
    start: int      # Bytes
    size: int       # Bytes
    type: str
    fstype: str = ""

    @property
    def end(self) -> int:
        return self.start + self.size


def read_layout(device: str) -> tuple[dict | None, list[Part]]:
    """(Partitionstabelle aus sfdisk -J, Partitionen mit Dateisystem); ohne Tabelle (None, [])."""
    r = subprocess.run(["sfdisk", "-J", device], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None, []
    table = json.loads(r.stdout)["partitiontable"]
    ss = int(table.get("sectorsize") or sector_size(device))
    parts = [Part(p["node"], int(p["start"]) * ss, int(p["size"]) * ss, str(p.get("type", "")).lower(),
                  probe_fstype(p["node"])) for p in table.get("partitions", [])]
    return table, parts


def probe_fstype(node: str) -> str:
    """Dateisystem direkt vom Datenträger lesen (unabhängig von udev)."""
    r = subprocess.run(["blkid", "-p", "-o", "value", "-s", "TYPE", node], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def smart_plan(table: dict | None, parts: list[Part]) -> tuple[bool, str]:
    """Lässt sich „nur belegte Bereiche“ sauber machen? (ja, Grund falls nein)."""
    if table is None or not parts:
        return False, "keine Partitionstabelle"
    if table.get("label") not in ("dos", "gpt"):
        return False, f"Partitionstabelle {table.get('label')} wird nicht unterstützt"
    if any(p.fstype == "iso9660" for p in parts):
        return False, "Boot-Stick aus ISO (Hybrid-Abbild)"
    real = sorted((p for p in parts if p.type not in EXTENDED_TYPES), key=lambda p: p.start)
    for a, b in zip(real, real[1:]):
        if b.start < a.end:
            return False, "Partitionen überlappen"
    return True, ""


def needed_size(table: dict | None, parts: list[Part], src_size: int, mode: str) -> int:
    if mode == "raw" or not parts:
        return src_size
    end = max(p.end for p in parts)
    return end + (34 * 512 if table and table.get("label") == "gpt" else 0)


def _copy_table(source: str, target: str, first: int, ss: int) -> None:
    """Partitionstabelle (gleiche Disk- und Partitions-IDs) und Startbereich übernehmen: MBR-Bootcode und alles
    zwischen Tabelle und erster Partition (z. B. GRUB bei MBR). sfdisk legt GPT-Reserve und Grenzen passend
    zum Ziel an – auch wenn es kleiner oder grösser ist."""
    dump = _run(["sfdisk", "-d", source])
    length = 128
    for line in dump.splitlines():
        if line.startswith("table-length:"):
            length = int(line.split(":")[1])
    gpt = "label: gpt" in dump
    dump = "\n".join(line for line in dump.splitlines() if not line.startswith(("last-lba:", "device:")))
    _run(["sfdisk", "--wipe", "always", "-q", target], input=dump + "\n")
    copy_range(source, target, 440, lambda *_a: None, "Bootcode")
    gap = ss * (2 + -(-length * 128 // ss)) if gpt else ss
    if first > gap:
        copy_range(source, target, first - gap, lambda *_a: None, "Startbereich", gap, gap)


def clone(source: str, target: str, mode: str, verify: bool, emit: Emit) -> None:
    def progress(frac: float, msg: str) -> None:
        emit("PROGRESS", f"{max(0.0, min(1.0, frac)):.3f} {msg}")

    def sub(start: float, share: float) -> Progress:
        return lambda f, m: progress(start + share * f, m)

    progress(0.0, "Datenträger wird geprüft")
    if source == target:
        raise StickError("Quelle und Ziel sind derselbe Datenträger")
    src, dst = _usb_disk(source), _usb_disk(target)
    if sector_size(source) != sector_size(target):
        raise StickError(f"Unterschiedliche Sektorgrösse ({sector_size(source)} / {sector_size(target)} Byte) – "
                         "die Partitionstabelle würde nicht passen. Klonen nicht möglich.")
    _unmount(src, progress)
    _unmount(dst, progress)
    src_size, dst_size = device_size(source), device_size(target)
    table, parts = read_layout(source)
    if mode == "smart":
        ok, why = smart_plan(table, parts)
        if not ok:
            emit("WARN", f"Nur belegte Bereiche geht hier nicht ({why}) – kopiere alles 1:1")
            mode = "raw"
    need = needed_size(table, parts, src_size, mode)
    if need > dst_size:
        raise StickError(f"Ziel zu klein: {dst_size / 1000**3:.1f} GB, nötig {need / 1000**3:.1f} GB"
                         + (" (Partitionen reichen bis dort)" if mode == "smart" else ""))

    if mode == "raw":
        share = 0.5 if verify else 0.98
        copy_range(source, target, src_size, sub(0.01, share), "1:1-Kopie")
        if verify:
            compare_range(source, target, src_size, sub(0.01 + share, 0.47))
        if table and table.get("label") == "gpt" and dst_size > src_size:
            progress(0.99, "Reserve-Partitionstabelle wird ans Ende verschoben")
            subprocess.run(["sfdisk", "--relocate", "gpt-bak-std", target], capture_output=True)
    else:
        ss = sector_size(source)
        real = sorted((p for p in parts if p.type not in EXTENDED_TYPES), key=lambda p: p.start)
        progress(0.01, "Übernehme Partitionstabelle")
        _run(["wipefs", "-a", target])
        _copy_table(source, target, real[0].start, ss)
        _settle(target)
        total = sum(p.size for p in real) or 1
        done = 0
        for i, p in enumerate(real, 1):
            dst_node = stick.partition_path(target, int(re.search(r"(\d+)$", p.node).group(1)))
            _wait_for(dst_node)
            step = sub(0.02 + 0.96 * done / total, 0.96 * p.size / total)
            name = Path(p.node).name
            variant = PARTCLONE.get(p.fstype)
            copied = False
            if variant and find_tool(f"partclone.{variant}"):
                what = f"{name} ({p.fstype}, nur belegte Blöcke) {i}/{len(real)}"
                child = _Child([find_tool(f"partclone.{variant}"), "-b", "-s", p.node, "-o", dst_node])
                rc = child.wait(step, what)
                if rc == 0:
                    copied = True
                else:
                    emit("WARN", f"{name}: partclone meldet „{child.error()}“ – kopiere diese Partition 1:1")
            if not copied:
                copy_range(p.node, dst_node, p.size, step,
                           f"{name} ({p.fstype or 'ohne Dateisystem'}, 1:1) {i}/{len(real)}")
            done += p.size
        progress(0.99, "Puffer wird auf das Ziel geschrieben (sync)")
        _run(["sync"])
        if verify:
            emit("WARN", "Vergleich gibt es nur bei „Alles 1:1“ (belegte Bereiche unterscheiden sich im freien Platz)")
    _settle(target)
    emit("WARN", "Quelle und Ziel tragen jetzt dieselben Kennungen (UUIDs) – nicht beide gleichzeitig am selben "
                 "Windows-PC anschliessen, Windows schaltet sonst einen offline.")
    if dst_size > need + 64 * 1024**2:
        emit("WARN", f"Auf dem Ziel bleiben {(dst_size - need) / 1000**3:.1f} GB frei (nicht partitioniert).")
    progress(1.0, "Fertig")
    emit("DONE", f"{source} wurde auf {target} geklont")


# ---------- Formatieren ----------

def _set_owner(part: str, uid: int, gid: int) -> None:
    with tempfile.TemporaryDirectory(prefix="okula-fmt-") as mnt:
        _run(["mount", part, mnt])
        try:
            os.chown(mnt, uid, gid)
        finally:
            subprocess.run(["umount", mnt], capture_output=True)


def format_disk(device: str, fs: str, scheme: str, label: str, prep: str, emit: Emit,
                owner: tuple[int, int] | None = None) -> None:
    def progress(frac: float, msg: str) -> None:
        emit("PROGRESS", f"{max(0.0, min(1.0, frac)):.3f} {msg}")

    def sub(start: float, share: float) -> Progress:
        return lambda f, m: progress(start + share * f, m)

    spec = FILESYSTEMS.get(fs)
    if spec is None:
        raise StickError(f"Unbekanntes Dateisystem: {fs}")
    if not available(spec):
        raise StickError(f"{spec.title}: Programm {spec.tool} fehlt (Paket {spec.package} installieren)")
    progress(0.0, "Datenträger wird geprüft")
    disk = _usb_disk(device)
    size = device_size(device)
    if scheme == "mbr" and size > MBR_LIMIT and sector_size(device) == 512 and fs != "none":
        raise StickError("MBR reicht nur bis 2 TiB – für diesen Datenträger GPT wählen")
    if spec.max_size and size > spec.max_size + 64 * 1024**2:
        raise StickError(f"{spec.title} geht nur bis {spec.max_size / 1024**3:.0f} GB – anderes Dateisystem wählen")
    if spec.min_size and size < spec.min_size:
        raise StickError(f"{spec.title} braucht mindestens {spec.min_size / 1024**2:.0f} MB")
    _unmount(disk, progress)

    from okula_recovery import isostick  # Schnelltest und badblocks wie beim Boot-Stick
    pre = {"none": 0.0, "quick": 0.1, "zero": 0.85, "full": 0.85}[prep]
    if prep == "quick":
        isostick.capacity_test(device, size, sub(0.01, pre))
    elif prep == "zero":
        write_zeros(device, size, sub(0.01, pre))
    elif prep == "full":
        isostick.badblocks_test(device, sub(0.01, pre))

    progress(0.01 + pre, "Alte Kennungen werden gelöscht")
    _run(["wipefs", "-a", device])  # auch die Reserve-GPT am Ende
    if fs == "none":
        progress(1.0, "Fertig")
        emit("DONE", f"{device} ist leer (keine Partition, kein Dateisystem)")
        return
    table = partition_table(spec, scheme)
    if table is None:
        target = device
    else:
        progress(0.02 + pre, "Partition wird angelegt")
        _run(["sfdisk", "--wipe", "always", "--wipe-partitions", "always", device], input=table)
        _settle(device)
        target = stick.partition_path(device)
        _wait_for(target)
        _run(["wipefs", "-a", target])
    progress(0.05 + pre * 0.95, f"Formatieren ({spec.title})")
    _run(mkfs_command(spec, target, label))
    if spec.linux and owner:
        progress(0.95, "Besitzer wird gesetzt (Schreiben ohne root möglich)")
        try:
            _set_owner(target, *owner)
        except StickError as e:
            emit("WARN", f"Besitzer nicht gesetzt ({e}) – Schreiben braucht dann root")
    progress(0.98, "Puffer wird geschrieben (sync)")
    _run(["sync"])
    _settle(device)
    progress(1.0, "Fertig")
    name = clean_label(spec, label)
    emit("DONE", f"{device} ist als {spec.title}{f' „{name}“' if name else ''} formatiert")


# ---------- Anzeige im Tool (ohne root) ----------

FS_NAMES = {"vfat": "FAT", "exfat": "exFAT", "ntfs": "NTFS", "ext4": "ext4", "ext3": "ext3", "ext2": "ext2",
            "btrfs": "Btrfs", "xfs": "XFS", "f2fs": "F2FS", "hfsplus": "HFS+", "udf": "UDF", "iso9660": "ISO (Boot-Stick)",
            "crypto_LUKS": "verschlüsselt (LUKS)", "BitLocker": "BitLocker", "apfs": "APFS", "swap": "Swap"}


def gb(n: int) -> str:
    return f"{n / 1000**4:.2f} TB" if n >= 1000**4 else f"{n / 1000**3:.1f} GB"


@dataclass
class DiskInfo:
    """Was auf einem USB-Datenträger ist – aus lsblk, ohne root."""
    path: str
    size: int
    pttype: str = ""
    parts: list[dict] = field(default_factory=list)   # path, size, fstype, label, start (Bytes)
    fstype: str = ""                                   # Dateisystem ohne Partitionstabelle

    @property
    def used_end(self) -> int:
        """Bis wohin Partitionen reichen (Klonen „nur belegte Bereiche“ braucht so viel Platz)."""
        end = max((p["start"] + p["size"] for p in self.parts), default=0)
        return end + (34 * 512 if self.pttype == "gpt" and end else 0)

    def summary(self) -> str:
        if not self.parts:
            if self.fstype:
                return f"ohne Partitionstabelle: {FS_NAMES.get(self.fstype, self.fstype)}"
            return "leer bzw. unbekannt"
        items = []
        for p in self.parts:
            fs = FS_NAMES.get(p["fstype"], p["fstype"]) or "ohne Dateisystem"
            label = f" „{p['label']}“" if p["label"] else ""
            items.append(f"{fs}{label} {gb(p['size'])}")
        table = {"gpt": "GPT", "dos": "MBR"}.get(self.pttype, self.pttype or "?")
        return f"{table}: " + " · ".join(items)


def parse_details(output: str) -> dict[str, DiskInfo]:
    """lsblk-JSON → {Disk-Pfad: DiskInfo}; Partitionen als Kinder oder (ohne Baum) flach über PKNAME."""
    try:
        devices = json.loads(output).get("blockdevices", [])
    except (json.JSONDecodeError, AttributeError):
        return {}
    flat: list[dict] = []

    def walk(items, parent=None):
        for d in items or []:
            flat.append({**d, "_parent": parent})
            walk(d.get("children"), d.get("path"))

    walk(devices)
    result = {d["path"]: DiskInfo(d["path"], int(d.get("size") or 0), d.get("pttype") or "",
                                  fstype=d.get("fstype") or "")
              for d in flat if d.get("type") in ("disk", "loop") and d.get("path")}
    for c in flat:
        if c.get("type") != "part":
            continue
        parent = c["_parent"] or (f"/dev/{c['pkname']}" if c.get("pkname") else None)
        if parent in result:
            result[parent].parts.append({"path": c.get("path", ""), "size": int(c.get("size") or 0),
                                         "fstype": c.get("fstype") or "", "label": c.get("label") or "",
                                         "start": int(c.get("start") or 0) * 512})
    return result


def disk_details() -> dict[str, DiskInfo]:
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-o", "PATH,PKNAME,TYPE,SIZE,PTTYPE,FSTYPE,LABEL,START"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return parse_details(out)


# ---------- Einstieg (okula-make-stick usb-clone / usb-format) ----------

def _watch_cancel() -> None:
    """Zeile „CANCEL“ auf stdin → wie SIGTERM abbrechen (der Benutzer darf root-Prozesse nicht beenden)."""
    def run():
        for line in sys.stdin:
            if line.strip() == "CANCEL":
                os.kill(os.getpid(), signal.SIGTERM)
                return
    threading.Thread(target=run, daemon=True).start()


class Cancelled(Exception):
    pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="okula-make-stick usb-clone|usb-format")
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("usb-clone", help="USB-Datenträger klonen (löscht das Ziel!)")
    c.add_argument("--source", required=True)
    c.add_argument("--target", required=True)
    c.add_argument("--mode", default="smart", choices=("smart", "raw"))
    c.add_argument("--verify", action="store_true")
    f = sp.add_parser("usb-format", help="USB-Datenträger formatieren (löscht alles!)")
    f.add_argument("--device", required=True)
    f.add_argument("--fs", required=True, choices=list(FILESYSTEMS))
    f.add_argument("--scheme", default="mbr", choices=("mbr", "gpt", "none"))
    f.add_argument("--label", default="")
    f.add_argument("--prep", default="none", choices=("none", "quick", "zero", "full"))
    args = ap.parse_args(argv)

    def emit(kind: str, text: str) -> None:
        print(f"{kind} {text}", flush=True)

    if os.geteuid() != 0:
        emit("ERROR", "Muss als root laufen (sudo okula-make-stick …)")
        return 1

    def on_term(*_a):
        raise Cancelled()

    signal.signal(signal.SIGTERM, on_term)
    _watch_cancel()
    try:
        if args.cmd == "usb-clone":
            clone(args.source, args.target, args.mode, args.verify, emit)
        else:
            uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
            owner = (int(uid), int(gid)) if uid and gid and uid.isdigit() and gid.isdigit() else None
            format_disk(args.device, args.fs, args.scheme, args.label, args.prep, emit, owner)
    except Cancelled:
        emit("ERROR", "Abgebrochen – der Ziel-Datenträger ist unvollständig und muss neu beschrieben werden")
        return 1
    except (StickError, ValueError, OSError) as e:
        emit("ERROR", str(e))
        return 1
    return 0
