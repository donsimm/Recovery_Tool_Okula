import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import nas, nasmount

SMBCLIENT_OUT = """\
Disk|recovery|Images und Backups
Disk|homes|
Disk|ADMIN$|Remote Admin
IPC|IPC$|IPC Service
Disk|backup|
"""


class SharesTest(unittest.TestCase):
    def test_parse_smbclient(self):
        self.assertEqual(nas.parse_smbclient_shares(SMBCLIENT_OUT), ["backup", "homes", "recovery"])


class HintTest(unittest.TestCase):
    def test_hints(self):
        self.assertIn("Passwort falsch", nas.mount_error_hint("mount error(13): Permission denied"))
        self.assertIn("existiert nicht", nas.mount_error_hint("mount error(2): No such file or directory"))
        self.assertEqual(nas.mount_error_hint("something else"), "")


class ValidationTest(unittest.TestCase):
    def test_mount_point_only_directly_under_mnt(self):
        self.assertEqual(nasmount.check_mount_point("/mnt/okula-nas"), Path("/mnt/okula-nas"))
        for bad in ("/etc", "/mnt", "/mnt/a/b", "/mnt/../etc", "relative"):
            with self.assertRaises(nasmount.MountError, msg=bad):
                nasmount.check_mount_point(bad)

    def test_rejects_option_injection(self):
        with self.assertRaises(nasmount.MountError):
            nasmount.do_mount("smb", "nas", "share,uid=0", "/mnt/x", "u", "p", 1000, 1000)
        with self.assertRaises(nasmount.MountError):
            nasmount.do_mount("smb", "-o x", "share", "/mnt/x", "u", "p", 1000, 1000)


class CredentialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cred = Path(self.tmp.name) / "etc" / "nas.cred"
        self.patch = mock.patch.object(nasmount, "CRED_FILE", self.cred)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_write_and_read(self):
        nasmount.write_cred("NASuser", "geheim!Pa$$")
        self.assertEqual(stat.S_IMODE(os.stat(self.cred).st_mode), 0o600)
        self.assertEqual(nasmount.read_cred_user(), "NASuser")
        self.assertIn("password=geheim!Pa$$\n", self.cred.read_text())

    def test_rejects_newline(self):
        with self.assertRaises(nasmount.MountError):
            nasmount.write_cred("u", "a\nusername=root")

    def test_smb_mount_command(self):
        calls = []
        with mock.patch.object(nasmount, "_run", calls.append), \
                mock.patch.object(nasmount, "MOUNT_ROOT", Path(self.tmp.name)):
            mp = str(Path(self.tmp.name) / "okula-nas")
            nasmount.do_mount("smb", "192.168.110.154", "recovery", mp, "NASuser", "Geheim-Passwort-42", 1000, 1000)
            # Ohne Passwort: gespeicherte Zugangsdaten desselben Benutzers verwenden
            nasmount.do_mount("smb", "192.168.110.154", "recovery", mp, "NASuser", None, 1000, 1000)
            with self.assertRaises(nasmount.MountError):
                nasmount.do_mount("smb", "192.168.110.154", "recovery", mp, "anderer", None, 1000, 1000)
        cmd = calls[0]
        self.assertEqual(cmd[:5], ["mount", "-t", "cifs", "//192.168.110.154/recovery", mp])
        self.assertIn(f"credentials={self.cred},uid=1000,gid=1000", cmd[6])
        self.assertNotIn("Geheim-Passwort-42", " ".join(cmd))

    def test_failed_mount_keeps_previous_credentials(self):
        def fail(cmd):
            raise nasmount.MountError("mount error(13): Permission denied")
        nasmount.write_cred("NASuser", "richtig")
        with mock.patch.object(nasmount, "_run", fail), \
                mock.patch.object(nasmount, "MOUNT_ROOT", Path(self.tmp.name)):
            mp = str(Path(self.tmp.name) / "okula-nas")
            with self.assertRaises(nasmount.MountError):
                nasmount.do_mount("smb", "nas", "recovery", mp, "NASuser", "falsch", 1000, 1000)
        self.assertIn("password=richtig", self.cred.read_text())

    def test_nfs_mount_command(self):
        calls = []
        with mock.patch.object(nasmount, "_run", calls.append), \
                mock.patch.object(nasmount, "MOUNT_ROOT", Path(self.tmp.name)):
            mp = str(Path(self.tmp.name) / "okula-nas")
            nasmount.do_mount("nfs", "nas", "/volume1/recovery", mp, "", None, 0, 0)
            with self.assertRaises(nasmount.MountError):
                nasmount.do_mount("nfs", "nas", "recovery", mp, "", None, 0, 0)
        self.assertEqual(calls[0][:5], ["mount", "-t", "nfs", "nas:/volume1/recovery", mp])


class ClientTest(unittest.TestCase):
    def test_password_goes_via_stdin(self):
        cfg = nas.NasConfig(host="192.168.110.154", share="recovery", username="NASuser")
        result = mock.Mock(stdout="OK /mnt/okula-nas eingehängt\n", stderr="", returncode=0)
        with mock.patch.object(nas.subprocess, "run", return_value=result) as run:
            ok, msg = nas.mount(cfg, "geheim")
        self.assertTrue(ok)
        args, kwargs = run.call_args
        self.assertNotIn("geheim", " ".join(args[0]))
        self.assertEqual(kwargs["input"], "geheim\n")

    def test_error_line(self):
        cfg = nas.NasConfig(host="h", share="s", username="u")
        result = mock.Mock(stdout="ERROR mount error(13): Permission denied – Benutzer …\n", stderr="", returncode=1)
        with mock.patch.object(nas.subprocess, "run", return_value=result):
            ok, msg = nas.mount(cfg)
        self.assertFalse(ok)
        self.assertIn("Permission denied", msg)


if __name__ == "__main__":
    unittest.main()
