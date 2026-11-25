"""B-021: Rest vor der ersten Anmeldung – Sperrbildschirm und „Microsoft-Benutzererfahrungen“ offline (hivexsh
nachgebildet wie in tests/test_offline_tweak.py), Edition aus dem Hive, ehrliche Hinweise zu den Werbe-Platzhaltern
im Startmenü, Uhr des Agents nach dem Server. Läuft ohne root, hivexsh und Windows."""

import socket
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, demo_agent, deploy, jobs, wintweaks, wire
from tests.test_offline_tweak import PINS, OfflineBase, make_hive
from tests.test_wintweaks import steps

VERSION = r"Microsoft\Windows NT\CurrentVersion"
LOCK_VALUES = [("NoLockScreen", 4, b"\x01\x00\x00\x00")]
CONSUMER = ("DisableWindowsConsumerFeatures", 4, b"\x01\x00\x00\x00")
OTHER = ("DisableSoftLanding", 4, b"\x01\x00\x00\x00")          # fremder Wert im selben Schlüssel


def sz(text: str) -> bytes:
    return text.encode("utf-16-le") + b"\0\0"


def version(edition: str | None = "Professional", build: str = "26100") -> dict:
    values = [("CurrentBuild", 1, sz(build))]
    if edition is not None:
        values.append(("EditionID", 1, sz(edition)))
    return {VERSION: values}


