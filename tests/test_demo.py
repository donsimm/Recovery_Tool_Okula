"""Demo-Gerät: echter Prozess, echtes Protokoll – aber nur Attrappen, nur 127.0.0.1."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from okula_recovery import agentclient, backups, demo_agent, discovery, distribute, wire

ROOT = Path(__file__).resolve().parent.parent


def free_port(kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DemoAgentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        cls.key = bytes(range(32))
        (cls.d / "agent.key").write_text(cls.key.hex() + "\n")
        cls.flag = cls.d / "demo-fehler"
        cls.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cls.udp.bind(("127.0.0.1", 0))
        cls.udp.settimeout(10)
        cls.port = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "okula_recovery.demo_agent", "--key-file", str(cls.d / "agent.key"),
             "--port", str(cls.udp.getsockname()[1]), "--control-port", str(cls.port),
             "--fail-flag", str(cls.flag), "--duration", "6"],
            env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        data, sender = cls.udp.recvfrom(discovery.MAX_PACKET + 1)
        cls.info = discovery.parse_beacon(data, sender[0])

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        cls.udp.close()
        cls.tmp.cleanup()

    def test_beacon_and_info(self):
        self.assertEqual((self.info.agent_id, self.info.ip, self.info.control_port),
                         (demo_agent.DEMO_ID, "127.0.0.1", self.port))
        info = agentclient.get_info("127.0.0.1", self.key, self.port)
        self.assertEqual([d["path"] for d in info["disks"]], [demo_agent.DEMO_DISK_PATH])
        inv = agentclient.get_inventory("127.0.0.1", self.key, self.port)
        self.assertEqual(inv["systems"][0]["hostname"], "DEMO-PC")
        # nur auf 127.0.0.1 erreichbar
        with socket.socket() as s:
            s.settimeout(1)
            for addr in {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - \
                    {"127.0.0.1", "127.0.1.1"}:
                self.assertNotEqual(s.connect_ex((addr, self.port)), 0)

    def test_image_restore_backup_deliver_customize(self):
        nas = self.d / "nas"
        events = []
        t0 = time.monotonic()
        image = agentclient.create_image("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, nas, "DEMO-PC",
                                         events.append, threading.Event(), port=self.port)
        took = time.monotonic() - t0
        self.assertGreater(took, 4)             # läuft sichtbar (hier 6 s, im Tool 45 s), nicht in einer Sekunde
        meta = json.loads((image / agentclient.IMAGE_META).read_text())
        self.assertTrue(meta["demo"])
        self.assertLess(meta["bytes"], 15_000_000)
        self.assertTrue(any(e.get("phase") == "data" for e in events))
        # zurück auf das Demo-Gerät: geht; auf ein echtes Gerät: verweigert
        agentclient.restore_image("127.0.0.1", self.key, image, demo_agent.DEMO_DISK_PATH, lambda e: None,
                                  threading.Event(), self.port)
        with self.assertRaisesRegex(agentclient.AgentError, "Demo-Image"):
            agentclient.restore_image("192.168.110.50", self.key, image, "/dev/sda", lambda e: None,
                                      threading.Event(), self.port)
        # Backup
        parts = backups.get_profiles("127.0.0.1", self.key, self.port)
        sources = backups.profile_sources(parts[0]["part"], "Users/Anna", "windows", list(backups.DEFAULT_CATEGORIES))
        path = backups.run_backup("127.0.0.1", self.key, self.port, demo_agent.DEMO_DISK_PATH, sources, nas,
                                  {"id": "x", "name": "DEMO-PC"}, "profiles", "files", ["Demo"], lambda e: None,
                                  threading.Event())
        self.assertEqual(json.loads((path / backups.MANIFEST).read_text())["files"], 7)
        # Ordner senden, Anpassen, Startreihenfolge
        base = distribute.ensure(nas)
        (base / "Software/setup.exe").write_bytes(b"MZ" * 1000)
        plan = distribute.plan(nas, ["Software"])
        result = agentclient.deliver("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, plan.items, plan.entries,
                                     plan.bytes, lambda e: None, threading.Event(), self.port)
        self.assertEqual(result["files"], 1)
        res = agentclient.customize("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, "<x/>", "demo-pc", self.port)
        self.assertEqual(res[0]["action"], "unattend")
        st = agentclient.bootorder("127.0.0.1", self.key, "netfirst", port=self.port)
        self.assertTrue(st["netfirst"])
        st = agentclient.bootorder("127.0.0.1", self.key, "normal", st["previous"], self.port)
        self.assertFalse(st["netfirst"])

    def test_zz_fail_flag_and_reboot(self):
        self.flag.touch()
        with self.assertRaisesRegex(agentclient.AgentError, "Demo: simulierter Fehler"):
            agentclient.create_image("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, self.d / "nas2", "DEMO-PC",
                                     lambda e: None, threading.Event(), port=self.port)
        self.assertFalse(self.flag.exists())     # nur einmal
        self.assertEqual(agentclient.countdown("127.0.0.1", self.key, 1, "Test", threading.Event(),
                                               port=self.port), "start")
        agentclient.power("127.0.0.1", self.key, "reboot", self.port, delay=0)
        time.sleep(4)
        self.udp.settimeout(4)
        while True:  # alte Beacons verwerfen
            try:
                self.udp.recvfrom(discovery.MAX_PACKET + 1)
            except TimeoutError:
                break
        with self.assertRaises(TimeoutError):  # „Neustart“: meldet sich eine Weile nicht
            self.udp.recvfrom(discovery.MAX_PACKET + 1)


if __name__ == "__main__":
    unittest.main()
