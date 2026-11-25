"""B-022: Startmenü-Liste auf neu installiertem Windows – ehrlicher Hinweis statt „ok“, Bereitstellungspaket (PPKG)
als belegter Weg (Erzeugen nur mit Windows Configuration Designer, hier nachgebildet), Protokoll der Direktinstallation
einheitlich (Datum, UTF-8 mit BOM)."""

import base64
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from okula_recovery import deploy, software, winsetup, wintweaks
from tests.test_wintweaks import steps

ROOT = Path(__file__).resolve().parents[1]
LABEL = "Startmenü: Werbe-Kacheln entfernen (Windows 11)"
NS = "{urn:schemas-microsoft-com:windows-provisioning}"


def start_body(selected=frozenset({wintweaks.START_CLEAN})) -> str:
    return steps(wintweaks.build_script(set(selected)))[LABEL]


class PackageSourceTest(unittest.TestCase):
    """Vorlage für Windows Configuration Designer: liegt im Repo und passt immer zur Liste im Code."""

    def test_customizations_xml_in_repo_matches_code(self):
        path = wintweaks.ASSETS_DIR / wintweaks.START_PPKG_XML
        self.assertEqual(path, ROOT / "okula_recovery/assets/startpins/customizations.xml")
        self.assertEqual(path.read_text(encoding="utf-8"), wintweaks.start_pins_customizations_xml())

    def test_customizations_xml_structure(self):
        root = ET.fromstring(wintweaks.start_pins_customizations_xml().encode("utf-8"))
        self.assertEqual(root.tag, "WindowsCustomizations")
        cfg = root.find("{urn:schemas-Microsoft-com:Windows-ICD-Package-Config.v1.0}PackageConfig")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.findtext("{urn:schemas-Microsoft-com:Windows-ICD-Package-Config.v1.0}ID"),
                         wintweaks.START_PPKG_ID)
        # Policies/Start/ConfigureStartPins (Microsoft Learn, Reiter PPKG), Wert = JSON in einer Zeile
        pins = root.find(f"{NS}Settings/{NS}Customizations/{NS}Common/{NS}Policies/{NS}Start/{NS}ConfigureStartPins")
        self.assertIsNotNone(pins)
        self.assertEqual(pins.text, wintweaks.start_pins_json())
        self.assertNotIn("\n", pins.text)


class PackageUseTest(unittest.TestCase):
    """Paket nur mitgeben, wenn es zur aktuellen Liste passt; Anwendung im Skript (nachgebildet)."""

    def test_package_only_when_matching_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertIsNone(wintweaks.start_pins_ppkg(folder))                       # nichts da
            (folder / wintweaks.START_PPKG_FILE).write_bytes(b"PKG")
            self.assertIsNone(wintweaks.start_pins_ppkg(folder))                       # Quelle fehlt
            (folder / wintweaks.START_PPKG_SOURCE).write_text("{}", encoding="utf-8")
            self.assertIsNone(wintweaks.start_pins_ppkg(folder))                       # veraltete Liste
            (folder / wintweaks.START_PPKG_SOURCE).write_text(wintweaks.start_pins_json() + "\n", encoding="utf-8")
            self.assertEqual(wintweaks.start_pins_ppkg(folder), b"PKG")
            (folder / wintweaks.START_PPKG_FILE).write_bytes(b"")
            self.assertIsNone(wintweaks.start_pins_ppkg(folder))                       # leere Datei
        if not (wintweaks.ASSETS_DIR / wintweaks.START_PPKG_FILE).exists():
            self.assertIsNone(wintweaks.start_pins_ppkg())

    def test_script_without_package(self):
        with mock.patch.object(wintweaks, "start_pins_ppkg", lambda: None):
            body = start_body()
        self.assertIn(wintweaks.PPKG_LINE, body)                                       # leer – nichts installiert
        self.assertIn("if ($ppkg) {", body)

    def test_script_with_package(self):
        data = bytes(range(256)) * 3
        with mock.patch.object(wintweaks, "start_pins_ppkg", lambda: data):
            body = start_body()
        b64 = base64.b64encode(data).decode("ascii")
        self.assertIn(f"$ppkg = '{b64}'", body)
        self.assertNotIn(wintweaks.PPKG_LINE, body)
        self.assertIn("[IO.File]::WriteAllBytes($pfile, [Convert]::FromBase64String($ppkg))", body)
        self.assertIn("Install-ProvisioningPackage -PackagePath $pfile -QuietInstall -ForceInstall", body)
        self.assertIn(f"Temp\\{wintweaks.START_PPKG_LOGS}", body)
        # Paket vor Windows-10-Abbruch nicht, aber vor Gruppenrichtlinie und MDM-Bridge
        self.assertLess(body.index("Build -lt 22000"), body.index("Install-ProvisioningPackage"))
        self.assertLess(body.index("Install-ProvisioningPackage"), body.index("Build -ge 26100"))
        # Fehler beim Paket: kein Abbruch, steht im Rückgabetext; Gruppenrichtlinie läuft trotzdem
        pkg = body[body.index("if ($ppkg) {"):body.index("Build -ge 26100")]
        self.assertNotIn("throw", pkg)
        self.assertIn("nicht installiert: ' + $_.Exception.Message", pkg)
        # vor 24H2 ersetzt das Paket die MDM-Bridge
        self.assertLess(body.index("if ($ppkgOk) {\n"), body.index("MDM_Policy_Config01_Start02"))

    def test_only_start_clean_gets_package(self):
        with mock.patch.object(wintweaks, "start_pins_ppkg", lambda: b"PKG"):
            other = wintweaks.build_script({"cortana", "show_ext"})
        self.assertNotIn("Install-ProvisioningPackage", other)


