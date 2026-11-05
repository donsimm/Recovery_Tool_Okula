"""Netzwerkstart sichtbar machen (Ä-034): echte dnsmasq-Protokolle (UEFI/OVMF mit shim+grub, BIOS/iPXE mit pxelinux,
nicht freigeschaltet) und HTTP-Meldungen in Schritte je Gerät übersetzen."""

import io
import json
import re
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import pxe, pxelog

DATA = Path(__file__).parent / "data" / "pxelog"


def rows(name: str) -> list[dict]:
    """Aufzeichnung aus dem Labor (dnsmasq 2.91, log-facility) in Journal-Zeilen wandeln."""
    out = []
    for line in (DATA / f"{name}.log").read_text().splitlines():
        m = re.match(r"^(\w{3}\s+\d+ \d\d:\d\d:\d\d) (\S+?)\[\d+\]: (.*)$", line)
        if m:
            t = time.mktime(time.strptime("2026 " + m.group(1), "%Y %b %d %H:%M:%S"))
            out.append({"t": t, "id": m.group(2), "msg": m.group(3)})
    return out


def texts(events):
    return [(e.text, e.ok) for e in events]


class ParseRealLogsTest(unittest.TestCase):
    def test_uefi(self):
        ev = pxelog.parse(rows("uefi_always"), modes={"52:54:00:12:34:56": "always"})
        self.assertEqual({e.mac for e in ev}, {"52:54:00:12:34:56"})          # MAC auch für TFTP (per okula/mode)
        self.assertEqual(texts(ev)[:6], [
            ("Netzwerkstart-Anfrage (UEFI)", None), ("Antwort vom Tool: bootx64.efi", True),
            ("Bootlader (shim, Secure Boot) geladen", True), ("grub geladen", True),
            ("Startmenü (grub) geladen", True), ("Startart gelesen: Agent starten", True)])
        # Labor: Kernel absichtlich ungültig → grub bricht ab; erscheint rot, Aborts der Firmware nicht
        self.assertEqual([t for t, _ in texts(ev)[6:]], ["Übertragung von vmlinuz abgebrochen – das Gerät hat die Datei verworfen (z. B. Secure Boot lehnt sie ab) oder die Verbindung brach ab"])
        self.assertFalse(any("revocations" in e.text or "command.lst" in e.text for e in ev))

    def test_bios_local(self):
        ev = pxelog.parse(rows("bios_local"))
        self.assertEqual(texts(ev), [
            ("Netzwerkstart-Anfrage (BIOS)", None), ("Antwort vom Tool: pxelinux.0", True),
            ("Bootlader (pxelinux, BIOS) geladen", True), ("pxelinux-Modul geladen", True),
            ("Startart lokal (BIOS): von der Festplatte", True)])
        self.assertTrue(all(e.mac == "52:54:00:12:34:57" for e in ev))

    def test_not_allowed_once(self):
        ev = pxelog.parse(rows("uefi_none"))                                    # 4 Versuche in 30 s → eine Zeile
        self.assertEqual(texts(ev), [("Netzwerkstart-Anfrage (UEFI) – keine Antwort: Gerät nicht freigeschaltet",
                                      False)])
        text, ok = pxelog.summary(ev, {u: "active" for u in pxelog.UNITS})
        self.assertFalse(ok)
        self.assertIn("nicht freigeschaltet", text)

    def test_for_device_and_summary(self):
        ev = pxelog.parse(rows("uefi_always") + rows("bios_local"))
        mine = pxelog.for_device(ev, ["52:54:00:12:34:57"])
        self.assertTrue(mine and all(e.mac == "52:54:00:12:34:57" for e in mine))
        self.assertIn("keine Netzwerkstart-Anfrage", pxelog.summary([], {u: "active" for u in pxelog.UNITS})[0])
        text, ok = pxelog.summary(mine, {"okula-pxe.service": "inactive", "okula-pxe-http.service": "active"})
        self.assertEqual(ok, False)
        self.assertIn("läuft nicht", text)

    def test_http(self):
        t = 1_800_000_000
        ev = pxelog.parse([
            {"t": t, "id": "python3", "msg": '10.0.0.9 - - [05/Nov/2026 12:00:00] "GET /filesystem.squashfs HTTP/1.1" 200 -'},
            {"t": t + 5, "id": "python3", "msg": '10.0.0.9 - - [05/Nov/2026 12:00:05] "GET /okula-agent.layer HTTP/1.1" 200 -'},
            {"t": t + 6, "id": "python3", "msg": "6c:c2:17:7d:33:db (10.0.0.9): Agent einmal gestartet – ab jetzt wieder lokal"},
            {"t": t + 9, "id": "python3", "msg": "aa:bb:cc:00:11:22 (10.0.0.7): abgewiesen – nicht freigeschaltet"},
            {"t": t + 9, "id": "python3", "msg": '10.0.0.7 - - [05/Nov/2026 12:00:09] "GET /filesystem.squashfs HTTP/1.1" 403 -'},
        ])
        self.assertEqual([(e.mac, e.text, e.ok) for e in ev], [
            ("6c:c2:17:7d:33:db", "Live-System geladen (HTTP)", True),
            ("6c:c2:17:7d:33:db", "Agent-Teil geladen – Agent startet", True),
            ("6c:c2:17:7d:33:db", "„Agent beim nächsten Start“ erledigt – danach wieder von der Festplatte", None),
            ("aa:bb:cc:00:11:22", "HTTP abgewiesen – Gerät nicht freigeschaltet", False)])
        self.assertEqual(pxelog.summary(ev[:2], {u: "active" for u in pxelog.UNITS})[1], True)


