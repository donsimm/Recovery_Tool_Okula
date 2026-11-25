"""BitLocker-Wiederherstellungsschlüssel pro Gerät (I-012) – nur root-lesbar.

- Ablage: KEY_DIR (/etc/okula-recovery/bitlocker, Ordner 0700) mit einer Datei <Geräte-ID>.json (0600) je Gerät:
  {"keys": {"/dev/nvme0n1p3": "111111-222222-…"}}. Geschrieben wird atomar (temporäre Datei 0600, fsync,
  os.replace). Gelesen wird nur, wenn Ordner und Datei root gehören und für niemanden sonst lesbar sind.
- Das Tool läuft als Benutzer und fragt den Root-Helfer /usr/local/sbin/okula-bitlocker (dieses Modul als root)
  per sudo – wie bei den Garantie-Schlüsseln. Der Schlüssel geht nur über stdin hinein.
- Nie in Geräte-JSON, Inventar, Inventar-Export, Einstellungs-Export/-Übertragung, Logs oder Verlauf. Gebraucht
  wird er nur für die Anfrage an den Agent (der die Partition damit nur lesend öffnet, `dislocker -r`).

Format: 48 Ziffern in 8 Blöcken à 6 (Bindestriche/Leerzeichen optional). Blockprüfung: jeder Block ist durch 11
teilbar und kleiner als 11 · 65536 = 720896 (der Block ist 11 × ein 16-Bit-Wert; die letzte Ziffer ist damit eine
Prüfziffer). Quelle: dislocker, src/accesses/rp/recovery_password.c (`valid_block`) – am realen System prüfen,
siehe docs/TESTS.md „I-012“.
Ausgabe des Root-Helfers: eine Zeile „OK <Text/JSON>“ oder „ERROR <Text>“.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable

KEY_DIR = Path("/etc/okula-recovery/bitlocker")
HELPER = "/usr/local/sbin/okula-bitlocker"
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
PART_RE = re.compile(r"^/dev/[A-Za-z0-9][A-Za-z0-9._/-]{0,79}$")
BLOCK_LIMIT = 11 * 65536

Helper = Callable[..., tuple[bool, str]]


class BitLockerKeyError(Exception):
    pass


# ---------- Format ----------

def normalize(value: str) -> str:
    """„111111222222…“ oder mit Bindestrichen/Leerzeichen → „111111-222222-…“; BitLockerKeyError, wenn ungültig."""
    digits = re.sub(r"[\s-]", "", str(value or ""))
    if not re.fullmatch(r"\d{48}", digits):
        raise BitLockerKeyError("Wiederherstellungsschlüssel ungültig – 48 Ziffern in 8 Blöcken à 6")
    blocks = [digits[i:i + 6] for i in range(0, 48, 6)]
    for n, block in enumerate(blocks, 1):
        v = int(block)
        if v % 11 or v >= BLOCK_LIMIT:
            raise BitLockerKeyError(f"Wiederherstellungsschlüssel ungültig – Block {n} ({block}) ist kein gültiger "
                                    "Block (Tippfehler?)")
    return "-".join(blocks)


def valid(value: str) -> bool:
    try:
        normalize(value)
    except BitLockerKeyError:
        return False
    return True


def _device(dev_id: str) -> str:
    if not DEVICE_RE.match(str(dev_id or "")):
        raise BitLockerKeyError("Geräte-ID ungültig")
    return dev_id


def _part(part: str) -> str:
    if not PART_RE.match(str(part or "")) or ".." in part:
        raise BitLockerKeyError(f"Partition ungültig: {part}")
    return part


# ---------- Ablage (als root) ----------

def _private(path: Path, mode: int) -> None:
    """Gehört dem aktuellen Benutzer (root) und ist für niemanden sonst les-/schreibbar – sonst Fehler."""
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode):
        raise BitLockerKeyError(f"{path} ist ein Link – nicht verwendet")
    if st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise BitLockerKeyError(f"Rechte von {path} falsch (erwartet {mode:o}, nur root) – nicht verwendet")


def _file(dev_id: str, base: Path) -> Path:
    return base / f"{_device(dev_id)}.json"


def read_keys(dev_id: str, base: Path | None = None) -> dict[str, str]:
    base = base or KEY_DIR
    path = _file(dev_id, base)
    if not base.exists() or not path.exists():
        return {}
    _private(base, 0o700)
    _private(path, 0o600)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise BitLockerKeyError(f"{path} unlesbar: {e.__class__.__name__}") from None
    keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(keys, dict):
        return {}
    return {p: k for p, k in keys.items() if isinstance(p, str) and isinstance(k, str) and PART_RE.match(p)
            and valid(k)}


def _write(path: Path, keys: dict[str, str]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"keys": keys}, f)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        dfd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dfd)
    except OSError:
        pass
    finally:
        os.close(dfd)


def write_key(dev_id: str, part: str, key: str, base: Path | None = None) -> str:
    base = base or KEY_DIR
    normal = normalize(key)
    path = _file(dev_id, base)
    _part(part)
    base.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    base.mkdir(mode=0o700, exist_ok=True)
    os.chmod(base, 0o700)
    if path.exists():
        os.chmod(path, 0o600)
    keys = read_keys(dev_id, base)
    keys[part] = normal
    _write(path, keys)
    return f"BitLocker-Schlüssel für {Path(part).name} gespeichert"


def delete_keys(dev_id: str, base: Path | None = None) -> str:
    path = _file(dev_id, base or KEY_DIR)
    if path.exists() or path.is_symlink():
        path.unlink()
        return "BitLocker-Schlüssel entfernt"
    return "kein BitLocker-Schlüssel hinterlegt"


# ---------- Aufruf aus dem Tool (Benutzer) ----------

def available() -> bool:
    """Root-Helfer installiert (bzw. Tool läuft als root)?"""
    return os.geteuid() == 0 or Path(HELPER).exists()


def _helper(args: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return [sys.executable, "-m", "okula_recovery.bitlocker_keys", *args]
    if not Path(HELPER).exists():
        raise FileNotFoundError(f"{HELPER} fehlt – install.sh erneut ausführen")
    return ["sudo", "-n", HELPER, *args]


def call_helper(args: list[str], stdin: str | None = None) -> tuple[bool, str]:
    try:
        r = subprocess.run(_helper(args), input=stdin, capture_output=True, text=True, timeout=30, cwd=PROJECT_DIR)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("OK ", "ERROR "))]
    if lines:
        kind, _, msg = lines[-1].partition(" ")
        return kind == "OK" and r.returncode == 0, msg
    return False, (r.stderr or "").strip()[:200] or f"Hilfsprogramm: Exit-Code {r.returncode}"


def stored(dev_id: str, run: Helper = call_helper) -> dict[str, str]:
    """Gespeicherte Schlüssel eines Geräts {partition: schlüssel}; BitLockerKeyError, wenn nicht lesbar."""
    ok, msg = run(["get", "--device", _device(dev_id)])
    if not ok:
        raise BitLockerKeyError(msg)
    try:
        data = json.loads(msg)
    except ValueError:
        raise BitLockerKeyError("Antwort des Root-Helfers unlesbar") from None
    return {p: k for p, k in data.items() if isinstance(p, str) and isinstance(k, str)} \
        if isinstance(data, dict) else {}


def has(dev_id: str, run: Helper = call_helper) -> bool:
    ok, msg = run(["has", "--device", _device(dev_id)])
    if not ok:
        raise BitLockerKeyError(msg)
    return msg.strip() == "ja"


def save(dev_id: str, part: str, key: str, run: Helper = call_helper) -> str:
    normal = normalize(key)
    ok, msg = run(["set", "--device", _device(dev_id), "--part", _part(part), "--stdin"], stdin=normal + "\n")
    if not ok:
        raise BitLockerKeyError(msg)
    return msg


def delete(dev_id: str, run: Helper = call_helper) -> str:
    ok, msg = run(["delete", "--device", _device(dev_id)])
    if not ok:
        raise BitLockerKeyError(msg)
    return msg


def for_partitions(keys: dict[str, str], parts: list[str]) -> dict[str, str]:
    """Schlüssel für die BitLocker-Partitionen: passend zur Partition; ist nur ein Schlüssel hinterlegt, gilt er
    auch für eine anders benannte Partition (z. B. sda3 statt sdb3 nach anderer Reihenfolge der Disks)."""
    out = {p: keys[p] for p in parts if p in keys}
    if len(keys) == 1:
        only = next(iter(keys.values()))
        out.update({p: only for p in parts if p not in out})
    return out


def inventory_partitions(inv: dict) -> list[str]:
    """BitLocker-Partitionen laut Inventar (Dateisystem bzw. erkanntes System „verschlüsselt (BitLocker)“)."""
    inv = inv or {}
    names = {s.get("partition") for s in inv.get("systems") or [] if "BitLocker" in str(s.get("name") or "")}
    out = []
    for disk in inv.get("disks") or []:
        for p in disk.get("partitions") or []:
            if str(p.get("fstype") or "").lower() == "bitlocker" or p.get("name") in names:
                if p.get("path") and p["path"] not in out:
                    out.append(p["path"])
    return out


# ---------- Root-Helfer ----------

def main(argv: list[str] | None = None, base: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description="BitLocker-Schlüssel (I-012) für das Okula Recovery Tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("has", "get", "delete"):
        sub.add_parser(name).add_argument("--device", required=True)
    s = sub.add_parser("set")
    s.add_argument("--device", required=True)
    s.add_argument("--part", required=True)
    s.add_argument("--stdin", action="store_true", help="Schlüssel in der ersten Zeile von stdin")
    args = ap.parse_args(argv)

    if os.geteuid() != 0 and base is None:
        print("ERROR Muss als root laufen", flush=True)
        return 1
    try:
        if args.cmd == "has":
            msg = "ja" if read_keys(args.device, base) else "nein"
        elif args.cmd == "get":
            msg = json.dumps(read_keys(args.device, base))
        elif args.cmd == "set":
            key = sys.stdin.readline().strip() if args.stdin else ""
            msg = write_key(args.device, args.part, key, base)
        else:
            msg = delete_keys(args.device, base)
    except (BitLockerKeyError, OSError) as e:
        print(f"ERROR {e}", flush=True)
        return 1
    print(f"OK {msg}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
