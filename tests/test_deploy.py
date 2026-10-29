"""Gerät anpassen (Master-Image), Ordner auf den Desktop, Countdown – Agent und Tool über TLS auf Loop-Disks."""

import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, deploy, distribute, filebackup, inventory, winunattend, wire
from tests.test_restore import can_run, loop_disks, sh


class HelpersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_windows_state_case_insensitive(self):
        self.assertEqual(deploy.windows_state(self.root), "")
        (self.root / "WINDOWS/system32/Config").mkdir(parents=True)
        (self.root / "WINDOWS/system32/Config/SYSTEM").write_bytes(b"regf")
        self.assertEqual(deploy.windows_state(self.root), "installed")
        (self.root / "WINDOWS/Setup/State").mkdir(parents=True)
        (self.root / "WINDOWS/Setup/State/State.ini").write_bytes(
            "[State]\r\nImageState=IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE\r\n".encode("utf-16"))
        self.assertEqual(deploy.windows_state(self.root), "generalized")
        target = deploy.write_unattend(self.root, "<unattend/>")
        self.assertEqual(target, self.root / "WINDOWS/Panther/unattend.xml")
        (self.root / "WINDOWS/Panther/unattend.xml").rename(self.root / "WINDOWS/Panther/Unattend.XML")
        self.assertEqual(deploy.write_unattend(self.root, "<neu/>").name, "Unattend.XML")  # vorhandene ersetzen

    def test_linux_hostname(self):
        (self.root / "etc").mkdir()
        (self.root / "etc/hostname").write_text("alt\n")
        (self.root / "etc/hosts").write_text("127.0.0.1\tlocalhost\n127.0.1.1\talt.example alt\n"
                                             "10.0.0.5 alt intranet\n# alt bleibt\n")
        self.assertEqual(deploy.set_linux_hostname(self.root, "dons-elitebook-1"), "alt")
        self.assertEqual((self.root / "etc/hostname").read_text(), "dons-elitebook-1\n")
        hosts = (self.root / "etc/hosts").read_text()
        self.assertIn("127.0.1.1\tdons-elitebook-1\n", hosts)
        self.assertIn("10.0.0.5\tdons-elitebook-1\tintranet\n", hosts)
        self.assertIn("# alt bleibt", hosts)
        with self.assertRaises(deploy.ImagingError):
            deploy.set_linux_hostname(self.root, "Ungültig_Name")

    def test_master_unattend(self):
        xml = winunattend.master_unattend("DoNs_EliteBook_1", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE", True, "Benutzer")
        self.assertIn("<ComputerName>DoNs-EliteBook</ComputerName>", xml)   # Windows: max. 15 Zeichen
        self.assertIn("<ProductKey>AAAAA-BBBBB-CCCCC-DDDDD-EEEEE</ProductKey>", xml)
        self.assertIn("<TimeZone>W. Europe Standard Time</TimeZone>", xml)
        self.assertIn("<InputLocale>0807:00000807</InputLocale>", xml)
        self.assertNotIn("UILanguage", xml)          # Sprache bleibt die des Images
        self.assertNotIn('pass="windowsPE"', xml)
        self.assertIn("logonpasswordchg:yes", xml)   # Passwort beim ersten Anmelden, nirgends gespeichert
        plain = winunattend.master_unattend("PC", "", False, "")
        self.assertNotIn("ProductKey", plain)
        self.assertNotIn("International-Core", plain)
        self.assertNotIn("LocalAccount", plain)

    def test_esc_from_input_events(self):
        r, w = os.pipe()
        try:
            os.set_blocking(r, False)
            os.write(w, deploy.EVENT.pack(0, 0, 1, 30, 1))          # Taste A
            self.assertFalse(deploy.esc_pressed([r]))
            os.write(w, deploy.EVENT.pack(0, 0, 1, 1, 0))           # Esc losgelassen zählt nicht
            self.assertFalse(deploy.esc_pressed([r]))
            os.write(w, deploy.EVENT.pack(0, 0, 4, 4, 1) + deploy.EVENT.pack(0, 0, 1, 1, 1))
            self.assertTrue(deploy.esc_pressed([r]))
        finally:
            os.close(r)
            os.close(w)


class DistributePlanTest(unittest.TestCase):
    def test_layout_projects_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas = Path(tmp)
            base = distribute.ensure(nas)
            self.assertEqual(sorted(p.name for p in base.iterdir()), ["Content", "Software", "Test Files"])
            (base / "Software/Setup.exe").write_bytes(b"MZ" * 10)
            (base / "Software/Leer").mkdir()
            (base / "Content/Projekt B/Daten").mkdir(parents=True)
            (base / "Content/Projekt B/Daten/a.txt").write_text("a")
            (base / "Content/Projekt A").mkdir()
            (base / "Content/.versteckt").mkdir()
            (base / "Content/Projekt B/link").symlink_to("/etc/passwd")
            self.assertEqual(distribute.projects(nas), ["Projekt A", "Projekt B"])
            items = distribute.items_for(True, False, ["Projekt B"])
            self.assertEqual(items, ["Software", "Content/Projekt B"])
            self.assertEqual(distribute.describe(items), "Software, Content: Projekt B")
            plan = distribute.plan(nas, items)
            self.assertEqual((plan.files, plan.bytes), (2, 21))
            paths = [(e[0], e[1]) for e in plan.entries]
            self.assertIn(("dir", "Software/Leer"), paths)
            self.assertIn(("file", "Content/Projekt B/Daten/a.txt"), paths)
            self.assertEqual(plan.skipped, ["Content/Projekt B/link"])
            for bad in ("../x", "Content", "Andere", "Content/a/b"):
                with self.assertRaises(distribute.DistributeError):
                    distribute.plan(nas, [bad])
            with self.assertRaises(distribute.DistributeError):
                distribute.plan(nas, ["Content/Fehlt"])


@unittest.skipUnless(can_run() and all(map(__import__("shutil").which, ("mkfs.ntfs", "ntfs-3g"))),
                     "braucht root, Loop-Devices und ntfs-3g")
class DeployE2ETest(unittest.TestCase):
    """Disk mit Windows (NTFS, generalisiert) und Linux (ext4) – wie nach dem Zurückspielen eines Master-Images."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        img = self.d / "disk.img"
        with open(img, "wb") as f:
            f.truncate(256 * 1024 * 1024)
        self.dev = sh("losetup", "-fP", "--show", str(img)).strip()
        sh("sfdisk", "-q", self.dev, input="label: gpt\nstart=2048, size=8M\nstart=, size=120M\nstart=, size=100M\n")
        sh("partx", "-u", self.dev)
        agent.imaging._wait_for([f"{self.dev}p1", f"{self.dev}p2", f"{self.dev}p3"])
        sh("mkfs.vfat", f"{self.dev}p1")
        sh("mkfs.ntfs", "-Q", "-F", f"{self.dev}p2")
        mnt = self.d / "m"
        mnt.mkdir()
        sh("ntfs-3g", f"{self.dev}p2", str(mnt))
        try:
            for rel, data in {"Windows/System32/config/SYSTEM": b"regf",
                              "Windows/Setup/State/State.ini":
                                  b"[State]\r\nImageState=IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE\r\n",
                              "Users/Public/Desktop/desktop.ini": b"[.ShellClassInfo]",
                              "Users/Public/Desktop/Software/alt.txt": b"alter Stand",
                              "Users/Public/Desktop/Content/Projekt A/bleibt.txt": b"A"}.items():
                (mnt / rel).parent.mkdir(parents=True, exist_ok=True)
                (mnt / rel).write_bytes(data)
        finally:
            sh("umount", str(mnt))
        lin = self.d / "lin"
        for rel, text in {"etc/os-release": 'PRETTY_NAME="Debian GNU/Linux 13"\n', "etc/hostname": "alt\n",
                          "etc/hosts": "127.0.0.1 localhost\n127.0.1.1 alt\n", "bin/sh": ""}.items():
            (lin / rel).parent.mkdir(parents=True, exist_ok=True)
            (lin / rel).write_text(text)
        sh("mkfs.ext4", "-q", "-F", "-d", str(lin), f"{self.dev}p3")
        self.key = bytes(range(32))
        self.patches = [mock.patch.object(agent, "log", lambda *a, **k: None),
                        mock.patch.object(filebackup, "WORK", self.d / "work"),
                        mock.patch.object(inventory, "MIN_OS_PARTITION", 50 * 1024 * 1024),
                        mock.patch.object(agent.imaging, "list_disks", lambda: loop_disks(self.dev))]
        for p in self.patches:
            p.start()
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        ctx = wire.server_context(self.key)

        def serve():
            while True:
                try:
                    conn, addr = self.server.accept()
                except OSError:
                    return
                threading.Thread(target=agent.handle_connection, args=(ctx, conn, addr), daemon=True).start()

        threading.Thread(target=serve, daemon=True).start()

    def tearDown(self):
        self.server.close()
        for p in self.patches:
            p.stop()
        subprocess.run(["umount", str(self.d / "m")], capture_output=True)
        subprocess.run(["losetup", "-d", self.dev], capture_output=True)
        self.tmp.cleanup()

    def read(self, part, rel, fs="ntfs-3g"):
        mnt = self.d / "m"
        sh(fs, f"{self.dev}{part}", str(mnt)) if fs == "ntfs-3g" else sh("mount", f"{self.dev}{part}", str(mnt))
        try:
            p = mnt / rel
            return sorted(x.name for x in p.iterdir()) if p.is_dir() else p.read_bytes()
        finally:
            sh("umount", str(mnt))

    def test_customize_master_and_linux(self):
        xml = winunattend.master_unattend("DoNs_EliteBook_1", "", True, "")
        results = agentclient.customize("127.0.0.1", self.key, self.dev, xml, "dons-elitebook-1", self.port)
        self.assertEqual({(r["part"][-2:], r["system"], r["action"]) for r in results},
                         {("p2", "windows", "unattend"), ("p3", "linux", "hostname")})
        self.assertEqual(self.read("p2", "Windows/Panther/unattend.xml").decode(), xml)
        self.assertEqual(self.read("p3", "etc/hostname", "mount"), b"dons-elitebook-1\n")
        # nicht generalisiert: nichts anfassen, nur melden
        mnt = self.d / "m"
        sh("ntfs-3g", f"{self.dev}p2", str(mnt))
        (mnt / "Windows/Setup/State/State.ini").write_bytes(b"[State]\r\nImageState=IMAGE_STATE_COMPLETE\r\n")
        (mnt / "Windows/Panther/unattend.xml").unlink()
        sh("umount", str(mnt))
        results = agentclient.customize("127.0.0.1", self.key, self.dev, xml, "", self.port)
        self.assertIn(("windows", "not_generalized"), {(r["system"], r["action"]) for r in results})
        self.assertEqual(self.read("p2", "Windows/Panther"), [])

    def test_deliver_replaces_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            nas = Path(tmp)
            base = distribute.ensure(nas)
            (base / "Software/Tool/setup.exe").parent.mkdir(parents=True)
            (base / "Software/Tool/setup.exe").write_bytes(b"MZ" * 50000)
            (base / "Software/Leer").mkdir()
            (base / "Content/Projekt B").mkdir(parents=True)
            (base / "Content/Projekt B/plan.pdf").write_bytes(b"%PDF")
            plan = distribute.plan(nas, distribute.items_for(True, False, ["Projekt B"]))
            events = []
            result = agentclient.deliver("127.0.0.1", self.key, self.dev, plan.items, plan.entries, plan.bytes,
                                         events.append, threading.Event(), self.port)
        self.assertEqual(result["files"], 2)
        desk = "Users/Public/Desktop"
        self.assertEqual(self.read("p2", desk), ["Content", "Software", "desktop.ini"])  # kein Zwischenordner
        self.assertEqual(self.read("p2", f"{desk}/Software"), ["Leer", "Tool"])          # alt.txt ersetzt
        self.assertEqual(self.read("p2", f"{desk}/Software/Tool/setup.exe"), b"MZ" * 50000)
        self.assertEqual(self.read("p2", f"{desk}/Content"), ["Projekt A", "Projekt B"])  # A bleibt
        self.assertEqual(self.read("p2", f"{desk}/Content/Projekt B/plan.pdf"), b"%PDF")

    def test_deliver_cancel_keeps_old_state(self):
        cancel = threading.Event()
        entries = [("dir", "Software", 0, 0, None)] + \
            [("file", f"Software/f{i}", 4, 0, __file__) for i in range(3)]

        def progress(ev):
            cancel.set()

        cancel.set()
        with self.assertRaises(agentclient.AgentError):
            agentclient.deliver("127.0.0.1", self.key, self.dev, ["Software"], entries, 12, progress, cancel,
                                self.port)
        time.sleep(0.5)
        desk = "Users/Public/Desktop"
        self.assertEqual(self.read("p2", f"{desk}/Software"), ["alt.txt"])
        self.assertEqual(self.read("p2", desk), ["Content", "Software", "desktop.ini"])

    def test_countdown_and_banner(self):
        console = self.d / "tty"
        console.write_text("")
        r, w = os.pipe()
        os.set_blocking(r, False)
        with mock.patch.object(agent, "console", str(console)), \
                mock.patch.object(deploy, "open_keyboards", lambda: [os.dup(r)]):
            self.assertEqual(agentclient.countdown("127.0.0.1", self.key, 1, "Test", threading.Event(),
                                                   port=self.port), "start")
            threading.Timer(0.5, os.write, args=(w, deploy.EVENT.pack(0, 0, 1, 1, 1))).start()
            self.assertEqual(agentclient.countdown("127.0.0.1", self.key, 20, "Test", threading.Event(),
                                                   port=self.port), "esc")
            cancel = threading.Event()
            threading.Timer(0.5, cancel.set).start()
            ticks = []
            self.assertEqual(agentclient.countdown("127.0.0.1", self.key, 20, "Test", cancel, ticks.append,
                                                   self.port), "tool")
            self.assertEqual(ticks[0], 20)
            self.assertTrue(agentclient.banner("127.0.0.1", self.key, ["Automatisierung fehlgeschlagen: X",
                                                                       "Gerät neu anschliessen"], True, self.port))
        time.sleep(0.3)
        screen = console.read_text()
        self.assertIn("Esc zum Abbrechen", screen)
        self.assertIn("mit Esc abgebrochen", screen)
        self.assertIn("im Tool abgebrochen", screen)
        self.assertIn("!!!!", screen)
        self.assertIn("Gerät neu anschliessen", screen)
        os.close(r)
        os.close(w)


if __name__ == "__main__":
    unittest.main()
