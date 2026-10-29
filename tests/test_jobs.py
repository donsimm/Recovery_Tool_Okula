import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, imaging, jobs, wire


def fake_disk(root: Path, name: str, data: bytes) -> dict:
    part = root / f"{name}1.bin"
    part.write_bytes(data)
    disk = root / f"{name}.bin"
    disk.write_bytes(b"\0" * 4 * 1024 * 1024)
    return {"name": name, "path": str(disk), "size": disk.stat().st_size, "model": f"Disk {name}", "serial": "",
            "transport": "", "pttype": "gpt", "fstype": "",
            "partitions": [{"name": f"{name}1", "path": str(part), "size": len(data), "fstype": "",
                            "label": "", "uuid": "", "parttype": "", "mounted": False}]}



class ParallelJobsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.nas = root / "nas"
        self.nas.mkdir()
        self.disks = [fake_disk(root, "sda", b"A" * 3_000_000), fake_disk(root, "sdb", b"B" * 3_000_000)]
        self.key = bytes(range(32))
        self.patches = [
            mock.patch.object(imaging, "list_disks", lambda: self.disks),
            mock.patch.object(imaging.shutil, "which", lambda n: None if n == "zstd" else n),
            # langsam lesen (pv-artig), damit sich beide Aufträge überlappen
            mock.patch.object(imaging, "partition_command",
                              lambda p: ("dd.img", ["sh", "-c", f"sleep 1; cat '{p['path']}'"])),
            mock.patch.object(agent, "log", lambda *a, **k: None),
            mock.patch.object(agent.inventory, "collect",
                              lambda with_os=True, skip=frozenset(): {"dmi": {"product_name": "Test"}, "skip": sorted(skip)}),
        ]
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
        self.tmp.cleanup()

    def test_two_disks_in_parallel_same_disk_refused(self):
        changes = []
        jm = jobs.JobManager(on_change=changes.append)
        results = {}

        def after(job, path, error):
            results[job.disk] = (path, error)

        def start(disk):
            return jm.start("dev1", "image", disk["path"], f"Disk-Image {disk['name']}",
                            jobs.image_work("127.0.0.1", self.key, self.port, disk, str(self.nas), "PC",
                                            {"device_id": "dev1"}, after))

        j1, j2 = start(self.disks[0]), start(self.disks[1])
        with self.assertRaisesRegex(agentclient.AgentError, "läuft bereits"):
            start(self.disks[0])  # gleiche Disk: abgelehnt
        time.sleep(0.5)
        self.assertEqual(len(jm.running()), 2, "beide Aufträge sollten gleichzeitig laufen")
        text, fraction = jm.status("dev1")
        self.assertRegex(text, r"^2 Aufträge \d+ %")
        self.assertIsNotNone(fraction)
        deadline = time.time() + 30
        while jm.running() and time.time() < deadline:
            time.sleep(0.1)
        self.assertEqual([j1.state, j2.state], [jobs.DONE, jobs.DONE], j1.log + j2.log)
        for disk, job in zip(self.disks, (j1, j2)):
            path, error = results[disk["path"]]
            self.assertIsNone(error)
            meta = json.loads((Path(path) / "okula-image.json").read_text())
            self.assertEqual(meta["source"]["device_id"], "dev1")
            self.assertTrue(any("Übertrage" in line for line in job.log))
        self.assertGreater(j2.started, 0)
        self.assertLess(abs(j1.started - j2.started), 1.0)

    def test_agent_refuses_same_disk_twice(self):
        self.assertTrue(agent.disk_locks.acquire(self.disks[0]["path"], "image"))
        try:
            with self.assertRaisesRegex(agentclient.AgentError, "läuft bereits"):
                agentclient.create_image("127.0.0.1", self.key, self.disks[0]["path"], self.nas, "PC",
                                         lambda e: None, threading.Event(), self.port)
        finally:
            agent.disk_locks.release(self.disks[0]["path"])

    def test_inventory_cached_and_refresh_blocked_during_job(self):
        agent.inventory_state.data = None
        data = agentclient.get_inventory("127.0.0.1", self.key, self.port)
        self.assertEqual(data["dmi"]["product_name"], "Test")
        version = agent.inventory_state.version
        agentclient.get_inventory("127.0.0.1", self.key, self.port)
        self.assertEqual(agent.inventory_state.version, version, "zweiter Abruf sollte den Cache nutzen")
        self.assertTrue(agent.disk_locks.acquire("/dev/sdz", "image"))
        try:
            with self.assertRaisesRegex(agentclient.AgentError, "Auftrags"):
                agentclient.get_inventory("127.0.0.1", self.key, self.port, refresh=True)
        finally:
            agent.disk_locks.release("/dev/sdz")

    def test_failed_job_logged(self):
        jm = jobs.JobManager()
        bad = dict(self.disks[0], path="/does/not/exist")
        job = jm.start("dev1", "image", bad["path"], "kaputt",
                       jobs.image_work("127.0.0.1", self.key, self.port, bad, str(self.nas), "PC", {},
                                       lambda *a: None))
        deadline = time.time() + 10
        while job.running and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(job.state, jobs.FAILED)
        self.assertIn("nicht gefunden", job.log[-1])


