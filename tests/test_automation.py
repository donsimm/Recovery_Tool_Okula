"""Automatisierung: Einstellungen, Vorlagen, 24 h, Warteschlange, Fehler – und ein ganzer Durchlauf auf Loop-Disks."""

import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from okula_recovery import (agent, agentclient, automation, config, deploy, devices, distribute, filebackup,
                            inventory, jobs, nas, wire)
from tests.test_restore import can_run, loop_disks, sh


def wait_for(cond, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_roundtrip_and_items(self):
        s = automation.Settings.from_dict({"enabled": True, "image_mode": "kaputt", "finish": "x",
                                           "projects": ["Projekt A", ""], "unbekannt": 1})
        self.assertEqual((s.image_mode, s.finish, s.projects), ("master", "reboot", ["Projekt A"]))
        s.software = True
        self.assertEqual(s.items, ["Software", "Content/Projekt A"])
        self.assertEqual(automation.Settings.from_dict(s.to_dict()), s)

    def test_templates(self):
        s = automation.Settings(enabled=True, backup=True, image="images/Master", disk_key="S1", software=True,
                                finish="poweroff")
        automation.save_template("Schulungs-PC", s)
        other = automation.Settings(disk_key="S2", enabled=False)
        merged = automation.apply_template(other, "Schulungs-PC")
        self.assertEqual((merged.backup, merged.image, merged.finish, merged.template), (True, "images/Master",
                                                                                          "poweroff", "Schulungs-PC"))
        self.assertEqual((merged.disk_key, merged.enabled), ("S2", False))   # gerätebezogen bleibt
        self.assertEqual(list(automation.load_templates()), ["Schulungs-PC"])
        automation.delete_template("Schulungs-PC")
        self.assertEqual(automation.load_templates(), {})
        with self.assertRaises(automation.AutomationError):
            automation.apply_template(other, "fehlt")

    def test_problems_and_rearm(self):
        with tempfile.TemporaryDirectory() as nasdir:
            img = Path(nasdir) / "images/Master"
            img.mkdir(parents=True)
            s = automation.Settings(image="images/Master", disk_key="S1")
            self.assertEqual(automation.problems(s, nasdir), ["Image ist nicht (mehr) als Master markiert: "
                                                              "images/Master"])
            nas.set_master(img, True)
            self.assertEqual(automation.problems(s, nasdir), [])
            self.assertEqual(automation.problems(automation.Settings(image="../x"), nasdir),
                             ["Ungültiger Image-Pfad: ../x", "Keine Zieldisk gewählt"])
            self.assertIn("NAS nicht verbunden", automation.problems(s, None))
        now = datetime(2026, 10, 30, 12, 0)
        s = automation.Settings(enabled=False, rearm=True, done_at="2026-10-30T07:00:00")
        self.assertEqual(automation.rearm_text(s, now), "wieder aktiv in 19 h")
        self.assertEqual(automation.rearm_text(s, now + timedelta(hours=18, minutes=30)), "wieder aktiv in 30 min")
        s.rearm = False
        self.assertEqual(automation.rearm_text(s, now), "")

    def test_disk_key(self):
        self.assertEqual(automation.disk_key({"serial": " S6ABC ", "model": "X", "size": 1}), "S6ABC")
        self.assertEqual(automation.disk_key({"serial": "", "model": "VBOX", "size": 5}), "VBOX|5")
        self.assertEqual(automation.disk_label({"model": "Samsung SSD", "size": 256e9, "serial": "S6"}),
                         "Samsung SSD 256 GB (S6)")


class EngineTest(unittest.TestCase):
    """Ablauf mit Attrappen statt Agent: Countdown, Warteschlange (N), Erfolg, Fehler, 24 h."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.nas = Path(self.tmp.name) / "nas"
        img = self.nas / "images/Master"
        img.mkdir(parents=True)
        nas.set_master(img, True)
        self.store = devices.DeviceStore(Path(self.tmp.name) / "geraete")
        self.jm = jobs.JobManager()
        self.cfg = config.Config(automation_max=1)
        self.changes = []
        self.engine = automation.Engine(self.store, self.jm, b"k" * 32, lambda: str(self.nas), lambda: self.cfg,
                                        self.changes.append)
        self.release = {}
        self.countdown_result = "start"
        self.banners = []

        def countdown(ip, key, seconds, title, cancel, tick, port):
            tick(seconds)
            return self.countdown_result

        def fake_work(ip, key, port, dev, s, nas_root, error):
            def work(job, jm):
                ev = self.release.setdefault(dev.id, threading.Event())
                ev.wait(10)
                if dev.name == "Kaputt":
                    error.update(step="Schritt 2/5 Image zurückspielen", message="Image beschädigt")
                    raise RuntimeError("Image beschädigt")
                return "ok"
            return work

        self.patches = [mock.patch.object(agentclient, "countdown", countdown),
                        mock.patch.object(agentclient, "banner",
                                          lambda ip, key, lines, error=False, port=0:
                                          self.banners.append((lines, error)) or True),
                        mock.patch.object(automation, "automation_work", fake_work)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for ev in self.release.values():
            ev.set()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def device(self, name, enabled=True):
        dev, _ = self.store.register(f"agent-{name}", "10.0.0.1", "", {"dmi": {"product_uuid": f"uuid-{name}"}},
                                     name)
        dev.name = name
        dev.automation = automation.Settings(enabled=enabled, image="images/Master", disk_key="S1").to_dict()
        self.store.save(dev)
        return dev

    def agent(self):
        return SimpleNamespace(ip="10.0.0.1", control_port=47812)

    def test_queue_success_and_rearm(self):
        a, b = self.device("A"), self.device("B")
        off = self.device("Aus", enabled=False)
        self.assertFalse(self.engine.consider(off, self.agent()))
        self.assertTrue(self.engine.consider(a, self.agent()))
        self.assertTrue(wait_for(lambda: self.engine.run(a.id).phase == "running"))
        self.assertTrue(self.engine.consider(b, self.agent()))
        self.assertTrue(wait_for(lambda: self.engine.run(b.id).phase == "waiting"))
        self.assertEqual(self.engine.text(b), "Automatisierung wartet (Platz 1 in der Warteschlange)")
        self.assertFalse(self.engine.consider(a, self.agent()))        # läuft schon
        self.release.setdefault(a.id, threading.Event()).set()
        self.assertTrue(wait_for(lambda: self.engine.run(a.id).phase == "done"))
        self.assertTrue(wait_for(lambda: self.engine.run(b.id).phase == "running"))   # rückt nach
        sa = automation.settings(a)
        self.assertFalse(sa.enabled)
        self.assertTrue(sa.done_at)
        self.assertEqual(self.engine.text(a), "Automatisierung fertig")
        self.assertIn("Automatisierung erfolgreich – wird in 24 h wieder eingeschaltet",
                      [h["text"] for h in a.history])
        # erledigt bleibt erledigt, bis das Gerät getrennt war; dann 24 h-Anzeige
        self.assertFalse(self.engine.consider(a, self.agent()))
        self.engine.offline(a.id)
        self.assertEqual(self.engine.text(a), "wieder aktiv in 24 h")
        self.assertEqual(self.engine.tick(datetime.now() + timedelta(hours=23)), [])
        self.assertEqual([d.id for d in self.engine.tick(datetime.now() + timedelta(hours=24, minutes=1))], [a.id])
        self.assertTrue(automation.settings(a).enabled)
        self.release.setdefault(b.id, threading.Event()).set()
        self.assertTrue(wait_for(lambda: self.engine.run(b.id).phase == "done"))

    def test_error_cancel_paused(self):
        bad = self.device("Kaputt")
        self.release[bad.id] = threading.Event()
        self.release[bad.id].set()
        self.engine.consider(bad, self.agent())
        self.assertTrue(wait_for(lambda: self.engine.run(bad.id).phase == "error"))
        s = automation.settings(bad)
        self.assertTrue(s.enabled)                        # bleibt an: neuer Versuch nach neuem Anschliessen
        self.assertEqual(s.last_error, "Schritt 2/5 Image zurückspielen: Image beschädigt")
        self.assertEqual(self.engine.text(bad), "Automatisierung: Fehler – Gerät neu anschliessen")
        self.assertTrue(self.banners[-1][1])
        self.assertIn("Automatisierung fehlgeschlagen: Schritt 2/5", self.banners[-1][0][0])
        self.assertFalse(self.engine.consider(bad, self.agent()))   # nicht sofort wieder
        self.engine.offline(bad.id)
        # Esc am Gerät
        self.countdown_result = "esc"
        self.engine.consider(bad, self.agent())
        self.assertTrue(wait_for(lambda: self.engine.run(bad.id).phase == "cancelled"))
        self.assertEqual(self.engine.text(bad), "Automatisierung am Gerät mit Esc abgebrochen")
        self.engine.offline(bad.id)
        self.assertEqual(self.engine.text(bad), "Automatisierung ein – letzter Versuch fehlgeschlagen")
        # Hauptschalter
        self.cfg.automation_paused = True
        self.assertFalse(self.engine.consider(bad, self.agent()))
        self.assertEqual(self.engine.text(bad), "Automatisierung pausiert")
        self.cfg.automation_paused = False
        # unvollständig
        bad.automation = automation.Settings(enabled=True).to_dict()
        self.assertFalse(self.engine.consider(bad, self.agent()))
        self.assertEqual(self.engine.text(bad), "Automatisierung: Einstellungen unvollständig")


@unittest.skipUnless(can_run() and all(map(shutil.which, ("mkfs.ntfs", "ntfs-3g", "partclone.ntfs"))),
                     "braucht root, Loop-Devices, ntfs-3g und partclone")
class AutomationE2ETest(unittest.TestCase):
    """Master-Image (Windows nach Sysprep, NTFS) → Automatisierung auf einer zweiten Disk: Zurückspielen,
    Anpassen, Ordner senden – über den echten Agent (TLS)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.loops = []
        src = self.loop("src.img", 160)
        sh("sfdisk", "-q", src, input="label: gpt\nstart=2048, size=8M\nstart=, size=140M\n")
        sh("partx", "-u", src)
        agent.imaging._wait_for([f"{src}p1", f"{src}p2"])
        sh("mkfs.vfat", f"{src}p1")
        sh("mkfs.ntfs", "-Q", "-F", f"{src}p2")
        mnt = self.d / "m"
        mnt.mkdir()
        sh("ntfs-3g", f"{src}p2", str(mnt))
        try:
            for rel, data in {"Windows/System32/config/SYSTEM": b"regf",
                              "Windows/Setup/State/State.ini":
                                  b"[State]\r\nImageState=IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE\r\n",
                              "Users/Public/Desktop/desktop.ini": b"x",
                              "Users/Admin/Documents/a.txt": b"aus dem Master"}.items():
                (mnt / rel).parent.mkdir(parents=True, exist_ok=True)
                (mnt / rel).write_bytes(data)
        finally:
            sh("umount", str(mnt))
        self.src = src
        self.dst = self.loop("dst.img", 200)
        self.key = bytes(range(32))
        self.nas = self.d / "nas"
        base = distribute.ensure(self.nas)
        (base / "Software/setup.exe").write_bytes(b"MZ" * 1000)
        (base / "Content/Projekt A").mkdir()
        (base / "Content/Projekt A/info.txt").write_text("Projekt A")
        self.tty = self.d / "tty1"
        self.tty.touch()
        self.patches = [mock.patch.object(agent, "log", lambda *a, **k: None),
                        mock.patch.object(agent, "console", str(self.tty)),
                        mock.patch.object(agent, "power_action", lambda action: None),
                        mock.patch.object(filebackup, "WORK", self.d / "work"),
                        mock.patch.object(inventory, "MIN_OS_PARTITION", 50 * 1024 * 1024),
                        mock.patch.object(deploy, "open_keyboards", lambda: []),
                        mock.patch.object(agent.imaging, "list_disks", lambda: loop_disks(self.src, self.dst))]
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
        for dev in self.loops:
            subprocess.run(["losetup", "-d", dev], capture_output=True)
        self.tmp.cleanup()

    def loop(self, name, size_mb):
        path = self.d / name
        with open(path, "wb") as f:
            f.truncate(size_mb * 1024 * 1024)
        dev = sh("losetup", "-fP", "--show", str(path)).strip()
        self.loops.append(dev)
        return dev

    def test_full_run(self):
        image = agentclient.create_image("127.0.0.1", self.key, self.src, self.nas, "Master-Win11",
                                         lambda e: None, threading.Event(), port=self.port)
        nas.set_master(image, True)
        self.assertTrue(nas.image_at(image, self.nas).master)
        dst_disk = next(d for d in loop_disks(self.dst))
        store = devices.DeviceStore(self.d / "geraete")
        dev, _ = store.register("a1", "127.0.0.1", "", {"dmi": {"product_uuid": "u1"}}, "x")
        dev.name, dev.product_key = "DoNs_EliteBook_1", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"
        dev.automation = automation.Settings(
            enabled=True, image=str(image.relative_to(self.nas)), disk_key=automation.disk_key(dst_disk),
            disk_label=automation.disk_label(dst_disk), account="Benutzer", software=True,
            projects=["Projekt A"], finish="reboot").to_dict()
        store.save(dev)
        jm = jobs.JobManager()
        cfg = config.Config()
        engine = automation.Engine(store, jm, self.key, lambda: str(self.nas), lambda: cfg)
        engine.countdown_seconds = 1
        self.assertTrue(engine.consider(dev, SimpleNamespace(ip="127.0.0.1", control_port=self.port)))
        self.assertTrue(wait_for(lambda: engine.run(dev.id).phase in ("done", "error"), 120),
                        engine.run(dev.id))
        job = engine.run(dev.id).job
        self.assertEqual(engine.run(dev.id).phase, "done", "\n".join(job.log if job else []))
        log = "\n".join(job.log)
        self.assertIn("Schritt 2/5 – Image zurückspielen", log)
        self.assertIn("Windows (Master): Name DoNs-EliteBook, Key gesetzt", log)
        self.assertIn("Schritt 4/5 – Ordner senden: Software, Content: Projekt A", log)
        self.assertFalse(automation.settings(dev).enabled)

        mnt = self.d / "m"
        sh("ntfs-3g", f"{self.dst}p2", str(mnt))
        try:
            xml = (mnt / "Windows/Panther/unattend.xml").read_text()
            self.assertIn("<ComputerName>DoNs-EliteBook</ComputerName>", xml)
            self.assertIn("AAAAA-BBBBB-CCCCC-DDDDD-EEEEE", xml)
            self.assertEqual((mnt / "Users/Admin/Documents/a.txt").read_bytes(), b"aus dem Master")
            self.assertEqual((mnt / "Users/Public/Desktop/Software/setup.exe").read_bytes(), b"MZ" * 1000)
            self.assertEqual((mnt / "Users/Public/Desktop/Content/Projekt A/info.txt").read_text(), "Projekt A")
        finally:
            sh("umount", str(mnt))
        screen = self.tty.read_text()
        self.assertIn("Esc zum Abbrechen", screen)
        self.assertIn("Automatisierung fertig (DoNs_EliteBook_1)", screen)

    def test_wrong_disk_deletes_nothing(self):
        image = agentclient.create_image("127.0.0.1", self.key, self.src, self.nas, "Master",
                                         lambda e: None, threading.Event(), port=self.port)
        nas.set_master(image, True)
        store = devices.DeviceStore(self.d / "geraete")
        dev, _ = store.register("a1", "127.0.0.1", "", {"dmi": {"product_uuid": "u1"}}, "PC")
        dev.automation = automation.Settings(enabled=True, image=str(image.relative_to(self.nas)),
                                             disk_key="ANDERE-SERIENNUMMER", finish="none").to_dict()
        store.save(dev)
        before = subprocess.run(["sha256sum", self.dst], capture_output=True, text=True).stdout.split()[0]
        engine = automation.Engine(store, jobs.JobManager(), self.key, lambda: str(self.nas), config.Config)
        engine.countdown_seconds = 1
        engine.consider(dev, SimpleNamespace(ip="127.0.0.1", control_port=self.port))
        self.assertTrue(wait_for(lambda: engine.run(dev.id).phase == "error", 60))
        self.assertIn("Zieldisk ANDERE-SERIENNUMMER nicht im Gerät gefunden – nichts gelöscht",
                      automation.settings(dev).last_error)
        self.assertEqual(subprocess.run(["sha256sum", self.dst], capture_output=True, text=True).stdout.split()[0],
                         before)
        self.assertIn("Automatisierung fehlgeschlagen", self.tty.read_text())


if __name__ == "__main__":
    unittest.main()
