"""B-020: Startmenü und Widgets offline beim Senden von „Windows anpassen“ (Agent, hivexsh nachgebildet), Marke für
das Startskript, Sperre gegen gleichzeitige Okula-Startskripte, Log im Tool. Läuft ohne root, hivexsh und Windows."""

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, deploy, demo_agent, jobs, software, winprofile, wintweaks
from tests.test_copyprofile import HiveWriter
from tests.test_wintweaks import FakeMounts, steps

LAYOUT = deploy.START_LAYOUT_DIR.replace("\\", "/")
PINS = wintweaks.start_pins_json()
START_VALUES = [("ConfigureStartPins", 4, b"\x01\x00\x00\x00"),
                ("ConfigureStartPinsJSON", 2, (deploy.START_PINS_PATH + "\0").encode("utf-16-le"))]
WIDGET_VALUES = [("AllowNewsAndInterests", 4, b"\x00\x00\x00\x00")]
START_LABEL = "Startmenü: Werbe-Kacheln entfernen (Windows 11)"


def make_hive(keys: dict, build: str | None = "26100", dirty: bool = False) -> bytes:
    """Hive mit den Schlüsseln {Pfad: [(Name, Typ, Daten)]} (Zwischenschlüssel werden angelegt) und CurrentBuild."""
    if build is not None:
        keys = {**keys, r"Microsoft\Windows NT\CurrentVersion": [("CurrentBuild", 1,
                                                                   build.encode("utf-16-le") + b"\0\0")]}
    root = {"sub": {}, "vals": []}
    for path, values in keys.items():
        node = root
        for part in path.split("\\"):
            node = node["sub"].setdefault(part, {"sub": {}, "vals": []})
        node["vals"] += list(values)
    h = HiveWriter()

    def emit(name, node):
        subs = [emit(n, c) for n, c in node["sub"].items()]
        return h.key(name, subs, [h.value(n, k, d) for n, k, d in node["vals"]])

    data = bytearray(h.file(emit("ROOT", root)))
    if dirty:
        data[4] = 7                                            # primäre ≠ sekundäre Sequenznummer
    return bytes(data)


class OfflineBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.root / "Windows/System32/config"
        self.config.mkdir(parents=True)
        self.hive = self.config / "SOFTWARE"
        self.okula = self.root / "ProgramData/Okula"
        self.calls = []
        which = mock.patch.object(deploy.shutil, "which", lambda name: f"/usr/bin/{name}")
        which.start()
        self.addCleanup(which.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self, name: str, *files: str) -> Path:
        layout = self.root / "Users" / name / LAYOUT
        layout.mkdir(parents=True)
        for f in files:
            (layout / f).write_bytes(b"alt")
        return layout

    def fake(self, after: bytes | None, rc: int = 0):
        def run(cmd, input=None, **_kw):
            if cmd == ["sync"]:
                return subprocess.CompletedProcess(cmd, 0)
            self.calls.append((cmd, input))
            if after is not None:
                Path(cmd[2]).write_bytes(after)
            return subprocess.CompletedProcess(cmd, rc, "", "hivex: Fehler" if rc else "")
        return run


