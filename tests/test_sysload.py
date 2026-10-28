"""Serverlast aus einem nachgebauten /proc und /sys."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import sysload

ROUTE = ("Iface\tDestination\tGateway\tFlags\n"
         "enp3s0\t0001A8C0\t00000000\t0001\n"
         "enp3s0\t00000000\t016EA8C0\t0003\n")
DEV = ("Inter-|   Receive |  Transmit\n face |bytes packets errs drop fifo frame compressed multicast|bytes\n"
       "    lo: 5000 10 0 0 0 0 0 0 5000 10 0 0 0 0 0 0\n"
       "enp3s0: {rx} 100 0 0 0 0 0 0 {tx} 50 0 0 0 0 0 0\n")


class SamplerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proc, self.sys = Path(self.tmp.name) / "proc", Path(self.tmp.name) / "sys"
        (self.proc / "net").mkdir(parents=True)
        (self.sys / "class/net/enp3s0").mkdir(parents=True)
        (self.sys / "class/net/enp3s0/speed").write_text("1000\n")
        (self.proc / "net/route").write_text(ROUTE)
        (self.proc / "loadavg").write_text("1.84 1.20 0.95 2/300 1234\n")
        (self.proc / "meminfo").write_text("MemTotal:       16000000 kB\nMemFree:         1000000 kB\n"
                                           "MemAvailable:    10000000 kB\nSwapTotal: 2000000 kB\nSwapFree: 1500000 kB\n")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, busy, idle, rx, tx):
        (self.proc / "stat").write_text(f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 2 3 4\n")
        (self.proc / "net/dev").write_text(DEV.format(rx=rx, tx=tx))

    def test_rates_and_usage(self):
        s = sysload.Sampler(self.proc, self.sys)
        self.write(1000, 9000, 0, 0)
        with mock.patch.object(sysload.time, "monotonic", return_value=100.0):
            first = s.sample()
        self.assertEqual((first.cpu, first.rx, first.iface, first.link), (0.0, 0.0, "enp3s0", 1000))
        self.write(1300, 9100, 62_500_000, 1_250_000)  # 1 s später: 300 von 400 Jiffies, 500 Mbit/s rein
        with mock.patch.object(sysload.time, "monotonic", return_value=101.0):
            load = s.sample()
        self.assertAlmostEqual(load.cpu, 0.75)
        self.assertEqual((load.rx, load.tx), (62_500_000, 1_250_000))
        self.assertAlmostEqual(load.lan, 0.5)
        self.assertEqual(load.mem_used, 6_000_000 * 1024)
        self.assertEqual(load.swap_used, 500_000 * 1024)
        self.assertEqual(load.loadavg, "1.84 1.20 0.95")
        self.assertEqual(sysload.rates(load.rx, load.tx), "↓ 500.0  ↑ 10.0 Mbit/s")

    def test_without_default_route_and_counter_reset(self):
        (self.proc / "net/route").write_text("Iface\tDestination\n")
        s = sysload.Sampler(self.proc, self.sys)
        self.write(0, 0, 900, 900)
        self.assertEqual(s.sample().iface, "enp3s0")  # meister Verkehr, lo zählt nicht
        self.write(0, 0, 10, 10)  # Zähler zurückgesetzt (Karte neu): keine negativen Raten
        self.assertEqual((s.sample().rx, s.sample().tx), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
