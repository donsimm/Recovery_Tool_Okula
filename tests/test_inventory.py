import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import inventory
from tests import test_restore as base

CPUINFO = """processor\t: 0
model name\t: Intel(R) Core(TM) i5-4200U CPU @ 1.60GHz
physical id\t: 0
core id\t: 0
processor\t: 1
model name\t: Intel(R) Core(TM) i5-4200U CPU @ 1.60GHz
physical id\t: 0
core id\t: 0
processor\t: 2
physical id\t: 0
core id\t: 1
processor\t: 3
physical id\t: 0
core id\t: 1
"""


class HardwareTest(unittest.TestCase):
    def test_dmi_cleans_placeholders(self):
        with tempfile.TemporaryDirectory() as d:
            values = {"sys_vendor": "Dell Inc.", "product_name": "Latitude 5420",
                      "product_serial": "To Be Filled By O.E.M.", "product_uuid": "4C4C4544-0035-3010-8052-B3C04F4A3133",
                      "board_serial": "Default string", "chassis_type": "10", "bios_version": "1.27.0"}
            for k, v in values.items():
                Path(d, k).write_text(v + "\n")
            info = inventory.dmi(Path(d))
        self.assertEqual(info["product_serial"], "")
        self.assertEqual(info["board_serial"], "")
        self.assertEqual(info["product_uuid"], "4c4c4544-0035-3010-8052-b3c04f4a3133")
        self.assertEqual(info["chassis"], "Notebook")
        self.assertEqual(info["bios_version"], "1.27.0")

    def test_junk_uuids(self):
        for v in ("03000200-0400-0500-0006-000700080009", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF", "0", ""):
            self.assertEqual(inventory.clean(v), "", v)

    def test_cpu_and_memory(self):
        self.assertEqual(inventory.cpu(CPUINFO), {"model": "Intel(R) Core(TM) i5-4200U CPU @ 1.60GHz",
                                                  "threads": 4, "cores": 2})
        self.assertEqual(inventory.memory("MemTotal:        2007564 kB\n"), 2007564 * 1024)

    def test_battery_health(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d, "BAT0")
            b.mkdir()
            for k, v in {"energy_full": "38000000", "energy_full_design": "50000000", "cycle_count": "312",
                         "manufacturer": "SMP", "capacity": "81"}.items():
                (b / k).write_text(v)
            [bat] = inventory.batteries(Path(d))
        self.assertEqual((bat["health_percent"], bat["cycles"]), (76, "312"))


class WindowsTest(unittest.TestCase):
    def test_windows_11_from_registry(self):
        answers = {("SOFTWARE", "ProductName"): "Windows 10 Pro", ("SOFTWARE", "CurrentBuild"): "22631",
                   ("SOFTWARE", "DisplayVersion"): "23H2", ("SOFTWARE", "EditionID"): "Professional",
                   ("SYSTEM", "ComputerName"): "BUCHHALTUNG-01"}

        def fake_run(cmd, **kw):
            hive = Path(cmd[1]).name
            return mock.Mock(returncode=0 if (hive, cmd[3]) in answers else 1, stdout=answers.get((hive, cmd[3]), ""))

        with tempfile.TemporaryDirectory() as d:
            config = Path(d, "Windows/System32/config")
            config.mkdir(parents=True)
            (config / "SOFTWARE").write_bytes(b"regf")
            (config / "SYSTEM").write_bytes(b"regf")
            with mock.patch.object(inventory.shutil, "which", lambda n: "/usr/bin/" + n), \
                    mock.patch.object(inventory.subprocess, "run", fake_run):
                info = inventory.inspect_root(Path(d))
        self.assertEqual(info["name"], "Windows 11 Pro 23H2")
        self.assertEqual(info["hostname"], "BUCHHALTUNG-01")
        self.assertEqual(info["build"], "22631")


@unittest.skipUnless(base.can_run(), "braucht root und Loop-Devices")
class OsDetectionTest(base.RestoreTest):
    def test_linux_detected_without_writing(self):
        dev = self.loop("os.img", 128)
        base.sh("sfdisk", "-q", dev, input="label: gpt\nstart=2048, size=100M\n")
        base.sh("partx", "-u", dev)
        inventory.imaging._wait_for([f"{dev}p1"])
        root = self.dir / "rootfs"
        (root / "etc").mkdir(parents=True)
        (root / "usr/bin").mkdir(parents=True)
        (root / "etc/os-release").write_text('NAME="Debian"\nPRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n')
        (root / "etc/hostname").write_text("werkstatt-pc\n")
        base.sh("mkfs.ext4", "-q", "-F", "-d", str(root), f"{dev}p1")
        before = base.sha(f"{dev}p1")
        disks = base.loop_disks(dev)
        with mock.patch.object(inventory, "INSPECT_DIR", str(self.dir / "inspect")), \
                mock.patch.object(inventory, "MIN_OS_PARTITION", 1):
            systems = inventory.operating_systems(disks)
        self.assertEqual([(s["name"], s["hostname"], s["partition"]) for s in systems],
                         [("Debian GNU/Linux 12 (bookworm)", "werkstatt-pc", f"{Path(dev).name}p1")])
        self.assertEqual(base.sha(f"{dev}p1"), before, "Partition wurde beim Auslesen verändert")
        self.assertEqual(list((self.dir / "inspect").iterdir()), [], "Einhängepunkt nicht aufgeräumt")
        mounts = Path("/proc/mounts").read_text()
        self.assertNotIn(str(self.dir / "inspect"), mounts)

    test_gpt = test_dos = test_refuses_smaller_target = test_corrupt_image_detected_before_writing = None
    test_console_shows_tool_verification_then_restore = None


if __name__ == "__main__":
    unittest.main()
