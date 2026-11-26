"""Ä-051: Ordner senden – Software wie Content (Einträge einzeln wählen)."""

import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, automation, deploy, distribute, filebackup, wire


def _nas(tmp: str) -> tuple[Path, Path]:
    nas = Path(tmp) / "nas"
    base = distribute.ensure(nas)
    sw = base / distribute.SOFTWARE
    (sw / "OBS & plugin/sub").mkdir(parents=True)
    (sw / "OBS & plugin/sub/obs.exe").write_bytes(b"MZ" * 5)
    (sw / "browser").mkdir()
    (sw / "browser/chrome.msi").write_bytes(b"MSI")
    (sw / "Reader_de_install.exe").write_bytes(b"MZ" * 3)
    (sw / "anleitung.pdf").write_bytes(b"%PDF")
    (sw / ".versteckt").mkdir()
    (sw / ".Reader.okula.json").write_text("{}")
    (sw / "link-ordner").symlink_to(sw / "browser")
    (sw / "link-datei.exe").symlink_to(sw / "Reader_de_install.exe")
    os.mkfifo(sw / "fifo")
    (base / distribute.CONTENT / "Projekt A").mkdir()
    (base / distribute.CONTENT / "Projekt A/a.txt").write_text("A")
    return nas, sw


class SoftwareEntriesTest(unittest.TestCase):
    def test_entries_folders_first_without_hidden_links_special(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas, _sw = _nas(tmp)
            self.assertEqual(distribute.software_entries(nas),
                             ["browser", "OBS & plugin", "anleitung.pdf", "Reader_de_install.exe"])
            self.assertEqual(distribute.software_entries(Path(tmp) / "fehlt"), [])

    def test_items_for_and_describe(self):
        self.assertEqual(distribute.items_for(True, False, []), ["Software"])            # alt: alle
        self.assertEqual(distribute.items_for(True, True, ["P"], []), ["Software", "Test Files", "Content/P"])
        self.assertEqual(distribute.items_for(True, False, [], ["browser", "a.exe"]),
                         ["Software/browser", "Software/a.exe"])
        self.assertEqual(distribute.items_for(False, False, ["P"], ["browser"]), ["Content/P"])
        self.assertEqual(distribute.describe(["Software"]), "Software: alle (Ordner ersetzt)")
        self.assertEqual(distribute.describe(["Software/a", "Software/b", "Test Files", "Content/P"]),
                         "Software: a, b, Test Files, Content: P")
        many = [f"Software/E{i}" for i in range(7)]
        self.assertEqual(distribute.describe(many), "Software: E0, E1, E2 und 4 weitere")
        self.assertEqual(distribute.describe([]), "nichts")


class SoftwarePlanTest(unittest.TestCase):
    def test_plan_selected_entries_folder_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas, sw = _nas(tmp)
            items = distribute.items_for(True, False, ["Projekt A"], ["OBS & plugin", "Reader_de_install.exe"])
            p = distribute.plan(nas, items)
            self.assertEqual(p.items, ["Software/OBS & plugin", "Software/Reader_de_install.exe", "Content/Projekt A"])
            self.assertEqual(p.requested, items)
            self.assertEqual(p.missing, [])
            paths = [(e[0], e[1]) for e in p.entries]
            self.assertIn(("dir", "Software/OBS & plugin/sub"), paths)
            self.assertIn(("file", "Software/OBS & plugin/sub/obs.exe"), paths)
            self.assertIn(("file", "Software/Reader_de_install.exe"), paths)
            self.assertNotIn(("dir", "Software/Reader_de_install.exe"), paths)
            self.assertEqual((p.files, p.bytes), (3, 10 + 6 + 1))
            file_entry = next(e for e in p.entries if e[1] == "Software/Reader_de_install.exe")
            self.assertEqual(file_entry[4], sw / "Reader_de_install.exe")

    def test_old_setting_software_means_whole_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas, _sw = _nas(tmp)
            s = automation.Settings.from_dict({"software": True, "testfiles": False, "projects": []})
            self.assertEqual(s.software_items, [])
            self.assertEqual(s.items, ["Software"])
            p = distribute.plan(nas, s.items)
            self.assertEqual(p.items, ["Software"])         # Ä-053: ein Eintrag – der ganze Ordner wird ersetzt
            self.assertEqual(p.requested, ["Software"])
            self.assertEqual(distribute.describe(p.requested), "Software: alle (Ordner ersetzt)")
            paths = [(e[0], e[1]) for e in p.entries]
            self.assertEqual(paths[0], ("dir", "Software"))
            self.assertIn(("file", "Software/OBS & plugin/sub/obs.exe"), paths)
            self.assertIn(("file", "Software/Reader_de_install.exe"), paths)
            self.assertNotIn(("file", "Software/.Reader.okula.json"), paths)
            self.assertNotIn(("dir", "Software/.versteckt"), paths)
            self.assertFalse(any("link-" in e[1] or "fifo" in e[1] for e in p.entries))

    def test_all_with_single_entries_is_whole_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas, _sw = _nas(tmp)
            p = distribute.plan(nas, ["Software", "Software/browser", "Test Files"])
            self.assertEqual(p.items, ["Software", "Test Files"])

    def test_software_choice(self):
        names = ["browser", "OBS & plugin", "a.exe"]
        self.assertEqual(distribute.software_choice(names, True, []), (True, []))           # Häkchen „Alle“
        self.assertEqual(distribute.software_choice(names, False, ["a.exe"]), (True, ["a.exe"]))
        self.assertEqual(distribute.software_choice(names, False, []), (False, []))
        # Ä-053: alle einzeln angehakt (auch mit gespeicherten, fehlenden Einträgen) = „Alle“
        self.assertEqual(distribute.software_choice(names, False, names), (True, []))
        self.assertEqual(distribute.software_choice(names, False, names + ["Weg"]), (True, []))
        self.assertEqual(distribute.software_choice([], False, ["Weg"]), (True, ["Weg"]))

    def test_missing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas, _sw = _nas(tmp)
            items = distribute.items_for(True, False, [], ["browser", "Weg", "link-ordner", "fifo"])
            p = distribute.plan(nas, items)
            self.assertEqual(p.items, ["Software/browser"])
            self.assertEqual(p.missing, ["Software/Weg", "Software/link-ordner", "Software/fifo"])
            self.assertEqual(distribute.describe(p.requested), "Software: browser")
            only_missing = distribute.items_for(True, False, [], ["Weg"])
            with self.assertRaises(distribute.DistributeError):
                distribute.plan(nas, only_missing)
            p = distribute.plan(nas, only_missing, strict=False)        # Automatisierung: Rest läuft
            self.assertEqual((p.items, p.entries, p.missing), ([], [], ["Software/Weg"]))

    def test_empty_software_folder_and_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas = Path(tmp)
            distribute.ensure(nas)
            p = distribute.plan(nas, ["Software", "Test Files"])
            self.assertEqual(p.items, ["Test Files"])
            self.assertEqual(p.missing, ["Software (leer)"])
            for bad in ("Software/../x", "Software/.versteckt", "Software/a/b", "Test Files/x", "/Software"):
                with self.assertRaises(distribute.DistributeError, msg=bad):
                    distribute.plan(nas, [bad])

    def test_old_template_means_all(self):
        with mock.patch.object(automation, "load_templates", lambda: {"Alt": {"software": True}}):
            s = automation.Settings(software=True, software_items=["browser"])
            self.assertEqual(automation.apply_template(s, "Alt").items, ["Software"])
        self.assertIn("software_items", automation.TEMPLATE_FIELDS)


class _FakeMounts:
    def __init__(self, write=False):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DeliverEntriesTest(unittest.TestCase):
    """Agent (deploy.deliver) und Tool (agentclient.deliver) über ein Socket-Paar, Windows als Ordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.win = self.d / "win"
        (self.win / "Windows").mkdir(parents=True)
        self.desk = self.win / "Users/Public/Desktop"
        (self.desk / "Software/browser").mkdir(parents=True)
        (self.desk / "Software/browser/alt.msi").write_bytes(b"alt")
        (self.desk / "Software/Reader_de_install.exe").write_bytes(b"alt")
        (self.desk / "Software/Eigenes").mkdir()
        (self.desk / "Software/Eigenes/bleibt.txt").write_text("bleibt")
        self.patches = [mock.patch.object(filebackup, "Mounts", _FakeMounts),
                        mock.patch.object(deploy, "_windows_root", lambda m, disk: self.win)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def send(self, plan, server=None):
        tool, agent_side = socket.socketpair()

        def serve():
            try:
                req = wire.recv_json(agent_side)
                (server or deploy.deliver)(agent_side, req, lambda m: None)
            except Exception as e:      # wie agent.run_job: Grund ans Tool
                wire.send_json(agent_side, {"type": "error", "message": str(e)})
            finally:
                agent_side.close()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        try:
            with mock.patch.object(agentclient, "_connect", lambda ip, key, port: tool):
                return agentclient.deliver("127.0.0.1", b"k" * 32, "/dev/x", plan.items, plan.entries, plan.bytes,
                                           lambda ev: None, threading.Event())
        finally:
            t.join(10)

    def test_replaces_only_chosen_entries(self):
        nas, _sw = _nas(str(self.d))
        plan = distribute.plan(nas, distribute.items_for(True, False, [], ["browser", "Reader_de_install.exe"]))
        result = self.send(plan)
        self.assertEqual(result["files"], 2)
        sw = self.desk / "Software"
        self.assertEqual(sorted(p.name for p in sw.iterdir()), ["Eigenes", "Reader_de_install.exe", "browser"])
        self.assertEqual(sorted(p.name for p in (sw / "browser").iterdir()), ["chrome.msi"])   # alt.msi weg
        self.assertEqual((sw / "Reader_de_install.exe").read_bytes(), b"MZ" * 3)
        self.assertTrue((sw / "Reader_de_install.exe").is_file())
        self.assertEqual((sw / "Eigenes/bleibt.txt").read_text(), "bleibt")
        self.assertEqual(sorted(p.name for p in self.desk.iterdir()), ["Software"])      # kein Zwischenordner

    def test_all_entries_and_new_file_on_empty_desktop(self):
        nas, _sw = _nas(str(self.d))
        import shutil
        shutil.rmtree(self.desk / "Software")
        plan = distribute.plan(nas, ["Software"])
        self.send(plan)
        self.assertEqual(sorted(p.name for p in (self.desk / "Software").iterdir()),
                         ["OBS & plugin", "Reader_de_install.exe", "anleitung.pdf", "browser"])
        self.assertTrue((self.desk / "Software/OBS & plugin/sub/obs.exe").is_file())

    def test_all_replaces_whole_folder(self):
        """Ä-053: „Alle“ – alter Inhalt unter Desktop\\Software weg (auch Eigenes), neuer Stand vom NAS."""
        nas, _sw = _nas(str(self.d))
        plan = distribute.plan(nas, distribute.items_for(True, False, [], []))
        result = self.send(plan)
        self.assertEqual(result["files"], 4)
        sw = self.desk / "Software"
        self.assertFalse((sw / "Eigenes").exists())
        self.assertFalse((sw / "browser/alt.msi").exists())
        self.assertEqual((sw / "Reader_de_install.exe").read_bytes(), b"MZ" * 3)
        self.assertEqual(sorted(p.name for p in self.desk.iterdir()), ["Software"])      # kein Zwischenordner

    def test_old_agent_reports_too_old(self):
        nas, _sw = _nas(str(self.d))
        plan = distribute.plan(nas, distribute.items_for(True, False, [], ["anleitung.pdf"]))

        def old_agent(sock, req, log):
            """Verhalten vor Ä-051: jeder Eintrag wird vorab als Ordner angelegt."""
            stage = self.desk / ".okula-alt"
            for item in req["items"]:
                (stage / item).mkdir(parents=True, exist_ok=True)
            deploy._receive_into(sock, stage, [deploy._item_name(i) for i in req["items"]], 1, lambda *a: None)

        with self.assertRaises(agentclient.AgentError) as ctx:
            self.send(plan, old_agent)
        self.assertEqual(str(ctx.exception), agentclient.DELIVER_TOO_OLD)


if __name__ == "__main__":
    unittest.main()