class TweakOfflineTest(OfflineBase):
    def test_start_and_widgets_offline(self):
        self.hive.write_bytes(make_hive({r"Policies\Microsoft": []}))
        after = make_hive({deploy.EXPLORER_KEY: START_VALUES, deploy.DSH_KEY: WIDGET_VALUES})
        test = self.profile("Okula-test", "start2.bin", "start.bin")
        probe = self.profile("Probe", "start2.bin")
        self.profile("Neu")                                               # noch ohne Startmenü-Datei
        (self.root / "Users/Public").mkdir()
        (self.root / "Users/All Users").symlink_to(self.root / "Users/Okula-test")   # Verknüpfung: übersprungen
        res = deploy.tweak_offline(self.root, wintweaks.offline_request({"start_clean", "apps_widgets"}),
                                   run=self.fake(after), now=0)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(0))
        self.assertEqual(res, {"offline": {"build": 26100, "widgets": True, "start": "set", "profiles": 2,
                                           "stamp": stamp}})
        # ein hivexsh-Lauf, je Schlüssel ein setval mit allen Werten
        self.assertEqual(len(self.calls), 1)
        cmds = self.calls[0][1]
        self.assertTrue(cmds.startswith("cd \\Policies\\Microsoft\nadd Windows\ncd Windows\nadd Explorer\n"
                                        "cd Explorer\nsetval 2\nConfigureStartPins\nhex:4:01,00,00,00\n"
                                        "ConfigureStartPinsJSON\nhex:2:"))
        self.assertTrue(cmds.endswith("cd \\Policies\\Microsoft\nadd Dsh\ncd Dsh\nsetval 1\n"
                                      "AllowNewsAndInterests\nhex:4:00,00,00,00\ncommit\n"))
        self.assertEqual(cmds.count("commit"), 1)
        self.assertEqual(self.hive.read_bytes(), after)
        h = winprofile.Hive(after)
        self.assertEqual(h.value(deploy.EXPLORER_KEY, "ConfigureStartPinsJSON")[1].decode("utf-16-le"),
                         "%ProgramData%\\Okula\\StartPins.json\0")
        # JSON wie im Startskript (UTF-8 ohne BOM)
        self.assertEqual((self.okula / "StartPins.json").read_bytes(), PINS.encode("ascii"))
        self.assertIs(json.loads((self.okula / "StartPins.json").read_text())["applyOnce"], True)
        # alle Profile umbenannt (nicht gelöscht)
        self.assertEqual(sorted(p.name for p in test.iterdir()),
                         [f"start.bin.okula-{stamp}", f"start2.bin.okula-{stamp}"])
        self.assertEqual([p.name for p in probe.iterdir()], [f"start2.bin.okula-{stamp}"])
        # Marke für das Startskript
        self.assertEqual((self.okula / deploy.START_MARKER).read_bytes(),
                         f"stamp={stamp}\r\nprofiles=2\r\n".encode("ascii"))
        self.assertEqual(deploy.START_MARKER, "start-offline.ok")
        self.assertEqual(sorted(p.name for p in self.config.iterdir()), ["SOFTWARE"])

    def test_only_selected_options(self):
        self.assertEqual(wintweaks.offline_request({"cortana"}), {})
        self.assertEqual(wintweaks.offline_request({"fastboot_off", "telemetry", "onedrive"}), {})
        self.assertEqual(wintweaks.offline_request({"apps_widgets"}), {"widgets": True})
        self.assertEqual(wintweaks.offline_request({"start_clean"}), {"start_pins": PINS})
        # nur Widgets: kein Startmenü, kein Umbenennen, keine Marke
        self.hive.write_bytes(make_hive({r"Policies\Microsoft": []}))
        layout = self.profile("Okula-test", "start2.bin")
        after = make_hive({deploy.DSH_KEY: WIDGET_VALUES})
        res = deploy.tweak_offline(self.root, {"widgets": True}, run=self.fake(after))
        self.assertEqual(res, {"offline": {"build": 26100, "widgets": True}})
        self.assertEqual(self.calls[0][1], "cd \\Policies\\Microsoft\nadd Dsh\ncd Dsh\nsetval 1\n"
                                           "AllowNewsAndInterests\nhex:4:00,00,00,00\ncommit\n")
        self.assertTrue((layout / "start2.bin").exists())
        self.assertFalse(self.okula.exists())
        # nichts gewählt: nichts
        self.calls.clear()
        self.assertEqual(deploy.tweak_offline(self.root, {}), {})
        self.assertEqual(deploy.tweak_offline(self.root, None), {})
        self.assertEqual(self.calls, [])

    def test_before_24h2_only_widgets(self):
        self.hive.write_bytes(make_hive({r"Policies\Microsoft": []}, build="22631"))
        layout = self.profile("Okula-test", "start2.bin")
        res = deploy.tweak_offline(self.root, {"start_pins": PINS}, run=self.fake(None))
        self.assertEqual(res, {"offline": {"build": 22631, "start": "old"}})
        self.assertEqual(self.calls, [])                                   # MDM-Bridge nur im Startskript
        self.assertTrue((layout / "start2.bin").exists())
        self.assertFalse(self.okula.exists())

    def test_values_already_set_still_renamed(self):
        self.hive.write_bytes(make_hive({deploy.EXPLORER_KEY: START_VALUES}))
        layout = self.profile("Okula-test", "start2.bin")
        res = deploy.tweak_offline(self.root, {"start_pins": PINS}, run=self.fake(None), now=0)
        self.assertEqual(self.calls, [])
        self.assertEqual(res["offline"]["profiles"], 1)
        self.assertFalse((layout / "start2.bin").exists())
        self.assertTrue((self.okula / deploy.START_MARKER).is_file())

    def test_hive_error_nothing_renamed_no_marker(self):
        for data, why in ((make_hive({r"Policies\Microsoft": []}, dirty=True), "nicht sauber geschlossen"),
                          (make_hive({r"Policies\Microsoft": []}, build=None), "CurrentBuild")):
            with self.subTest(why=why):
                self.hive.write_bytes(data)
                layout = self.root / "Users/Okula-test" / LAYOUT
                if not layout.exists():
                    self.profile("Okula-test", "start2.bin")
                self.okula.mkdir(parents=True, exist_ok=True)
                (self.okula / deploy.START_MARKER).write_bytes(b"stamp=alt\r\nprofiles=9\r\n")   # alte Marke
                res = deploy.tweak_offline(self.root, {"start_pins": PINS, "widgets": True},
                                           run=self.fake(make_hive({})))
                self.assertEqual(list(res), ["offline_error"])
                self.assertIn(why, res["offline_error"])
                self.assertEqual(self.hive.read_bytes(), data)                # Hive unverändert
                self.assertTrue((layout / "start2.bin").exists())             # nichts umbenannt
                self.assertFalse((self.okula / deploy.START_MARKER).exists())  # alte Marke weg, keine neue
                self.assertEqual(self.calls, [])

    def test_rename_failure_no_marker(self):
        self.hive.write_bytes(make_hive({deploy.EXPLORER_KEY: START_VALUES}))
        self.profile("Okula-test", "start2.bin")
        with mock.patch.object(Path, "rename", side_effect=OSError("gesperrt")):
            res = deploy.tweak_offline(self.root, {"start_pins": PINS}, run=self.fake(None))
        self.assertEqual(res["offline"]["profiles"], 0)
        self.assertIn("start2.bin von Okula-test nicht umbenannt: gesperrt", res["offline"]["hints"][0])
        self.assertFalse((self.okula / deploy.START_MARKER).exists())   # das Startskript versucht es nochmals

    def test_stale_marker_removed_without_request(self):
        self.okula.mkdir(parents=True)
        (self.okula / deploy.START_MARKER).write_bytes(b"stamp=alt\r\nprofiles=1\r\n")
        self.assertEqual(deploy.tweak_offline(self.root, {}), {})
        self.assertFalse((self.okula / deploy.START_MARKER).exists())

    def test_invalid_pins_refused(self):
        self.hive.write_bytes(make_hive({r"Policies\Microsoft": []}))
        for bad in (["x"], "ü" * 3, "x" * (deploy.MAX_PINS + 1)):
            with self.subTest(bad=str(bad)[:10]):
                res = deploy.tweak_offline(self.root, {"start_pins": bad}, run=self.fake(None))
                self.assertEqual(res, {"offline_error": "Startmenü-Liste ungültig"})
        self.assertEqual(self.calls, [])

    def test_tweak_sends_offline_result(self):
        (self.root / "Windows/System32/GroupPolicy").mkdir(parents=True)
        self.hive.write_bytes(make_hive({r"Policies\Microsoft": []}))
        self.profile("Okula-test", "start2.bin")
        after = make_hive({deploy.EXPLORER_KEY: START_VALUES, deploy.DSH_KEY: WIDGET_VALUES})
        lines = []
        parts = [{"path": "/dev/sda3", "fstype": "ntfs", "size": 1 << 35}]
        with mock.patch.object(deploy, "_candidates", lambda disk: parts), \
                mock.patch.object(deploy.filebackup, "Mounts", FakeMounts({"/dev/sda3": self.root})), \
                mock.patch.object(deploy, "windows_state", lambda root: "installed"), \
                mock.patch.object(deploy.subprocess, "run", self.fake(after)):
            res = deploy.tweak({"disk": "/dev/sda", "script": "Write-Host 1",
                                "offline": {"start_pins": PINS, "widgets": True}}, log=lines.append)
        self.assertEqual(res["offline"]["start"], "set")
        self.assertEqual(res["offline"]["profiles"], 1)
        self.assertTrue((self.root / "Windows/System32/GroupPolicy/Machine/Scripts/Startup" /
                         deploy.TWEAK_PS1).is_file())
        self.assertIn("vor dem Windows-Start: Startmenü-Richtlinie gesetzt, Startmenü von 1 Profil(en) "
                      "zurückgesetzt, Widgets-Richtlinie gesetzt", lines[-1])
        self.assertIn("Hinweis: vor dem Windows-Start nichts gesetzt – x",
                      deploy.offline_log({"offline_error": "x"}))


