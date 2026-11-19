"""Ä-044 Software installieren an einem Gerät mit Windows: Menüeintrag und Bereitschaft (ohne GTK), Auftrag an
send_software mit richtiger Disk und Auswahl, Skript mit den Programmen, Zusammenspiel mit „Windows anpassen“."""

import ast
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, deploy, devices, jobs, software
from tests.test_software import INNO, NSIS, FakeMounts

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "okula_recovery/ui.py"


def ui_function(name: str) -> str:
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(UI.read_text(encoding="utf-8"), node)


class ReadinessTest(unittest.TestCase):
    """Bereitschaft wie bei „Windows anpassen“: Windows laut Inventar, nicht mit BitLocker."""

    def dev(self, *systems):
        return devices.Device(id="d1", name="PC-1", inventory={"systems": list(systems)})

    def test_windows_disk(self):
        win = {"family": "Windows", "name": "Windows 11 Pro", "disk": "nvme0n1"}
        self.assertEqual(devices.windows_disk(self.dev(win)), "/dev/nvme0n1")
        linux = {"family": "Linux", "name": "Debian 13", "disk": "sda"}
        self.assertEqual(devices.windows_disk(self.dev(linux, win)), "/dev/nvme0n1")
        self.assertIsNone(devices.windows_disk(self.dev(linux)))
        self.assertIsNone(devices.windows_disk(self.dev()))
        locked = {"family": "Windows", "name": "Windows (BitLocker)", "disk": "sda"}
        self.assertIsNone(devices.windows_disk(self.dev(locked)))
        self.assertIsNone(devices.windows_disk(self.dev({"family": "Windows", "name": "Windows 10"})))

    def test_menu_entries_next_to_windows_anpassen(self):
        from tests.test_help import load_menu_labels
        tools = load_menu_labels()["_Tools"]
        self.assertEqual(tools[tools.index("Windows _anpassen …") + 1], "Soft_ware installieren …")
        src = UI.read_text(encoding="utf-8")
        self.assertIn('"Soft_ware installieren …": (lambda: self._with_device(self.on_install_software), None)', src)
        # Rechtsklick: direkt unter „Windows anpassen …“, gleiche Bereitschaft (ready)
        tweak = 'add("Windows anpassen …", lambda: self.on_tweak_windows(dev), ready)'
        soft = 'add("Software installieren …", lambda: self.on_install_software(dev), ready)'
        self.assertIn(tweak, src)
        self.assertIn(soft, src)
        self.assertLess(src.index(tweak), src.index(soft))
        self.assertLess(src.index(soft) - src.index(tweak), 160)
        window = (ROOT / "okula_recovery/device_window.py").read_text(encoding="utf-8")
        self.assertIn('("software", "Software installieren …", lambda: main.on_install_software(self.dev))', window)
        self.assertIn('"tweak", "software", "inventory"', window)

    def test_handler_checks_like_windows_anpassen(self):
        body = ui_function("on_install_software")
        tweak = ui_function("on_tweak_windows")
        for check in ("self._ready_agent(dev, parent)", "self.windows_disk(dev)",
                      "kein Windows erkannt (oder es ist mit BitLocker"):
            self.assertIn(check, body)
            self.assertIn(check, tweak)
        self.assertLess(body.index("_ready_agent"), body.index("SoftwareInstallDialog(parent"))
        self.assertLess(body.index("windows_disk"), body.index("SoftwareInstallDialog(parent"))
        self.assertIn("self.root_for(dev)", body)                     # Demo-Gerät: Bibliothek im Demo-Speicher
        self.assertIn('self.jobs.start(dev.id, "software", disk, what', body)
        self.assertIn("jobs.software_work(agent.ip, self.key, agent.control_port, disk, root, names, dev.name",
                      body)
        self.assertIn('job.kind == "software"', ui_function("_after_job"))


