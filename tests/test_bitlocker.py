"""I-012 BitLocker entsperren – Agent-Seite (dislocker nur lesend, Aufräumen, Schlüssel nie in Meldungen/Log).

Alle Schlüssel sind offensichtliche Testwerte (jeder Block durch 11 teilbar, aber kein echter Schlüssel)."""

import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from okula_recovery import agent, bitlocker_keys, deploy, filebackup, imaging, inventory

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


class KeyStoreTest(unittest.TestCase):
    """Schlüssel-Speicher (Tool): Format, Rechte, atomar, Löschen, Root-Helfer, nichts in Exporten."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "etc" / "bitlocker"

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalize_and_block_check(self):
        self.assertEqual(bitlocker_keys.normalize(KEY_PLAIN), KEY)
        self.assertEqual(bitlocker_keys.normalize(KEY.replace("-", " ")), KEY)
        with self.assertRaisesRegex(bitlocker_keys.BitLockerKeyError, "48 Ziffern"):
            bitlocker_keys.normalize("1234")
        with self.assertRaisesRegex(bitlocker_keys.BitLockerKeyError, "Block 2"):
            bitlocker_keys.normalize(KEY.replace("222222", "222223", 1))      # nicht durch 11 teilbar
        with self.assertRaisesRegex(bitlocker_keys.BitLockerKeyError, "Block 1"):
            bitlocker_keys.normalize("720896" + KEY_PLAIN[6:])                # 11 · 65536 – zu gross
        self.assertTrue(bitlocker_keys.valid("720885" + KEY_PLAIN[6:]))       # 11 · 65535 – grösster Block

    def test_write_read_rights_atomic_delete(self):
        msg = bitlocker_keys.write_key("dev-1", DEV, KEY_PLAIN, self.base)
        self.assertNotIn(KEY, msg)
        path = self.base / "dev-1.json"
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(bitlocker_keys.read_keys("dev-1", self.base), {DEV: KEY})
        bitlocker_keys.write_key("dev-1", "/dev/sdb2", KEY, self.base)
        self.assertEqual(set(bitlocker_keys.read_keys("dev-1", self.base)), {DEV, "/dev/sdb2"})
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["dev-1.json"])   # keine .tmp-Reste
        with mock.patch.object(bitlocker_keys.os, "replace", side_effect=OSError("Platte voll")):
            with self.assertRaises(OSError):
                bitlocker_keys.write_key("dev-1", DEV, KEY.replace("111111", "000000", 1), self.base)
        self.assertEqual(bitlocker_keys.read_keys("dev-1", self.base)[DEV], KEY)          # alte Datei unverändert
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["dev-1.json"])
        self.assertEqual(bitlocker_keys.read_keys("anderes", self.base), {})
        bitlocker_keys.delete_keys("dev-1", self.base)
        self.assertFalse(path.exists())
        self.assertEqual(bitlocker_keys.read_keys("dev-1", self.base), {})

    def test_wrong_rights_are_refused(self):
        bitlocker_keys.write_key("dev-1", DEV, KEY, self.base)
        os.chmod(self.base / "dev-1.json", 0o644)
        with self.assertRaisesRegex(bitlocker_keys.BitLockerKeyError, "Rechte"):
            bitlocker_keys.read_keys("dev-1", self.base)
        os.chmod(self.base / "dev-1.json", 0o600)
        os.chmod(self.base, 0o755)
        with self.assertRaisesRegex(bitlocker_keys.BitLockerKeyError, "Rechte"):
            bitlocker_keys.read_keys("dev-1", self.base)
        bitlocker_keys.write_key("dev-1", DEV, KEY, self.base)           # schreiben setzt die Rechte wieder
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode), 0o700)

    def test_invalid_device_or_partition(self):
        for bad in ("../x", "", ".versteckt", "a/b"):
            with self.assertRaises(bitlocker_keys.BitLockerKeyError):
                bitlocker_keys.write_key(bad, DEV, KEY, self.base)
        with self.assertRaises(bitlocker_keys.BitLockerKeyError):
            bitlocker_keys.write_key("dev-1", "/etc/passwd", KEY, self.base)
        with self.assertRaises(bitlocker_keys.BitLockerKeyError):
            bitlocker_keys.write_key("dev-1", DEV, "1234", self.base)
        self.assertFalse((self.base / "dev-1.json").exists())

    def test_helper_cli_and_tool_side(self):
        def run(args, stdin=None):
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(stdin or "")), mock.patch("sys.stdout", out):
                rc = bitlocker_keys.main(args, base=self.base)
            line = out.getvalue().strip().splitlines()[-1]
            kind, _, msg = line.partition(" ")
            return kind == "OK" and rc == 0, msg

        self.assertFalse(bitlocker_keys.has("dev-1", run))
        calls = []

        def spy(args, stdin=None):
            calls.append(args)
            return run(args, stdin)

        bitlocker_keys.save("dev-1", DEV, KEY_PLAIN, spy)
        self.assertFalse(any(KEY in a or KEY_PLAIN in a for a in calls[-1]))     # Schlüssel nur über stdin
        self.assertTrue(bitlocker_keys.has("dev-1", run))
        self.assertEqual(bitlocker_keys.stored("dev-1", run), {DEV: KEY})
        with self.assertRaises(bitlocker_keys.BitLockerKeyError):
            bitlocker_keys.save("dev-1", DEV, "kaputt", run)
        bitlocker_keys.delete("dev-1", run)
        self.assertFalse(bitlocker_keys.has("dev-1", run))

    def test_for_partitions(self):
        self.assertEqual(bitlocker_keys.for_partitions({DEV: KEY}, [DEV]), {DEV: KEY})
        self.assertEqual(bitlocker_keys.for_partitions({DEV: KEY}, ["/dev/sdb3"]), {"/dev/sdb3": KEY})
        two = {DEV: KEY, "/dev/sda4": KEY}
        self.assertEqual(bitlocker_keys.for_partitions(two, ["/dev/sdb3"]), {})
        self.assertEqual(bitlocker_keys.for_partitions({}, [DEV]), {})

    def test_inventory_partitions(self):
        inv = {"disks": [{"partitions": [{"path": "/dev/sda1", "name": "sda1", "fstype": "vfat"},
                                         {"path": "/dev/sda2", "name": "sda2", "fstype": "BitLocker"},
                                         {"path": "/dev/sda3", "name": "sda3", "fstype": ""}]}],
               "systems": [{"name": "verschlüsselt (BitLocker)", "partition": "sda3"}]}
        self.assertEqual(bitlocker_keys.inventory_partitions(inv), ["/dev/sda2", "/dev/sda3"])
        self.assertEqual(bitlocker_keys.inventory_partitions({}), [])

    def test_key_not_in_exports(self):
        from okula_recovery import devices, inventory_export, transfer
        root = Path(self.tmp.name)
        env = {"XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data")}
        with mock.patch.dict(os.environ, env), mock.patch.object(bitlocker_keys, "KEY_DIR", self.base):
            bitlocker_keys.write_key("d1", DEV, KEY)
            base = devices.default_base()
            base.mkdir(parents=True, exist_ok=True)
            (base / "d1.json").write_text(json.dumps({"id": "d1", "name": "PC", "inventory": {
                "disks": [{"name": "sda", "partitions": [{"path": DEV, "name": "sda3", "fstype": "BitLocker"}]}]}}))
            out = root / "export.okula.zip"
            transfer.export_all(out)
            with zipfile.ZipFile(out) as z:
                blob = b"".join(z.read(n) for n in z.namelist())
            store = devices.DeviceStore(base)
            rows = inventory_export.build(list(store.devices.values()), {}, {}, with_key=True)
            self.assertEqual(len(rows), 1)
            self.assertTrue(bitlocker_keys.read_keys("d1"))           # Schlüssel ist wirklich gespeichert
            csv = inventory_export.write_csv(root / "inv.csv", rows, with_key=True).read_bytes()
            saved = b"".join(p.read_bytes() for p in base.rglob("*.json"))
        for data in (blob, csv, saved):
            self.assertNotIn(KEY.encode(), data)
            self.assertNotIn(KEY_PLAIN.encode(), data)


class StickTest(unittest.TestCase):
    def test_dislocker_on_stick_and_netboot(self):
        from okula_recovery import stick
        # Agent-Stick und Netzwerkstart bauen den Agent-Teil mit derselben Liste (stick.install_agent)
        self.assertIn("dislocker", stick.BUNDLED_PACKAGES)
        self.assertIn("fuse3", stick.BUNDLED_PACKAGES)


if __name__ == "__main__":
    unittest.main()
