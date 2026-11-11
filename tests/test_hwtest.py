"""Hardware-Test (I-023): Bewertung je Bereich, Selbsttest-Ablauf, Oberfläche, RAM/CPU, Protokoll, Demo-Agent."""

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, devices, discovery, hwreport, hwtest, inventory_export

ROOT = Path(__file__).resolve().parent.parent


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


class AreasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_battery(self):
        bat = self.root / "class/power_supply/BAT0"
        for k, v in {"energy_full": "39000000", "energy_full_design": "50000000", "cycle_count": "412",
                     "capacity": "96", "status": "Charging", "manufacturer": "Hewlett-Packard"}.items():
            write(bat / k, v)
        r = hwtest.battery(self.root)[0]
        self.assertEqual((r["status"], r["values"]["health"]), (hwtest.WARN, 78))
        write(bat / "energy_full", "25000000")
        self.assertEqual(hwtest.battery(self.root)[0]["status"], hwtest.FAIL)
        self.assertEqual(hwtest.battery(self.root / "leer")[0]["status"], hwtest.SKIP)

    def test_temperatures(self):
        write(self.root / "class/hwmon/hwmon0/name", "coretemp")
        write(self.root / "class/hwmon/hwmon0/temp1_input", "86000")
        write(self.root / "class/hwmon/hwmon0/temp1_label", "Package id 0")
        r = hwtest.temperature_step(self.root)
        self.assertEqual(r["status"], hwtest.WARN)
        self.assertIn("86 °C (coretemp Package id 0)", r["summary"])

    def test_smart_values(self):
        ata = {"smart_status": {"passed": True}, "power_on_time": {"hours": 9000},
               "ata_smart_attributes": {"table": [{"id": 5, "raw": {"value": 8}}, {"id": 197, "raw": {"value": 0}}]}}
        self.assertEqual(hwtest.smart_values(ata)[0], hwtest.WARN)                 # umgeschriebene Sektoren
        ata["ata_smart_attributes"]["table"][1]["raw"]["value"] = 3
        self.assertEqual(hwtest.smart_values(ata)[0], hwtest.FAIL)                 # unsichere Sektoren
        nvme = {"smart_status": {"passed": True}, "nvme_smart_health_information_log": {
            "critical_warning": 0, "percentage_used": 4, "available_spare": 100, "available_spare_threshold": 10,
            "media_errors": 0}}
        self.assertEqual(hwtest.smart_values(nvme)[0], hwtest.OK)
        nvme["nvme_smart_health_information_log"]["available_spare"] = 9
        self.assertEqual(hwtest.smart_values(nvme)[0], hwtest.FAIL)
        self.assertEqual(hwtest.smart_values({"smart_status": {"passed": False}})[0], hwtest.FAIL)

    def test_self_test_flow_ata_and_nvme(self):
        disk = {"name": "sda", "path": "/dev/sda", "model": "Samsung SSD"}
        running = {"ata_smart_data": {"self_test": {"status": {"value": 249, "remaining_percent": 40}}}}
        done = {"smart_status": {"passed": True}, "ata_smart_data": {"self_test": {"status": {"value": 0}}},
                "ata_smart_self_test_log": {"standard": {"table": [{"status": {"passed": True, "string": "ok"}}]}}}
        seq = iter([{"smartctl": {"exit_status": 0}}, running, done])
        ev = []
        with mock.patch.object(hwtest, "_smartctl", lambda *a: next(seq)), \
                mock.patch.object(hwtest.shutil, "which", lambda _x: "/usr/sbin/smartctl"):
            r = hwtest.smart_test(disk, "short", ev.append, lambda: False, "smart_short", poll=0)
        self.assertEqual((r["status"], r["summary"]), (hwtest.OK, "Selbsttest bestanden"))
        self.assertAlmostEqual(ev[0]["fraction"], 0.6)
        nv_fail = {"nvme_self_test_log": {"current_self_test_operation": {"value": 0},
                                          "table": [{"self_test_result": {"value": 7, "string": "Failed segment"}}]}}
        seq = iter([{"smartctl": {"exit_status": 0}}, nv_fail])
        with mock.patch.object(hwtest, "_smartctl", lambda *a: next(seq)), \
                mock.patch.object(hwtest.shutil, "which", lambda _x: "/usr/sbin/smartctl"):
            r = hwtest.smart_test(disk, "long", ev.append, lambda: False, "smart_long", poll=0)
        self.assertEqual(r["status"], hwtest.FAIL)
        self.assertIn("FEHLGESCHLAGEN", r["summary"])
        # USB-Disk ohne Selbsttest: nur Werte
        seq = iter([{"smartctl": {"exit_status": 4}}, {"smart_status": {"passed": True}}])
        with mock.patch.object(hwtest, "_smartctl", lambda *a: next(seq)), \
                mock.patch.object(hwtest.shutil, "which", lambda _x: "/usr/sbin/smartctl"):
            r = hwtest.smart_test(disk, "short", ev.append, lambda: False, "smart_short", poll=0)
        self.assertEqual(r["status"], hwtest.SKIP)

    def test_surface_with_read_error(self):
        img = self.root / "disk.img"
        img.write_bytes(os.urandom(3 * 1024 * 1024 + 4096))
        disk = {"name": "loop", "path": str(img), "size": img.stat().st_size}
        self.assertEqual(hwtest.surface(disk, lambda e: None, lambda: False)["status"], hwtest.OK)
        real = os.read
        calls = {"n": 0}

        def flaky(fd, n):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError(5, "Input/output error")
            return real(fd, n)
        with mock.patch.object(hwtest.os, "read", flaky):
            r = hwtest.surface(disk, lambda e: None, lambda: False)
        self.assertEqual(r["status"], hwtest.FAIL)
        self.assertIn("Lesefehler bei 0 MiB", r["details"][0])
        with self.assertRaises(hwtest.Cancelled):
            hwtest.surface(disk, lambda e: None, lambda: True)

    def test_ram_and_cpu_short(self):
        r = hwtest.ram("quick", lambda e: None, lambda: False, size=64 << 20)
        self.assertEqual(r["status"], hwtest.OK)
        write(self.root / "class/hwmon/hwmon0/temp1_input", "70000")
        t = time.monotonic()
        with mock.patch.object(hwtest, "_mce_lines", lambda: []):
            r = hwtest.cpu("quick", lambda e: None, lambda: False, self.root, seconds=2)
            self.assertLess(time.monotonic() - t, 10)
            self.assertEqual(r["status"], hwtest.OK)
            self.assertIn("70 °C", r["summary"])
            self.assertIn("Hardware-Fehler: keine seit dem Start", r["details"])
            r = hwtest.cpu("quick", lambda e: None, lambda: False, self.root / "leer", seconds=1)
            self.assertIn("Temperatur nicht messbar", r["summary"])

    def test_one_area_failing_does_not_stop_the_rest(self):
        with mock.patch.object(hwtest, "battery", side_effect=RuntimeError("kaputt")), \
                mock.patch.object(hwtest, "temperature_step", lambda: hwtest.result("temperature", hwtest.OK, "ok")), \
                mock.patch.object(hwtest, "smart_test", lambda *a: hwtest.result("smart_short", hwtest.OK, "ok")), \
                mock.patch.object(hwtest, "ram", lambda *a: hwtest.result("ram", hwtest.OK, "ok")), \
                mock.patch.object(hwtest, "cpu", lambda *a: hwtest.result("cpu", hwtest.OK, "ok")), \
                mock.patch.object(hwtest, "network", lambda *a: hwtest.result("network", hwtest.OK, "ok")):
            rep = hwtest.run({"level": "quick"}, [], lambda e: None, lambda: False, None, None)
        self.assertEqual(rep["results"][0]["status"], hwtest.SKIP)
        self.assertIn("kaputt", rep["results"][0]["summary"])
        self.assertEqual(rep["results"][2]["summary"], "keine interne Disk gefunden")
        self.assertEqual(len(rep["results"]), 6)


