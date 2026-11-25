"""Ä-046: „Windows anpassen“ beim Aufsetzen mitgeben – OS installieren (Direktinstallation), Image zurückspielen →
Danach anpassen, Automatisierung (auch Vorlagen). Ohne root, ohne GTK (Dialogteile nur mit Bildschirm)."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from okula_recovery import deploy, software, winsetup, wintweaks, winunattend

CLEAN = wintweaks.choice("Clean", wintweaks.TEMPLATES["Clean"])


class ChoiceTest(unittest.TestCase):
    def test_choice_drops_autologon_and_unknown(self):
        c = wintweaks.choice("Player", list(wintweaks.TEMPLATES["Player"]) + ["gibt-es-nicht"])
        self.assertNotIn(wintweaks.AUTOLOGON, c["keys"])
        self.assertNotIn("gibt-es-nicht", c["keys"])
        self.assertEqual(c["keys"], [k for k in wintweaks.KEYS if k in c["keys"]])     # Reihenfolge wie im Dialog
        self.assertEqual(wintweaks.choice_label(c), "Player")            # ohne Anmeldung gilt als unverändert
        self.assertIsNone(wintweaks.choice("Clean", []))
        self.assertIsNone(wintweaks.choice("Clean", [wintweaks.AUTOLOGON]))
        self.assertEqual(wintweaks.choice("Gibt es nicht", ["show_ext"])["template"], wintweaks.NO_TEMPLATE)

    def test_clean_choice_and_texts(self):
        for bad in (None, "Clean", {"keys": "show_ext"}, {"template": "Clean"}, {"keys": []}):
            self.assertIsNone(wintweaks.clean_choice(bad))
        self.assertEqual(wintweaks.clean_choice({**CLEAN, "device": "PC-1"}), CLEAN)
        self.assertEqual(wintweaks.choice_label(CLEAN), "Clean")
        changed = wintweaks.choice("Clean", CLEAN["keys"] + ["show_ext"])
        self.assertEqual(wintweaks.choice_label(changed), "Clean (geändert)")
        self.assertEqual(wintweaks.choice_label(wintweaks.choice("Keine", ["show_ext"])), "keine")
        self.assertTrue(wintweaks.choice_summary(CLEAN).startswith("Vorlage Clean: Apps ("))
        self.assertEqual(wintweaks.choice_summary(None), "")
        self.assertIn("– wird beim ersten Windows-Start umgesetzt", wintweaks.choice_history(CLEAN))

    def test_choice_script_and_offline(self):
        script = wintweaks.choice_script(CLEAN, "PC-1", created=0)
        self.assertIn("Vorlage Clean -----", script)
        self.assertNotIn("Vorlage Clean (geändert)", script)
        self.assertNotIn("AutoAdminLogon", script)
        self.assertEqual(wintweaks.choice_offline(CLEAN), wintweaks.offline_request(CLEAN["keys"]))
        self.assertIn("start_pins", wintweaks.choice_offline(CLEAN))
        with self.assertRaises(wintweaks.TweakError):
            wintweaks.choice_script(None)
        self.assertEqual(wintweaks.choice_offline(None), {})

    def test_marker_from_setup(self):
        body = wintweaks.BY_KEY[wintweaks.START_CLEAN].body
        self.assertIn("$offline['source'] -eq 'setup'", body)
        self.assertIn("schon bei der Installation vor dem", body)
        # Setup-Fall kommt vor der Meldung des Agents (B-020) – Rückgabetext, nicht der Kommentar davor
        self.assertLess(body.index("'source'"), body.index("Startmenü schon beim Senden vor dem"))


OFFLINE_ALL = {"start_pins": wintweaks.start_pins_json(), "widgets": True, "lock_screen_off": True,
               "consumer_off": True}


class InstallCmdTest(unittest.TestCase):
    def cmd(self, **kw):
        return winsetup.install_cmd("abcd", 1, "sources/install.wim", False, "de-DE", **kw)

    def test_offline_policies_after_dism(self):
        cmd = self.cmd(tweak=OFFLINE_ALL)
        self.assertTrue(cmd.isascii())
        load = cmd.index('reg load HKLM\\OKULASW "%W%:\\Windows\\System32\\config\\SOFTWARE"')
        self.assertLess(cmd.index("dism /Apply-Image"), load)
        self.assertLess(load, cmd.index("reg unload HKLM\\OKULASW"))
        self.assertLess(cmd.index("reg unload HKLM\\OKULASW"), cmd.index("echo Okula: fertig"))
        for key, name, data in ((deploy.EXPLORER_KEY, "ConfigureStartPins", "/t REG_DWORD /d 1"),
                                (deploy.EXPLORER_KEY, "ConfigureStartPinsJSON",
                                 '/t REG_EXPAND_SZ /d "%%ProgramData%%\\Okula\\StartPins.json"'),
                                (deploy.DSH_KEY, "AllowNewsAndInterests", "/t REG_DWORD /d 0"),
                                (deploy.LOCK_KEY, "NoLockScreen", "/t REG_DWORD /d 1"),
                                (deploy.CLOUD_KEY, "DisableWindowsConsumerFeatures", "/t REG_DWORD /d 1")):
            self.assertIn(f'reg add "HKLM\\OKULASW\\{key}" /v {name} {data} /f', cmd)
        # Startmenü erst ab 24H2 (Build aus dem Hive), Marke für das Skript: nichts umzubenennen
        self.assertIn('if /i "%%a"=="CurrentBuild" set TWB=%%b', cmd)
        self.assertIn(f"if %TWB% LSS {deploy.START_GPO_BUILD} goto twaltstart", cmd)
        self.assertIn('okula\\tweak\\StartPins.json" "%W%:\\ProgramData\\Okula\\StartPins.json"', cmd)
        self.assertIn(f'> "%W%:\\ProgramData\\Okula\\{deploy.START_MARKER}" echo stamp=setup', cmd)
        self.assertIn("echo source=setup", cmd)
        # Fehler brechen die Installation nicht ab – nur Protokoll
        block = cmd[load:cmd.index(":twende")]
        self.assertNotIn("goto fehler", block)
        self.assertIn('>>"%TWLOG%" echo', block)
        self.assertIn('set "TWLOG=%W%:\\Windows\\Temp\\okula-windows-anpassen.log"', cmd)
        # Startskript wird mitkopiert
        self.assertIn('xcopy "%S%:\\okula\\gp" "%OKGP%\\"', cmd)
        self.assertLess(load, cmd.index('xcopy "%S%:\\okula\\gp"'))

    def test_only_chosen_values(self):
        cmd = self.cmd(tweak={"widgets": True})
        self.assertIn("AllowNewsAndInterests", cmd)
        for name in ("ConfigureStartPins", "NoLockScreen", "DisableWindowsConsumerFeatures", "twaltstart"):
            self.assertNotIn(name, cmd)
        empty = self.cmd(tweak={})                       # nichts vor der Anmeldung nötig, Startskript trotzdem
        self.assertNotIn("reg load", empty)
        self.assertIn('xcopy "%S%:\\okula\\gp"', empty)
        plain = self.cmd()
        self.assertNotIn("reg load", plain)
        self.assertNotIn("okula\\gp", plain)
        soft = self.cmd(software=True)
        self.assertIn('xcopy "%S%:\\okula\\software"', soft)
        self.assertIn('xcopy "%S%:\\okula\\gp"', soft)
        self.assertNotIn("reg load", soft)


class SetupCompleteTest(unittest.TestCase):
    def test_tweak_after_software_with_wait(self):
        sc = winsetup.setupcomplete_cmd("abcd", software=True, tweak=True)
        self.assertTrue(sc.isascii())
        sw = sc.index('if exist "%OKULA_SW%" cmd /c "%OKULA_SW%"')
        wait = sc.index(f'schtasks /query /tn "{software.TASK_NAME}"')
        tw = sc.index('cmd /c "%OKULA_TW%"')
        self.assertLess(sc.index(":ende"), sw)
        self.assertLess(sw, wait)
        self.assertLess(wait, tw)
        rounds = winsetup.SOFTWARE_WAIT_MIN * 60 // winsetup.SOFTWARE_WAIT_STEP
        self.assertIn(f"if %N% GEQ {rounds} goto anpassen", sc)
        self.assertIn("ping -n", sc)                    # timeout braucht eine Konsole
        self.assertNotIn("timeout ", sc)
        # Neustart der Software (3010) zurückstellen, erst ganz am Schluss wieder auslösen
        self.assertLess(sc.index("shutdown /a"), tw)
        self.assertLess(tw, sc.index("shutdown /r"))
        self.assertIn(deploy.TWEAK_CMD, sc)

    def test_tweak_alone_and_none(self):
        sc = winsetup.setupcomplete_cmd("abcd", tweak=True)
        self.assertIn('cmd /c "%OKULA_TW%"', sc)
        self.assertNotIn("schtasks", sc)
        self.assertNotIn("shutdown", sc)
        self.assertNotIn("OKULA_SW", sc)
        self.assertNotIn("OKULA_TW", winsetup.setupcomplete_cmd("abcd", software=True))
        self.assertNotIn("OKULA_TW", winsetup.setupcomplete_cmd("abcd"))


class FakeIso:
    def __init__(self):
        self.entries = [("bootmgr", SimpleNamespace(is_dir=False, size=10)),
                        ("sources/install.wim", SimpleNamespace(is_dir=False, size=1000))]

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return None

    def walk(self):
        return iter(self.entries)


class PlanTest(unittest.TestCase):
    def plan(self, opts=None, software_plan=None, tweak=CLEAN):
        with mock.patch.object(winsetup.udf.UdfImage, "open", lambda _p: FakeIso()), \
                mock.patch.object(software, "build_script", lambda entries, device="": "# Software"):
            return winsetup.plan("x.iso", 1, opts or winunattend.WinOptions(), software_plan, "PC-1", tweak)

    def test_files_on_setup_partition(self):
        plan = self.plan()
        self.assertEqual(plan.tweak, CLEAN)
        ini = plan.extra["okula/gp/Machine/Scripts/scripts.ini"]
        self.assertIn("0CmdLine=okula-windows-anpassen.cmd", ini)
        self.assertNotIn("okula-software", ini)
        start = "okula/gp/Machine/Scripts/Startup/"
        self.assertEqual(plan.extra[start + "okula-windows-anpassen.cmd"], deploy.TWEAK_CMD_TEXT)
        ps1 = plan.extra[start + "okula-windows-anpassen.ps1"]
        self.assertTrue(ps1.startswith("﻿"))
        self.assertIn("Vorlage Clean", ps1)
        self.assertIn("Gerät: PC-1", ps1)
        self.assertEqual(plan.extra["okula/tweak/StartPins.json"], wintweaks.start_pins_json())
        self.assertIn("reg load", plan.extra["okula/install.cmd"])
        self.assertIn('cmd /c "%OKULA_TW%"', plan.extra["okula/SetupComplete.cmd"])
        self.assertTrue(any("Windows anpassen (Vorlage Clean" in line for line in winsetup.describe(plan)))

    def test_software_first_in_scripts_ini(self):
        soft = SimpleNamespace(entries=[SimpleNamespace(label="VLC 3")],
                               files=[("file", "vlc-3/vlc.exe", 10, 0, "/nas/vlc.exe")])
        plan = self.plan(software_plan=soft)
        ini = plan.extra["okula/gp/Machine/Scripts/scripts.ini"]
        self.assertLess(ini.index("0CmdLine=okula-software.cmd"), ini.index("1CmdLine=okula-windows-anpassen.cmd"))
        sc = plan.extra["okula/SetupComplete.cmd"]
        self.assertLess(sc.index("OKULA_SW"), sc.index("OKULA_TW"))
        self.assertIn("schtasks", sc)
        self.assertTrue(any("nach der Software" in line for line in winsetup.describe(plan)))

    def test_without_choice_unchanged(self):
        with_none = self.plan(tweak=None)
        self.assertIsNone(with_none.tweak)
        self.assertNotIn("okula/gp/gpt.ini", with_none.extra)
        self.assertNotIn("okula/tweak/StartPins.json", with_none.extra)
        self.assertNotIn("reg load", with_none.extra["okula/install.cmd"])
        self.assertNotIn("OKULA_TW", with_none.extra["okula/SetupComplete.cmd"])
        # automatische Anmeldung allein ist beim Aufsetzen keine Auswahl
        self.assertIsNone(self.plan(tweak={"template": "Keine", "keys": [wintweaks.AUTOLOGON]}).tweak)

    def test_not_for_master_audit_mode(self):
        with self.assertRaisesRegex(winsetup.WinSetupError, "Audit-Modus"):
            self.plan(opts=winunattend.WinOptions(audit_mode=True))
        self.assertIsNone(self.plan(opts=winunattend.WinOptions(audit_mode=True), tweak=None).tweak)


class InstallJobLogTest(unittest.TestCase):
    """Log der Direktinstallation: Auswahl, Reihenfolge, Hinweis OEM-Schlüssel (B-013)."""

    def run_job(self, opts, soft_entries=()):
        from okula_recovery import agentclient, jobs
        plan = winsetup.Plan("abcd", [], "sources/install.wim", False, software=list(soft_entries), tweak=CLEAN)
        job = SimpleNamespace(cancel=None, log=[], phase="")
        lines = []
        jm_stub = SimpleNamespace(log=lambda _j, line: lines.append(line), progress=lambda *a, **k: None)
        with mock.patch.object(winsetup, "plan", lambda *a, **k: plan), \
                mock.patch.object(agentclient, "install_windows", lambda *a, **k: "0007"):
            work = jobs.install_work("127.0.0.1", b"k", 1, "x.iso", 1, opts, "/dev/sda", lambda *a: None,
                                     None, {**CLEAN, "device": "PC-1"})
            work(job, jm_stub)
        return lines

    def test_log_lines(self):
        lines = self.run_job(winunattend.WinOptions(product_key="AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"))
        text = "\n".join(lines)
        self.assertIn("Windows anpassen (Vorlage Clean", text)
        self.assertIn("vor dem ersten Start", text)
        self.assertIn("OEM-Schlüssel", text)
        self.assertNotIn("zuerst die Software", text)
        lines = self.run_job(winunattend.WinOptions(), [SimpleNamespace(label="VLC 3")])
        text = "\n".join(lines)
        self.assertNotIn("OEM-Schlüssel", text)
        self.assertIn("zuerst die Software", text)


class FakeTweakAgent:
    """agentclient.tweak/send_software als Aufzeichnung (Reihenfolge, Disk, Skript, Offline-Teil)."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"type": "done", "part": "/dev/sda3", "state": "generalized", "replaced": False,
                                 "gpo": False, "shared": True,
                                 "offline": {"build": 26200, "edition": "Professional", "start": "set",
                                             "profiles": 1, "stamp": "20261125-100000", "widgets": True}}

    def tweak(self, ip, key, disk, script, port=0, offline=None):
        self.calls.append(("tweak", disk, script, offline))
        return self.result

    def software(self, *a, **k):
        self.calls.append(("software",) + a[3:5])
        return SimpleNamespace(entries=[SimpleNamespace(label="VLC 3")]), {}


