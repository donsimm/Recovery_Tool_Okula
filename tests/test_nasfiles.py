import os
import tempfile
import unittest
from pathlib import Path

from okula_recovery import nasfiles


class NasFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "nas"
        self.outside = base / "geheim"
        self.outside.mkdir()
        (self.outside / "wichtig.txt").write_text("nicht löschen")
        (self.root / "images/PC1").mkdir(parents=True)
        (self.root / "images/PC1/sda1.pcl").write_bytes(b"x" * 100)
        (self.root / "readme.txt").write_text("hallo")
        os.symlink(self.outside, self.root / "link-nach-draussen")

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_dirs_first(self):
        names = [(e.name, e.is_dir) for e in nasfiles.list_dir(self.root)]
        self.assertEqual(names, [("images", True), ("link-nach-draussen", False), ("readme.txt", False)])
        self.assertTrue(nasfiles.list_dir(self.root)[1].is_link)

    def test_make_dir_and_rename(self):
        nasfiles.make_dir(self.root, "images", "PC2")
        self.assertTrue((self.root / "images/PC2").is_dir())
        with self.assertRaises(nasfiles.FileError):
            nasfiles.make_dir(self.root, "images", "PC2")
        nasfiles.rename(self.root, "images", "PC2", "PC-Buchhaltung")
        self.assertTrue((self.root / "images/PC-Buchhaltung").is_dir())
        with self.assertRaises(nasfiles.FileError):
            nasfiles.rename(self.root, "images", "PC1", "PC-Buchhaltung")

    def test_invalid_names(self):
        for bad in ("", " ", ".", "..", "a/b", "a\\b", "x:y", "end.", "a*"):
            with self.assertRaises(nasfiles.FileError, msg=bad):
                nasfiles.make_dir(self.root, "", bad)
        # Leerzeichen am Rand werden entfernt (Tippfehler)
        self.assertEqual(nasfiles.make_dir(self.root, "", "  PC3 ").name, "PC3")

    def test_no_escape(self):
        for rel in ("..", "../geheim", "/etc", "images/../.."):
            with self.assertRaises(nasfiles.FileError, msg=rel):
                nasfiles.list_dir(self.root, rel)
        with self.assertRaises(nasfiles.FileError):
            nasfiles.list_dir(self.root, "link-nach-draussen")
        with self.assertRaises(nasfiles.FileError):
            nasfiles.make_dir(self.root, "link-nach-draussen", "x")
        with self.assertRaises(nasfiles.FileError):
            nasfiles.delete(self.root, "link-nach-draussen", ["wichtig.txt"])
        self.assertTrue((self.outside / "wichtig.txt").exists())

    def test_delete_symlink_removes_only_link(self):
        nasfiles.delete(self.root, "", ["link-nach-draussen"])
        self.assertFalse((self.root / "link-nach-draussen").exists())
        self.assertTrue((self.outside / "wichtig.txt").exists())

    def test_delete_folder_recursive_and_measure(self):
        self.assertEqual(nasfiles.measure(self.root, "", ["images", "readme.txt"]), (2, 105))
        self.assertEqual(nasfiles.delete(self.root, "", ["images", "readme.txt"]), 2)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["link-nach-draussen"])

    def test_paths(self):
        self.assertEqual(nasfiles.parent("images/PC1"), "images")
        self.assertEqual(nasfiles.parent("images"), "")
        self.assertEqual(nasfiles.join("", "images"), "images")
        self.assertEqual(nasfiles.join("images", "PC1"), "images/PC1")


if __name__ == "__main__":
    unittest.main()
