"""Datei-Backup Ende-zu-Ende: Agent auf einer Loop-Disk (ext4 mit Windows-artiger Struktur) ↔ Tool/NAS."""

import json
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, backups, filebackup, wire
from tests.test_restore import can_run, loop_disks, sh


class RulesTest(unittest.TestCase):
    def test_skip_rules(self):
        for rel in ("pagefile.sys", "Users/Anna/AppData/Local/Temp/x.tmp", "$Recycle.Bin/S-1/a",
                    "Users/Anna/Documents/~$Offerte.docx", "home/anna/.cache/thumbs/a.png"):
            self.assertTrue(filebackup.skipped_by_rule(rel), rel)
        for rel in ("Users/Anna/Documents/Offerte.docx", "home/anna/.config/app.conf"):
            self.assertFalse(filebackup.skipped_by_rule(rel), rel)

    def test_profile_sources_and_mapping(self):
        src = backups.profile_sources("/dev/sda3", "Users/Anna", "windows", ["documents", "browser"])
        self.assertIn({"part": "/dev/sda3", "path": "Users/Anna/Documents"}, src)
        self.assertIn({"part": "/dev/sda3", "path": "Users/Anna/AppData/Local/Google/Chrome/User Data/*/Bookmarks"},
                      src)
        self.assertEqual(backups.profile_sources("/dev/sda2", "home/anna", "linux", []),
                         [{"part": "/dev/sda2", "path": "home/anna"}])
        plan = backups.RestorePlan("/dev/sdb3", [("sda3/Users/Anna", "Users/Neu"), ("sda3", "Okula-Wiederherstellung")])
        self.assertEqual(plan.target("sda3/Users/Anna/Documents/a.txt"), "Users/Neu/Documents/a.txt")
        self.assertEqual(plan.target("sda3/Daten/b.txt"), "Okula-Wiederherstellung/Daten/b.txt")
        self.assertIsNone(plan.target("sda5/x"))


