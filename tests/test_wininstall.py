"""Windows-Direktinstallation: Tool → Agent auf einer Loop-Disk (ohne FAT/NTFS im Test-Kernel: ext4)."""

import re
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from okula_recovery import agent, agentclient, jobs, wininstall, winsetup, winunattend, wire
from tests.isofixtures import HAVE_TOOLS, windows_iso
from tests.test_restore import can_run, loop_disks, sh


class ScriptTest(unittest.TestCase):
    def test_install_cmd_split_and_single(self):
        cmd = winsetup.install_cmd("ab12cd34", 2, "sources/install.wim", True, "de-DE")
        self.assertIn("\r\n", cmd)
        self.assertTrue(cmd.isascii(), "cmd-Skripte nur ASCII")
        self.assertIn('/SWMFile:"%S%:\\sources\\install*.swm" /Index:2 /ApplyDir:%W%:\\', cmd)
        self.assertIn("okula-ab12cd34.target", cmd)
        self.assertIn("bcdboot %W%:\\Windows /s Z: /f UEFI /l de-DE", cmd)
        self.assertIn("wpeutil reboot", cmd)
        single = winsetup.install_cmd("x", 1, "sources/install.esd", False, "en-US")
        self.assertIn('/ImageFile:"%S%:\\sources\\install.esd" /Index:1', single)
        self.assertNotIn("SWMFile", single)
        done = winsetup.setupcomplete_cmd("ab12cd34")
        self.assertIn("okula\\ab12cd34.setup", done)
        self.assertIn("delete partition override", done)
        self.assertIn("extend", done)
        self.assertNotIn(" C D ", done.split("for %%L in (")[1].split(")")[0] + " ")  # C: nie löschen

    def test_install_cmd_finds_partition_safely(self):
        """B-014: Markierung, sonst genau ein Laufwerk mit Bezeichnung OKULAWIN, sonst Fehler – nie auf Verdacht."""
        cmd = winsetup.install_cmd("ab12cd34", 1, "sources/install.wim", False, "de-DE")
        self.assertEqual(winsetup.WIN_LABEL, wininstall.WIN_LABEL)
        main = cmd.split(":fehler")[0]
        marker = main.index("okula-ab12cd34.target set W=%%L")
        by_label = main.index("call :bezeichnung %%L")
        self.assertLess(marker, by_label)
        self.assertLess(main.index('if not "%W%"=="" goto gefunden'), by_label)  # Markierung hat Vorrang
        # Bezeichnung nur bei genau einem Treffer, und erst danach wird W gesetzt
        self.assertLess(main.index('if not "%N%"=="1" goto fehler'), main.index("set W=%K%"))
        self.assertLess(main.index("set W=%K%"), main.index(":gefunden"))
        # formatiert wird nur %W% und erst nach der Suche
        self.assertEqual(re.findall(r"^format [^\r\n]*", cmd, re.M), ['format %W%: /fs:ntfs /q /y /v:Windows >> "%LOG%" 2>&1'])
        self.assertLess(main.index(":gefunden"), main.index("format %W%:"))
        # Suche über die Bezeichnung: genaues Wort aus der vol-Ausgabe, zählt jeden Treffer
        sub = cmd.split(":bezeichnung\r\n")[1].split("goto :eof")[1]
        self.assertIn("('vol %1: 2^>nul')", sub)
        self.assertIn('if /i "%%t"=="OKULAWIN" (set /a N+=1 & set K=%1)', sub)
        self.assertNotIn("Windows", sub)   # altes Windows („Windows“) zählt nie

    def test_install_cmd_error_diagnosis(self):
        """Ä-039: Laufwerksliste und je Laufwerk Bezeichnung/Inhalt/Markierung; Hinweis oben im Editor."""
        cmd = winsetup.install_cmd("ab12cd34", 1, "sources/install.wim", True, "de-DE")
        self.assertTrue(cmd.isascii(), "cmd-Skripte nur ASCII")
        self.assertNotIn("\n", cmd.replace("\r\n", ""), "nur CRLF")
        error = cmd.split("\r\n:fehler\r\n")[1]
        self.assertIn('> "%TEMP%\\okula-dp.txt" echo list volume', error)
        self.assertIn('diskpart /s "%TEMP%\\okula-dp.txt" >> "%LOG%" 2>&1', error)
        self.assertIn("call :laufwerk %%L", error)
        drive = cmd.split("\r\n:laufwerk\r\n")[1]
        self.assertIn("if exist %1:\\okula-*.target set M=ja", drive)
        self.assertIn('dir %1:\\ >> "%LOG%" 2>&1', drive)   # Bezeichnung, Inhalt, freier Platz
        self.assertIn("set FEHLT=%FEHLT% %1:", drive)        # nicht vorhandene Laufwerke
        head = error.split('> "%TEMP%\\okula-kopf.txt" (')[1].split("\r\n)\r\n")[0]
        self.assertIn("Nach dem Schliessen dieses Fensters schaltet sich das Geraet aus.", head)
        self.assertIn("Fuer eine Eingabeaufforderung vorher Shift+F10 druecken.", head)
        self.assertIn("X:\\Windows\\System32\\cmd.exe", head)
        self.assertNotIn(")", head)  # sonst endet der Klammerblock zu früh
        self.assertNotRegex(head.lower(), r"\b(du|sie|ihr|dein)\b")
        # Hinweis zuoberst ins Protokoll, dann Editor, dann Ausschalten
        self.assertLess(error.index('"%TEMP%\\okula-kopf.txt"+"%LOG%"'), error.index('notepad "%LOG%"'))
        self.assertLess(error.index('notepad "%LOG%"'), error.index("wpeutil shutdown"))
        self.assertLess(error.index("wpeutil shutdown"), error.index("exit /b 1"))
        self.assertLess(error.index("exit /b 1"), error.index(":bezeichnung"))  # nicht in die Unterprogramme laufen
        # Echo-Zeilen ausserhalb von Klammerblöcken ohne Klammern (Fehlerquelle in cmd)
        for line in cmd.split(":fehler")[0].splitlines():
            if "echo" in line and ">>" in line:
                self.assertNotIn("(", line.split("echo", 1)[1], line)

    def test_layout(self):
        t = wininstall.layout(256 * 1000**3, 7 * 1024**3, 40 * 1000**3)
        sizes = [int(x) for x in re.findall(r"size=(\d+)MiB", t)]
        self.assertEqual(sizes[:2], [260, 16])
        self.assertIn(wininstall.GPT_ESP, t)
        self.assertTrue(t.strip().endswith('name="Okula Setup"'))
        with self.assertRaisesRegex(wininstall.ImagingError, "zu klein"):
            wininstall.layout(32 * 1000**3, 7 * 1024**3, 40 * 1000**3)


