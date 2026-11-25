import hashlib
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, imaging, systools, wire
from okula_recovery.systools import find_tool, resolve

LSBLK = json.dumps({"blockdevices": [
    {"name": "sda", "path": "/dev/sda", "size": 512110190592, "type": "disk", "fstype": None, "model": "SSD 860 ",
     "serial": "S3Z", "tran": "sata", "pttype": "gpt", "mountpoints": [None], "children": [
         {"name": "sda1", "path": "/dev/sda1", "size": 104857600, "type": "part", "fstype": "vfat", "label": "EFI",
          "uuid": "AAAA-BBBB", "parttype": "c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "mountpoints": [None]},
         {"name": "sda2", "path": "/dev/sda2", "size": 16777216, "type": "part", "fstype": None,
          "mountpoints": [None]},
         {"name": "sda3", "path": "/dev/sda3", "size": 500000000000, "type": "part", "fstype": "ntfs",
          "label": "Windows", "mountpoints": [None]},
         {"name": "sda4", "path": "/dev/sda4", "size": 8000000000, "type": "part", "fstype": "swap",
          "uuid": "1234", "mountpoints": [None]}]},
    {"name": "sdb", "path": "/dev/sdb", "size": 16008609792, "type": "disk", "tran": "usb", "mountpoints": [None],
     "children": [{"name": "sdb1", "path": "/dev/sdb1", "type": "part", "fstype": "vfat",
                   "mountpoints": ["/run/live/medium"]}]},
    {"name": "loop0", "path": "/dev/loop0", "size": 1, "type": "loop", "mountpoints": ["/run/live/rootfs/x"]},
]})


class PlanTest(unittest.TestCase):
    def test_parse_disks_skips_boot_stick_and_loops(self):
        disks = imaging.parse_disks(LSBLK)
        self.assertEqual([d["path"] for d in disks], ["/dev/sda"])
        self.assertEqual([p["fstype"] for p in disks[0]["partitions"]], ["vfat", "", "ntfs", "swap"])
        self.assertEqual(disks[0]["model"], "SSD 860")

    def test_plan(self):
        disk = imaging.parse_disks(LSBLK)[0]
        with mock.patch.object(imaging, "find_tool", lambda name: f"/usr/sbin/{name}"):
            plan = imaging.make_plan(disk, compress=True)
        files = [s["file"] for s in plan]
        self.assertEqual(files, ["sda.sfdisk", "sda-head.img", "sda-tail.img",
                                 "sda1.vfat.pcl.zst", "sda2.dd.img.zst", "sda3.ntfs.pcl.zst", None])
        self.assertEqual(plan[5]["cmds"][0], ["partclone.ntfs", "-c", "-s", "/dev/sda3", "-o", "-"])
        self.assertEqual(plan[4]["cmds"][0][0], "partclone.dd")
        self.assertEqual(plan[6]["reason"], "swap")
        self.assertEqual(plan[2]["offset"], disk["size"] - imaging.HEAD_TAIL)

    def test_plan_requires_partclone(self):
        disk = imaging.parse_disks(LSBLK)[0]
        with mock.patch.object(imaging, "find_tool", lambda name: None):
            with self.assertRaises(imaging.ImagingError):
                imaging.make_plan(disk, compress=False)

    def test_plan_refuses_mounted(self):
        disk = imaging.parse_disks(LSBLK)[0]
        disk["partitions"][2]["mounted"] = True
        with mock.patch.object(imaging, "find_tool", lambda name: name):
            with self.assertRaises(imaging.ImagingError):
                imaging.make_plan(disk, compress=False)


class FindToolTest(unittest.TestCase):
    """B-009: Werkzeuge in sbin-Ordnern auch ohne sbin im PATH finden (normaler Benutzer)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.sbin, self.bin = root / "sbin", root / "bin"
        self.sbin.mkdir()
        self.bin.mkdir()
        self.tool = self.sbin / "okula-testtool"
        self.tool.write_text("#!/bin/sh\necho gefunden\n")
        self.tool.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def test_found_in_sbin_without_path(self):
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}), \
                mock.patch.object(systools, "SBIN_DIRS", (str(self.sbin),)):
            self.assertEqual(find_tool("okula-testtool"), str(self.tool))
            argv = resolve(["okula-testtool", "-x"])
            self.assertEqual(argv, [str(self.tool), "-x"])
            self.assertEqual(subprocess.run(argv[:1], capture_output=True, text=True).stdout, "gefunden\n")
            self.assertIsNone(find_tool("gibt-es-nicht"))
            self.assertEqual(resolve(["gibt-es-nicht", "-x"]), ["gibt-es-nicht", "-x"])

    def test_path_comes_first(self):
        first = self.bin / "okula-testtool"
        first.write_text("#!/bin/sh\n")
        first.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}), \
                mock.patch.object(systools, "SBIN_DIRS", (str(self.sbin),)):
            self.assertEqual(find_tool("okula-testtool"), str(first))

    def test_imaging_uses_search(self):
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}), \
                mock.patch.object(systools, "SBIN_DIRS", (str(self.sbin),)):
            for name in ("partclone.dd", "zstd", "sfdisk"):
                (self.sbin / name).write_text("#!/bin/sh\n")
                (self.sbin / name).chmod(0o755)
            self.assertEqual(imaging.tool_status(), {"partclone": True, "zstd": True, "sfdisk": True})


class EndToEndTest(unittest.TestCase):
    """Agent-Steuerdienst und Tool über echtes TLS-PSK; Partitionen sind Dateien, partclone = cat."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.disk_file = root / "disk.bin"
        self.disk_file.write_bytes(bytes(range(256)) * 16384)  # 4 MiB
        self.part1 = root / "p1.bin"
        self.part1.write_bytes(b"A" * 3_000_000)
        self.part2 = root / "p2.bin"
        self.part2.write_bytes(b"B" * 10)
        self.nas = root / "nas"
        self.nas.mkdir()
        self.key = bytes(range(32))
        self.disk = {"name": "sda", "path": str(self.disk_file), "size": self.disk_file.stat().st_size,
                     "model": "Test", "serial": "1", "transport": "sata", "pttype": "gpt", "fstype": "",
                     "partitions": [
                         {"name": "sda1", "path": str(self.part1), "size": 3_000_000, "fstype": "ntfs",
                          "label": "", "uuid": "", "parttype": "", "mounted": False},
                         {"name": "sda2", "path": str(self.part2), "size": 10, "fstype": "", "label": "",
                          "uuid": "", "parttype": "", "mounted": False},
                         {"name": "sda3", "path": "/nope", "size": 1, "fstype": "swap", "label": "",
                          "uuid": "u", "parttype": "", "mounted": False}]}
        self.patches = [
            mock.patch.object(imaging, "list_disks", lambda: [self.disk]),
            mock.patch.object(imaging, "find_tool", lambda name: None if name == "zstd" else name),
            mock.patch.object(imaging, "partition_command",
                              lambda p: None if p["fstype"] == "swap" else ("dd.img", ["cat", p["path"]])),
            mock.patch.object(agent, "log", lambda *a, **k: None),
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

    def image(self, key=None, **kw):
        events = []
        path = agentclient.create_image("127.0.0.1", key or self.key, str(self.disk_file), self.nas, "PC Büro/1",
                                        events.append, threading.Event(), port=self.port, **kw)
        return path, events

    def test_info(self):
        info = agentclient.get_info("127.0.0.1", self.key, self.port)
        self.assertEqual(info["disks"][0]["name"], "sda")

    def test_full_image(self):
        path, events = self.image()
        self.assertEqual(path.parent, self.nas / "images" / "PC_B_ro_1")
        self.assertFalse(path.name.endswith(".partial"))
        self.assertEqual(sorted(p.name for p in path.iterdir()),
                         sorted(["okula-image.json", "sda-head.img", "sda-tail.img", "sda1.dd.img", "sda2.dd.img"]
                                + (["sda.sfdisk"] if (path / "sda.sfdisk").exists() else [])))
        self.assertEqual((path / "sda1.dd.img").read_bytes(), self.part1.read_bytes())
        self.assertEqual((path / "sda-head.img").read_bytes(), self.disk_file.read_bytes()[:1024 * 1024])
        self.assertEqual((path / "sda-tail.img").read_bytes(), self.disk_file.read_bytes()[-1024 * 1024:])
        meta = json.loads((path / "okula-image.json").read_text())
        self.assertEqual(meta["machine"], "PC Büro/1")
        by_name = {f["name"]: f for f in meta["files"]}
        self.assertEqual(by_name["sda1.dd.img"]["sha256"], hashlib.sha256(self.part1.read_bytes()).hexdigest())
        self.assertEqual(events[-1]["phase"], "done")
        phases = [e["phase"] for e in events]
        self.assertEqual(phases.count("file"), 5 if (path / "sda.sfdisk").exists() else 4)
        self.assertTrue(all(e.get("file") for e in events if e["phase"] == "file"))
        self.assertTrue(any(s.get("reason") == "swap" for s in meta["plan"]))

    def test_wrong_key(self):
        with self.assertRaisesRegex(agentclient.AgentError, "Schlüssel"):
            self.image(key=b"x" * 32)

    def test_failure_leaves_no_partial(self):
        self.disk["partitions"][1]["path"] = "/does/not/exist"
        with self.assertRaisesRegex(agentclient.AgentError, "fehlgeschlagen"):
            self.image()
        self.assertEqual(list((self.nas / "images").rglob("*")), [(self.nas / "images" / "PC_B_ro_1")])

    def test_cancel(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(agentclient.AgentError, "Abgebrochen"):
            agentclient.create_image("127.0.0.1", self.key, str(self.disk_file), self.nas, "x",
                                     lambda e: None, cancel, port=self.port)
        self.assertEqual(list((self.nas / "images" / "x").iterdir()), [])


def partclone_log_writable() -> bool:
    """partclone schreibt sein Log fest nach /var/log/partclone.log – als normaler Benutzer meist nicht erlaubt."""
    log = Path("/var/log/partclone.log")
    return os.access(log, os.W_OK) if log.exists() else os.access(log.parent, os.W_OK)


@unittest.skipUnless(find_tool("partclone.extfs") and find_tool("zstd") and find_tool("mkfs.ext4"),
                     "partclone/zstd/mkfs.ext4 fehlen")
@unittest.skipUnless(partclone_log_writable(), "/var/log/partclone.log nicht beschreibbar (Test braucht root)")
class RealPartcloneTest(unittest.TestCase):
    """Echte Pipeline partclone.extfs | zstd über TLS, danach Restore und Vergleich."""

    def test_ext4_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            content = root / "content"
            (content / "docs").mkdir(parents=True)
            (content / "docs/rechnung.txt").write_text("Rechnung 2026-10 " * 1000)
            (content / "bild.bin").write_bytes(os.urandom(2_000_000))
            part = root / "sda1.img"
            with open(part, "wb") as f:
                f.truncate(64 * 1024 * 1024)
            subprocess.run(resolve(["mkfs.ext4", "-q", "-F", "-d", str(content), str(part)]), check=True)
            disk = {"name": "sda", "path": str(part), "size": part.stat().st_size, "model": "", "serial": "",
                    "transport": "", "pttype": "", "fstype": "",
                    "partitions": [{"name": "sda1", "path": str(part), "size": part.stat().st_size,
                                    "fstype": "ext4", "label": "", "uuid": "", "parttype": "", "mounted": False}]}
            key = bytes(range(32))
            server = socket.create_server(("127.0.0.1", 0))
            ctx = wire.server_context(key)

            def serve():
                conn, addr = server.accept()
                agent.handle_connection(ctx, conn, addr)

            with mock.patch.object(imaging, "list_disks", lambda: [disk]), mock.patch.object(agent, "log", lambda *a, **k: None):
                threading.Thread(target=serve, daemon=True).start()
                nas = root / "nas"
                path = agentclient.create_image("127.0.0.1", key, str(part), nas, "test", lambda e: None,
                                                threading.Event(), port=server.getsockname()[1])
            server.close()
            image = path / "sda1.ext4.pcl.zst"
            self.assertTrue(image.is_file())
            self.assertLess(image.stat().st_size, part.stat().st_size / 4)  # nur belegte Blöcke, komprimiert

            # Restore in eine leere Datei gleicher Grösse → muss bitgleich sein
            restored = root / "restored.img"
            with open(restored, "wb") as f:
                f.truncate(part.stat().st_size)
            zstd = subprocess.Popen(resolve(["zstd", "-d", "-c", str(image)]), stdout=subprocess.PIPE)
            r = subprocess.run(resolve(["partclone.extfs", "-r", "-s", "-", "-O", str(restored), "-q"]),
                               stdin=zstd.stdout, capture_output=True)
            zstd.stdout.close()
            zstd.wait()
            self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace")[-500:])
            self.assertEqual(hashlib.sha256(restored.read_bytes()).hexdigest(),
                             hashlib.sha256(part.read_bytes()).hexdigest())


class ConsoleAndPowerTest(EndToEndTest):
    def test_console_bar_render(self):
        r = agent.ConsoleBar.render
        self.assertEqual(r(0.47, "sda3", 47_000_000_000, 600),
                         "  [==============>               ]  47 %  sda3  78 MB/s  noch ca. 11 min")
        self.assertNotIn("noch", r(1.0, "sda3", 1, 100))
        self.assertTrue(r(2.0, "x", 0, 0).startswith("  [" + "=" * 30 + "] 100 %"))
        self.assertEqual(agent.format_eta(3 * 3600 + 5 * 60), "3 h 05 min")

    def test_image_shows_progress_on_console(self):
        with tempfile.NamedTemporaryFile("r") as tty, mock.patch.object(agent, "console", tty.name):
            self.image()
            text = Path(tty.name).read_text()
        self.assertIn("Disk-Image von", text)
        self.assertIn("» Disk-Image auf", text)
        self.assertIn("fertig", text)

    def test_power_off(self):
        calls = []
        with mock.patch.object(agent, "power_action", calls.append):
            agentclient.power("127.0.0.1", self.key, "poweroff", self.port, delay=0)
            deadline = time.monotonic() + 3
            while not calls and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual(calls, ["poweroff"])

    def test_power_refused_while_busy_or_unknown(self):
        with mock.patch.object(agent, "power_action", lambda a: self.fail("darf nicht ausschalten")):
            self.assertTrue(agent.disk_locks.acquire("/dev/sdz", "image"))
            try:
                with self.assertRaisesRegex(agentclient.AgentError, "beschäftigt"):
                    agentclient.power("127.0.0.1", self.key, "poweroff", self.port, delay=0)
            finally:
                agent.disk_locks.release("/dev/sdz")
            with self.assertRaisesRegex(agentclient.AgentError, "Unbekannte Aktion"):
                agentclient.power("127.0.0.1", self.key, "halt; rm -rf /", self.port, delay=0)

    # Basistests nicht doppelt
    test_info = test_full_image = test_wrong_key = test_failure_leaves_no_partial = test_cancel = None


class MaliciousAgentTest(unittest.TestCase):
    def test_rejects_path_traversal(self):
        key = bytes(32)
        server = socket.create_server(("127.0.0.1", 0))
        port = server.getsockname()[1]

        def fake_agent():
            conn, _ = server.accept()
            with wire.server_context(key).wrap_socket(conn, server_side=True) as tls:
                wire.recv_json(tls)
                wire.send_json(tls, {"type": "begin", "disk": {}, "plan": []})
                wire.send_json(tls, {"type": "file", "file": "../../etc/evil"})
                try:
                    tls.recv(1)
                except OSError:
                    pass

        threading.Thread(target=fake_agent, daemon=True).start()
        with tempfile.TemporaryDirectory() as nas:
            with self.assertRaisesRegex(agentclient.AgentError, "Ungültiger Dateiname"):
                agentclient.create_image("127.0.0.1", key, "/dev/sda", nas, "m", lambda e: None,
                                         threading.Event(), port=port)
            self.assertFalse((Path(nas).parent / "etc" / "evil").exists())
        server.close()


class FakeAgent:
    """Agent-Attrappe über echtes TLS-PSK: beantwortet eine Verbindung mit festen Frames (dict = JSON, bytes = Daten)."""

    def __init__(self, frames, linger: float = 5.0, close_after: float | None = None):
        self.key = bytes(32)
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.request = None
        threading.Thread(target=self._serve, args=(frames, linger, close_after), daemon=True).start()

    def _serve(self, frames, linger, close_after):
        try:
            conn, _ = self.server.accept()
        except OSError:
            return
        with wire.server_context(self.key).wrap_socket(conn, server_side=True) as tls:
            self.request = wire.recv_json(tls)
            for f in frames:
                if isinstance(f, bytes):
                    wire.send_data(tls, f)
                else:
                    wire.send_json(tls, f)
            if close_after is not None:
                time.sleep(close_after)
                return
            tls.settimeout(linger)
            try:
                tls.recv(1)
            except OSError:
                pass

    def close(self):
        self.server.close()


def file_frames(name: str, data: bytes, end: bool = True) -> list:
    frames = [{"type": "file", "file": name}, data]
    if end:
        frames.append({"type": "file_end", "file": name, "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()})
    return frames


PLAN = [{"file": "sda.sfdisk", "kind": "command", "optional": True},
        {"file": "sda-head.img", "kind": "range"},
        {"file": "sda1.dd.img", "kind": "pipe", "part": "sda1"},
        {"file": None, "kind": "skip", "part": "sda2", "reason": "swap"}]
BEGIN = {"type": "begin", "disk": {"name": "sda"}, "plan": PLAN}


class ImageCompleteTest(unittest.TestCase):
    """B-027: Ein Image gilt nur als fertig, wenn alle Dateien des Plans vollständig angekommen sind."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.nas = Path(self.tmp.name) / "nas"

    def tearDown(self):
        self.tmp.cleanup()

    def run_agent(self, frames):
        fake = FakeAgent(frames)
        try:
            return agentclient.create_image("127.0.0.1", fake.key, "/dev/sda", self.nas, "PC", lambda e: None,
                                            threading.Event(), port=fake.port)
        finally:
            fake.close()

    def assert_nothing_left(self):
        self.assertEqual([p.name for p in (self.nas / "images" / "PC").iterdir()], [])

    def test_complete_image(self):
        path = self.run_agent([BEGIN, *file_frames("sda-head.img", b"H" * 100),
                               *file_frames("sda1.dd.img", b"D" * 5000), {"type": "end"}])
        self.assertFalse(path.name.endswith(".partial"))
        self.assertEqual(sorted(p.name for p in path.iterdir()), ["okula-image.json", "sda-head.img", "sda1.dd.img"])
        meta = agentclient.load_image(path)
        self.assertEqual([f["name"] for f in meta["files"]], ["sda-head.img", "sda1.dd.img"])

    def test_end_with_open_file(self):
        with self.assertRaisesRegex(agentclient.AgentError, "Image unvollständig: Ende von sda1.dd.img fehlt"):
            self.run_agent([BEGIN, *file_frames("sda-head.img", b"H"),
                            *file_frames("sda1.dd.img", b"D" * 10, end=False), {"type": "end"}])
        self.assert_nothing_left()

    def test_end_without_begin(self):
        with self.assertRaisesRegex(agentclient.AgentError, "Image unvollständig: Beginn"):
            self.run_agent([{"type": "end"}])
        self.assert_nothing_left()

    def test_end_with_missing_plan_file(self):
        with self.assertRaisesRegex(agentclient.AgentError, "Image unvollständig: sda1.dd.img fehlt"):
            self.run_agent([BEGIN, *file_frames("sda-head.img", b"H"), {"type": "end"}])
        self.assert_nothing_left()

    def test_second_file_while_first_open(self):
        with self.assertRaisesRegex(agentclient.AgentError, "bevor sda-head.img fertig"):
            self.run_agent([BEGIN, *file_frames("sda-head.img", b"H", end=False),
                            *file_frames("sda1.dd.img", b"D")])
        self.assert_nothing_left()

    def test_folder_collision_and_partial_rest(self):
        base = self.nas / "images" / "PC" / "2026-11-25_1000_sda"
        base.mkdir(parents=True)
        rest = base.with_name(base.name + "-2.partial")
        rest.mkdir()
        (rest / "sda-head.img").write_bytes(b"alt")
        frames = [BEGIN, *file_frames("sda-head.img", b"H"), *file_frames("sda1.dd.img", b"D"), {"type": "end"}]
        with mock.patch.object(agentclient, "image_dir", lambda *a, **k: base):
            path = self.run_agent(frames)
        self.assertEqual(path.name, "2026-11-25_1000_sda-3")
        self.assertEqual((rest / "sda-head.img").read_bytes(), b"alt")    # Rest bleibt unangetastet
        self.assertEqual(sorted(p.name for p in base.parent.iterdir()),
                         ["2026-11-25_1000_sda", "2026-11-25_1000_sda-2.partial", "2026-11-25_1000_sda-3"])

    def test_new_image_dir_names(self):
        base = self.nas / "x" / "img"
        final, work = agentclient._new_image_dir(base)
        self.assertEqual((final, work.name), (base, "img.partial"))
        final2, work2 = agentclient._new_image_dir(base)          # img.partial ist noch da
        self.assertEqual((final2.name, work2.name), ("img-2", "img-2.partial"))

    def test_unreachable_agent_leaves_no_partial(self):
        server = socket.create_server(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.close()
        with self.assertRaisesRegex(agentclient.AgentError, "nicht erreichbar"):
            agentclient.create_image("127.0.0.1", bytes(32), "/dev/sda", self.nas, "PC", lambda e: None,
                                     threading.Event(), port=port)
        self.assert_nothing_left()


class CountdownTest(unittest.TestCase):
    """B-027: Verbindungsverlust im Countdown heisst „abgebrochen“, nie „start“."""

    def test_connection_lost_after_accept(self):
        fake = FakeAgent([], close_after=0.3)
        try:
            with self.assertRaisesRegex(agentclient.AgentError, "abgebrochen – nicht gestartet"):
                agentclient.countdown("127.0.0.1", fake.key, 1, "Test", threading.Event(), port=fake.port)
        finally:
            fake.close()
        self.assertEqual(fake.request["cmd"], "countdown")

    def test_result_from_agent(self):
        fake = FakeAgent([{"type": "countdown", "result": "esc"}])
        try:
            self.assertEqual(agentclient.countdown("127.0.0.1", fake.key, 5, "Test", threading.Event(),
                                                   port=fake.port), "esc")
        finally:
            fake.close()

    def test_old_agent_counts_in_tool(self):
        fake = FakeAgent([{"type": "error", "message": "Unbekannter Befehl: countdown"}])
        ticks = []
        try:
            self.assertEqual(agentclient.countdown("127.0.0.1", fake.key, 1, "Test", threading.Event(),
                                                   ticks.append, port=fake.port), "start")
        finally:
            fake.close()
        self.assertEqual(ticks[0], 1)

    def test_other_error_is_no_start(self):
        fake = FakeAgent([{"type": "error", "message": "beschäftigt"}])
        try:
            with self.assertRaisesRegex(agentclient.AgentError, "abgelehnt: beschäftigt"):
                agentclient.countdown("127.0.0.1", fake.key, 1, "Test", threading.Event(), port=fake.port)
        finally:
            fake.close()

    def test_unreachable_is_no_start(self):
        server = socket.create_server(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.close()
        with self.assertRaisesRegex(agentclient.AgentError, "nicht erreichbar"):
            agentclient.countdown("127.0.0.1", bytes(32), 1, "Test", threading.Event(), port=port)


class KeyTest(unittest.TestCase):
    def test_key_created_once_with_0600(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": d}):
            k1 = agentclient.load_or_create_key()
            k2 = agentclient.load_or_create_key()
            self.assertEqual(k1, k2)
            self.assertEqual(len(k1), 32)
            self.assertEqual(agentclient.key_path().stat().st_mode & 0o777, 0o600)
            self.assertEqual([p.name for p in agentclient.key_path().parent.iterdir()], ["agent.key"])  # kein .tmp

    def test_broken_key_file_is_not_replaced(self):
        """B-027: leere oder kaputte Schlüsseldatei → Fehler mit Pfad, Datei bleibt unverändert."""
        for content in ("", "kaputt\n", "abcd\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as d, \
                    mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": d}):
                path = agentclient.key_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                with self.assertRaises(agentclient.AgentError) as cm:
                    agentclient.load_or_create_key()
                self.assertIn(str(path), str(cm.exception))
                self.assertIn("ungültig", str(cm.exception))
                self.assertEqual(path.read_text(), content)


if __name__ == "__main__":
    unittest.main()
