"""BIOS-Einstellungen im Agent lesen und setzen (I-032) – Linux-Schnittstelle „firmware-attributes“.

    /sys/class/firmware-attributes/<Treiber>/attributes/<Name>/{type,current_value,display_name,possible_values,…}
    /sys/class/firmware-attributes/<Treiber>/authentication/<Rolle>/{is_enabled,current_password}
Treiber im Debian-Kernel: hp-bioscfg (HP Business), dell-wmi-sysman (Dell Business), think-lmi (Lenovo Think…).
Ältere oder Consumer-Modelle haben keinen Treiber – dann gibt es nur die Grundangaben (DMI, UEFI, Secure Boot,
TPM) und die UEFI-Startreihenfolge.
Passwörter kommen nur für eine Änderung vom Tool, werden nach dem Schreiben gelöscht und nie gespeichert.
Nur stdlib, läuft auf dem Stick.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

MODULES = ("hp_bioscfg", "dell_wmi_sysman", "think_lmi")
MAX_VALUE = 500
MAX_ATTRS = 1000
VENDOR = {"hp-bioscfg": "HP", "dell-wmi-sysman": "Dell", "thinklmi": "Lenovo", "think-lmi": "Lenovo"}


class BiosError(Exception):
    pass


def text(raw: bytes) -> str:
    """BIOS-Texte: UTF-8, sonst Windows-1252 (HP meldet manche Namen so, z. B. Byte 0xCE)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def name_of(p: Path) -> str:
    """Verzeichnisname lesbar machen (Python liefert fremde Bytes sonst als Platzhalter → JSON scheitert, B-005)."""
    return text(os.fsencode(p.name))


def _codec(attr: Path) -> str:
    """Kodierung, in der das BIOS die Werte dieser Einstellung liefert (zum Zurückschreiben)."""
    for f in ("possible_values", "current_value"):
        try:
            (attr / f).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            return "cp1252"
        except OSError:
            continue
    return "utf-8"


def _read(path: Path) -> str:
    try:
        return text(path.read_bytes()).strip()[:MAX_VALUE]
    except OSError:
        return ""


def load_drivers(sys_root: Path = Path("/sys")) -> None:
    """Treiber des Herstellers laden, falls der Kernel ihn nicht von selbst geladen hat. Nur der passende –
    andere schreiben sonst „Unable to run on non-Dell system“ auf den Bildschirm."""
    vendor = _read(sys_root / "class" / "dmi" / "id" / "sys_vendor").lower()
    mods = [m for key, m in (("hewlett", "hp_bioscfg"), ("hp", "hp_bioscfg"), ("dell", "dell_wmi_sysman"),
                             ("lenovo", "think_lmi")) if key in vendor]
    for mod in dict.fromkeys(mods):
        subprocess.run(["modprobe", "-q", mod], capture_output=True)


def _attribute(d: Path) -> dict:
    a = {"name": name_of(d), "type": _read(d / "type"), "value": _read(d / "current_value"),
         "display": _read(d / "display_name") or name_of(d)}
    for key, fname in (("default", "default_value"), ("possible", "possible_values"), ("min", "min_value"),
                       ("max", "max_value"), ("step", "scalar_increment"), ("min_length", "min_length"),
                       ("max_length", "max_length")):
        v = _read(d / fname)
        if v:
            a[key] = v
    if a.get("possible"):
        a["possible"] = [p for p in a["possible"].split(";") if p]
    return a


def read(sys_root: Path = Path("/sys"), drivers: bool = True) -> dict:
    """Alles, was sich über das BIOS lesen lässt."""
    if drivers:
        load_drivers(sys_root)
    from okula_recovery import inventory, wininstall   # erst hier: Tests ohne Agent-Umgebung
    dmi = sys_root / "class" / "dmi" / "id"
    out = {"read": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "bios": {k: _read(dmi / f"bios_{k}") for k in ("vendor", "version", "date", "release")},
           "platform": inventory.platform(sys_root), "interfaces": [], "attributes": [], "auth": {},
           "pending_reboot": False}
    base = sys_root / "class" / "firmware-attributes"
    for drv in sorted(base.iterdir()) if base.is_dir() else []:
        attrs = drv / "attributes"
        if not attrs.is_dir():
            continue
        out["interfaces"].append(name_of(drv))
        for d in sorted(attrs.iterdir()):
            if d.is_dir() and len(out["attributes"]) < MAX_ATTRS:
                a = _attribute(d)
                a["driver"] = name_of(drv)
                out["attributes"].append(a)
        if _read(attrs / "pending_reboot") == "1":
            out["pending_reboot"] = True
        auth = drv / "authentication"
        for role in sorted(auth.iterdir()) if auth.is_dir() else []:
            out["auth"][name_of(role)] = _read(role / "is_enabled") == "1"
    if out["platform"].get("uefi") and sys_root == Path("/sys"):
        try:
            out["boot"] = wininstall.boot_status()
        except Exception as e:   # efibootmgr fehlt/scheitert: Rest trotzdem liefern
            out["boot"] = {"uefi": True, "message": str(e)}
    return out


def write(name: str, value: str, password: str = "", sys_root: Path = Path("/sys")) -> dict:
    """Eine Einstellung setzen. Gilt meist erst nach dem nächsten Neustart (pending_reboot)."""
    base = sys_root / "class" / "firmware-attributes"
    target = attr = None
    if "/" not in name and not name.startswith("."):
        for drv in sorted(base.iterdir()) if base.is_dir() else []:
            attrs = drv / "attributes"
            # Name wie beim Lesen dekodiert (auch Namen in Windows-1252) – nur bestehende Einträge
            attr = next((d for d in sorted(attrs.iterdir()) if name_of(d) == name
                         and (d / "current_value").exists()), None) if attrs.is_dir() else None
            if attr is not None:
                target = drv
                break
    if target is None or attr is None:
        raise BiosError(f"Einstellung „{name}“ gibt es auf diesem Gerät nicht")
    possible = [p for p in _read(attr / "possible_values").split(";") if p]
    if possible and value not in possible:
        raise BiosError(f"„{value}“ ist für „{name}“ nicht erlaubt ({', '.join(possible)})")
    roles = [r for r in sorted((target / "authentication").iterdir()) if (r / "current_password").exists()] \
        if (target / "authentication").is_dir() else []
    enabled = [r for r in roles if _read(r / "is_enabled") == "1"]
    if enabled and not password:
        raise BiosError("Im BIOS ist ein Passwort gesetzt – BIOS-Admin-Passwort eingeben")
    try:
        for r in enabled:
            (r / "current_password").write_text(password)
        try:
            (attr / "current_value").write_bytes(value.encode(_codec(attr)))
        except OSError as e:
            raise BiosError(f"BIOS hat „{name}“ = „{value}“ abgelehnt ({e.strerror or e})"
                            + (" – Passwort falsch?" if enabled else "")) from None
    finally:
        for r in enabled:          # Passwort nicht im Kernel stehen lassen
            try:
                (r / "current_password").write_text("")
            except OSError:
                pass
    now = _read(attr / "current_value")
    return {"name": name, "value": now or value,
            "pending_reboot": _read(target / "attributes" / "pending_reboot") == "1"}
