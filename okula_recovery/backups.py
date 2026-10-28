"""Datei-Backups (Tool-Seite): Auswahl, Ablage auf dem NAS, Zurückspielen und Herunterladen.

Ablage:  NAS/Backups/<Gerät>/<JJJJ-MM-TT_HHMM>/
             okula-backup.json      Beschreibung (Gerät, Auswahl, Anzahl, übersprungene Dateien)
             dateien.tsv            je Datei: SHA-256, Grösse, Änderungszeit, Pfad
             Dateien/<Partition>/…  bei Ablage „Dateien“ (im Reiter Dateien durchsuchbar)
             backup.tar.zst         bei Ablage „Archiv“
Pfade im Backup beginnen mit dem Partitionsnamen, z. B. „sda3/Users/Anna/Documents/Offerte.docx“.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

from okula_recovery import agentclient, nasfiles, wire

BACKUP_DIR = "Backups"
MANIFEST = "okula-backup.json"
INDEX = "dateien.tsv"
FILES_DIR = "Dateien"
ARCHIVE = "backup.tar.zst"
RESTORE_DIR = "Okula-Wiederherstellung"

# Benutzerdaten (Windows): Kategorie → (Anzeige, Pfade relativ zum Benutzerordner; Platzhalter erlaubt)
WINDOWS_CATEGORIES = {
    "desktop": ("Desktop", ["Desktop"]),
    "documents": ("Dokumente", ["Documents"]),
    "pictures": ("Bilder", ["Pictures"]),
    "music": ("Musik", ["Music"]),
    "videos": ("Videos", ["Videos"]),
    "downloads": ("Downloads", ["Downloads"]),
    "favorites": ("Favoriten und Links", ["Favorites", "Links"]),
    "onedrive": ("OneDrive (lokale Kopie)", ["OneDrive", "OneDrive - *"]),
    "outlook": ("Outlook-Datendateien (PST)", ["AppData/Local/Microsoft/Outlook/*.pst",
                                               "AppData/Roaming/Microsoft/Outlook/*.pst"]),
    "browser": ("Browser-Lesezeichen (Chrome, Edge, Firefox)",
                ["AppData/Local/Google/Chrome/User Data/*/Bookmarks",
                 "AppData/Local/Microsoft/Edge/User Data/*/Bookmarks",
                 "AppData/Roaming/Mozilla/Firefox/Profiles/*/places.sqlite",
                 "AppData/Roaming/Mozilla/Firefox/Profiles/*/favicons.sqlite"]),
}
DEFAULT_CATEGORIES = ("desktop", "documents", "pictures", "music", "videos", "downloads", "favorites", "outlook",
                      "browser")

Progress = Callable[[dict], None]


class BackupError(Exception):
    pass


# ---------- Auswahl → Quellen für den Agent ----------

def profile_sources(part: str, user_path: str, kind: str, categories: list[str]) -> list[dict]:
    """Benutzerdaten eines Profils. Linux/home: ganzer Benutzerordner (Caches werden ohnehin übersprungen)."""
    if kind != "windows":
        return [{"part": part, "path": user_path}]
    paths = [p for c in categories for p in WINDOWS_CATEGORIES[c][1]]
    return [{"part": part, "path": f"{user_path}/{p}"} for p in paths]


def describe_selection(mode: str, items: list[str], storage: str) -> list[str]:
    what = {"profiles": "Benutzerdaten", "partitions": "Ganze Partitionen", "folders": "Eigene Ordner"}[mode]
    return [f"{what}: {', '.join(items)}", "Ablage: " + ("normale Dateien" if storage == "files" else "Archiv tar.zst")]


# ---------- Ablage ----------

def backup_root(root: str | Path, device_name: str) -> Path:
    base = nasfiles.resolve(root, BACKUP_DIR)
    base.mkdir(exist_ok=True)
    dev = base / agentclient.safe_name(device_name or "Gerät")
    dev.mkdir(exist_ok=True)
    return dev


def _safe_rel(rel: str) -> PurePosixPath:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise BackupError(f"Ungültiger Pfad im Backup: {rel}")
    return p


class _FrameReader:
    """Daten-Frames einer Datei als lesbarer Strom (für tarfile); kürzer als angekündigt → mit Nullen auffüllen."""

    def __init__(self, sock, size: int):
        self.sock, self.size, self.pos, self.buf = sock, size, 0, b""
        self.h = hashlib.sha256()
        self.end: dict | None = None

    def _next(self) -> None:
        if self.end is not None:
            return
        kind, payload = wire.recv_frame(self.sock)
        if kind == wire.FRAME_DATA:
            self.h.update(payload)
            self.buf += payload
        elif payload.get("type") == "file_end":
            self.end = payload
        else:
            raise BackupError(f"Unerwartete Nachricht: {payload.get('type')}")

    def read(self, n: int = -1) -> bytes:
        want = self.size - self.pos if n < 0 else min(n, self.size - self.pos)
        while len(self.buf) < want and self.end is None:
            self._next()
        if len(self.buf) < want:  # Lesefehler am Gerät: Rest mit Nullen (Datei wird als defekt vermerkt)
            self.buf += bytes(want - len(self.buf))
        out, self.buf = self.buf[:want], self.buf[want:]
        self.pos += len(out)
        return out

    def finish(self) -> dict:
        while self.end is None:
            self._next()
        return self.end


class FilesStore:
    def __init__(self, dest: Path):
        self.base = dest / FILES_DIR
        self.base.mkdir(parents=True, exist_ok=True)

    def add(self, rel: str, size: int, mtime: int, frames: _FrameReader) -> dict:
        path = self.base.joinpath(*_safe_rel(rel).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as out:
            while True:
                chunk = frames.read(4 * 1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        end = frames.finish()
        if end.get("error"):
            path.unlink(missing_ok=True)  # unvollständig: nicht als gute Datei liegen lassen
        elif mtime:
            os.utime(path, (mtime, mtime))
        return end

    def close(self) -> None:
        pass


class TarStore:
    def __init__(self, dest: Path):
        if not shutil.which("zstd"):
            raise BackupError("zstd fehlt auf dem Server – install.sh erneut ausführen")
        self.out = open(dest / ARCHIVE, "wb")
        self.proc = subprocess.Popen(["zstd", "-q", "-T0", "-3", "-c"], stdin=subprocess.PIPE, stdout=self.out)
        self.tar = tarfile.open(fileobj=self.proc.stdin, mode="w|", format=tarfile.PAX_FORMAT)

    def add(self, rel: str, size: int, mtime: int, frames: _FrameReader) -> dict:
        info = tarfile.TarInfo(str(_safe_rel(rel)))
        info.size, info.mtime, info.mode = size, mtime, 0o644
        self.tar.addfile(info, frames)
        return frames.finish()

    def close(self) -> None:
        self.tar.close()
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise BackupError("zstd: Archiv konnte nicht geschrieben werden")
        self.out.close()


@dataclass
class BackupInfo:
    path: Path
    manifest: dict

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def device(self) -> str:
        return self.manifest.get("device_name") or self.path.parent.name

    @property
    def size(self) -> int:
        return int(self.manifest.get("bytes") or 0)

    @property
    def created(self) -> datetime:
        try:
            return datetime.fromisoformat(self.manifest.get("created", ""))
        except ValueError:
            return datetime.fromtimestamp(self.path.stat().st_mtime)

    @property
    def storage(self) -> str:
        return self.manifest.get("storage", "files")

    @property
    def summary(self) -> str:
        m = self.manifest
        mode = {"profiles": "Benutzerdaten", "partitions": "Partitionen", "folders": "Ordner"}.get(m.get("mode"), "")
        return f"{mode} · {m.get('files', 0)} Dateien · {'Dateien' if self.storage == 'files' else 'tar.zst'}"


def list_backups(root: str | Path) -> list[BackupInfo]:
    base = Path(root) / BACKUP_DIR
    found = []
    if not base.is_dir():
        return found
    for dev in sorted(base.iterdir()):
        if not dev.is_dir() or dev.is_symlink():
            continue
        for b in sorted(dev.iterdir(), reverse=True):
            if b.name.endswith(".partial") or not (b / MANIFEST).is_file():
                continue
            try:
                found.append(BackupInfo(b, json.loads((b / MANIFEST).read_text())))
            except (OSError, ValueError):
                continue
    return found


def read_index(backup: Path) -> list[tuple[str, int, int, str]]:
    """[(Pfad, Grösse, mtime, sha256)] aus dateien.tsv."""
    rows = []
    try:
        for line in (backup / INDEX).read_text(encoding="utf-8").splitlines():
            sha, size, mtime, path = line.split("\t", 3)
            rows.append((path, int(size), int(mtime), sha))
    except (OSError, ValueError):
        pass
    return rows


# ---------- Sichern (Tool ← Agent) ----------

def run_backup(ip: str, key: bytes, port: int, disk: str, sources: list[dict], root: str | Path, device: dict,
               mode: str, storage: str, description: list[str], progress: Progress,
               cancel: threading.Event) -> Path:
    """Backup vom Agent holen und auf dem NAS ablegen. device: {id, name}. Gibt den Backup-Ordner zurück."""
    final = backup_root(root, device.get("name", "")) / time.strftime("%Y-%m-%d_%H%M")
    if final.exists():
        final = final.with_name(final.name + time.strftime("%S"))
    work = final.with_name(final.name + ".partial")
    work.mkdir()
    store = None
    index_lines: list[str] = []
    defective: list[dict] = []
    sock = agentclient._connect(ip, key, port)
    try:
        sock.settimeout(900)
        wire.send_json(sock, {"cmd": "backup", "disk": disk, "sources": sources})
        plan = agentclient._expect(sock, "plan")
        progress({"phase": "plan", "files": plan.get("files", 0), "bytes": plan.get("bytes", 0)})
        total = int(plan.get("bytes") or 0) or 1
        store = FilesStore(work) if storage == "files" else TarStore(work)
        received, count, started, last = 0, 0, time.monotonic(), 0.0
        while True:
            msg = wire.recv_json(sock)
            if msg.get("type") == "done":
                done = msg
                break
            if msg.get("type") == "error":
                raise BackupError(str(msg.get("message")))
            if msg.get("type") != "file":
                raise BackupError(f"Unerwartete Nachricht: {msg.get('type')}")
            if cancel.is_set():
                raise BackupError("Abgebrochen")
            rel, size, mtime = str(msg["path"]), int(msg.get("size") or 0), int(msg.get("mtime") or 0)
            frames = _FrameReader(sock, size)
            end = store.add(rel, size, mtime, frames)
            received += size
            count += 1
            if end.get("error"):
                defective.append({"path": rel, "reason": end["error"]})
            elif end.get("sha256") != frames.h.hexdigest():
                raise BackupError(f"Prüfsumme von {rel} stimmt nicht – Übertragung fehlerhaft")
            else:
                index_lines.append(f"{end['sha256']}\t{size}\t{mtime}\t{rel}")
            if time.monotonic() - last >= 0.5:
                last = time.monotonic()
                progress({"phase": "data", "fraction": min(1.0, received / total), "file": rel, "files": count,
                          "speed": received / max(time.monotonic() - started, 0.001)})
        store.close()
        store = None
        (work / INDEX).write_text("\n".join(index_lines) + ("\n" if index_lines else ""), encoding="utf-8")
        skipped = list(done.get("skipped") or []) + defective
        manifest = {"format": "okula-backup", "version": 1, "device_id": device.get("id", ""),
                    "device_name": device.get("name", ""), "created": datetime.now().isoformat(timespec="seconds"),
                    "mode": mode, "storage": storage, "sources": sources, "description": description,
                    "files": len(index_lines), "bytes": received, "skipped_count": int(done.get("skipped_count") or 0)
                    + len(defective), "skipped": skipped[:500], "tool_version": agentclient.__version__}
        (work / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        work.rename(final)
        progress({"phase": "done", "files": len(index_lines), "skipped": manifest["skipped_count"]})
        return final
    except wire.ProtocolError as e:
        raise BackupError(f"Verbindung zum Agent gestört: {e}") from None
    except (TimeoutError, ConnectionError) as e:
        raise BackupError(f"Verbindung zum Agent abgebrochen: {e}") from None
    finally:
        sock.close()
        if store is not None:
            try:
                store.close()
            except (BackupError, OSError, tarfile.TarError):
                pass
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)


# ---------- Dateien eines Backups lesen ----------

def iter_files(backup: Path, prefixes: list[str] | None = None) -> Iterator[tuple[str, int, int, object]]:
    """(Pfad, Grösse, mtime, lesbarer Strom) aller (bzw. der gewählten) Dateien – Dateien oder tar.zst."""
    def wanted(rel: str) -> bool:
        return not prefixes or any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in prefixes)

    manifest = json.loads((backup / MANIFEST).read_text())
    if manifest.get("storage", "files") == "files":
        for rel, size, mtime, _sha in read_index(backup):
            if wanted(rel):
                path = backup / FILES_DIR / Path(*_safe_rel(rel).parts)
                with open(path, "rb") as fh:
                    yield rel, size, mtime, fh
        return
    proc = subprocess.Popen(["zstd", "-dc", "-q", str(backup / ARCHIVE)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for info in tar:
                if info.isfile() and wanted(info.name):
                    _safe_rel(info.name)
                    yield info.name, info.size, int(info.mtime), tar.extractfile(info)
    finally:
        proc.stdout.close()
        proc.wait()


def selection_size(backup: Path, prefixes: list[str] | None) -> tuple[int, int]:
    rows = [r for r in read_index(backup)
            if not prefixes or any(r[0] == p or r[0].startswith(p.rstrip("/") + "/") for p in prefixes)]
    return len(rows), sum(r[1] for r in rows)


def download(backup: Path, target: Path, prefixes: list[str] | None, progress: Progress,
             cancel: threading.Event) -> int:
    """Dateien in einen Ordner auf dem Server/USB kopieren bzw. entpacken. Gibt die Anzahl zurück."""
    count, total = selection_size(backup, prefixes)
    done = n = 0
    last = 0.0
    for rel, _size, mtime, fh in iter_files(backup, prefixes):
        if cancel.is_set():
            raise BackupError("Abgebrochen")
        dest = target.joinpath(*_safe_rel(rel).parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as out:
            while chunk := fh.read(4 * 1024 * 1024):
                out.write(chunk)
                done += len(chunk)
                if time.monotonic() - last >= 0.5:
                    last = time.monotonic()
                    progress({"phase": "data", "fraction": done / (total or 1), "file": rel})
        if mtime:
            os.utime(dest, (mtime, mtime))
        n += 1
    progress({"phase": "done", "files": n})
    return n


# ---------- Zurückspielen (Tool → Agent) ----------

@dataclass
class RestorePlan:
    part: str                              # Zielpartition, z. B. /dev/sda3
    mapping: list[tuple[str, str]]         # (Präfix im Backup, Ziel relativ zur Partition)
    owner: str = ""                        # Linux: Besitzer der Dateien
    overwrite: bool = False
    prefixes: list[str] = field(default_factory=list)  # nur diese Teile des Backups

    def target(self, rel: str) -> str | None:
        for src, dst in sorted(self.mapping, key=lambda m: -len(m[0])):
            if rel == src or rel.startswith(src.rstrip("/") + "/") or not src:
                rest = rel[len(src):].lstrip("/") if src else rel
                return str(PurePosixPath(dst) / rest) if dst else rest
        return None


def run_restore(ip: str, key: bytes, port: int, disk: str, backup: Path, plan: RestorePlan, progress: Progress,
                cancel: threading.Event) -> dict:
    count, total = selection_size(backup, plan.prefixes)
    sock = agentclient._connect(ip, key, port)
    try:
        sock.settimeout(900)
        wire.send_json(sock, {"cmd": "filerestore", "disk": disk, "part": plan.part, "owner": plan.owner,
                              "overwrite": plan.overwrite, "bytes": total})
        agentclient._expect(sock, "ready")
        sent, n, started, last = 0, 0, time.monotonic(), 0.0
        for rel, size, mtime, fh in iter_files(backup, plan.prefixes):
            dest = plan.target(rel)
            if dest is None:
                continue
            if cancel.is_set():
                raise BackupError("Abgebrochen – bereits geschriebene Dateien bleiben auf dem Gerät")
            h = hashlib.sha256()
            got = 0
            try:
                wire.send_json(sock, {"type": "file", "path": dest, "size": size, "mtime": mtime})
                while chunk := fh.read(wire.CHUNK):
                    wire.send_data(sock, chunk)
                    h.update(chunk)
                    got += len(chunk)
                    sent += len(chunk)
                wire.send_json(sock, {"type": "file_end", "file": dest, "size": got, "sha256": h.hexdigest()})
            except (BrokenPipeError, ConnectionResetError) as e:
                raise BackupError(agentclient._agent_error(sock) or f"Verbindung zum Agent abgebrochen: {e}") from None
            n += 1
            if time.monotonic() - last >= 0.5:
                last = time.monotonic()
                progress({"phase": "data", "fraction": min(1.0, sent / (total or 1)), "file": dest, "files": n,
                          "speed": sent / max(time.monotonic() - started, 0.001)})
        wire.send_json(sock, {"type": "end"})
        result = agentclient._expect(sock, "done")
        progress({"phase": "done", "files": result.get("files", n), "renamed": result.get("renamed", 0)})
        return result
    except agentclient.AgentError as e:
        raise BackupError(str(e)) from None
    except wire.ProtocolError as e:
        raise BackupError(f"Verbindung zum Agent gestört: {e}") from None
    except (TimeoutError, ConnectionError) as e:
        raise BackupError(f"Verbindung zum Agent abgebrochen: {e}") from None
    finally:
        sock.close()


# ---------- kurze Abfragen beim Agent ----------

def _ask(ip: str, key: bytes, port: int, req: dict, wanted: str, timeout: int = 300) -> dict:
    with agentclient._connect(ip, key, port) as sock:
        sock.settimeout(timeout)
        wire.send_json(sock, req)
        return agentclient._expect(sock, wanted)


def get_profiles(ip: str, key: bytes, port: int) -> list[dict]:
    return _ask(ip, key, port, {"cmd": "profiles"}, "profiles").get("partitions", [])


def browse(ip: str, key: bytes, port: int, part: str, path: str) -> list[dict]:
    return _ask(ip, key, port, {"cmd": "browse", "part": part, "path": path}, "entries", 120).get("entries", [])


def estimate(ip: str, key: bytes, port: int, sources: list[dict]) -> dict:
    return _ask(ip, key, port, {"cmd": "estimate", "sources": sources}, "estimate", 900)
