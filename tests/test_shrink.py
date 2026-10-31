"""Ä-002: Image für eine kleinere Disk anpassen – Bausteine und Ende-zu-Ende über den Agent auf Loop-Disks."""

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

from okula_recovery import agent, agentclient, automation, devices, imaging, jobs, shrink, wire
from tests.test_restore import can_run, loop_disks, sh

MB = 1024 * 1024
DUMP = """label: gpt
label-id: 11111111-2222-3333-4444-555555555555
device: /dev/sda
unit: sectors
first-lba: 34
last-lba: 1048542
sector-size: 512

/dev/sda1 : start=2048, size=65536, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, uuid=A1, name="EFI system partition"
/dev/sda2 : start=67584, size=32768, type=E3C9E316-0B5C-4C58-A10A-04EB08E6C5D4, uuid=A2, name="Microsoft reserved"
/dev/sda3 : start=100352, size=819200, type=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7, uuid=A3, name="Basic data"
/dev/sda4 : start=919552, size=122880, type=DE94BBA4-06D1-4D40-A16A-BFD50179D6AC, uuid=A4, name="Recovery", attrs="RequiredPartition GUID:63"
"""


class UnitTest(unittest.TestCase):
    def test_sfdisk_roundtrip(self):
        header, parts = shrink.parse_sfdisk(DUMP)
        self.assertEqual([p.number for p in parts], [1, 2, 3, 4])
        self.assertEqual((parts[2].start, parts[2].size), (100352, 819200))
        self.assertEqual(parts[3].fields["attrs"], '"RequiredPartition GUID:63"')
        out = shrink.build_sfdisk(header, parts, 524254)
        self.assertIn("last-lba: 524254", out)
        self.assertIn('name="Recovery", attrs="RequiredPartition GUID:63"', out)
        self.assertNotIn("1048542", out)
        self.assertEqual(shrink.parse_sfdisk(out)[1][3].line(), parts[3].line())

    def test_pcl_header(self):
        head = bytearray(b"partclone-image\0" + b"0.3.27".ljust(14, b"\0") + b"0002" + b"\xde\xc0" +
                         b"NTFS".ljust(16, b"\0"))
        head += (314572800).to_bytes(8, "little") + (76800).to_bytes(8, "little") + (21786).to_bytes(8, "little")
        head += (21786).to_bytes(8, "little") + (4096).to_bytes(4, "little")
        info = shrink.parse_pcl_header(bytes(head))
        self.assertEqual((info["fs"], info["device_size"], info["used"]), ("NTFS", 314572800, 21786 * 4096))
        with self.assertRaises(shrink.ShrinkError):
            shrink.parse_pcl_header(b"kein image")

    def test_reserve_and_tmp(self):
        self.assertEqual(shrink.reserve_for(100), 1024**3)
        self.assertEqual(shrink.reserve_for(100 * 1024**3), 10 * 1024**3)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(shrink, "LOCAL_TMP", Path(tmp) / "lokal"), \
                mock.patch.object(shrink.shutil, "disk_usage",
                                  lambda p: shutil._ntuple_diskusage(0, 0, 10**9 if "lokal" in str(p) else 10**12)):
            self.assertEqual(shrink.choose_tmp(5 * 10**9, tmp), Path(tmp) / shrink.NAS_TMP)    # Server zu klein → NAS
            with self.assertRaisesRegex(shrink.ShrinkError, "Zu wenig Platz"):
                shrink.choose_tmp(5 * 10**12, tmp)


