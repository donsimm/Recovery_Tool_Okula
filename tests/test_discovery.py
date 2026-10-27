import json
import socket
import threading
import unittest

from okula_recovery import discovery

LSBLK = json.dumps({"blockdevices": [
    {"name": "sda", "size": 512110190592, "model": "Samsung SSD 860 ", "serial": "S3Z1", "type": "disk", "tran": "sata"},
    {"name": "sdb", "size": 16008609792, "model": "Cruzer", "serial": "4C53", "type": "disk", "tran": "usb"},
    {"name": "loop0", "size": 1000, "model": None, "serial": None, "type": "loop", "tran": None},
    {"name": "sr0", "size": 1073741312, "model": "DVD", "serial": "", "type": "rom", "tran": "sata"},
]})


def beacon(**over):
    msg = {"type": discovery.BEACON_TYPE, "proto": discovery.PROTOCOL_VERSION, "id": "uuid-1",
           "hostname": "debian-live", "ip": "10.9.9.9", "mac": "aa:bb:cc:dd:ee:ff",
           "vendor": "Dell Inc.", "product": "OptiPlex 7050",
           "disks": [{"name": "sda", "size": 500, "model": "SSD", "serial": "X", "transport": "sata"}],
           "version": "0.1.0"}
    msg.update(over)
    return json.dumps(msg).encode()


class ParseTest(unittest.TestCase):
    def test_lsblk_only_disks(self):
        disks = discovery.parse_lsblk(LSBLK)
        self.assertEqual([(d.name, d.transport) for d in disks], [("sda", "sata"), ("sdb", "usb")])
        self.assertEqual(disks[0].model, "Samsung SSD 860")

    def test_lsblk_garbage(self):
        self.assertEqual(discovery.parse_lsblk("nope"), [])

    def test_beacon_uses_sender_ip(self):
        info = discovery.parse_beacon(beacon(), "192.168.1.77")
        self.assertEqual(info.ip, "192.168.1.77")
        self.assertEqual(info.hardware, "Dell Inc. OptiPlex 7050")
        self.assertEqual(info.disks[0].size, 500)

    def test_beacon_rejects_foreign_and_oversized(self):
        self.assertIsNone(discovery.parse_beacon(b"hello", "1.2.3.4"))
        self.assertIsNone(discovery.parse_beacon(beacon(type="other"), "1.2.3.4"))
        self.assertIsNone(discovery.parse_beacon(beacon(proto=99), "1.2.3.4"))
        self.assertIsNone(discovery.parse_beacon(b" " * (discovery.MAX_PACKET + 1), "1.2.3.4"))

    def test_beacon_skips_bad_disks(self):
        info = discovery.parse_beacon(beacon(disks=[{"name": "sda", "size": "x"}, "junk", {"size": 1}]), "1.2.3.4")
        self.assertEqual(info.disks, [])


class ListenerTest(unittest.TestCase):
    def test_round_trip_with_ack(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        got, event = [], threading.Event()
        listener = discovery.Listener(lambda i: (got.append(i), event.set()), port=port, server_name="srv")
        listener.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as agent:
                agent.settimeout(2)
                agent.sendto(beacon(), ("127.0.0.1", port))
                ack = json.loads(agent.recvfrom(1024)[0])
            self.assertTrue(event.wait(2))
        finally:
            listener.stop()
        self.assertEqual(ack["type"], discovery.ACK_TYPE)
        self.assertEqual(ack["name"], "srv")
        self.assertEqual(got[0].hostname, "debian-live")
        self.assertEqual(got[0].ip, "127.0.0.1")


class AgentNetworkTest(unittest.TestCase):
    def test_link_local_address(self):
        from okula_recovery import agent
        self.assertEqual(agent.link_local_address("3c:52:82:1a:4f:10"), "169.254.80.16")
        addr = agent.link_local_address("00:00:00:00:fe:ff")
        self.assertTrue(addr.startswith("169.254.") and 1 <= int(addr.split(".")[2]) <= 254)

    def test_wired_interfaces(self):
        import tempfile
        from pathlib import Path
        from okula_recovery import agent
        with tempfile.TemporaryDirectory() as d:
            for name, dev, wifi in (("lo", False, False), ("enp2s0", True, False), ("wlp3s0", True, True),
                                    ("docker0", False, False)):
                p = Path(d) / name
                p.mkdir()
                if dev:
                    (p / "device").mkdir()
                if wifi:
                    (p / "wireless").mkdir()
            self.assertEqual(agent.wired_interfaces(Path(d)), ["enp2s0"])


class AgentConsoleTest(unittest.TestCase):
    def test_console_shows_only_key_messages_without_banner(self):
        import subprocess
        import sys
        import tempfile
        import time
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        listener = discovery.Listener(lambda i: None, port=port, server_name="RecoveryPC")
        listener.start()
        with tempfile.NamedTemporaryFile("r") as tty:
            p = subprocess.Popen([sys.executable, "-m", "okula_recovery.agent", "--port", str(port), "--server",
                                  "127.0.0.1", "--no-broadcast", "--interval", "0.5", "--console", tty.name,
                                  "--key-file", "/nonexistent"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.5)
            p.terminate()
            p.wait()
            listener.stop()
            text = open(tty.name).read()
        self.assertNotIn("#", text)
        self.assertNotIn("sh[", text)
        self.assertEqual(text.count("» Verbunden:"), 1, text)
        self.assertIn("RecoveryPC", text)
        self.assertIn("» Kein Schlüssel", text)  # Meldungen dürfen sich nicht überschreiben


if __name__ == "__main__":
    unittest.main()
