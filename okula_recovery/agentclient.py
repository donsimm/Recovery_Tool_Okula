"""Tool-Seite: Agent ansprechen, Disk-Image empfangen und auf das NAS schreiben.

Ablage auf dem NAS:
    <NAS>/images/<Maschine>/<JJJJ-MM-TT_HHMM>_<disk>/   (während der Arbeit: ….partial)
        okula-image.json   Metadaten, Dateiliste mit SHA256
        sda.sfdisk, sda-head.img, sda-tail.img, sda1.ntfs.pcl.zst, …
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import shutil
import ssl
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from okula_recovery import __version__, clonezilla, config, wire

IMAGE_META = "okula-image.json"
SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")

# Fehlermeldungen von partclone → Hinweis
IMAGE_HINTS = (
    ("NTFS is inconsistent", "Windows wurde nicht vollständig heruntergefahren (Schnellstart/Ruhezustand). "
                             "Windows starten und mit Shift+Herunterfahren beenden oder chkdsk ausführen"),
    ("Input/output error", "Lesefehler auf der Disk – Disk ist vermutlich defekt"),
    ("bad sectors", "Lesefehler auf der Disk – Disk ist vermutlich defekt"),
)

Progress = Callable[[dict], None]


class AgentError(Exception):
    pass


def key_path() -> Path:
    return config.config_path().parent / "agent.key"


def load_or_create_key() -> bytes:
    """Gemeinsamer Schlüssel Tool ↔ Agent-Sticks; wird beim ersten Gebrauch erzeugt."""
    path = key_path()
    try:
        key = bytes.fromhex(path.read_text().strip())
        if len(key) == wire.KEY_LEN:
            return key
    except (OSError, ValueError):
        pass
    key = secrets.token_bytes(wire.KEY_LEN)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex() + "\n")
    return key


def _hint(message: str) -> str:
    for needle, hint in IMAGE_HINTS:
        if needle in message:
            return f"{message} – {hint}"
    return message


def _connect(ip: str, key: bytes, port: int) -> ssl.SSLSocket:
    try:
        return wire.connect(ip, key, port)
    except ssl.SSLError:
        raise AgentError("Agent lehnt den Schlüssel ab – Agent-Stick mit diesem Tool neu erstellen") from None
    except OSError as e:
        raise AgentError(f"Agent {ip}:{port} nicht erreichbar: {e}") from None


def get_info(ip: str, key: bytes, port: int = wire.PORT) -> dict:
    with _connect(ip, key, port) as sock:
        wire.send_json(sock, {"cmd": "info"})
        reply = wire.recv_json(sock)
    if reply.get("type") == "error":
        raise AgentError(reply.get("message", "Fehler"))
    return reply


def power(ip: str, key: bytes, action: str = "poweroff", port: int = wire.PORT, delay: int = 5) -> None:
    """Zielmaschine herunterfahren („poweroff“) oder neu starten („reboot“)."""
    with _connect(ip, key, port) as sock:
        wire.send_json(sock, {"cmd": "power", "action": action, "delay": delay})
        reply = wire.recv_json(sock)
    if reply.get("type") != "ok":
        raise AgentError(reply.get("message", "Agent hat abgelehnt"))


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")[:80] or "maschine"


def image_dir(nas_root: str | Path, machine: str, disk: str, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M")
    return Path(nas_root) / "images" / safe_name(machine) / f"{stamp}_{Path(disk).name}"


def create_image(ip: str, key: bytes, disk: str, nas_root: str | Path, machine: str,
                 progress: Progress, cancel: threading.Event, port: int = wire.PORT,
                 source: dict | None = None) -> Path:
    final = image_dir(nas_root, machine, disk)
    if final.exists():
        final = final.with_name(final.name + time.strftime("%S"))
    work = final.with_name(final.name + ".partial")
    work.mkdir(parents=True)

    meta: dict = {"format": "okula-image", "version": 1, "tool_version": __version__, "machine": machine,
                  "source": source or {}, "agent_ip": ip, "started": datetime.now().isoformat(timespec="seconds"),
                  "files": []}
    current = None
    sock = _connect(ip, key, port)
    try:
        # partclone liest zuerst die Belegungs-Bitmap; bei grossen HDDs kommen minutenlang keine Daten
        sock.settimeout(900)
        wire.send_json(sock, {"cmd": "image", "disk": disk})
        received = 0
        started = time.monotonic()
        last_report = 0.0
        state: dict = {}
        while True:
            if cancel.is_set():
                raise AgentError("Abgebrochen")
            kind, payload = wire.recv_frame(sock)
            if kind == wire.FRAME_DATA:
                if current is None:
                    raise wire.ProtocolError("Daten ohne Datei")
                current["fh"].write(payload)
                current["hash"].update(payload)
                current["size"] += len(payload)
                received += len(payload)
                now = time.monotonic()
                if now - last_report >= 0.5:
                    last_report = now
                    progress({**state, "phase": "data", "file_bytes": current["size"], "total_bytes": received,
                              "speed": received / max(now - started, 0.001)})
                continue

            msg = payload
            t = msg.get("type")
            if t == "begin":
                meta["disk"] = msg.get("disk", {})
                meta["plan"] = msg.get("plan", [])
                meta["compression"] = msg.get("compression", "")
                progress({"phase": "begin", "disk": meta["disk"], "plan": meta["plan"]})
            elif t == "file":
                name = str(msg.get("file") or "")
                if not SAFE_FILE_RE.match(name) or name == IMAGE_META:
                    raise wire.ProtocolError(f"Ungültiger Dateiname vom Agent: {name!r}")
                current = {"name": name, "fh": open(work / name, "xb"), "hash": hashlib.sha256(), "size": 0}
                state = {"phase": "file", "file": name, "part": msg.get("part", ""), "total": msg.get("total", 0),
                         "pct": None}
                progress(state)
            elif t == "progress":
                state = {**state, "pct": msg.get("pct")}
            elif t == "file_end":
                if current is None or msg.get("file") != current["name"]:
                    raise wire.ProtocolError("file_end ohne passende Datei")
                current["fh"].close()
                digest = current["hash"].hexdigest()
                if msg.get("sha256") != digest or msg.get("size") != current["size"]:
                    raise AgentError(f"Prüfsumme von {current['name']} stimmt nicht – Übertragung fehlerhaft")
                meta["files"].append({"name": current["name"], "size": current["size"], "sha256": digest})
                current = None
            elif t == "error":
                raise AgentError(_hint(str(msg.get("message", "Fehler auf dem Agent"))))
            elif t == "end":
                break

        meta["completed"] = datetime.now().isoformat(timespec="seconds")
        meta["bytes"] = received
        (work / IMAGE_META).write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        work.rename(final)
        progress({"phase": "done", "path": str(final), "total_bytes": received})
        return final
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise AgentError("Kein Platz mehr auf dem NAS") from None
        if isinstance(e, (ConnectionError, TimeoutError, ssl.SSLError)):
            raise AgentError(f"Verbindung zum Agent abgebrochen: {e}") from None
        raise
    except wire.ProtocolError as e:
        raise AgentError(f"Verbindung zum Agent gestört: {e}") from None
    finally:
        if current is not None:
            current["fh"].close()
        sock.close()
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)  # nur unser eigener .partial-Ordner


# ---------- Zurückspielen ----------

def load_image(path: str | Path) -> dict:
    path = Path(path)
    try:
        meta = json.loads((path / IMAGE_META).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise AgentError(f"Kein gültiges Okula-Image: {e}") from None
    if meta.get("format") != "okula-image" or meta.get("version") != 1:
        raise AgentError("Unbekanntes Image-Format")
    for f in meta.get("files", []):
        if not SAFE_FILE_RE.match(f.get("name", "")) or not (path / f["name"]).is_file():
            raise AgentError(f"Datei fehlt im Image: {f.get('name')}")
    return meta


def restore_steps(meta: dict) -> list[dict]:
    """Schritte für den Agent aus dem Sicherungsplan des Images."""
    sizes = {f["name"]: f["size"] for f in meta.get("files", [])}
    steps = []
    for s in meta.get("plan", []):
        if s.get("kind") == "skip":
            steps.append({"kind": "swap", "part": s["part"], "uuid": s.get("uuid", ""), "label": s.get("label", "")})
        elif s.get("kind") == "pipe":
            tool = s["cmds"][0][0]
            variant = tool.split(".", 1)[1] if tool.startswith("partclone.") else ""
            steps.append({"kind": "dd" if variant == "dd" else "pcl", "variant": variant, "part": s["part"],
                          "file": s["file"], "size": sizes.get(s["file"], 0),
                          "compressed": s["file"].endswith(".zst")})
    return steps


def verify_image(path: str | Path, meta: dict, progress: Progress, cancel: threading.Event) -> None:
    """Liest alle Dateien und vergleicht die SHA256 – bevor auf die Zieldisk geschrieben wird."""
    total = sum(f["size"] for f in meta["files"]) or 1
    done = 0
    last = 0.0
    for f in meta["files"]:
        h = hashlib.sha256()
        with open(Path(path) / f["name"], "rb") as fh:
            while chunk := fh.read(wire.CHUNK):
                if cancel.is_set():
                    raise AgentError("Abgebrochen")
                h.update(chunk)
                done += len(chunk)
                if time.monotonic() - last >= 0.5:
                    last = time.monotonic()
                    progress({"phase": "verify", "file": f["name"], "fraction": done / total})
        if h.hexdigest() != f["sha256"]:
            raise AgentError(f"Image beschädigt: Prüfsumme von {f['name']} stimmt nicht")


def _read_pieces(pieces: list[Path]):
    """Liest (gesplittete) Image-Dateien nacheinander als einen Datenstrom."""
    for piece in pieces:
        with open(piece, "rb") as fh:
            while chunk := fh.read(wire.CHUNK):
                yield chunk


def _agent_error(sock) -> str | None:
    """Nach einem Sendefehler: hat der Agent noch eine Fehlermeldung geschickt?"""
    try:
        sock.settimeout(5)
        while True:
            kind, msg = wire.recv_frame(sock)
            if kind == wire.FRAME_JSON and msg.get("type") == "error":
                return str(msg.get("message"))
    except (OSError, wire.ProtocolError, ssl.SSLError):
        return None


def _expect(sock, wanted: str) -> dict:
    msg = wire.recv_json(sock)
    if msg.get("type") == "error":
        raise AgentError(_hint(str(msg.get("message", "Fehler auf dem Agent"))))
    if msg.get("type") != wanted:
        raise wire.ProtocolError(f"{wanted} erwartet, {msg.get('type')} erhalten")
    return msg


def okula_source(image_path: Path) -> dict:
    meta = load_image(image_path)
    disk = meta.get("disk") or {}
    names = {f["name"] for f in meta["files"]}
    sfdisk_file = f"{disk.get('name')}.sfdisk"
    head_file = f"{disk.get('name')}-head.img"
    if head_file not in names:
        raise AgentError("Image ohne Kopfbereich – kann nicht zurückgespielt werden")
    steps = restore_steps(meta)
    for st in steps:
        if st.get("file"):
            st["pieces"] = [image_path / st["file"]]
    return {"source": disk, "steps": steps, "format": "okula",
            "sfdisk": (image_path / sfdisk_file).read_text() if sfdisk_file in names else "",
            "head": (image_path / head_file).read_bytes(),
            "verify": lambda progress, cancel: verify_image(image_path, meta, progress, cancel)}


def image_source(image_path: str | Path, disk: str | None = None) -> dict:
    """Quelle für restore_image: Okula-Image oder Clonezilla-Image (disk = welche Disk daraus)."""
    image_path = Path(image_path)
    if clonezilla.is_clonezilla(image_path):
        try:
            src = clonezilla.build(image_path, disk or clonezilla.disks(image_path)[0])
        except (clonezilla.ClonezillaError, IndexError) as e:
            raise AgentError(str(e) or "Clonezilla-Image ohne Disk") from None

        def verify(progress, cancel):
            try:
                clonezilla.verify(src, progress, cancel)
            except clonezilla.ClonezillaError as e:
                raise AgentError(str(e)) from None
        src["verify"] = verify
        return src
    return okula_source(image_path)


def restore_image(ip: str, key: bytes, image_path: str | Path, target_disk: str, progress: Progress,
                  cancel: threading.Event, port: int = wire.PORT, verify: bool = True,
                  source_disk: str | None = None) -> None:
    src = image_source(image_path, source_disk)
    if verify:
        src["verify"](progress, cancel)
    steps = src["steps"]
    req = {"cmd": "restore", "disk": target_disk, "source": src["source"], "sfdisk": src["sfdisk"],
           "head": src["head"].hex(), "steps": [{k: v for k, v in st.items() if k != "pieces"} for st in steps]}

    total = sum(s.get("size", 0) for s in steps) or 1
    sent = 0
    started = time.monotonic()
    sock = _connect(ip, key, port)
    try:
        sock.settimeout(900)
        wire.send_json(sock, req)
        progress({"phase": "table"})
        _expect(sock, "ready")
        for s in steps:
            if s["kind"] == "swap":
                continue
            progress({"phase": "file", "file": s["file"], "part": s["part"]})
            h = hashlib.sha256()
            size = 0
            last = 0.0
            try:
                wire.send_json(sock, {"type": "file", "file": s["file"]})
                for chunk in _read_pieces(s["pieces"]):
                    if cancel.is_set():
                        raise AgentError("Abgebrochen – die Zieldisk ist jetzt unvollständig")
                    wire.send_data(sock, chunk)
                    h.update(chunk)
                    size += len(chunk)
                    sent += len(chunk)
                    if time.monotonic() - last >= 0.5:
                        last = time.monotonic()
                        progress({"phase": "data", "part": s["part"], "fraction": sent / total,
                                  "total_bytes": sent, "speed": sent / max(time.monotonic() - started, 0.001)})
                wire.send_json(sock, {"type": "file_end", "file": s["file"], "size": size, "sha256": h.hexdigest()})
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError) as e:
                raise AgentError(_hint(_agent_error(sock) or f"Verbindung zum Agent abgebrochen: {e}")) from None
            _expect(sock, "file_done")
        wire.send_json(sock, {"type": "end"})
        _expect(sock, "done")
        progress({"phase": "done", "total_bytes": sent})
    except wire.ProtocolError as e:
        raise AgentError(f"Verbindung zum Agent gestört: {e}") from None
    except (TimeoutError, ConnectionError) as e:
        raise AgentError(f"Verbindung zum Agent abgebrochen: {e}") from None
    finally:
        sock.close()