def settle(*devices) -> None:
    """lsblk kennt neue Dateisysteme erst, wenn udev sie gesehen hat (sonst sichert der Agent eine Rohkopie)."""
    for dev in devices:
        subprocess.run(["udevadm", "trigger", "--action=change", dev], capture_output=True)
    subprocess.run(["udevadm", "settle"], capture_output=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(can_run() and all(map(shutil.which, ("mkfs.ntfs", "ntfs-3g", "partclone.ntfs", "ntfsresize",
                                                          "resize2fs", "mkfs.vfat"))),
                     "braucht root, Loop-Devices, ntfs-3g, partclone")
class ShrinkE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.loops = []
        self.key = bytes(range(32))
        self.nas = self.d / "nas"
        self.patches = [mock.patch.object(agent, "log", lambda *a, **k: None),
                        mock.patch.object(shrink, "LOCAL_TMP", self.d / "tmp"),
                        mock.patch.object(shrink, "reserve_for", lambda used: used // 10 + 2 * MB)]
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
            f.truncate(size_mb * MB)
        dev = sh("losetup", "-fP", "--show", str(path)).strip()
        self.loops.append(dev)
        return dev

    def roundtrip(self, src, target_mb):
        dst = self.loop("dst.img", target_mb)
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(src, dst)):
            image = agentclient.create_image("127.0.0.1", self.key, src, self.nas, "PC-512", lambda e: None,
                                             threading.Event(), port=self.port)
            target_size = int(sh("blockdev", "--getsize64", dst))
            with self.assertRaisesRegex(agentclient.AgentError, "zu klein"):
                agentclient.restore_image("127.0.0.1", self.key, image, dst, lambda e: None, threading.Event(),
                                          self.port, verify=False)
            plan = shrink.plan(image, target_size)
            events = []
            derived = shrink.create(plan, self.nas, events.append)
            self.assertTrue(any(e.get("phase") == "shrink" for e in events))
            self.assertEqual(shrink.ensure(image, target_size, self.nas), derived)      # wird wiederverwendet
            agentclient.restore_image("127.0.0.1", self.key, derived, dst, lambda e: None, threading.Event(),
                                      self.port)
        self.assertTrue((image / agentclient.IMAGE_META).is_file())                      # Original unverändert
        meta = json.loads((derived / agentclient.IMAGE_META).read_text())
        self.assertEqual(meta["shrunk"]["part"], plan.part)
        return dst, plan, meta

    def test_gpt_windows_layout(self):
        src = self.loop("src.img", 420)
        sh("sfdisk", "-q", src, input="label: gpt\nstart=2048, size=32M, type=uefi\nsize=16M, "
                                      "type=E3C9E316-0B5C-4C58-A10A-04EB08E6C5D4\nsize=300M, type=linux\n"
                                      "size=60M, type=DE94BBA4-06D1-4D40-A16A-BFD50179D6AC\n")
        sh("partx", "-u", src)
        agent.imaging._wait_for([f"{src}p{i}" for i in (1, 2, 3, 4)])
        sh("mkfs.vfat", f"{src}p1")
        mnt = self.d / "m"
        mnt.mkdir()
        payload = os.urandom(40 * MB)
        for n, files in ((3, {"Windows/System32/config/SYSTEM": b"regf", "Users/Anna/data.bin": payload}),
                         (4, {"Recovery/WindowsRE/winre.wim": b"WIM" * 1000})):
            sh("mkfs.ntfs", "-Q", "-F", f"{src}p{n}")
            sh("ntfs-3g", f"{src}p{n}", str(mnt))
            for rel, data in files.items():
                (mnt / rel).parent.mkdir(parents=True, exist_ok=True)
                (mnt / rel).write_bytes(data)
            sh("umount", str(mnt))
        dst, plan, meta = self.roundtrip(src, 260)
        self.assertEqual(plan.part, Path(f"{src}p3").name)
        self.assertEqual(plan.moved, [Path(f"{src}p4").name])
        self.assertLess(plan.new_size, 300 * MB)
        # Tabelle gültig, Recovery am Ende, Inhalte lesbar
        sh("sfdisk", "--verify", dst)
        parts = json.loads(sh("sfdisk", "-J", dst))["partitiontable"]["partitions"]
        self.assertEqual(len(parts), 4)
        last_end = (parts[3]["start"] + parts[3]["size"]) * 512
        self.assertGreater(last_end, 255 * MB)
        sh("partx", "-u", dst)
        agent.imaging._wait_for([f"{dst}p3", f"{dst}p4"])
        # Struktur in Ordnung (den Ersatz-Bootsektor am Partitionsende überträgt partclone nie – auch ohne
        # Verkleinern; Windows schreibt ihn bei der nächsten Prüfung neu)
        self.assertIn("$MFTMirr completed successfully", subprocess.run(["ntfsfix", "-n", f"{dst}p3"],
                                                                        capture_output=True, text=True).stdout)
        sh("ntfs-3g", f"{dst}p3", str(mnt))   # schreibend einhängbar (Anpassen nach dem Zurückspielen braucht das)
        try:
            self.assertEqual(sha(mnt / "Users/Anna/data.bin"), hashlib.sha256(payload).hexdigest())
        finally:
            sh("umount", str(mnt))
        sh("ntfs-3g", "-o", "ro", f"{dst}p4", str(mnt))
        try:
            self.assertEqual((mnt / "Recovery/WindowsRE/winre.wim").read_bytes(), b"WIM" * 1000)
        finally:
            sh("umount", str(mnt))
        self.assertEqual(sh("blkid", "-o", "value", "-s", "TYPE", f"{dst}p1").strip(), "vfat")

    def test_mbr_ext4_with_swap(self):
        src = self.loop("src.img", 360)
        sh("sfdisk", "-q", src, input="label: dos\nstart=2048, size=300M, type=83\nsize=32M, type=82\n")
        sh("partx", "-u", src)
        agent.imaging._wait_for([f"{src}p1", f"{src}p2"])
        tree = self.d / "tree"
        tree.mkdir()
        payload = os.urandom(30 * MB)
        (tree / "home").mkdir()
        (tree / "home/daten.bin").write_bytes(payload)
        sh("mkfs.ext4", "-q", "-F", "-d", str(tree), f"{src}p1")
        sh("mkswap", f"{src}p2")
        settle(f"{src}p1", f"{src}p2")
        dst, plan, meta = self.roundtrip(src, 200)
        sh("partx", "-u", dst)
        agent.imaging._wait_for([f"{dst}p1", f"{dst}p2"])
        self.assertEqual(subprocess.run(["e2fsck", "-f", "-n", f"{dst}p1"], capture_output=True).returncode, 0)
        mnt = self.d / "m"
        mnt.mkdir(exist_ok=True)
        sh("mount", "-o", "ro", f"{dst}p1", str(mnt))
        try:
            self.assertEqual(sha(mnt / "home/daten.bin"), hashlib.sha256(payload).hexdigest())
        finally:
            sh("umount", str(mnt))
        self.assertEqual(sh("blkid", "-o", "value", "-s", "TYPE", f"{dst}p2").strip(), "swap")


    def test_job_and_automation_adapt(self):
        src = self.loop("src.img", 300)
        sh("sfdisk", "-q", src, input="label: gpt\nstart=2048, size=280M\n")
        sh("partx", "-u", src)
        agent.imaging._wait_for([f"{src}p1"])
        tree = self.d / "t"
        (tree / "home").mkdir(parents=True)
        (tree / "home/x.bin").write_bytes(os.urandom(20 * MB))
        sh("mkfs.ext4", "-q", "-F", "-d", str(tree), f"{src}p1")
        dst = self.loop("dst.img", 150)
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(src, dst)):
            image = agentclient.create_image("127.0.0.1", self.key, src, self.nas, "PC", lambda e: None,
                                             threading.Event(), port=self.port)
            size = int(sh("blockdev", "--getsize64", dst))
            # Auftrag „Zurückspielen“ mit Anpassen (wie im Dialog)
            jm, results = jobs.JobManager(), []
            work = jobs.restore_work("127.0.0.1", self.key, self.port, str(image), dst, None, True,
                                     lambda job, path, error: results.append((path, error)),
                                     adapt={"target_size": size, "nas_root": str(self.nas)})
            job = jm.start("dev", "restore", dst, "Zurückspielen", work)
            for _ in range(600):
                if not job.running:
                    break
                threading.Event().wait(0.1)
            self.assertEqual(job.state, jobs.DONE, "\n".join(job.log))
            self.assertIn("Image wird angepasst", "".join(job.log))
            self.assertTrue(shrink.find_derived(image, size))
            self.assertEqual(subprocess.run(["e2fsck", "-f", "-n", f"{dst}p1"], capture_output=True).returncode, 0)
            # Automatisierung: Option aus → klare Meldung, nichts gelöscht
            store = devices.DeviceStore(self.d / "geraete")
            dev, _ = store.register("a", "127.0.0.1", "", {"dmi": {"product_uuid": "u"}}, "PC")
            disk = next(d for d in loop_disks(dst))
            s = automation.Settings(image=str(image.relative_to(self.nas)), disk_key=automation.disk_key(disk),
                                    adapt_smaller=False, finish="none")
            err = {}
            w = automation.automation_work("127.0.0.1", self.key, self.port, dev, s, str(self.nas), err)
            job = jm.start("dev", "auto", "x", "Auto", w)
            for _ in range(300):
                if not job.running:
                    break
                threading.Event().wait(0.1)
            self.assertEqual(job.state, jobs.FAILED)
            self.assertIn("passt nicht auf die Zieldisk", err["message"])

    def test_refusals(self):
        src = self.loop("src.img", 200)
        sh("sfdisk", "-q", src, input="label: gpt\nstart=2048, size=180M\n")
        sh("partx", "-u", src)
        agent.imaging._wait_for([f"{src}p1"])
        tree = self.d / "voll"
        tree.mkdir()
        (tree / "gross.bin").write_bytes(os.urandom(120 * MB))
        sh("mkfs.ext4", "-q", "-F", "-d", str(tree), f"{src}p1")
        settle(f"{src}p1")
        with mock.patch.object(imaging, "list_disks", lambda: loop_disks(src)):
            image = agentclient.create_image("127.0.0.1", self.key, src, self.nas, "voll", lambda e: None,
                                             threading.Event(), port=self.port)
        with self.assertRaisesRegex(shrink.ShrinkError, r"Passt nicht: .* belegt"):
            shrink.plan(image, 100 * MB)
        with self.assertRaisesRegex(shrink.ShrinkError, "passt schon"):
            shrink.plan(image, 400 * MB)
        # Rohkopie (z. B. BitLocker): nicht verkleinerbar
        meta = json.loads((image / agentclient.IMAGE_META).read_text())
        for step in meta["plan"]:
            if step.get("kind") == "pipe":
                step["cmds"][0][0] = "partclone.dd"
        (image / agentclient.IMAGE_META).write_text(json.dumps(meta))
        with self.assertRaisesRegex(shrink.ShrinkError, "Rohkopie"):
            shrink.plan(image, 100 * MB)


if __name__ == "__main__":
    unittest.main()