def stub_jm(lines):
    return SimpleNamespace(log=lambda _j, line: lines.append(line), progress=lambda *a, **k: None)


class RestoreTest(unittest.TestCase):
    """Image zurückspielen → Danach anpassen: Startskript und Offline-Werte wie bei „Windows anpassen“."""

    def run_restore(self, software=None, tweak=None, tweak_error=None):
        import threading
        from okula_recovery import agentclient, jobs
        fake = FakeTweakAgent()
        lines, results = [], []
        tweak_fn = fake.tweak
        if tweak_error:
            def tweak_fn(*_a, **_k):
                raise agentclient.AgentError(tweak_error)
        with mock.patch.object(agentclient, "restore_image", lambda *a, **k: None), \
                mock.patch.object(agentclient, "tweak", tweak_fn), \
                mock.patch.object(jobs, "send_software", fake.software):
            work = jobs.restore_work("127.0.0.1", b"k", 1, "/nas/x", "/dev/sda", None, False,
                                     lambda j, p, e: results.append(e), None, None, software, tweak)
            job = SimpleNamespace(cancel=threading.Event(), phase="")
            try:
                text = work(job, stub_jm(lines))
            except agentclient.AgentError as e:
                text = e
        return fake, lines, results, text

    def test_tweak_after_software(self):
        fake, lines, results, text = self.run_restore(
            {"nas_root": "/nas", "names": ["vlc-3"], "device": "PC-1"}, {**CLEAN, "device": "PC-1"})
        self.assertEqual([c[0] for c in fake.calls], ["software", "tweak"])        # Software zuerst
        _kind, disk, script, offline = fake.calls[1]
        self.assertEqual(disk, "/dev/sda")
        self.assertIn("Vorlage Clean", script)
        self.assertIn("Gerät: PC-1", script)
        self.assertEqual(offline, wintweaks.choice_offline(CLEAN))
        self.assertEqual(results, [None])
        self.assertIn("Windows anpassen beim ersten Start", text)
        log = "\n".join(lines)
        self.assertIn("Windows anpassen (Vorlage Clean", log)
        self.assertIn("Vor dem Windows-Start gesetzt: Startmenü-Richtlinie", log)      # Offline-Teil (B-020)
        self.assertIn("Software installieren) steht noch aus", log)
        self.assertIn("generalisiert", log)

    def test_without_choice_nothing_sent(self):
        fake, _lines, results, text = self.run_restore()
        self.assertEqual(fake.calls, [])
        self.assertEqual(results, [None])
        self.assertNotIn("Windows anpassen", text)

    def test_error_reported(self):
        _fake, _lines, results, text = self.run_restore(tweak={**CLEAN, "device": "PC-1"},
                                                        tweak_error="Kein Windows auf /dev/sda gefunden")
        self.assertIn("Zurückgespielt, aber Windows anpassen nicht übertragen", str(text))
        self.assertIsNotNone(results[0])


