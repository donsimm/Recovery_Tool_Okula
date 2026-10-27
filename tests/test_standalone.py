"""Restore-Stick: Bildschirmführung, Stick-Layer, Layout und echter lokaler Restore."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, imaging, standalone, stick
from tests import test_clonezilla as cz
from tests import test_restore as base

DISK_OK = {"name": "sda", "path": "/dev/sda", "size": 1000 * 1000**3, "model": "Crucial MX500", "fstype": "",
           "partitions": [{"name": "sda1", "fstype": "ntfs", "label": "Daten", "size": 1, "mounted": False}]}
DISK_SMALL = {"name": "sdb", "path": "/dev/sdb", "size": 120 * 1000**3, "model": "Kingston", "fstype": "",
              "partitions": []}
SRC = {"source": {"size": 500 * 1000**3, "model": "SSD", "pttype": "gpt", "partitions": [{"name": "nvme0n1p1"}]},
       "format": "okula", "steps": [], "verify": lambda progress, cancel: None}


class FakeUi(standalone.Ui):
    def __init__(self, answers, console):
        super().__init__(console, read=self._read)
        self.answers = list(answers)
        self.lines = []
        self.write = self.lines.append

    def _read(self, prompt):
        self.lines.append(prompt)
        return self.answers.pop(0)


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.console = str(Path(self.tmp.name) / "tty")
        Path(self.console).touch()
        self.root = Path(self.tmp.name) / "data"
        (self.root / "image").mkdir(parents=True)
        (self.root / "okula-restore.json").write_text(json.dumps({"label": "PC-Buchhaltung", "created": "x"}))
        self.patches = [mock.patch.object(imaging, "list_disks", lambda: [DISK_SMALL, DISK_OK]),
                        mock.patch.object(standalone, "load", lambda root: (json.loads(
                            (root / "okula-restore.json").read_text()), dict(SRC)))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_flow(self, answers):
        ui = FakeUi(answers, self.console)
        powers, restored = [], []
        with mock.patch.object(imaging, "restore_local", lambda path, src, log, report: restored.append(path)):
            standalone.run(ui, self.root, powers.append)
        return ui, powers, restored

    def test_full_flow_with_confirmation(self):
        # 1 = zu klein → abgelehnt; 2 mit falschem Namen → nichts; 2 mit richtigem Namen → zurückspielen
        ui, powers, restored = self.run_flow(["1", "2", "sdb", "2", "sda", ""])
        text = "\n".join(ui.lines)
        self.assertIn("zu klein", text)
        self.assertIn("Nicht bestätigt – nichts geändert.", text)
        self.assertIn("ACHTUNG: Alle Daten auf sda", text)
        self.assertEqual(restored, ["/dev/sda"])
        self.assertEqual(powers, ["poweroff"])
        self.assertIn("» Image auf sda zurückgespielt", Path(self.console).read_text())

    def test_abort_changes_nothing(self):
        ui, powers, restored = self.run_flow(["q", ""])
        self.assertEqual(restored, [])
        self.assertEqual(powers, ["poweroff"])

    def test_reboot_and_error_retry(self):
        calls = iter([imaging.ImagingError("Lesefehler"), None])

        def flaky(path, src, log, report):
            e = next(calls)
            if e:
                raise e

        ui = FakeUi(["2", "sda", "", "2", "sda", "n"], self.console)
        powers = []
        with mock.patch.object(imaging, "restore_local", flaky):
            standalone.run(ui, self.root, powers.append)
        self.assertIn("Fehler: Lesefehler", "\n".join(ui.lines))
        self.assertEqual(powers, ["reboot"])


class StickLayoutTest(unittest.TestCase):
    def test_restore_tree(self):
        with tempfile.TemporaryDirectory() as d:
            tree = Path(d) / "tree"
            stick.build_agent_tree(tree, mode="restore")
            units = tree / "etc/systemd/system"
            self.assertEqual(os.readlink(units / "getty@tty1.service"), "/dev/null")
            self.assertTrue((units / "multi-user.target.wants/okula-restore.service").is_symlink())
            self.assertFalse((units / "okula-agent.service").exists())
            self.assertFalse((tree / "etc/okula-agent.key").exists())
            self.assertIn("Restore-Stick", (tree / "etc/issue").read_text())
            app = tree / "opt/okula-recovery"
            self.assertEqual(subprocess.run(["sh", "-n", str(app / "start-restore.sh")]).returncode, 0)
            r = subprocess.run(["python3", "-c", "import okula_recovery.standalone"], cwd=app,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_grub_restore_title_and_label(self):
        cfg = stick.grub_cfg("vmlinuz", "initrd.img", stick.RESTORE_LABEL, "Okula Restore-Stick")
        self.assertIn('menuentry "Okula Restore-Stick" {', cfg)
        self.assertIn("--set=root OKULA-REST", cfg)
        self.assertTrue(cfg.isascii())
        self.assertLessEqual(len(stick.RESTORE_LABEL), 11)

    def test_layout_and_size_check(self):
        mib, table = stick.restore_layout(1_500_000_000, 40 * 1000**3, 64 * 1000**3)
        self.assertGreaterEqual(mib, 1536)
        self.assertIn(f"size={mib}MiB, type=c, bootable", table)
        self.assertIn("start=, type=83", table)
        with self.assertRaisesRegex(stick.StickError, "zu klein"):
            stick.restore_layout(1_500_000_000, 40 * 1000**3, 32 * 1000**3)
        self.assertEqual(stick.partition_path("/dev/sdb", 2), "/dev/sdb2")
        self.assertEqual(stick.partition_path("/dev/nvme0n1", 2), "/dev/nvme0n1p2")

    def test_image_must_be_under_mnt(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(stick.StickError, "unter /mnt"):
                stick.check_image(d, None)
        with self.assertRaisesRegex(stick.StickError, "unter /mnt"):
            stick.check_image("/mnt/../etc", None)


@unittest.skipUnless(base.can_run(), "braucht root und Loop-Devices")
class LocalRestoreTest(cz.ClonezillaRestoreTest):
    """Image wie vom Tool auf die Datenpartition gelegt, dann wie auf dem Stick zurückgespielt."""

    def stick_restore(self, image: Path, dst: str, source_disk=None):
        data = self.dir / "stick-data"
        src_for_cfg = agentclient.image_source(image, source_disk)
        stick.install_image(data, image, src_for_cfg, source_disk, lambda d, t: None)
        cfg, src = standalone.load(data)
        self.assertEqual(cfg["image_name"], image.name)
        tty = self.dir / "tty"
        tty.touch()
        ui = standalone.Ui(str(tty), read=lambda p: "", write=lambda t: None)
        with mock.patch.object(imaging, "list_disks", lambda: base.loop_disks(dst)):
            disk = next(d for d in imaging.list_disks() if d["path"] == dst)
            standalone.restore(ui, src, disk)
        text = tty.read_text()
        self.assertIn("» Image ist in Ordnung", text)
        self.assertIn("zurückgespielt", text)

    def check(self, src, dst, label):
        self.assertEqual(base.sha(f"{dst}p1"), base.sha(f"{src}p1"), "ext4 nicht bitgleich")
        self.assertEqual(base.sha(f"{dst}p2"), base.sha(f"{src}p2"))
        self.assertEqual(base.sh("blkid", "-s", "UUID", "-o", "value", f"{dst}p3").strip(), base.SWAP_UUID)

    def test_okula_image_from_stick(self):
        src = self.build_source("gpt")
        dst = self.loop("dst.img", 128)
        port = self.serve()
        with mock.patch.object(imaging, "list_disks", lambda: base.loop_disks(src)), \
                mock.patch.object(agent, "log", lambda *a, **k: None):
            image = agentclient.create_image("127.0.0.1", self.key, src, self.dir / "nas", "PC",
                                             lambda e: None, threading.Event(), port=port)
        self.stick_restore(image, dst)
        self.check(src, dst, "gpt")

    def test_clonezilla_image_from_stick(self):
        src = self.build_source("dos")
        dst = self.loop("dst.img", 128)
        image = self.make_clonezilla(src, "dos")
        self.stick_restore(image, dst, "sda")
        self.check(src, dst, "dos")

    test_gpt = test_dos = test_corrupt_clonezilla_detected_before_writing = None
    test_verify_with_debian_user_path = test_verify_falls_back_without_chkimg = None
    test_console_shows_tool_verification_then_restore = None


if __name__ == "__main__":
    unittest.main()
