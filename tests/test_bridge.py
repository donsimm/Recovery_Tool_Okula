"""Netzwerkbrücke br0 (I-001) mit nachgebildetem nmcli und ip: Einrichten, schon vorhanden, Rückfall, Entfernen."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from okula_recovery import bridge

MAC = "70:85:c2:a8:cd:13"


class FakeNet:
    """NetworkManager-Zustand im Speicher; br0 bekommt beim Aktivieren eine IP (oder nicht: dhcp_ok=False)."""

    def __init__(self, nm=True, dhcp_ok=True, dev_type="ethernet"):
        self.nm, self.dhcp_ok, self.dev_type = nm, dhcp_ok, dev_type
        self.cons = {"Wired connection 1": {"connection.autoconnect": "yes", "ipv4.method": "auto",
                                            "ipv4.addresses": "", "ipv6.method": "auto", "ipv6.dns": "fd00\\:\\:1"},
                     "lo": {}}
        self.addr = {"eno2": "192.168.110.199/24"}
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        ok = lambda out="": subprocess.CompletedProcess(cmd, 0, out, "")
        if cmd[0] == "ip":
            if cmd[1:4] == ["-4", "route", "show"]:
                return ok("default via 192.168.110.1 dev eno2 proto dhcp src 192.168.110.199 metric 100\n")
            dev = cmd[-1]
            ip = self.addr.get(dev, "")
            return ok(f"3: {dev}    inet {ip} brd 192.168.110.255 scope global {dev}\n" if ip else "")
        assert cmd[0] == "nmcli", cmd
        if not self.nm:
            return subprocess.CompletedProcess(cmd, 8, "", "Error: NetworkManager is not running.")
        args = [a for a in cmd[1:] if a not in ("--wait", "30", "5")]
        if args[:4] == ["-t", "-f", "RUNNING", "general"]:
            return ok("running\n")
        if args[:5] == ["-t", "-f", "NAME", "connection", "show"]:
            return ok("".join(n + "\n" for n in self.cons))
        if args[0] == "-g" and args[2:4] == ["device", "show"]:
            return ok({"GENERAL.TYPE": self.dev_type, "GENERAL.CONNECTION": "Wired connection 1",
                       "GENERAL.HWADDR": MAC.upper().replace(":", "\\:")}[args[1]] + "\n")
        if args[0] == "-g" and args[2:4] == ["connection", "show"]:
            return ok(self.cons[args[4]].get(args[1], "") + "\n")
        if args[:2] == ["connection", "add"]:
            settings = dict(zip(args[2::2], args[3::2]))
            self.cons[settings["con-name"]] = settings
            return ok()
        if args[:2] == ["connection", "modify"]:
            self.cons[args[2]][args[3]] = args[4]
            return ok()
        if args[:2] == ["connection", "delete"]:
            self.cons.pop(args[2])
            if args[2] == bridge.CON_BRIDGE:
                self.addr.pop("br0", None)
            return ok()
        if args[:2] == ["connection", "up"]:
            name = args[2]
            if name == bridge.CON_PORT:
                self.addr.pop("eno2", None)
            elif name == bridge.CON_BRIDGE and self.dhcp_ok:
                self.addr["br0"] = "192.168.110.199/24"
            elif name == "Wired connection 1":
                self.addr["eno2"] = "192.168.110.199/24"
            return ok()
        raise AssertionError(f"unerwartet: {cmd}")


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name) / "bridge.json"
        self.out = []
        self.now = [0.0]

    def tearDown(self):
        self.dir.cleanup()

    def make(self, net):
        def sleep(s):
            self.now[0] += s
        return bridge.Bridge(run=net, emit=self.out.append, sleep=sleep, clock=lambda: self.now[0],
                             state_file=self.state)

    def test_setup_same_mac_and_ip_settings(self):
        net = FakeNet()
        self.assertEqual(self.make(net).setup(), 0)
        br = net.cons[bridge.CON_BRIDGE]
        self.assertEqual((br["type"], br["ifname"], br["bridge.stp"], br["bridge.forward-delay"]),
                         ("bridge", "br0", "no", "0"))
        self.assertEqual(br["bridge.mac-address"], MAC)
        self.assertEqual((br["ipv4.method"], br["ipv6.method"], br["ipv6.dns"]), ("auto", "auto", "fd00::1"))
        self.assertNotIn("ipv4.addresses", br)                         # leere Werte nicht übernommen
        port = net.cons[bridge.CON_PORT]
        self.assertEqual((port["ifname"], port["master"], port["slave-type"]), ("eno2", bridge.CON_BRIDGE, "bridge"))
        self.assertEqual(net.cons["Wired connection 1"]["connection.autoconnect"], "no")
        self.assertIn("br0 aktiv: 192.168.110.199/24 (gleiche Adresse)", self.out[-1])
        self.assertTrue(self.state.exists())

    def test_already_running_does_nothing(self):
        net = FakeNet()
        self.make(net).setup()
        before = len(net.calls)
        self.out.clear()
        self.assertEqual(self.make(net).setup(), 0)
        self.assertIn("läuft bereits", self.out[-1])
        self.assertFalse([c for c in net.calls[before:] if c[1:3] in (["connection", "add"], ["connection", "up"])])

    def test_fallback_without_ipv4(self):
        net = FakeNet(dhcp_ok=False)
        self.assertEqual(self.make(net).setup(), 2)
        self.assertNotIn(bridge.CON_BRIDGE, net.cons)
        self.assertNotIn(bridge.CON_PORT, net.cons)
        self.assertEqual(net.cons["Wired connection 1"]["connection.autoconnect"], "yes")
        self.assertEqual(net.addr.get("eno2"), "192.168.110.199/24")
        self.assertGreaterEqual(self.now[0], 45)
        self.assertIn("NICHT eingerichtet", self.out[-1])
        self.assertFalse(self.state.exists())

    def test_remove_restores(self):
        net = FakeNet()
        self.make(net).setup()
        self.assertEqual(self.make(net).remove(), 0)
        self.assertEqual(set(net.cons), {"Wired connection 1", "lo"})
        self.assertEqual(net.cons["Wired connection 1"]["connection.autoconnect"], "yes")
        self.assertEqual(net.addr, {"eno2": "192.168.110.199/24"})
        self.assertEqual(self.make(net).remove(), 0)
        self.assertIn("Keine Netzwerkbrücke", self.out[-1])

    def test_without_networkmanager_nothing_changes(self):
        net = FakeNet(nm=False)
        self.assertEqual(self.make(net).setup(), 0)
        self.assertIn("NetworkManager läuft nicht", self.out[-1])
        self.assertFalse([c for c in net.calls if "add" in c or "modify" in c])

    def test_never_on_wlan(self):
        net = FakeNet(dev_type="wifi")
        with self.assertRaisesRegex(bridge.BridgeError, "Kabel-Schnittstelle"):
            self.make(net).setup()
        self.assertNotIn(bridge.CON_BRIDGE, net.cons)

    def test_unescape(self):
        self.assertEqual(bridge._unescape("70\\:85\\:c2"), "70:85:c2")
        self.assertEqual(bridge._unescape("a\\\\b"), "a\\b")

    def test_messages_without_address(self):
        net = FakeNet()
        self.make(net).setup()
        self.make(net).remove()
        for text in self.out:
            self.assertNotRegex(text, r"\b(du|Sie|Ihr|dein)\b")


if __name__ == "__main__":
    unittest.main()
