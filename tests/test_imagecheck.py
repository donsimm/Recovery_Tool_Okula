"""Image prüfen (I-007): Okula- und Clonezilla-Images auf dem Server prüfen, Ergebnis speichern und anzeigen."""

import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, archive, imagecheck, imaging, nas
from tests import test_clonezilla, test_restore
from tests.test_restore import can_run, loop_disks


def make_okula_image(folder: Path, files: dict[str, bytes], demo: bool = False) -> Path:
    """Okula-Image mit gültigem okula-image.json (SHA256 je Datei) – ohne Agent."""
    folder.mkdir(parents=True)
    entries = []
    for name, data in files.items():
        (folder / name).write_bytes(data)
        entries.append({"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    meta = {"format": "okula-image", "version": 1, "machine": "PC-01", "completed": "2026-10-31T10:00:00",
            "disk": {"name": "sda", "model": "Test-SSD", "size": 10**9}, "files": entries,
            "source": {"device_id": "dev1"}}
    if demo:
        meta["demo"] = True
    (folder / agentclient.IMAGE_META).write_text(json.dumps(meta))
    return folder


def flip_byte(path: Path, offset: int = 10) -> None:
    with open(path, "r+b") as f:
        f.seek(offset)
        b = f.read(1)
        f.seek(offset)
        f.write(bytes([b[0] ^ 0xFF]))


FILES = {"sda.sfdisk": b"label: gpt\n", "sda-head.img": os.urandom(4096), "sda1.ext4.pcl.zst": os.urandom(300_000)}


class CheckOkulaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ok_then_broken_with_file(self):
        img = make_okula_image(self.root / "images" / "PC-01" / "2026-10-31_sda", FILES)
        seen = []
        res = imagecheck.check(img, lambda f, n: seen.append((f, n)))
        self.assertEqual(res["status"], imagecheck.OK)
        self.assertEqual(seen[-1][0], 1.0)
        flip_byte(img / "sda1.ext4.pcl.zst")
        res = imagecheck.check(img)
        self.assertEqual((res["status"], res["file"]), (imagecheck.BROKEN, "sda1.ext4.pcl.zst"))
        self.assertIn("Prüfsumme", res["message"])

    def test_missing_file_and_uncheckable(self):
        img = make_okula_image(self.root / "a", FILES)
        (img / "sda-head.img").unlink()
        res = imagecheck.check(img)
        self.assertEqual((res["status"], res["file"]), (imagecheck.BROKEN, "sda-head.img"))
        raw = self.root / "alt.img"
        raw.write_bytes(b"x" * 100)
        self.assertEqual(imagecheck.check(raw)["status"], imagecheck.UNCHECKABLE)

    def test_cancel(self):
        img = make_okula_image(self.root / "a", FILES)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(imagecheck.Cancelled):
            imagecheck.check(img, cancel=cancel)
        self.assertIsNone(imagecheck.load(img))                     # nichts gespeichert

    def test_result_saved_and_survives_restart(self):
        img = make_okula_image(self.root / "images" / "PC-01" / "2026-10-31_sda", FILES)
        before = {n: (img / n).read_bytes() for n in FILES}
        meta_before = json.loads((img / agentclient.IMAGE_META).read_text())
        res = imagecheck.check(img)
        imagecheck.save(img, res)
        # nur das Feld „check“ kommt dazu, Image-Dateien und Prüfsummen bleiben gleich
        meta = json.loads((img / agentclient.IMAGE_META).read_text())
        self.assertEqual(meta.pop("check")["status"], imagecheck.OK)
        self.assertEqual(meta, meta_before)
        self.assertEqual({n: (img / n).read_bytes() for n in FILES}, before)
        # „Neustart“: frisch einlesen wie die Image-Liste
        info = archive.scan(self.root).all_images()[0]
        self.assertEqual(info.check["status"], imagecheck.OK)
        self.assertIn("✔", imagecheck.cell(info.check))
        self.assertIn(imagecheck.short_date(info.check), imagecheck.cell(info.check))

    def test_folder_run_and_summary(self):
        a = make_okula_image(self.root / "Archiv" / "Zürich" / "a", FILES)
        b = make_okula_image(self.root / "Archiv" / "Zürich" / "Buchhaltung" / "b", FILES)
        c = make_okula_image(self.root / "Archiv" / "Zürich" / "c", FILES)
        flip_byte(c / "sda-head.img")
        tree = archive.scan(self.root)
        folder = tree.folders[0]
        paths = [str(i.path) for i in imagecheck_images(folder)]
        self.assertEqual(len(paths), 3)                                     # mit Unterordnern
        progress, got = [], {}
        results, cancelled = imagecheck.run(paths, lambda *a: progress.append(a), lambda p, r: got.update({p: r}),
                                            threading.Event())
        self.assertFalse(cancelled)
        self.assertEqual(imagecheck.summary(results), "3 Images geprüft: 2 ✔, 1 ✖")
        self.assertEqual(got[str(c)]["status"], imagecheck.BROKEN)
        self.assertTrue(all(0 <= p[2] <= 1 for p in progress))
        self.assertEqual(imagecheck.load(b)["status"], imagecheck.OK)
        self.assertEqual(imagecheck.load(a)["status"], imagecheck.OK)
        # Abbrechen mitten drin: Rest wird nicht geprüft
        cancel = threading.Event()
        results, cancelled = imagecheck.run(paths, lambda *a: cancel.set(), lambda p, r: None, cancel)
        self.assertTrue(cancelled)
        self.assertIn("abgebrochen", imagecheck.summary(results, cancelled))

    def test_display_texts(self):
        self.assertEqual(imagecheck.cell(None), "")
        self.assertIn("Noch nie geprüft", imagecheck.tooltip(None))
        broken = {"status": "broken", "date": "2026-10-31T10:00:00", "file": "sda1.ext4.pcl.zst",
                  "message": "Image beschädigt: Prüfsumme von sda1.ext4.pcl.zst stimmt nicht"}
        self.assertIn("✖ beschädigt", imagecheck.cell(broken))
        self.assertIn("#c62828", imagecheck.cell(broken))
        self.assertIn("Datei: sda1.ext4.pcl.zst", imagecheck.tooltip(broken))
        self.assertIn("beschädigt (sda1.ext4.pcl.zst)", imagecheck.warning(broken))
        self.assertIn("31.10.2026", imagecheck.warning(broken))
        self.assertEqual(imagecheck.warning({"status": "ok", "date": "2026-10-31T10:00:00"}), "")
        self.assertEqual(imagecheck.summary([]), "0 Images geprüft: 0 ✔, 0 ✖")


def imagecheck_images(folder: archive.Folder) -> list[nas.ImageInfo]:
    out = list(folder.images)
    for sub in folder.folders:
        out += imagecheck_images(sub)
    return out


@unittest.skipUnless(can_run(), "braucht root und Loop-Devices")
class CheckRealImagesTest(unittest.TestCase):
    """Echte Images: Okula-Image über den Agent von einer Loop-Disk, Clonezilla-Image wie ocs-sr savedisk."""

    # Helfer der Restore-Tests übernehmen (ohne deren Tests nochmals laufen zu lassen)
    setUp = test_restore.RestoreTest.setUp
    tearDown = test_restore.RestoreTest.tearDown
    loop = test_restore.RestoreTest.loop
    build_source = test_restore.RestoreTest.build_source
    serve = test_restore.RestoreTest.serve
    make_clonezilla = test_clonezilla.ClonezillaRestoreTest.make_clonezilla

    def test_okula_image_from_loop_disk(self):
        src = self.build_source("gpt")
        port = self.serve()
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(src)), \
                mock.patch.object(agent, "log", lambda *a, **k: None):
            image = Path(agentclient.create_image("127.0.0.1", self.key, src, self.dir / "nas", "test",
                                                  lambda e: None, threading.Event(), port=port))
        self.assertEqual(imagecheck.check(image)["status"], imagecheck.OK)
        part = next(p for p in image.iterdir() if ".pcl." in p.name)
        flip_byte(part, part.stat().st_size // 2)
        res = imagecheck.check(image)
        self.assertEqual((res["status"], res["file"]), (imagecheck.BROKEN, part.name))

    def test_clonezilla_image(self):
        src = self.build_source("dos")
        img = self.make_clonezilla(src, "dos")
        res = imagecheck.check(img)
        self.assertEqual(res["status"], imagecheck.OK, res)
        imagecheck.save(img, res)
        self.assertEqual(json.loads((img / nas.CHECK_FILE).read_text())["status"], imagecheck.OK)
        self.assertEqual(nas.image_at(img, img.parent).check["status"], imagecheck.OK)
        piece = sorted(img.glob("sda1.ext4-ptcl-img.gz.a?"))[0]
        flip_byte(piece, 5000)
        res = imagecheck.check(img)
        self.assertEqual(res["status"], imagecheck.BROKEN, res)
        self.assertEqual(res["file"], "sda1")


if __name__ == "__main__":
    unittest.main()
