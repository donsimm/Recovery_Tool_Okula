"""I-012 BitLocker entsperren – Agent-Seite (dislocker nur lesend, Aufräumen, Schlüssel nie in Meldungen/Log).

Alle Schlüssel sind offensichtliche Testwerte (jeder Block durch 11 teilbar, aber kein echter Schlüssel)."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, deploy, filebackup, imaging, inventory

KEY = "111111-222222-333333-444444-555555-666666-111111-222222"
KEY_PLAIN = KEY.replace("-", "")
DEV = "/dev/sda3"
DISKS = [{"path": "/dev/sda", "name": "sda", "partitions": [
    {"path": "/dev/sda1", "name": "sda1", "fstype": "vfat", "size": 100 * 1024**2},
    {"path": DEV, "name": "sda3", "fstype": "BitLocker", "size": 100 * 1024**3}]}]


class FakeRun:
    """subprocess.run für dislocker/mount/umount/fusermount; legt dislocker-file wie FUSE an."""

    def __init__(self, dislocker_rc=0, dislocker_err="", mount_rc=0, inner_fs="ntfs"):
        self.calls: list[list[str]] = []
        self.dislocker_rc, self.dislocker_err, self.mount_rc, self.inner_fs = \
            dislocker_rc, dislocker_err, mount_rc, inner_fs

    def __call__(self, cmd, **_kw):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        out, err, rc = "", "", 0
        if cmd[0] == "dislocker":
            rc, err = self.dislocker_rc, self.dislocker_err
            if rc == 0:
                (Path(cmd[-1]) / filebackup.DISLOCKER_FILE).write_bytes(b"")
        elif cmd[0] == "blkid":
            out = self.inner_fs
        elif cmd[0] == "mount":
            rc = self.mount_rc
        elif cmd[0] in ("fusermount3", "fusermount"):
            (Path(cmd[-1]) / filebackup.DISLOCKER_FILE).unlink(missing_ok=True)
        return subprocess.CompletedProcess(cmd, rc, out, err)

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


class AgentBitlockerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name) / "work"
        self.run = FakeRun()
        self.patches = [mock.patch.object(filebackup, "WORK", self.work),
                        mock.patch.object(imaging, "list_disks", lambda: DISKS),
                        mock.patch.object(filebackup.shutil, "which", lambda name: f"/usr/bin/{name}"),
                        mock.patch("subprocess.run", self.run)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_recovery_key_format(self):
        self.assertEqual(filebackup.recovery_key(KEY_PLAIN), KEY)
        self.assertEqual(filebackup.recovery_key(" " + KEY.replace("-", " ") + " "), KEY)
        self.assertEqual(filebackup.recovery_key(KEY), KEY)
        for bad in ("", "123", KEY[:-1], KEY + "1", KEY.replace("1", "x", 1)):
            self.assertEqual(filebackup.recovery_key(bad), "", bad)

    def test_unlock_read_only_and_cleanup_in_reverse(self):
        with filebackup.Mounts(bitlocker={DEV: KEY_PLAIN}) as m:
            root = m.get(DEV)
            self.assertTrue(root.is_dir())
        dis = next(c for c in self.run.calls if c[0] == "dislocker")
        self.assertIn("-r", dis)                                   # immer nur lesend
        self.assertEqual(dis[dis.index("-V") + 1], DEV)
        self.assertIn(f"-p{KEY}", dis)
        self.assertNotIn("-w", dis)
        mount = next(c for c in self.run.calls if c[0] == "mount")
        self.assertTrue(mount[mount.index("-o") + 1].startswith("ro"))
        self.assertIn("loop", mount[mount.index("-o") + 1])
        self.assertTrue(mount[-2].endswith(filebackup.DISLOCKER_FILE))
        names = self.run.names()
        self.assertLess(names.index("umount"), names.index("fusermount3"))   # erst NTFS, dann FUSE
        self.assertEqual(list(self.work.iterdir()), [])              # alle Ordner weg

    def test_wrong_key_clear_message_without_key(self):
        self.run.dislocker_rc = 1
        self.run.dislocker_err = (f"[CRITICAL] None of the provided decryption mean is decrypting the keys. "
                                  f"Abort. (-p{KEY})")
        with self.assertRaises(imaging.ImagingError) as cm, filebackup.Mounts(bitlocker={DEV: KEY}) as m:
            m.get(DEV)
        self.assertEqual(str(cm.exception), "Wiederherstellungsschlüssel passt nicht zu sda3")
        self.assertIn("fusermount3", self.run.names())
        self.assertNotIn("mount", self.run.names())
        self.assertEqual(list(self.work.iterdir()), [])

    def test_other_dislocker_error_is_scrubbed(self):
        self.run.dislocker_rc = 2
        self.run.dislocker_err = f"fehler mit {KEY} und {KEY_PLAIN}\nkaputt {KEY}"
        with self.assertRaises(imaging.ImagingError) as cm, filebackup.Mounts(bitlocker={DEV: KEY}) as m:
            m.get(DEV)
        self.assertNotIn(KEY, str(cm.exception))
        self.assertNotIn(KEY_PLAIN, str(cm.exception))
        self.assertIn("sda3", str(cm.exception))

    def test_mount_fails_fuse_is_cleaned(self):
        self.run.mount_rc = 32
        with self.assertRaises(imaging.ImagingError), filebackup.Mounts(bitlocker={DEV: KEY}) as m:
            m.get(DEV)
        self.assertIn("fusermount3", self.run.names())
        self.assertEqual(list(self.work.iterdir()), [])

    def test_invalid_key_format_no_call(self):
        with self.assertRaises(imaging.ImagingError) as cm, filebackup.Mounts(bitlocker={DEV: "1234"}) as m:
            m.get(DEV)
        self.assertIn("48 Ziffern", str(cm.exception))
        self.assertNotIn("dislocker", self.run.names())

    def test_old_stick_without_dislocker(self):
        with mock.patch.object(filebackup.shutil, "which", lambda name: None):
            with self.assertRaises(imaging.ImagingError) as cm, filebackup.Mounts(bitlocker={DEV: KEY}) as m:
                m.get(DEV)
        self.assertEqual(str(cm.exception), filebackup.STICK_TOO_OLD)

    def test_without_key_as_before(self):
        with self.assertRaises(imaging.ImagingError) as cm, filebackup.Mounts() as m:
            m.get(DEV)
        self.assertIn("BitLocker", str(cm.exception))
        self.assertEqual(self.run.calls, [])

    def test_write_stays_blocked_even_with_key(self):
        with self.assertRaises(imaging.ImagingError) as cm, \
                filebackup.Mounts(write=True, bitlocker={DEV: KEY}) as m:
            m.get(DEV)
        self.assertIn("nicht beschreibbar", str(cm.exception))
        self.assertNotIn("dislocker", self.run.names())
        with self.assertRaises(imaging.ImagingError):
            deploy._candidates("/dev/sda")

    def test_profiles_with_and_without_key(self):
        win = {"name": "Windows 11 Pro"}
        with mock.patch.object(inventory, "inspect_root", lambda root: win), \
                mock.patch.object(filebackup, "_users", lambda root: ("windows", [{"name": "Test",
                                                                                   "path": "Users/Test"}])):
            plain = {p["part"]: p for p in filebackup.profiles()}
            self.assertTrue(plain[DEV]["bitlocker"])
            self.assertEqual(plain[DEV]["error"], "BitLocker – nicht lesbar")
            self.assertNotIn("dislocker", self.run.names())
            opened = {p["part"]: p for p in filebackup.profiles(bitlocker={DEV: KEY})}
        self.assertNotIn("error", opened[DEV])
        self.assertTrue(opened[DEV]["unlocked"])
        self.assertEqual([u["name"] for u in opened[DEV]["users"]], ["Test"])
        self.assertEqual(opened[DEV]["kind"], "windows")

    def test_profiles_wrong_key_error_in_entry(self):
        self.run.dislocker_rc = 1
        self.run.dislocker_err = "None of the provided decryption mean is decrypting the keys"
        entry = {p["part"]: p for p in filebackup.profiles(bitlocker={DEV: KEY})}[DEV]
        self.assertEqual(entry["error"], "Wiederherstellungsschlüssel passt nicht zu sda3")
        self.assertTrue(entry["bitlocker"])

    def test_request_keys_only_strings(self):
        self.assertEqual(filebackup.bitlocker_keys({DEV: KEY, "x": 3, 4: "y", "z": ""}), {DEV: KEY})
        self.assertEqual(filebackup.bitlocker_keys(["a"]), {})
        self.assertEqual(filebackup.bitlocker_keys(None), {})

    def test_agent_log_and_error_without_key(self):
        logged, sent = [], []

        def boom(*_a, **_k):
            raise imaging.ImagingError(f"kaputt -p{KEY}")

        with mock.patch.object(agent, "log", lambda msg, **_k: logged.append(msg)), \
                mock.patch.object(agent.wire, "send_json", lambda _s, msg: sent.append(msg)), \
                mock.patch.object(agent, "console", None), \
                mock.patch.object(filebackup, "backup", boom):
            agent.run_job(None, ("127.0.0.1", 1), {"cmd": "backup", "disk": "/dev/sda", "sources": [],
                                                   "bitlocker": {DEV: KEY}}, "backup")
        text = " ".join(logged) + " ".join(str(m) for m in sent)
        self.assertIn("fehlgeschlagen", text)
        self.assertNotIn(KEY, text)
        self.assertNotIn(KEY_PLAIN, text)


if __name__ == "__main__":
    unittest.main()