class ScriptMarkerTest(unittest.TestCase):
    """Startskript: mit Marke kein Umbenennen (und damit kein Nachholen im Nachlauf), ohne Marke wie bisher."""

    def test_marker_skips_rename(self):
        body = steps(wintweaks.build_script({"start_clean"}))[START_LABEL]
        gpo = body[body.index("Build -ge 26100"):body.index("MDM_Policy_Config01_Start02")]
        marker = gpo.index(f"$marker = Join-Path $folder '{deploy.START_MARKER}'")
        self.assertLess(gpo.index("Set-OkulaReg $key 'ConfigureStartPinsJSON' $file 'ExpandString'"), marker)
        self.assertLess(marker, gpo.index("$sub = '"))
        self.assertLess(marker, gpo.index("$script:OkulaStartLater += [string]$p.SID"))   # kein -StartSids
        self.assertLess(marker, gpo.index("Rename-Item -LiteralPath $bin"))
        block = gpo[marker:gpo.index("$sub = '")]
        self.assertIn("ConvertFrom-StringData ([IO.File]::ReadAllText($marker))", block)
        self.assertIn("Remove-Item -LiteralPath $marker -Force", block)              # einmalig
        self.assertIn("Startmenü schon beim Senden vor dem ' +", block)
        self.assertIn("-f $file, $offCount, $offStamp", block)
        self.assertNotIn("Rename-Item", block)
        self.assertIn("return (", block)
        # Ohne Marke: Umbenennen und Nachholen wie bisher
        self.assertIn("Ohne Marke (Agent älter als B-020 oder offline nicht geklappt) wie bisher", gpo)
        self.assertEqual(wintweaks.START_LAYOUT_DIR, deploy.START_LAYOUT_DIR)
        self.assertEqual(wintweaks.START_PINS_FILE, "StartPins.json")
        self.assertEqual(deploy.START_PINS_PATH, "%ProgramData%\\Okula\\StartPins.json")

    def test_script_still_sets_values(self):
        """Doppelt schadet nicht: Das Startskript setzt Richtlinien und JSON wie bisher."""
        script = wintweaks.build_script({"start_clean", "apps_widgets"})
        self.assertIn("Set-OkulaReg $key 'ConfigureStartPins' 1", script)
        self.assertIn("Set-OkulaReg 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Dsh' 'AllowNewsAndInterests' 0", script)
        self.assertIn("[IO.File]::WriteAllText($file, $json, (New-Object Text.UTF8Encoding $false))", script)


