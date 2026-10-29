"""Fernsteuerung: Wake-on-LAN, Startreihenfolge (efibootmgr), Startarten pro Gerät und beim PXE-Dienst."""

import ipaddress
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import devices, pxe, wininstall, wol
from okula_recovery.imaging import ImagingError

OVMF = """BootCurrent: 0001
Timeout: 0 seconds
BootOrder: 0000,0001,0002,0003
Boot0000* Windows Boot Manager\tHD(1,GPT,1234,0x800,0x32000)/File(\\EFI\\Microsoft\\Boot\\bootmgfw.efi)
Boot0001* UEFI PXEv4 (MAC:525400123456)\tPciRoot(0x0)/Pci(0x2,0x0)/MAC(525400123456,0x1)/IPv4(0.0.0.0,0x0,DHCP,0.0.0.0,0.0.0.0,0.0.0.0)
Boot0002* UEFI PXEv6 (MAC:525400123456)\tPciRoot(0x0)/Pci(0x2,0x0)/MAC(525400123456,0x1)/IPv6([::]:<->[::]:,0,0)
Boot0003* UEFI HTTPv4 (MAC:525400123456)\tPciRoot(0x0)/Pci(0x2,0x0)/MAC(525400123456,0x1)/IPv4(0.0.0.0,0x0,DHCP,0.0.0.0,0.0.0.0,0.0.0.0)/Uri()
"""
HP = """BootCurrent: 0004
BootOrder: 0004,0000,0005,0003
Boot0000* Windows Boot Manager\tHD(1,GPT,a,0x800,0x82000)/File(\\EFI\\Microsoft\\Boot\\bootmgfw.efi)
Boot0003* Generic USB Boot\tVenHw(1234)
Boot0004* USB:  SanDisk\tPciRoot(0x0)/Pci(0x14,0x0)/USB(1,0)
Boot0005  IPV4 Network - Intel(R) Ethernet Connection I219-LM\tPciRoot(0x0)/Pci(0x1f,0x6)/MAC(3c5282112233,0)/IPv4(0.0.0.0:0<->0.0.0.0:0,0,0)
"""


class BootOrderTest(unittest.TestCase):
    def test_find_network_entry(self):
        self.assertEqual(wininstall.network_entry(wininstall.parse_boot(OVMF)), "0001")   # nicht IPv6/HTTP
        self.assertEqual(wininstall.network_entry(wininstall.parse_boot(HP)), "0005")     # nicht „Generic USB“
        self.assertEqual(wininstall.network_entry(wininstall.parse_boot(
            "BootOrder: 0000\nBoot0000* Windows Boot Manager\tHD(1)\n")), "")

    def run_efi(self, output: str, on: bool, saved=None):
        calls = []
        state = {"out": output}

        def fake(*args):
            calls.append(args)
            if args and args[0] == "--bootorder":
                lines = [line for line in state["out"].splitlines() if not line.startswith("BootOrder:")]
                state["out"] = "\n".join([f"BootOrder: {args[1]}"] + lines)
            return state["out"]

        with mock.patch.object(wininstall, "efibootmgr", side_effect=fake), \
                mock.patch.object(wininstall.Path, "is_dir", return_value=True):
            return wininstall.set_netfirst(on, saved), calls

    def test_netfirst_on_and_back(self):
        result, calls = self.run_efi(HP, True)
        self.assertIn(("--bootorder", "0005,0004,0000,0003"), calls)
        self.assertIn(("--active", "--bootnum", "0005"), calls)   # inaktiver Eintrag wird aktiviert
        self.assertTrue(result["netfirst"])
        self.assertEqual(result["previous"], ["0004", "0000", "0005", "0003"])
        on = HP.replace("BootOrder: 0004,0000,0005,0003", "BootOrder: 0005,0004,0000,0003")
        result, calls = self.run_efi(on, False, saved=["0004", "0000", "0005", "0003"])
        self.assertIn(("--bootorder", "0004,0000,0005,0003"), calls)            # gespeicherte Reihenfolge
        self.assertFalse(result["netfirst"])
        _result, calls = self.run_efi(on, False, saved=["0001", "0002"])        # passt nicht mehr
        self.assertIn(("--bootorder", "0004,0000,0003,0005"), calls)            # Netzwerk ans Ende

    def test_errors(self):
        with mock.patch.object(wininstall.Path, "is_dir", return_value=False):
            self.assertFalse(wininstall.boot_status()["uefi"])
            with self.assertRaises(ImagingError):
                wininstall.set_netfirst(True)
        with mock.patch.object(wininstall, "efibootmgr", return_value="BootOrder: 0000\nBoot0000* Windows\tHD(1)\n"), \
                mock.patch.object(wininstall.Path, "is_dir", return_value=True):
            with self.assertRaises(ImagingError):   # kein Netzwerkeintrag (PXE im BIOS aus)
                wininstall.set_netfirst(True)


