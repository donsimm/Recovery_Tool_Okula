"""Windows-Direktinstallation: Tool → Agent auf einer Loop-Disk (ohne FAT/NTFS im Test-Kernel: ext4)."""

import re
import socket
import subprocess
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, jobs, wininstall, winsetup, winunattend, wire
from tests.isofixtures import HAVE_TOOLS, windows_iso
from tests.test_restore import can_run, loop_disks, sh


class ScriptTest(unittest.TestCase):
    def test_install_cmd_split_and_single(self):
        cmd = winsetup.install_cmd("ab12cd34", 2, "sources/install.wim", True, "de-DE")
        self.assertIn("\r\n", cmd)
        self.assertTrue(cmd.isascii(), "cmd-Skripte nur ASCII")
        self.assertIn('/SWMFile:"%S%:\\sources\\install*.swm" /Index:2 /ApplyDir:%W%:\\', cmd)
        self.assertIn("okula-ab12cd34.target", cmd)
        self.assertIn("bcdboot %W%:\\Windows /s Z: /f UEFI /l de-DE", cmd)
        self.assertIn("wpeutil reboot", cmd)
        single = winsetup.install_cmd("x", 1, "sources/install.esd", False, "en-US")
        self.assertIn('/ImageFile:"%S%:\\sources\\install.esd" /Index:1', single)
        self.assertNotIn("SWMFile", single)
        done = winsetup.setupcomplete_cmd("ab12cd34")
        self.assertIn("okula\\ab12cd34.setup", done)
        self.assertIn("delete partition override", done)
        self.assertIn("extend", done)
        self.assertNotIn(" C D ", done.split("for %%L in (")[1].split(")")[0] + " ")  # C: nie löschen

    def test_layout(self):
        t = wininstall.layout(256 * 1000**3, 7 * 1024**3, 40 * 1000**3)
        sizes = [int(x) for x in re.findall(r"size=(\d+)MiB", t)]
        self.assertEqual(sizes[:2], [260, 16])
        self.assertIn(wininstall.GPT_ESP, t)
        self.assertTrue(t.strip().endswith('name="Okula Setup"'))
        with self.assertRaisesRegex(wininstall.ImagingError, "zu klein"):
            wininstall.layout(32 * 1000**3, 7 * 1024**3, 40 * 1000**3)


