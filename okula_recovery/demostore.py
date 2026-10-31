"""Demo-Speicher (Ä-027): lokaler Ordner für alle Daten des Demo-Geräts – das NAS wird nie gebraucht oder berührt.

Aufbau wie auf dem NAS, damit die normalen Abläufe ohne Sonderfall laufen:
    <Konfig-Ordner>/demo/images/      Demo-Images (Disk-Image erstellen, fertige Demo-Images)
    <Konfig-Ordner>/demo/Backups/     Demo-Backups
    <Konfig-Ordner>/demo/Verteilen/   Software, Test Files, Content mit Beispielprojekten
Fertige Demo-Images (wenige MB, als „demo“ markiert, gültige Prüfsummen):
    DEMO-Master-Win11        als Master-Image markiert – Prüfung ergibt ✔
    DEMO-Image-beschaedigt   gleich aufgebaut, ein Byte absichtlich verändert – Prüfung ergibt ✖
Kein GTK hier.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from okula_recovery import __version__, agentclient, backups, config, demo_agent, distribute, imaging, nas

MASTER = "DEMO-Master-Win11"
BROKEN = "DEMO-Image-beschaedigt"
PROJECTS = ("Projekt Alpha", "Projekt Beta", "Schulung 2026")
TITLE = "Demo (lokal, nicht auf dem NAS)"


def base() -> Path:
    return config.config_path().parent / "demo"


def images_dir(root: Path | None = None) -> Path:
    return Path(root or base()) / "images"


def ensure(root: Path | None = None) -> Path:
    """Demo-Speicher anlegen bzw. ergänzen (fehlende Ordner, Beispielprojekte und fertige Images)."""
    root = Path(root or base())
    for d in (images_dir(root), root / backups.BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)
    dist = distribute.ensure(root)
    samples = {
        dist / "Software" / "Demo-Installer.txt": "Beispiel – hier liegen Installationsprogramme.\n",
        dist / "Test Files" / "Testseite.txt": "Beispiel-Testdatei für die Vorführung.\n",
    }
    for project in PROJECTS:
        samples[dist / distribute.CONTENT / project / "Liesmich.txt"] = f"{project} – Beispielinhalt (Demo).\n"
    for path, text in samples.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    master = images_dir(root) / MASTER
    if not (master / agentclient.IMAGE_META).is_file():
        make_image(master, "Master-Image für die Vorführung (Sysprep, erfunden)")
        nas.set_master(master, True, "Demo")
    broken = images_dir(root) / BROKEN
    if not (broken / agentclient.IMAGE_META).is_file():
        make_image(broken, "Absichtlich beschädigt – zeigt, was „Image prüfen …“ meldet")
        corrupt(broken)
    return root


def make_image(folder: Path, note: str = "") -> Path:
    """Okula-Image wie vom Demo-Gerät (gleicher Plan, gleiche Dateien) mit gültigem okula-image.json."""
    tmp = folder.with_name(folder.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    name = demo_agent.DISK["name"]
    contents: dict[str, bytes] = {f"{name}.sfdisk": demo_agent.sfdisk_text().encode(),
                                  f"{name}-head.img": bytes(imaging.HEAD_TAIL),
                                  f"{name}-tail.img": bytes(imaging.HEAD_TAIL)}
    plan = demo_agent.image_plan()
    for step in plan[3:]:
        contents[step["file"]] = demo_agent._payload(step["part"], demo_agent.PART_SIZES[step["part"]])
    files = []
    for fname, data in contents.items():
        (tmp / fname).write_bytes(data)
        files.append({"name": fname, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    stamp = datetime.now().isoformat(timespec="seconds")
    meta = {"format": "okula-image", "version": 1, "tool_version": __version__, "machine": demo_agent.DEMO_HOST,
            "source": {"agent_id": demo_agent.DEMO_ID, "device_name": demo_agent.DEMO_HOST, "note": note},
            "agent_ip": agentclient.DEMO_IP, "started": stamp, "completed": stamp, "files": files,
            "demo": True, "disk": json.loads(json.dumps(demo_agent.DISK)), "plan": plan, "compression": "zstd",
            "bytes": sum(f["size"] for f in files)}
    (tmp / agentclient.IMAGE_META).write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    shutil.rmtree(folder, ignore_errors=True)
    tmp.rename(folder)
    return folder


def corrupt(folder: Path) -> str:
    """Ein Byte in der grössten Partitionsdatei ändern (Prüfsumme stimmt danach nicht mehr)."""
    target = max((p for p in folder.iterdir() if ".pcl." in p.name), key=lambda p: p.stat().st_size)
    with open(target, "r+b") as f:
        f.seek(target.stat().st_size // 2)
        b = f.read(1)
        f.seek(-1, 1)
        f.write(bytes([b[0] ^ 0xFF]))
    return target.name


def reset(root: Path | None = None) -> None:
    """Demo-Speicher löschen – beim nächsten Einschalten entsteht der Ausgangszustand neu."""
    shutil.rmtree(Path(root or base()), ignore_errors=True)


def is_demo_device(dev) -> bool:
    """DEMO-PC (Agent-ID/Board-UUID des Demo-Agents)."""
    return demo_agent.DEMO_ID in getattr(dev, "agent_ids", []) or \
        getattr(dev, "key", "") == "uuid:" + demo_agent.DEMO_ID.lower()


def root_for(dev, nas_root: str | None) -> str | None:
    """Ablage für Aufträge eines Geräts: Demo-Gerät immer der Demo-Speicher (nie das NAS), sonst das NAS."""
    if dev is not None and is_demo_device(dev):
        return str(ensure())
    return nas_root


def is_demo_path(path: str | Path) -> bool:
    """Liegt der Pfad (Image, Backup) im Demo-Speicher?"""
    return Path(path).resolve().is_relative_to(base().resolve())


def allowed(dev, path: str | Path, demo_image: bool = False) -> bool:
    """Demo-Daten nur für das Demo-Gerät, echte Daten nie für das Demo-Gerät (Images, Backups)."""
    return is_demo_device(dev) == (demo_image or is_demo_path(path))


def allowed_images(images: list[nas.ImageInfo], dev) -> list[nas.ImageInfo]:
    return [i for i in images if allowed(dev, i.path, i.demo)]


def nas_demo_images(images: list[nas.ImageInfo]) -> list[nas.ImageInfo]:
    """Frühere Demo-Images auf dem NAS (vor Ä-027 entstanden) – werden ausgeblendet und zum Löschen angeboten."""
    return [i for i in images if i.demo]
