"""B-019/B-020: Registrierung offline schreiben (deploy.set_hive_values, hivexsh nachgebildet), SyncForegroundPolicy
nur noch als Altlast (wird nicht mehr gesetzt, aber wiederhergestellt); Nachlauf mit Zeit-Auslöser; Startmenü bei
angemeldeten Profilen. Läuft ohne root, ohne hivexsh und ohne Windows."""

import base64
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import deploy, software, winprofile, wintweaks
from tests.test_copyprofile import HiveWriter
from tests.test_wintweaks import steps

SYNC_PATH = ["Policies", "Microsoft", "Windows NT", "CurrentVersion", "Winlogon"]
ON = (4, b"\x01\x00\x00\x00")
OFF = (4, b"\x00\x00\x00\x00")
TIMEOUT = ("GpNetworkStartTimeoutPolicyValue", 4, b"\x3c\x00\x00\x00")
TEXT = ("Hinweis", 1, "ab".encode("utf-16-le") + b"\0\0")
SYNC = [("SyncForegroundPolicy", *ON)]           # Beispielwert für die allgemeine Funktion


def software_hive(sync=None, others=(), depth=5, build="26100", dirty=False) -> bytes:
    """Hive SOFTWARE mit Policies\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon bis zur Tiefe depth (Werte nur
    bei depth 5) und der Stichprobe Microsoft\\Windows NT\\CurrentVersion\\CurrentBuild."""
    h = HiveWriter()
    vals = [h.value(n, k, d) for n, k, d in others]
    if sync is not None:
        vals.append(h.value("SyncForegroundPolicy", *sync))
    node = None
    for i in reversed(range(depth)):
        node = h.key(SYNC_PATH[i], [node] if node is not None else [], vals if i == 4 else ())
    cv = h.key("CurrentVersion", values=[h.value("CurrentBuild", 1, build.encode("utf-16-le") + b"\0\0")])
    ms = h.key("Microsoft", [h.key("Windows NT", [cv])])
    data = bytearray(h.file(h.key("ROOT", [ms] + ([node] if node is not None else []))))
    if dirty:
        struct.pack_into("<I", data, 4, 7)                      # primäre ≠ sekundäre Sequenznummer
    return bytes(data)


class HiveReaderTest(unittest.TestCase):
    def test_values_and_clean(self):
        h = winprofile.Hive(software_hive(OFF, (TIMEOUT, TEXT)))
        self.assertEqual(h.values(deploy.SYNC_KEY), [TIMEOUT, TEXT, ("SyncForegroundPolicy",) + OFF])
        self.assertEqual(h.value(deploy.SYNC_KEY, "syncforegroundpolicy"), OFF)       # Name ohne Gross/Klein
        self.assertIsNone(winprofile.Hive(software_hive(depth=2)).values(deploy.SYNC_KEY))
        self.assertEqual(winprofile.Hive(software_hive()).values(deploy.SYNC_KEY), [])
        self.assertTrue(h.clean())
        self.assertFalse(winprofile.Hive(software_hive(dirty=True)).clean())


