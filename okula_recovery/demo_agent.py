"""Demo-Gerät zum Vorführen: ein simulierter Agent auf dem Server selbst.

Start aus dem Tool (Extras → Demo-Gerät starten) oder: python3 -m okula_recovery.demo_agent --key-file …

Es ist der echte Agent-Steuerdienst (gleiches Protokoll, gleiche Verschlüsselung) – aber alle Teile, die Disks
oder das System anfassen würden, sind durch Attrappen ersetzt: erfundene Disks und erfundenes Inventar, Aufträge
laufen in etwa einer Minute durch, Daten werden nur empfangen und verworfen. Das Demo-Gerät meldet sich nur bei
127.0.0.1 (andere Geräte im Netz sehen nichts) und läuft als normaler Benutzer ohne Root-Rechte.

Ein Demo-Image (wenige MB, im Image als „demo“ markiert) lässt sich nur auf das Demo-Gerät zurückspielen.
Fehler vorführen: Datei <Konfig>/demo-fehler anlegen (Extras → „Demo: nächster Auftrag mit Fehler“) – der nächste
Auftrag bricht bei etwa 40 % mit einer Meldung ab.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

from okula_recovery import (__version__, agent, deploy, discovery, filebackup, imaging, inventory, wininstall,
                            wire)

DEMO_ID = "okula-demo-0001"            # Agent-ID (beim echten Agent die Board-UUID)
DEMO_MAC = "02:0d:e0:00:00:01"          # lokal verwaltete MAC – gibt es in keinem echten Gerät
DEMO_HOST = "DEMO-PC"
DEMO_DISK_PATH = "/dev/demo-nvme0n1"    # kein echtes Gerät – auch ohne Attrappen nicht beschreibbar
GB = 1000**3
DURATION = 45.0                         # so lange dauert ein Auftrag ungefähr (Sekunden)

ImagingError = imaging.ImagingError
fail_flag: Path | None = None
offline_until = 0.0


def _part(n: int, size: int, fstype: str, label: str, parttype: str) -> dict:
    return {"name": f"demo-nvme0n1p{n}", "path": f"{DEMO_DISK_PATH}p{n}", "size": size, "fstype": fstype,
            "label": label, "uuid": f"0de30000-0000-4000-8000-00000000000{n}", "parttype": parttype,
            "mounted": False}


DISK = {"name": "demo-nvme0n1", "path": DEMO_DISK_PATH, "size": 512110190592, "model": "Demo SSD 512GB",
        "serial": "DEMO-SSD-0001", "transport": "nvme", "pttype": "gpt", "fstype": "",
        "partitions": [_part(1, 272629760, "vfat", "SYSTEM", "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"),
                       _part(2, 16777216, "", "", "e3c9e316-0b5c-4c58-a10a-04eb08e6c5d4"),
                       _part(3, 510745690112, "ntfs", "Windows", "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"),
                       _part(4, 1073741824, "ntfs", "Recovery", "de94bba4-06d1-4d40-a16a-bfd50179d6ac")]}

INVENTORY = {
    "dmi": {"sys_vendor": "Okula", "product_name": "Demo-PC (Vorführung)", "product_serial": "DEMO-0001",
            "product_uuid": DEMO_ID, "chassis": "Notebook", "board_vendor": "Okula", "board_name": "Demo-Board",
            "bios_vendor": "Okula", "bios_version": "1.0 (Demo)", "bios_date": "10/29/2026"},
    "cpu": {"model": "Intel(R) Core(TM) i5-1145G7 @ 2.60GHz (Demo)", "cores": 4, "threads": 8},
    "memory": 16 * 1024**3,
    "batteries": [{"name": "BAT0", "manufacturer": "Demo", "model": "Demo-Akku 56Wh", "health_percent": 87}],
    "network": [{"name": "enp0s31f6", "mac": DEMO_MAC, "wireless": False},
                {"name": "wlp0s20f3", "mac": "02:0d:e0:00:00:02", "wireless": True}],
    "disks": [{**DISK, "smart": {"passed": True, "power_on_hours": 3120, "temperature": 36}}],
    "systems": [{"family": "Windows", "name": "Windows 11 Pro 24H2", "build": "26100", "edition": "Professional",
                 "hostname": DEMO_HOST, "partition": "demo-nvme0n1p3", "disk": "demo-nvme0n1"}],
    "oem_key": "DEMOA-DEMOB-DEMOC-DEMOD-DEMOE",
    "platform": {"tpm": "2.0", "uefi": True, "secure_boot": True},
}

USERS = ("Anna", "Demo")
DEMO_FILES = {  # Benutzerdaten für Backups (klein, mit Text drin)
    "Desktop/Offerte Müller AG.docx": 48_000, "Desktop/Notizen.txt": 2_000,
    "Documents/Buchhaltung 2026.xlsx": 180_000, "Documents/Vertrag.pdf": 260_000,
    "Pictures/Firmenanlass.jpg": 420_000, "Downloads/Anleitung.pdf": 150_000,
    "AppData/Local/Google/Chrome/User Data/Default/Bookmarks": 6_000,
}


# ---------- Hilfen ----------

def set_duration(seconds: float) -> None:
    global DURATION
    DURATION = max(1.0, seconds)


def maybe_fail(fraction: float) -> None:
    """Fehler vorführen: ist die Merker-Datei da, bricht der Auftrag bei ~40 % ab (Merker wird gelöscht)."""
    if fail_flag is not None and fraction >= 0.4 and fail_flag.exists():
        try:
            fail_flag.unlink()
        except OSError:
            pass
        raise ImagingError("Demo: simulierter Fehler – Verbindung zur Disk unterbrochen (Lesefehler)")


def _pace(done: float, total: float, started: float, duration: float | None = None) -> None:
    """So warten, dass der Auftrag insgesamt etwa duration Sekunden dauert."""
    target = started + (duration or DURATION) * done / max(total, 1)
    wait = target - time.monotonic()
    if wait > 0:
        time.sleep(min(wait, 2.0))


def _consume(sock, expected: dict, on_bytes, started: float, total: int, before: int) -> int:
    n = 0
    for chunk in imaging._frames(sock, expected):
        n += len(chunk)
        on_bytes(before + n)
        maybe_fail((before + n) / max(total, 1))
        _pace(before + n, total, started)
    return n


def _payload(name: str, size: int):
    """Inhalt einer Demo-Datei (Text, damit klar ist, dass es eine Attrappe ist)."""
    line = f"Okula Recovery Tool – Demo-Datei {name} (keine echten Daten)\n".encode()
    data = line * (size // len(line) + 1)
    return data[:size]


# ---------- Attrappen für die Teile, die Disks anfassen würden ----------

def list_disks() -> list[dict]:
    return [json.loads(json.dumps(DISK))]


def collect_inventory(with_os: bool = True, skip=frozenset()) -> dict:
    return {**json.loads(json.dumps(INVENTORY)), "collected": time.strftime("%Y-%m-%dT%H:%M:%S")}


def stream_disk_image(sock, disk_path: str, log=print, report=None) -> None:
    if disk_path != DEMO_DISK_PATH:
        raise ImagingError(f"Disk {disk_path} nicht gefunden")
    report = report or (lambda f, p, n: None)
    name = DISK["name"]
    sizes = {"demo-nvme0n1p1": 400_000, "demo-nvme0n1p2": 100_000, "demo-nvme0n1p3": 9_000_000,
             "demo-nvme0n1p4": 300_000}
    tools = {"vfat": "partclone.vfat", "ntfs": "partclone.ntfs", "": "partclone.dd"}
    plan = [{"file": f"{name}.sfdisk", "kind": "command", "cmd": ["sfdisk", "-d", DEMO_DISK_PATH], "optional": True},
            {"file": f"{name}-head.img", "kind": "range", "path": DEMO_DISK_PATH, "offset": 0,
             "length": imaging.HEAD_TAIL},
            {"file": f"{name}-tail.img", "kind": "range", "path": DEMO_DISK_PATH,
             "offset": DISK["size"] - imaging.HEAD_TAIL, "length": imaging.HEAD_TAIL}]
    for p in DISK["partitions"]:
        ext = f"{p['fstype'] or 'dd'}.pcl.zst"
        plan.append({"file": f"{p['name']}.{ext}", "kind": "pipe", "part": p["name"], "size": p["size"],
                     "fstype": p["fstype"], "cmds": [[tools[p["fstype"]], "-c", "-s", p["path"], "-o", "-"],
                                                     ["zstd", "-1", "-T0", "-q", "-c"]]})
    wire.send_json(sock, {"type": "begin", "disk": DISK, "plan": plan, "compression": "zstd", "demo": True})
    sfdisk = (f"label: gpt\nlabel-id: 0DE30000-0000-4000-8000-000000000000\ndevice: {DEMO_DISK_PATH}\n"
              "unit: sectors\nfirst-lba: 34\nsector-size: 512\n\n" +
              "".join(f"{p['path']} : start={2048 + i * 1000}, size={p['size'] // 512}, type={p['parttype'].upper()}"
                      f", uuid={p['uuid'].upper()}\n" for i, p in enumerate(DISK["partitions"])))
    imaging._send_file(sock, f"{name}.sfdisk", [sfdisk.encode()], {}, lambda n: {})
    imaging._send_file(sock, f"{name}-head.img", [bytes(imaging.HEAD_TAIL)], {}, lambda n: {})
    imaging._send_file(sock, f"{name}-tail.img", [bytes(imaging.HEAD_TAIL)], {}, lambda n: {})
    total = sum(sizes.values())
    started = time.monotonic()
    done = 0
    for step in plan[3:]:
        part, want = step["part"], sizes[step["part"]]
        log(f"Demo: {part} wird gesichert …")

        def chunks(part=part, want=want, before=done):
            sent = 0
            while sent < want:
                n = min(256 * 1024, want - sent)
                yield _payload(part, n)
                sent += n
                maybe_fail((before + sent) / total)
                _pace(before + sent, total, started)

        def tick(n: int, part=part, want=want, before=done) -> dict:
            report((before + n) / total, part, before + n)
            return {"part": part, "pct": round(100 * n / want, 1)}

        imaging._send_file(sock, step["file"], chunks(), {"part": part, "total": step["size"]}, tick)
        done += want
    wire.send_json(sock, {"type": "end"})


def restore_disk(sock, req: dict, log=print, report=None) -> None:
    report = report or (lambda f, p, n: None)
    if str(req.get("disk") or "") != DEMO_DISK_PATH:
        raise ImagingError(f"Zieldisk {req.get('disk')} nicht gefunden")
    source = req.get("source") or {}
    if int(source.get("size") or 0) > DISK["size"]:
        raise ImagingError("Zieldisk ist kleiner als die Quelldisk")
    steps = req.get("steps") or []
    by_file = {s["file"]: s for s in steps if s.get("file")}
    total = sum(int(s.get("size") or 0) for s in by_file.values()) or 1
    log("Demo: Partitionstabelle geschrieben (simuliert)")
    wire.send_json(sock, {"type": "ready", "devices": {s["part"]: f"{DEMO_DISK_PATH}p{i}"
                                                       for i, s in enumerate(steps, 1) if s.get("part")}})
    started, received = time.monotonic(), 0
    while True:
        msg = wire.recv_json(sock)
        if msg.get("type") == "end":
            break
        step = by_file.get(msg.get("file"))
        if msg.get("type") != "file" or step is None:
            raise ImagingError(f"Unerwartete Datei: {msg.get('file')}")
        received += _consume(sock, step, lambda n, p=step["part"]: report(n / total, p, n), started, total, received)
        wire.send_json(sock, {"type": "file_done", "file": step["file"]})
    wire.send_json(sock, {"type": "done"})


def _receive_files(sock, req: dict, report, key=lambda m: str(m.get("path") or ""), ack=True) -> int:
    """Dateien empfangen und verwerfen (Installation, Zurückschreiben, Ordner senden)."""
    total = int(req.get("bytes") or 0) or sum(int(f.get("size") or 0) for f in req.get("files") or []) or 1
    wire.send_json(sock, {"type": "ready"})
    started, received, files = time.monotonic(), 0, 0
    while True:
        msg = wire.recv_json(sock)
        kind = msg.get("type")
        if kind == "end":
            return files
        if kind == "dir":
            continue
        if kind != "file":
            raise ImagingError(f"Unerwartete Nachricht: {kind}")
        path = key(msg)
        received += _consume(sock, {"file": path}, lambda n, p=path: report(min(1.0, n / total), p, n),
                             started, total, received)
        files += 1
        if ack:
            wire.send_json(sock, {"type": "file_done", "path": path})


def install(sock, req: dict, log=print, report=None) -> str:
    log("Demo: Windows-Installation (Dateien werden nur empfangen)")
    _receive_files(sock, req, report or (lambda f, p, n: None))
    return "0007"


def bootprep(sock, req: dict, log=print, report=None) -> str:
    log("Demo: Linux-Installation (Dateien werden nur empfangen)")
    _receive_files(sock, req, report or (lambda f, p, n: None))
    return "0008"


def profiles(busy=frozenset()) -> list[dict]:
    return [{"part": f"{DEMO_DISK_PATH}p3", "name": "demo-nvme0n1p3", "disk": DEMO_DISK_PATH, "fstype": "ntfs",
             "size": DISK["partitions"][2]["size"], "label": "Windows", "os": "Windows 11 Pro 24H2",
             "kind": "windows", "users": [{"name": u, "path": f"Users/{u}"} for u in USERS]}]


def browse(dev: str, rel: str) -> list[dict]:
    rel = rel.strip("/")
    if not rel:
        names = ["Users", "Windows", "Program Files", "Daten"]
    elif rel == "Users":
        names = list(USERS) + ["Public"]
    elif rel.startswith("Users/") and rel.count("/") == 1:
        names = ["Desktop", "Documents", "Pictures", "Downloads", "AppData"]
    elif rel == "Daten":
        names = ["Buchhaltung", "Projekte"]
    else:
        return [{"name": n.split("/")[-1], "dir": False, "size": s, "mtime": int(time.time()) - 86400}
                for n, s in DEMO_FILES.items() if n.startswith(rel.split("/", 2)[-1] + "/")][:20]
    return [{"name": n, "dir": True, "size": 0, "mtime": int(time.time()) - 86400} for n in names]


def _selected(sources: list[dict]) -> list[tuple[str, int]]:
    out = []
    for src in sources:
        path = str(src.get("path") or "").strip("/")
        for user in USERS:
            for rel, size in DEMO_FILES.items():
                full = f"Users/{user}/{rel}"
                if not path or full == path or full.startswith(path + "/") or fnmatch.fnmatchcase(full, path):
                    out.append((full, size))
    return list(dict.fromkeys(out))


def estimate(sources: list[dict]) -> dict:
    files = _selected(sources)
    return {"type": "estimate", "files": len(files), "bytes": sum(s for _p, s in files), "skipped": 0}


def backup(sock, req: dict, log=print, report=None) -> None:
    report = report or (lambda f, p, n: None)
    files = _selected(req.get("sources") or [])
    total = sum(s for _p, s in files) or 1
    wire.send_json(sock, {"type": "plan", "files": len(files), "bytes": total, "skipped": 0})
    started, sent = time.monotonic(), 0
    for path, size in files:
        data = _payload(path, size)
        wire.send_json(sock, {"type": "file", "path": f"demo-nvme0n1p3/{path}", "size": size,
                              "mtime": int(time.time()) - 86400})
        h = hashlib.sha256(data)
        for i in range(0, len(data), wire.CHUNK):
            wire.send_data(sock, data[i:i + wire.CHUNK])
        sent += size
        report(sent / total, path, sent)
        maybe_fail(sent / total)
        _pace(sent, total, started, DURATION / 2)
        wire.send_json(sock, {"type": "file_end", "size": size, "sha256": h.hexdigest(), "error": ""})
    wire.send_json(sock, {"type": "done", "files": len(files), "bytes": sent, "skipped": [], "skipped_count": 0})


def restore_files(sock, req: dict, log=print, report=None) -> None:
    files = _receive_files(sock, req, report or (lambda f, p, n: None), ack=False)
    wire.send_json(sock, {"type": "done", "files": files, "renamed": 0})


def customize(req: dict, log=print) -> dict:
    time.sleep(2)
    log("Demo: Antwortdatei (Name, Key) geschrieben (simuliert)")
    return {"type": "done", "results": [{"part": f"{DEMO_DISK_PATH}p3", "system": "windows", "action": "unattend"}]}


def deliver(sock, req: dict, log=print, report=None) -> None:
    files = _receive_files(sock, req, report or (lambda f, p, n: None), ack=False)
    wire.send_json(sock, {"type": "done", "files": files, "bytes": int(req.get("bytes") or 0)})
    log(f"Demo: Ordner auf den Desktop gelegt (simuliert): {', '.join(map(str, req.get('items') or []))}")


BOOT = {"order": ["0001", "0002", "0003"], "netfirst": False}
LABELS = {"0001": "Windows Boot Manager", "0002": "UEFI: USB-Stick", "0003": "UEFI: PXE IPv4 Intel(R) Ethernet"}


def boot_status() -> dict:
    return {"uefi": True, "order": list(BOOT["order"]), "network": "0003", "labels": dict(LABELS),
            "netfirst": BOOT["order"][0] == "0003"}


def set_netfirst(on: bool, saved: list[str] | None = None) -> dict:
    previous = list(BOOT["order"])
    if on:
        BOOT["order"] = ["0003"] + [n for n in previous if n != "0003"]
    else:
        BOOT["order"] = list(saved) if saved and set(saved) == set(previous) else \
            [n for n in previous if n != "0003"] + ["0003"]
    return {**boot_status(), "previous": previous}


def power_action(action: str) -> None:
    """Neustart/Herunterfahren vorführen: das Demo-Gerät ist kurz weg und meldet sich dann wieder."""
    global offline_until
    offline_until = time.monotonic() + (20 if action == "reboot" else 40)
    agent.log(f"Demo: {'Neustart' if action == 'reboot' else 'Herunterfahren'} (simuliert) – "
              f"meldet sich in {int(offline_until - time.monotonic())} s wieder")


def install_fakes() -> None:
    """Alles ersetzen, was eine Disk oder das System anfassen würde (nur in diesem Prozess)."""
    imaging.list_disks = list_disks
    imaging.stream_disk_image = stream_disk_image
    imaging.restore_disk = restore_disk
    inventory.collect = collect_inventory
    filebackup.profiles, filebackup.browse, filebackup.estimate = profiles, browse, estimate
    filebackup.backup, filebackup.restore_files = backup, restore_files
    wininstall.install, wininstall.bootprep = install, bootprep
    wininstall.boot_status, wininstall.set_netfirst = boot_status, set_netfirst
    deploy.customize, deploy.deliver = customize, deliver
    deploy.open_keyboards = lambda pattern="": []
    agent.power_action = power_action
    agent.console = ""


# ---------- Start ----------

def beacon(control_port: int) -> dict:
    return {"type": discovery.BEACON_TYPE, "proto": discovery.PROTOCOL_VERSION, "id": DEMO_ID,
            "hostname": DEMO_HOST.lower(), "ip": "127.0.0.1", "mac": DEMO_MAC, "vendor": "Okula",
            "product": "Demo-PC (Vorführung)",
            "disks": [{"name": DISK["name"], "size": DISK["size"], "model": DISK["model"], "serial": DISK["serial"],
                       "transport": "nvme"}],
            "version": __version__, "control": control_port, "busy": agent.disk_locks.busy(),
            "inv": agent.inventory_state.version, **agent.job_state.beacon(), "demo": True}


def main(argv: list[str] | None = None) -> int:
    global fail_flag
    ap = argparse.ArgumentParser(description="Okula Demo-Gerät (simulierter Agent, nur 127.0.0.1)")
    ap.add_argument("--key-file", required=True, help="Schlüssel des Tools (agent.key)")
    ap.add_argument("--port", type=int, default=discovery.PORT)
    ap.add_argument("--control-port", type=int, default=wire.PORT)
    ap.add_argument("--fail-flag", default="", help="Datei: existiert sie, bricht der nächste Auftrag ab")
    ap.add_argument("--duration", type=float, default=DURATION, help="Dauer eines Auftrags in Sekunden")
    args = ap.parse_args(argv)
    key = agent.load_key(args.key_file)
    if key is None:
        print(f"Kein gültiger Schlüssel in {args.key_file}", file=sys.stderr)
        return 1
    fail_flag = Path(args.fail_flag) if args.fail_flag else None
    set_duration(args.duration)
    install_fakes()
    try:
        probe = socket.create_server(("127.0.0.1", args.control_port))
        probe.close()
    except OSError as e:
        print(f"TCP {args.control_port} belegt – läuft schon ein Agent auf diesem Rechner? ({e})", file=sys.stderr)
        return 2
    threading.Thread(target=agent.serve_control, args=(key, args.control_port, "127.0.0.1"), daemon=True).start()
    threading.Thread(target=agent.inventory_state.collect, daemon=True).start()
    for _ in range(50):  # erst melden, wenn der Steuerdienst Verbindungen annimmt
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", args.control_port)) == 0:
                break
        time.sleep(0.1)
    agent.log("Demo-Gerät gestartet (nur für dieses Tool, 127.0.0.1)")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        if time.monotonic() >= offline_until:
            try:
                sock.sendto(json.dumps(beacon(args.control_port)).encode(), ("127.0.0.1", args.port))
            except OSError:
                pass
        time.sleep(3)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
