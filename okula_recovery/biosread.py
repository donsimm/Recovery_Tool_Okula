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

import subprocess
import time
from pathlib import Path

MODULES = ("hp_bioscfg", "dell_wmi_sysman", "think_lmi")
MAX_VALUE = 500
MAX_ATTRS = 1000
VENDOR = {"hp-bioscfg": "HP", "dell-wmi-sysman": "Dell", "thinklmi": "Lenovo", "think-lmi": "Lenovo"}


class BiosError(Exception):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()[:MAX_VALUE]
    except OSError:
        return ""


def load_drivers() -> None:
    """Treiber laden, falls der Kernel sie nicht von selbst geladen hat (passen sie nicht, passiert nichts)."""
    for mod in MODULES:
        subprocess.run(["modprobe", "-q", mod], capture_output=True)


def _attribute(d: Path) -> dict:
    a = {"name": d.name, "type": _read(d / "type"), "value": _read(d / "current_value"),
         "display": _read(d / "display_name") or d.name}
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
        load_drivers()
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
        out["interfaces"].append(drv.name)
        for d in sorted(attrs.iterdir()):
            if d.is_dir() and len(out["attributes"]) < MAX_ATTRS:
                a = _attribute(d)
                a["driver"] = drv.name
                out["attributes"].append(a)
        if _read(attrs / "pending_reboot") == "1":
            out["pending_reboot"] = True
        auth = drv / "authentication"
        for role in sorted(auth.iterdir()) if auth.is_dir() else []:
            out["auth"][role.name] = _read(role / "is_enabled") == "1"
    if out["platform"].get("uefi") and sys_root == Path("/sys"):
        try:
            out["boot"] = wininstall.boot_status()
        except Exception as e:   # efibootmgr fehlt/scheitert: Rest trotzdem liefern
            out["boot"] = {"uefi": True, "message": str(e)}
    return out


def write(name: str, value: str, password: str = "", sys_root: Path = Path("/sys")) -> dict:
    """Eine Einstellung setzen. Gilt meist erst nach dem nächsten Neustart (pending_reboot)."""
    base = sys_root / "class" / "firmware-attributes"
    target = None
    for drv in sorted(base.iterdir()) if base.is_dir() else []:
        if (drv / "attributes" / name / "current_value").exists():
            target = drv
            break
    if target is None or "/" in name or name.startswith("."):
        raise BiosError(f"Einstellung „{name}“ gibt es auf diesem Gerät nicht")
    attr = target / "attributes" / name
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
            (attr / "current_value").write_text(value)
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