class HiveWriteTest(unittest.TestCase):
    """set_hive_values auf einer Probe-Windows-Partition; hivexsh wird nachgebildet (schreibt einen fertigen Hive)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.root / "Windows/System32/config"
        self.config.mkdir(parents=True)
        self.hive = self.config / "SOFTWARE"
        self.calls = []
        which = mock.patch.object(deploy.shutil, "which", lambda name: f"/usr/bin/{name}")
        which.start()
        self.addCleanup(which.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, after: bytes | None, rc: int = 0):
        def run(cmd, input=None, **_kw):
            self.calls.append((cmd, input))
            self.assertEqual(cmd[:2], ["hivexsh", "-w"])
            self.assertNotEqual(Path(cmd[2]), self.hive)                    # nie direkt das Original
            if after is not None:
                Path(cmd[2]).write_bytes(after)
            return subprocess.CompletedProcess(cmd, rc, "", "hivex: Fehler" if rc else "")
        return run

    def assert_unchanged(self, before: bytes):
        self.assertEqual(self.hive.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.config.iterdir()), ["SOFTWARE"])     # Kopie weg

    def test_missing_key_created(self):
        self.hive.write_bytes(software_hive(depth=2))
        after = software_hive(ON)
        self.assertTrue(deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(after)))
        self.assertEqual(self.hive.read_bytes(), after)
        self.assertEqual(self.calls[0][1], "cd \\Policies\\Microsoft\nadd Windows NT\ncd Windows NT\n"
                                           "add CurrentVersion\ncd CurrentVersion\nadd Winlogon\ncd Winlogon\n"
                                           "setval 1\nSyncForegroundPolicy\nhex:4:01,00,00,00\ncommit\n")
        self.assertEqual(sorted(p.name for p in self.config.iterdir()), ["SOFTWARE"])

    def test_existing_value_replaced_and_other_values_kept(self):
        for old in (OFF, (1, "1".encode("utf-16-le") + b"\0\0")):         # auch anderer Typ wird ersetzt
            with self.subTest(old=old):
                self.calls.clear()
                self.hive.write_bytes(software_hive(old, (TIMEOUT, TEXT)))
                after = software_hive(ON, (TIMEOUT, TEXT))
                self.assertTrue(deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(after)))
                # setval ersetzt alle Werte des Schlüssels: die übrigen werden unverändert mitgeschrieben
                self.assertEqual(self.calls[0][1], "cd \\Policies\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\n"
                                                   "setval 3\nGpNetworkStartTimeoutPolicyValue\nhex:4:3c,00,00,00\n"
                                                   "Hinweis\nhex:1:61,00,62,00,00,00\n"
                                                   "SyncForegroundPolicy\nhex:4:01,00,00,00\ncommit\n")

    def test_already_set_nothing_written(self):
        self.hive.write_bytes(software_hive(ON, (TIMEOUT,), dirty=True))   # auch unsauber: nichts zu tun
        before = self.hive.read_bytes()
        self.assertFalse(deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(None)))
        self.assertEqual(self.calls, [])
        self.assert_unchanged(before)

    def test_hivexsh_error_leaves_hive_unchanged(self):
        self.hive.write_bytes(software_hive(OFF))
        before = self.hive.read_bytes()
        with self.assertRaisesRegex(deploy.HiveError, "hivexsh: hivex: Fehler – nicht geändert"):
            deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(software_hive(ON), rc=1))
        self.assert_unchanged(before)

    def test_wrong_result_leaves_hive_unchanged(self):
        self.hive.write_bytes(software_hive(OFF, (TIMEOUT, TEXT)))
        before = self.hive.read_bytes()
        for after, message in ((software_hive(OFF, (TIMEOUT, TEXT)), "SyncForegroundPolicy fehlt in der "
                                                                     "geschriebenen Kopie"),
                               (software_hive(ON, (TIMEOUT,)), "weicht ab"),
                               (software_hive(ON, (TIMEOUT, TEXT), build="19045"), "weicht ab"),
                               (software_hive(ON, (TIMEOUT, TEXT), dirty=True), "nicht sauber"),
                               (b"kaputt", "nicht lesbar")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(deploy.HiveError, message):
                    deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(after))
                self.assert_unchanged(before)

    def test_refused_before_writing(self):
        cases = ((software_hive(OFF, dirty=True), "nicht sauber geschlossen"),
                 (software_hive(OFF, (("Name mit ü", 4, b"\0\0\0\0"),)), "nicht sicher mitschreiben"),
                 (b"regf", "nicht lesbar"))
        for data, message in cases:
            with self.subTest(message=message):
                self.hive.write_bytes(data)
                with self.assertRaisesRegex(deploy.HiveError, message):
                    deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(software_hive(ON)))
                self.assertEqual(self.calls, [])
                self.assert_unchanged(data)

    def test_no_hive_or_no_hivexsh(self):
        with self.assertRaisesRegex(deploy.HiveError, "SOFTWARE nicht gefunden"):
            deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(None))
        self.hive.write_bytes(software_hive(OFF))
        with mock.patch.object(deploy.shutil, "which", lambda name: None):
            with self.assertRaisesRegex(deploy.HiveError, "hivexsh fehlt"):
                deploy.set_hive_values(self.root, {deploy.SYNC_KEY: SYNC}, run=self.fake(None))

    def test_write_back_error_restores_original(self):
        self.hive.write_bytes(b"alt")
        real_open = open
        calls = []

        def failing_open(path, mode="r", *a, **kw):
            calls.append(mode)
            if mode == "r+b" and len(calls) == 1:
                raise OSError("Datenträger voll")
            return real_open(path, mode, *a, **kw)

        with mock.patch("builtins.open", failing_open):
            with self.assertRaisesRegex(deploy.HiveError, "SOFTWARE nicht geschrieben.*Datenträger voll.*Original "
                                                          "zurückgelegt"):
                deploy._write_back(self.hive, b"neu", b"alt")
        self.assertEqual(self.hive.read_bytes(), b"alt")
        deploy._write_back(self.hive, b"neu-und-laenger", b"alt")
        self.assertEqual(self.hive.read_bytes(), b"neu-und-laenger")

    def test_commands_several_keys_one_run(self):
        """B-020: je Schlüssel ein setval, alle in einem Lauf; ein von einem früheren Block angelegter Teil wird
        nicht nochmals angelegt."""
        cmds = deploy.hivexsh_commands([(["Policies"], ["Microsoft", "Windows", "Explorer"],
                                         [("A", 4, b"\1\0\0\0"), ("B", 2, "x\0".encode("utf-16-le"))]),
                                        (["Policies", "Microsoft"], ["Dsh"], [("C", 4, b"\0\0\0\0")])])
        self.assertEqual(cmds, "cd \\Policies\nadd Microsoft\ncd Microsoft\nadd Windows\ncd Windows\nadd Explorer\n"
                               "cd Explorer\nsetval 2\nA\nhex:4:01,00,00,00\nB\nhex:2:78,00,00,00\n"
                               "cd \\Policies\\Microsoft\nadd Dsh\ncd Dsh\nsetval 1\nC\nhex:4:00,00,00,00\ncommit\n")
        self.assertEqual(deploy.hivexsh_commands([([], ["Policies"], [])]), "add Policies\ncd Policies\nsetval 0\n"
                                                                            "commit\n")
        self.assertEqual(deploy.hivexsh_commands([([], ["X"], []), ([], ["Y"], [])]).count("cd \\\n"), 1)


class NoSyncPolicyTest(unittest.TestCase):
    """B-020: Der Agent setzt SyncForegroundPolicy nicht mehr (Windows wartet trotzdem nicht auf die Startskripte)."""

    def test_agent_no_longer_sets_it(self):
        from tests.test_wintweaks import FakeMounts
        self.assertFalse(hasattr(deploy, "set_sync_policy"))
        self.assertFalse(hasattr(deploy, "sync_result"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Windows/System32/config").mkdir(parents=True)
            hive = root / "Windows/System32/config/SOFTWARE"
            hive.write_bytes(software_hive(depth=2))
            before = hive.read_bytes()
            calls = []
            parts = [{"path": "/dev/sda3", "fstype": "ntfs", "size": 1 << 35}]
            with mock.patch.object(deploy, "_candidates", lambda disk: parts), \
                    mock.patch.object(deploy.filebackup, "Mounts", FakeMounts({"/dev/sda3": root})), \
                    mock.patch.object(deploy, "windows_state", lambda r: "installed"), \
                    mock.patch.object(deploy.subprocess, "run", lambda cmd, **kw: calls.append(cmd)):
                res = deploy.tweak({"disk": "/dev/sda", "script": "Write-Host 1"}, log=lambda *_a: None)
            self.assertEqual(calls, [["sync"]])                                       # kein hivexsh
            self.assertEqual(hive.read_bytes(), before)
            self.assertFalse((root / "Windows/System32/GroupPolicy" / deploy.SYNC_SAVED).exists())
            self.assertNotIn("sync", res)
            self.assertNotIn("offline", res)
        # das Startskript kennt den Wert nur noch zum Wiederherstellen (Altlast)
        script = wintweaks.build_script({"cortana", "start_clean", "apps_widgets"})
        self.assertNotIn("Set-OkulaReg 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon' "
                         "'SyncForegroundPolicy'", script)
        # nur im Rückbau: New-ItemProperty, GetValue, Remove-ItemProperty
        self.assertEqual(script.count("'SyncForegroundPolicy'"), 3)


class RestoreTest(unittest.TestCase):
    """Altlast B-019: Das letzte Okula-Startskript stellt SyncForegroundPolicy her (PowerShell und Notfall im .cmd)."""

    def test_restore_in_both_scripts(self):
        fn = wintweaks.RESTORE_START
        others = fn.index("if (-not $others) {")
        sync = fn.index("$syncSaved = Join-Path $OkulaGp 'SyncForegroundPolicy__AFTER__'")
        self.assertLess(others, sync)
        self.assertLess(sync, fn.index("$base = 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Group Policy'"))
        block = fn[sync:fn.index("$base = ")]
        self.assertIn("$syncKey = 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'",
                      block)
        self.assertIn("if ($was -match '^dword:(\\d+)$') {", block)
        self.assertIn("New-ItemProperty -LiteralPath $syncKey -Name 'SyncForegroundPolicy' -Value $v -PropertyType "
                      "DWord", block)
        self.assertIn("Remove-ItemProperty -LiteralPath $syncKey -Name 'SyncForegroundPolicy'", block)
        self.assertLess(block.index("Remove-ItemProperty"), block.index("Remove-Item -LiteralPath $syncSaved"))
        self.assertIn("$syncError = 'SyncForegroundPolicy nicht zurückgesetzt", block)
        # B-020: Sicherung schon weg (anderes Skript war schneller) = kein Fehler
        catch = block[block.index("} catch {"):]
        self.assertLess(catch.index("if (Test-Path -LiteralPath $syncSaved) {"), catch.index("$syncError = "))
        # Fehler erst nach dem Aufräumen der Registrierung, mit den übrigen Hinweisen
        self.assertLess(fn.index("$removed++"), fn.index("if ($syncError) { throw ((@($notes) + $syncError)"))
        tweak = wintweaks.build_script({"cortana"})
        self.assertIn("Join-Path $OkulaGp 'SyncForegroundPolicy.okula-nachher'", tweak)
        self.assertIn("Join-Path $OkulaGp 'SyncForegroundPolicy.okula-nachher'", software.SCRIPT.replace(
            "__RESTORE__", fn).replace("__AFTER__", deploy.TWEAK_AFTER))

    def test_cmd_emergency_restore(self):
        for cmd in (deploy.TWEAK_CMD_TEXT, deploy.SOFTWARE_CMD_TEXT):
            self.assertTrue(cmd.isascii())
            lines = cmd.split("\r\n")
            guard = lines.index("if defined OKULA_ANDERE goto ende")
            check = lines.index('if not exist "%OKULA_GP%\\SyncForegroundPolicy.okula-nachher" goto ende')
            self.assertLess(guard, check)
            self.assertLess(lines.index(")"), check)                       # nach gpt.ini/scripts.ini
            self.assertLess(check, lines.index(":ende"))
            self.assertIn('set /p OKULA_SYNC=<"%OKULA_GP%\\SyncForegroundPolicy.okula-nachher"', lines)
            self.assertIn('set "OKULA_KEY=HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"',
                          lines)
            self.assertIn('if /i "%OKULA_SYNC:~0,6%"=="dword:" reg add "%OKULA_KEY%" /v SyncForegroundPolicy '
                          '/t REG_DWORD /d %OKULA_SYNC:~6% /f >nul 2>&1', lines)
            self.assertIn('if /i not "%OKULA_SYNC:~0,6%"=="dword:" reg delete "%OKULA_KEY%" /v SyncForegroundPolicy '
                          '/f >nul 2>&1', lines)
            self.assertLess(lines.index('del /f /q "%OKULA_GP%\\SyncForegroundPolicy.okula-nachher" >nul 2>&1'),
                            lines.index(":ende"))


class LaterAndStartMenuTest(unittest.TestCase):
    def later_body(self, sel):
        return steps(wintweaks.build_script(sel, device="PC-1", created=0))[wintweaks.BY_KEY["later_cleanup"].label]

    def test_once_trigger_when_someone_logged_on(self):
        """B-019, bleibt mit B-020: Ist beim Anlegen schon jemand angemeldet, zusätzlich „jetzt + 30 min“."""
        b = self.later_body({"later_cleanup", "apps_ads"})
        shell = b.index("$shell = @(Get-CimInstance -ClassName Win32_Process -Filter \"Name='explorer.exe'\"")
        self.assertLess(b.index("$triggers = @($trigger)"), shell)
        block = b[shell:b.index("$principal")]
        self.assertIn("$at = (Get-Date).AddMinutes(30)", block)
        self.assertIn("$once = New-ScheduledTaskTrigger -Once -At $at", block)
        self.assertIn("$once.EndBoundary = $end", block)                      # nötig für -DeleteExpiredTaskAfter
        self.assertIn("$triggers += $once", block)
        self.assertIn("da schon jemand angemeldet ist – einmalig um {0}", block)
        self.assertIn("$trigger.EndBoundary = $end", b)
        self.assertIn("Register-ScheduledTask -TaskName 'Okula Windows anpassen Nachlauf' -Action $action "
                      "-Trigger $triggers", b)
        self.assertIn("$arg += ' -StartSids \"{0}\"' -f ($later -join ',')", b)
        self.assertIn("$later = @($script:OkulaStartLater | Where-Object { $_ } | Sort-Object -Unique)", b)

    def test_start_clean_skips_loaded_profiles(self):
        body = steps(wintweaks.build_script({"start_clean"}))["Startmenü: Werbe-Kacheln entfernen (Windows 11)"]
        loaded = body.index("if ($p.Loaded) {")
        self.assertLess(loaded, body.index("Rename-Item -LiteralPath $bin"))
        block = body[loaded:body.index("$done = $false")]
        self.assertIn("$script:OkulaStartLater += [string]$p.SID", block)
        self.assertIn("continue", block)
        self.assertNotIn("Rename-Item", block)
        self.assertIn("beim Lauf angemeldet – Startmenü dort nicht zurückgesetzt, greift erst nach ' +", body)
        self.assertIn("'erneutem Lauf / Neustart (der Nachlauf – falls gewählt – holt es einmalig nach", body)
        self.assertIn("$script:OkulaStartLater = @()", wintweaks.COMMON)

    def test_later_catches_up_only_logged_off(self):
        sel = {"later_cleanup", "apps_ads", "start_clean"}
        body = self.later_body(sel)
        later = base64.b64decode(re.search(r"FromBase64String\('([A-Za-z0-9+/=]+)'\)", body).group(1)).decode()
        self.assertEqual(later, wintweaks.build_later_script(sel, "PC-1", created=0))
        self.assertLess(later.index("param([string]$StartSids = '')"), later.index("$ErrorActionPreference"))
        self.assertTrue(all(line.startswith("#") or not line.strip()
                            for line in later[:later.index("param(")].splitlines()))   # param zuerst
        step = later[later.index("if ($StartSids) {"):]
        self.assertLess(later.index("if ($StartSids) {"), later.index("Remove-OkulaApps @('5319275A"))
        self.assertIn("Where-Object { $_ -match '^S-1-5-21-[\\d-]+$' }", step)
        self.assertIn("Get-CimInstance -ClassName Win32_UserProfile -Filter (\"SID='{0}'\" -f $sid)", step)
        self.assertLess(step.index("if ($p.Loaded) {"), step.index("Rename-Item -LiteralPath $bin"))
        self.assertIn(f"$sub = '{wintweaks.START_LAYOUT_DIR}'", step)
        self.assertIn("nicht nachgeholt, Startmenü greift erst nach erneutem Lauf", step)
        self.assertEqual(later.count("{"), later.count("}"))
        self.assertEqual(later.count("("), later.count(")"))
        # ohne Startmenü-Option kein Nachholen
        self.assertNotIn("if ($StartSids) {", wintweaks.build_later_script({"apps_ads"}))


class SoftwareWaitTest(unittest.TestCase):
    def test_shorter_wait_when_another_script_pending(self):
        """Die 600 s gelten für alle Startskripte zusammen: Steht danach noch „Windows anpassen“ aus, wartet
        Software höchstens SHARED_WAIT."""
        script = software.SCRIPT.replace("__SHAREDWAIT__", str(software.SHARED_WAIT))
        start = script[script.index("function Start-Okula"):]
        wait = start.index(f"$OkulaWait = [Math]::Min($OkulaWait, {software.SHARED_WAIT})")
        self.assertLess(start.index('(Join-Path $OkulaStartup "$OkulaName.cmd")'), wait)
        self.assertLess(wait, start.index("$t0 = Get-Date"))
        self.assertIn("Get-ChildItem -LiteralPath $OkulaStartup -Filter 'okula-*.cmd'", start[:wait])
        self.assertLess(software.SHARED_WAIT + 300, 600)          # Windows anpassen ~90 s, Reserve bis 600 s
        self.assertLess(software.SHARED_WAIT, software.START_WAIT)


if __name__ == "__main__":
    unittest.main()
