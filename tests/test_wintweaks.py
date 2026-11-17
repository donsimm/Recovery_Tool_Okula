"""Windows anpassen (I-039): Optionen, Vorlagen, Skript-Erzeugung, Startmechanismus auf Probe-Daten, Auftrag."""

import base64
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, deploy, jobs, wintweaks

PASSWORD = "Geh'eim‘Pass„1“"   # mit Anführungszeichen, die PowerShell als Stringende liest

# je Option: was im Skript stehen muss
EXPECTED = {
    "apps_xbox": ["'Microsoft.Xbox*'", "'Microsoft.GamingApp'"],
    "apps_bing": ["'Microsoft.Bing*'"],
    "apps_zune": ["'Microsoft.ZuneMusic'", "'Microsoft.ZuneVideo'"],
    "apps_solitaire": ["'Microsoft.MicrosoftSolitaireCollection'"],
    "apps_people": ["'Microsoft.People'"],
    "apps_phone": ["'Microsoft.YourPhone'"],
    "apps_camera": ["'Microsoft.WindowsCamera'"],
    "apps_office": ["'Microsoft.MicrosoftOfficeHub'"],
    "apps_3d": ["'Microsoft.Microsoft3DViewer'", "'Microsoft.MSPaint'", "'Microsoft.MixedReality.Portal'"],
    "apps_help": ["'Microsoft.WindowsFeedbackHub'", "'Microsoft.Getstarted'", "'Microsoft.GetHelp'"],
    "apps_store": ["'Microsoft.WindowsStore'"],
    "no_reinstall": ["CloudContent' 'DisableWindowsConsumerFeatures' 1", "'SilentInstalledAppsEnabled'",
                     "'PreInstalledAppsEnabled'", "'OemPreInstalledAppsEnabled'", "Invoke-OkulaAllUsers"],
    "onedrive": ["OneDriveSetup.exe", "'/uninstall'", "'DisableFileSyncNGSC' 1", "'OneDriveSetup'"],
    "cortana": ["'AllowCortana' 0"],
    "wu_off": ["WindowsUpdate\\AU' 'NoAutoUpdate' 1"],
    "wu_drivers": ["'ExcludeWUDriversInQualityUpdate' 1", "DriverSearching' 'SearchOrderConfig' 0"],
    "store_updates": ["WindowsStore' 'AutoDownload' 2"],
    "power_high": ["8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "'/setactive'", "'/duplicatescheme'"],
    "power_never": ["'monitor-timeout-ac'", "'monitor-timeout-dc'", "'standby-timeout-ac'", "'standby-timeout-dc'"],
    "hibernate_off": ["@('/hibernate', 'off')"],
    "fastboot_off": ["'HiberbootEnabled' 0"],
    "lockscreen_off": ["Personalization' 'NoLockScreen' 1"],
    "tips_off": ["'SubscribedContent-338388Enabled'", "'SystemPaneSuggestionsEnabled' 0", "'SoftLandingEnabled' 0",
                 "PushNotifications\" 'ToastEnabled' 0"],
    "sticky_off": ["StickyKeys\" 'Flags' '506' 'String'", "Keyboard Response\" 'Flags' '122' 'String'"],
    "telemetry": ["'AllowTelemetry' 0", "'DiagTrack'"],
    "adid_off": ["'DisabledByGroupPolicy' 1"],
    "location_off": ["'DisableLocation' 1"],
    "wer_off": ["Windows Error Reporting' 'Disabled' 1"],
    "bing_search_off": ["'DisableWebSearch' 1", "'ConnectedSearchUseWeb' 0", "'BingSearchEnabled' 0"],
    "show_ext": ["'HideFileExt' 0"],
    "show_hidden": ["'Hidden' 1"],
    "explorer_thispc": ["'LaunchTo' 1"],
    "desktop_icons": ["NewStartPanel", "'{20D04FE0-3AEA-1069-A2D8-08002B30309D}' 0",
                      "'{F02C1A0D-BE21-4350-88B0-7367FC96EF3C}' 0"],
    "taskbar_clean": ["'SearchboxTaskbarMode' 0", "'ShowTaskViewButton' 0"],
    "svc_search": ["'WSearch'"],
    "svc_xbox": ["'XblAuthManager'", "'XblGameSave'", "'XboxNetApiSvc'"],
    "svc_sysmain": ["'SysMain'"],
    "svc_remotereg": ["'RemoteRegistry'"],
    "svc_spooler": ["'Spooler'"],
    "autologon": ["'AutoAdminLogon' '1' 'String'", "'DefaultUserName'", "'DefaultPassword'", "'DefaultDomainName'",
                  "Get-LocalUser"],
}


def steps(script: str) -> dict[str, str]:
    """Bausteine des Skripts: Beschriftung → Inhalt."""
    out = {}
    for m in re.finditer(r"^Invoke-OkulaStep '((?:[^']|'')*)' \{\n(.*?)\n\}$", script, re.MULTILINE | re.DOTALL):
        out[m.group(1).replace("''", "'")] = m.group(2)
    return out


class OptionsTemplatesTest(unittest.TestCase):
    def test_every_option_has_a_test_and_groups(self):
        self.assertEqual(set(EXPECTED), set(wintweaks.KEYS))
        self.assertEqual(list(wintweaks.by_group()), list(wintweaks.GROUPS))
        self.assertEqual(len(wintweaks.APP_KEYS), 11)
        self.assertEqual([o.label for o in wintweaks.by_group()["Dienste"]],
                         ["Windows Search", "Xbox-Dienste", "SysMain", "Remote-Registrierung", "Druckwarteschlange"])

    def test_templates(self):
        player = wintweaks.template_keys("Player")
        self.assertEqual(set(wintweaks.KEYS) - player, {"apps_camera", "svc_spooler"})
        self.assertIn(wintweaks.AUTOLOGON, player)
        laptop = wintweaks.template_keys("Laptop")
        self.assertEqual({k for k in laptop if k.startswith("apps_")}, set(wintweaks.APP_KEYS) - {"apps_camera",
                                                                                                    "apps_store"})
        self.assertTrue({"no_reinstall", "cortana"} <= laptop)
        self.assertNotIn("onedrive", laptop)
        self.assertFalse(laptop & {"wu_off", "wu_drivers", "store_updates"})                       # Updates nicht
        self.assertEqual({o.key for o in wintweaks.by_group(laptop)["Betrieb"]},
                         {"fastboot_off", "tips_off", "sticky_off"})
        for group in ("Datenschutz", "Explorer und Desktop"):                                       # alles
            self.assertEqual(wintweaks.by_group(laptop)[group], wintweaks.by_group()[group])
        self.assertEqual({o.key for o in wintweaks.by_group(laptop)["Dienste"]}, {"svc_xbox", "svc_remotereg"})
        self.assertNotIn(wintweaks.AUTOLOGON, laptop)
        self.assertEqual(wintweaks.template_keys("Keine"), frozenset())
        self.assertEqual(wintweaks.TEMPLATE_NAMES, ("Player", "Laptop", "Keine"))

    def test_template_label_changed(self):
        player = set(wintweaks.template_keys("Player"))
        self.assertEqual(wintweaks.template_label("Player", player), "Player")
        self.assertEqual(wintweaks.template_label("Player", player - {"cortana"}), "Player (geändert)")
        self.assertEqual(wintweaks.template_label("Laptop", player), "Laptop (geändert)")
        self.assertEqual(wintweaks.template_label("Keine", {"cortana"}), "keine")

    def test_check_autologon_needs_fields(self):
        self.assertEqual(wintweaks.check(set()), "Keine Einstellung gewählt.")
        self.assertIsNone(wintweaks.check({"cortana"}))
        player = wintweaks.template_keys("Player")
        self.assertIn("Benutzername und Passwort", wintweaks.check(player))
        self.assertIn("Benutzername und Passwort", wintweaks.check(player, "Okula", ""))
        self.assertIn("Benutzername und Passwort", wintweaks.check(player, "  ", "x"))
        self.assertIsNone(wintweaks.check(player, "Okula", "x"))
        self.assertIn("Steuerzeichen", wintweaks.check(player, "Okula", "a\nb"))
        self.assertIn("Unbekannte", wintweaks.check({"utilman"}))
        with self.assertRaises(wintweaks.TweakError):
            wintweaks.build_script(player, "Okula", "")

    def test_summary_and_log_lines_without_password(self):
        sel = set(wintweaks.template_keys("Player")) - {"cortana"}
        text = wintweaks.summary(sel, "Player", "Okula")
        self.assertTrue(text.startswith("Vorlage Player (geändert): Apps (12), Updates (3), Betrieb (7)"), text)
        self.assertIn("Dienste (4), automatische Anmeldung (Okula)", text)
        lines = wintweaks.describe_lines(sel, "Okula")
        self.assertTrue(any(line.startswith("  Apps: Store-Apps entfernen: Xbox, ") for line in lines), lines)
        self.assertTrue(any("abschalten: Windows Search, Xbox-Dienste" in line for line in lines), lines)
        self.assertNotIn(PASSWORD, " ".join(lines) + text)


class ScriptTest(unittest.TestCase):
    def setUp(self):
        self.all = set(wintweaks.KEYS)
        self.script = wintweaks.build_script(self.all, "Okula", PASSWORD, "PC-1 „Test“", "Player", created=0)
        self.steps = steps(self.script)

    def test_each_option_its_own_step(self):
        self.assertEqual(len(self.steps), len(wintweaks.KEYS) + 1)        # + Aufräumen
        for key, needles in EXPECTED.items():
            label = next(lbl for lbl in self.steps if lbl.endswith(wintweaks.BY_KEY[key].label))
            for needle in needles:
                self.assertIn(needle, self.steps[label], f"{key}: {needle}")
        # einzeln: nur der gewählte Baustein
        one = wintweaks.build_script({"cortana"})
        self.assertEqual(list(steps(one)), ["Startskript und Gruppenrichtlinie aufräumen", "Cortana aus"])
        self.assertNotIn("NoAutoUpdate", one)

    def test_errors_do_not_stop_the_rest(self):
        # jeder Baustein läuft in Invoke-OkulaStep (try/catch, Fehler ins Protokoll), Store-Apps zuletzt
        self.assertIn("function Invoke-OkulaStep", self.script)
        self.assertRegex(self.script, r"catch \{\n\s+\$script:OkulaFailed\+\+\n\s+Write-OkulaLog \"FEHLER")
        labels = list(self.steps)
        first_app = next(i for i, lbl in enumerate(labels) if lbl.startswith("Store-Apps entfernen"))
        self.assertTrue(all(lbl.startswith("Store-Apps entfernen") for lbl in labels[first_app:]))
        self.assertTrue(self.script.rstrip().endswith("-f $script:OkulaOk, $script:OkulaFailed)"))
        # Frameworks und Treiber-Apps nie, vorinstallierte Pakete mit
        for keep in ("*VCLibs*", "*NET.Native*", "*UI.Xaml*", "*NVIDIA*", "*Realtek*", "*Intel*"):
            self.assertIn(f"'{keep}'", self.script)
        self.assertIn("$p.NonRemovable", self.script)
        self.assertIn("Remove-AppxPackage -Package $p.PackageFullName -AllUsers", self.script)
        self.assertIn("Remove-AppxProvisionedPackage -Online", self.script)

    def test_password_never_in_log_or_plain(self):
        self.assertNotIn(PASSWORD, self.script)
        self.assertIn(base64.b64encode(PASSWORD.encode()).decode(), self.script)
        log_lines = [line for line in self.script.splitlines() if "Write-OkulaLog" in line or "throw" in line]
        self.assertTrue(log_lines)
        for line in log_lines:
            self.assertNotIn("$secret", line)
            self.assertNotIn("DefaultPassword", line)
        logon = next(body for lbl, body in self.steps.items() if lbl == "Automatische Anmeldung")
        self.assertIn("$secret = $null", logon)
        self.assertTrue(logon.rstrip().endswith("'Konto ' + $user"))            # Rückgabe ohne Passwort
        self.assertIn("nicht vorhanden – nichts gesetzt", logon)

    def test_self_cleanup_first(self):
        s = self.script
        first_step = s.index("Invoke-OkulaStep 'Startskript und Gruppenrichtlinie aufräumen'")
        delete = s.index('Remove-Item -LiteralPath (Join-Path $OkulaStartup "$OkulaName.ps1")')
        self.assertLess(delete, s.index("function Restore-OkulaStart"))
        self.assertLess(first_step, s.index("Invoke-OkulaStep 'Windows Update aus'"))
        self.assertIn(f"$OkulaName = '{deploy.TWEAK_NAME}'", s)
        self.assertIn(f"$saved = $file + '{deploy.TWEAK_AFTER}'", s)
        self.assertIn("Group Policy", s)
        self.assertIn("State\\Machine\\Scripts\\Startup", s)
        self.assertIn(r"C:\Windows\Temp\okula-windows-anpassen.log", s)

    def test_quoting_and_balance(self):
        self.assertEqual(wintweaks.ps_quote("a'b‘c"), "'a''b‘‘c'")
        self.assertIn("Explorer öffnet „Dieser PC“", self.script)
        self.assertEqual(self.script.count("{"), self.script.count("}"))
        self.assertEqual(self.script.count("("), self.script.count(")"))
        self.assertNotIn("„Test“", self.script)                     # Gerätename gefiltert (nur im Kommentar)
        self.assertIn("Gerät: PC-1 Test", self.script)

    @unittest.skipUnless(shutil.which("pwsh"), "braucht PowerShell (pwsh)")
    def test_powershell_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.ps1"
            path.write_text(self.script, encoding="utf-8-sig")
            cmd = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
                   f"'{path}', [ref]$null, [ref]$e); $e | ForEach-Object {{ $_.ToString() }}")
            out = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
            self.assertEqual(out.stdout.strip(), "")


