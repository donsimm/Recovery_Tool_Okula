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

from okula_recovery import __version__, config, wire

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
