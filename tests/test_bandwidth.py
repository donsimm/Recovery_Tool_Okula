"""Bandbreite begrenzen (I-030): Limiter, Zeitfenster, Einstellungen, Auftrags-Log, Ende-zu-Ende über den Demo-Agent."""

import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, bandwidth, config, demo_agent, discovery, jobs, transfer, wire
from tests.test_transfer import Machine

ROOT = Path(__file__).resolve().parent.parent
CHUNK = 256 * 1024
MBIT = 1_000_000


class Recorder(bandwidth.Limiter):
    """Limiter, der festhält, wann wie viele Bytes freigegeben wurden."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.events: list[tuple[float, int]] = []
        self.ev_lock = threading.Lock()

    def take(self, nbytes):
        super().take(nbytes)
        with self.ev_lock:
            self.events.append((time.monotonic(), nbytes))

    def rate_bits(self, since: float = 0.0) -> float:
        """Durchsatz aus den Freigaben: (Bytes ohne die letzte) / (Zeit erste → letzte)."""
        ev = [e for e in self.events if e[0] >= since]
        span = ev[-1][0] - ev[0][0]
        return sum(n for _t, n in ev[1:]) * 8 / span


def pump(limiter: bandwidth.Limiter, seconds: float, counter: list, idx: int, stop: threading.Event | None = None):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not (stop and stop.is_set()):
        limiter.take(CHUNK)
        counter[idx] += CHUNK


class LimiterTest(unittest.TestCase):
    def assertRate(self, measured: float, limit: float):
        self.assertLess(abs(measured - limit) / limit, 0.10, f"{measured / MBIT:.1f} statt {limit / MBIT:.1f} Mbit/s")

    def test_single_stream_within_10_percent(self):
        lim = Recorder(lambda: 40 * MBIT)
        pump(lim, 2.0, [0], 0)
        self.assertRate(lim.rate_bits(), 40 * MBIT)

    def test_parallel_streams_share_fairly(self):
        lim = Recorder(lambda: 60 * MBIT)
        counts = [0, 0, 0]
        started = time.monotonic()
        threads = [threading.Thread(target=pump, args=(lim, 2.5, counts, i)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertRate(lim.rate_bits(), 60 * MBIT)                          # Summe ≤ Grenze (±10 %)
        self.assertLess(sum(counts) * 8 / (time.monotonic() - started), 60 * MBIT * 1.1)
        for c in counts:                                                     # je etwa ein Drittel
            self.assertAlmostEqual(c / sum(counts), 1 / 3, delta=0.05)

    def test_unlimited_by_default_and_none(self):
        self.assertFalse(config.Config().bandwidth.enabled)
        self.assertIsNone(bandwidth.active_mbit(bandwidth.Settings()))
        lim = bandwidth.Limiter(lambda: None)
        t = time.monotonic()
        for _ in range(2000):
            lim.take(CHUNK)                                                  # 500 MiB „sofort“
        self.assertLess(time.monotonic() - t, 1.0)
        # ohne Tool: wire hat keinen Limiter (Agent und andere Tests unverändert)
        out = subprocess.run([sys.executable, "-c", "from okula_recovery import wire; print(wire.get_limiter())"],
                             capture_output=True, text=True, cwd=ROOT, check=True).stdout.strip()
        self.assertEqual(out, "None")

    def test_change_during_transfer(self):
        rate = {"bits": 16 * MBIT}
        changes = []
        lim = Recorder(lambda: rate["bits"], changes.append)
        stop = threading.Event()
        t = threading.Thread(target=pump, args=(lim, 10, [0], 0, stop))
        t.start()
        time.sleep(1.2)
        self.assertRate(lim.rate_bits(), 16 * MBIT)
        switched = time.monotonic()
        rate["bits"] = 64 * MBIT                                             # sofort, ohne Neustart
        time.sleep(1.5)
        self.assertRate(lim.rate_bits(since=switched + 0.3), 64 * MBIT)
        rate["bits"] = None                                                  # Grenze aus → ungebremst
        time.sleep(0.4)
        n = len(lim.events)
        time.sleep(0.3)
        stop.set()
        t.join()
        self.assertGreater(len(lim.events) - n, 100)
        self.assertEqual(changes, [16 * MBIT, 64 * MBIT, None])

    def test_wire_send_and_receive_are_limited(self):
        lim = Recorder(lambda: 32 * MBIT)
        old = wire.get_limiter()
        wire.set_limiter(lim)
        try:
            a, b = socket.socketpair()
            got = []

            def drain():      # Gegenstelle ohne wire: liest roh mit
                while chunk := b.recv(1 << 20):
                    got.append(len(chunk))
            reader = threading.Thread(target=drain)
            reader.start()
            t = time.monotonic()
            for _ in range(12):
                wire.send_data(a, b"x" * CHUNK)
            a.close()
            reader.join()
            b.close()
            self.assertGreater(time.monotonic() - t, 11 * CHUNK * 8 / (32 * MBIT) * 0.9)
            self.assertRate(lim.rate_bits(), 32 * MBIT)
            # Empfangen: der Absender schreibt roh, wire.recv_frame bremst das Lesen
            lim.events.clear()
            a, b = socket.socketpair()

            def write():
                for _ in range(12):
                    a.sendall(struct.pack(">cI", wire.FRAME_DATA, CHUNK) + b"y" * CHUNK)
                wire.send_json(a, {"type": "ende"})
            writer = threading.Thread(target=write)
            writer.start()
            frames = 0
            while True:
                kind, payload = wire.recv_frame(b)
                if kind == wire.FRAME_JSON:
                    break
                frames += 1
            writer.join()
            a.close()
            b.close()
            self.assertEqual(frames, 12)
            self.assertRate(lim.rate_bits(), 32 * MBIT)
        finally:
            wire.set_limiter(old)


class WindowTest(unittest.TestCase):
    def s(self, **k):
        return bandwidth.clean({"enabled": True, "mbit": 300, "window": True, **k})

    def test_inside_outside_weekend(self):
        s = self.s()                                                         # Mo–Fr 07:00–18:00
        self.assertEqual(bandwidth.active_mbit(s, datetime(2026, 10, 30, 10, 0)), 300)    # Fr 10:00
        self.assertIsNone(bandwidth.active_mbit(s, datetime(2026, 10, 30, 18, 0)))        # Fr 18:00 = Ende
        self.assertIsNone(bandwidth.active_mbit(s, datetime(2026, 10, 30, 6, 59)))
        self.assertIsNone(bandwidth.active_mbit(s, datetime(2026, 10, 31, 10, 0)))        # Sa
        self.assertIsNone(bandwidth.active_mbit(s, datetime(2026, 11, 1, 10, 0)))         # So
        self.assertEqual(bandwidth.active_mbit(self.s(window=False), datetime(2026, 11, 1, 3, 0)), 300)  # immer
        self.assertIsNone(bandwidth.active_mbit(self.s(enabled=False), datetime(2026, 10, 30, 10, 0)))

    def test_over_midnight_and_whole_day(self):
        s = self.s(start="22:00", end="06:00", days=[4])                     # Freitagnacht
        self.assertTrue(bandwidth.in_window(s, datetime(2026, 10, 30, 23, 30)))           # Fr 23:30
        self.assertTrue(bandwidth.in_window(s, datetime(2026, 10, 31, 5, 59)))            # Sa 05:59 (Fr-Nacht)
        self.assertFalse(bandwidth.in_window(s, datetime(2026, 10, 31, 6, 0)))
        self.assertFalse(bandwidth.in_window(s, datetime(2026, 10, 30, 5, 0)))            # Fr früh = Do-Nacht
        self.assertFalse(bandwidth.in_window(s, datetime(2026, 10, 31, 23, 0)))           # Sa abends
        whole = self.s(start="00:00", end="00:00", days=[5, 6])
        self.assertTrue(bandwidth.in_window(whole, datetime(2026, 11, 1, 12, 0)))
        self.assertFalse(bandwidth.in_window(whole, datetime(2026, 11, 2, 12, 0)))

    def test_texts(self):
        self.assertEqual(bandwidth.window_text(self.s()), "Mo–Fr 07:00–18:00")
        self.assertEqual(bandwidth.window_text(self.s(days=[0, 2])), "Mo, Mi 07:00–18:00")
        self.assertEqual(bandwidth.fmt_mbit(10000), "10'000 Mbit/s")
        self.assertEqual(bandwidth.fmt_mbyte(300), "37.5 MB/s")
        self.assertEqual(bandwidth.fmt_mbyte(10000), "1'250 MB/s")
        friday = datetime(2026, 10, 30, 10, 0)
        self.assertEqual(bandwidth.describe(self.s(), friday),
                         "Bandbreite begrenzt auf 300 Mbit/s (Mo–Fr 07:00–18:00) – gilt für alle Aufträge zusammen")
        self.assertIn("unbegrenzt (ausserhalb", bandwidth.describe(self.s(), datetime(2026, 10, 31, 10, 0)))
        self.assertEqual(bandwidth.describe(bandwidth.Settings()), "")


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_limits(self):
        s = bandwidth.clean({"enabled": 1, "mbit": 5, "start": "25:00", "end": "7:5", "days": [0, 9, "x", True, 6]})
        self.assertEqual((s.mbit, s.start, s.end, s.days), (10, "07:00", "07:05", [0, 6]))
        self.assertEqual(bandwidth.clean({"mbit": 99999}).mbit, 10000)
        self.assertEqual(bandwidth.clean({"mbit": "abc"}).mbit, 300)
        self.assertEqual(bandwidth.clean("Unsinn"), bandwidth.Settings())

    def test_save_load_export_import(self):
        old, new = Machine(self.root / "alt"), Machine(self.root / "neu")
        with old:
            cfg = config.Config()
            cfg.bandwidth = bandwidth.Settings(True, 100, True, "22:00", "06:00", [5, 6])
            config.save(cfg)
            self.assertEqual(config.load().bandwidth, cfg.bandwidth)
            transfer.export_all(self.root / "x.zip", include_key=False, include_devices=False)
        with new:
            self.assertFalse(config.load().bandwidth.enabled)                # neuer Rechner: unbegrenzt
            transfer.import_all(transfer.read_export(self.root / "x.zip"), use_key=False, use_devices=False)
            self.assertEqual(config.load().bandwidth, bandwidth.Settings(True, 100, True, "22:00", "06:00", [5, 6]))
        # alte config.json ohne „bandwidth“: Standard
        p = self.root / "alt.json"
        p.write_text('{"automation_max": 3}')
        self.assertEqual(config.load(p).bandwidth, bandwidth.Settings())


class JobsTest(unittest.TestCase):
    def test_log_line_only_for_network_jobs_and_rebase(self):
        jm = jobs.JobManager()
        jm.start_note = lambda: "Bandbreite begrenzt auf 300 Mbit/s"
        gate = threading.Event()
        job = jm.start("dev", "image", "/dev/sda", "Disk-Image", lambda j, m: gate.wait(5) and "")
        dl = jm.start("dev", "download", "download:x", "Herunterladen", lambda j, m: "")
        self.assertTrue(job.log[1].endswith("Bandbreite begrenzt auf 300 Mbit/s"))
        self.assertFalse(any("Bandbreite" in line for line in dl.log))
        # Restzeit: nach einer Änderung zählt nur der Fortschritt seither
        now = time.monotonic()
        job.t0, job.fraction = now - 100, 0.5                                # 50 % in 100 s → noch 100 s
        self.assertAlmostEqual(job.remaining, 100, delta=2)
        with mock.patch.object(jobs.time, "monotonic", return_value=now):
            jm.rebase()
        job.fraction = 0.6                                                   # dann 10 % in 40 s → noch 160 s
        with mock.patch.object(jobs.time, "monotonic", return_value=now + 40):
            self.assertAlmostEqual(job.remaining, 160, delta=1)
        gate.set()


class DemoAgentTest(unittest.TestCase):
    """Ende-zu-Ende: Disk-Image vom Demo-Agent und Zurückspielen mit kleiner Grenze."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.key = bytes(range(32))
        (self.d / "agent.key").write_text(self.key.hex() + "\n")
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.udp.settimeout(10)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "okula_recovery.demo_agent", "--key-file", str(self.d / "agent.key"),
             "--port", str(self.udp.getsockname()[1]), "--control-port", str(self.port), "--duration", "0.5"],
            env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.udp.recvfrom(discovery.MAX_PACKET + 1)
        self.old = wire.get_limiter()

    def tearDown(self):
        wire.set_limiter(self.old)
        self.proc.terminate()
        self.proc.wait(5)
        self.udp.close()
        self.tmp.cleanup()

    def test_image_and_restore_limited(self):
        limit = 24 * MBIT                                                    # 3 MB/s
        lim = Recorder(lambda: limit)
        wire.set_limiter(lim)
        t = time.monotonic()
        image = agentclient.create_image("127.0.0.1", self.key, demo_agent.DEMO_DISK_PATH, self.d / "nas", "DEMO-PC",
                                         lambda e: None, threading.Event(), port=self.port)
        took = time.monotonic() - t
        data = sum(p.stat().st_size for p in Path(image).iterdir() if ".pcl." in p.name)
        self.assertGreater(data, 5_000_000)
        self.assertGreater(took, data * 8 / limit * 0.9)                     # ohne Grenze: ~0.5 s
        self.assertLess(abs(lim.rate_bits() - limit) / limit, 0.10)
        self.assertEqual(agentclient.verify_image(image, agentclient.load_image(image), lambda e: None,
                                                  threading.Event()), None)
        # Zurückspielen: das Tool sendet, die Grenze gilt genauso
        lim.events.clear()
        agentclient.restore_image("127.0.0.1", self.key, image, demo_agent.DEMO_DISK_PATH, lambda e: None,
                                  threading.Event(), self.port)
        self.assertLess(abs(lim.rate_bits() - limit) / limit, 0.10)


if __name__ == "__main__":
    unittest.main()
