"""winsetup: Antwortdatei für den ersten Start nach der Direktinstallation (ohne ISO, ohne Agent)."""

import unittest
import xml.etree.ElementTree as ET

from okula_recovery import winsetup, winunattend as wu
from tests.test_winunattend import DIRECT_OPTS, EXPECTED_DIRECT, N, component, structure


class SystemUnattendTest(unittest.TestCase):
    def test_without_audit_unchanged(self):
        # skip_network setzt die Direktinstallation immer; sonst wie bisher
        opts = wu.WinOptions(**{**DIRECT_OPTS, "skip_network": False})
        self.assertEqual(structure(winsetup.system_unattend(opts)), EXPECTED_DIRECT)
        self.assertNotIn("auditUser", winsetup.system_unattend(opts))

    def test_audit_cleans_setup_partition(self):
        """I-038: Setup-Partition wird auch beim Start in den Audit-Modus aufgeräumt, dann die Antwortdatei gelöscht."""
        root = ET.fromstring(winsetup.system_unattend(wu.WinOptions(**DIRECT_OPTS, audit_mode=True)))
        paths = [p.text for p in component(root, "auditUser", "Microsoft-Windows-Deployment")
                 .iter(f"{{{wu.NS}}}Path")]
        self.assertEqual(paths[0], 'cmd /c "%WINDIR%\\Setup\\Scripts\\SetupComplete.cmd"')
        self.assertIn("Panther\\unattend.xml", paths[1])
        self.assertEqual(component(root, "oobeSystem", "Microsoft-Windows-Deployment")
                         .find("u:Reseal/u:Mode", N).text, "Audit")

    def test_setupcomplete_runs_twice_harmlessly(self):
        # install.cmd legt das Skript genau dort ab, wo auditUser es aufruft
        cmd = winsetup.install_cmd("ab12cd34", 1, "sources/install.wim", False, "de-DE")
        self.assertIn("%W%:\\Windows\\Setup\\Scripts\\SetupComplete.cmd", cmd)
        self.assertIn("%W%:\\Windows\\Panther\\unattend.xml", cmd)
        # ohne Marker-Datei (Partition schon gelöscht) springt das Skript ans Ende – zweiter Lauf tut nichts
        done = winsetup.setupcomplete_cmd("ab12cd34")
        self.assertIn('if "%S%"=="" goto ende', done)
        self.assertLess(done.index('goto ende'), done.index("diskpart"))
        self.assertTrue(winsetup.AUDIT_CLEANUP.isascii())


if __name__ == "__main__":
    unittest.main()
