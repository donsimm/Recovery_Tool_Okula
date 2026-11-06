"""Netzwerkbrücke br0 für die virtuellen Maschinen (I-001) – nur mit NetworkManager.

Die Kabel-Schnittstelle der Standardroute (z. B. eno2) wird Port der Brücke br0; br0 übernimmt deren MAC und
IP-Einstellungen, damit der DHCP-Server dieselbe Adresse vergibt. VMs hängen danach mit eigener MAC im LAN.
Bekommt br0 nicht innert 45 s eine IPv4-Adresse, wird die alte Verbindung wiederhergestellt.

Aufruf (nur als root, aus install.sh):
    okula-bridge setup | status | remove
Exit-Code: 0 = in Ordnung bzw. nichts zu tun, 1 = Fehler, 2 = Rückfall (alte Verbindung wieder aktiv).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

BRIDGE = "br0"
CON_BRIDGE = "okula-br0"
CON_PORT = "okula-br0-port"
STATE_FILE = Path("/etc/okula-recovery/bridge.json")
WAIT_SECONDS = 45
# IP-Einstellungen, die von der bisherigen Verbindung auf br0 übernommen werden
IP_FIELDS = ("ipv4.method", "ipv4.addresses", "ipv4.gateway", "ipv4.dns", "ipv4.dns-search",
             "ipv4.ignore-auto-dns", "ipv6.method", "ipv6.addresses", "ipv6.gateway", "ipv6.dns",
             "ipv6.dns-search", "ipv6.ignore-auto-dns")

Run = Callable[[list[str]], subprocess.CompletedProcess]


class BridgeError(Exception):
    pass


def _default_run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]} nicht gefunden")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"{cmd[0]}: Zeitüberschreitung")


def _unescape(value: str) -> str:
    """nmcli -g maskiert „:“ und „\\“ mit Backslash."""
    out, i = [], 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            out.append(value[i + 1])
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


class Bridge:
    def __init__(self, run: Run = _default_run, emit: Callable[[str], None] = print,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 state_file: Path = STATE_FILE, wait: float = WAIT_SECONDS):
        self.run, self.emit, self.sleep, self.clock = run, emit, sleep, clock
        self.state_file, self.wait = state_file, wait

    # ---------- Abfragen ----------

    def _ok(self, cmd: list[str]) -> str:
        r = self.run(cmd)
        if r.returncode != 0:
            raise BridgeError(f"{' '.join(cmd[:3])}: {(r.stderr or r.stdout).strip() or 'Fehler'}")
        return r.stdout

    def nm_running(self) -> bool:
        r = self.run(["nmcli", "-t", "-f", "RUNNING", "general"])
        return r.returncode == 0 and r.stdout.strip() == "running"

    def connections(self) -> list[str]:
        out = self.run(["nmcli", "-t", "-f", "NAME", "connection", "show"]).stdout
        return [_unescape(line) for line in out.splitlines() if line]

    def ipv4_of(self, dev: str) -> str:
        """Erste IPv4-Adresse der Schnittstelle („“ = keine)."""
        out = self.run(["ip", "-o", "-4", "addr", "show", "dev", dev]).stdout
        for line in out.splitlines():
            parts = line.split()
            if "inet" in parts:
                return parts[parts.index("inet") + 1]
        return ""

    def default_interface(self) -> str:
        out = self.run(["ip", "-4", "route", "show", "default"]).stdout
        for line in out.splitlines():
            parts = line.split()
            if "dev" in parts:
                return parts[parts.index("dev") + 1]
        return ""

    def device_field(self, dev: str, field: str) -> str:
        return _unescape(self.run(["nmcli", "-g", field, "device", "show", dev]).stdout.strip())

    def con_field(self, con: str, field: str) -> str:
        return _unescape(self.run(["nmcli", "-g", field, "connection", "show", con]).stdout.strip())

    def mac_of(self, dev: str) -> str:
        mac = self.device_field(dev, "GENERAL.HWADDR").lower()
        if len(mac) != 17:
            raise BridgeError(f"MAC-Adresse von {dev} nicht lesbar")
        return mac

    def _save_state(self, data: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(data, indent=1) + "\n")

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    # ---------- Befehle ----------

    def status(self) -> int:
        if not self.nm_running():
            self.emit("NetworkManager läuft nicht – Netzwerkbrücke wird nicht verwaltet.")
            return 0
        ip = self.ipv4_of(BRIDGE)
        if CON_BRIDGE not in self.connections():
            self.emit("Keine Netzwerkbrücke eingerichtet.")
        elif ip:
            port = self._load_state().get("interface", "?")
            self.emit(f"Netzwerkbrücke {BRIDGE} aktiv: {ip} (Port {port}).")
        else:
            self.emit(f"Netzwerkbrücke {BRIDGE} eingerichtet, aber ohne IPv4-Adresse.")
        return 0

    def setup(self) -> int:
        if not self.nm_running():
            self.emit("Hinweis: NetworkManager läuft nicht – Netzwerkbrücke nicht eingerichtet, nichts geändert. "
                      "Virtuelle Maschinen haben so kein Netzwerk im LAN.")
            return 0
        cons = self.connections()
        if CON_BRIDGE in cons and self.ipv4_of(BRIDGE):
            self.emit(f"Netzwerkbrücke {BRIDGE} läuft bereits ({self.ipv4_of(BRIDGE)}) – nichts zu tun.")
            return 0
        if CON_BRIDGE in cons or CON_PORT in cons:
            self.emit("Unvollständige Netzwerkbrücke wird entfernt und neu eingerichtet …")
            self._restore(self._load_state(), quiet=True)

        dev = self.default_interface()
        if not dev:
            raise BridgeError("Keine Standardroute gefunden – Netzwerkbrücke nicht eingerichtet")
        if dev == BRIDGE:
            self.emit(f"Standardroute läuft bereits über {BRIDGE} – nichts zu tun.")
            return 0
        dtype = self.device_field(dev, "GENERAL.TYPE")
        if dtype != "ethernet":
            raise BridgeError(f"Standardroute über {dev} ({dtype or 'unbekannt'}) – Brücke nur auf einer "
                              "Kabel-Schnittstelle möglich, nichts geändert")
        old = self.device_field(dev, "GENERAL.CONNECTION")
        if not old or old == "--":
            raise BridgeError(f"{dev} hat keine aktive NetworkManager-Verbindung – nichts geändert")
        mac = self.mac_of(dev)
        ip_settings = []
        for field in IP_FIELDS:
            value = self.con_field(old, field)
            if value and value != "--":
                ip_settings += [field, value]
        old_ip = self.ipv4_of(dev)
        self._save_state({"interface": dev, "connection": old, "mac": mac, "ipv4": old_ip})
        self.emit(f"Brücke {BRIDGE} wird auf {dev} angelegt (MAC {mac}, bisher {old_ip or 'ohne IPv4'}) …")

        try:
            self._ok(["nmcli", "connection", "add", "type", "bridge", "con-name", CON_BRIDGE, "ifname", BRIDGE,
                      "bridge.stp", "no", "bridge.forward-delay", "0", "bridge.mac-address", mac,
                      "connection.autoconnect", "yes", "connection.autoconnect-priority", "10",
                      "connection.autoconnect-slaves", "yes", *ip_settings])
            self._ok(["nmcli", "connection", "add", "type", "ethernet", "con-name", CON_PORT, "ifname", dev,
                      "master", CON_BRIDGE, "slave-type", "bridge",
                      "connection.autoconnect", "yes", "connection.autoconnect-priority", "10"])
            self._ok(["nmcli", "connection", "modify", old, "connection.autoconnect", "no"])
            self.emit("Netzwerk wird auf die Brücke umgeschaltet (kurz offline) …")
            self.run(["nmcli", "--wait", "30", "connection", "up", CON_PORT])
            self.run(["nmcli", "--wait", "5", "connection", "up", CON_BRIDGE])
        except BridgeError as e:
            self.emit(f"Fehler beim Anlegen der Brücke: {e}")
            return self._fallback()

        deadline = self.clock() + self.wait
        while True:
            ip = self.ipv4_of(BRIDGE)
            if ip:
                same = " (gleiche Adresse)" if old_ip and ip.split("/")[0] == old_ip.split("/")[0] else ""
                self.emit(f"Netzwerkbrücke {BRIDGE} aktiv: {ip}{same}.")
                return 0
            if self.clock() >= deadline:
                break
            self.sleep(1)
        self.emit(f"{BRIDGE} hat nach {int(self.wait)} s keine IPv4-Adresse.")
        return self._fallback()

    def _fallback(self) -> int:
        self._restore(self._load_state(), quiet=True)
        self.emit("!!! Netzwerkbrücke NICHT eingerichtet – alte Verbindung wieder aktiv. "
                  "Virtuelle Maschinen haben vorerst kein Netzwerk im LAN; die übrige Installation läuft weiter.")
        return 2

    def _restore(self, state: dict, quiet: bool = False) -> None:
        cons = self.connections()
        old = state.get("connection", "")
        if old and old in cons:
            self.run(["nmcli", "connection", "modify", old, "connection.autoconnect", "yes"])
        for con in (CON_PORT, CON_BRIDGE):
            if con in cons:
                self.run(["nmcli", "connection", "delete", con])
        if old and old in cons:
            r = self.run(["nmcli", "--wait", "30", "connection", "up", old])
            if r.returncode != 0 and not quiet:
                self.emit(f"Hinweis: „{old}“ liess sich nicht aktivieren: {(r.stderr or '').strip()}")
        try:
            self.state_file.unlink()
        except OSError:
            pass

    def remove(self) -> int:
        if not self.nm_running():
            self.emit("NetworkManager läuft nicht – nichts geändert.")
            return 0
        cons = self.connections()
        if CON_BRIDGE not in cons and CON_PORT not in cons:
            self.emit("Keine Netzwerkbrücke vorhanden – nichts zu tun.")
            return 0
        state = self._load_state()
        if not state.get("connection"):
            raise BridgeError(f"Ursprüngliche Verbindung unbekannt ({self.state_file} fehlt) – "
                              f"Brücke von Hand entfernen: nmcli connection delete {CON_PORT} {CON_BRIDGE}")
        self.emit(f"Netzwerkbrücke {BRIDGE} wird entfernt, „{state['connection']}“ wieder aktiviert …")
        self._restore(state)
        self.emit("Netzwerkbrücke entfernt.")
        return 0


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("setup", "status", "remove"):
        print("Aufruf: okula-bridge setup | status | remove", file=sys.stderr)
        return 1
    if argv[0] != "status" and os.geteuid() != 0:
        print("Muss als root laufen (aus sudo ./install.sh)", file=sys.stderr)
        return 1
    bridge = Bridge(emit=lambda text: print(text, flush=True))
    try:
        return getattr(bridge, argv[0])()
    except BridgeError as e:
        print(f"Fehler: {e}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