class SharedOrderTest(unittest.TestCase):
    """Agent: Software zuerst, danach Windows anpassen – zweites Skript nur in scripts.ini (Reihenfolge)."""

    def test_software_then_tweak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Windows/System32/config").mkdir(parents=True)
            first = deploy.install_startup_script(root, "A", deploy.SOFTWARE_NAME, deploy.SOFTWARE_CMD_TEXT)
            second = deploy.install_startup_script(root, wintweaks.choice_script(CLEAN, "PC-1"))
            self.assertFalse(first["replaced"])
            self.assertTrue(second.get("shared"))
            ini = (root / "Windows/System32/GroupPolicy/Machine/Scripts/scripts.ini").read_bytes()[2:]
            ini = ini.decode("utf-16-le")
            self.assertLess(ini.index("0CmdLine=okula-software.cmd"), ini.index("1CmdLine=okula-windows-anpassen.cmd"))


class AutomationTest(unittest.TestCase):
    def test_setting_saved_and_in_templates(self):
        from okula_recovery import automation
        self.assertIn("tweak", automation.TEMPLATE_FIELDS)
        self.assertIsNone(automation.Settings().tweak)
        s = automation.Settings.from_dict({"tweak": {"template": "Player",
                                                     "keys": list(wintweaks.TEMPLATES["Player"]) + ["x"]}})
        self.assertNotIn(wintweaks.AUTOLOGON, s.tweak["keys"])            # kein Passwort gespeichert
        self.assertNotIn("x", s.tweak["keys"])
        self.assertEqual(automation.Settings.from_dict(s.to_dict()).tweak, s.tweak)
        for bad in ("Clean", {"keys": []}, 3):
            self.assertIsNone(automation.Settings.from_dict({"tweak": bad}).tweak)

    def test_template_roundtrip(self):
        from okula_recovery import automation, config
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(config, "config_path", lambda: Path(tmp) / "config.json"):
            automation.save_template("Schulung", automation.Settings(tweak=CLEAN))
            self.assertEqual(automation.load_templates()["Schulung"]["tweak"], CLEAN)
            merged = automation.apply_template(automation.Settings(), "Schulung")
            self.assertEqual(merged.tweak, CLEAN)

    def test_confirm_summary(self):
        from okula_recovery import automation
        dev = SimpleNamespace(name="PC-1", inventory={}, is_vm=False)
        _t, text, _b = automation.confirm_summary(dev, automation.Settings(tweak=CLEAN, disk_label="SSD"), True)
        self.assertIn("Windows anpassen: Vorlage Clean", text)
        _t, text, _b = automation.confirm_summary(dev, automation.Settings(disk_label="SSD"), True)
        self.assertNotIn("Windows anpassen", text)

    def test_run_sends_tweak_after_software(self):
        import threading
        from okula_recovery import agentclient, automation, imagecheck, jobs
        fake = FakeTweakAgent()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Images").mkdir()
            (Path(tmp) / "Images/master").write_text("x")
            s = automation.Settings(image="Images/master", image_mode="own", disk_key="S123", finish="none",
                                    install_software=["vlc-3"], tweak=CLEAN)
            dev = SimpleNamespace(name="PC-1", id="d1", windows_key=("", ""), is_vm=False)
            info = {"disks": [{"path": "/dev/sda", "serial": "S123", "size": 10**12, "model": "SSD",
                               "partitions": []}]}
            error, lines = {}, []
            with mock.patch.object(agentclient, "get_info", lambda *a, **k: info), \
                    mock.patch.object(agentclient, "image_source", lambda *a, **k: {"source": {"size": 0}}), \
                    mock.patch.object(imagecheck, "load", lambda *a, **k: None), \
                    mock.patch.object(imagecheck, "warning", lambda *a, **k: ""), \
                    mock.patch.object(agentclient, "restore_image", lambda *a, **k: None), \
                    mock.patch.object(agentclient, "customize", lambda *a, **k: []), \
                    mock.patch.object(agentclient, "banner", lambda *a, **k: True), \
                    mock.patch.object(agentclient, "tweak", fake.tweak), \
                    mock.patch.object(jobs, "send_software", fake.software):
                work = automation.automation_work("127.0.0.1", b"k", 1, dev, s, tmp, error)
                work(SimpleNamespace(cancel=threading.Event(), phase="x"), stub_jm(lines))
        self.assertEqual([c[0] for c in fake.calls], ["software", "tweak"])
        self.assertIn("Gerät: PC-1", fake.calls[1][2])
        self.assertTrue(error["tweak"].startswith("Windows anpassen (Vorlage Clean"))


