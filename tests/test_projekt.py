"""Projektübersicht (I-034): Parser, Schlüssel, Rückmeldungen-Datei und lokaler Webserver – ohne GTK."""

import http.client
import json
import os
import shutil
import socket
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import projekt
from okula_recovery.projekt_server import ProjectServer

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "data" / "projekt"


class InlineTest(unittest.TestCase):
    def test_markdown_and_escaping(self):
        out = projekt.inline_html("**fett** und *kursiv* mit `a <b> & c` und [Doku](VM.md) <script>x</script>")
        self.assertIn("<b>fett</b>", out)
        self.assertIn("<i>kursiv</i>", out)
        self.assertIn("<code>a &lt;b&gt; &amp; c</code>", out)
        self.assertIn('<span class="ref" title="VM.md">Doku</span>', out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>", out)

    def test_links_only_http(self):
        self.assertIn('href="https://okula.ch"', projekt.inline_html("[x](https://okula.ch)"))
        self.assertNotIn("href", projekt.inline_html("[x](javascript:alert(1))"))
        out = projekt.inline_html('[x](https://a"onmouseover=1)')
        self.assertIn('href="https://a&quot;onmouseover=1"', out)          # Anführungszeichen bleibt im Attribut

    def test_plain_and_key_ignore_markup_and_space(self):
        self.assertEqual(projekt.plain("**Agent-Stick**  neu   `x`"), "Agent-Stick neu x")
        a = projekt.text_key("test", "11", "**Snapshot** erstellen\n   und  prüfen")
        b = projekt.text_key("test", "11", "Snapshot erstellen und prüfen")
        self.assertEqual(a, b)
        self.assertNotEqual(a, projekt.text_key("test", "10", "Snapshot erstellen und prüfen"))
        self.assertNotEqual(a, projekt.text_key("test", "11", "Snapshot erstellen und löschen"))

    def test_table_row_with_pipe_in_code(self):
        self.assertEqual(projekt.split_row("| a | `x | y` | b \\| c |"), ["a", "`x | y`", "b | c"])


class ParserFixtureTest(unittest.TestCase):
    """Ausschnitte der echten Dateien in tests/data/projekt/docs."""

    @classmethod
    def setUpClass(cls):
        cls.data = projekt.collect(FIXTURE)

    def test_no_errors(self):
        self.assertEqual(self.data["hinweis"], "")
        self.assertEqual(self.data["fehler"], [])

    def test_tests_groups(self):
        groups = {g["id"]: g for g in self.data["tests"]}
        self.assertEqual(list(groups), ["vorbereitung", "1", "2", "3", "6", "9", "11"])
        self.assertEqual(len(groups["vorbereitung"]["items"]), 5)
        self.assertIn("TPM/Secure Boot", groups["vorbereitung"]["text_html"][0])
        self.assertEqual(groups["1"]["items"], [])
        self.assertEqual(len(groups["2"]["items"]), 8)
        self.assertEqual(len(groups["3"]["items"]), 7)
        self.assertIn("Audit-Modus", groups["3"]["text_html"][0])
        nine = groups["9"]["items"]
        self.assertEqual([i["erledigt"] for i in nine], [False, True, True, False, True, False, False])
        # eingerückte Folgezeilen gehören zum Testpunkt
        self.assertIn("sich nicht hineinziehen", nine[0]["text"])
        eleven = groups["11"]["items"]
        self.assertEqual(len(eleven), 5)
        self.assertIn("<b>Snapshots</b>", eleven[0]["html"])
        self.assertEqual(eleven[0]["bezug"], "Abschnitt 11")
        self.assertTrue(eleven[0]["key"].startswith("test:11:"))

    def test_tables(self):
        tab = self.data["tabellen"]
        self.assertEqual([i["id"] for i in tab["bug"]["items"]], ["B-004"])
        b4 = tab["bug"]["items"][0]
        self.assertEqual((b4["prio"], b4["status"], b4["key"]), ("🔴", "offen", "B-004"))
        self.assertIn(["Gemeldet", "05.11."], b4["spalten"])
        self.assertEqual(len(tab["aenderung"]["items"]), 7)
        ideas = {i["id"]: i for i in tab["idee"]["items"]}
        self.assertEqual(list(ideas), ["I-003", "I-004", "I-005", "I-033", "I-034"])
        self.assertIn(["Gemeldet", "10.11."], ideas["I-034"]["spalten"])   # Spalte mehr als im Kopf
        self.assertIn("<code>~/.local/share/okula-recovery/projekt-rueckmeldungen.json</code>", ideas["I-034"]["html"])

    def test_summary_and_decisions(self):
        kurz = self.data["kurz"]
        self.assertEqual(kurz["zaehler"][0], ["🐞 Bugs", "1", "0", "0"])
        self.assertIn("I-001 VMs erledigt", kurz["als_naechstes"])
        self.assertIn("Ä-007", kurz["vorschlag"])
        self.assertEqual(len(self.data["entscheidungen"]), 3)

    def test_handover_and_prompts(self):
        u = self.data["uebergabe"]
        self.assertEqual(u["titel"], "Übergabe – 06.11.2026, Nachmittag")
        self.assertEqual([i["nr"] for i in u["items"]], ["1", "2", "3", "4", "5"])
        self.assertIn("• Abschnitt <b>8</b>", u["items"][1]["html"])
        self.assertIn("<b>Tests am Server", u["items"][1]["html"])        # fett über zwei Zeilen
        self.assertEqual([p["datei"] for p in self.data["prompts"]], ["I-001-4-snapshots.md"])   # ohne VORLAGE
        self.assertTrue(self.data["prompts"][0]["status_kurz"].startswith("abgenommen 06.11."))

    def test_checkmark_note_keeps_key(self):
        a = projekt.parse_tests("## Offen\n### 7. X\n- [ ] Test A\n")[0]["items"][0]
        b = projekt.parse_tests("## Offen\n### 7. X\n- [x] Test A – ✔ 10.11. (Dominik)\n")[0]["items"][0]
        self.assertEqual(a["key"], b["key"])
        self.assertTrue(b["erledigt"])

    def test_unknown_structure_does_not_crash(self):
        for md in ("", "# nur Titel", "## Offen\n### \n- [ ]\n|||\n", "| ID |\n|---|\n| B-1 |\n", "\x00﻿"):
            projekt.parse_tests(md)
            projekt.parse_changes(md)
            projekt.parse_handover(md)
            projekt.parse_prompt("x.md", md)


class ParserRepoTest(unittest.TestCase):
    """Gegen die aktuellen Dateien im Repo: darf nicht abstürzen, findet B-004, Abschnitt 11, I-034."""

    def test_real_docs(self):
        data = projekt.collect(ROOT)
        self.assertEqual(data["fehler"], [])
        ids = {i["id"] for t in data["tabellen"].values() for i in t["items"]}
        groups = {g["id"] for g in data["tests"]}
        self.assertIn("11", groups)
        self.assertIn("vorbereitung", groups)
        self.assertTrue(data["prompts"])
        self.assertTrue(data["tests"])
        # Einträge kommen und gehen – geprüft wird, dass bekannte IDs gefunden werden, falls sie noch offen sind
        text = (ROOT / "docs" / "AENDERUNGEN.md").read_text(encoding="utf-8")
        for ident in ("B-004", "I-034"):
            if f"| {ident} |" in text:
                self.assertIn(ident, ids)
        keys = projekt.all_keys(data)
        self.assertEqual(len(keys), sum(len(g["items"]) for g in data["tests"]) + len(ids)
                         + len(data["uebergabe"]["items"]) + len(data["prompts"]))   # Schlüssel eindeutig

    def test_missing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = projekt.collect(Path(tmp) / "fehlt")
            self.assertIn("nicht gefunden", data["hinweis"])
            data = projekt.collect(Path(tmp))
            self.assertIn("fehlt der Ordner docs", data["hinweis"])
            (Path(tmp) / "docs").mkdir()
            data = projekt.collect(Path(tmp))
            self.assertEqual(data["hinweis"], "")
            self.assertEqual(len(data["fehler"]), 3)       # drei Dateien fehlen – kein Absturz


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "projekt-rueckmeldungen.json"
        self.store = projekt.FeedbackStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_save_entry_file_format(self):
        e = self.store.save_entry("B-004", "bug", "B-004", "Text", {"kommentar": "Hallo", "prio_wunsch": "🔴"})
        self.assertEqual((e["kommentar"], e["prio_wunsch"], e["uebernommen"]), ("Hallo", "🔴", None))
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        data = self.read()
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["eintraege"]["B-004"]["art"], "bug")
        self.assertIn("🔴", self.path.read_text(encoding="utf-8"))        # UTF-8, von Hand lesbar
        self.assertIn("\n  ", self.path.read_text(encoding="utf-8"))
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])   # keine Temp-Datei

    def test_validation(self):
        for changes in ({"haken": "vielleicht"}, {"prio_wunsch": "rot"}, {"status_wunsch": "irgendwann"}):
            with self.assertRaises(projekt.FeedbackError):
                self.store.save_entry("k", "test", "x", "t", changes)
        with self.assertRaises(projekt.FeedbackError):
            self.store.save_entry("k", "unbekannt", "x", "t", {"kommentar": "a"})
        self.assertFalse(self.path.exists())

    def test_taken_reset_on_change_and_clear_removes(self):
        self.store.save_entry("k", "test", "Abschnitt 11", "t", {"haken": "ok"})
        data = self.read()
        data["eintraege"]["k"]["uebernommen"] = "2026-11-10"          # setzt die Projektleitung von Hand
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.store.load()["eintraege"]["k"]["uebernommen"], "2026-11-10")
        # gleicher Wert = keine Änderung
        self.assertEqual(self.store.save_entry("k", "test", "Abschnitt 11", "t", {"haken": "ok"})["uebernommen"],
                         "2026-11-10")
        e = self.store.save_entry("k", "test", "Abschnitt 11", "t", {"haken": "fehler"})
        self.assertIsNone(e["uebernommen"])
        self.assertIsNone(self.store.save_entry("k", "test", "Abschnitt 11", "t", {"haken": None}))
        self.assertNotIn("k", self.read()["eintraege"])

    def test_broken_file_set_aside(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{kaputt", encoding="utf-8")
        self.assertEqual(self.store.load()["eintraege"], {})
        self.assertIn("defekt", self.store.hinweis)
        broken = [p.name for p in self.path.parent.iterdir() if ".defekt-" in p.name]
        self.assertEqual(len(broken), 1)
        self.assertEqual((self.path.parent / broken[0]).read_text(encoding="utf-8"), "{kaputt")
        self.store.save_entry("k", "test", "x", "t", {"kommentar": "neu"})
        self.assertEqual(self.read()["eintraege"]["k"]["kommentar"], "neu")

    def test_notes(self):
        n = self.store.add_note("idee", "  Neue Idee ")
        self.assertEqual((n["art"], n["text"], n["uebernommen"]), ("idee", "Neue Idee", None))
        self.store.update_note(n["id"], "bug", "Doch ein Bug")
        self.assertEqual(self.read()["notizen"][0]["art"], "bug")
        with self.assertRaises(projekt.FeedbackError):
            self.store.add_note("idee", "  ")
        data = self.read()
        data["notizen"][0]["uebernommen"] = "2026-11-10"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(projekt.FeedbackError):
            self.store.update_note(n["id"], "bug", "x")
        with self.assertRaises(projekt.FeedbackError):
            self.store.delete_note(n["id"])
        m = self.store.add_note("frage", "Frage?")
        self.store.delete_note(m["id"])
        self.assertEqual([x["id"] for x in self.read()["notizen"]], [n["id"]])

    def test_orphans(self):
        folder = Path(self.tmp.name) / "repo"
        shutil.copytree(FIXTURE, folder)
        data = projekt.collect(folder)
        item = next(g for g in data["tests"] if g["id"] == "11")["items"][0]
        self.store.save_entry(item["key"], "test", item["bezug"], item["text"], {"haken": "fehler",
                                                                                  "kommentar": "geht nicht"})
        self.store.save_entry("B-004", "bug", "B-004", "x", {"kommentar": "a"})
        page = projekt.page_data(folder, self.store)
        self.assertEqual(page["ohne_eintrag"], [])
        # Testtext in der Doku geändert → Rückmeldung unter „ohne Eintrag“, nichts verloren
        tests = folder / "docs" / "TESTS.md"
        changed = tests.read_text(encoding="utf-8").replace("Reiter **Snapshots**", "Reiter **Schnappschüsse**")
        tests.write_text(changed, encoding="utf-8")
        page = projekt.page_data(folder, self.store)
        self.assertEqual(page["ohne_eintrag"], [item["key"]])
        self.assertEqual(page["rueckmeldungen"][item["key"]]["kommentar"], "geht nicht")
        self.assertIn("Snapshots", page["rueckmeldungen"][item["key"]]["text"])


class PathTest(unittest.TestCase):
    def test_default_and_configured(self):
        with mock.patch.dict(os.environ, {"SUDO_USER": ""}):
            self.assertEqual(projekt.project_dir(""), Path.home() / "recovery_tool_okula")
            self.assertEqual(projekt.project_dir("  /srv/repo "), Path("/srv/repo"))
            self.assertEqual(projekt.feedback_path(),
                             Path.home() / ".local/share/okula-recovery/projekt-rueckmeldungen.json")

    def test_sudo_user_home(self):
        fake = mock.Mock(pw_dir="/home/tester")
        with mock.patch.dict(os.environ, {"SUDO_USER": "tester"}), mock.patch("os.geteuid", return_value=0), \
                mock.patch("pwd.getpwnam", return_value=fake):
            self.assertEqual(projekt.default_project_dir(), Path("/home/tester/recovery_tool_okula"))
            self.assertEqual(projekt.feedback_path().parent, Path("/home/tester/.local/share/okula-recovery"))


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = projekt.FeedbackStore(Path(cls.tmp.name) / "rm.json")
        cls.server = ProjectServer(lambda: FIXTURE, cls.store)
        cls.url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.server.port}"}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def post(self, route, payload, token=None, ctype="application/json"):
        return self.request("POST", f"/{token or self.server.token}/{route}",
                            json.dumps(payload).encode(), {"Content-Type": ctype})

    def test_same_url_on_second_start(self):
        self.assertEqual(self.server.start(), self.url)
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))
        self.assertIn(self.server.token, self.url)

    def test_token_required(self):
        for path in ("/", "/api/daten", "/falsch/api/daten", f"/{self.server.token[:-1]}/", "/../etc/passwd"):
            self.assertEqual(self.request("GET", path)[0], 403, path)
        self.assertEqual(self.post("api/rueckmeldung", {"key": "B-004"}, token="falsch")[0], 403)
        self.assertEqual(self.request("GET", f"/{self.server.token}/", host="evil.example:80")[0], 403)

    def test_page_and_assets(self):
        status, body = self.request("GET", f"/{self.server.token}/")
        self.assertEqual(status, 200)
        self.assertIn("Projektübersicht – Okula Recovery Tool".encode(), body)
        for name in ("app.js", "style.css"):
            self.assertEqual(self.request("GET", f"/{self.server.token}/{name}")[0], 200)
        self.assertEqual(self.request("GET", f"/{self.server.token}/../projekt.py")[0], 404)

    def test_data_and_save(self):
        status, body = self.request("GET", f"/{self.server.token}/api/daten")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["tabellen"]["bug"]["items"][0]["id"], "B-004")
        status, body = self.post("api/rueckmeldung", {"key": "B-004", "art": "bug", "bezug": "B-004", "text": "x",
                                                      "status_wunsch": "als Nächstes"})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.store.load()["eintraege"]["B-004"]["status_wunsch"], "als Nächstes")
        self.assertEqual(self.post("api/rueckmeldung", {"key": "B-004", "art": "bug", "prio_wunsch": "x"})[0], 400)
        status, body = self.post("api/notiz", {"aktion": "neu", "art": "frage", "text": "Wann?"})
        self.assertEqual(status, 200)
        note = json.loads(body)["notiz"]
        self.assertEqual(self.post("api/notiz", {"aktion": "loeschen", "id": note["id"]})[0], 200)
        data = json.loads(self.request("GET", f"/{self.server.token}/api/daten")[1])
        self.assertEqual(data["rueckmeldungen"]["B-004"]["status_wunsch"], "als Nächstes")
        self.assertEqual(data["notizen"], [])

    def test_post_needs_json(self):
        self.assertEqual(self.post("api/rueckmeldung", {"key": "x"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.request("POST", f"/{self.server.token}/api/rueckmeldung", b"{kaputt",
                                      {"Content-Type": "application/json"})[0], 400)

    def test_only_localhost(self):
        self.assertEqual(self.server.httpd.server_address[0], "127.0.0.1")
        addrs = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1",
                                                                                                    "127.0.1.1"}
        for addr in addrs:
            with self.assertRaises(OSError):
                socket.create_connection((addr, self.server.port), timeout=1).close()


if __name__ == "__main__":
    unittest.main()