@unittest.skipUnless(can_run(), "braucht root und Loop-Devices")
class BackupE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        img = self.d / "disk.img"
        with open(img, "wb") as f:
            f.truncate(256 * 1024 * 1024)
        self.dev = sh("losetup", "-fP", "--show", str(img)).strip()
        sh("sfdisk", "-q", self.dev, input="label: gpt\nstart=2048, size=96M\nstart=, size=96M\n")
        sh("partx", "-u", self.dev)
        agent.imaging._wait_for([f"{self.dev}p1", f"{self.dev}p2"])
        src = self.d / "win"
        files = {"Windows/System32/notepad.exe": b"MZ", "pagefile.sys": b"P" * 1000,
                 "Users/Anna/Documents/Offerte.docx": b"Offerte" * 5000,
                 "Users/Anna/Desktop/Notiz.txt": "Grüezi".encode(),
                 "Users/Anna/AppData/Local/Temp/junk.tmp": b"x",
                 "Users/Anna/AppData/Local/Google/Chrome/User Data/Default/Bookmarks": b'{"roots":{}}',
                 "Users/Public/Desktop/x.lnk": b"L", "Daten/Buchhaltung/2026.xlsx": b"XLSX" * 1000}
        for rel, data in files.items():
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_bytes(data)
        self.files = files
        sh("mkfs.ext4", "-q", "-F", "-d", str(src), f"{self.dev}p1")
        tgt = self.d / "neu"
        (tgt / "Windows").mkdir(parents=True)
        (tgt / "Users/Neu/Documents").mkdir(parents=True)
        (tgt / "Users/Neu/Documents/Offerte.docx").write_bytes(b"neu")
        sh("mkfs.ext4", "-q", "-F", "-d", str(tgt), f"{self.dev}p2")
        self.nas = self.d / "nas"
        self.nas.mkdir()
        self.key = bytes(range(32))
        self.patches = [mock.patch.object(agent, "log", lambda *a, **k: None),
                        mock.patch.object(filebackup, "WORK", self.d / "work"),
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
        subprocess.run(["umount", str(self.d / "mnt")], capture_output=True)
        subprocess.run(["losetup", "-d", self.dev], capture_output=True)
        self.tmp.cleanup()

    def part(self, n):
        return f"{self.dev}p{n}"

    def test_profiles_estimate_backup_download_restore(self):
        parts = {p["part"]: p for p in backups.get_profiles("127.0.0.1", self.key, self.port)}
        win = parts[self.part(1)]
        self.assertEqual(win["kind"], "windows")
        self.assertEqual([u["name"] for u in win["users"]], ["Anna"])  # Public fällt weg
        self.assertEqual([e["name"] for e in backups.browse("127.0.0.1", self.key, self.port, self.part(1), "Daten")],
                         ["Buchhaltung"])
        sources = backups.profile_sources(self.part(1), "Users/Anna", "windows", list(backups.DEFAULT_CATEGORIES))
        est = backups.estimate("127.0.0.1", self.key, self.port, sources)
        self.assertEqual(est["files"], 3)  # Offerte, Notiz, Bookmarks – Temp nicht

        name = Path(self.part(1)).name
        for storage in ("files", "tar"):
            events = []
            path = backups.run_backup("127.0.0.1", self.key, self.port, self.dev, sources, self.nas,
                                      {"id": "dev1", "name": "PC Empfang"}, "profiles", storage, ["Test"],
                                      events.append, threading.Event())
            manifest = json.loads((path / backups.MANIFEST).read_text())
            self.assertEqual((manifest["files"], manifest["storage"], manifest["device_id"]), (3, storage, "dev1"))
            index = {r[0]: r for r in backups.read_index(path)}
            self.assertIn(f"{name}/Users/Anna/Documents/Offerte.docx", index)
            if storage == "files":
                self.assertEqual((path / "Dateien" / name / "Users/Anna/Desktop/Notiz.txt").read_text(), "Grüezi")
            else:
                self.assertTrue((path / backups.ARCHIVE).is_file())
            # Herunterladen in einen Ordner
            out = self.d / f"download-{storage}"
            n = backups.download(path, out, [f"{name}/Users/Anna/Documents"], lambda e: None, threading.Event())
            self.assertEqual(n, 1)
            self.assertEqual((out / name / "Users/Anna/Documents/Offerte.docx").read_bytes(), b"Offerte" * 5000)
        self.assertEqual(len(backups.list_backups(self.nas)), 2)

        # Zurückspielen: Anna → Neu auf Partition 2; vorhandene Offerte bleibt, neue kommt mit Zusatz
        plan = backups.RestorePlan(self.part(2), [(f"{name}/Users/Anna", "Users/Neu")])
        result = backups.run_restore("127.0.0.1", self.key, self.port, self.dev, path, plan, lambda e: None,
                                     threading.Event())
        self.assertEqual((result["files"], result["renamed"]), (3, 1))
        mnt = self.d / "mnt"
        mnt.mkdir()
        sh("mount", self.part(2), str(mnt))
        try:
            docs = mnt / "Users/Neu/Documents"
            self.assertEqual((docs / "Offerte.docx").read_bytes(), b"neu")
            self.assertEqual((docs / "Offerte (wiederhergestellt).docx").read_bytes(), b"Offerte" * 5000)
            self.assertEqual((mnt / "Users/Neu/Desktop/Notiz.txt").read_text(), "Grüezi")
        finally:
            sh("umount", str(mnt))

    def test_whole_partition_skips_system_files(self):
        path = backups.run_backup("127.0.0.1", self.key, self.port, self.dev, [{"part": self.part(1), "path": ""}],
                                  self.nas, {"id": "d", "name": "X"}, "partitions", "files", [], lambda e: None,
                                  threading.Event())
        rels = {r[0].split("/", 1)[1] for r in backups.read_index(path)}
        self.assertIn("Daten/Buchhaltung/2026.xlsx", rels)
        self.assertIn("Windows/System32/notepad.exe", rels)
        self.assertNotIn("pagefile.sys", rels)
        self.assertNotIn("Users/Anna/AppData/Local/Temp/junk.tmp", rels)
        self.assertFalse(list(self.nas.rglob("*.partial")))


if __name__ == "__main__":
    unittest.main()
