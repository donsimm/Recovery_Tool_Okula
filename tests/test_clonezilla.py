import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, clonezilla, imaging
from tests import test_restore as base
from tests.test_restore import SWAP_UUID, can_run, loop_disks, sh, sha


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "disk").write_text("sda\n")
        (self.d / "parts").write_text("sda1 sda2 sda3\n")
        (self.d / "sda-pt.sf").write_text("label: gpt\nunit: sectors\n\n/dev/sda1 : start=2048, size=1000\n")
        (self.d / "sda-pt.parted").write_text("Model: ATA X (scsi)\nDisk /dev/sda: 976773168s\n"
                                              "Sector size (logical/physical): 512B/4096B\n")
        (self.d / "sda-mbr").write_bytes(b"\x33" * 512)
        for suffix in ("ab", "aa", "ac"):
            (self.d / f"sda1.ntfs-ptcl-img.gz.{suffix}").write_bytes(b"x")
        (self.d / "sda2.dd-ptcl-img.zst").write_bytes(b"y")
        (self.d / "swappt-sda3.info").write_text('UUID="abc-123"\nLABEL="SWAP"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_build(self):
        src = clonezilla.build(self.d, "sda")
        self.assertEqual(src["source"]["size"], 976773168 * 512)
        self.assertEqual(src["source"]["pttype"], "gpt")
        s1, s2, s3 = src["steps"]
        self.assertEqual((s1["kind"], s1["variant"], s1["compression"]), ("pcl", "ntfs", "gzip"))
        self.assertEqual([p.name for p in s1["pieces"]],
                         ["sda1.ntfs-ptcl-img.gz.aa", "sda1.ntfs-ptcl-img.gz.ab", "sda1.ntfs-ptcl-img.gz.ac"])
        self.assertEqual((s2["kind"], s2["compression"]), ("dd", "zstd"))
        self.assertEqual(s3, {"kind": "swap", "part": "sda3", "uuid": "abc-123", "label": "SWAP"})
        self.assertEqual(len(src["head"]), 512)  # GPT: nur MBR, keine hidden data

    def test_three_letter_split_order(self):
        for f in self.d.glob("sda1.*"):
            f.unlink()
        for suffix in ("aab", "aaa", "aba"):
            (self.d / f"sda1.ext4-ptcl-img.zst.{suffix}").write_bytes(b"x")
        pieces = clonezilla.build(self.d, "sda")["steps"][0]["pieces"]
        self.assertEqual([p.suffix for p in pieces], [".aaa", ".aab", ".aba"])

    def test_size_fallback_without_parted(self):
        (self.d / "sda-pt.parted").unlink()
        self.assertEqual(clonezilla.build(self.d, "sda")["source"]["size"], (2048 + 1000 + 34) * 512)

    def test_rejects_lvm_old_format_and_missing(self):
        (self.d / "lvm_vg_dev.list").touch()
        with self.assertRaisesRegex(clonezilla.ClonezillaError, "LVM"):
            clonezilla.build(self.d, "sda")
        (self.d / "lvm_vg_dev.list").unlink()
        (self.d / "sda2.dd-ptcl-img.zst").unlink()
        (self.d / "sda2.ntfs-img.aa").touch()
        with self.assertRaisesRegex(clonezilla.ClonezillaError, "altes Clonezilla-Format"):
            clonezilla.build(self.d, "sda")
        (self.d / "sda2.ntfs-img.aa").unlink()
        with self.assertRaisesRegex(clonezilla.ClonezillaError, "sda2"):
            clonezilla.build(self.d, "sda")

    def test_dos_head_includes_hidden_data(self):
        (self.d / "sda-pt.sf").write_text("label: dos\n\n/dev/sda1 : start=2048, size=1000, type=7\n")
        (self.d / "sda-hidden-data-after-mbr").write_bytes(b"\x44" * (2047 * 512))
        head = clonezilla.build(self.d, "sda")["head"]
        self.assertEqual(len(head), 2048 * 512)
        self.assertEqual(head[512:516], b"\x44" * 4)


@unittest.skipUnless(can_run() and shutil.which("gzip") and shutil.which("split"), "braucht root und Loop-Devices")
class ClonezillaRestoreTest(base.RestoreTest):
    """Clonezilla-Image wie ocs-sr savedisk erzeugen und mit dem Tool zurückspielen."""

    def make_clonezilla(self, src: str, label: str) -> Path:
        img = self.dir / "nas" / "2026-03-14-09-img_PC-Empfang"
        img.mkdir(parents=True)
        (img / "disk").write_text("sda\n")
        (img / "parts").write_text("sda1 sda2 sda3\n")
        (img / "clonezilla-img").write_text("Clonezilla\n")
        (img / "sda-pt.sf").write_text(sh("sfdisk", "-d", src).replace(src, "/dev/sda"))
        if shutil.which("parted"):
            (img / "sda-pt.parted").write_text(sh("parted", "-s", src, "unit", "s", "print").replace(src, "/dev/sda"))
        sh("dd", f"if={src}", f"of={img / 'sda-mbr'}", "bs=512", "count=1", "status=none")
        if label == "dos":
            sh("dd", f"if={src}", f"of={img / 'sda-hidden-data-after-mbr'}", "skip=1", "bs=512", "count=2047",
               "status=none")
        # wie Clonezilla: partclone … --output - | gzip -c | split -b …
        subprocess.run(f"partclone.ext4 -c -s {src}p1 -o - -L /dev/null 2>/dev/null | gzip -c | "
                       f"split -a 2 -b 1M - {img}/sda1.ext4-ptcl-img.gz.", shell=True, check=True)
        subprocess.run(f"partclone.dd -s {src}p2 -o - -L /dev/null 2>/dev/null | zstd -q -c > "
                       f"{img}/sda2.dd-ptcl-img.zst", shell=True, check=True)
        blkid = sh("blkid", f"{src}p3").replace(f"{src}p3", "/dev/sda3")
        (img / "swappt-sda3.info").write_text(blkid)
        self.assertGreater(len(list(img.glob("sda1.ext4-ptcl-img.gz.a?"))), 1, "Split hat nicht gegriffen")
        return img

    def roundtrip(self, label):
        src = self.build_source(label)
        dst = self.loop("dst.img", 128)
        img = self.make_clonezilla(src, label)
        port = self.serve()
        events = []
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(dst)), \
                mock.patch.object(agent, "log", lambda m: None):
            agentclient.restore_image("127.0.0.1", self.key, img, dst, events.append, threading.Event(),
                                      port=port, verify=True, source_disk="sda")
        self.assertIn("verify", [e["phase"] for e in events])
        self.assertEqual(sha(f"{dst}p1"), sha(f"{src}p1"), "ext4 nicht bitgleich")
        self.assertEqual(sha(f"{dst}p2"), sha(f"{src}p2"), "Rohpartition nicht bitgleich")
        self.assertEqual(sh("blkid", "-s", "UUID", "-o", "value", f"{dst}p3").strip(), SWAP_UUID)
        with open(dst, "rb") as f:
            self.assertEqual(f.read(440), b"\xebBOOTCODE-OKULA".ljust(440, b"\x90"))
            if label == "dos":
                f.seek(100 * 512)
                self.assertEqual(f.read(190), b"GRUB-CORE-IMG-OKULA" * 10)
        if label == "gpt":
            sh("sfdisk", "--verify", dst)

    def test_corrupt_clonezilla_detected_before_writing(self):
        src = self.build_source("gpt")
        dst = self.loop("dst.img", 128)
        img = self.make_clonezilla(src, "gpt")
        piece = sorted(img.glob("sda1.ext4-ptcl-img.gz.*"))[0]
        data = bytearray(piece.read_bytes())
        data[len(data) // 2] ^= 0xFF
        piece.write_bytes(bytes(data))
        port = self.serve()
        before = sha(dst)
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(dst)), \
                mock.patch.object(agent, "log", lambda m: None):
            with self.assertRaisesRegex(agentclient.AgentError, "beschädigt"):
                agentclient.restore_image("127.0.0.1", self.key, img, dst, lambda e: None, threading.Event(),
                                          port=port, source_disk="sda")
        self.assertEqual(sha(dst), before)

    # Okula-spezifische Tests der Basisklasse hier nicht doppelt ausführen
    test_refuses_smaller_target = None
    test_corrupt_image_detected_before_writing = None


if __name__ == "__main__":
    unittest.main()