class WolTest(unittest.TestCase):
    def test_packet_and_targets(self):
        p = wol.magic_packet("3C-52-82-11-22-33")
        self.assertEqual((len(p), p[:6], p[6:12]), (102, b"\xff" * 6, bytes.fromhex("3c5282112233")))
        with self.assertRaises(ValueError):
            wol.magic_packet("3c:52:82:11:22")
        ifaces = [ipaddress.IPv4Interface("192.168.110.10/24"), ipaddress.IPv4Interface("127.0.0.1/8"),
                  ipaddress.IPv4Interface("10.0.0.5/16")]
        self.assertEqual(wol.targets(ifaces), ["192.168.110.255", "10.0.255.255", "255.255.255.255"])

    def test_wake_sends_broadcasts(self):
        sock = mock.MagicMock()
        with mock.patch.object(wol.socket, "socket", return_value=sock):
            sock.__enter__.return_value = sock
            n = wol.wake(["3c:52:82:11:22:33"], [ipaddress.IPv4Interface("192.168.110.10/24")])
        self.assertEqual(n, 4)   # 2 Ziele × 2 Ports
        sock.setsockopt.assert_called_with(wol.socket.SOL_SOCKET, wol.socket.SO_BROADCAST, 1)
        self.assertIn(mock.call(wol.magic_packet("3c:52:82:11:22:33"), ("192.168.110.255", 9)),
                      sock.sendto.call_args_list)


class ModesTest(unittest.TestCase):
    def test_device_modes(self):
        inv = {"network": [{"mac": "3c:52:82:11:22:33"}, {"mac": "a4:c3:f0:77:88:99", "wireless": True}]}
        d = devices.Device(id="d", netboot=True, macs=["3c:52:82:11:22:33", "a4:c3:f0:77:88:99"], inventory=inv)
        off = devices.Device(id="e", netboot=False, macs=["00:11:22:33:44:55"])
        self.assertEqual(devices.netboot_modes([d, off]), {"3c:52:82:11:22:33": "always"})
        d.netfirst = True
        self.assertEqual(devices.netboot_modes([d]), {"3c:52:82:11:22:33": "local"})
        d.boot_request = True
        self.assertEqual(devices.netboot_modes([d]), {"3c:52:82:11:22:33": "once"})

    def test_pxe_modes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "tftp" / "pxelinux.cfg").mkdir(parents=True)
            modes = pxe.parse_allow(["52:54:00:12:34:56 local", "52-54-00-AA-BB-CC once", "52:54:00:00:00:01"])
            self.assertEqual(modes, {"52:54:00:00:00:01": "always", "52:54:00:12:34:56": "local",
                                     "52:54:00:aa:bb:cc": "once"})
            pxe.write_allowed(modes, base)
            self.assertEqual(pxe.read_allowed(base), set(modes))
            self.assertEqual(pxe.read_modes(base), modes)
            mode = base / "tftp/okula/mode"
            self.assertIn("set default=2", (mode / "52:54:00:12:34:56").read_text())          # lokal
            self.assertNotIn("default", (mode / "52:54:00:aa:bb:cc").read_text())            # einmal Agent
            self.assertNotIn("default", (mode / "52:54:00:00:00:01").read_text())            # immer Agent
            self.assertEqual(len(list(mode.iterdir())), 3)
            self.assertIn("LOCALBOOT 0", (base / "tftp/pxelinux.cfg/01-52-54-00-12-34-56").read_text())
            self.assertFalse((base / "tftp/pxelinux.cfg/01-52-54-00-aa-bb-cc").exists())
            pxe.write_allowed({"52:54:00:aa:bb:cc": "local"}, base)    # Alte Marker verschwinden
            self.assertEqual(sorted(p.name for p in mode.iterdir()), ["52:54:00:aa:bb:cc"])
            self.assertIn("set default=2", (mode / "52:54:00:aa:bb:cc").read_text())
            self.assertFalse((base / "tftp/pxelinux.cfg/01-52-54-00-12-34-56").exists())
            for bad in (["52:54:00:12:34:56 immer"], ["52:54:00:12:34 local"], ["52:54:00:12:34:56 local x"]):
                with self.assertRaises(pxe.PxeError):
                    pxe.parse_allow(bad)
        cfg = pxe.GRUB_CFG.format(params="boot=live")
        self.assertIn("source /okula/mode/${net_default_mac}", cfg)
        self.assertNotIn("[ -f", cfg)   # geht über TFTP nicht
        for text in (cfg, pxe.PXELINUX_CFG, pxe.PXELINUX_LOCAL, *pxe.GRUB_MODE.values()):
            text.encode("ascii")    # Startdateien nur ASCII

    def test_http_once_becomes_local(self):
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        from okula_recovery import stick
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "http").mkdir()
            (base / "tftp" / "pxelinux.cfg").mkdir(parents=True)
            (base / "http" / stick.AGENT_LAYER).write_bytes(b"agent")
            (base / "arp").write_text("IP HW Flags MAC Mask Dev\n127.0.0.1 0x1 0x2 52:54:00:12:34:56 * lo\n")
            pxe.write_allowed({"52:54:00:12:34:56": "once"}, base)

            class H(pxe.Handler):
                arp = str(base / "arp")

                def log_message(self, *a):
                    pass

            H.base = base
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/{stick.AGENT_LAYER}") as r:
                    self.assertEqual(r.read(), b"agent")
            finally:
                httpd.shutdown()
                httpd.server_close()
            self.assertEqual(json.loads((base / "modes.json").read_text()), {"52:54:00:12:34:56": "local"})
            self.assertIn("set default=2", (base / "tftp/okula/mode/52:54:00:12:34:56").read_text())


if __name__ == "__main__":
    unittest.main()