if __name__ == "__main__":
    unittest.main()


class LastFailedTest(unittest.TestCase):
    """Roter Balken: letzter Auftrag fehlgeschlagen – bis der nächste startet."""

    def wait(self, job):
        for _ in range(200):
            if not job.running:
                return
            time.sleep(0.01)

    def test_last_failed(self):
        jm = jobs.JobManager()
        self.assertIsNone(jm.last_failed("d1"))

        def fail(job, m):
            raise RuntimeError("kaputt")

        bad = jm.start("d1", "restore", "/dev/sda", "Zurückspielen", fail)
        self.wait(bad)
        self.assertIs(jm.last_failed("d1"), bad)
        self.assertIsNone(jm.last_failed("d2"))
        release = threading.Event()
        ok = jm.start("d1", "image", "/dev/sda", "Image", lambda job, m: release.wait(5) and "ok")
        self.assertIsNone(jm.last_failed("d1"))   # läuft wieder etwas: kein roter Balken
        release.set()
        self.wait(ok)
        self.assertIsNone(jm.last_failed("d1"))   # neuester Auftrag erfolgreich


class EtaTest(unittest.TestCase):
    def test_remaining_and_text(self):
        job = jobs.Job(1, "dev", "image", "/dev/sda", "Disk-Image sda", started=time.time() - 600, fraction=0.25)
        self.assertAlmostEqual(job.remaining, 1800, delta=5)
        self.assertEqual(jobs.eta_text(job.remaining), "noch 30 min")
        self.assertEqual(jobs.eta_text(4000), "noch 1 h 06 min")
        self.assertIsNone(jobs.Job(2, "dev", "image", "/dev/sdb", "x", fraction=0.5).remaining)  # zu früh
        jm = jobs.JobManager()
        jm.jobs.append(job)
        self.assertEqual(jm.status("dev"), ("Disk-Image 25 % · noch 30 min", 0.25))

    def test_restore_phases_shown_separately(self):
        """Prüfung und Schreiben als eigene Schritte – wie am Agent-Bildschirm, nicht 29 % gesamt bei 96 % Prüfung."""
        jm = jobs.JobManager()
        job = jobs.Job(1, "dev", "restore", "/dev/sda", "Zurückspielen")
        jm.jobs.append(job)
        jm.progress(job, 0.96 * 0.3, "sda1.ntfs-ptcl-img.gz.aa", "Image prüfen (1/2)", 0.96)
        self.assertEqual(jm.parts("dev")[:2], ("Image prüfen (1/2)", 0.96))
        self.assertAlmostEqual(job.fraction, 0.288)
        jm.progress(job, 0.3 + 0.7 * 0.5, "sda1 · 90 MB/s", "Zurückspielen (2/2)", 0.5)
        self.assertEqual(jm.parts("dev")[:2], ("Zurückspielen (2/2)", 0.5))
        self.assertIsNone(job.remaining)  # neuer Schritt: Restzeit erst nach einigen Sekunden
        job.phase_started -= 60
        self.assertAlmostEqual(job.remaining, 60, delta=2)