def kline(t: float, text: str) -> str:
    """Zeile wie aus `journalctl -k -o short-monotonic`."""
    return f"[{t:12.6f}] okula-a1b2c3 kernel: {text}"


def mce_event(t: float, cpu: int = 3, bank: int = 0, status: str = "d400008000040150") -> list[str]:
    """Ein Ereignis wie auf dem Foto von SRV-002 (11.11.2026): drei Zeilen."""
    return [kline(t, "mce: [Hardware Error]: PROCESSOR 0:506e3 TIME 1794387393 SOCKET 0 APIC 6 microcode f0"),
            kline(t, f"mce: [Hardware Error]: CPU {cpu}: Machine Check: 0 Bank {bank}: {status}"),
            kline(t, "mce: [Hardware Error]: TSC 0 ADDR 1ffff993a5650")]


BOOT = [kline(0.1, "mce: CPU0: Thermal monitoring enabled (TM1)"), kline(0.2, "MCE: In-kernel MCE decoding enabled."),
        kline(0.3, "mce: CPU supports 10 MCE banks")]


class MceTest(unittest.TestCase):
    """B-011: Prozessor-Fehler (Machine Check) seit dem Start und während der Last."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write(self.root / "class/hwmon/hwmon0/temp1_input", "70000")

    def tearDown(self):
        self.tmp.cleanup()

    def cpu(self, before, after):
        seq = iter([before, after])
        with mock.patch.object(hwtest, "_mce_lines", lambda: next(seq)):
            return hwtest.cpu("quick", lambda e: None, lambda: False, self.root, seconds=1)

    def test_parser_with_photo_lines(self):
        lines = BOOT + mce_event(10.5) + mce_event(11.5) + mce_event(12.5, bank=4, status="b200000000070005") + [
            kline(13, "mce: [Hardware Error]: Machine check events logged")]
        events = hwtest.mce_events(lines)
        self.assertEqual([(e["cpu"], e["bank"], e["kind"]) for e in events],
                         [(3, 0, "corrected"), (3, 0, "corrected"), (3, 4, "uncorrected"), (None, None, "")])
        groups = hwtest.mce_groups(lines)
        self.assertEqual([(g["cpu"], g["bank"], g["kind"], g["count"]) for g in groups],
                         [(3, 0, "corrected", 2), (3, 4, "uncorrected", 1), (None, None, "", 1)])
        self.assertEqual(groups[0]["examples"],
                         ["mce: [Hardware Error]: CPU 3: Machine Check: 0 Bank 0: d400008000040150"])
        self.assertEqual(hwtest.mce_short(groups), "CPU 3, Bank 0: 2 Mal; CPU 3, Bank 4: 1 Mal; ohne Zuordnung: 1 Mal")
        details = hwtest.mce_details(groups)
        self.assertIn("Hardware-Fehler CPU 3, Bank 0 (korrigiert): 2 Mal seit dem Start", details)
        self.assertIn("Hardware-Fehler CPU 3, Bank 4 (nicht korrigiert): 1 Mal seit dem Start", details)
        self.assertIn("Hardware-Fehler ohne Zuordnung: 1 Mal seit dem Start", details)
        self.assertEqual(hwtest.mce_events(BOOT), [])                        # Startmeldungen sind keine Fehler
        # dmesg-Format und Gross-/Kleinschreibung
        self.assertEqual(len(hwtest.mce_events(["[  3.1] MCE: [HARDWARE ERROR]: CPU 1: MACHINE CHECK: 0 BANK 2: 9c00"])), 1)
        # höchstens 3 Beispielzeilen je Gruppe, lange Zeilen gekürzt
        many = [kline(i, f"mce: [Hardware Error]: CPU 0: Machine Check: 0 Bank 1: 9c00{i:04x}" + "0" * 120)
                for i in range(5)]
        g = hwtest.mce_groups(many)[0]
        self.assertEqual((g["count"], len(g["examples"])), (5, 3))
        self.assertTrue(all(len(x) <= 110 and x.endswith("…") for x in g["examples"]))

    def test_new_lines_counts_repeated_lines(self):
        a, b = ["x", "y"], ["x", "y", "x", "z"]
        self.assertEqual(hwtest.new_lines(a, b), ["x", "z"])
        groups = hwtest.mce_groups(mce_event(1) + mce_event(2), mce_event(2))
        self.assertEqual((groups[0]["count"], groups[0]["during"]), (2, 1))

    def test_rating_before_during_none(self):
        before = BOOT + mce_event(10) + mce_event(11)
        # nur vor dem Test → gelb mit Gruppierung
        r = self.cpu(hwtest.mce_filter(before), hwtest.mce_filter(before))
        self.assertEqual(r["status"], hwtest.WARN)
        self.assertEqual(r["summary"], "Hardware-Fehler seit dem Start gemeldet (CPU 3, Bank 0: 2 Mal) – "
                                       "BIOS-Update bzw. Prozessor prüfen")
        self.assertEqual((r["values"]["mce"], r["values"]["mce_boot"]), (0, 2))
        self.assertEqual(r["values"]["mce_groups"],
                         [{"cpu": 3, "bank": 0, "count": 2, "kind": "corrected", "during": 0}])
        self.assertIn("  Beispiel: mce: [Hardware Error]: CPU 3: Machine Check: 0 Bank 0: d400008000040150",
                      r["details"])
        self.assertEqual(hwreport.overall({"results": [r]}), hwreport.WARN)
        # neue während der Last → rot
        after = before + mce_event(20) + mce_event(21) + mce_event(22)
        r = self.cpu(hwtest.mce_filter(before), hwtest.mce_filter(after))
        self.assertEqual(r["status"], hwtest.FAIL)
        self.assertIn("während der Last gemeldet (CPU 3, Bank 0: 3 Mal)", r["summary"])
        self.assertEqual((r["values"]["mce"], r["values"]["mce_boot"]), (3, 5))
        self.assertIn("Hardware-Fehler CPU 3, Bank 0 (korrigiert): 5 Mal seit dem Start, davon 3 während der Last",
                      r["details"])
        # nicht korrigiert vor dem Test → immer rot
        uc = hwtest.mce_filter(BOOT + mce_event(5, bank=4, status="b200000000070005"))
        r = self.cpu(uc, uc)
        self.assertEqual(r["status"], hwtest.FAIL)
        self.assertIn("Nicht korrigierte Hardware-Fehler seit dem Start", r["summary"])
        # keine → wie bisher
        r = self.cpu(hwtest.mce_filter(BOOT), hwtest.mce_filter(BOOT))
        self.assertEqual((r["status"], r["summary"]), (hwtest.OK, "höchstens 70 °C, stabil"))
        self.assertEqual((r["values"]["mce"], r["values"]["mce_boot"], r["values"]["mce_groups"]), (0, 0, []))

    def test_temperature_still_decides_when_worse(self):
        write(self.root / "class/hwmon/hwmon0/temp1_input", "100000")
        lines = hwtest.mce_filter(mce_event(10))
        r = self.cpu(lines, lines)
        self.assertEqual(r["status"], hwtest.FAIL)                         # Temperatur rot, Fehler nur gelb
        self.assertIn("Hardware-Fehler seit dem Start", r["summary"])

    def test_not_checkable(self):
        r = self.cpu(None, None)
        self.assertEqual(r["status"], hwtest.OK)
        self.assertIn("Hardware-Fehler nicht prüfbar (Kernel-Protokoll nicht lesbar)", r["details"])
        self.assertEqual(r["values"]["mce_boot"], 0)
        # vorher lesbar, nachher nicht → Stand von vorher
        lines = hwtest.mce_filter(mce_event(10))
        r = self.cpu(lines, None)
        self.assertEqual((r["status"], r["values"]["mce_boot"]), (hwtest.WARN, 1))

    def test_kernel_log_sources(self):
        dmesg_out = "\n".join(f"[ 10.5] {l.split('kernel: ')[1]}" for l in BOOT + mce_event(10)) + "\n"

        def fake(responses):
            def run(cmd, **_kw):
                cmd_out = responses[cmd[0]]
                if isinstance(cmd_out, Exception):
                    raise cmd_out
                return subprocess.CompletedProcess(cmd, cmd_out[0], cmd_out[1], "")
            return run
        cases = [
            ({"journalctl": FileNotFoundError("journalctl"), "dmesg": (0, dmesg_out)}, "dmesg"),      # fehlt
            ({"journalctl": (1, ""), "dmesg": (0, dmesg_out)}, "dmesg"),                              # Fehler
            ({"journalctl": (0, "-- No entries --\n"), "dmesg": (0, dmesg_out)}, "dmesg"),           # leer
            ({"journalctl": subprocess.TimeoutExpired("journalctl", 60), "dmesg": (0, dmesg_out)}, "dmesg"),
            ({"journalctl": (0, "\n".join(BOOT + mce_event(10))), "dmesg": (0, "")}, "journal"),
        ]
        for responses, source in cases:
            with self.subTest(responses=list(responses.values())[0]), \
                    mock.patch.object(hwtest.subprocess, "run", fake(responses)):
                lines = hwtest._mce_lines()
                self.assertEqual(len(hwtest.mce_events(lines)), 1)
                self.assertEqual(lines[0].startswith("[ 10.5]"), source == "dmesg")
        both_missing = {"journalctl": FileNotFoundError("journalctl"), "dmesg": (1, "")}
        with mock.patch.object(hwtest.subprocess, "run", fake(both_missing)):
            self.assertIsNone(hwtest._mce_lines())
        # journalctl ohne -g (braucht PCRE2) und mit Zeitstempel
        self.assertNotIn("-g", hwtest.KERNEL_LOG_SOURCES[0])


class ReportTest(unittest.TestCase):
    report = {"level": "quick", "started": "2026-11-05T15:00:00", "finished": "2026-11-05T15:05:00",
              "results": [{"id": "battery", "title": "Akku – BAT0", "status": "warn", "summary": "78 %", "details": []},
                          {"id": "ram", "title": "Arbeitsspeicher", "status": "ok", "summary": "keine Fehler",
                           "details": ["Teilprüfung"]},
                          {"id": "cpu", "title": "CPU unter Last", "status": "skip", "summary": "x", "details": []}]}

    def test_texts_and_store(self):
        self.assertEqual(hwreport.headline(self.report), "Schnelltest 05.11.2026 15:05: 1 ✔, 1 ⚠, 0 ✖, 1 nicht geprüft")
        self.assertEqual(hwreport.overall(self.report), hwreport.WARN)
        dev = devices.Device(id="d", name="EliteBook")
        for i in range(12):
            hwreport.store(dev, dict(self.report, started=f"2026-11-{i + 1:02d}T10:00:00"))
        self.assertEqual(len(dev.hwtests), hwreport.MAX_KEEP)
        self.assertEqual(dev.hwtests[0]["started"], "2026-11-12T10:00:00")

    @unittest.skipUnless(inventory_export.pdf_available(), "python3-reportlab fehlt")
    def test_pdf(self):
        dev = devices.Device(id="d", name="DoNs_EliteBook_1", inventory={
            "dmi": {"sys_vendor": "Hewlett-Packard", "product_name": "HP EliteBook 850 G1", "product_serial": "CNU4279G9B"},
            "memory": 8 * 2**30, "disks": [{"name": "sda", "model": "Samsung SSD", "size": 256e9}]})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "p.pdf"
            hwreport.write_pdf(out, dev, self.report)
            text = subprocess.run(["pdftotext", str(out), "-"], capture_output=True, text=True).stdout \
                if subprocess.run(["which", "pdftotext"], capture_output=True).returncode == 0 else ""
            self.assertGreater(out.stat().st_size, 1000)
            if text:
                self.assertIn("Hardware-Prüfprotokoll", text)
                self.assertIn("CNU4279G9B", text)
                self.assertIn("In Ordnung, aber mit Hinweisen", text)


class DemoAgentHwTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.key = bytes(range(32))
        (d / "agent.key").write_text(self.key.hex() + "\n")
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.udp.settimeout(10)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "okula_recovery.demo_agent", "--key-file", str(d / "agent.key"),
             "--port", str(self.udp.getsockname()[1]), "--control-port", str(self.port), "--duration", "5"],
            env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.udp.recvfrom(discovery.MAX_PACKET + 1)

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(5)
        self.udp.close()
        self.tmp.cleanup()

    def test_quick_and_cancel(self):
        events = []
        rep = agentclient.hwtest("127.0.0.1", self.key, "quick", ["/dev/demo-nvme0n1"], events.append,
                                 threading.Event(), self.port)
        ids = [r["id"] for r in rep["results"]]
        self.assertEqual(ids, ["battery", "temperature", "smart_short", "ram", "cpu", "network"])
        net = rep["results"][-1]
        self.assertEqual(net["status"], hwtest.OK)
        self.assertGreater(net["values"]["mbit"], 10)                          # echt über 127.0.0.1 gemessen
        self.assertEqual(hwreport.overall(rep), hwreport.WARN)                  # Demo-Akku 78 %
        self.assertTrue(any(e.get("event") == "progress" for e in events))
        # Abbrechen während des Selbsttests
        cancel = threading.Event()

        def stop(ev):
            if ev.get("event") == "step_start" and ev.get("id") == "smart_short":
                cancel.set()
        with self.assertRaisesRegex(agentclient.AgentError, "abgebrochen"):
            agentclient.hwtest("127.0.0.1", self.key, "quick", ["/dev/demo-nvme0n1"], stop, cancel, self.port)
        # danach ist die Disk wieder frei
        rep = agentclient.hwtest("127.0.0.1", self.key, "quick", [], lambda e: None, threading.Event(), self.port)
        self.assertEqual(rep["results"][2]["summary"], "keine interne Disk gefunden")


if __name__ == "__main__":
    unittest.main()
