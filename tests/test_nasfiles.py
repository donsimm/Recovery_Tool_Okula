import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

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



class CopyInTest(unittest.TestCase):
    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.nas = self.d / "nas"
        (self.nas / "images").mkdir(parents=True)
        # Clonezilla-Image wie auf einer externen Platte: Ordner mit disk, parts und Teilen
        self.cz = self.d / "usb" / "2026-10-20-12-img"
        self.cz.mkdir(parents=True)
        (self.cz / "disk").write_text("sda\n")
        (self.cz / "parts").write_text("sda1 sda2\n")
        (self.cz / "sda2.ntfs-ptcl-img.zst.aa").write_bytes(os.urandom(3 * 1024 * 1024 + 7))
        (self.cz / "sub").mkdir()
        (self.cz / "sub" / "info.txt").write_text("x")
        os.symlink("/etc/passwd", self.cz / "link")
        self.single = self.d / "usb" / "notiz.txt"
        self.single.write_text("hallo")

    def tearDown(self):
        self.tmp.cleanup()

    def test_copy_folder_and_file(self):
        plan = nasfiles.plan_copy([self.cz, self.single])
        self.assertEqual((plan.files, plan.skipped), (5, ["2026-10-20-12-img/link"]))
        seen = []
        names = nasfiles.copy_in(self.nas, "images", plan, lambda d, t, f: seen.append((d, t)), threading.Event())
        self.assertEqual(names, ["2026-10-20-12-img", "notiz.txt"])
        out = self.nas / "images" / "2026-10-20-12-img"
        self.assertEqual((out / "sda2.ntfs-ptcl-img.zst.aa").read_bytes(), (self.cz / "sda2.ntfs-ptcl-img.zst.aa").read_bytes())
        self.assertEqual((out / "sub" / "info.txt").read_text(), "x")
        self.assertFalse((out / "link").exists())
        self.assertEqual(seen[-1], (plan.bytes, plan.bytes))
        self.assertEqual(os.stat(out / "disk").st_mtime, os.stat(self.cz / "disk").st_mtime)
        # zweites Mal: nichts überschreiben, neuer Name
        names = nasfiles.copy_in(self.nas, "images", nasfiles.plan_copy([self.cz, self.single]),
                                 lambda *a: None, threading.Event())
        self.assertEqual(names, ["2026-10-20-12-img (2)", "notiz (2).txt"])

    def test_cancel_leaves_nothing(self):
        cancel = threading.Event()

        def progress(done, total, current):
            cancel.set()

        with mock.patch.object(nasfiles, "COPY_CHUNK", 1024 * 1024):
            with self.assertRaises(nasfiles.FileError):
                nasfiles.copy_in(self.nas, "", nasfiles.plan_copy([self.cz]), progress, cancel)
        self.assertEqual(sorted(p.name for p in self.nas.iterdir()), ["images"])

    def test_checks_before_copy(self):
        bad = self.d / "usb" / "a:b"
        bad.write_text("x")
        with self.assertRaises(nasfiles.FileError):
            nasfiles.plan_copy([bad])
        with self.assertRaises(nasfiles.FileError):
            nasfiles.plan_copy([self.d / "fehlt"])
        with mock.patch.object(nasfiles.shutil, "disk_usage", return_value=mock.Mock(free=10)):
            with self.assertRaises(nasfiles.FileError):
                nasfiles.copy_in(self.nas, "", nasfiles.plan_copy([self.cz]), lambda *a: None, threading.Event())
        with self.assertRaises(nasfiles.FileError):
            nasfiles.copy_in(self.nas, "../draussen", nasfiles.plan_copy([self.single]), lambda *a: None,
                             threading.Event())


if __name__ == "__main__":
    unittest.main()
