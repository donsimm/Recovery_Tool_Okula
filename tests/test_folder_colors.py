"""Ordner einfärben (I-043): Farbdatei im Ordner, wandert beim Umbenennen/Verschieben mit, zählt nie als Inhalt."""

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from okula_recovery import archive, devices, folder_colors, nasfiles, oslib, transfer


class FolderColorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_set_none(self):
        self.assertIsNone(folder_colors.get_color(self.dir))
        folder_colors.set_color(self.dir, "blau")
        self.assertEqual(folder_colors.get_color(self.dir), "blau")
        self.assertEqual(json.loads((self.dir / folder_colors.FILE).read_text()), {"color": "blau"})
        folder_colors.set_color(self.dir, "rot")
        self.assertEqual(folder_colors.get_color(self.dir), "rot")
        self.assertEqual([p.name for p in self.dir.iterdir()], [folder_colors.FILE])   # kein .tmp übrig
        folder_colors.set_color(self.dir, None)
        self.assertIsNone(folder_colors.get_color(self.dir))
        self.assertFalse((self.dir / folder_colors.FILE).exists())
        folder_colors.set_color(self.dir, None)      # ohne Farbe: kein Fehler

    def test_broken_or_unknown_is_no_color(self):
        path = self.dir / folder_colors.FILE
        for content in ("{kaputt", '{"color": "pink"}', '["rot"]', '{"color": 3}', ""):
            path.write_text(content)
            self.assertIsNone(folder_colors.get_color(self.dir), content)
        path.write_bytes(b"\xff\xfe")
        self.assertIsNone(folder_colors.get_color(self.dir))
        with self.assertRaises(ValueError):
            folder_colors.set_color(self.dir, "pink")

    def test_palette(self):
        self.assertEqual(len(folder_colors.COLORS), 8)
        for c in folder_colors.COLORS:
            self.assertRegex(c.light, r"^#[0-9a-f]{6}$")
            self.assertRegex(c.dark, r"^#[0-9a-f]{6}$")
        self.assertEqual(folder_colors.hex_for("gruen", dark=False), "#2e7d32")
        self.assertEqual(folder_colors.hex_for("gruen", dark=True), "#66bb6a")
        self.assertEqual(folder_colors.hex_for(None, dark=True), "")

    def test_remove_empty(self):
        (self.dir / "A").mkdir()
        folder_colors.set_color(self.dir / "A", "gelb")
        self.assertTrue(folder_colors.only_color_file(self.dir / "A"))
        folder_colors.remove_empty(self.dir / "A")
        self.assertFalse((self.dir / "A").exists())
        (self.dir / "B").mkdir()
        folder_colors.set_color(self.dir / "B", "gelb")
        (self.dir / "B" / "x").write_text("x")
        self.assertFalse(folder_colors.only_color_file(self.dir / "B"))
        with self.assertRaises(OSError):
            folder_colors.remove_empty(self.dir / "B")
        self.assertEqual(folder_colors.get_color(self.dir / "B"), "gelb")

    def test_nas_file_list_hides_color(self):
        (self.dir / "A").mkdir()
        folder_colors.set_color(self.dir / "A", "rot")
        (self.dir / "A" / "datei.txt").write_text("x")
        self.assertEqual([e.name for e in nasfiles.list_dir(self.dir, "A")], ["datei.txt"])


class DeviceFolderColorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "geraete"
        self.store = devices.DeviceStore(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_color_follows_rename_and_move(self):
        self.store.make_folder("", "Kunde A")
        self.store.make_folder("", "Kunden")
        self.store.set_folder_color("Kunde A", "violett")
        self.assertEqual(self.store.folder_color("Kunde A"), "violett")
        self.store.rename_folder("Kunde A", "Kunde Z")
        self.assertEqual(self.store.folder_color("Kunde Z"), "violett")
        self.store.move_folder("Kunde Z", "Kunden")
        self.assertEqual(self.store.folder_color("Kunden/Kunde Z"), "violett")
        # nach Neustart des Tools
        self.assertEqual(devices.DeviceStore(self.base).folder_color("Kunden/Kunde Z"), "violett")
        self.store.set_folder_color("Kunden/Kunde Z", None)
        self.assertIsNone(self.store.folder_color("Kunden/Kunde Z"))
        self.assertIsNone(self.store.folder_color(""))
        self.assertIsNone(self.store.folder_color("gibt es nicht"))
        with self.assertRaises(devices.DeviceError):
            self.store.set_folder_color("gibt es nicht", "rot")

    def test_color_file_is_no_device(self):
        self.store.make_folder("", "Kunde A")
        self.store.set_folder_color("Kunde A", "rot")
        (self.base / folder_colors.FILE).write_text('{"color": "rot"}')   # auch oben ohne Folgen
        store = devices.DeviceStore(self.base)
        self.assertEqual(store.devices, {})
        self.assertEqual(store.folders, ["Kunde A"])
        self.assertEqual(store.in_folder("Kunde A"), [])

    def test_colored_empty_folder_can_be_deleted(self):
        self.store.make_folder("", "Leer")
        self.store.set_folder_color("Leer", "grau")
        self.store.delete_folder("Leer")
        self.assertFalse((self.base / "Leer").exists())
        self.assertNotIn("Leer", self.store.folders)

    def test_colored_folder_with_device_stays(self):
        self.store.make_folder("", "Voll")
        self.store.set_folder_color("Voll", "grau")
        (self.base / "Voll" / "abc.json").write_text(json.dumps({"id": "abc", "name": "PC"}))
        self.store.load()
        with self.assertRaises(devices.DeviceError):
            self.store.delete_folder("Voll")

    def test_export_skips_color_file(self):
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(Path(self.tmp.name) / "data"),
                                          "XDG_CONFIG_HOME": str(Path(self.tmp.name) / "config")}):
            store = devices.DeviceStore()
            store.make_folder("", "Kunde A")
            store.set_folder_color("Kunde A", "blau")
            (store.base / "Kunde A" / "abc.json").write_text(json.dumps({"id": "abc", "name": "PC"}))
            self.assertEqual(transfer.summary_counts(), {"devices": 1, "folders": 1})
            out = Path(self.tmp.name) / "export.okula.zip"
            transfer.export_all(out, include_key=False, include_config=False)
            names = zipfile.ZipFile(out).namelist()
            self.assertNotIn(f"geraete/Kunde A/{folder_colors.FILE}", names)
            self.assertEqual(len(transfer.read_export(out).device_files), 1)   # Import scheitert nicht


class ArchiveFolderColorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_color_follows_rename_and_move(self):
        archive.make_folder(self.root, "", "A")
        archive.make_folder(self.root, "", "C")
        archive.set_folder_color(self.root, "A", "tuerkis")
        archive.rename_folder(self.root, "A", "B")
        self.assertEqual(archive.folder_color(self.root, "B"), "tuerkis")
        self.assertEqual(archive.move_folder(self.root, "B", "C"), "C/B")
        self.assertEqual(archive.folder_color(self.root, "C/B"), "tuerkis")
        archive.set_folder_color(self.root, "C/B", None)
        self.assertIsNone(archive.folder_color(self.root, "C/B"))
        with self.assertRaises(archive.ArchiveError):
            archive.set_folder_color(self.root, "fehlt", "rot")

    def test_color_file_is_no_image(self):
        archive.make_folder(self.root, "", "A")
        archive.set_folder_color(self.root, "A", "orange")
        (self.root / "images").mkdir()
        tree = archive.scan(self.root)
        self.assertEqual(tree.all_images(), [])
        self.assertEqual([(f.name, f.count(), f.folders, f.color) for f in tree.folders], [("A", 0, [], "orange")])

    def test_colored_empty_folder_can_be_deleted(self):
        archive.make_folder(self.root, "", "A")
        archive.set_folder_color(self.root, "A", "rot")
        archive.delete_folder(self.root, "A")
        self.assertFalse((self.root / archive.ARCHIVE_DIR / "A").exists())

    def test_colored_folder_with_subfolder_stays(self):
        archive.make_folder(self.root, "", "A")
        archive.make_folder(self.root, "A", "B")
        archive.set_folder_color(self.root, "A", "rot")
        with self.assertRaises(archive.ArchiveError):
            archive.delete_folder(self.root, "A")

    def test_os_folder(self):
        oslib.ensure_layout(self.root)
        rel = oslib.make_folder(self.root, "Windows", "Kunden")
        oslib.set_folder_color(self.root, rel, "gruen")
        self.assertEqual(oslib.folder_color(self.root, rel), "gruen")
        new = oslib.rename_folder(self.root, rel, "Kunden-ISOs")
        self.assertEqual(oslib.folder_color(self.root, new), "gruen")
        windows = next(f for f in oslib.scan(self.root, inspect_missing=False) if f.rel == "Windows")
        self.assertEqual([(f.name, f.isos, f.color) for f in windows.folders], [("Kunden-ISOs", [], "gruen")])
        self.assertIsNone(windows.color)
        oslib.delete_folder(self.root, new)
        self.assertFalse((self.root / oslib.OS_DIR / new).exists())


if __name__ == "__main__":
    unittest.main()