class LockAndConsumerOfflineTest(OfflineBase):
    def test_lock_screen_and_consumer_offline(self):
        self.hive.write_bytes(make_hive({deploy.CLOUD_KEY: [OTHER], **version()}, build=None))
        after = make_hive({deploy.LOCK_KEY: LOCK_VALUES, deploy.CLOUD_KEY: [OTHER, CONSUMER], **version()},
                          build=None)
        req = wintweaks.offline_request({"lockscreen_off", "no_reinstall"})
        self.assertEqual(req, {"lock_screen_off": True, "consumer_off": True})
        layout = self.profile("Okula-test", "start2.bin")
        res = deploy.tweak_offline(self.root, req, run=self.fake(after), now=0)
        self.assertEqual(res, {"offline": {"build": 26100, "edition": "Professional", "lock_screen_off": True,
                                           "consumer_off": True}})
        # ein hivexsh-Lauf: fehlender Schlüssel Personalization angelegt, fremder Wert in CloudContent mitgeschrieben
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1],
                         "cd \\Policies\\Microsoft\\Windows\nadd Personalization\ncd Personalization\nsetval 1\n"
                         "NoLockScreen\nhex:4:01,00,00,00\n"
                         "cd \\Policies\\Microsoft\\Windows\\CloudContent\nsetval 2\n"
                         "DisableSoftLanding\nhex:4:01,00,00,00\n"
                         "DisableWindowsConsumerFeatures\nhex:4:01,00,00,00\ncommit\n")
        self.assertEqual(self.hive.read_bytes(), after)
        # ohne Startmenü: nichts umbenannt, keine Marke
        self.assertTrue((layout / "start2.bin").exists())
        self.assertFalse(self.okula.exists())
        self.assertEqual(deploy.LOCK_KEY, r"Policies\Microsoft\Windows\Personalization")
        self.assertEqual(deploy.CLOUD_KEY, r"Policies\Microsoft\Windows\CloudContent")

    def test_with_start_and_widgets_one_run(self):
        self.hive.write_bytes(make_hive({r"Policies\Microsoft\Windows": [], **version("Enterprise")}, build=None))
        start = [("ConfigureStartPins", 4, b"\x01\x00\x00\x00"),
                 ("ConfigureStartPinsJSON", 2, (deploy.START_PINS_PATH + "\0").encode("utf-16-le"))]
        after = make_hive({deploy.EXPLORER_KEY: start, deploy.DSH_KEY: [("AllowNewsAndInterests", 4, b"\0" * 4)],
                           deploy.LOCK_KEY: LOCK_VALUES, deploy.CLOUD_KEY: [CONSUMER], **version("Enterprise")},
                          build=None)
        self.profile("Okula-test", "start2.bin")
        req = wintweaks.offline_request({"start_clean", "apps_widgets", "lockscreen_off", "no_reinstall"})
        res = deploy.tweak_offline(self.root, req, run=self.fake(after), now=0)
        off = res["offline"]
        self.assertEqual((off["start"], off["profiles"], off["edition"]), ("set", 1, "Enterprise"))
        self.assertTrue(off["widgets"] and off["lock_screen_off"] and off["consumer_off"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1].count("commit"), 1)
        self.assertIn("add Personalization\ncd Personalization\nsetval 1\nNoLockScreen\n", self.calls[0][1])
        self.assertIn("add CloudContent\ncd CloudContent\nsetval 1\nDisableWindowsConsumerFeatures\n",
                      self.calls[0][1])
        self.assertTrue((self.okula / deploy.START_MARKER).is_file())

    def test_already_set_nothing_written(self):
        self.hive.write_bytes(make_hive({deploy.LOCK_KEY: LOCK_VALUES, **version("Core")}, build=None))
        res = deploy.tweak_offline(self.root, {"lock_screen_off": True}, run=self.fake(None))
        self.assertEqual(self.calls, [])
        self.assertEqual(res, {"offline": {"build": 26100, "edition": "Core", "lock_screen_off": True}})

    def test_hive_error_leaves_hive(self):
        data = make_hive({r"Policies\Microsoft": [], **version()}, build=None, dirty=True)
        self.hive.write_bytes(data)
        res = deploy.tweak_offline(self.root, {"lock_screen_off": True}, run=self.fake(make_hive({})))
        self.assertIn("nicht sauber geschlossen", res["offline_error"])
        self.assertEqual(self.hive.read_bytes(), data)
        self.assertEqual(self.calls, [])

    def test_edition_read_and_checked(self):
        for edition, want in (("Professional", "Professional"), ("CoreSingleLanguage", "CoreSingleLanguage"),
                              (None, ""), ("Pro fessional", ""), ("x" * 41, ""), ("Pröfessional", "")):
            with self.subTest(edition=edition):
                self.hive.write_bytes(make_hive(version(edition), build=None))
                self.assertEqual(deploy.windows_edition(self.root), want)
        self.assertEqual(deploy.windows_build(self.root), 26100)

    def test_agent_log_line(self):
        line = deploy.offline_log({"offline": {"lock_screen_off": True, "consumer_off": True}})
        self.assertIn("Sperrbildschirm-Richtlinie gesetzt", line)
        self.assertIn("Richtlinie Microsoft-Benutzererfahrungen gesetzt", line)