@unittest.skipUnless(can_run() and HAVE_TOOLS, "braucht root, Loop-Devices, genisoimage, wimlib, xorriso")
class DirectInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        img = self.d / "disk.img"
        with open(img, "wb") as f:
            f.truncate(1536 * 1024 * 1024)
        self.dev = sh("losetup", "-fP", "--show", str(img)).strip()
        self.key = bytes(range(32))
        self.efi = []
        efi_dir = self.d / "efi"
        efi_dir.mkdir()

        def fake_efibootmgr(*args):
            self.efi.append(args)
            entries = "BootCurrent: 0001\nBoot0000* Windows Boot Manager\nBoot0001* USB\n"
            if any("--create-only" in a for a in args) or len(self.efi) > 2:
                entries += "Boot0007* Okula Windows-Installation\n"
            return entries

        def mkfs(part, label=""):
            sh("mkfs.ext4", "-q", "-F", part)

        def mount(part, where, ntfs=False):
            where.mkdir(parents=True, exist_ok=True)
            sh("mount", part, str(where))

        self.patches = [
            mock.patch.object(wininstall, "EFI_DIR", efi_dir),
            mock.patch.object(wininstall, "WORK", self.d / "work"),
            mock.patch.object(wininstall, "MIN_WIN_MIB", 64),
            mock.patch.object(wininstall, "_mkfat", mkfs),
            mock.patch.object(wininstall, "_mkntfs", mkfs),
            mock.patch.object(wininstall, "_mount", mount),
            mock.patch.object(wininstall, "efibootmgr", fake_efibootmgr),
            mock.patch.object(winsetup, "FAT32_MAX", 1_000_000),
            mock.patch.object(winsetup, "SPLIT_MB", 1),
            mock.patch.object(winsetup, "MIN_DISK", 0),
            mock.patch.object(agent, "log", lambda *a, **k: None),
            mock.patch.object(agent.imaging, "list_disks", lambda: loop_disks(self.dev)),
        ]
        for p in self.patches:
            p.start()
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        ctx = wire.server_context(self.key)

        def serve():
            while True:
                try:
                    conn, addr = self.server.accept()
                except OSError:
                    return
                threading.Thread(target=agent.handle_connection, args=(ctx, conn, addr), daemon=True).start()

        threading.Thread(target=serve, daemon=True).start()

    def tearDown(self):
        self.server.close()
        for p in self.patches:
            p.stop()
        subprocess.run(["umount", "-R", str(self.d / "mnt")], capture_output=True)
        subprocess.run(["losetup", "-d", self.dev], capture_output=True)
        self.tmp.cleanup()

    def mounted(self, number):
        mnt = self.d / "mnt"
        mnt.mkdir(exist_ok=True)
        sh("mount", f"{self.dev}p{number}", str(mnt))
        return mnt

    def test_setup_partition_prepared_and_bootnext_set(self):
        iso = windows_iso(self.d, payload=3_000_000)
        opts = winunattend.WinOptions(local_account="Okula", computer_name="PC-Empfang")
        plan = winsetup.plan(iso, 2, opts)
        self.assertTrue(plan.split)
        events = []
        timers = []
        with mock.patch.object(agent.threading, "Timer", lambda *a, **k: timers.append(a) or mock.Mock()):
            boot = agentclient.install_windows("127.0.0.1", self.key, iso, plan, self.dev, events.append,
                                               threading.Event(), self.port)
            for _ in range(50):  # Agent schliesst den Auftrag kurz nach „done“ ab
                if timers:
                    break
                threading.Event().wait(0.1)
        self.assertEqual(boot, "0007")
        self.assertEqual(timers[0][0], 15)  # Neustart geplant (hier nicht ausgeführt)
        self.assertIn("split", [e["phase"] for e in events])
        table = sh("sfdisk", "-d", self.dev)
        self.assertIn("label: gpt", table)
        self.assertEqual(len(re.findall(rf"^{self.dev}p\d", table, re.M)), 4)
        self.assertIn(f"type={wininstall.GPT_ESP}", table)
        # BootNext auf Partition 4 der Zieldisk
        create = next(a for a in self.efi if "--create-only" in a)
        self.assertEqual(create[create.index("--disk") + 1], self.dev)
        self.assertEqual(create[create.index("--part") + 1], "4")
        self.assertIn(("--bootnext", "0007"), self.efi)

        setup = self.mounted(4)
        try:
            names = {str(p.relative_to(setup)).lower() for p in setup.rglob("*")}
            for f in ("bootmgr", "efi/boot/bootx64.efi", "sources/boot.wim", "sources/install.swm",
                      "sources/install2.swm", "autounattend.xml", "sources/autounattend.xml",
                      "okula/install.cmd", "okula/unattend.xml", "okula/setupcomplete.cmd",
                      f"okula/{plan.install_id}.setup"):
                self.assertIn(f, names)
            self.assertNotIn("sources/install.wim", names)
            r = subprocess.run(["wimlib-imagex", "verify", str(setup / "sources/install.swm"),
                                f"--ref={setup}/sources/install*.swm"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            launcher = (setup / "sources/autounattend.xml").read_text()
            self.assertIn("okula\\install.cmd", launcher)
            root = ET.fromstring(launcher)
            self.assertEqual([s.get("pass") for s in root], ["windowsPE"])
            system = ET.fromstring((setup / "okula/unattend.xml").read_text())
            self.assertEqual([s.get("pass") for s in system], ["specialize", "oobeSystem"])
            self.assertIn("HideWirelessSetupInOOBE", (setup / "okula/unattend.xml").read_text())
            self.assertIn("PC-Empfang", (setup / "okula/unattend.xml").read_text())
            self.assertIn("/Index:2", (setup / "okula/install.cmd").read_text())
        finally:
            sh("umount", str(setup))
        win = self.mounted(3)
        try:
            self.assertTrue((win / plan.target_marker).is_file())
        finally:
            sh("umount", str(win))

    def test_refuses_bios_mode(self):
        iso = windows_iso(self.d)
        plan = winsetup.plan(iso, 1, winunattend.WinOptions())
        with mock.patch.object(wininstall, "EFI_DIR", self.d / "nicht-da"):
            with self.assertRaisesRegex(agentclient.AgentError, "BIOS-Modus"):
                agentclient.install_windows("127.0.0.1", self.key, iso, plan, self.dev, lambda e: None,
                                            threading.Event(), self.port)

    def test_job_phases(self):
        iso = windows_iso(self.d, payload=3_000_000)
        jm = jobs.JobManager()
        results = []
        with mock.patch.object(agent.threading, "Timer", lambda *a, **k: mock.Mock()):
            job = jm.start("dev", "install", self.dev, "Windows",
                           jobs.install_work("127.0.0.1", self.key, self.port, str(iso), 1,
                                             winunattend.WinOptions(), self.dev,
                                             lambda j, b, e: results.append((b, e))))
            for _ in range(300):
                if not job.running:
                    break
                threading.Event().wait(0.1)
        self.assertEqual(job.state, jobs.DONE, job.log)
        self.assertEqual(results, [("0007", None)])
        self.assertTrue(any("Stick JETZT abziehen" in line for line in job.log))


if __name__ == "__main__":
    unittest.main()
