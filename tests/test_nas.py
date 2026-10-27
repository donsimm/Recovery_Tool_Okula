import os
import tempfile
import unittest
from pathlib import Path

from okula_recovery import nas
from okula_recovery.config import NasConfig


class ListImagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def touch(self, rel, size=0, mtime=None):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\0" * size)
        if mtime:
            os.utime(p, (mtime, mtime))
        return p

    def test_finds_files_by_suffix(self):
        self.touch("pc1/sda.img", 10, mtime=1_000)
        self.touch("pc2/sda1.pcl.zst", 20, mtime=2_000)
        self.touch("notes.txt")
        self.touch("pc1/sda.map")
        self.touch(".hidden.img")
        images = nas.list_images(self.root)
        self.assertEqual([i.name for i in images], ["pc2/sda1.pcl.zst", "pc1/sda.img"])
        self.assertEqual([i.kind for i in images], ["PCL", "IMG"])
        self.assertEqual(images[0].size, 20)

    def test_detects_clonezilla_dir(self):
        self.touch("2026-10-27-pc1/disk")
        self.touch("2026-10-27-pc1/parts")
        self.touch("2026-10-27-pc1/sda1.ntfs-ptcl-img.gz.aa", 100)
        images = nas.list_images(self.root)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].kind, "Clonezilla")
        self.assertEqual(images[0].size, 100)

    def test_respects_max_depth(self):
        self.touch("a/b/c/deep.img")
        self.assertEqual(nas.list_images(self.root, max_depth=2), [])
        self.assertEqual(len(nas.list_images(self.root, max_depth=3)), 1)

    def test_missing_root(self):
        self.assertEqual(nas.list_images(self.root / "nope"), [])


class ConnectionTest(unittest.TestCase):
    def test_no_host(self):
        checks = nas.test_connection(NasConfig(host=""))
        self.assertFalse(checks[0].ok)

    def test_unreachable_port_stops_early(self):
        # Port 9 auf localhost ist praktisch nie offen
        nas.PORTS["test"] = 9
        try:
            checks = nas.test_connection(NasConfig(protocol="test", host="127.0.0.1"), timeout=1)
        finally:
            del nas.PORTS["test"]
        self.assertEqual([c.ok for c in checks], [True, False])


class FormatSizeTest(unittest.TestCase):
    def test_units(self):
        self.assertEqual(nas.format_size(512), "512 B")
        self.assertEqual(nas.format_size(1536), "1.5 KiB")
        self.assertEqual(nas.format_size(500 * 1024**3), "500.0 GiB")


if __name__ == "__main__":
    unittest.main()