class HelperTest(unittest.TestCase):
    def test_helper_and_fetch(self):
        journal = "\n".join(json.dumps(r) for r in [
            {"__REALTIME_TIMESTAMP": "1800000000000000", "SYSLOG_IDENTIFIER": "dnsmasq-dhcp",
             "MESSAGE": "1 vendor class: PXEClient:Arch:00007:UNDI:003001"},
            {"__REALTIME_TIMESTAMP": "1800000001000000", "SYSLOG_IDENTIFIER": "dnsmasq-dhcp",
             "MESSAGE": [49, 32, 80, 88, 69, 40, 101, 48, 41, 32] + list(b"6c:c2:17:7d:33:db proxy")}])

        def run(cmd, **_k):
            out = journal if cmd[0] == "journalctl" else "active\n"
            return mock.Mock(stdout=out, returncode=0)
        lines = []
        with mock.patch.object(pxelog.subprocess, "run", run):
            pxelog.helper_main(lambda k, t: lines.append(f"{k} {t}"), {"6c:c2:17:7d:33:db": "local"})
        self.assertTrue(lines[0].startswith("STATE ") and lines[1].startswith("MODES "))
        with mock.patch.object(pxelog, "helper_command", lambda: ["x"]), \
                mock.patch.object(pxelog.subprocess, "run", lambda *a, **k: mock.Mock(stdout="\n".join(lines),
                                                                                     stderr="", returncode=0)):
            states, got, modes = pxelog.fetch()
        self.assertEqual(states["okula-pxe.service"], "active")
        self.assertEqual(modes, {"6c:c2:17:7d:33:db": "local"})
        self.assertEqual(texts(pxelog.parse(got)), [("Netzwerkstart-Anfrage (UEFI)", None)])

    def test_http_note_has_mac(self):
        h = pxe.Handler.__new__(pxe.Handler)
        h.client_address = ("10.0.0.9", 1234)
        err = io.StringIO()
        with mock.patch.object(pxe, "mac_of", lambda ip, arp: "6c:c2:17:7d:33:db"), \
                mock.patch.object(pxe.sys, "stderr", err):
            h._note("abgewiesen – nicht freigeschaltet")
        self.assertEqual(err.getvalue(), "6c:c2:17:7d:33:db (10.0.0.9): abgewiesen – nicht freigeschaltet\n")


if __name__ == "__main__":
    unittest.main()