class RestoreLockTest(unittest.TestCase):
    """Gleichzeitige Okula-Startskripte: Aufräumen unter einer Sperre, „anderes Skript war schneller“ ohne FEHLER."""

    def setUp(self):
        self.fn = wintweaks.RESTORE_START

    def test_lock_around_restore(self):
        fn = self.fn
        outer = fn[fn.index("function Restore-OkulaStart {"):fn.index("function Invoke-OkulaStartRestore")]
        self.assertIn("New-Object System.Threading.Mutex($false, 'Global\\OkulaStartRestore')", outer)
        self.assertIn("$locked = $lock.WaitOne(120 * 1000)", outer)
        self.assertIn("[System.Threading.AbandonedMutexException]", outer)
        self.assertIn("'Sperre nach 120 s nicht frei – ohne Sperre aufgeräumt'", outer)
        # Entscheidung und Aufräumen erst unter der Sperre, Freigabe im finally
        self.assertLess(outer.index("WaitOne"), outer.index("$note = Invoke-OkulaStartRestore"))
        fin = outer[outer.index("} finally {"):]
        self.assertIn("if ($locked) { try { $lock.ReleaseMutex() } catch { } }", fin)
        self.assertIn("$lock.Dispose()", fin)
        inner = fn[fn.index("function Invoke-OkulaStartRestore"):]
        self.assertIn("$others = @(Get-ChildItem -LiteralPath $OkulaStartup -Filter 'okula-*.cmd'", inner)
        self.assertNotIn("__LOCK", fn)
        # beide Skripte haben ihre .cmd vor dem Aufruf gelöscht
        tweak = wintweaks.build_script({"cortana"})
        self.assertLess(tweak.index('(Join-Path $OkulaStartup "$OkulaName.cmd")'),
                        tweak.index("Invoke-OkulaStep 'Startskript und Gruppenrichtlinie aufräumen'"))
        start = software.SCRIPT[software.SCRIPT.index("function Start-Okula"):]
        self.assertLess(start.index('(Join-Path $OkulaStartup "$OkulaName.cmd")'),
                        start.index("$note = Restore-OkulaStart"))
        for script in (tweak, software.SCRIPT.replace("__RESTORE__", fn)):
            self.assertIn("function Invoke-OkulaStartRestore", script)
            self.assertIn("'Global\\OkulaStartRestore'", script)

    def test_already_restored_by_other_script(self):
        """Hat das andere Skript gpt.ini/scripts.ini schon zurückgelegt, wird nichts gelöscht."""
        inner = self.fn[self.fn.index("function Invoke-OkulaStartRestore"):]
        pending = inner.index("$pending = (Test-Path -LiteralPath ($ini + '__AFTER__'))")
        self.assertIn("-match 'okula-[^\\r\\n]*\\.cmd'", inner[pending:pending + 400])
        self.assertLess(pending, inner.index("Remove-Item -LiteralPath $file -Force"))
        self.assertLess(inner.index("if ($pending) {"), inner.index("Remove-Item -LiteralPath $file -Force"))
        self.assertIn("$notes += 'Gruppenrichtlinie war schon zurückgelegt (anderes Okula-Startskript)'", inner)

    def test_not_present_is_no_error(self):
        inner = self.fn[self.fn.index("function Invoke-OkulaStartRestore"):]
        reg = inner[inner.index("$base = "):]
        catch = reg[reg.index("} catch {"):]
        self.assertLess(catch.index("if ((Test-Path -LiteralPath $list) -and (Get-OkulaGpLeft $list)) {"),
                        catch.index("$notes += ('Registrierung {0} nicht ganz aufgeräumt"))
        left = self.fn[self.fn.index("function Get-OkulaGpLeft"):self.fn.index("function Restore-OkulaStart")]
        self.assertIn("Test-OkulaGpScript ([string]$entry.GetValue('Script'))", left)
        self.assertIn("-ErrorAction SilentlyContinue", left)
        sync = inner[inner.index("$syncSaved = "):inner.index("$base = ")]
        self.assertLess(sync.index("if (Test-Path -LiteralPath $syncSaved) {\n                    $syncError"),
                        len(sync))
        self.assertEqual(self.fn.count("{"), self.fn.count("}"))
        self.assertEqual(self.fn.count("("), self.fn.count(")"))

    def test_cmd_emergency_stays_simple(self):
        for cmd in (deploy.TWEAK_CMD_TEXT, deploy.SOFTWARE_CMD_TEXT):
            self.assertNotIn("Mutex", cmd)
            self.assertIn("if defined OKULA_ANDERE goto ende", cmd)


