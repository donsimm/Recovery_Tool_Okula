"""USB klonen und formatieren: Regeln und Ende-zu-Ende auf Loop-Devices (als „USB-Datenträger“ ausgegeben)."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import stick, usbtools
from okula_recovery.stick import StickError
from tests.test_restore import can_run, sh


class RulesTest(unittest.TestCase):
    def test_labels_and_commands(self):
        fat = usbtools.FILESYSTEMS["fat32"]
        self.assertEqual(usbtools.clean_label(fat, "Daten Büro 2026!"), "DATEN B_RO ")
        self.assertEqual(usbtools.clean_label(usbtools.FILESYSTEMS["xfs"], "x" * 20), "x" * 12)
        self.assertEqual(usbtools.mkfs_command(fat, "/dev/sdz1", "okula")[-3:], ["-n", "OKULA", "/dev/sdz1"])
        self.assertNotIn("-L", usbtools.mkfs_command(usbtools.FILESYSTEMS["exfat"], "/dev/sdz1", ""))
        self.assertIn("-Q", usbtools.mkfs_command(usbtools.FILESYSTEMS["ntfs"], "/dev/sdz1", "D"))
        self.assertIn("--label=Film", usbtools.mkfs_command(usbtools.FILESYSTEMS["udf"], "/dev/sdz", "Film"))
        self.assertEqual(usbtools.partition_table(usbtools.FILESYSTEMS["ext4"], "gpt"),
                         f"label: gpt\nstart=2048, type={usbtools.GPT_LINUX}\n")
        self.assertEqual(usbtools.partition_table(fat, "mbr"), "label: dos\nstart=2048, type=c\n")
        self.assertIsNone(usbtools.partition_table(fat, "none"))

    def test_smart_plan(self):
        P = usbtools.Part
        gpt = {"label": "gpt"}
        self.assertEqual(usbtools.smart_plan(None, []), (False, "keine Partitionstabelle"))
        self.assertFalse(usbtools.smart_plan(gpt, [P("/dev/a1", 0, 100, "x", "iso9660")])[0])
        self.assertFalse(usbtools.smart_plan(gpt, [P("/dev/a1", 0, 100, "x"), P("/dev/a2", 50, 100, "x")])[0])
        ok = [P("/dev/a1", 1 << 20, 10 << 20, "x", "vfat"), P("/dev/a2", 11 << 20, 5 << 20, "x", "ext4")]
        self.assertEqual(usbtools.smart_plan(gpt, ok), (True, ""))
        self.assertEqual(usbtools.needed_size(gpt, ok, 1 << 30, "smart"), (16 << 20) + 34 * 512)
        self.assertEqual(usbtools.needed_size(gpt, ok, 1 << 30, "raw"), 1 << 30)


    def test_disk_details_from_lsblk(self):
        nested = {"blockdevices": [{"path": "/dev/sdb", "pkname": None, "type": "disk", "size": 16 * 10**9,
                                    "pttype": "gpt", "fstype": None, "label": None, "start": None, "children": [
                                        {"path": "/dev/sdb1", "pkname": "sdb", "type": "part", "size": 200 * 2**20,
                                         "pttype": "gpt", "fstype": "vfat", "label": "BOOT", "start": 2048},
                                        {"path": "/dev/sdb2", "pkname": "sdb", "type": "part", "size": 2 * 2**30,
                                         "pttype": "gpt", "fstype": "ext4", "label": None, "start": 411648}]},
                                   {"path": "/dev/sdc", "type": "disk", "size": 8 * 10**9, "pttype": None,
                                    "fstype": "exfat", "label": "X", "start": None}]}
        flat = {"blockdevices": [{k: v for k, v in nested["blockdevices"][0].items() if k != "children"},
                                 *nested["blockdevices"][0]["children"]]}
        for data in (nested, flat):
            info = usbtools.parse_details(json.dumps(data))["/dev/sdb"]
            self.assertEqual(info.used_end, 411648 * 512 + 2 * 2**30 + 34 * 512)
            self.assertEqual(info.summary(), "GPT: FAT „BOOT“ 0.2 GB · ext4 2.1 GB")
        self.assertEqual(usbtools.parse_details(json.dumps(nested))["/dev/sdc"].summary(),
                         "ohne Partitionstabelle: exFAT")


@unittest.skipUnless(can_run(), "braucht root und Loop-Devices")
class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.loops: list[str] = []
        self.usb: list[stick.UsbDisk] = []
        p = mock.patch.object(stick, "list_usb_disks", lambda: list(self.usb))
        p.start()
        self.addCleanup(p.stop)
        self.events: list[tuple[str, str]] = []

    def tearDown(self):
        subprocess.run(["umount", str(self.d / "mnt")], capture_output=True)
        for dev in self.loops:
            subprocess.run(["losetup", "-d", dev], capture_output=True)
        self.tmp.cleanup()

    def emit(self, kind, text):
        self.events.append((kind, text))

    def loop(self, name: str, mb: int) -> str:
        img = self.d / name
        with open(img, "wb") as f:
            f.truncate(mb * 1024 * 1024)
        dev = sh("losetup", "-fP", "--show", str(img)).strip()
        self.loops.append(dev)
        self.usb.append(stick.UsbDisk(path=dev, size=mb * 1024 * 1024, model=name, transport="usb"))
        return dev

    def part(self, dev, n):
        return stick.partition_path(dev, n)

    def mounted(self, node):
        mnt = self.d / "mnt"
        mnt.mkdir(exist_ok=True)
        sh("mount", "-o", "ro", node, str(mnt))
        self.addCleanup(lambda: subprocess.run(["umount", str(mnt)], capture_output=True))
        return mnt

    def unmount(self):
        sh("umount", str(self.d / "mnt"))

    def make_source(self, label="gpt", mb=64, extended=False):
        src = self.loop("quelle.img", mb)
        if label == "gpt":
            table = "label: gpt\nstart=2048, size=20M, type=U\nsize=20M, type=L\nsize=4M, type=L\n"
        elif extended:
            table = "label: dos\nstart=2048, size=20M, type=c\nsize=30M, type=5\n"
        else:
            table = "label: dos\nstart=2048, size=20M, type=c\nsize=20M, type=83\nsize=4M, type=83\n"
        sh("sfdisk", "-q", src, input=table)
        if extended:
            sh("sfdisk", "-q", "-N", "5", src, input="size=20M, type=83\n")
        usbtools._settle(src)
        p1 = self.part(src, 1)
        p2 = self.part(src, 5 if extended else 2)
        usbtools._wait_for(p2)
        sh("mkfs.vfat", "-F", "32", "-n", "QUELLE", p1)
        tree = self.d / "tree"
        (tree / "Ordner").mkdir(parents=True)
        (tree / "Ordner/Notiz.txt").write_text("Grüezi")
        (tree / "gross.bin").write_bytes(os.urandom(3 * 1024 * 1024))
        sh("mkfs.ext4", "-q", "-F", "-d", str(tree), "-L", "LINUXDATEN", p2)
        raw = os.urandom(1024 * 1024)
        if not extended:
            with open(self.part(src, 3), "r+b") as f:
                f.write(raw)
        # Bootcode im Startbereich (z. B. GRUB) muss mit
        with open(src, "r+b") as f:
            f.seek(300)
            f.write(b"BOOTCODE")
            f.seek(512 * 40)
            f.write(b"GRUB-CORE")
        return src, raw

    def check_clone(self, src, dst, raw, extended=False):
        with open(dst, "rb") as f:
            f.seek(300)
            self.assertEqual(f.read(8), b"BOOTCODE")
            f.seek(512 * 40)
            self.assertEqual(f.read(9), b"GRUB-CORE")
        usbtools._settle(dst)
        p2 = self.part(dst, 5 if extended else 2)
        usbtools._wait_for(p2)
        self.assertEqual(usbtools.probe_fstype(self.part(dst, 1)), "vfat")
        mnt = self.mounted(p2)
        self.assertEqual((mnt / "Ordner/Notiz.txt").read_text(), "Grüezi")
        self.assertEqual((mnt / "gross.bin").read_bytes(), (self.d / "tree/gross.bin").read_bytes())
        self.unmount()
        if not extended:
            with open(self.part(dst, 3), "rb") as f:
                self.assertEqual(f.read(len(raw)), raw)
        self.assertEqual(self.events[-1][0], "DONE")

    def test_smart_gpt_to_larger_target(self):
        src, raw = self.make_source("gpt")
        dst = self.loop("ziel.img", 96)
        usbtools.clone(src, dst, "smart", False, self.emit)
        self.check_clone(src, dst, raw)
        table = json.loads(sh("sfdisk", "-J", dst))["partitiontable"]
        self.assertEqual(table["lastlba"], 96 * 2048 - 34)  # Reserve-GPT am Ende des grösseren Ziels
        self.assertIn("nur belegte Blöcke", " ".join(t for k, t in self.events if k == "PROGRESS"))
        self.assertEqual(subprocess.run(["sfdisk", "--verify", dst], capture_output=True).returncode, 0)

    def test_smart_to_smaller_target_when_partitions_fit(self):
        src, raw = self.make_source("gpt", mb=128)
        dst = self.loop("klein.img", 64)
        with self.assertRaises(StickError):
            usbtools.clone(src, dst, "raw", False, self.emit)
        usbtools.clone(src, dst, "smart", False, self.emit)
        self.check_clone(src, dst, raw)

    def test_smart_dos_with_logical_partition(self):
        src, raw = self.make_source("dos", extended=True)
        dst = self.loop("ziel.img", 64)
        usbtools.clone(src, dst, "smart", False, self.emit)
        self.check_clone(src, dst, raw, extended=True)

    def test_raw_with_verify(self):
        src, raw = self.make_source("dos", mb=48)
        dst = self.loop("ziel.img", 64)
        usbtools.clone(src, dst, "raw", True, self.emit)
        self.check_clone(src, dst, raw)
        self.assertIn("Vergleich ·", " ".join(t for k, t in self.events if k == "PROGRESS"))

    def test_same_disk_refused(self):
        src, _raw = self.make_source("gpt")
        with self.assertRaises(StickError):
            usbtools.clone(src, src, "smart", False, self.emit)

    def test_format_all_available(self):
        dev = self.loop("stick.img", 320)
        expected = {"fat32": "vfat", "exfat": "exfat", "ntfs": "ntfs", "ext4": "ext4", "btrfs": "btrfs",
                    "xfs": "xfs", "f2fs": "f2fs", "ext3": "ext3", "ext2": "ext2", "hfsplus": "hfsplus", "udf": "udf"}
        tested = []
        for key, blkid in expected.items():
            spec = usbtools.FILESYSTEMS[key]
            if not usbtools.available(spec):
                continue
            with self.subTest(fs=key):
                self.events.clear()
                scheme = "gpt" if key in ("ext4", "exfat") else "mbr"
                usbtools.format_disk(dev, key, scheme, "Okula Test", "none", self.emit, (1234, 1234))
                node = self.part(dev, 1)
                self.assertEqual(usbtools.probe_fstype(node), blkid)
                label = subprocess.run(["blkid", "-p", "-o", "value", "-s", "LABEL", node],
                                       capture_output=True, text=True).stdout.strip()
                self.assertEqual(label, usbtools.clean_label(spec, "Okula Test"))
                self.assertEqual(json.loads(sh("sfdisk", "-J", dev))["partitiontable"]["label"],
                                 "gpt" if scheme == "gpt" else "dos")
                no_kernel_fs = any(k == "WARN" and "Besitzer" in t for k, t in self.events)  # z. B. f2fs im Container
                if spec.linux and not no_kernel_fs:
                    st = os.stat(self.mounted(node))
                    self.assertEqual((st.st_uid, st.st_gid), (1234, 1234))
                    self.unmount()
                tested.append(key)
        self.assertGreaterEqual(len(tested), 5, tested)

    def test_format_without_table_zero_and_wipe(self):
        dev = self.loop("stick.img", 64)
        usbtools.format_disk(dev, "fat32", "none", "ganz", "zero", self.emit)
        self.assertEqual(usbtools.probe_fstype(dev), "vfat")
        self.assertIn("Nullen", " ".join(t for k, t in self.events if k == "PROGRESS"))
        usbtools.format_disk(dev, "none", "mbr", "", "none", self.emit)
        self.assertEqual(usbtools.probe_fstype(dev), "")
        with self.assertRaises(StickError):
            usbtools.format_disk(dev, "xfs", "mbr", "", "none", self.emit)  # zu klein für XFS

    def test_fat16_size_limit_and_mbr_limit(self):
        dev = self.loop("stick.img", 64)
        usbtools.format_disk(dev, "fat16", "mbr", "alt", "quick", self.emit)
        self.assertEqual(usbtools.probe_fstype(self.part(dev, 1)), "vfat")
        with mock.patch.object(usbtools, "device_size", return_value=3 * 1024**4):
            with self.assertRaises(StickError):
                usbtools.format_disk(dev, "exfat", "mbr", "", "none", self.emit)


if __name__ == "__main__":
    unittest.main()
