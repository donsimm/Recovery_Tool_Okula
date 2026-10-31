"""Unicode: NFC/NFD, ASCII-Umschrift für Computernamen, unsichtbare Steuerzeichen, doppelte Namen."""

import tempfile
import unicodedata
import unittest
from pathlib import Path

from okula_recovery import archive, devices, inventory_export, linuxsetup, nasfiles, textnorm, winunattend


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


class TextnormTest(unittest.TestCase):
    def test_to_ascii(self):
        self.assertEqual(textnorm.to_ascii("Büro Straße Café Øster Æble Łódź"), "Buero Strasse Cafe Oester Aeble Lodz")
        self.assertEqual(textnorm.to_ascii(nfd("Zürich")), "Zuerich")              # NFD vom Mac
        self.assertEqual(textnorm.to_ascii("北京"), "")

    def test_computer_names(self):
        for name, win, linux in (("Büro_PC_01", "Buero-PC-01", "buero-pc-01"),
                                 (nfd("Büro-PC"), "Buero-PC", "buero-pc"),
                                 ("Café-Zürich", "Cafe-Zuerich", "cafe-zuerich"),
                                 ("Straße-1", "Strasse-1", "strasse-1"),
                                 ("Øster", "Oester", "oester"),
                                 ("PC\u202egnp.exe", "PCgnp-exe", "pcgnp-exe"),
                                 ("Ünterwäsche-Lager-01", "Uenterwaesche-L", "uenterwaesche-lager-01")):
            self.assertEqual(winunattend.computer_name(name), win, name)
            self.assertEqual(linuxsetup.hostname(name), linux, name)

    def test_unsafe_and_clean(self):
        self.assertEqual(textnorm.unsafe_chars("Rechnung\u202efdp.exe"), ["U+202E"])
        self.assertEqual(textnorm.unsafe_chars("PC\u200b01\ufeff"), ["U+200B", "U+FEFF"])
        self.assertEqual(textnorm.unsafe_chars("Büro Zürich (2) – Ü"), [])
        self.assertEqual(textnorm.clean(" PC\u200b-01\u202e\tA\n"), "PC-01 A")
        self.assertEqual(textnorm.clean(nfd("Büro")), "Büro")
        self.assertEqual(len(textnorm.clean(nfd("Büro"))), 4)

    def test_same_name(self):
        self.assertTrue(textnorm.same_name("Büro", nfd("büro")))
        self.assertFalse(textnorm.same_name("Buero", "Büro"))


class NamesOnDiskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_names_strict_existing_untouched(self):
        with self.assertRaisesRegex(nasfiles.FileError, "Steuerzeichen.*U\\+202E"):
            nasfiles.make_dir(self.root, "", "Rechnung\u202efdp.exe")
        made = nasfiles.make_dir(self.root, "", nfd("Büro"))
        self.assertEqual(made.name, "Büro")                                        # als NFC angelegt
        # Ordner, der in NFD auf dem NAS liegt (vom Mac angelegt): bleibt erreichbar und umbenennbar
        (self.root / nfd("Zürich")).mkdir()
        renamed = nasfiles.rename(self.root, "", nfd("Zürich"), "Zürich 2")
        self.assertTrue(renamed.is_dir())

    def test_duplicate_in_other_form_or_case(self):
        (self.root / nfd("Kunde Zürich")).mkdir()                                  # NFD auf dem NAS
        with self.assertRaisesRegex(nasfiles.FileError, "existiert bereits"):
            nasfiles.make_dir(self.root, "", "Kunde Zürich")                       # sieht gleich aus
        with self.assertRaisesRegex(nasfiles.FileError, "existiert bereits"):
            nasfiles.make_dir(self.root, "", "kunde zürich")                       # SMB: Gross/klein egal
        (self.root / "Test").mkdir()
        self.assertTrue(nasfiles.rename(self.root, "", "Test", "TEST").is_dir())    # nur Schreibweise: erlaubt
        with self.assertRaises(nasfiles.FileError):
            nasfiles.rename(self.root, "", "TEST", "kunde ZÜRICH")

    def test_archive_and_devices(self):
        archive.make_folder(self.root, "", "Kunde Ä")
        with self.assertRaises(archive.ArchiveError):
            archive.make_folder(self.root, "", nfd("kunde ä"))
        store = devices.DeviceStore(self.root / "geraete")
        store.make_folder("", "Büro")
        with self.assertRaises(devices.DeviceError):
            store.make_folder("", nfd("büro"))
        with self.assertRaises(nasfiles.FileError):
            store.make_folder("", "A\u202eB")

    def test_device_names(self):
        store = devices.DeviceStore(self.root / "geraete")
        inv = {"dmi": {"product_uuid": "11111111-1111-1111-1111-111111111111"},
               "systems": [{"name": "Windows 11 Pro", "hostname": nfd("BÜRO-PC") + "\u200b"}]}
        dev, _ = store.register("a", "10.0.0.5", "", inv)
        self.assertEqual(dev.name, "BÜRO-PC")
        store.update(dev, name="Empfang\u202e 01 ")
        self.assertEqual(dev.name, "Empfang 01")
        store.update(dev, name="\u200b")                                           # nur unsichtbar = ignoriert
        self.assertEqual(dev.name, "Empfang 01")

    def test_export_file_names(self):
        self.assertEqual(inventory_export.safe_name(nfd("Zürich")), "Zürich")
        stem = inventory_export.safe_name(nfd("ü" * 70))
        self.assertEqual(stem, "ü" * 60)                                          # kein halbes „ü“


if __name__ == "__main__":
    unittest.main()
