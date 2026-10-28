"""Boot-Stick aus ISO auf echten Loop-Geräten (root). FAT32 fehlt im Test-Kernel: dort ext4 statt FAT32."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import isostick, stick, winunattend
from tests.isofixtures import HAVE_TOOLS, linux_iso, windows_iso
from tests.test_restore import can_run, sh


def mkfs_ext4(part, label):
    sh("mkfs.ext4", "-q", "-F", "-L", label, part)


@unittest.skipUnless(can_run() and HAVE_TOOLS, "braucht root, Loop-Devices, genisoimage, wimlib, xorriso")
class IsoStickTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.nas = self.d / "nas"
        (self.nas / "OS").mkdir(parents=True)
        self.loops = []
        self.events = []
        self.patches = [mock.patch.object(isostick, "ISO_ROOT", self.nas)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for dev in self.loops:
            subprocess.run(["umount", "-R", dev + "p1"], capture_output=True)
            subprocess.run(["losetup", "-d", dev], capture_output=True)
        self.tmp.cleanup()

    def stick(self, size_mb=64):
        path = self.d / f"stick{len(self.loops)}.img"
        with open(path, "wb") as f:
            f.truncate(size_mb * 1024 * 1024)
        dev = sh("losetup", "-fP", "--show", str(path)).strip()
        self.loops.append(dev)
        usb = stick.UsbDisk(path=dev, size=size_mb * 1024 * 1024, model="Testlaufwerk", transport="usb")
        p = mock.patch.object(stick, "list_usb_disks", lambda: [usb])
        p.start()
        self.patches.append(p)
        return dev, path

    def emit(self, kind, text):
        self.events.append((kind, text))

    def progress(self):
        return [float(t.split(" ", 1)[0]) for k, t in self.events if k == "PROGRESS"]

    def on_nas(self, src: Path) -> Path:
        dest = self.nas / "OS" / src.name
        shutil.copy(src, dest)
        return dest

    def test_dd_hybrid_iso_written_and_verified(self):
        dev, backing = self.stick()
        with open(backing, "r+b") as f:  # alte GPT-Kopie am Ende muss weg
            f.seek(64 * 1024 * 1024 - 512)
            f.write(b"EFI PART")
        iso = self.on_nas(linux_iso(self.d))
        isostick.prepare(dev, str(iso), "dd", self.emit, check="quick")
        data = backing.read_bytes()
        self.assertEqual(data[:iso.stat().st_size], iso.read_bytes())
        self.assertNotIn(b"EFI PART", data[-1024 * 1024:])
        self.assertEqual(self.events[-1][0], "DONE")
        prog = self.progress()
        self.assertEqual(prog, sorted(prog), "Fortschritt darf nicht zurückspringen")
        self.assertTrue(any("Prüfe Stick" in t for _k, t in self.events), "Lesevergleich fehlt")
        self.assertTrue(any("Schnelltest" in t for _k, t in self.events))

    def test_dd_compressed_image(self):
        dev, backing = self.stick()
        raw = os.urandom(3 * 1024 * 1024)
        img = self.d / "freedos.img"
        img.write_bytes(raw)
        sh("xz", "-1", "-k", str(img))
        target = self.on_nas(Path(str(img) + ".xz"))
        isostick.prepare(dev, str(target), "dd", self.emit, check="none")
        self.assertEqual(backing.read_bytes()[:len(raw)], raw)

    def test_windows_split_unattend_and_bios(self):
        dev, _backing = self.stick(96)
        iso = self.on_nas(windows_iso(self.d, payload=3_000_000))
        unattend = winunattend.build(winunattend.WinOptions())
        with mock.patch.object(isostick, "_format", mkfs_ext4), \
                mock.patch.object(isostick, "FAT32_MAX", 1_000_000), \
                mock.patch.object(isostick, "SPLIT_MB", 1):
            isostick.prepare(dev, str(iso), "windows", self.emit, scheme="mbr", check="none",
                             unattend=unattend)
        self.assertEqual(self.events[-1][0], "DONE", self.events[-3:])
        self.assertTrue(any(k == "WARN" and "gesplittet" in t for k, t in self.events))
        mnt = self.d / "mnt"
        mnt.mkdir()
        sh("mount", dev + "p1", str(mnt))
        try:
            names = {str(p.relative_to(mnt)).lower() for p in mnt.rglob("*")}
            for f in ("bootmgr", "efi/boot/bootx64.efi", "sources/boot.wim", "setup.exe", "autounattend.xml",
                      "sources/install.swm", "sources/install2.swm", "boot/grub/grub.cfg"):
                self.assertIn(f, names)
            self.assertNotIn("sources/install.wim", names)
            self.assertIn("ntldr /bootmgr", (mnt / "boot/grub/grub.cfg").read_text())
            self.assertEqual((mnt / "autounattend.xml").read_text(), unattend)
            # die Teile ergeben wieder das vollständige Abbild mit beiden Editionen
            r = subprocess.run(["wimlib-imagex", "verify", str(mnt / "sources/install.swm"),
                                f"--ref={mnt}/sources/install*.swm"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = subprocess.run(["wimlib-imagex", "info", str(mnt / "sources/install.swm")],
                               capture_output=True, text=True)
            self.assertIn("Image Count:    2", r.stdout)
        finally:
            sh("umount", str(mnt))
        with open(dev, "rb") as f:
            self.assertIn(b"GRUB", f.read(512), "BIOS-Bootcode fehlt im MBR")

    def test_capacity_test_detects_fake_stick(self):
        fake = self.d / "fake.bin"
        size = 256 * 1024 * 1024
        with open(fake, "wb") as f:
            f.truncate(size)
        real_pwrite = os.pwrite
        real_pread = os.pread
        # „gefälschter“ Stick: echte Kapazität 64 MB, alles darüber landet wieder vorne
        with mock.patch.object(isostick.os, "pwrite", lambda fd, data, off: real_pwrite(fd, data, off % (64 << 20))), \
                mock.patch.object(isostick.os, "pread", lambda fd, n, off: real_pread(fd, n, off % (64 << 20))):
            with self.assertRaisesRegex(stick.StickError, "gefälscht"):
                isostick.capacity_test(str(fake), size, lambda f, m: None)
        isostick.capacity_test(str(fake), size, lambda f, m: None)  # echter Stick: in Ordnung

    def test_badblocks_progress(self):
        dev, _backing = self.stick(16)
        seen = []
        isostick.badblocks_test(dev, lambda f, m: seen.append((f, m)))
        self.assertTrue(seen and seen[-1][0] > 0.9, seen[-3:])
        self.assertTrue(any("lesen" in m for _f, m in seen))

    def test_refuses_iso_outside_nas_and_wrong_mode(self):
        dev, _backing = self.stick()
        outside = linux_iso(self.d)
        with self.assertRaisesRegex(stick.StickError, "NAS"):
            isostick.prepare(dev, str(outside), "dd", self.emit)
        with self.assertRaisesRegex(stick.StickError, "passt nicht"):
            isostick.prepare(dev, str(self.on_nas(outside)), "windows", self.emit)

    def test_fat_label(self):
        self.assertEqual(isostick.fat_label({"family": "windows",
                                             "windows": {"product": "Windows 11", "version": "24H2"}}), "WIN11_24H2")
        self.assertEqual(isostick.fat_label({"family": "linux", "volume_id": "Ubuntu 24.04.1 LTS amd64"}),
                         "UBUNTU_24_0")


if __name__ == "__main__":
    unittest.main()