def _gtk() -> bool:
    from tests.test_wintweaks import gtk_available
    return gtk_available()


@unittest.skipUnless(_gtk(), "braucht GTK mit Bildschirm")
class ChooserTest(unittest.TestCase):
    def test_chooser_template_and_load(self):
        from okula_recovery.automation_tab import TweakChooser
        changes = []
        c = TweakChooser(on_change=lambda: changes.append(1), device_name="PC-1")
        self.assertIsNone(c.selection())                                  # Standard aus
        c.check.set_active(True)
        self.assertEqual(c.selection(), CLEAN)                            # Vorlage Clean vorgewählt
        self.assertTrue(changes)
        c.combo.set_active_id("Player")
        self.assertNotIn(wintweaks.AUTOLOGON, c.selection()["keys"])
        c.load(None)
        self.assertIsNone(c.selection())
        c.load(CLEAN)
        self.assertEqual(c.selection(), CLEAN)
        c.set_blocked(winsetup.TWEAK_AUDIT)                               # Master (Audit-Modus)
        self.assertIsNone(c.selection())
        self.assertFalse(c.check.get_sensitive())

    def test_dialog_choose_mode(self):
        from okula_recovery.automation_tab import WindowsTweakDialog
        dlg = WindowsTweakDialog(None, "PC-1", choose=True, selected=["show_ext"], template="Clean")
        try:
            self.assertEqual(dlg.selected(), {"show_ext"})
            self.assertEqual(dlg.template, "Clean")
            self.assertFalse(dlg.checks[wintweaks.AUTOLOGON].get_sensitive())
            dlg.combo.set_active_id("Player")
            self.assertNotIn(wintweaks.AUTOLOGON, dlg.selected())
            self.assertIn("Player", dlg.state.get_text())
            self.assertNotIn("geändert", dlg.state.get_text())
        finally:
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