class HonestHintTest(unittest.TestCase):
    """Ohne wirksames Paket kein „ok“: Status „Hinweis“ im Protokoll, Hinweis im Log, Tooltip und Hilfe."""

    def test_hint_text(self):
        self.assertIn("stufenweise", wintweaks.START_GPO_HINT)
        self.assertIn("KB5062660", wintweaks.START_GPO_HINT)
        self.assertIn("frisch installierten Geräten", wintweaks.START_GPO_HINT)
        self.assertNotIn("'", wintweaks.START_GPO_HINT)                                # passt in '…' von PowerShell

    def test_script_reports_hint_not_ok(self):
        body = start_body()
        self.assertIn("if (-not $ppkgOk) { $pinHint = 'Hinweis: Wirkung nicht sicher – "
                      + wintweaks.START_GPO_HINT + "; ' }", body)
        gpo = body[body.index("Build -ge 26100"):body.index("MDM_Policy_Config01_Start02")]
        # alle drei Rückgaben der Gruppenrichtlinie (Setup, Agent, Startskript) beginnen mit dem Hinweis
        self.assertEqual(gpo.count("return ($pinHint + "), 2)
        self.assertEqual(gpo.count("return $pinHint + $text"), 1)
        script = wintweaks.build_script({wintweaks.START_CLEAN})
        step = script[script.index("function Invoke-OkulaStep"):script.index("function Invoke-OkulaNative")]
        self.assertIn("if ($note -like 'Hinweis: *') {", step)
        self.assertIn("$script:OkulaHint++", step)
        self.assertIn('Write-OkulaLog "Hinweis $Label ($($note.Substring(9)))"', step)
        self.assertEqual(len("Hinweis: "), 9)
        self.assertEqual(len("Hinweis "), len("ok      "))                               # Spalte wie ok/FEHLER
        self.assertLess(step.index("$script:OkulaHint++"), step.index("$script:OkulaOk++"))
        self.assertIn("{1} mit Hinweis, {2} mit Fehler", script)
        self.assertIn("{1} mit Hinweis, {2} mit Fehler", wintweaks.build_later_script({"apps_xbox"}))

    def test_tooltip_help_and_direct_install(self):
        self.assertIn(wintweaks.START_GPO_HINT, wintweaks.BY_KEY[wintweaks.START_CLEAN].tooltip)
        help_text = (ROOT / "okula_recovery/help_window.py").read_text(encoding="utf-8")
        self.assertIn("stufenweise frei", help_text)
        self.assertIn("Bereitstellungspaket", help_text)
        clean = wintweaks.choice("Clean", wintweaks.TEMPLATES["Clean"])
        plan = winsetup.Plan("abcd", [], "sources/install.wim", False, tweak=clean)
        with mock.patch.object(wintweaks, "start_pins_ppkg", lambda: None):
            self.assertIn("Hinweis Startmenü: " + wintweaks.START_GPO_HINT, winsetup.describe(plan))
        with mock.patch.object(wintweaks, "start_pins_ppkg", lambda: b"PKG"):
            self.assertFalse(any(line.startswith("Hinweis Startmenü") for line in winsetup.describe(plan)))
        no_start = winsetup.Plan("abcd", [], "sources/install.wim", False,
                                 tweak=wintweaks.choice("Keine", ["show_ext"]))
        self.assertFalse(any(line.startswith("Hinweis Startmenü") for line in winsetup.describe(no_start)))
        # install.cmd: „gesetzt“ heisst nicht „wirkt“
        cmd = winsetup.install_cmd("abcd", 1, "sources/install.wim", False, "de-DE",
                                   tweak={"start_pins": wintweaks.start_pins_json()})
        self.assertIn("Wirkung: siehe Zeile Startmenue beim ersten Start", cmd)
        self.assertTrue(cmd.isascii())


def convert(line: str) -> str:
    """ConvertTo-OkulaLogLine in Python nachgebildet (gleiche Muster, gleiche Gruppen)."""
    for pattern, day, month in ((wintweaks.LOG_DATE_DE, 1, 2), (wintweaks.LOG_DATE_US, 2, 1)):
        m = re.match(pattern, line)
        if m:
            return (f"{int(m.group(3)):04d}-{int(m.group(month)):02d}-{int(m.group(day)):02d} "
                    f"{int(m.group(4)):02d}:{m.group(5)}:{m.group(6)}  {m.group(7)}")
    return line


