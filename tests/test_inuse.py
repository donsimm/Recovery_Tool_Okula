"""B-026: Image/ISO/Backup, das ein laufender Auftrag liest, lässt sich nicht löschen oder verschieben.

Gemeinsame Prüfung jobs.JobManager.in_use (ohne GTK); die Stellen in der Oberfläche (ui.py) nachgebildet,
sofern PyGObject installiert ist.
"""

import os
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import jobs

ROOT = "/mnt/nas"
IMAGE = f"{ROOT}/Archiv/Kunden/Meier-2026-11-25"


def start(jm: jobs.JobManager, source: str = IMAGE, device: str = "dev1", disk: str = "/dev/sda"):
    """Auftrag, der läuft, bis das zurückgegebene Event gesetzt wird."""
    release = threading.Event()
    job = jm.start(device, "restore", disk, "Zurückspielen Meier → /dev/sda",
                   lambda job, jm: release.wait(5) and "", source=source)
    return job, release


def wait_done(job: jobs.Job) -> None:
    for _ in range(200):
        if not job.running:
            return
        threading.Event().wait(0.01)
    raise AssertionError("Auftrag endet nicht")


class InUseTest(unittest.TestCase):
    def setUp(self):
        self.jm = jobs.JobManager()

    def test_running_job_blocks_file_and_parent_folders(self):
        job, release = start(self.jm)
        try:
            self.assertEqual(job.source, IMAGE)
            self.assertIs(self.jm.in_use(IMAGE), job)                       # das Image selbst
            self.assertIs(self.jm.in_use(IMAGE + "/"), job)                 # Schreibweise egal
            self.assertIs(self.jm.in_use(f"{ROOT}/Archiv/Kunden"), job)     # Ordner, in dem es liegt
            self.assertIs(self.jm.in_use(f"{ROOT}/Archiv"), job)
            self.assertIs(self.jm.in_use(f"{IMAGE}/sda1.ntfs-ptcl-img.gz"), job)   # Datei im Image-Ordner
            self.assertIs(self.jm.in_use("/tmp/x", Path(IMAGE)), job)       # einer von mehreren Pfaden
        finally:
            release.set()
        wait_done(job)

    def test_other_paths_are_free(self):
        job, release = start(self.jm)
        try:
            self.assertIsNone(self.jm.in_use(f"{ROOT}/Archiv/Kunden/Meier-2026-11-2"))   # gleicher Anfang
            self.assertIsNone(self.jm.in_use(f"{IMAGE}-alt"))
            self.assertIsNone(self.jm.in_use(f"{ROOT}/Archiv/Andere"))
            self.assertIsNone(self.jm.in_use(""))
            self.assertIsNone(self.jm.in_use())
        finally:
            release.set()
        wait_done(job)

    def test_finished_job_releases(self):
        job, release = start(self.jm)
        release.set()
        wait_done(job)
        self.assertEqual(job.state, jobs.DONE)
        self.assertIsNone(self.jm.in_use(IMAGE))
        self.assertEqual(self.jm.busy_paths(), [])

    def test_job_without_source_blocks_nothing(self):
        release = threading.Event()
        job = self.jm.start("dev1", "image", "/dev/sda", "Disk-Image", lambda j, m: release.wait(5) and "")
        try:
            self.assertEqual(job.source, "")
            self.assertIsNone(self.jm.in_use(ROOT))
        finally:
            release.set()
        wait_done(job)

    def test_message(self):
        job, release = start(self.jm)
        release.set()
        wait_done(job)
        self.assertEqual(jobs.busy_message("„Meier“", job),
                         "„Meier“ wird gerade von „Zurückspielen Meier → /dev/sda“ verwendet – "
                         "erst nach Ende löschen/verschieben.")


# ---------- Oberfläche (nachgebildet) ----------

def load_ui():
    try:
        from okula_recovery import ui
    except Exception:          # kein PyGObject/GTK installiert
        return None
    return ui


ui = load_ui()