class ToolLogTest(unittest.TestCase):
    """Log des Auftrags im Tool: ehrlich je Edition (Microsoft Learn, Policy CSP)."""

    def test_lock_screen(self):
        req = {"lock_screen_off": True}
        pro = jobs.offline_lines(req, {"offline": {"edition": "Professional", "lock_screen_off": True}})
        self.assertEqual(pro, ["Vor dem Windows-Start gesetzt: Richtlinie „Sperrbildschirm nicht anzeigen“ – kein "
                               "Sperrbildschirm ab dem ersten Start"])
        home = jobs.offline_lines(req, {"offline": {"edition": "Core", "lock_screen_off": True}})
        self.assertIn("Windows Core laut Microsoft nicht unterstützt, wirkt evtl. nicht", home[0])

    def test_ads_hint_per_edition(self):
        req = {"start_pins": PINS, "consumer_off": True}
        base = {"build": 26100, "start": "set", "profiles": 1, "stamp": "s", "consumer_off": True}
        pro = jobs.offline_lines(req, {"offline": {**base, "edition": "Professional"}})
        self.assertEqual(len(pro), 2)                                    # Hinweis nur einmal
        self.assertIn("wirkt bei Windows Professional nicht (nur Enterprise/Education)", pro[1])
        self.assertIn("Werbe-Platzhalter im Startmenü (z. B. WhatsApp, LinkedIn, Adobe Express)", pro[1])
        ent = jobs.offline_lines(req, {"offline": {**base, "edition": "Enterprise"}})
        self.assertIn("keine Werbe-Apps und Werbe-Platzhalter ab der ersten Anmeldung", ent[1])
        self.assertNotIn("von Hand", "\n".join(ent))
        # nur Startmenü gewählt: Hinweis bei Pro, nicht bei Education
        only = {"start_pins": PINS}
        lines = jobs.offline_lines(only, {"offline": {**base, "consumer_off": False, "edition": "Professional"}})
        self.assertTrue(lines[-1].startswith("Hinweis (Windows Professional): Werbe-Platzhalter"))
        edu = jobs.offline_lines(only, {"offline": {**base, "consumer_off": False, "edition": "Education"}})
        self.assertEqual(len(edu), 1)

    def test_agent_of_b020(self):
        """Agent von B-020: kennt Sperrbildschirm und Benutzererfahrungen nicht (setzt nur Widgets)."""
        req = {"widgets": True, "lock_screen_off": True}
        lines = jobs.offline_lines(req, {"offline": {"build": 26100, "widgets": True}})
        self.assertTrue(lines[0].startswith("Hinweis: Agent zu alt für Sperrbildschirm bzw. Werbe-Richtlinie"))
        self.assertIn("„Widgets zulassen“ aus", lines[1])
        # nur Sperrbildschirm: alter Agent antwortet ganz ohne „offline“
        self.assertIn("Agent zu alt", jobs.offline_lines({"lock_screen_off": True}, {})[0])

    def test_demo_agent(self):
        with mock.patch.object(demo_agent.time, "sleep"):
            res = demo_agent.tweak({"script": "x", "offline": {"lock_screen_off": True, "consumer_off": True}},
                                   log=lambda *_a: None)
        self.assertEqual(res["offline"], {"build": 26100, "edition": "Professional", "lock_screen_off": True,
                                          "consumer_off": True})


class ScriptTextTest(unittest.TestCase):
    """Startskript und Tooltips: ehrliche Hinweise statt „ok“."""

    def test_lock_screen_step(self):
        body = steps(wintweaks.build_script({"lockscreen_off"}))["Sperrbildschirm aus"]
        self.assertIn("Set-OkulaReg 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Personalization' 'NoLockScreen' 1",
                      body)
        self.assertIn("if ($edition -like 'Core*') {", body)
        self.assertIn("laut Microsoft nicht unterstützt, wirkt evtl. nicht' -f $edition", body)
        # typografische Anführungszeichen nur in einfachen Anführungszeichen (in "…" beendeten sie den Text)
        for line in body.splitlines():
            if "„" in line:
                self.assertNotIn('"', line)

    def test_start_menu_ads_note(self):
        body = steps(wintweaks.build_script({"start_clean"}))["Startmenü: Werbe-Kacheln entfernen (Windows 11)"]
        note = body.index("$adsNote = ''")
        self.assertLess(note, body.index("$json = '"))
        self.assertIn("if ($edition -notmatch 'Enterprise|Education') {", body)
        self.assertIn("abschalten lässt sich das laut Microsoft nur bei Enterprise/Education", body)
        # in allen Rückgaben: mit Marke, ohne Marke, vor 24H2 (Paket bzw. MDM-Bridge) – B-022: mit Hinweis zur Wirkung
        self.assertIn("return ($pinHint + $done + $pinNote + $adsNote)", body)
        self.assertIn("return $pinHint + $text + $pinNote + $adsNote", body)
        self.assertIn("'Anmeldung, auch für bestehende Benutzer' + $pinNote + $adsNote)", body)
        self.assertIn("'Benutzer' + $adsNote)", body)

    def test_no_reinstall_text(self):
        body = steps(wintweaks.build_script({"no_reinstall"}))["Wiederinstallation von Werbe-Apps sperren"]
        self.assertIn("Werbe-Platzhalter im Startmenü (WhatsApp, LinkedIn, Adobe Express …) bleiben evtl.", body)

    def test_tooltips(self):
        start = wintweaks.BY_KEY["start_clean"].tooltip
        self.assertNotIn("auch die Platzhalter", start)
        self.assertIn("nur bei Enterprise und Education", start)
        lock = wintweaks.BY_KEY["lockscreen_off"].tooltip
        self.assertIn("schon beim Senden vor dem Windows-Start", lock)
        self.assertIn("nicht bei Home", lock)
        self.assertIn("nur bei Windows Enterprise und Education", wintweaks.BY_KEY["no_reinstall"].tooltip)


