"""Image für eine kleinere Disk anpassen (Ä-002, Plan: docs/KLEINERE-DISK.md).

Auf dem Server, als normaler Benutzer: die grosse Partition (meist C:) in eine Sparse-Datei zurückspielen, das
Dateisystem verkleinern (ntfsresize / resize2fs), neu sichern und mit angepasster Partitionstabelle als NEUES
Okula-Image neben das Original legen. Partitionen danach (z. B. Recovery) rücken ans neue Disk-Ende.
Das Original bleibt unverändert; ein schon angepasstes Image für dieselbe Grösse wird wiederverwendet.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from okula_recovery import __version__, agentclient, imaging

SHRINKABLE = {"ntfs": "ntfs", "extfs": "ext", "ext2": "ext", "ext3": "ext", "ext4": "ext"}
ALIGN = 1024 * 1024                # Partitionen auf 1 MiB ausrichten
GPT_BACKUP_SECTORS = 33            # Einträge + Header am Disk-Ende
LOCAL_TMP = Path("/var/tmp/okula-recovery")
NAS_TMP = ".okula-tmp"
CHUNK = 4 * 1024 * 1024

Progress = Callable[[dict], None]


class ShrinkError(Exception):
    pass


def gb(n: float) -> str:
    return f"{n / 1000**3:.1f} GB"


def reserve_for(used: int) -> int:
    """Platz, der nach dem Verkleinern frei bleiben soll (10 %, mindestens 1 GB)."""
    return max(1024**3, used // 10)


# ---------- partclone-Kopf ----------

def parse_pcl_header(data: bytes) -> dict:
    """partclone-Image (Format 0001/0002): Gerätegrösse, Blöcke, belegte Blöcke, Blockgrösse."""
    if not data.startswith(b"partclone-image"):
        raise ShrinkError("Kein partclone-Image")
    version = data[30:34].decode("ascii", "replace")
    if version == "0002":
        device_size, total, used, _ubm, block = struct.unpack_from("<QQQQI", data, 52)
    elif version == "0001":
        block, device_size, total, used = struct.unpack_from("<IQQQ", data, 52)
    else:
        raise ShrinkError(f"Unbekanntes partclone-Format {version}")
    return {"fs": data[36:52].split(b"\0")[0].decode("ascii", "replace"), "device_size": device_size,
            "total": total, "used_blocks": used, "block_size": block, "used": used * block}


def read_header(step: dict) -> dict:
    """Kopf eines Partitions-Images lesen, ohne alles zu entpacken."""
    pieces = [Path(x) for x in step.get("pieces") or []]
    dec = imaging.decompressor(step)
    if not dec:
        with open(pieces[0], "rb") as f:
            return parse_pcl_header(f.read(4096))
    p = subprocess.Popen(dec, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def feed():
        try:
            for chunk in imaging.read_pieces(pieces):
                p.stdin.write(chunk)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                p.stdin.close()
            except OSError:
                pass

    t = threading.Thread(target=feed, daemon=True)
    t.start()
    try:
        data = p.stdout.read(4096)
    finally:
        p.stdout.close()
        p.kill()
        p.wait()
        t.join(timeout=5)
    return parse_pcl_header(data)


# ---------- Partitionstabelle (sfdisk -d) ----------

LINE_RE = re.compile(r"^(?P<node>\S+)\s*:\s*(?P<fields>.*)$")


@dataclass
class Part:
    node: str
    fields: dict            # start, size, type, uuid, name, attrs, bootable …
    order: list[str]

    @property
    def start(self) -> int:
        return int(self.fields["start"])

    @property
    def size(self) -> int:
        return int(self.fields["size"])

    @property
    def number(self) -> int:
        return int(re.search(r"(\d+)$", self.node).group(1))

    def line(self) -> str:
        out = []
        for key in self.order:
            value = self.fields[key]
            out.append(key if value is None else f"{key}={value}")
        return f"{self.node} : " + ", ".join(out)


def parse_sfdisk(dump: str) -> tuple[list[str], list[Part]]:
    header, parts = [], []
    for line in dump.splitlines():
        m = LINE_RE.match(line)
        if m and m.group("node").startswith("/"):
            fields, order = {}, []
            for item in re.findall(r'(\w[\w-]*)(?:=\s*("[^"]*"|[^,]*))?', m.group("fields")):
                key, value = item[0], item[1].strip() if item[1] else None
                fields[key], order = value, order + [key]
            parts.append(Part(m.group("node"), fields, order))
        else:
            header.append(line)
    return header, parts


def build_sfdisk(header: list[str], parts: list[Part], last_lba: int | None) -> str:
    lines = []
    for line in header:
        if line.startswith("last-lba:"):
            if last_lba is not None:
                lines.append(f"last-lba: {last_lba}")
            continue
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines + [""] + [p.line() for p in parts]) + "\n"


# ---------- Planen ----------

@dataclass
class Plan:
    image: Path
    source_disk: str | None
    target_size: int
    part: str                       # verkleinerte Partition (Name wie im Image, z. B. sda3)
    variant: str                    # partclone-Variante (ntfs, extfs …)
    used: int                       # belegt auf dieser Partition (Bytes)
    old_size: int                   # Partition vorher (Bytes)
    new_size: int                   # Partition nachher (Bytes)
    sfdisk: str                     # neue Tabelle
    moved: list[str] = field(default_factory=list)   # Partitionen, die ans Ende rücken
    src: dict = field(default_factory=dict, repr=False)

    def lines(self) -> list[str]:
        out = [f"{self.part}: belegt {gb(self.used)} – wird von {gb(self.old_size)} auf {gb(self.new_size)} "
               f"verkleinert (frei danach {gb(self.new_size - self.used)})"]
        if self.moved:
            out.append(f"{', '.join(self.moved)} rück{'t' if len(self.moved) == 1 else 'en'} ans Ende der neuen Disk")
        out.append(f"Neues Image für {gb(self.target_size)}; das Original bleibt unverändert")
        return out


def plan(image: str | Path, target_size: int, source_disk: str | None = None) -> Plan:
    """Prüfen, ob und wie das Image auf eine Disk mit target_size Bytes passt (ShrinkError mit Grund)."""
    image = Path(image)
    try:
        src = agentclient.image_source(image, source_disk)
    except agentclient.AgentError as e:
        raise ShrinkError(str(e)) from None
    if src.get("demo"):
        raise ShrinkError("Demo-Image – nicht anpassbar")
    disk = src["source"]
    if int(disk.get("size") or 0) <= target_size:
        raise ShrinkError("Das Image passt schon auf diese Disk")
    dump = src.get("sfdisk") or ""
    if not dump:
        raise ShrinkError("Image ohne Partitionstabelle – nicht anpassbar")
    header, parts = parse_sfdisk(dump)
    label = (re.search(r"^label:\s*(\S+)", dump, re.M) or [None, ""])[1]
    if label not in ("gpt", "dos"):
        raise ShrinkError(f"Partitionstabelle „{label or '?'}“ wird nicht unterstützt")
    if label == "dos" and any(p.number > 4 or (p.fields.get("type") or "").lower() in ("5", "f", "85")
                              for p in parts):
        raise ShrinkError("MBR mit erweiterter/logischen Partitionen – nur primäre Partitionen werden unterstützt")
    sector = imaging.sfdisk_sector_size(dump) or 512
    steps = {s["part"]: s for s in src["steps"]}
    by_number = {p.number: p for p in parts}

    def step_of(p: Part) -> dict | None:
        return next((s for name, s in steps.items()
                     if imaging.partition_number(disk["name"], name) == p.number), None)

    biggest = max(parts, key=lambda p: p.size)
    step = step_of(biggest)
    if step is None or step.get("kind") == "swap":
        raise ShrinkError("Die grösste Partition ist nicht im Image enthalten")
    name = step["part"]
    if step.get("kind") == "dd":
        raise ShrinkError(f"{name} ist eine Rohkopie (z. B. BitLocker oder unbekanntes Dateisystem) – Inhalt "
                          "unbekannt, nicht verkleinerbar")
    variant = step.get("variant", "")
    if variant not in SHRINKABLE:
        raise ShrinkError(f"{name}: Dateisystem „{variant}“ lässt sich nicht verkleinern (nur NTFS und ext2/3/4)")
    head = read_header(step)
    used = int(head["used"])
    old_size = biggest.size * sector

    align = ALIGN // sector
    total = target_size // sector
    last_usable = total - GPT_BACKUP_SECTORS - 1 - 1 if label == "gpt" else total - 1
    after = sorted((p for p in parts if p.start > biggest.start), key=lambda p: p.start)
    end = last_usable + 1
    moved = []
    for p in reversed(after):
        new_start = (end - p.size) // align * align
        if new_start <= biggest.start:
            raise ShrinkError("Die Partitionen hinter der grossen Partition passen nicht auf die neue Disk")
        if new_start != p.start:
            p.fields["start"] = str(new_start)
            st = step_of(p)
            moved.append(st["part"] if st else p.node.rsplit("/", 1)[-1])
        end = new_start
    new_sectors = (end - biggest.start) // align * align
    new_size = new_sectors * sector
    need = used + reserve_for(used)
    if new_size < need:
        raise ShrinkError(f"Passt nicht: auf {name} sind {gb(used)} belegt, mit Reserve {gb(need)} nötig, auf der "
                          f"Zieldisk ({gb(target_size)}) bleiben aber nur {gb(max(0, new_size))} dafür")
    biggest.fields["size"] = str(new_sectors)
    new_dump = build_sfdisk(header, [by_number[n] for n in sorted(by_number)],
                            last_usable if label == "gpt" else None)
    return Plan(image, source_disk, target_size, name, variant, used, old_size, new_size, new_dump,
                list(reversed(moved)), src)


# ---------- Anpassen ----------

def derived_path(image: Path, target_size: int, source_disk: str | None = None) -> Path:
    suffix = f"_{source_disk}" if source_disk else ""
    size = target_size / 1000**3
    label = f"{size:.0f}GB" if size >= 10 else f"{size:.1f}GB"
    return image.parent / f"{image.name}{suffix}_für_{label}"


def find_derived(image: str | Path, target_size: int, source_disk: str | None = None) -> Path | None:
    """Schon angepasstes Image für diese Disk-Grösse (vollständig, gleiche Quelle)?"""
    path = derived_path(Path(image), target_size, source_disk)
    try:
        meta = json.loads((path / agentclient.IMAGE_META).read_text())
    except (OSError, ValueError):
        return None
    shrunk = meta.get("shrunk") or {}
    if shrunk.get("target_size") == target_size and meta.get("completed"):
        return path
    return None


def choose_tmp(need: int, nas_root: str | Path | None) -> Path:
    """Zwischenspeicher: Server-SSD, sonst NAS (Entscheid Dominik); sonst Meldung mit Zahlen."""
    spare = 2 * 1024**3
    candidates = [LOCAL_TMP] + ([Path(nas_root) / NAS_TMP] if nas_root else [])
    free = {}
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            free[c] = shutil.disk_usage(c).free
        except OSError:
            continue
        if free[c] >= need + spare:
            return c
    detail = ", ".join(f"{'Server' if c == LOCAL_TMP else 'NAS'} {gb(f)} frei" for c, f in free.items())
    raise ShrinkError(f"Zu wenig Platz für den Zwischenspeicher: nötig {gb(need + spare)} ({detail})")


def _run(cmd: list[str], what: str, timeout: int = 6 * 3600) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        raise ShrinkError(f"{what} fehlgeschlagen: {msg[-1] if msg else r.returncode}")
    return r.stdout


def _pipe(src_cmds: list[list[str]], feed, out_path: Path | None, cancel: threading.Event,
          on_bytes: Callable[[int], None] = lambda n: None) -> int:
    """Datenstrom (feed: Stücke) durch Befehle; Ausgabe in out_path (None = Befehl schreibt selbst)."""
    procs, stdin = [], subprocess.PIPE
    out = open(out_path, "wb") if out_path else None
    try:
        for i, argv in enumerate(src_cmds):
            last = i == len(src_cmds) - 1
            p = subprocess.Popen(argv, stdin=stdin, stdout=(out or subprocess.DEVNULL) if last else subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
            if i > 0:
                procs[-1].stdout.close()
            procs.append(p)
            stdin = p.stdout
        n = 0
        sink = procs[0].stdin
        for chunk in feed:
            if cancel.is_set():
                raise ShrinkError("Abgebrochen")
            sink.write(chunk)
            n += len(chunk)
            on_bytes(n)
        sink.close()
        codes = [p.wait() for p in procs]
        if any(codes):
            raise ShrinkError(f"{src_cmds[-1][0]} fehlgeschlagen ({codes})")
        return n
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait()
        if out:
            out.close()


def _file_chunks(path: Path):
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            yield chunk


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    for chunk in _file_chunks(path):
        h.update(chunk)
    return h.hexdigest()


def create(p: Plan, nas_root: str | Path | None, progress: Progress = lambda ev: None,
           cancel: threading.Event | None = None) -> Path:
    """Angepasstes Image erzeugen (oder vorhandenes zurückgeben)."""
    cancel = cancel or threading.Event()
    existing = find_derived(p.image, p.target_size, p.source_disk)
    if existing:
        progress({"phase": "shrink", "fraction": 1.0, "detail": f"vorhanden: {existing.name}"})
        return existing
    src = p.src
    disk = dict(src["source"])
    out = derived_path(p.image, p.target_size, p.source_disk)
    work = out.with_name(out.name + ".partial")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    tmpdir = Path(tempfile.mkdtemp(prefix="okula-shrink-", dir=choose_tmp(p.used, nas_root)))
    files, plan_entries = [], []
    _header, new_parts = parse_sfdisk(p.sfdisk)
    sector = imaging.sfdisk_sector_size(p.sfdisk) or 512
    part_sizes = {s["part"]: next((q.size * sector for q in new_parts
                                   if q.number == imaging.partition_number(disk.get("name", ""), s["part"])), 0)
                  for s in src["steps"]}
    total_work = p.used * 2 + sum(int(s.get("size") or 0) for s in src["steps"] if s["part"] != p.part) or 1
    done = 0
    started = time.monotonic()

    def report(extra: int, detail: str) -> None:
        progress({"phase": "shrink", "fraction": min(1.0, (done + extra) / total_work), "detail": detail,
                  "speed": (done + extra) / max(time.monotonic() - started, 0.001)})

    try:
        for step in src["steps"]:
            if step["kind"] == "swap":
                plan_entries.append({"file": None, "kind": "skip", "part": step["part"], "reason": "swap",
                                     "uuid": step.get("uuid", ""), "label": step.get("label", "")})
                continue
            variant = step.get("variant") or "dd"
            tool = f"partclone.{variant if step['kind'] == 'pcl' else 'dd'}"
            name = f"{step['part']}.{variant if step['kind'] == 'pcl' else 'dd'}.pcl.zst"
            target = work / name
            pieces = [Path(x) for x in step.get("pieces") or []]
            if step["part"] == p.part:
                size = _shrink_partition(step, pieces, p, tmpdir, target, cancel,
                                         lambda n, d: report(n, d))
                done += p.used * 2
                part_size = p.new_size
            else:
                dec = imaging.decompressor(step)
                if dec == imaging.DECOMPRESS["zstd"] and len(pieces) == 1:
                    shutil.copyfile(pieces[0], target)        # schon zstd: unverändert übernehmen
                else:
                    _pipe(([dec] if dec else []) + [["zstd", "-1", "-T0", "-q", "-c"]], imaging.read_pieces(pieces),
                          target, cancel)
                done += int(step.get("size") or 0)
                part_size = part_sizes.get(step["part"], 0)
                size = target.stat().st_size
            report(0, step["part"])
            files.append({"name": name, "size": size, "sha256": _sha256(target)})
            plan_entries.append({"file": name, "kind": "pipe", "part": step["part"], "size": part_size,
                                 "fstype": variant, "cmds": [[tool, "-c", "-s", step["part"], "-o", "-"],
                                                            ["zstd", "-1", "-T0", "-q", "-c"]]})
        dname = disk.get("name") or "disk"
        (work / f"{dname}.sfdisk").write_text(p.sfdisk)
        (work / f"{dname}-head.img").write_bytes(src["head"].ljust(imaging.HEAD_TAIL, b"\0")[:imaging.HEAD_TAIL])
        for f in (f"{dname}.sfdisk", f"{dname}-head.img"):
            files.insert(0, {"name": f, "size": (work / f).stat().st_size, "sha256": _sha256(work / f)})
        for part in disk.get("partitions") or []:
            if part.get("name") == p.part:
                part["size"] = p.new_size
        disk["size"] = p.target_size
        try:
            original = json.loads((p.image / agentclient.IMAGE_META).read_text())
        except (OSError, ValueError):
            original = {}
        meta = {"format": "okula-image", "version": 1, "tool_version": __version__,
                "machine": original.get("machine") or p.image.name, "source": original.get("source") or {},
                "disk": disk, "plan": plan_entries, "compression": "zstd", "files": files,
                "started": datetime.fromtimestamp(time.time() - (time.monotonic() - started)).isoformat(
                    timespec="seconds"),
                "derived_from": str(p.image.name) + (f" ({p.source_disk})" if p.source_disk else ""),
                "shrunk": {"part": p.part, "from": p.old_size, "to": p.new_size, "used": p.used,
                           "target_size": p.target_size},
                "completed": datetime.now().isoformat(timespec="seconds")}
        (work / agentclient.IMAGE_META).write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        work.rename(out)
        progress({"phase": "shrink", "fraction": 1.0, "detail": out.name})
        return out
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _shrink_partition(step: dict, pieces: list[Path], p: Plan, tmpdir: Path, target: Path,
                      cancel: threading.Event, report: Callable[[int, str], None]) -> int:
    """Partition entpacken → Dateisystem verkleinern → neu sichern (zstd). Gibt die Dateigrösse zurück."""
    raw = tmpdir / f"{p.part}.img"
    log = tmpdir / "partclone.log"
    with open(raw, "wb") as f:
        f.truncate(p.old_size)                                   # Sparse-Datei: nur belegte Blöcke kosten Platz
    dec = imaging.decompressor(step)
    tool = f"partclone.{p.variant}"
    _pipe(([dec] if dec else []) + [[tool, "-r", "-O", str(raw), "-s", "-", "-L", str(log)]],
          imaging.read_pieces(pieces), None, cancel,
          lambda n: report(min(n, p.used), f"{p.part} entpacken"))
    report(p.used, f"{p.part} verkleinern")
    if SHRINKABLE[p.variant] == "ntfs":
        _run(["ntfsresize", "--force", "--force", "--no-progress-bar", "--size", str(p.new_size), str(raw)],
             "ntfsresize")
        _run(["ntfsfix", "-d", str(raw)], "ntfsfix")                # sonst „Prüfung geplant“ → nicht einhängbar
    else:
        check = subprocess.run(["e2fsck", "-f", "-y", str(raw)], capture_output=True, text=True)
        if check.returncode >= 4:   # 0/1/2 = in Ordnung bzw. repariert
            raise ShrinkError(f"e2fsck meldet Fehler auf {p.part}: {check.stdout.strip().splitlines()[-1:]}")
        _run(["resize2fs", str(raw), f"{p.new_size // 1024}K"], "resize2fs")
    os.truncate(raw, p.new_size)
    if cancel.is_set():
        raise ShrinkError("Abgebrochen")
    with open(target, "wb") as out:
        c = subprocess.Popen([tool, "-c", "-s", str(raw), "-o", "-", "-L", str(log)], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
        z = subprocess.Popen(["zstd", "-1", "-T0", "-q", "-c"], stdin=c.stdout, stdout=out)
        c.stdout.close()
        if z.wait() or c.wait():
            raise ShrinkError(f"{tool} (neu sichern) fehlgeschlagen – Protokoll: {log.read_text()[-300:]}"
                              if log.exists() else f"{tool} (neu sichern) fehlgeschlagen")
    report(p.used * 2, f"{p.part} gesichert")
    return target.stat().st_size


def ensure(image: str | Path, target_size: int, nas_root: str | Path | None, source_disk: str | None = None,
           progress: Progress = lambda ev: None, cancel: threading.Event | None = None) -> Path:
    """Angepasstes Image für target_size liefern (vorhandenes wiederverwenden, sonst erstellen)."""
    existing = find_derived(image, target_size, source_disk)
    if existing:
        return existing
    return create(plan(image, target_size, source_disk), nas_root, progress, cancel)