MIB = 1024 * 1024
NTFS_TOOLS = all(shutil.which(t) for t in ("mkntfs", "wipefs", "blkid"))


class WipeTest(unittest.TestCase):
    """B-014: Anfang und Ende der Partition mit Nullen überschreiben – hier auf Probe-Dateien (ohne root)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def probe(self, size, fill=b"\xab"):
        path = self.d / "part.img"
        with open(path, "wb") as f:
            for _ in range(size // MIB):
                f.write(fill * MIB)
            f.write(fill * (size % MIB))
        return path

    def test_ranges(self):
        self.assertEqual(wininstall.zero_ranges(100 * MIB), [(0, 16 * MIB), (99 * MIB, MIB)])
        self.assertEqual(wininstall.zero_ranges(16 * MIB), [(0, 16 * MIB)])   # MSR: ganz
        start, length = wininstall.zero_ranges(100 * MIB + 512)[1]
        self.assertEqual(start % 4096, 0)
        self.assertEqual(start + length, 100 * MIB + 512)                      # bis zum letzten Sektor
        self.assertGreaterEqual(length, MIB)

    def test_head_and_tail_zeroed_middle_kept(self):
        path = self.probe(40 * MIB + 1000)   # Länge nicht ausgerichtet → ohne O_DIRECT weiter
        wininstall.zero_ends(str(path))
        data = path.read_bytes()
        self.assertEqual(len(data), 40 * MIB + 1000)
        self.assertEqual(data[:16 * MIB].count(0), 16 * MIB)
        self.assertEqual(data[-MIB:].count(0), MIB)
        self.assertEqual(set(data[16 * MIB:39 * MIB]), {0xAB})

    def test_small_partition_completely(self):
        path = self.probe(8 * MIB)
        wininstall.zero_ends(str(path))
        self.assertEqual(path.read_bytes().count(0), 8 * MIB)

    @unittest.skipUnless(NTFS_TOOLS, "braucht mkntfs, wipefs, blkid")
    def test_old_ntfs_gone_and_probe_reads_label(self):
        path = str(self.probe(64 * MIB, b"\0"))
        sh("mkntfs", "-F", "-Q", "-q", "-L", "Windows", path)
        data = Path(path).read_bytes()
        self.assertEqual(data[3:11], b"NTFS    ")
        self.assertEqual(data[-512:][3:11], b"NTFS    ")   # Backup-Bootsektor im letzten Sektor
        self.assertEqual(wininstall._probe(path).get("LABEL"), "Windows")
        wininstall._wipe(path)
        data = Path(path).read_bytes()
        self.assertEqual(data[:512].count(0), 512)
        self.assertEqual(data[-512:].count(0), 512)
        self.assertEqual(wininstall._probe(path), {})        # keine Signatur mehr
        sh("mkntfs", "-F", "-Q", "-q", "-L", "OKULAWIN", path)
        self.assertEqual({k: v for k, v in wininstall._probe(path).items() if k in ("TYPE", "LABEL")},
                         {"TYPE": "ntfs", "LABEL": "OKULAWIN"})


class CheckAfterWriteTest(unittest.TestCase):
    """B-014: Prüfung nach dem Schreiben – Bezeichnung und Markierung müssen von der Disk kommen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.where = Path(self.tmp.name) / "windows"
        self.mounts = []
        self.patches = [mock.patch.object(wininstall, "_flush", lambda part: None),
                        mock.patch.object(wininstall, "_umount", lambda where: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def check(self, probe, marker_present=True):
        def mount(part, where, ntfs=False, ro=False):
            self.mounts.append((part, ntfs, ro))
            where.mkdir(parents=True, exist_ok=True)
            if marker_present:
                (where / "okula-ab12.target").write_text("x")

        with mock.patch.object(wininstall, "_probe", lambda part: probe), \
                mock.patch.object(wininstall, "_mount", mount):
            wininstall.check_windows_partition("/dev/sdz3", "okula-ab12.target", self.where)

    def test_ok(self):
        self.check({"TYPE": "ntfs", "LABEL": "OKULAWIN"})
        self.assertEqual(self.mounts, [("/dev/sdz3", True, True)])   # nur lesend eingehängt

    def test_old_windows_label(self):
        with self.assertRaisesRegex(wininstall.ImagingError,
                                    "Schreiben auf die Disk wird nicht übernommen – Disk prüfen.*„Windows“"):
            self.check({"TYPE": "ntfs", "LABEL": "Windows"})
        self.assertEqual(self.mounts, [])

    def test_no_filesystem(self):
        with self.assertRaisesRegex(wininstall.ImagingError, "kein Dateisystem"):
            self.check({})

    def test_marker_missing(self):
        with self.assertRaisesRegex(wininstall.ImagingError, "Markierung okula-ab12.target fehlt"):
            self.check({"TYPE": "ntfs", "LABEL": "OKULAWIN"}, marker_present=False)


class InstallFlowTest(unittest.TestCase):
    """B-014: Ablauf von install() ohne Disk – Löschen vor dem Formatieren, Prüfung vor BootNext."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "efi").mkdir()
        self.calls = []
        self.sent = []
        rec = self.calls.append

        def mount(part, where, ntfs=False, ro=False):
            rec(("mount", part, ro))
            where.mkdir(parents=True, exist_ok=True)

        self.messages = [{"type": "end"}]
        self.patches = [
            mock.patch.object(wininstall.imaging, "_find_target",
                              lambda p: {"path": "/dev/sdz", "size": 256 * 1000**3, "partitions": []}),
            mock.patch.object(wininstall.imaging, "_wait_for", lambda parts: None),
            mock.patch.object(wininstall.imaging, "_frames", lambda sock, info: iter([b"wim"])),
            mock.patch.object(wininstall, "EFI_DIR", self.d / "efi"),
            mock.patch.object(wininstall, "WORK", self.d / "work"),
            mock.patch.object(wininstall, "subprocess", mock.Mock()),
            mock.patch.object(wininstall, "_run", lambda cmd, input=None: rec((cmd[0], cmd[-1])) or ""),
            mock.patch.object(wininstall, "_wipe", lambda part: rec(("wipe", part))),
            mock.patch.object(wininstall, "_mkfat", lambda part, label: rec(("mkfat", part))),
            mock.patch.object(wininstall, "_mkstage", lambda part: rec(("mkstage", part))),
            mock.patch.object(wininstall, "_mkntfs", lambda part, label: rec(("mkntfs", part, label))),
            mock.patch.object(wininstall, "_mount", mount),
            mock.patch.object(wininstall, "_umount", lambda where: None),
            mock.patch.object(wininstall, "_split", lambda *a: rec(("split",))),
            mock.patch.object(wininstall.wire, "send_json", lambda sock, msg: self.sent.append(msg)),
            mock.patch.object(wininstall.wire, "recv_json", lambda sock: self.messages.pop(0)),
            mock.patch.object(wininstall, "set_bootnext", lambda *a: rec(("bootnext",)) or "0007"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def install(self, split=False, check_error=None):
        def check(part, marker, where):
            self.calls.append(("check", part, marker))
            if check_error:
                raise wininstall.ImagingError(check_error)

        req = {"disk": "/dev/sdz", "setup_size": 6 * 1024**3, "target_marker": "okula-ab12.target",
               "files": [], "split": None}
        if split:
            req["files"] = [{"path": "sources/install.wim", "size": 3}]
            req["split"] = {"path": "sources/install.wim", "mb": 1}
            self.messages[:0] = [{"type": "file", "path": "sources/install.wim"}]
        with mock.patch.object(wininstall, "check_windows_partition", check):
            return wininstall.install(None, req, log=lambda m: None)

    def test_wipe_before_format_and_check_before_bootnext(self):
        self.assertEqual(self.install(), "0007")
        names = [c[0] for c in self.calls]
        wipes = [c[1] for c in self.calls if c[0] == "wipe"]
        self.assertEqual(wipes, ["/dev/sdz1", "/dev/sdz2", "/dev/sdz3", "/dev/sdz4"])
        self.assertLess(names.index("sfdisk"), names.index("wipe"))
        self.assertLess(max(i for i, n in enumerate(names) if n == "wipe"), names.index("mkfat"))
        self.assertIn(("mkntfs", "/dev/sdz3", "OKULAWIN"), self.calls)
        self.assertEqual(names[-2:], ["check", "bootnext"])
        self.assertIn(("check", "/dev/sdz3", "okula-ab12.target"), self.calls)

    def test_split_stage_wiped_again_before_ntfs(self):
        self.install(split=True)
        names = [c[0] for c in self.calls]
        stage = names.index("mkstage")
        self.assertEqual(self.calls[names.index("mkntfs") - 1], ("wipe", "/dev/sdz3"))
        self.assertLess(stage, names.index("mkntfs") - 1)

    def test_check_fails_no_bootnext(self):
        with self.assertRaisesRegex(wininstall.ImagingError, "nicht übernommen"):
            self.install(check_error=wininstall.WRITE_CHECK_FAILED)
        self.assertNotIn(("bootnext",), self.calls)

    def test_agent_reports_error_without_reboot(self):
        """Fehlerfall: klare Meldung an das Tool, kein Neustart des Geräts."""
        sent, timers = [], []
        error = wininstall.ImagingError(f"{wininstall.WRITE_CHECK_FAILED} (Windows-Partition /dev/sdz3: …)")
        with mock.patch.object(agent.wininstall, "install", mock.Mock(side_effect=error)), \
                mock.patch.object(agent.wire, "send_json", lambda sock, msg: sent.append(msg)), \
                mock.patch.object(agent, "log", lambda *a, **k: None), \
                mock.patch.object(agent.threading, "Timer", lambda *a, **k: timers.append(a) or mock.Mock()):
            agent.run_job(None, ("127.0.0.1", 0), {"disk": "/dev/sdz", "reboot": True}, "install")
        self.assertEqual(sent[-1]["type"], "error")
        self.assertIn("Schreiben auf die Disk wird nicht übernommen – Disk prüfen", sent[-1]["message"])
        self.assertEqual(timers, [])


@unittest.skipUnless(can_run() and HAVE_TOOLS, "braucht root, Loop-Devices, genisoimage, wimlib, xorriso")
class DirectInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        img = self.d / "disk.img"
        with open(img, "wb") as f:
            f.truncate(1536 * 1024 * 1024)
        self.dev = sh("losetup", "-fP", "--show", str(img)).strip()
        self.key = bytes(range(32))
        self.efi = []
        efi_dir = self.d / "efi"
        efi_dir.mkdir()

        def fake_efibootmgr(*args):
            self.efi.append(args)
            entries = "BootCurrent: 0001\nBoot0000* Windows Boot Manager\nBoot0001* USB\n"
            if any("--create-only" in a for a in args) or len(self.efi) > 2:
                entries += "Boot0007* Okula Windows-Installation\n"
            return entries

        def mkfs(part, label=""):
            sh("mkfs.ext4", "-q", "-F", part)

        def mount(part, where, ntfs=False, ro=False):
            where.mkdir(parents=True, exist_ok=True)
            sh("mount", *(["-o", "ro"] if ro else []), part, str(where))

        self.patches = [
            mock.patch.object(wininstall, "EFI_DIR", efi_dir),
            mock.patch.object(wininstall, "WORK", self.d / "work"),
            mock.patch.object(wininstall, "MIN_WIN_MIB", 64),
            mock.patch.object(wininstall, "_mkfat", mkfs),
            mock.patch.object(wininstall, "_mkntfs", mkfs),
            mock.patch.object(wininstall, "_mount", mount),
            # Test-Kernel ohne NTFS: ext4 statt NTFS, Bezeichnung wie nach mkntfs
            mock.patch.object(wininstall, "_probe", lambda part: {"TYPE": "ntfs", "LABEL": "OKULAWIN"}),
            mock.patch.object(wininstall, "efibootmgr", fake_efibootmgr),
            mock.patch.object(winsetup, "FAT32_MAX", 1_000_000),
            mock.patch.object(winsetup, "SPLIT_MB", 1),
            mock.patch.object(winsetup, "MIN_DISK", 0),
            mock.patch.object(agent, "log", lambda *a, **k: None),
            mock.patch.object(agent.imaging, "list_disks", lambda: loop_disks(self.dev)),
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
        subprocess.run(["umount", "-R", str(self.d / "mnt")], capture_output=True)
        subprocess.run(["losetup", "-d", self.dev], capture_output=True)
        self.tmp.cleanup()

    def mounted(self, number):
        mnt = self.d / "mnt"
        mnt.mkdir(exist_ok=True)
        sh("mount", f"{self.dev}p{number}", str(mnt))
        return mnt

    def test_setup_partition_prepared_and_bootnext_set(self):
        iso = windows_iso(self.d, payload=3_000_000)
        opts = winunattend.WinOptions(local_account="Okula", computer_name="PC-Empfang")
        plan = winsetup.plan(iso, 2, opts)
        self.assertTrue(plan.split)
        events = []
        timers = []
        with mock.patch.object(agent.threading, "Timer", lambda *a, **k: timers.append(a) or mock.Mock()):
            boot = agentclient.install_windows("127.0.0.1", self.key, iso, plan, self.dev, events.append,
                                               threading.Event(), self.port)
            for _ in range(50):  # Agent schliesst den Auftrag kurz nach „done“ ab
                if timers:
                    break
                threading.Event().wait(0.1)
        self.assertEqual(boot, "0007")
        self.assertEqual(timers[0][0], 15)  # Neustart geplant (hier nicht ausgeführt)
        self.assertIn("split", [e["phase"] for e in events])
        table = sh("sfdisk", "-d", self.dev)
        self.assertIn("label: gpt", table)
        self.assertEqual(len(re.findall(rf"^{self.dev}p\d", table, re.M)), 4)
        self.assertIn(f"type={wininstall.GPT_ESP}", table)
        # BootNext auf Partition 4 der Zieldisk
        create = next(a for a in self.efi if "--create-only" in a)
        self.assertEqual(create[create.index("--disk") + 1], self.dev)
        self.assertEqual(create[create.index("--part") + 1], "4")
        self.assertIn(("--bootnext", "0007"), self.efi)

        setup = self.mounted(4)
        try:
            names = {str(p.relative_to(setup)).lower() for p in setup.rglob("*")}
            for f in ("bootmgr", "efi/boot/bootx64.efi", "sources/boot.wim", "sources/install.swm",
                      "sources/install2.swm", "autounattend.xml", "sources/autounattend.xml",
                      "okula/install.cmd", "okula/unattend.xml", "okula/setupcomplete.cmd",
                      f"okula/{plan.install_id}.setup"):
                self.assertIn(f, names)
            self.assertNotIn("sources/install.wim", names)
            r = subprocess.run(["wimlib-imagex", "verify", str(setup / "sources/install.swm"),
                                f"--ref={setup}/sources/install*.swm"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            launcher = (setup / "sources/autounattend.xml").read_text()
            self.assertIn("okula\\install.cmd", launcher)
            root = ET.fromstring(launcher)
            self.assertEqual([s.get("pass") for s in root], ["windowsPE"])
            system = ET.fromstring((setup / "okula/unattend.xml").read_text())
            self.assertEqual([s.get("pass") for s in system], ["specialize", "oobeSystem"])
            self.assertIn("HideWirelessSetupInOOBE", (setup / "okula/unattend.xml").read_text())
            self.assertIn("PC-Empfang", (setup / "okula/unattend.xml").read_text())
            self.assertIn("/Index:2", (setup / "okula/install.cmd").read_text())
        finally:
            sh("umount", str(setup))
        win = self.mounted(3)
        try:
            self.assertTrue((win / plan.target_marker).is_file())
        finally:
            sh("umount", str(win))

    def test_refuses_bios_mode(self):
        iso = windows_iso(self.d)
        plan = winsetup.plan(iso, 1, winunattend.WinOptions())
        with mock.patch.object(wininstall, "EFI_DIR", self.d / "nicht-da"):
            with self.assertRaisesRegex(agentclient.AgentError, "BIOS-Modus"):
                agentclient.install_windows("127.0.0.1", self.key, iso, plan, self.dev, lambda e: None,
                                            threading.Event(), self.port)

    def test_job_phases(self):
        iso = windows_iso(self.d, payload=3_000_000)
        jm = jobs.JobManager()
        results = []
        with mock.patch.object(agent.threading, "Timer", lambda *a, **k: mock.Mock()):
            job = jm.start("dev", "install", self.dev, "Windows",
                           jobs.install_work("127.0.0.1", self.key, self.port, str(iso), 1,
                                             winunattend.WinOptions(), self.dev,
                                             lambda j, b, e: results.append((b, e))))
            for _ in range(300):
                if not job.running:
                    break
                threading.Event().wait(0.1)
        self.assertEqual(job.state, jobs.DONE, job.log)
        self.assertEqual(results, [("0007", None)])
        self.assertTrue(any("Agent-Stick stecken lassen" in line for line in job.log))


if __name__ == "__main__":
    unittest.main()
