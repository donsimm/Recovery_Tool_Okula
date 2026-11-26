"""B-030/B-031: Umbenennen nach grossem Schreiben auf dem NAS mit Wiederholung (SMB hält Dateien noch kurz offen)."""

import errno
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import nas, software


class RenameRetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / ".abc.partial"
        self.src.mkdir()
        (self.src / "datei.bin").write_bytes(b"x")
        self.dst = self.root / "ziel"
        self.sleeps: list[float] = []
        self.waits = 0
        self.real_rename = Path.rename

    def tearDown(self):
        self.tmp.cleanup()

    def run_retry(self, side_effects, **kw):
        """rename: Einträge aus side_effects nacheinander (Exception → werfen, None → wirklich umbenennen)."""
        calls = []
        effects = iter(side_effects)
        real = self.real_rename

        def fake(path, target):
            calls.append((path, target))
            effect = next(effects, None)
            if effect is not None:
                raise effect
            return real(path, target)

        def on_wait():
            self.waits += 1

        with mock.patch.object(Path, "rename", fake):
            nas.rename_retry(self.src, self.dst, attempts=kw.pop("attempts", 10), pause=2.0, on_wait=on_wait,
                             sleep=self.sleeps.append, **kw)
        return calls

    def test_ok_after_three_permission_errors(self):
        err = PermissionError(errno.EACCES, "Keine Berechtigung")
        calls = self.run_retry([err, err, err, None])
        self.assertEqual(len(calls), 4)
        self.assertEqual(self.sleeps, [2.0, 2.0, 2.0])
        self.assertEqual(self.waits, 1)                       # „Ordner wird fertiggestellt …“ nur einmal
        self.assertTrue((self.dst / "datei.bin").is_file())
        self.assertFalse(self.src.exists())

    def test_ebusy_is_retried(self):
        calls = self.run_retry([OSError(errno.EBUSY, "Gerät belegt"), None])
        self.assertEqual(len(calls), 2)
        self.assertTrue(self.dst.is_dir())

    def test_first_try_ok_no_wait(self):
        calls = self.run_retry([None])
        self.assertEqual((len(calls), self.sleeps, self.waits), (1, [], 0))

    def test_always_permission_error_gives_message(self):
        err = PermissionError(errno.EACCES, "Keine Berechtigung")
        with self.assertRaises(nas.RenameError) as cm:
            self.run_retry([err] * 20, again="nochmals laden")
        self.assertEqual(len(self.sleeps), 9)                 # 10 Versuche, ~18 s gewartet
        self.assertEqual(self.waits, 1)
        e = cm.exception
        self.assertIsInstance(e, OSError)                     # bestehende „except OSError“ greifen weiter
        self.assertEqual(e.errno, errno.EACCES)
        self.assertIn("Kopie fertig, aber das NAS lässt den Ordner nicht umbenennen", str(e))
        self.assertIn("nochmals laden", str(e))
        self.assertIn("Netzwerkzugriff des Servers hält den Ordner noch kurz offen", str(e))
        self.assertNotIn("Virenscan", str(e))                 # B-031: falscher Hinweis entfernt
        self.assertNotIn("Errno", str(e))
        self.assertTrue(self.src.is_dir())                    # Aufräumen ist Sache des Aufrufers

    def test_target_exists_fails_immediately(self):
        self.dst.mkdir()
        err = PermissionError(errno.EACCES, "Keine Berechtigung")
        with self.assertRaises(PermissionError) as cm:
            self.run_retry([err] * 5)
        self.assertNotIsInstance(cm.exception, nas.RenameError)
        self.assertEqual((self.sleeps, self.waits), ([], 0))

    def test_other_error_fails_immediately(self):
        with self.assertRaises(OSError) as cm:
            self.run_retry([OSError(errno.ENOSPC, "Kein Platz")] * 5)
        self.assertEqual(cm.exception.errno, errno.ENOSPC)
        self.assertNotIsInstance(cm.exception, nas.RenameError)
        self.assertEqual(self.sleeps, [])

    def test_default_wait_ninety_seconds(self):
        # B-031: CIFS dir_cache_timeout (30 s) hält den Ordner offen – mindestens 3 × warten, insgesamt 90 s
        self.assertAlmostEqual((nas.RENAME_ATTEMPTS - 1) * nas.RENAME_PAUSE, 90.0)
        self.assertIn("bis 90 s", nas.FINISHING)

    def test_default_arguments_wait_ninety_seconds(self):
        err = PermissionError(errno.EACCES, "Keine Berechtigung")
        sleeps: list[float] = []
        with mock.patch.object(Path, "rename", side_effect=err):
            with self.assertRaises(nas.RenameError):
                nas.rename_retry(self.src, self.dst, sleep=sleeps.append)
        self.assertEqual(len(sleeps), nas.RENAME_ATTEMPTS - 1)
        self.assertAlmostEqual(sum(sleeps), 90.0)


class SoftwareLoadRenameTest(unittest.TestCase):
    """software.load: endgültig gescheitertes Umbenennen → Meldung, .partial weg, Fortschritt zeigt den Vorgang."""

    def test_load_gives_message_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            src = Path(tmp) / "q" / "werkzeug.msi"
            src.parent.mkdir()
            src.write_bytes(b"msi" * 100)
            real = Path.rename
            texts = []

            def fake(path, target):
                if path.name.endswith(software.PARTIAL):
                    raise PermissionError(errno.EACCES, "Keine Berechtigung", str(path), None, str(target))
                return real(path, target)

            with mock.patch.object(Path, "rename", fake), mock.patch.object(nas.time, "sleep") as sleep:
                with self.assertRaises(nas.RenameError) as cm:
                    software.load(root, src, lambda d, t, f: texts.append(f))
            self.assertEqual(sleep.call_count, nas.RENAME_ATTEMPTS - 1)
            self.assertIn("nochmals laden", str(cm.exception))
            self.assertIn(nas.FINISHING, texts)
            base = software.library_dir(root)
            self.assertEqual([p.name for p in base.iterdir() if p.name.endswith(software.PARTIAL)], [])


if __name__ == "__main__":
    unittest.main()
