"""Demo ohne NAS (Ä-027): Demo-Speicher, fertige Demo-Images, Sperren, ganzer Vorführ-Ablauf ohne NAS."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from okula_recovery import (agentclient, archive, automation, backups, config, demo_agent, demostore, devices,
                            discovery, distribute, imagecheck, inventory_export, jobs, nas)

ROOT = Path(__file__).resolve().parent.parent


def snapshot(path: Path) -> dict:
    """Alle Dateien mit Grösse und Zeit – zum Vergleich vorher/nachher."""
    if not path.exists():
        return {}
    return {str(p.relative_to(path)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in path.rglob("*")}


def wait_for(cond, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


class DemoStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_ensure_layout_and_ready_images(self):
        root = demostore.ensure()
        self.assertEqual(root, Path(self.tmp.name) / "okula-recovery" / "demo")
        for d in ("images", backups.BACKUP_DIR, "Verteilen/Software", "Verteilen/Test Files", "Verteilen/Content"):
            self.assertTrue((root / d).is_dir(), d)
        self.assertEqual(distribute.projects(root), sorted(demostore.PROJECTS, key=str.lower))
        imgs = {i.path.name: i for i in archive.scan(root).all_images()}
        self.assertEqual(set(imgs), {demostore.MASTER, demostore.BROKEN})
        master, broken = imgs[demostore.MASTER], imgs[demostore.BROKEN]
        self.assertTrue(master.master and master.demo and broken.demo)
        self.assertFalse(broken.master)
        self.assertEqual(json.loads((master.path / agentclient.IMAGE_META).read_text())["machine"], "DEMO-PC")
        self.assertLess(sum(f.stat().st_size for f in master.path.iterdir()), 15_000_000)   # wenige MB
        self.assertEqual(imagecheck.check(master.path)["status"], imagecheck.OK)
        res = imagecheck.check(broken.path)
        self.assertEqual(res["status"], imagecheck.BROKEN)
        self.assertEqual(res["file"], "demo-nvme0n1p3.ntfs.pcl.zst")
        # zweites ensure ändert nichts an vorhandenen Images
        before = snapshot(root / "images")
        demostore.ensure()
        self.assertEqual(snapshot(root / "images"), before)

    def test_reset_and_recreate(self):
        root = demostore.ensure()
        (root / "images" / "eigenes").mkdir()
        demostore.reset()
        self.assertFalse(root.exists())
        demostore.ensure()
        self.assertEqual({p.name for p in (root / "images").iterdir()}, {demostore.MASTER, demostore.BROKEN})

    def test_access_rules_both_directions(self):
        demo_dev = devices.Device(id="d", agent_ids=[demo_agent.DEMO_ID])
        real_dev = devices.Device(id="r", agent_ids=["real-uuid"], key="uuid:real-uuid")
        self.assertTrue(demostore.is_demo_device(demo_dev))
        self.assertTrue(demostore.is_demo_device(devices.Device(id="k", key="uuid:okula-demo-0001")))
        self.assertFalse(demostore.is_demo_device(real_dev))
        root = demostore.ensure()
        nas_dir = Path(self.tmp.name) / "nas"
        self.assertEqual(demostore.root_for(demo_dev, str(nas_dir)), str(root))      # nie das NAS
        self.assertEqual(demostore.root_for(demo_dev, None), str(root))              # auch ohne NAS
        self.assertEqual(demostore.root_for(real_dev, str(nas_dir)), str(nas_dir))
        self.assertIsNone(demostore.root_for(real_dev, None))
        demo_img = root / "images" / demostore.MASTER
        real_img = nas_dir / "images" / "PC" / "2026"
        self.assertTrue(demostore.allowed(demo_dev, demo_img))
        self.assertFalse(demostore.allowed(real_dev, demo_img))
        self.assertFalse(demostore.allowed(demo_dev, real_img))
        self.assertTrue(demostore.allowed(real_dev, real_img))
        self.assertFalse(demostore.allowed(real_dev, real_img, demo_image=True))     # altes Demo-Image auf dem NAS
        imgs = [nas.ImageInfo("a", demo_img, "Disk-Image", 1, datetime.now(), demo=True),
                nas.ImageInfo("b", real_img, "Disk-Image", 1, datetime.now())]
        self.assertEqual([i.name for i in demostore.allowed_images(imgs, demo_dev)], ["a"])
        self.assertEqual([i.name for i in demostore.allowed_images(imgs, real_dev)], ["b"])
        # Backups gleich
        self.assertTrue(demostore.allowed(demo_dev, root / backups.BACKUP_DIR / "DEMO-PC" / "x"))
        self.assertFalse(demostore.allowed(real_dev, root / backups.BACKUP_DIR / "DEMO-PC" / "x"))

    def test_old_demo_images_on_nas_are_found(self):
        nas_dir = Path(self.tmp.name) / "nas"
        demostore.make_image(nas_dir / "images" / "DEMO-PC" / "2026-10-01_demo-nvme0n1")
        from tests.test_imagecheck import make_okula_image
        make_okula_image(nas_dir / "images" / "PC-01" / "2026-10-02_sda", {"a.img": b"x"})
        old = demostore.nas_demo_images(archive.scan(nas_dir).all_images())
        self.assertEqual([i.path.parent.name for i in old], ["DEMO-PC"])


class DemoWithoutNasTest(unittest.TestCase):
    """Ganzer Vorführ-Ablauf (B4) mit dem echten Demo-Agent – ohne NAS bzw. ohne das NAS zu berühren."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        cls.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(cls.d / "cfg")})
        cls.env.start()
        cls.key = bytes(range(32))
        (cls.d / "agent.key").write_text(cls.key.hex() + "\n")
        cls.flag = cls.d / "demo-fehler"
        cls.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cls.udp.bind(("127.0.0.1", 0))
        cls.udp.settimeout(10)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "okula_recovery.demo_agent", "--key-file", str(cls.d / "agent.key"),
             "--port", str(cls.udp.getsockname()[1]), "--control-port", str(cls.port),
             "--fail-flag", str(cls.flag), "--duration", "2"],
            env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        data, sender = cls.udp.recvfrom(discovery.MAX_PACKET + 1)
        cls.info = discovery.parse_beacon(data, sender[0])

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        cls.udp.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def register(self, store):
        inv = agentclient.get_inventory("127.0.0.1", self.key, self.port)
        dev, _ = store.register(self.info.agent_id, "127.0.0.1", "", inv, "DEMO-PC")
        return dev

    def run_flow(self, nas_root: str | None) -> None:
        demostore.reset()                         # Ausgangszustand wie nach „Demo-Daten zurücksetzen“
        store = devices.DeviceStore(self.d / f"geraete-{bool(nas_root)}")
        dev = self.register(store)
        self.assertTrue(demostore.is_demo_device(dev))
        root = Path(demostore.root_for(dev, nas_root))
        self.assertEqual(root, demostore.base())
        # 1 Disk-Image erstellen → Demo-Speicher
        image = agentclient.create_image("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, root, dev.name,
                                         lambda e: None, threading.Event(), port=self.port,
                                         source={"device_id": dev.id, "device_name": dev.name})
        self.assertTrue(image.is_relative_to(root))
        # 2 Image prüfen (✔) und Demo-Ordner prüfen: 2 ✔ (Master + eigenes), 1 ✖
        self.assertEqual(imagecheck.check(image)["status"], imagecheck.OK)
        paths = [str(i.path) for i in archive.scan(root).all_images()]
        results, cancelled = imagecheck.run(paths, lambda *a: None, lambda p, r: None, threading.Event())
        self.assertEqual(imagecheck.summary(results, cancelled), "3 Images geprüft: 2 ✔, 1 ✖")
        # 3 Master zurückspielen
        master = root / "images" / demostore.MASTER
        agentclient.restore_image("127.0.0.1", self.key, master, demo_agent.DEMO_DISK_PATH, lambda e: None,
                                  threading.Event(), self.port)
        # 4 Automatisierung mit dem Demo-Master
        disk = demo_agent.DISK
        dev.automation = automation.Settings(
            enabled=True, image=str(master.relative_to(root)), disk_key=automation.disk_key(disk),
            disk_label=automation.disk_label(disk), software=True, projects=[demostore.PROJECTS[0]],
            finish="none").to_dict()
        store.save(dev)
        self.assertEqual(automation.problems(automation.settings(dev), str(root)), [])
        jm = jobs.JobManager()
        cfg = config.Config()
        engine = automation.Engine(store, jm, self.key, lambda: nas_root, lambda: cfg,
                                   root_for=lambda d: demostore.root_for(d, nas_root))
        engine.countdown_seconds = 1
        self.assertTrue(engine.consider(dev, SimpleNamespace(ip="127.0.0.1", control_port=self.port)))
        self.assertTrue(wait_for(lambda: engine.run(dev.id).phase in ("done", "error"), 120))
        job = engine.run(dev.id).job
        self.assertEqual(engine.run(dev.id).phase, "done", "\n".join(job.log if job else []))
        # 5 Backup erstellen und zurückspielen
        parts = backups.get_profiles("127.0.0.1", self.key, self.port)
        sources = backups.profile_sources(parts[0]["part"], "Users/Anna", "windows", list(backups.DEFAULT_CATEGORIES))
        bk = backups.run_backup("127.0.0.1", self.key, self.port, demo_agent.DEMO_DISK_PATH, sources, str(root),
                                {"id": dev.id, "name": dev.name}, "profiles", "files", ["Demo"], lambda e: None,
                                threading.Event())
        self.assertTrue(Path(bk).is_relative_to(root))
        self.assertEqual([b.path for b in backups.list_backups(root)], [Path(bk)])
        plan = backups.RestorePlan(part=parts[0]["part"], mapping=[("", "")])
        backups.run_restore("127.0.0.1", self.key, self.port, demo_agent.DEMO_DISK_PATH, Path(bk), plan,
                            lambda e: None, threading.Event())
        # 6 Ordner senden aus dem Demo-Speicher
        dplan = distribute.plan(root, ["Software", f"{distribute.CONTENT}/{demostore.PROJECTS[1]}"])
        result = agentclient.deliver("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, dplan.items, dplan.entries,
                                     dplan.bytes, lambda e: None, threading.Event(), self.port)
        self.assertGreaterEqual(result["files"], 2)
        # 7 Inventar exportieren: letztes Image aus dem Demo-Speicher
        latest = inventory_export.latest_images(demostore.base(), [dev])
        self.assertIn(dev.id, latest)
        # 8 Fehler vorführen
        self.flag.touch()
        with self.assertRaisesRegex(agentclient.AgentError, "Demo: simulierter Fehler"):
            agentclient.create_image("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, root, dev.name,
                                     lambda e: None, threading.Event(), port=self.port)
        # Demo-Image auf ein echtes Gerät: weiterhin verweigert
        with self.assertRaisesRegex(agentclient.AgentError, "Demo-Image"):
            agentclient.restore_image("192.168.110.50", self.key, master, "/dev/sda", lambda e: None,
                                      threading.Event(), self.port)

    def test_a_without_nas(self):
        """Kein NAS eingehängt, der NAS-Pfad existiert nicht."""
        self.run_flow(None)

    def test_b_with_nas_nothing_written(self):
        nas_dir = self.d / "nas"
        (nas_dir / "images").mkdir(parents=True)
        (nas_dir / "images" / "echt.txt").write_text("echtes NAS")
        before = snapshot(nas_dir)
        self.run_flow(str(nas_dir))
        self.assertEqual(snapshot(nas_dir), before, "Demo hat auf dem NAS geschrieben")


if __name__ == "__main__":
    unittest.main()
