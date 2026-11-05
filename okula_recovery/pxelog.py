"""Netzwerkstart sichtbar machen (Ä-034): was die PXE-Dienste je Gerät gesehen haben.

Quelle: Journal von okula-pxe.service (dnsmasq mit log-dhcp: Proxy-DHCP und TFTP) und okula-pxe-http.service
(Live-System und Agent-Teil per HTTP). Lesen darf das Journal nur root – der Root-Helfer liefert die Zeilen
(`okula-make-stick pxe log`), hier werden sie in Schritte übersetzt:
    Anfrage (BIOS/UEFI) → Antwort (Bootdatei) bzw. keine Antwort → Bootlader/grub/Kernel/initrd per TFTP →
    Live-System und Agent-Teil per HTTP → Agent startet
TFTP und HTTP kennen nur die IP; die MAC kommt aus Dateinamen mit MAC (okula/mode/<mac>, pxelinux.cfg/01-<mac>),
der HTTP-Meldung (seit Ä-034 mit MAC) oder der ARP-Tabelle.
Kein GTK hier.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HELPER = "/usr/local/sbin/okula-make-stick"
UNITS = ("okula-pxe.service", "okula-pxe-http.service")
SINCE = "-6h"
MAX_LINES = 3000
MAC = r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}"

ARCH = {"00000": "BIOS", "00006": "UEFI 32-Bit", "00007": "UEFI", "00009": "UEFI", "00010": "UEFI ARM",
        "00011": "UEFI ARM 64-Bit"}

# TFTP-Datei → Schritt (Reihenfolge wie beim Start)
FILES = (
    (re.compile(r"(^|/)bootx64\.efi$"), "Bootlader (shim, Secure Boot) geladen"),
    (re.compile(r"(^|/)grubx64\.efi$"), "grub geladen"),
    (re.compile(r"grub\.cfg$"), "Startmenü (grub) geladen"),
    (re.compile(rf"okula/mode/({MAC})$"), "Startart gelesen"),
    (re.compile(r"okula/vmlinuz$"), "Kernel geladen"),
    (re.compile(r"okula/initrd\.img$"), "initrd geladen"),
    (re.compile(r"(^|/)pxelinux\.0$"), "Bootlader (pxelinux, BIOS) geladen"),
    (re.compile(r"(^|/)ldlinux\.c32$"), "pxelinux-Modul geladen"),
    (re.compile(r"pxelinux\.cfg/01-([0-9a-f]{2}(?:-[0-9a-f]{2}){5})$"), "Startart lokal (BIOS): von der Festplatte"),
    (re.compile(r"pxelinux\.cfg/default$"), "Startmenü (BIOS) geladen"),
)
ESSENTIAL = re.compile(r"(bootx64\.efi|grubx64\.efi|okula/vmlinuz|okula/initrd\.img|pxelinux\.0|ldlinux\.c32)$")
HTTP_FILES = {"filesystem.squashfs": "Live-System geladen (HTTP)",
              "okula-agent.layer": "Agent-Teil geladen – Agent startet"}


@dataclass
class Event:
    time: float          # Unix-Zeit
    mac: str             # "" = unbekannt
    ip: str
    text: str
    ok: bool | None      # True grün, False rot, None neutral

    @property
    def clock(self) -> str:
        return datetime.fromtimestamp(self.time).strftime("%d.%m. %H:%M:%S")


# ---------- Root-Helfer: Journal lesen ----------

def journal_lines(since: str = SINCE) -> list[dict]:
    """Journal der PXE-Dienste (nur root): [{t, id, msg}]."""
    cmd = ["journalctl", "--no-pager", "-o", "json", "--since", since, "-n", str(MAX_LINES)]
    for unit in UNITS:
        cmd += ["-u", unit]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    rows = []
    for line in out.splitlines():
        try:
            r = json.loads(line)
            msg = r.get("MESSAGE")
            if isinstance(msg, list):     # Nicht-UTF-8 liefert journalctl als Byte-Liste
                msg = bytes(msg).decode("utf-8", "replace")
            rows.append({"t": int(r.get("__REALTIME_TIMESTAMP", 0)) / 1e6,
                         "id": str(r.get("SYSLOG_IDENTIFIER") or r.get("_SYSTEMD_UNIT") or ""),
                         "msg": str(msg or "")})
        except (ValueError, TypeError):
            continue
    return rows


def unit_states() -> dict[str, str]:
    out = {}
    for unit in UNITS:
        r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
        out[unit] = r.stdout.strip() or "unbekannt"
    return out


def helper_main(emit, modes: dict[str, str] | None = None) -> None:
    """`okula-make-stick pxe log`: Zustand der Dienste, Startarten und Journal als JSON-Zeilen."""
    emit("STATE", json.dumps(unit_states()))
    emit("MODES", json.dumps(modes or {}))
    for row in journal_lines():
        emit("LOG", json.dumps(row, ensure_ascii=False))


# ---------- Tool: Helfer aufrufen ----------

def helper_command() -> list[str]:
    if os.geteuid() == 0:
        return [sys.executable, "-m", "okula_recovery.stick", "pxe", "log"]
    if not Path(HELPER).exists():
        raise FileNotFoundError(f"{HELPER} fehlt – bitte install.sh ausführen")
    return ["sudo", "-n", HELPER, "pxe", "log"]


def fetch() -> tuple[dict[str, str], list[dict], dict[str, str]]:
    """(Zustand der Dienste, Journal-Zeilen, Startarten je MAC) vom Root-Helfer."""
    r = subprocess.run(helper_command(), capture_output=True, text=True, timeout=60)
    states, rows, modes = {}, [], {}
    for line in r.stdout.splitlines():
        kind, _, data = line.partition(" ")
        try:
            if kind == "STATE":
                states = json.loads(data)
            elif kind == "MODES":
                modes = json.loads(data)
            elif kind == "LOG":
                rows.append(json.loads(data))
        except ValueError:
            continue
    if r.returncode != 0 and not rows:
        raise OSError((r.stderr or r.stdout).strip()[-300:] or "Netzwerkstart-Protokoll nicht lesbar")
    return states, rows, modes


def arp_table(path: str = "/proc/net/arp") -> dict[str, str]:
    """IP → MAC (nur vollständige Einträge)."""
    out = {}
    try:
        for line in Path(path).read_text().splitlines()[1:]:
            f = line.split()
            if len(f) >= 4 and f[2] != "0x0":
                out[f[0]] = f[3].lower()
    except OSError:
        pass
    return out


# ---------- Übersetzen ----------

DHCP_RE = re.compile(rf"^(\d+) (?:PXE|DHCP\w*|BOOTP)\((\S+)\) (?:([\d.]+) )?({MAC}) (\S+)", re.I)
XID_RE = re.compile(r"^(\d+) (.+)$")
TFTP_SENT = re.compile(r"^sent (\S+) to (\S+)$")
TFTP_MISSING = re.compile(r"^file (\S+) not found(?: for (\S+))?$")
TFTP_ERROR = re.compile(r"^(?:error (\d+) (.*) received from|failed sending (\S+) to) (\S+)$")
HTTP_RE = re.compile(rf'^(\S+) - - \[[^\]]*\] "(?:GET|HEAD) /(\S*) [^"]*" (\d{{3}})')
HTTP_MAC = re.compile(rf"^({MAC}) \(([\d.]+)\): (.+)$")


def parse(rows: list[dict], arp: dict[str, str] | None = None, ip_hints: dict[str, str] | None = None,
          modes: dict[str, str] | None = None) -> list[Event]:
    """Journal-Zeilen → Ereignisse. arp/ip_hints: IP → MAC (ARP-Tabelle, letzte IP der Geräte);
    modes: aktuelle Startart je MAC (local/always/once) für „Startart gelesen“."""
    ip_mac = dict(ip_hints or {})
    ip_mac.update(arp or {})
    xids: dict[str, dict] = {}
    events: list[Event] = []

    def mac_for(ip: str) -> str:
        return ip_mac.get(ip, "")

    def add(e: Event) -> None:
        """Firmware fragt mehrmals (Wiederholung, Port 67 und 4011): gleiche Meldung je Gerät nur einmal je Minute."""
        if any((o.mac or o.ip) == (e.mac or e.ip) and o.text.split(" (")[0] == e.text.split(" (")[0]
               and e.time - o.time < 60 for o in events[-20:]):
            return
        events.append(e)

    for row in sorted(rows, key=lambda r: r.get("t", 0)):
        t, ident, msg = float(row.get("t", 0)), str(row.get("id", "")), str(row.get("msg", "")).strip()
        if ident.startswith("dnsmasq-dhcp"):
            m = DHCP_RE.match(msg)
            if m:
                xid, ip, mac, what = m.group(1), m.group(3) or "", m.group(4).lower(), m.group(5).lower()
                if ip and ip != "0.0.0.0":
                    ip_mac[ip] = mac               # Anfrage auf Port 4011 nennt die IP schon
                info = xids.setdefault(xid, {})
                info["mac"] = mac
                fw = info.get("arch", "")
                if "ignored" in what:
                    add(Event(t, mac, ip, f"Netzwerkstart-Anfrage{f' ({fw})' if fw else ''} – keine Antwort: Gerät "
                                          "nicht freigeschaltet", False))
                else:
                    add(Event(t, mac, ip, f"Netzwerkstart-Anfrage{f' ({fw})' if fw else ''}", None))
                continue
            m = XID_RE.match(msg)
            if m:
                xid, rest = m.groups()
                info = xids.setdefault(xid, {})
                if rest.startswith("vendor class: PXEClient:Arch:"):
                    code = rest.split("Arch:")[1][:5]
                    info["arch"] = ARCH.get(code, f"Firmware {code}")
                elif rest.startswith("bootfile name:") and info.get("mac"):
                    add(Event(t, info["mac"], "", f"Antwort vom Tool: {rest.split(':', 1)[1].strip()}", True))
            continue
        if ident.startswith("dnsmasq-tftp"):
            m = TFTP_SENT.match(msg)
            if m:
                path, ip = m.groups()
                for rx, text in FILES:
                    fm = rx.search(path)
                    if fm:
                        if fm.groups() and fm.group(fm.lastindex or 1) and re.fullmatch(
                                r"[0-9a-f]{2}([:-][0-9a-f]{2}){5}", fm.group(fm.lastindex or 1)):
                            ip_mac[ip] = fm.group(fm.lastindex or 1).replace("-", ":")
                        if text == "Startart gelesen":
                            text += {"local": ": ohne Auftrag von der Festplatte", "always": ": Agent starten",
                                     "once": ": einmal Agent starten"}.get((modes or {}).get(ip_mac.get(ip, "")), "")
                        add(Event(t, mac_for(ip), ip, text, True))
                        break
                continue
            m = TFTP_MISSING.match(msg)
            if m:
                path, ip = m.group(1), m.group(2) or ""
                fm = re.search(r"pxelinux\.cfg/01-([0-9a-f]{2}(?:-[0-9a-f]{2}){5})$", path)
                if fm and ip:
                    ip_mac[ip] = fm.group(1).replace("-", ":")     # BIOS fragt zuerst nach der eigenen Datei
                if ESSENTIAL.search(path):
                    add(Event(t, mac_for(ip), ip, f"Datei fehlt auf dem Server: {Path(path).name} – Netzwerkstart "
                                                  "neu vorbereiten", False))
                continue
            m = TFTP_ERROR.match(msg)
            if m:
                code, text, failed, ip = m.groups()
                if code in ("0", "8") or "abort" in (text or "").lower():
                    continue        # UEFI bricht die erste Übertragung nach der Grössenabfrage absichtlich ab
                name = Path(failed).name if failed else ""
                what = (f"Übertragung von {name} abgebrochen" + (" – das Gerät hat die Datei verworfen (z. B. Secure "
                        "Boot lehnt sie ab) oder die Verbindung brach ab" if name in ("vmlinuz", "initrd.img") else "")
                        if failed else f"TFTP-Fehler {code}: {text}")
                add(Event(t, mac_for(ip), ip, what, False))
            continue
        # HTTP-Dienst (python3)
        m = HTTP_MAC.match(msg)
        if m:
            mac, ip, text = m.group(1).lower(), m.group(2), m.group(3)
            ip_mac[ip] = mac
            if "abgewiesen" in text:
                add(Event(t, mac, ip, "HTTP abgewiesen – Gerät nicht freigeschaltet", False))
            elif "einmal gestartet" in text:
                events.append(Event(t, mac, ip, "„Agent beim nächsten Start“ erledigt – danach wieder von der "
                                                "Festplatte", None))
            continue
        m = HTTP_RE.match(msg)
        if m:
            ip, name, status = m.group(1), m.group(2).split("?")[0], m.group(3)
            if name in HTTP_FILES:
                if status == "200":
                    events.append(Event(t, mac_for(ip), ip, HTTP_FILES[name], True))
                elif status == "403":
                    if not any(e.ip == ip and "HTTP abgewiesen" in e.text and abs(e.time - t) < 2 for e in events):
                        add(Event(t, mac_for(ip), ip, "HTTP abgewiesen – Gerät nicht freigeschaltet", False))
                else:
                    events.append(Event(t, mac_for(ip), ip, f"{name}: HTTP {status}", False))
            continue
        if "abgewiesen:" in msg:
            ip = msg.split("abgewiesen:")[1].split()[0]
            add(Event(t, mac_for(ip), ip, "HTTP abgewiesen – Gerät nicht freigeschaltet", False))
    # IPs, deren MAC erst später bekannt wurde, nachtragen
    for e in events:
        if not e.mac and e.ip:
            e.mac = ip_mac.get(e.ip, "")
    return events


def for_device(events: list[Event], macs: list[str], ips: list[str] = ()) -> list[Event]:
    want, want_ip = {m.lower() for m in macs}, set(ips)
    return [e for e in events if e.mac in want or (not e.mac and e.ip in want_ip)]


def summary(events: list[Event], states: dict[str, str]) -> tuple[str, bool | None]:
    """Eine Zeile über dem Protokoll: (Text, ok)."""
    down = [u for u, s in states.items() if s != "active"]
    if down:
        return ("Netzwerkstart-Dienst läuft nicht (" + ", ".join(down) + ") – Tools → Netzwerkstart (PXE) … → "
                "Einschalten"), False
    if not events:
        return ("In den letzten 6 Stunden keine Netzwerkstart-Anfrage von diesem Gerät angekommen – im BIOS den "
                "Netzwerkstart (PXE) einschalten, Kabel prüfen, beim Start „Netzwerk“ wählen"), None
    last = events[-1]
    if last.ok is False:
        return f"Letzter Versuch {last.clock}: {last.text}", False
    if "Agent startet" in last.text:
        return f"Letzter Netzwerkstart {last.clock}: Agent gestartet", True
    return f"Letzter Netzwerkstart {last.clock}: {last.text}", None