class StartMechanismTest(unittest.TestCase):
    """Startskript der lokalen Gruppenrichtlinie auf einer Probe-Windows-Partition (Verzeichnis)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Windows/System32/config").mkdir(parents=True)
        (self.root / "Windows/System32/config/SYSTEM").write_bytes(b"regf")
        self.gp = self.root / "Windows/System32/GroupPolicy"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_windows(self):
        res = deploy.install_startup_script(self.root, "Write-Host 1\n")
        self.assertEqual(res, {"replaced": False, "gpo": False, "version": 1})
        gpt = (self.gp / "gpt.ini").read_bytes().decode()
        self.assertIn("[General]\r\n", gpt)
        self.assertIn(f"gPCMachineExtensionNames=[{deploy.SCRIPTS_CSE}{deploy.SCRIPTS_TOOL}]\r\n", gpt)
        self.assertIn("Version=1\r\n", gpt)
        raw = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()
        self.assertTrue(raw.startswith(b"\xff\xfe"))                                   # UTF-16 wie gpedit
        self.assertEqual(raw[2:].decode("utf-16-le"), "[Startup]\r\n0CmdLine=okula-windows-anpassen.cmd\r\n"
                                                      "0Parameters=\r\n")
        startup = self.gp / "Machine/Scripts/Startup"
        self.assertEqual((startup / deploy.TWEAK_PS1).read_bytes(), b"\xef\xbb\xbfWrite-Host 1\r\n")
        cmd = (startup / deploy.TWEAK_CMD).read_bytes()
        self.assertTrue(cmd.isascii())
        self.assertIn(b'-ExecutionPolicy Bypass -File "%~dp0okula-windows-anpassen.ps1"', cmd)
        self.assertIn(b'del /f /q "%~f0"', cmd)                                           # Notfall: räumt auf
        self.assertIn(b"FEHLER", cmd)
        # nichts von vorher → nach dem Lauf löschen (keine „nachher“-Dateien)
        self.assertFalse((self.gp / ("gpt.ini" + deploy.TWEAK_AFTER)).exists())
        self.assertFalse((self.gp / ("Machine/Scripts/scripts.ini" + deploy.TWEAK_AFTER)).exists())

    def test_existing_policy_kept_and_restored(self):
        (self.gp / "Machine/Scripts").mkdir(parents=True)
        (self.gp / "Machine/Registry.pol").write_bytes(b"PReg\x01\x00\x00\x00")
        orig_gpt = ("[General]\r\ngPCFunctionalityVersion=2\r\ngPCMachineExtensionNames=[{35378EAC-683F-11D2-A89A-"
                    "00C04FBBCFA2}{D02B1F72-3407-48AE-BA88-E8213C6761F1}]\r\ngPCUserExtensionNames=[{X}]\r\n"
                    "Version=131074\r\n").encode()
        (self.gp / "gpt.ini").write_bytes(orig_gpt)
        orig_ini = "\r\n[Startup]\r\n0CmdLine=firma.cmd\r\n0Parameters=/q\r\n[Shutdown]\r\n0CmdLine=aus.cmd\r\n" \
                   "0Parameters=\r\n"
        orig_ini_bytes = b"\xff\xfe" + orig_ini.encode("utf-16-le")
        (self.gp / "Machine/Scripts/scripts.ini").write_bytes(orig_ini_bytes)
        res = deploy.install_startup_script(self.root, "A")
        self.assertEqual(res, {"replaced": False, "gpo": True, "version": 131075})       # Computer-Teil +1
        gpt = (self.gp / "gpt.ini").read_text()
        self.assertIn("gPCMachineExtensionNames=[{35378EAC-683F-11D2-A89A-00C04FBBCFA2}{D02B1F72-3407-48AE-BA88-"
                      f"E8213C6761F1}}][{deploy.SCRIPTS_CSE}{deploy.SCRIPTS_TOOL}]", gpt)
        self.assertIn("gPCUserExtensionNames=[{X}]", gpt)
        self.assertIn("Version=131075", gpt)
        ini = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()[2:].decode("utf-16-le")
        self.assertIn("0CmdLine=firma.cmd\r\n0Parameters=/q\r\n1CmdLine=okula-windows-anpassen.cmd\r\n"
                      "1Parameters=\r\n[Shutdown]\r\n0CmdLine=aus.cmd", ini)
        # Stand nach dem Lauf: Originale, gpt.ini mit Version +2 (Windows verarbeitet die Richtlinie neu)
        self.assertEqual((self.gp / ("Machine/Scripts/scripts.ini" + deploy.TWEAK_AFTER)).read_bytes(),
                         orig_ini_bytes)
        after = (self.gp / ("gpt.ini" + deploy.TWEAK_AFTER)).read_bytes()
        self.assertEqual(after, orig_gpt.replace(b"Version=131074", b"Version=131076"))
        self.assertEqual((self.gp / "Machine/Registry.pol").read_bytes(), b"PReg\x01\x00\x00\x00")
        # erneut senden: nur das Skript wird ersetzt, kein zweiter Eintrag, Originale bleiben
        res = deploy.install_startup_script(self.root, "B")
        self.assertEqual(res, {"replaced": True, "gpo": True, "version": 131075})
        ini2 = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()[2:].decode("utf-16-le")
        self.assertEqual(ini2, ini)
        self.assertEqual((self.gp / ("gpt.ini" + deploy.TWEAK_AFTER)).read_bytes(), after)
        self.assertEqual((self.gp / "Machine/Scripts/Startup" / deploy.TWEAK_PS1).read_bytes(), b"\xef\xbb\xbfB")

    def test_existing_ansi_scripts_ini_and_case(self):
        (self.gp / "MACHINE/scripts").mkdir(parents=True)
        (self.gp / "GPT.INI").write_bytes(b"[General]\r\nVersion=65535\r\n")
        (self.gp / "MACHINE/scripts/Scripts.ini").write_bytes(b"[Shutdown]\r\n0CmdLine=x.cmd\r\n0Parameters=\r\n")
        res = deploy.install_startup_script(self.root, "A")
        self.assertEqual(res["version"], 1)                                     # Überlauf: Computer-Teil neu
        self.assertEqual(sorted(p.name for p in self.gp.iterdir()), ["GPT.INI", "GPT.INI" + deploy.TWEAK_AFTER,
                                                                     "MACHINE"])
        ini = (self.gp / "MACHINE/scripts/Scripts.ini").read_bytes()
        self.assertEqual(ini, b"[Shutdown]\r\n0CmdLine=x.cmd\r\n0Parameters=\r\n[Startup]\r\n"
                              b"0CmdLine=okula-windows-anpassen.cmd\r\n0Parameters=\r\n")
        self.assertTrue((self.gp / "MACHINE/scripts/Startup" / deploy.TWEAK_PS1).is_file())

    def test_helpers(self):
        self.assertEqual(deploy.merge_extensions(""), f"[{deploy.SCRIPTS_CSE}{deploy.SCRIPTS_TOOL}]")
        merged = deploy.merge_extensions(f"[{deploy.SCRIPTS_CSE}{{AAAAAAAA-0000-0000-0000-000000000000}}]")
        self.assertEqual(merged, f"[{deploy.SCRIPTS_CSE}{deploy.SCRIPTS_TOOL}{{AAAAAAAA-0000-0000-0000-"
                                 "000000000000}]")
        self.assertEqual(deploy.merge_extensions(merged), merged)
        self.assertEqual(deploy.bump_version(0x00020005, 2), 0x00020007)
        self.assertEqual(deploy.bump_version(0x0002FFFF, 1), 0x00020001)
        self.assertFalse(deploy.scripts_ini_has("[Shutdown]\r\n0CmdLine=okula-windows-anpassen.cmd\r\n"))
        self.assertTrue(deploy.scripts_ini_has("[startup]\r\n3cmdline=C:\\x\\okula-windows-anpassen.cmd\r\n"))

    def test_link_refused(self):
        (self.root / "anderswo").mkdir()
        (self.gp).symlink_to(self.root / "anderswo")
        with self.assertRaises(deploy.ImagingError):
            deploy.install_startup_script(self.root, "A")


class FakeMounts:
    def __init__(self, roots, error=None):
        self.roots, self.error = roots, error

    def __call__(self, write=False):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return None

    def get(self, dev):
        if self.error:
            raise deploy.ImagingError(self.error)
        return self.roots[dev]


class TweakAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.parts = [{"path": "/dev/sda3", "fstype": "ntfs", "size": 1 << 35}]

    def tearDown(self):
        self.tmp.cleanup()

    def run_tweak(self, mounts):
        with mock.patch.object(deploy, "_candidates", lambda disk: self.parts), \
                mock.patch.object(deploy.filebackup, "Mounts", mounts), \
                mock.patch.object(deploy.subprocess, "run"):
            return deploy.tweak({"disk": "/dev/sda", "script": "Write-Host 1"}, log=lambda *_a: None)

    def test_no_windows_refused(self):
        with self.assertRaisesRegex(deploy.ImagingError, "Kein Windows auf /dev/sda gefunden"):
            self.run_tweak(FakeMounts({"/dev/sda3": self.root}))
        self.assertEqual(list(self.root.iterdir()), [])                         # nichts angelegt

    def test_fast_startup_message(self):
        msg = "Windows ist im Ruhezustand bzw. Schnellstart – Windows starten und vollständig herunterfahren"
        with self.assertRaisesRegex(deploy.ImagingError, "Ruhezustand bzw. Schnellstart"):
            self.run_tweak(FakeMounts({}, msg))

    def test_windows_gets_script(self):
        (self.root / "Windows/System32/config").mkdir(parents=True)
        (self.root / "Windows/System32/config/SYSTEM").write_bytes(b"regf")
        res = self.run_tweak(FakeMounts({"/dev/sda3": self.root}))
        self.assertEqual((res["type"], res["part"], res["state"], res["replaced"]), ("done", "/dev/sda3", "installed",
                                                                                    False))
        self.assertTrue((self.root / "Windows/System32/GroupPolicy/Machine/Scripts/Startup" /
                         deploy.TWEAK_PS1).is_file())
        with self.assertRaisesRegex(deploy.ImagingError, "Keine Einstellungen"):
            deploy.tweak({"disk": "/dev/sda", "script": " "})


class TweakJobTest(unittest.TestCase):
    def test_job_log_without_password(self):
        script = wintweaks.build_script(wintweaks.template_keys("Player"), "Okula", PASSWORD)
        sent = {}

        def fake(ip, key, disk, s, port):
            sent["script"] = s
            return {"type": "done", "part": "/dev/sda3", "state": "generalized", "replaced": False, "gpo": True}

        results = []
        jm = jobs.JobManager()
        with mock.patch.object(agentclient, "tweak", fake):
            job = jm.start("dev", "tweak", "/dev/sda", "Windows anpassen (Vorlage Player)",
                           jobs.tweak_work("127.0.0.1", b"k", 1, "/dev/sda", script,
                                           wintweaks.describe_lines(wintweaks.template_keys("Player"), "Okula"),
                                           lambda j, p, e: results.append(e)))
            for _ in range(100):
                if not job.running:
                    break
                time.sleep(0.05)
        self.assertEqual(job.state, jobs.DONE)
        self.assertEqual(results, [None])
        self.assertEqual(sent["script"], script)
        log = "\n".join(job.log)
        self.assertEqual(job.label, "Windows anpassen")
        self.assertIn("Einstellungen werden übertragen …", log)
        self.assertIn("vorhandene lokale Gruppenrichtlinie bleibt erhalten", log)
        self.assertIn("generalisiert", log)
        self.assertIn("automatisch als „Okula“", log)
        self.assertNotIn(PASSWORD, log)
        self.assertNotIn(base64.b64encode(PASSWORD.encode()).decode(), log)

    def test_old_agent(self):
        class Sock:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return None

            def settimeout(self, _t):
                pass

        with mock.patch.object(agentclient, "_connect", lambda *a: Sock()), \
                mock.patch.object(agentclient.wire, "send_json", lambda *a: None), \
                mock.patch.object(agentclient.wire, "recv_json",
                                  lambda *a: {"type": "error", "message": "Unbekannter Befehl: tweak"}):
            with self.assertRaisesRegex(agentclient.AgentError, "Agent zu alt"):
                agentclient.tweak("127.0.0.1", b"k", "/dev/sda", "x", 1)


def gtk_available() -> bool:
    """GTK mit Bildschirm? Erst in einem eigenen Prozess prüfen (ohne Meldungen auf stderr)."""
    probe = ("import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk; "
             "raise SystemExit(0 if Gtk.init_check(None)[0] else 1)")
    try:
        if subprocess.run([sys.executable, "-c", probe], capture_output=True, timeout=30).returncode != 0:
            return False
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        return bool(Gtk.init_check(None)[0])
    except (ImportError, ValueError, TypeError, OSError, subprocess.TimeoutExpired):
        return False


@unittest.skipUnless(gtk_available(), "braucht GTK mit Bildschirm")
class DialogTest(unittest.TestCase):
    def test_templates_set_checks_and_autologon_blocks_send(self):
        from okula_recovery.automation_tab import WindowsTweakDialog
        dlg = WindowsTweakDialog(None, "PC-1")
        try:
            self.assertEqual(set(dlg.checks), set(wintweaks.KEYS))
            self.assertFalse(dlg.btn.get_sensitive())                     # nichts gewählt
            dlg.combo.set_active_id("Player")
            self.assertEqual(dlg.selected(), set(wintweaks.template_keys("Player")))
            self.assertEqual(dlg.state.get_text(), "Vorlage: Player")
            self.assertFalse(dlg.btn.get_sensitive())                     # automatische Anmeldung ohne Felder
            dlg.user.set_text("Okula")
            dlg.password.set_text("x")
            self.assertTrue(dlg.btn.get_sensitive())
            self.assertEqual(dlg.credentials(), ("Okula", "x"))
            dlg.checks["cortana"].set_active(False)
            self.assertEqual(dlg.state.get_text(), "Vorlage: Player (geändert)")
            dlg.combo.set_active_id("Laptop")
            self.assertEqual(dlg.selected(), set(wintweaks.template_keys("Laptop")))
            self.assertFalse(dlg.user.get_sensitive())
            dlg.combo.set_active_id("Keine")
            self.assertEqual(dlg.selected(), set())
            self.assertFalse(dlg.btn.get_sensitive())
        finally:
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
