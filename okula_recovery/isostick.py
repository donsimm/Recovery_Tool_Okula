"""Boot-Stick aus einer ISO vom NAS (Rufus-Funktionen). Läuft als root:

    sudo okula-make-stick iso-stick --device /dev/sdX --iso /mnt/okula-nas/OS/Windows/Win11.iso --mode windows

Schreibarten:
- windows: FAT32-Partition mit den Dateien des Mediums (UDF gelesen, ohne Einhängen). Eine install.wim
  über 4 GB wird in install.swm-Teile gesplittet (von Windows-Setup unterstützt). UEFI startet den
  signierten Microsoft-Bootloader (Secure Boot geht), BIOS startet über GRUB → bootmgr.
- dd: Abbild 1:1 auf den Stick (Hybrid-ISOs von Linux, Disk-Abbilder auch komprimiert), danach Lesevergleich.
- files: FAT32 mit den Dateien einer UEFI-fähigen ISO (für ISOs ohne Hybrid-Bootsektor).

Vorher auf Wunsch: Schnelltest auf gefälschte Kapazität und/oder badblocks (Schreib-/Lesetest).
Ausgabe zeilenweise wie beim Agent-Stick: PROGRESS <0..1> <Text> / WARN / DONE / ERROR.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from okula_recovery import oslib, stick, udf

ISO_ROOT = Path("/mnt")                 # nur ISOs vom eingehängten NAS
FAT32_MAX = 4 * 1024**3 - 1
SPLIT_MB = 3800                         # Teilgrösse der install.swm
BLOCK = 1024 * 1024
CAPACITY_PROBES = 64
DECOMPRESS = {"xz": ["xz", "-dc"], "gz": ["gzip", "-dc"], "zst": ["zstd", "-dc", "-q"], "bz2": ["bzip2", "-dc"]}
GPT_BASIC_DATA = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"

GRUB_NTLDR = """# Okula Recovery Tool: BIOS-Start des Windows-Setups über bootmgr
insmod part_msdos
insmod fat
insmod ntldr
search --no-floppy --file /bootmgr --set=root
ntldr /bootmgr
boot
"""

Emit = Callable[[str, str], None]
Progress = Callable[[float, str], None]

StickError = stick.StickError


def _run(cmd: list[str], input: str | None = None) -> None:
    stick._run(cmd, input)


class _drain(threading.Thread):
    """Liest eine Ausgabe-Pipe laufend leer und behält nur das Ende (für Fehlermeldungen)."""

    def __init__(self, stream, keep: int = 8192):
        super().__init__(daemon=True)
        self.stream, self.keep, self.tail = stream, keep, b""
        self.start()

    def run(self) -> None:
        while chunk := self.stream.read1(65536):
            self.tail = (self.tail + chunk)[-self.keep:]

    def text(self) -> str:
        return self.tail.decode(errors="replace").replace("\r", "\n").strip()


def fat_label(meta: dict) -> str:
    """Datenträgername (FAT: max. 11 Zeichen), z. B. WIN11_24H2 oder UBUNTU_2404."""
    if meta.get("family") == "windows":
        w = meta["windows"]
        base = w.get("product", "Windows").replace("Windows ", "WIN")
        label = f"{base}_{w.get('version', '')}".strip("_")
    else:
        label = meta.get("volume_id") or meta.get("title") or "OKULA"
    label = re.sub(r"[^A-Z0-9_-]", "_", label.upper())
    return re.sub(r"_+", "_", label).strip("_")[:11] or "OKULA"


# ---------- Stick vorbereiten ----------

def _partition(device: str, table: str) -> str:
    _run(["wipefs", "-a", device])
    _run(["sfdisk", "--wipe", "always", device], input=table)
    subprocess.run(["partx", "-u", device], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)
    part = stick.partition_path(device)
    for _ in range(50):
        if Path(part).exists():
            return part
        time.sleep(0.2)
    raise StickError(f"Partition {part} erscheint nicht")


def _format(part: str, label: str) -> None:
    _run(["mkfs.vfat", "-F", "32", "-n", label, part])


def _mount(part: str, where: str) -> None:
    _run(["mount", part, where])


def _drop_cache(fd: int) -> None:
    os.fsync(fd)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    except (AttributeError, OSError):
        pass


def capacity_test(device: str, size: int, progress: Progress) -> None:
    """Gefälschte Sticks melden mehr Platz als vorhanden und überschreiben dann vorne wieder.
    Prüfmuster an 64 Stellen über die ganze Grösse schreiben und zurücklesen."""
    count = max(2, min(CAPACITY_PROBES, size // BLOCK))
    offsets = sorted({(size - BLOCK) * i // (count - 1) // BLOCK * BLOCK for i in range(count)})
    token = os.urandom(16)

    def pattern(off: int) -> bytes:
        unit = token + off.to_bytes(8, "little") + b"OKULA-CAPTEST\0\0\0"
        return (unit * (BLOCK // len(unit) + 1))[:BLOCK]

    fd = os.open(device, os.O_RDWR)
    try:
        for i, off in enumerate(offsets):
            os.pwrite(fd, pattern(off), off)
            progress(0.5 * (i + 1) / len(offsets), "Schnelltest: schreibe Prüfmuster")
        _drop_cache(fd)
        bad = []
        for i, off in enumerate(offsets):
            if os.pread(fd, BLOCK, off) != pattern(off):
                bad.append(off)
            progress(0.5 + 0.5 * (i + 1) / len(offsets), "Schnelltest: lese Prüfmuster")
    finally:
        os.close(fd)
    if bad:
        raise StickError(f"Stick ist vermutlich gefälscht oder defekt: {len(bad)} von {len(offsets)} Prüfstellen "
                         f"falsch, erste bei {bad[0] / 1000**3:.1f} GB (gemeldet: {size / 1000**3:.1f} GB). "
                         "Stick nicht verwenden.")


BADBLOCKS_RE = re.compile(r"(\d+(?:\.\d+)?)% done")


def badblocks_test(device: str, progress: Progress) -> None:
    """Vollständiger Schreib-/Lesetest (zerstört den Inhalt, der Stick wird danach ohnehin neu beschrieben)."""
    if not shutil.which("badblocks"):
        raise StickError("badblocks fehlt (Paket e2fsprogs)")
    proc = subprocess.Popen(["badblocks", "-w", "-s", "-b", "4096", "-c", "256", "-t", "random", device],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    bad: list[str] = []

    def collect() -> None:
        for line in proc.stdout:
            if line.strip():
                bad.append(line.decode(errors="replace").strip())

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    phase, buf = 0, b""
    while chunk := proc.stderr.read1(4096):
        buf = (buf + chunk)[-4096:]
        text = chunk.decode(errors="replace")
        if "Reading and comparing" in text:
            phase = 1
        found = BADBLOCKS_RE.findall(text)
        if found:
            progress((phase + float(found[-1]) / 100) / 2,
                     ("Prüfe Blöcke: schreiben" if phase == 0 else "Prüfe Blöcke: lesen") + f" {found[-1]} %")
    rc = proc.wait()
    reader.join()
    proc.stdout.close()
    proc.stderr.close()
    if bad:
        raise StickError(f"Stick hat {len(bad)} defekte Blöcke – nicht verwenden")
    if rc != 0:
        raise StickError(f"badblocks fehlgeschlagen: {buf.decode(errors='replace').strip().splitlines()[-1:]}")
    progress(1.0, "Blöcke geprüft – keine Fehler")


# ---------- Schreibarten ----------

def _source_stream(iso: Path, compression: str):
    if not compression:
        return open(iso, "rb"), None
    proc = subprocess.Popen(DECOMPRESS[compression] + [str(iso)], stdout=subprocess.PIPE)
    return proc.stdout, proc


def _expected_size(iso: Path, compression: str) -> int | None:
    if not compression:
        return iso.stat().st_size
    if compression == "xz":
        r = subprocess.run(["xz", "--robot", "-l", str(iso)], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if parts[0] == "totals" and len(parts) > 4 and parts[4].isdigit():
                return int(parts[4])
    if compression == "zst":
        r = subprocess.run(["zstd", "-lv", str(iso)], capture_output=True, text=True)
        m = re.search(r"Decompressed Size:.*\((\d+) B\)", r.stdout)
        if m:
            return int(m.group(1))
    return None


def write_dd(iso: Path, device: str, dev_size: int, compression: str, verify: bool, progress: Progress) -> None:
    expected = _expected_size(iso, compression)
    if expected and expected > dev_size:
        raise StickError(f"Stick zu klein: Abbild {expected / 1000**3:.1f} GB, Stick {dev_size / 1000**3:.1f} GB")
    fd = os.open(device, os.O_RDWR)
    h = hashlib.sha256()
    written = 0
    try:
        # alte Partitionstabellen (auch die GPT-Kopie am Ende) entfernen
        os.pwrite(fd, bytes(BLOCK), 0)
        os.pwrite(fd, bytes(BLOCK), max(0, dev_size - BLOCK))
        src, proc = _source_stream(iso, compression)
        last_sync = 0
        try:
            while chunk := src.read(4 * BLOCK):
                if written + len(chunk) > dev_size:
                    raise StickError("Abbild ist grösser als der Stick")
                os.pwrite(fd, chunk, written)
                h.update(chunk)
                written += len(chunk)
                if written - last_sync >= 64 * BLOCK:  # Fortschritt folgt dem echten Schreiben
                    os.fsync(fd)
                    last_sync = written
                total = expected or max(written, 1)
                progress(min(0.99, written / total) * (0.75 if verify else 1.0),
                         f"Schreibe Abbild {written / 1000**2:.0f} / {total / 1000**2:.0f} MB")
        finally:
            src.close()
            if proc and proc.wait() != 0:
                raise StickError("Entpacken des Abbilds fehlgeschlagen")
        _drop_cache(fd)
        if verify:
            check = hashlib.sha256()
            done = 0
            while done < written:
                n = min(4 * BLOCK, written - done)
                check.update(os.pread(fd, n, done))
                done += n
                progress(0.75 + 0.25 * done / written, f"Prüfe Stick {done * 100 // written} %")
            if check.digest() != h.digest():
                raise StickError("Lesevergleich fehlgeschlagen: der Stick speichert nicht zuverlässig")
    finally:
        os.close(fd)
    subprocess.run(["partx", "-u", device], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)


def _wim_source(iso: Path, img: udf.UdfImage, wim: udf.Entry, workdir: Path, progress: Progress):
    """install.wim als Datei für wimlib: ISO als UDF einhängen, sonst in einen Arbeitsordner kopieren."""
    mnt = workdir / "iso"
    mnt.mkdir()
    r = subprocess.run(["mount", "-t", "udf", "-o", "loop,ro", str(iso), str(mnt)], capture_output=True)
    if r.returncode == 0:
        for name in os.listdir(mnt):
            if name.lower() == "sources":
                for f in os.listdir(mnt / name):
                    if f.lower() == wim.name.lower():
                        return mnt / name / f, mnt
        subprocess.run(["umount", str(mnt)], capture_output=True)
    target = workdir / "install.wim"
    if shutil.disk_usage(workdir).free < wim.size + 512 * BLOCK:
        raise StickError(f"Zu wenig Platz in {workdir} zum Aufteilen der install.wim ({wim.size / 1000**3:.1f} GB)")
    done = 0
    with open(target, "wb") as out:
        for chunk in img.chunks(wim):
            out.write(chunk)
            done += len(chunk)
            progress(done / wim.size, "Lese install.wim")
    return target, None


def copy_windows(iso: Path, dest: Path, unattend: str | None, progress: Progress, emit: Emit,
                 workdir: Path) -> None:
    """Dateien des Windows-Mediums nach dest; install.wim > 4 GB wird gesplittet."""
    with udf.UdfImage.open(str(iso)) as img:
        entries = list(img.walk())
        wim = next((e for p, e in entries if p.lower() == "sources/install.wim"), None)
        split = wim is not None and wim.size > FAT32_MAX
        too_big = [p for p, e in entries if not e.is_dir and e.size > FAT32_MAX and e is not wim]
        if too_big:
            raise StickError(f"Datei grösser als 4 GB, passt nicht auf FAT32: {too_big[0]}")
        total = sum(e.size for _p, e in entries if not e.is_dir) or 1
        done = 0
        for path, e in entries:
            target = dest / path
            if e.is_dir:
                target.mkdir(parents=True, exist_ok=True)
                continue
            if split and e is wim:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as out:
                for chunk in img.chunks(e):
                    out.write(chunk)
                    done += len(chunk)
                    progress(0.9 * done / total, f"Kopiere {path}")
                if e.size > 64 * BLOCK:
                    out.flush()
                    os.fsync(out.fileno())
        if split:
            emit("WARN", f"install.wim ist {wim.size / 1000**3:.1f} GB (FAT32: max. 4 GB) – wird in "
                         "install.swm-Teile gesplittet")
            if not shutil.which("wimlib-imagex"):
                raise StickError("wimlib-imagex fehlt (Paket wimtools) – install.sh erneut ausführen")
            base = done
            src, mounted = _wim_source(iso, img, wim, workdir,
                                       lambda f, m: progress(0.9 * (base + 0.3 * f * wim.size) / total, m))
            try:
                swm = dest / "sources" / "install.swm"
                proc = subprocess.Popen(["wimlib-imagex", "split", str(src), str(swm), str(SPLIT_MB)],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                # wimlib meldet laufend Fortschritt: mitlesen, sonst läuft die Pipe voll und wimlib hängt
                tail = _drain(proc.stdout)
                while proc.poll() is None:
                    written = sum(p.stat().st_size for p in swm.parent.glob("install*.swm"))
                    progress(0.9 * (base + 0.3 * wim.size + 0.7 * min(written, wim.size)) / total,
                             f"Splitte install.wim in install.swm-Teile ({written / 1000**3:.1f} / "
                             f"{wim.size / 1000**3:.1f} GB)")
                    time.sleep(0.5)
                tail.join()
                proc.stdout.close()
                if proc.returncode != 0:
                    msg = tail.text().splitlines()
                    raise StickError(f"wimlib-imagex split: {msg[-1] if msg else proc.returncode}")
            finally:
                if "proc" in locals() and proc.poll() is None:  # Abbruch: wimlib mit beenden
                    proc.kill()
                    proc.wait()
                if mounted:
                    subprocess.run(["umount", str(mounted)], capture_output=True)
    if unattend:
        (dest / "autounattend.xml").write_text(unattend, encoding="utf-8")
    progress(0.9, "Dateien kopiert")


def copy_iso9660(iso: Path, dest: Path, progress: Progress) -> None:
    """Dateien einer ISO9660/Rock-Ridge-ISO (Linux u. a.) nach dest – mit xorriso, ohne Einhängen."""
    total = iso.stat().st_size
    proc = subprocess.Popen(["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/", str(dest)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    tail = b""

    def drain() -> None:
        nonlocal tail
        while chunk := proc.stderr.read1(4096):
            tail = (tail + chunk)[-4096:]

    t = threading.Thread(target=drain, daemon=True)
    t.start()
    while proc.poll() is None:
        used = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
        progress(0.9 * min(1.0, used / total), "Kopiere Dateien")
        time.sleep(1)
    t.join()
    if proc.returncode != 0:
        msg = tail.decode(errors="replace").strip().splitlines()
        raise StickError(f"xorriso: {msg[-1] if msg else proc.returncode}")


def install_bios_loader(device: str, mnt: Path) -> bool:
    if not (stick.BIOS_GRUB_DIR.is_dir() and shutil.which("grub-install")):
        return False
    _run(["grub-install", "--target=i386-pc", f"--boot-directory={mnt}/boot", device])
    (mnt / "boot" / "grub" / "grub.cfg").write_text(GRUB_NTLDR)
    return True


def prepare(device: str, iso: str, mode: str, emit: Emit, scheme: str = "mbr", label: str = "",
            check: str = "quick", verify: bool = True, unattend: str | None = None) -> None:
    def progress(frac: float, msg: str) -> None:
        emit("PROGRESS", f"{max(0.0, min(1.0, frac)):.3f} {msg}")

    progress(0.0, "Prüfe Stick und ISO")
    disk = {d.path: d for d in stick.list_usb_disks()}.get(device)
    if disk is None:
        raise StickError(f"{device} ist kein auswählbarer USB-Stick")
    iso_path = Path(iso).resolve()
    if not iso_path.is_relative_to(ISO_ROOT) or not iso_path.is_file():
        raise StickError(f"ISO muss auf dem eingehängten NAS liegen ({ISO_ROOT}): {iso}")
    meta = oslib.inspect(iso_path)
    modes = oslib.stick_modes(meta)
    if mode not in modes:
        raise StickError(f"Schreibart „{mode}“ passt nicht zu diesem Medium (möglich: {', '.join(modes) or 'keine'})")
    if mode == "dd" and not meta.get("compression") and iso_path.stat().st_size > disk.size:
        raise StickError(f"Stick zu klein: {disk.size / 1000**3:.1f} GB, nötig {iso_path.stat().st_size / 1000**3:.1f} GB")
    need = iso_path.stat().st_size + 64 * BLOCK  # FAT32-Verwaltung + Reserve
    if mode != "dd" and need > disk.size:
        raise StickError(f"Stick zu klein: {disk.size / 1000**3:.1f} GB, nötig {need / 1000**3:.1f} GB")

    for mp in sorted(disk.mountpoints, reverse=True):
        progress(0.01, f"Hänge {mp} aus")
        _run(["umount", mp])

    # Anteile am Fortschritt: Prüfen vorher, dann Schreiben
    pre = {"none": 0.0, "quick": 0.05, "full": 0.5}[check]

    def sub(start: float, share: float) -> Progress:
        return lambda f, m: progress(start + share * f, m)

    if check == "quick":
        capacity_test(device, disk.size, sub(0.01, pre))
    elif check == "full":
        badblocks_test(device, sub(0.01, pre))
    write = sub(0.01 + pre, 0.98 - pre)

    if mode == "dd":
        write_dd(iso_path, device, disk.size, meta.get("compression", ""), verify, write)
    else:
        bios = mode == "windows" and scheme == "mbr" and meta.get("bios")
        table = (f"label: gpt\nstart=2048, type={GPT_BASIC_DATA}\n" if scheme == "gpt"
                 else "label: dos\nstart=2048, type=c, bootable\n")
        write(0.0, "Partitioniere Stick")
        part = _partition(device, table)
        write(0.01, "Formatiere FAT32")
        _format(part, (label or fat_label(meta))[:11])
        with tempfile.TemporaryDirectory(prefix="okula-osstick-") as mnt, \
                tempfile.TemporaryDirectory(prefix="okula-wim-", dir="/var/tmp") as work:
            _mount(part, mnt)
            try:
                files = sub(0.01 + pre + 0.02 * (0.98 - pre), 0.96 * (0.98 - pre))
                if mode == "windows":
                    copy_windows(iso_path, Path(mnt), unattend, files, emit, Path(work))
                else:
                    copy_iso9660(iso_path, Path(mnt), files)
                if bios:
                    progress(0.95, "Installiere BIOS-Bootloader")
                    if not install_bios_loader(device, Path(mnt)):
                        emit("WARN", "grub-pc-bin fehlt: Stick startet nur per UEFI")
                elif scheme == "mbr" and mode != "windows":
                    emit("WARN", "Dateimodus: Stick startet nur per UEFI")
                progress(0.97, "Schreibe Daten auf den Stick (sync)")
                _run(["sync"])
            finally:
                subprocess.run(["umount", mnt], capture_output=True)

    progress(1.0, "Fertig")
    emit("DONE", f"Boot-Stick „{meta.get('title') or iso_path.name}“ auf {device} ist bereit")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="okula-make-stick iso-stick",
                                 description="Boot-Stick aus ISO erstellen (löscht den Stick!)")
    ap.add_argument("--device", required=True)
    ap.add_argument("--iso", required=True, help=f"ISO oder IMG unter {ISO_ROOT}")
    ap.add_argument("--mode", required=True, choices=("windows", "dd", "files"))
    ap.add_argument("--scheme", default="mbr", choices=("mbr", "gpt"))
    ap.add_argument("--label", default="")
    ap.add_argument("--check", default="quick", choices=("none", "quick", "full"))
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--unattend-stdin", action="store_true", help="autounattend.xml von stdin")
    args = ap.parse_args(argv)

    def emit(kind: str, text: str) -> None:
        print(f"{kind} {text}", flush=True)

    if os.geteuid() != 0:
        emit("ERROR", "Muss als root laufen (sudo okula-make-stick iso-stick …)")
        return 1
    # Abbruch von aussen (kill): wie ein Fehler behandeln, damit Einhängepunkte aufgeräumt werden
    signal.signal(signal.SIGTERM, lambda *_a: sys.exit("Abgebrochen"))
    try:
        unattend = sys.stdin.read() if args.unattend_stdin else None
        if unattend is not None and not unattend.lstrip().startswith("<?xml"):
            raise ValueError("autounattend.xml ungültig")
        prepare(args.device, args.iso, args.mode, emit, args.scheme, args.label, args.check,
                not args.no_verify, unattend)
    except (StickError, oslib.OsLibError, udf.UdfError, ValueError, OSError) as e:
        emit("ERROR", str(e))
        return 1
    return 0
