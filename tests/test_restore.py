"""Ende-zu-Ende: Image einer Loop-Disk erstellen und auf eine grössere Loop-Disk zurückspielen.

Braucht root, Loop-Devices, sfdisk, partx, partclone, zstd, mkfs.ext4, mkswap – sonst übersprungen.
"""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, imaging, wire

TOOLS = ("losetup", "sfdisk", "partx", "partclone.extfs", "partclone.dd", "zstd", "mkfs.ext4", "mkswap",
         "wipefs", "blkid")
SWAP_UUID = "0b5e6c1a-1111-4222-8333-444455556666"


def can_run() -> bool:
    if os.geteuid() != 0 or not all(shutil.which(t) for t in TOOLS):
        return False
    with tempfile.NamedTemporaryFile() as f:
        f.truncate(1024 * 1024)
        r = subprocess.run(["losetup", "-f", "--show", f.name], capture_output=True, text=True)
        if r.returncode != 0:
            return False
        subprocess.run(["losetup", "-d", r.stdout.strip()])
    return True


def sh(*cmd, input=None):
    return subprocess.run(cmd, input=input, capture_output=True, text=True, check=True).stdout


def sha(path, length=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        remaining = length
        while chunk := f.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining)):
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0:
                    break
    return h.hexdigest()


def loop_disks(*devices):
    out = subprocess.run(["lsblk", "-J", "-b", "-o", imaging.LSBLK_COLUMNS, *devices],
                         capture_output=True, text=True).stdout
    return imaging.parse_disks(out, types=("loop",), skip=())


@unittest.skipUnless(can_run(), "braucht root und Loop-Devices")
class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.loops = []
        self.key = bytes(range(32))

    def tearDown(self):
        for dev in self.loops:
            subprocess.run(["losetup", "-d", dev], capture_output=True)
        self.tmp.cleanup()

    def loop(self, name, size_mb):
        path = self.dir / name
        with open(path, "wb") as f:
            f.truncate(size_mb * 1024 * 1024)
        dev = sh("losetup", "-fP", "--show", str(path)).strip()
        self.loops.append(dev)
        return dev

    def build_source(self, label):
        dev = self.loop("src.img", 96)
        sh("sfdisk", "-q", dev, input=f"label: {label}\nstart=2048, size=40M\nstart=, size=8M\nstart=, size=16M\n")
        sh("partx", "-u", dev)
        imaging._wait_for([f"{dev}p1", f"{dev}p2", f"{dev}p3"])
        content = self.dir / "content"
        (content / "docs").mkdir(parents=True)
        (content / "docs/offerte.txt").write_text("Offerte Okula " * 2000)
        (content / "foto.bin").write_bytes(os.urandom(3_000_000))
        sh("mkfs.ext4", "-q", "-F", "-d", str(content), f"{dev}p1")
        with open(f"{dev}p2", "r+b") as f:
            f.write(os.urandom(8 * 1024 * 1024))
        sh("mkswap", "-q", "-U", SWAP_UUID, "-L", "SWAP", f"{dev}p3")
        with open(dev, "r+b") as f:
            f.write(b"\xebBOOTCODE-OKULA".ljust(440, b"\x90"))
            f.seek(100 * 512)
            f.write(b"GRUB-CORE-IMG-OKULA" * 10)
        return dev

    def serve(self):
        server = socket.create_server(("127.0.0.1", 0))
        ctx = wire.server_context(self.key)

        def run():
            while True:
                try:
                    conn, addr = server.accept()
                except OSError:
                    return
                threading.Thread(target=agent.handle_connection, args=(ctx, conn, addr), daemon=True).start()

        threading.Thread(target=run, daemon=True).start()
        self.addCleanup(server.close)
        return server.getsockname()[1]

    def roundtrip(self, label):
        src = self.build_source(label)
        dst = self.loop("dst.img", 128)  # grössere Zieldisk
        port = self.serve()
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(src, dst)), \
                mock.patch.object(agent, "log", lambda m: None):
            image = agentclient.create_image("127.0.0.1", self.key, src, self.dir / "nas", "test",
                                             lambda e: None, threading.Event(), port=port)
            events = []
            agentclient.restore_image("127.0.0.1", self.key, image, dst, events.append, threading.Event(),
                                      port=port, verify=True)
        self.assertEqual(events[-1]["phase"], "done")
        self.assertIn("verify", [e["phase"] for e in events])

        # Tabelle: gleiche Partitionen
        src_parts = [ln.split(":", 1)[1].strip() for ln in sh("sfdisk", "-d", src).splitlines()
                     if ln.startswith("/dev/")]
        dst_parts = [ln.split(":", 1)[1].strip() for ln in sh("sfdisk", "-d", dst).splitlines()
                     if ln.startswith("/dev/")]
        strip = lambda parts: [",".join(x for x in p.split(",") if "uuid" not in x) for p in parts]  # noqa: E731
        self.assertEqual(strip(dst_parts) if label == "dos" else dst_parts, strip(src_parts)
                         if label == "dos" else src_parts)
        # Inhalte
        self.assertEqual(sha(f"{dst}p1"), sha(f"{src}p1"), "ext4 nicht bitgleich")
        self.assertEqual(sha(f"{dst}p2"), sha(f"{src}p2"), "Rohpartition nicht bitgleich")
        self.assertEqual(sh("blkid", "-s", "UUID", "-o", "value", f"{dst}p3").strip(), SWAP_UUID)
        with open(dst, "rb") as f:
            self.assertEqual(f.read(440), b"\xebBOOTCODE-OKULA".ljust(440, b"\x90"))
            f.seek(100 * 512)
            self.assertEqual(f.read(190), b"GRUB-CORE-IMG-OKULA" * 10)
        if label == "gpt":
            sh("sfdisk", "--verify", dst)  # Backup-GPT am Ende der grösseren Disk korrekt

    def test_gpt(self):
        self.roundtrip("gpt")

    def test_dos(self):
        self.roundtrip("dos")

    def test_refuses_smaller_target(self):
        src = self.build_source("gpt")
        small = self.loop("small.img", 64)
        port = self.serve()
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(src, small)), \
                mock.patch.object(agent, "log", lambda m: None):
            image = agentclient.create_image("127.0.0.1", self.key, src, self.dir / "nas", "t",
                                             lambda e: None, threading.Event(), port=port)
            before = sha(small)
            with self.assertRaisesRegex(agentclient.AgentError, "zu klein"):
                agentclient.restore_image("127.0.0.1", self.key, image, small, lambda e: None,
                                          threading.Event(), port=port)
        self.assertEqual(sha(small), before, "Zieldisk wurde trotz Ablehnung verändert")

    def test_corrupt_image_detected_before_writing(self):
        src = self.build_source("gpt")
        dst = self.loop("dst.img", 128)
        port = self.serve()
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(src, dst)), \
                mock.patch.object(agent, "log", lambda m: None):
            image = agentclient.create_image("127.0.0.1", self.key, src, self.dir / "nas", "t",
                                             lambda e: None, threading.Event(), port=port)
            victim = next(image.glob("*p1.*"))
            data = bytearray(victim.read_bytes())
            data[len(data) // 2] ^= 0xFF
            victim.write_bytes(bytes(data))
            before = sha(dst)
            with self.assertRaisesRegex(agentclient.AgentError, "beschädigt"):
                agentclient.restore_image("127.0.0.1", self.key, image, dst, lambda e: None,
                                          threading.Event(), port=port)
        self.assertEqual(sha(dst), before)


if __name__ == "__main__":
    unittest.main()
