import json
import os
import tempfile
import unittest
from pathlib import Path

from okula_recovery import archive


def okula_image(path: Path, machine: str, completed: str) -> Path:
    path.mkdir(parents=True)
    (path / "okula-image.json").write_text(json.dumps({
        "format": "okula-image", "version": 1, "machine": machine, "completed": completed,
        "disk": {"model": "SSD"}, "files": [{"name": "a", "size": 10}]}))
    return path


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "nas"
        self.img1 = okula_image(self.root / "images/PC-Buchhaltung/2026-10-27_1040_sda", "PC-Buchhaltung",
                                "2026-10-27T10:40:00")
        self.img2 = okula_image(self.root / "images/PC-Empfang/2026-10-28_0900_nvme0n1", "PC-Empfang",
                                "2026-10-28T09:00:00")
        cz = self.root / "2026-03-14-img_Server"
        cz.mkdir()
        (cz / "disk").write_text("sda")
        (cz / "parts").write_text("sda1")
        os.utime(cz, (1710000000, 1710000000))  # März 2024 – älter als die Okula-Images

    def tearDown(self):
        self.tmp.cleanup()

    def test_initially_everything_unsorted_newest_first(self):
        tree = archive.scan(self.root)
        self.assertEqual(tree.folders, [])
        self.assertEqual([i.path.name for i in tree.unsorted][:2],
                         ["2026-10-28_0900_nvme0n1", "2026-10-27_1040_sda"])
        self.assertEqual(len(tree.unsorted), 3)

    def test_folders_max_three_levels(self):
        archive.make_folder(self.root, "", "Kunde A")
        archive.make_folder(self.root, "Kunde A", "Zürich")
        archive.make_folder(self.root, "Kunde A/Zürich", "Buchhaltung")
        with self.assertRaisesRegex(archive.ArchiveError, "3 Ebenen"):
            archive.make_folder(self.root, "Kunde A/Zürich/Buchhaltung", "zu tief")
        with self.assertRaisesRegex(archive.ArchiveError, "existiert"):
            archive.make_folder(self.root, "", "Kunde A")
        tree = archive.scan(self.root)
        self.assertEqual(tree.folders[0].folders[0].folders[0].rel, "Kunde A/Zürich/Buchhaltung")

    def test_move_image_into_folder_and_back(self):
        archive.make_folder(self.root, "", "Kunde A")
        archive.make_folder(self.root, "Kunde A", "Zürich")
        moved = archive.move_image(self.root, self.img1, "Kunde A/Zürich")
        self.assertEqual(moved, self.root / "Archiv/Kunde A/Zürich/2026-10-27_1040_sda")
        self.assertFalse((self.root / "images/PC-Buchhaltung").exists(), "leerer Maschinenordner bleibt liegen")
        tree = archive.scan(self.root)
        zurich = tree.folders[0].folders[0]
        self.assertEqual([i.name for i in zurich.images], ["PC-Buchhaltung – 2026-10-27_1040_sda  (SSD)"])
        self.assertEqual(len(tree.unsorted), 2)
        self.assertEqual(len(tree.all_images()), 3)
        back = archive.move_image(self.root, moved, None)
        self.assertEqual(back, self.root / "images/2026-10-27_1040_sda")
        self.assertEqual(len(archive.scan(self.root).unsorted), 3)
        names = [i.name for i in archive.scan(self.root).unsorted]
        self.assertIn("PC-Buchhaltung – 2026-10-27_1040_sda  (SSD)", names)  # Gerätename bleibt sichtbar

    def test_name_conflicts_get_suffix(self):
        archive.make_folder(self.root, "", "A")
        twin = okula_image(self.root / "images/other/2026-10-27_1040_sda", "X", "2026-01-01T00:00:00")
        archive.move_image(self.root, self.img1, "A")
        second = archive.move_image(self.root, twin, "A")
        self.assertEqual(second.name, "2026-10-27_1040_sda (2)")

    def test_move_folder_rules(self):
        for parent, name in (("", "A"), ("A", "B"), ("", "C"), ("C", "D"), ("C/D", "E")):
            archive.make_folder(self.root, parent, name)
        self.assertEqual(archive.move_folder(self.root, "A/B", "C"), "C/B")
        with self.assertRaisesRegex(archive.ArchiveError, "in sich selbst"):
            archive.move_folder(self.root, "C", "C/D")
        with self.assertRaisesRegex(archive.ArchiveError, "3 Ebenen"):
            archive.move_folder(self.root, "C", "A")  # C hat 3 Ebenen (C/D/E) → unter A wären es 4
        archive.move_image(self.root, self.img1, "C/D/E")
        self.assertEqual(archive.move_folder(self.root, "C/D/E", ""), "E")
        self.assertTrue((self.root / "Archiv/E/2026-10-27_1040_sda").is_dir())

    def test_rename_and_delete_only_empty(self):
        archive.make_folder(self.root, "", "Kunde")
        self.assertEqual(archive.rename_folder(self.root, "Kunde", "Kunde B"), "Kunde B")
        archive.move_image(self.root, self.img2, "Kunde B")
        with self.assertRaisesRegex(archive.ArchiveError, "nicht leer"):
            archive.delete_folder(self.root, "Kunde B")
        archive.move_image(self.root, self.root / "Archiv/Kunde B/2026-10-28_0900_nvme0n1", None)
        archive.delete_folder(self.root, "Kunde B")
        self.assertEqual(archive.scan(self.root).folders, [])

    def test_rejects_escape_and_non_images(self):
        archive.make_folder(self.root, "", "A")
        outside = Path(self.tmp.name) / "geheim"
        outside.mkdir()
        os.symlink(outside, self.root / "Archiv/Link")
        with self.assertRaises(Exception):
            archive.make_folder(self.root, "Link", "x")
        with self.assertRaises(Exception):
            archive.move_image(self.root, self.img1, "Link")
        with self.assertRaisesRegex(archive.ArchiveError, "nicht auf dem NAS"):
            archive.move_image(self.root, outside, "A")
        with self.assertRaisesRegex(archive.ArchiveError, "kein Image"):
            archive.move_image(self.root, self.root / "images", "A")
        with self.assertRaises(Exception):
            archive.make_folder(self.root, "../..", "x")
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