class JobLogTest(unittest.TestCase):
    def test_offline_lines(self):
        req = {"start_pins": PINS, "widgets": True}
        self.assertEqual(jobs.offline_lines({}, {}), [])
        lines = jobs.offline_lines(req, {"offline": {"build": 26100, "start": "set", "profiles": 2,
                                                     "stamp": "20261124-1000", "widgets": True}})
        self.assertEqual(len(lines), 3)
        self.assertIn("Startmenü von 2 Profil(en) zurückgesetzt", lines[0])
        self.assertIn("gilt ab der ersten Anmeldung", lines[0])
        self.assertIn("„Widgets zulassen“ aus", lines[1])
        self.assertTrue(lines[2].startswith("Hinweis: Werbe-Platzhalter im Startmenü"))       # B-021: Edition unbekannt
        old = jobs.offline_lines(req, {"offline": {"build": 22631, "start": "old"}})
        self.assertIn("vor 24H2", old[0])
        err = jobs.offline_lines(req, {"offline_error": "nicht sauber geschlossen"})
        self.assertTrue(err[0].startswith("Hinweis: Einstellungen vor dem Windows-Start nicht gesetzt "
                                          "(nicht sauber geschlossen)"))
        self.assertIn("Sperrbildschirm", err[0])
        self.assertIn("Agent zu alt", jobs.offline_lines(req, {})[0])               # Agent vor B-020
        hint = jobs.offline_lines(req, {"offline": {"start": "set", "profiles": 0, "hints": ["x gesperrt"]}})
        self.assertIn("Hinweis: x gesperrt", hint[1])
        self.assertFalse(hasattr(jobs, "sync_line"))

    def test_tweak_job_sends_offline(self):
        sent = {}

        def fake(ip, key, disk, s, port, offline=None):
            sent["offline"] = offline
            return {"type": "done", "part": "/dev/sda3", "state": "installed", "replaced": False, "gpo": False,
                    "offline": {"build": 26100, "start": "set", "profiles": 1, "stamp": "s"}}

        req = wintweaks.offline_request({"start_clean"})
        jm = jobs.JobManager()
        with mock.patch.object(agentclient, "tweak", fake):
            job = jm.start("dev", "tweak", "/dev/sda", "Windows anpassen",
                           jobs.tweak_work("127.0.0.1", b"k", 1, "/dev/sda", "x", [], lambda j, p, e: None, req))
            for _ in range(100):
                if not job.running:
                    break
                time.sleep(0.05)
        self.assertEqual(job.state, jobs.DONE)
        self.assertEqual(sent["offline"], req)
        self.assertIn("Startmenü von 1 Profil(en) zurückgesetzt", "\n".join(job.log))

    def test_agentclient_request(self):
        sent = []

        class Sock:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return None

            def settimeout(self, _t):
                pass

        with mock.patch.object(agentclient, "_connect", lambda *a: Sock()), \
                mock.patch.object(agentclient.wire, "send_json", lambda sock, req: sent.append(req)), \
                mock.patch.object(agentclient.wire, "recv_json", lambda *a: {"type": "done"}):
            agentclient.tweak("127.0.0.1", b"k", "/dev/sda", "x", 1)
            agentclient.tweak("127.0.0.1", b"k", "/dev/sda", "x", 1, offline={"widgets": True})
        self.assertNotIn("offline", sent[0])
        self.assertEqual(sent[1]["offline"], {"widgets": True})

    def test_demo_agent(self):
        with mock.patch.object(demo_agent.time, "sleep"):
            res = demo_agent.tweak({"script": "x", "offline": {"start_pins": PINS, "widgets": True}},
                                   log=lambda *_a: None)
            self.assertEqual(res["offline"]["start"], "set")
            self.assertTrue(res["offline"]["widgets"])
            self.assertNotIn("offline", demo_agent.tweak({"script": "x"}, log=lambda *_a: None))
            self.assertNotIn("sync", res)


if __name__ == "__main__":
    unittest.main()