def make_window(jm: jobs.JobManager):
    fake = types.SimpleNamespace()
    for name in ("_in_use", "delete_old_demo_images", "drop", "_confirm_delete", "delete_backup"):
        setattr(fake, name, getattr(ui.MainWindow, name).__get__(fake))
    fake.jobs = jm
    fake.ops, fake.statuses = [], []
    fake._nas_root = lambda: ROOT
    fake.root_of = lambda _path: ROOT
    fake.status = fake.statuses.append
    fake._archive_op = lambda op, msg: fake.ops.append((op, msg))
    fake._file_op = lambda op, msg: fake.ops.append((op, msg))
    return fake


@unittest.skipIf(ui is None, "PyGObject/GTK nicht installiert")
class UiInUseTest(unittest.TestCase):
    def setUp(self):
        self.jm = jobs.JobManager()
        self.job, self.release = start(self.jm)
        self.win = make_window(self.jm)
        self.errors = []
        patcher = mock.patch.object(ui, "confirm_error", lambda _parent, text: self.errors.append(text))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.release.set()
        wait_done(self.job)

    def test_drop_image_and_folder_blocked(self):
        self.win.drop("image", "archive", "Kunden", IMAGE, "Meier", "unsorted", "")
        self.win.drop("image", "archive", "Kunden", IMAGE, "Meier", "archive", "Andere")
        self.win.drop("folder", "archive", "Kunden", "", "Kunden", "archive", "Andere")
        self.assertEqual(self.win.ops, [])
        self.assertEqual(len(self.errors), 3)
        self.assertIn("wird gerade von „Zurückspielen Meier → /dev/sda“ verwendet", self.errors[0])
        self.assertTrue(self.errors[2].startswith("Ordner „Kunden“"))

    def test_drop_other_image_allowed(self):
        self.win.drop("image", "archive", "Andere", f"{ROOT}/Archiv/Andere/Img", "Img", "archive", "Kunden")
        self.assertEqual(len(self.win.ops), 1)
        self.assertEqual(self.errors, [])

    def test_delete_blocked_before_asking(self):
        with mock.patch.object(ui, "run_async") as measure:
            self.win._confirm_delete(ROOT, "Archiv/Kunden", [os.path.basename(IMAGE)])
            self.win._confirm_delete(ROOT, "Archiv", ["Kunden"])                     # übergeordneter Ordner
        measure.assert_not_called()
        self.assertEqual(len(self.errors), 2)
        self.assertEqual(self.win.ops, [])

    def test_delete_backup_uses_same_check(self):
        self.release.set()
        wait_done(self.job)
        backup = f"{ROOT}/Backups/Meier/2026-11-25"
        self.job, self.release = start(self.jm, backup, disk="/dev/sdb")
        b = types.SimpleNamespace(path=Path(backup))
        with mock.patch.object(ui, "run_async") as measure:
            self.win.delete_backup(b)
        measure.assert_not_called()
        self.assertTrue(self.errors and self.errors[0].startswith("Dieses Backup wird gerade von"))

    def test_demo_cleanup_skips_busy_images(self):
        busy = types.SimpleNamespace(path=Path(IMAGE))
        free = types.SimpleNamespace(path=Path(f"{ROOT}/DEMO-Master-Win11"))
        self.win._old_demo_images = [busy, free]
        deleted = []
        with mock.patch.object(ui, "confirm", return_value=True) as asked, \
                mock.patch.object(ui.nasfiles, "delete", lambda root, rel, names: deleted.append(names)):
            self.win.delete_old_demo_images()
            self.assertIn("DEMO-Master-Win11", asked.call_args[0][2])
            self.assertNotIn("Meier", asked.call_args[0][2])
            op, msg = self.win.ops[0]
            op()
        self.assertEqual(deleted, [["DEMO-Master-Win11"]])
        self.assertEqual(msg, "1 alte Demo-Images vom NAS gelöscht")
        self.assertTrue(any("übersprungen" in s for s in self.win.statuses))

    def test_demo_cleanup_only_busy_does_nothing(self):
        self.win._old_demo_images = [types.SimpleNamespace(path=Path(IMAGE))]
        with mock.patch.object(ui, "confirm") as asked:
            self.win.delete_old_demo_images()
        asked.assert_not_called()
        self.assertEqual(self.win.ops, [])


if __name__ == "__main__":
    unittest.main()
