"""Restore-Stick: spielt das Image auf dem Stick nach Rückfrage auf eine Disk dieser Maschine zurück.

Läuft als root auf tty1 (okula-restore.service). Ablauf: Image zeigen → Zieldisk wählen →
Disk-Namen zur Bestätigung eintippen → Image prüfen → zurückspielen → herunterfahren/neu starten.
Nur stdlib, kein Netzwerk nötig.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from okula_recovery import agentclient, imaging
from okula_recovery.agent import ConsoleBar

DATA_LABEL = "OKULADATA"
DATA_MOUNT = imaging.STICK_DATA
CONFIG_FILE = "okula-restore.json"
IMAGE_DIR = "image"

HEADER = """
  ####   #   #  #   #  #       ###
 #    #  #  #   #   #  #      #   #
 #    #  ###    #   #  #      #####
 #    #  #  #   #   #  #      #   #
  ####   #   #   ###   #####  #   #   Restore-Stick
"""


class StickError(Exception):
    pass


def gb(n: int) -> str:
    return f"{n / 1000**3:.1f} GB"


def mount_data(mount: str = DATA_MOUNT) -> Path:
    """Datenpartition des Sticks (Label OKULADATA) nur lesend einhängen."""
    path = Path(mount)
    if os.path.ismount(path):
        return path
    dev = Path(f"/dev/disk/by-label/{DATA_LABEL}")
    for _ in range(50):  # USB-Stick braucht beim Booten teils ein paar Sekunden
        if dev.exists():
            break
        time.sleep(0.2)
    if not dev.exists():
        r = subprocess.run(["blkid", "-L", DATA_LABEL], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            raise StickError(f"Datenpartition „{DATA_LABEL}“ nicht gefunden")
        dev = Path(r.stdout.strip())
    path.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["mount", "-o", "ro", str(dev), str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise StickError(f"Datenpartition nicht lesbar: {r.stderr.strip()}")
    return path


def load(root: Path) -> tuple[dict, dict]:
    try:
        cfg = json.loads((root / CONFIG_FILE).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise StickError(f"{CONFIG_FILE} fehlt oder ist defekt: {e}") from None
    try:
        src = agentclient.image_source(root / IMAGE_DIR, cfg.get("source_disk"))
    except agentclient.AgentError as e:
        raise StickError(str(e)) from None
    return cfg, src


def candidates(src: dict, disks: list[dict]) -> list[tuple[dict, str]]:
    """Alle Disks dieser Maschine mit Grund, falls ungeeignet („“ = passt)."""
    need = int(src["source"].get("size") or 0)
    result = []
    for d in disks:
        if d["size"] < need:
            reason = f"zu klein (braucht {gb(need)})"
        elif any(p["mounted"] for p in d["partitions"]):
            reason = "eingehängt"
        else:
            reason = ""
        result.append((d, reason))
    return result


class Ui:
    """Ein- und Ausgabe am Terminal; in Tests durch Listen ersetzbar."""

    def __init__(self, console: str, read: Callable[[str], str] = input, write: Callable[[str], None] | None = None):
        self.console = console
        self.read = read
        self.write = write or (lambda text: print(text, flush=True))

    def ask(self, prompt: str) -> str:
        return self.read(prompt).strip()


def describe(cfg: dict, src: dict) -> str:
    d = src["source"]
    parts = ", ".join(f"{p['name']} {p.get('fstype') or 'roh'}" for p in d.get("partitions", []))
    return (f"  Image:   {cfg.get('label') or cfg.get('image_name', '?')}\n"
            f"  Format:  {src.get('format', 'okula')}   erstellt: {cfg.get('created', '?')}\n"
            f"  Quelle:  {d.get('model') or 'Disk'} {gb(int(d.get('size') or 0))} {d.get('pttype', '')} – {parts}")


def choose_disk(ui: Ui, src: dict) -> dict | None:
    """Zieldisk wählen und mit dem Disk-Namen bestätigen; None = abbrechen."""
    while True:
        options = candidates(src, imaging.list_disks())
        ui.write("\n  Disks in dieser Maschine:")
        if not options:
            ui.write("    (keine – Disk angeschlossen?)")
        for i, (d, reason) in enumerate(options, 1):
            parts = ", ".join(f"{p['name']} {p['fstype'] or '?'}"
                              + (f" „{p['label']}“" if p.get("label") else "") for p in d["partitions"]) or "leer"
            ui.write(f"    {i}) {d['name']:<8} {d['model'][:28]:<28} {gb(d['size']):>9}   [{parts}]"
                     + (f"  – {reason}" if reason else ""))
        answer = ui.ask("\n  Zieldisk-Nummer wählen (Enter = neu suchen, q = abbrechen): ")
        if answer.lower() == "q":
            return None
        if not answer.isdigit() or not 1 <= int(answer) <= len(options):
            continue
        disk, reason = options[int(answer) - 1]
        if reason:
            ui.write(f"\n  {disk['name']} ist nicht geeignet: {reason}")
            continue
        ui.write(f"\n  ACHTUNG: Alle Daten auf {disk['name']} ({disk['model']}, {gb(disk['size'])}) werden gelöscht!")
        typed = ui.ask(f"  Zur Bestätigung den Disk-Namen eintippen ({disk['name']}), sonst Enter: ")
        if typed == disk["name"]:
            return disk
        ui.write("  Nicht bestätigt – nichts geändert.")


def restore(ui: Ui, src: dict, disk: dict) -> None:
    cancel = threading.Event()
    bar = ConsoleBar(ui.console, "Image auf dem Stick wird geprüft …")
    src["verify"](lambda ev: ev.get("phase") == "verify" and bar(ev.get("fraction", 0), "Prüfung", 0), cancel)
    bar.finish("» Image ist in Ordnung")
    bar = ConsoleBar(ui.console, f"Image wird auf {disk['name']} zurückgespielt – Maschine nicht ausschalten")
    try:
        imaging.restore_local(disk["path"], src, log=lambda m: None, report=bar)
    except BaseException:
        bar.finish("» Zurückspielen abgebrochen – die Disk ist unvollständig")
        raise
    bar.finish(f"» Image auf {disk['name']} zurückgespielt")


def final_menu(ui: Ui, power: Callable[[str], None]) -> None:
    ui.write("\n  Fertig. Stick abziehen, dann:")
    answer = ui.ask("  Enter = herunterfahren, n = neu starten, s = Kommandozeile: ").lower()
    if answer == "s":
        power("shell")
    else:
        power("reboot" if answer == "n" else "poweroff")


def run(ui: Ui, root: Path, power: Callable[[str], None]) -> None:
    ui.write(HEADER)
    try:
        cfg, src = load(root)
    except StickError as e:
        ui.write(f"\n  Fehler: {e}")
        ui.ask("  Enter = herunterfahren: ")
        power("poweroff")
        return
    ui.write(describe(cfg, src))
    while True:
        disk = choose_disk(ui, src)
        if disk is None:
            ui.write("\n  Abgebrochen – nichts geändert.")
            answer = ui.ask("  Enter = herunterfahren, s = Kommandozeile: ").lower()
            power("shell" if answer == "s" else "poweroff")
            return
        try:
            restore(ui, src, disk)
        except (agentclient.AgentError, imaging.ImagingError, OSError) as e:
            ui.write(f"\n  Fehler: {e}")
            ui.ask("  Enter = zurück zur Disk-Auswahl: ")
            continue
        final_menu(ui, power)
        return


def power_action(action: str) -> None:
    if action == "shell":
        os.execv("/bin/bash", ["bash", "--login"])
    subprocess.run(["systemctl", action])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Okula Restore-Stick")
    ap.add_argument("--console", default="/dev/tty1")
    ap.add_argument("--data", default="", help="Datenordner statt Datenpartition (Tests)")
    args = ap.parse_args(argv)
    ui = Ui(args.console)
    try:
        root = Path(args.data) if args.data else mount_data()
    except StickError as e:
        ui.write(HEADER + f"\n  Fehler: {e}")
        ui.ask("  Enter = herunterfahren: ")
        power_action("poweroff")
        return 1
    run(ui, root, power_action)
    return 0


if __name__ == "__main__":
    sys.exit(main())