class ClockTest(unittest.TestCase):
    """Agent-Uhr: nach der Server-Uhr stellen (Anfrage trägt „now“), Hardware-Uhr nie."""

    def test_sync_sets_system_clock(self):
        got, lines = [], []
        with mock.patch.object(agent, "log", lambda msg, show=False: lines.append(msg)):
            server = time.time() - 3600                   # Agent geht 1 h vor (RTC in Ortszeit, als UTC gelesen)
            diff = agent.sync_clock(server, set_time=got.append)
        self.assertEqual(got, [server])
        self.assertAlmostEqual(diff, -3600, delta=5)
        self.assertIn("Uhr nach dem Server gestellt (ging 3600 s vor; Hardware-Uhr unverändert)", lines[0])

    def test_small_or_invalid_ignored(self):
        got = []
        for now in (time.time() + 2, None, "1764000000", True, 0, 5e9, float("nan"), [1]):
            with self.subTest(now=now):
                self.assertIsNone(agent.sync_clock(now, set_time=got.append))
        self.assertEqual(got, [])

    def test_failure_only_logged(self):
        lines = []

        def refuse(_t):
            raise PermissionError("Operation not permitted")

        with mock.patch.object(agent, "log", lambda msg, show=False: lines.append(msg)):
            self.assertIsNone(agent.sync_clock(time.time() + 600, set_time=refuse))
        self.assertIn("Uhr nicht gestellt", lines[0])

    def test_no_hwclock(self):
        src = Path(agent.__file__).read_text(encoding="utf-8")
        self.assertNotIn("hwclock", src.replace("kein hwclock --systohc", ""))
        self.assertIn("time.clock_settime(time.CLOCK_REALTIME, t)", src)

    def test_request_carries_server_time(self):
        a, b = socket.socketpair()
        with a, b:
            before = time.time()
            wire.send_json(a, {"cmd": "info"})
            req = wire.recv_json(b)
            self.assertEqual(req["cmd"], "info")
            self.assertGreaterEqual(req["now"], before - 1)
            self.assertLessEqual(req["now"], time.time() + 1)
            wire.send_json(a, {"type": "ok"})                       # Antworten des Agents: ohne Zeit
            self.assertEqual(wire.recv_json(b), {"type": "ok"})
            wire.send_json(a, {"cmd": "x", "now": 5})               # vorhandene Zeit bleibt
            self.assertEqual(wire.recv_json(b), {"cmd": "x", "now": 5})

    def test_connection_syncs_before_command(self):
        order = []

        class Tls:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return None

            def settimeout(self, _t):
                pass

        ctx = mock.Mock()
        ctx.wrap_socket.return_value = Tls()
        with mock.patch.object(agent.wire, "recv_json", lambda _s: {"cmd": "unbekannt", "now": 1_800_000_000}), \
                mock.patch.object(agent.wire, "send_json", lambda _s, msg: order.append(("send", msg))), \
                mock.patch.object(agent, "sync_clock", lambda now: order.append(("clock", now))):
            agent.handle_connection(ctx, None, ("192.0.2.1", 1))
        self.assertEqual(order[0], ("clock", 1_800_000_000))
        self.assertEqual(order[1][1]["message"], "Unbekannter Befehl: unbekannt")


if __name__ == "__main__":
    unittest.main()