class LogFormatTest(unittest.TestCase):
    """Protokoll der Direktinstallation: Zeilen von cmd einheitlich, Datei UTF-8 mit BOM, nichts geht verloren."""

    def test_cmd_lines_converted(self):
        self.assertEqual(convert("25.11.2026  8:28:45,79  ok      Vor dem ersten Start gesetzt - Setup-Umgebung"),
                         "2026-11-25 08:28:45  ok      Vor dem ersten Start gesetzt - Setup-Umgebung")
        self.assertEqual(convert("05.01.2027 14:03:09.12  Hinweis Richtlinien nicht vollstaendig gesetzt"),
                         "2027-01-05 14:03:09  Hinweis Richtlinien nicht vollstaendig gesetzt")
        self.assertEqual(convert("Tue 11/25/2026  8:28:45.79  Software wird noch installiert"),
                         "2026-11-25 08:28:45  Software wird noch installiert")
        # Zeilen des Skripts und andere bleiben, wie sie sind
        for line in ("2026-11-25 08:35:04  ok      Cortana aus", "", "----- Ende -----", "Startmenü: ok"):
            self.assertEqual(convert(line), line)

    def test_install_and_setupcomplete_lines_match_pattern(self):
        """Jede Zeile, die cmd mit Datum ins Protokoll schreibt, beginnt mit „%DATE% %TIME%  “ – nach Ersetzen mit
        dem Befund-Format greift das Muster."""
        texts = [winsetup.install_cmd("abcd", 1, "sources/install.wim", False, "de-DE",
                                      tweak={"start_pins": wintweaks.start_pins_json(), "widgets": True}),
                 winsetup.setupcomplete_cmd("abcd", software=True, tweak=True)]
        lines = [line for text in texts for line in text.splitlines()
                 if deploy.TWEAK_NAME in line or "%TWLOG%" in line]
        written = [line for line in lines if " echo " in line and "%DATE%" in line]
        self.assertGreaterEqual(len(written), 5)
        for line in written:
            out = line[line.index(" echo ") + 6:].replace("%DATE%", "25.11.2026").replace("%TIME%", " 8:28:45,79")
            self.assertTrue(convert(out).startswith("2026-11-25 08:28:45  "), out)

    def test_script_rewrites_log_once_with_bom(self):
        for script in (wintweaks.build_script({"cortana"}), wintweaks.build_later_script({"apps_xbox"})):
            fn = script[script.index("function ConvertTo-OkulaLogLine"):script.index("function Write-OkulaLog")]
            self.assertIn(f"@(@('{wintweaks.LOG_DATE_DE}', 1, 2), @('{wintweaks.LOG_DATE_US}', 2, 1))", fn)
            init = fn[fn.index("function Initialize-OkulaLog"):]
            # schon mit BOM: nichts tun; sonst lesen, angleichen, mit BOM schreiben (über Zwischendatei)
            self.assertIn("$bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { return }", init)
            self.assertIn("ConvertTo-OkulaLogLine $l", init)
            self.assertIn("[IO.File]::WriteAllText($tmp, ($lines -join \"`r`n\"), (New-Object Text.UTF8Encoding $true))",
                          init)
            self.assertIn("Move-Item -LiteralPath $tmp -Destination $OkulaLog -Force", init)
            self.assertIn("} catch { }", init)                                          # Protokoll nie Abbruchgrund
            write = script[script.index("function Write-OkulaLog"):]
            self.assertIn("if (-not $script:OkulaLogReady) { Initialize-OkulaLog }", write)
            self.assertLess(script.index("function Write-OkulaLog"), script.index("Write-OkulaLog '-----"))
        for pattern in (wintweaks.LOG_DATE_DE, wintweaks.LOG_DATE_US):
            self.assertNotIn("'", pattern)
            self.assertTrue(pattern.isascii())

    def test_setupcomplete_writes_before_script(self):
        """Nach dem Skript schreibt cmd nichts mehr ins Protokoll (die Zeile bliebe im Format von cmd)."""
        sc = winsetup.setupcomplete_cmd("abcd", software=True, tweak=True)
        tw = sc.index('cmd /c "%OKULA_TW%"')
        self.assertNotIn(deploy.TWEAK_NAME + ".log", sc[tw:])
        self.assertIn(f"Neustart {software.REBOOT_DELAY} s nach Windows anpassen", sc[:tw])
        self.assertLess(sc.index('if not errorlevel 1 set "OKULA_NEUSTART=1"'),
                        sc.index("if defined OKULA_NEUSTART >>"))
        self.assertLess(sc.index("if defined OKULA_NEUSTART >>"), tw)
        self.assertLess(tw, sc.index("shutdown /r"))


class DocsTest(unittest.TestCase):
    def test_docs_mention_b022(self):
        for name in ("docs/AENDERUNGEN.md", "docs/TECHNIK.md", "docs/TESTS.md"):
            self.assertIn("B-022", (ROOT / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