class JobTest(unittest.TestCase):
    """Auftrag: Tool → Agent über ein Socket-Paar, Ablage auf einer Probe-Windows-Partition (Verzeichnis)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.nas = base / "nas"
        self.win = base / "win"
        (self.win / "Windows/System32/config").mkdir(parents=True)
        (self.win / "Windows/System32/config/SYSTEM").write_bytes(b"regf")
        self.nas.mkdir()
        src = base / "quelle"
        (src / "Barco Tool").mkdir(parents=True)
        (src / "vlc-3.0.24-win64.exe").write_bytes(NSIS)
        (src / "Barco Tool/Setup.exe").write_bytes(INNO)
        software.load(self.nas, src / "vlc-3.0.24-win64.exe")
        software.load(self.nas, src / "Barco Tool")
        self.gp = self.win / "Windows/System32/GroupPolicy"

    def tearDown(self):
        self.tmp.cleanup()

    def run_job(self, names, disk="/dev/nvme0n1"):
        a, b = socket.socketpair()
        seen, errors = {}, []

        def agent_side():
            try:
                req = deploy.wire.recv_json(b)
                seen.update(req)
                deploy.software(b, req, log=lambda *_a: None)
            except Exception as e:  # im Test sichtbar machen
                errors.append(e)
                deploy.wire.send_json(b, {"type": "error", "message": str(e)})

        t = threading.Thread(target=agent_side, daemon=True)
        parts = [{"path": disk + "p3", "fstype": "ntfs", "size": 1 << 35}]
        done = []
        jm = jobs.JobManager()
        job = jobs.Job(1, "d1", "software", disk, "Software installieren")
        with mock.patch.object(deploy, "_candidates", lambda d: parts if d == disk else []), \
                mock.patch.object(deploy.filebackup, "Mounts", FakeMounts({disk + "p3": self.win})), \
                mock.patch.object(deploy.subprocess, "run"), \
                mock.patch.object(agentclient, "_connect", lambda *_a: a):
            t.start()
            work = jobs.software_work("127.0.0.1", b"k", 1, disk, str(self.nas), names, "PC-1",
                                      lambda j, chosen, err: done.append((chosen, err)))
            result = work(job, jm)
            t.join(10)
        b.close()
        self.assertEqual(errors, [])
        return seen, done, result, job

    def test_job_sends_disk_and_selection(self):
        seen, done, result, job = self.run_job(["barco-tool", "vlc-3.0.24"])
        self.assertEqual(seen["cmd"], "software")
        self.assertEqual(seen["disk"], "/dev/nvme0n1")
        self.assertEqual(sorted(seen["items"]), ["barco-tool", "vlc-3.0.24"])
        self.assertIn("Item = 'vlc-3.0.24'", seen["script"])
        self.assertIn("Item = 'barco-tool'", seen["script"])
        self.assertEqual(len(done), 1)
        chosen, error = done[0]
        self.assertIsNone(error)
        labels = [e.label for e in software.plan(self.nas, ["barco-tool", "vlc-3.0.24"]).entries]
        self.assertIn("VLC media player 3.0.24", labels)
        self.assertEqual(chosen, ", ".join(labels))                   # Reihenfolge wie gewählt
        self.assertLess(seen["script"].index("Item = 'barco-tool'"), seen["script"].index("Item = 'vlc-3.0.24'"))
        self.assertEqual(result, "wird beim nächsten Windows-Start installiert")
        log = "\n".join(job.log)
        self.assertIn("nächsten Windows-Start", log)
        self.assertIn("okula-software.log", log)
        target = self.win / "ProgramData/Okula/Software"
        self.assertEqual((target / "vlc-3.0.24/vlc-3.0.24-win64.exe").read_bytes(), NSIS)
        ps1 = (self.gp / "Machine/Scripts/Startup/okula-software.ps1").read_bytes()
        self.assertIn(b"Item = 'barco-tool'", ps1)

    def test_history_text_and_label(self):
        self.assertEqual(jobs.software_history("Software installieren (VLC media player 3.0.24)"),
                         "Software installieren (VLC media player 3.0.24) – wird beim nächsten Start installiert")
        self.assertEqual(jobs.Job(1, "d", "software", "/dev/sda", "x").label, "Software installieren")
        self.assertIn("software", jobs.NETWORK_KINDS)

    def test_nothing_installable_fails_cleanly(self):
        jm = jobs.JobManager()
        job = jobs.Job(1, "d1", "software", "/dev/sda", "x")
        done = []
        work = jobs.software_work("127.0.0.1", b"k", 1, "/dev/sda", str(self.nas), ["gibt-es-nicht"], "PC-1",
                                  lambda j, chosen, err: done.append((chosen, err)))
        with self.assertRaises(agentclient.AgentError):
            work(job, jm)
        self.assertIsNone(done[0][0])
        self.assertIsInstance(done[0][1], agentclient.AgentError)

    def test_with_pending_windows_anpassen(self):
        """„Windows anpassen“ steht noch aus: Software kommt dazu, die Originale bleiben, beide Startskripte stehen
        in scripts.ini; das zuletzt laufende stellt die Gruppenrichtlinie her."""
        (self.gp / "Machine/Scripts").mkdir(parents=True)
        (self.gp / "gpt.ini").write_bytes(b"[General]\r\nVersion=7\r\n")
        deploy.install_startup_script(self.win, "# Windows anpassen")
        after = (self.gp / "gpt.ini.okula-nachher").read_bytes()
        _seen, done, _result, job = self.run_job(["vlc-3.0.24"])
        self.assertIsNone(done[0][1])
        self.assertEqual((self.gp / "gpt.ini.okula-nachher").read_bytes(), after)
        ini = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()[2:].decode("utf-16-le")
        self.assertIn("0CmdLine=okula-windows-anpassen.cmd", ini)
        self.assertIn("1CmdLine=okula-software.cmd", ini)
        self.assertIn("Windows anpassen) steht noch aus", "\n".join(job.log))
        startup = self.gp / "Machine/Scripts/Startup"
        self.assertEqual(sorted(p.name for p in startup.iterdir()),
                         ["okula-software.cmd", "okula-software.ps1", "okula-windows-anpassen.cmd",
                          "okula-windows-anpassen.ps1"])
        # beide Skripte räumen nur auf, wenn kein anderes Okula-Startskript mehr wartet (RESTORE_START)
        ps1 = (startup / "okula-software.ps1").read_bytes().decode("utf-8-sig")
        self.assertIn("Filter 'okula-*.cmd'", ps1)
        self.assertIn("$saved = $file + '.okula-nachher'", ps1)
        for cmd in ("okula-software.cmd", "okula-windows-anpassen.cmd"):
            self.assertIn("if defined OKULA_ANDERE goto ende", (startup / cmd).read_text(encoding="ascii"))

    def test_windows_anpassen_after_software(self):
        """Umgekehrt: erst Software, dann „Windows anpassen“ – das zweite Skript kommt nur dazu."""
        self.run_job(["vlc-3.0.24"])
        orig_ini = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()
        with mock.patch.object(deploy, "_candidates",
                               lambda d: [{"path": "/dev/nvme0n1p3", "fstype": "ntfs", "size": 1 << 35}]), \
                mock.patch.object(deploy.filebackup, "Mounts", FakeMounts({"/dev/nvme0n1p3": self.win})), \
                mock.patch.object(deploy.subprocess, "run"):
            result = deploy.tweak({"disk": "/dev/nvme0n1", "script": "# Windows anpassen"}, log=lambda *_a: None)
        self.assertTrue(result.get("shared"))
        self.assertFalse((self.gp / "gpt.ini.okula-nachher").exists())   # es gab vorher keine Richtlinie
        ini = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()[2:].decode("utf-16-le")
        self.assertIn("0CmdLine=okula-software.cmd", ini)
        self.assertIn("1CmdLine=okula-windows-anpassen.cmd", ini)
        self.assertNotEqual(orig_ini, (self.gp / "Machine/Scripts/scripts.ini").read_bytes())
        # erneut Software senden: nur Skript und Installer ersetzt, Eintrag bleibt einmal
        self.run_job(["barco-tool"])
        ini2 = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()[2:].decode("utf-16-le")
        self.assertEqual(ini2, ini)
        self.assertEqual([p.name for p in (self.win / "ProgramData/Okula/Software").iterdir()], ["barco-tool"])


@unittest.skipUnless(__import__("tests.test_wintweaks", fromlist=["gtk_available"]).gtk_available(),
                     "braucht GTK mit Bildschirm")
class DialogTest(unittest.TestCase):
    def test_only_ready_selectable_send_needs_selection(self):
        import time
        from gi.repository import GLib
        from okula_recovery.software_ui import SoftwareInstallDialog
        from tests.test_software import UNKNOWN, Library
        lib = Library()
        with lib.tmp:
            lib.load("vlc-3.0.24-win64.exe", NSIS)
            lib.load("unbekannt.exe", UNKNOWN)
            dlg = SoftwareInstallDialog(None, "PC-1", str(lib.root))
            for _ in range(500):
                if dlg.chooser.loaded:
                    break
                GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
            self.assertTrue(dlg.chooser.loaded)
            self.assertFalse(dlg.btn.get_sensitive())                  # nichts gewählt
            rows = {row[dlg.chooser.C_NAME]: row for row in dlg.chooser.store}
            self.assertFalse(rows["unbekannt"][dlg.chooser.C_OK])      # „Parameter fehlt“ ausgegraut
            rows["vlc-3.0.24"][dlg.chooser.C_ON] = True
            dlg.chooser._update_total()
            dlg._update()
            self.assertTrue(dlg.btn.get_sensitive())
            self.assertEqual(dlg.selected(), ["vlc-3.0.24"])
            self.assertEqual(dlg.summary(), "VLC media player 3.0.24")
            self.assertIn("nächsten Windows-Start", dlg.chooser.total.get_text())
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
