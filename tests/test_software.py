"""I-020 Software installieren: Katalog, Erkennung der Installer, neue Version, Auswahl."""

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

from okula_recovery import distribute, software


def pe(sections=(".text", ".rdata", ".rsrc"), body: bytes = b"") -> bytes:
    """Kleinste Windows-Programmdatei: MZ-Kopf, PE-Kopf ohne optionalen Teil, Abschnittstabelle, Inhalt."""
    head = bytearray(0x80)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x80)
    coff = b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, len(sections), 0, 0, 0, 0, 0x22)
    table = b"".join(name.encode().ljust(8, b"\0") + bytes(32) for name in sections)
    return bytes(head) + coff + table + bytes(64) + body


def version_string(key: str, value: str) -> bytes:
    """Ein String-Eintrag aus VS_VERSIONINFO (Schlüssel, auf 32 Bit aufgefüllt, Wert)."""
    k = key.encode("utf-16-le") + b"\0\0"
    v = value.encode("utf-16-le") + b"\0\0"
    pad = b"\0\0" if (6 + len(k)) % 4 else b""
    body = k + pad + v
    return struct.pack("<HHH", 6 + len(body), len(value) + 1, 1) + body


NSIS = pe(body=b"<assemblyIdentity name=\"Nullsoft.NSIS.exehead\"/>" + bytes(512) +
          b"\xef\xbe\xad\xdeNullsoftInst" + version_string("ProductName", "VLC media player") +
          version_string("ProductVersion", "3.0.24"))
INNO = pe(body=b"Inno Setup Setup Data (6.2.2)" + "This installation was built with Inno Setup.".encode("utf-16-le"))
WIX = pe(sections=(".text", ".rdata", ".wixburn", ".rsrc"))
ISHIELD = pe(body="InstallShield (R)".encode("utf-16-le"))
SQUIRREL = pe(body=b"SquirrelSetup Update.exe --install")
UNKNOWN = pe(body=b"just some program")
MSI = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(1024)


class DetectTest(unittest.TestCase):
    def test_types(self):
        cases = {"vlc.exe": (NSIS, "nsis", "/S"),
                 "inno.exe": (INNO, "inno", "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"),
                 "burn.exe": (WIX, "wix", "/quiet /norestart"),
                 "is.exe": (ISHIELD, "installshield", '/s /v"/qn /norestart"'),
                 "reader.msi": (MSI, "msi", "/qn /norestart"),
                 "tool.exe": (UNKNOWN, "", "")}
        for name, (data, kind, args) in cases.items():
            with self.subTest(name):
                found = software.detect_bytes(data, name)
                self.assertEqual((found["kind"], found["args"], found["mode"]), (kind, args, software.INSTALL))

    def test_squirrel_manual(self):
        found = software.detect_bytes(SQUIRREL, "Teams.exe")
        self.assertEqual((found["kind"], found["mode"]), ("squirrel", software.MANUAL))
        self.assertIn("angemeldeten Benutzer", found["note"])

    def test_msi_by_extension_and_magic(self):
        self.assertEqual(software.detect_bytes(b"", "x.MSI")["kind"], "msi")
        self.assertEqual(software.detect_bytes(MSI, "ohne-endung.exe")["kind"], "msi")
        self.assertEqual(software.detect_bytes(b"kein Programm", "x.exe")["kind"], "")

    def test_version_info(self):
        found = software.detect_bytes(NSIS, "vlc.exe")
        self.assertEqual((found["program"], found["version"]), ("VLC media player", "3.0.24"))
        self.assertEqual(software.version_info(b"\0\0" + version_string("FileVersion", "1.2")),
                         {"FileVersion": "1.2"})

    def test_sections(self):
        self.assertIn(".wixburn", software._pe_sections(WIX))
        self.assertEqual(software._pe_sections(b"MZ" + bytes(10)), [])


class NameTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(software.split_name("vlc-3.0.24-win64.exe"), ("vlc", "3.0.24", "vlc"))
        self.assertEqual(software.split_name("vlc-3.0.23-win64.exe")[2], "vlc")
        self.assertEqual(software.split_name("AcroRdrDC2400221005_de_DE.exe"),
                         ("AcroRdrDC", "2400221005", "acrordrdc-de-de"))
        self.assertEqual(software.split_name("Firefox Setup 120.0.1.exe"), ("Firefox Setup", "120.0.1", "firefox"))
        self.assertEqual(software.split_name("npp.8.6.2.Installer.x64.exe")[::2], ("npp", "npp"))
        self.assertEqual(software.split_name("7z2301-x64.exe"), ("7z", "2301", "7z"))
        self.assertEqual(software.split_name("Tool v1.2.msi"), ("Tool", "1.2", "tool"))
        self.assertEqual(software.split_name("setup.exe")[2], "")
        self.assertEqual(software.split_name("Barco Eventmaster Toolset 7.2")[::2],
                         ("Barco Eventmaster Toolset", "barco-eventmaster-toolset"))

    def test_exit_codes_and_args(self):
        self.assertEqual(software.parse_exit_codes("0, 3010;1641 0"), [0, 3010, 1641])
        with self.assertRaises(software.SoftwareError):
            software.parse_exit_codes("0, ok")
        with self.assertRaises(software.SoftwareError):
            software.parse_exit_codes(" ")
        with self.assertRaises(software.SoftwareError):
            software.check_args("/S\n/D=C:\\x")
        self.assertEqual(software.check_args("  /S  "), "/S")


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sw = distribute.ensure(self.root) / "Software"

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel: str, data: bytes) -> Path:
        path = self.sw / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_new_file_appears_with_hidden_description(self):
        self.put("vlc-3.0.24-win64.exe", NSIS)
        self.put("AcroRdrDC_de_DE.msi", MSI)
        self.put("Liesmich.txt", b"kein Installer")
        self.put("Unbekannt-Setup.exe", UNKNOWN)
        entries = {e.name: e for e in software.scan(self.root)}
        self.assertEqual(set(entries), {"vlc-3.0.24-win64.exe", "AcroRdrDC_de_DE.msi", "Unbekannt-Setup.exe"})
        vlc = entries["vlc-3.0.24-win64.exe"]
        self.assertEqual((vlc.program, vlc.version, vlc.kind, vlc.args, vlc.status, vlc.selectable),
                         ("VLC media player", "3.0.24", "nsis", "/S", software.READY, True))
        self.assertEqual(entries["AcroRdrDC_de_DE.msi"].status, software.READY)
        unknown = entries["Unbekannt-Setup.exe"]
        self.assertEqual((unknown.status, unknown.selectable), (software.MISSING, False))
        meta = json.loads((self.sw / ".vlc-3.0.24-win64.exe.okula.json").read_text())
        self.assertEqual((meta["kind"], meta["args"], meta["exit_codes"], meta["size"]), ("nsis", "/S", [0, 3010],
                                                                                         len(NSIS)))
        self.assertEqual(len(meta["sha256"]), 64)
        # Beschreibungen erscheinen nicht als Einträge, Ordner senden nimmt sie nicht mit
        self.assertEqual(len(software.scan(self.root)), 3)
        names = [rel for _k, rel, *_r in distribute.plan(self.root, ["Software"]).entries]
        self.assertFalse(any(n.endswith(".okula.json") for n in names))

    def test_missing_parameters_become_selectable_after_edit(self):
        self.put("Unbekannt-Setup.exe", UNKNOWN)
        software.scan(self.root)
        plan = software.plan(self.root, ["Unbekannt-Setup.exe"])
        self.assertEqual((plan.entries, plan.blocked), ([], [("Unbekannt-Setup.exe", software.MISSING)]))
        entry = software.update(self.root, "Unbekannt-Setup.exe", args="/silent", exit_codes="0, 3010, 1641")
        self.assertEqual((entry.status, entry.exit_codes), (software.READY, [0, 3010, 1641]))
        again = software.find(software.scan(self.root), "Unbekannt-Setup.exe")
        self.assertEqual((again.args, again.meta["edited"]), ("/silent", True))
        self.assertEqual(software.plan(self.root, ["Unbekannt-Setup.exe"]).names, ["Unbekannt-Setup.exe"])
        software.update(self.root, "Unbekannt-Setup.exe", mode=software.MANUAL)
        hand = software.find(software.scan(self.root), "Unbekannt-Setup.exe")
        self.assertEqual((hand.status, hand.selectable), (software.HAND, False))
        with self.assertRaises(software.SoftwareError):
            software.update(self.root, "Unbekannt-Setup.exe", mode=software.COPY)   # nur Ordner

    def test_new_version_adopts_parameters(self):
        self.put("vlc-3.0.23-win64.exe", UNKNOWN)
        software.scan(self.root)
        software.update(self.root, "vlc-3.0.23-win64.exe", args="/S /L=1031", exit_codes="0")
        # neue Version dazu, alte gelöscht – Parameter kommen trotzdem aus der alten Beschreibung
        (self.sw / "vlc-3.0.23-win64.exe").unlink()
        self.put("vlc-3.0.24-win64.exe", NSIS)
        new = software.find(software.scan(self.root), "vlc-3.0.24-win64.exe")
        self.assertEqual((new.args, new.exit_codes, new.adopted_from), ("/S /L=1031", [0], "vlc-3.0.23-win64.exe"))
        self.assertIn("übernommen", new.note)
        self.assertEqual(new.status, software.READY)
        # gespeicherte Auswahl (Automatisierung) mit dem alten Namen → neue Version
        p = software.plan(self.root, ["vlc-3.0.23-win64.exe"])
        self.assertEqual((p.names, p.renamed), (["vlc-3.0.24-win64.exe"],
                                                [("vlc-3.0.23-win64.exe", "vlc-3.0.24-win64.exe")]))

    def test_unrelated_program_not_adopted(self):
        self.put("vlc-3.0.23-win64.exe", UNKNOWN)
        software.scan(self.root)
        software.update(self.root, "vlc-3.0.23-win64.exe", args="/S")
        self.put("setup.exe", UNKNOWN)
        self.put("7z2301-x64.exe", UNKNOWN)
        entries = {e.name: e for e in software.scan(self.root)}
        self.assertEqual(entries["setup.exe"].status, software.MISSING)
        self.assertEqual(entries["7z2301-x64.exe"].args, "")

    def test_folder_installer_choice_and_copy(self):
        self.put("Barco Eventmaster Toolset 7.2/Setup.exe", INNO)
        self.put("Barco Eventmaster Toolset 7.2/data/lib.dll", b"x" * 100)
        self.put("System Tools/a.exe", UNKNOWN)
        self.put("System Tools/b.msi", MSI)
        self.put("System Tools/sub/c.txt", b"c")
        entries = {e.name: e for e in software.scan(self.root)}
        barco = entries["Barco Eventmaster Toolset 7.2"]
        self.assertEqual((barco.installer, barco.kind, barco.status, barco.size), ("Setup.exe", "inno", software.READY,
                                                                                    len(INNO) + 100))
        tools = entries["System Tools"]
        self.assertEqual((tools.status, tools.candidates), (software.MISSING, ["a.exe", "b.msi"]))
        self.assertIn("Installer im Ordner wählen", tools.note)
        with self.assertRaises(software.SoftwareError):
            software.update(self.root, "System Tools", installer="gibtsnicht.exe")
        chosen = software.update(self.root, "System Tools", installer="b.msi")
        self.assertEqual((chosen.kind, chosen.status), ("msi", software.READY))
        copy = software.update(self.root, "System Tools", mode=software.COPY)
        self.assertEqual((copy.status, copy.selectable, copy.kind_label), (software.COPY_ONLY, True, "Ordner"))
        p = software.plan(self.root, ["Barco Eventmaster Toolset 7.2", "System Tools", "weg.exe"])
        self.assertEqual(p.missing, ["weg.exe"])
        rels = [(k, rel) for k, rel, *_r in p.files]
        self.assertIn(("dir", "Barco Eventmaster Toolset 7.2/data"), rels)
        self.assertIn(("file", "Barco Eventmaster Toolset 7.2/data/lib.dll"), rels)
        self.assertIn(("dir", "System Tools/sub"), rels)
        self.assertLess(rels.index(("dir", "System Tools/sub")), rels.index(("file", "System Tools/sub/c.txt")))
        self.assertEqual(p.bytes, len(INNO) + 100 + len(UNKNOWN) + len(MSI) + 1)

    def test_replaced_file_detected_again(self):
        path = self.put("tool.exe", UNKNOWN)
        self.assertEqual(software.find(software.scan(self.root), "tool.exe").kind, "")
        path.write_bytes(NSIS)
        os.utime(path, (1, 1))
        self.assertEqual(software.find(software.scan(self.root), "tool.exe").kind, "nsis")

    def test_symlinks_ignored(self):
        self.put("echt.exe", NSIS)
        (self.sw / "link.exe").symlink_to(self.sw / "echt.exe")
        self.assertEqual([e.name for e in software.scan(self.root)], ["echt.exe"])

    def test_texts(self):
        self.put("vlc-3.0.24-win64.exe", NSIS)
        self.put("AcroRdrDC_de_DE.msi", MSI)
        entries = software.scan(self.root)
        self.assertEqual(software.history_text(entries),
                         "Software: AcroRdrDC de DE, VLC media player 3.0.24 (wird beim ersten Start installiert)")


class ScriptTest(unittest.TestCase):
    """Erzeugtes Installationsskript (PowerShell) und Startskript (cmd)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        sw = distribute.ensure(self.root) / "Software"
        (sw / "vlc-3.0.24-win64.exe").write_bytes(NSIS)
        (sw / "AcroRdrDC_de_DE.msi").write_bytes(MSI)
        (sw / "System Tools").mkdir()
        (sw / "System Tools/a.exe").write_bytes(UNKNOWN)
        (sw / "Barco Tool 7.2").mkdir()
        (sw / "Barco Tool 7.2/Setup.exe").write_bytes(INNO)
        software.scan(self.root)
        software.update(self.root, "System Tools", mode=software.COPY)
        software.update(self.root, "AcroRdrDC_de_DE.msi", exit_codes="0, 3010, 1641")
        self.entries = software.plan(self.root, ["vlc-3.0.24-win64.exe", "AcroRdrDC_de_DE.msi",
                                                 "Barco Tool 7.2", "System Tools"]).entries
        self.script = software.build_script(self.entries, "PC-1 „Test“", created=0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_programs_in_order_with_codes(self):
        s = self.script
        vlc = s.index("Item = 'vlc-3.0.24-win64.exe'")
        msi = s.index("Item = 'AcroRdrDC_de_DE.msi'")
        barco = s.index("Item = 'Barco Tool 7.2'")
        tools = s.index("Item = 'System Tools'")
        self.assertLess(vlc, msi)
        self.assertLess(msi, barco)
        self.assertLess(barco, tools)
        self.assertIn("Kind = 'exe'; Args = '/S'; Ok = @(0, 3010)", s)
        self.assertIn("Kind = 'msi'; Args = '/qn /norestart'; Ok = @(0, 3010, 1641)", s)
        self.assertIn("File = 'Barco Tool 7.2\\Setup.exe'; Kind = 'exe'; "
                      "Args = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-'", s)
        self.assertIn("Item = 'System Tools'; File = 'System Tools'; Kind = 'copy'", s)
        self.assertIn("'/i \"{0}\" {1}' -f $file", s)              # MSI über msiexec /i

    def test_log_cleanup_and_one_reboot(self):
        s = self.script
        self.assertIn("$OkulaLog = Join-Path $env:SystemRoot \"Temp\\$OkulaName.log\"", s)
        self.assertIn("$OkulaName = 'okula-software'", s)
        self.assertIn("Start   {0}", s)
        self.assertIn("ok      {0}: Rückgabewert {1}{2} ({3} s)", s)
        self.assertIn("FEHLER  {0}: Rückgabewert {1} ({2} s)", s)
        self.assertIn("----- Ende: {0} ok, {1} mit Fehler -----", s)
        # Fehler stoppt die übrigen nicht: jedes Programm in eigenem try/catch, Löschen im finally
        body = s[s.index("function Install-OkulaProgram"):s.index("function Install-Okula {")]
        self.assertIn("} catch {", body)
        self.assertIn("} finally {\n        Remove-Item -LiteralPath $item -Recurse -Force", body)
        self.assertIn("@(3010, 1641) -contains $code", body)
        self.assertNotIn("shutdown.exe", body)                      # kein Neustart je Programm …
        self.assertEqual(s.count("shutdown.exe /r"), 1)              # … sondern einer am Schluss
        main = s[s.index("function Install-Okula {"):s.index("function Start-Okula")]
        self.assertLess(main.index("foreach ($p in $OkulaPrograms)"), main.index("shutdown.exe /r"))
        self.assertIn("if ($script:OkulaReboot)", main)
        self.assertLess(main.index("shutdown.exe"), main.index("Unregister-ScheduledTask"))

    def test_start_mode_task_and_ten_minutes(self):
        s = self.script
        start = s[s.index("function Start-Okula"):]
        self.assertLess(start.index("Remove-Item -LiteralPath (Join-Path $OkulaStartup"),
                        start.index("Restore-OkulaStart"))
        self.assertIn("Register-ScheduledTask", start)
        self.assertIn("-UserId 'S-1-5-18'", start)                   # SYSTEM
        self.assertIn("-ExecutionTimeLimit (New-TimeSpan -Hours 12)", start)
        self.assertIn("Install-Okula", start)                        # Ausweichweg ohne Aufgabe
        self.assertLess(software.START_WAIT, 600)                    # Windows bricht Startskripte nach 600 s ab
        self.assertIn(f"$OkulaWait = {software.START_WAIT}", s)
        self.assertIn("if ($Mode -eq 'Install') { Install-Okula } else { Start-Okula }", s)
        # gemeinsamer Rückbau mit „Windows anpassen“: nur das letzte Okula-Startskript stellt her
        self.assertIn("Filter 'okula-*.cmd'", s)
        self.assertIn("$saved = $file + '.okula-nachher'", s)
        self.assertNotIn("__", s.replace("__RESTORE__", ""))          # alle Platzhalter ersetzt

    def test_balance_and_quoting(self):
        s = self.script
        self.assertEqual(s.count("{"), s.count("}"))
        self.assertEqual(s.count("("), s.count(")"))
        self.assertIn("Gerät: PC-1 Test", s)
        e = software.find(self.entries, "vlc-3.0.24-win64.exe")
        e.meta["program"] = "O'Brien"
        self.assertIn("Name = 'O''Brien 3.0.24'", software.program_line(e))

    def test_missing_parameters_refused(self):
        sw = self.root / "Verteilen/Software"
        (sw / "unbekannt.exe").write_bytes(UNKNOWN)
        entry = software.find(software.scan(self.root), "unbekannt.exe")
        with self.assertRaisesRegex(software.SoftwareError, "Parameter"):
            software.build_script([entry])
        with self.assertRaises(software.SoftwareError):
            software.build_script([])

    def test_cmd_ascii_and_guard(self):
        from okula_recovery import deploy
        cmd = deploy.SOFTWARE_CMD_TEXT
        self.assertTrue(cmd.isascii())
        self.assertIn('-File "%~dp0okula-software.ps1" -Mode Start', cmd)
        self.assertIn('if /i not "%%~nxF"=="%~nx0" set "OKULA_ANDERE=1"', cmd)
        self.assertLess(cmd.index("if defined OKULA_ANDERE goto ende"), cmd.index("gpt.ini"))
        self.assertTrue(deploy.TWEAK_CMD_TEXT.isascii())
        files = software.setup_files(self.script)
        for rel, text in files.items():
            if not rel.endswith(".ps1"):
                self.assertTrue(text.isascii(), rel)
        self.assertTrue(files["okula/gp/Machine/Scripts/Startup/okula-software.ps1"].startswith("﻿"))
        self.assertIn("0CmdLine=okula-software.cmd", files["okula/gp/Machine/Scripts/scripts.ini"])
        self.assertIn(deploy.SCRIPTS_CSE, files["okula/gp/gpt.ini"])


class SharedStartupTest(unittest.TestCase):
    """Software und „Windows anpassen“ stehen gleichzeitig aus: ein Eintrag mehr, Originale bleiben."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Windows/System32/config").mkdir(parents=True)
        (self.root / "Windows/System32/config/SYSTEM").write_bytes(b"regf")
        self.gp = self.root / "Windows/System32/GroupPolicy"

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_script_shares(self):
        from okula_recovery import deploy
        (self.gp / "Machine/Scripts").mkdir(parents=True)
        orig = b"[General]\r\nVersion=7\r\n"
        (self.gp / "gpt.ini").write_bytes(orig)
        first = deploy.install_startup_script(self.root, "A")                       # Windows anpassen
        after = (self.gp / "gpt.ini.okula-nachher").read_bytes()
        second = deploy.install_startup_script(self.root, "B", deploy.SOFTWARE_NAME, deploy.SOFTWARE_CMD_TEXT)
        self.assertEqual((first["version"], second["version"], second.get("shared")), (8, 8, True))
        self.assertEqual((self.gp / "gpt.ini.okula-nachher").read_bytes(), after)  # Original (Version +2) bleibt
        ini = (self.gp / "Machine/Scripts/scripts.ini").read_bytes()[2:].decode("utf-16-le")
        self.assertIn("0CmdLine=okula-windows-anpassen.cmd", ini)
        self.assertIn("1CmdLine=okula-software.cmd", ini)
        startup = self.gp / "Machine/Scripts/Startup"
        self.assertEqual(sorted(p.name for p in startup.iterdir()),
                         ["okula-software.cmd", "okula-software.ps1", "okula-windows-anpassen.cmd",
                          "okula-windows-anpassen.ps1"])
        # erneut senden ersetzt nur das Skript
        third = deploy.install_startup_script(self.root, "C", deploy.SOFTWARE_NAME, deploy.SOFTWARE_CMD_TEXT)
        self.assertTrue(third["replaced"])
        self.assertEqual((self.gp / "Machine/Scripts/scripts.ini").read_bytes()[2:].decode("utf-16-le"), ini)


class FakeMounts:
    def __init__(self, roots):
        self.roots = roots

    def __call__(self, write=False):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return None

    def get(self, dev):
        return self.roots[dev]


class AgentTransferTest(unittest.TestCase):
    """Tool → Agent über ein Socket-Paar: Ablage auf einer Probe-Windows-Partition (Verzeichnis)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.nas = base / "nas"
        self.win = base / "win"
        (self.win / "Windows/System32/config").mkdir(parents=True)
        (self.win / "Windows/System32/config/SYSTEM").write_bytes(b"regf")
        sw = distribute.ensure(self.nas) / "Software"
        (sw / "vlc-3.0.24-win64.exe").write_bytes(NSIS)
        (sw / "Barco Tool").mkdir()
        (sw / "Barco Tool/Setup.exe").write_bytes(INNO)
        (sw / "Barco Tool/data").mkdir()
        (sw / "Barco Tool/data/x.bin").write_bytes(b"x" * 5000)

    def tearDown(self):
        self.tmp.cleanup()

    def transfer(self, names):
        import socket
        import threading
        from unittest import mock
        from okula_recovery import agentclient, deploy, jobs
        a, b = socket.socketpair()
        errors = []

        def agent_side():
            try:
                req = deploy.wire.recv_json(b)
                deploy.software(b, req, log=lambda *_a: None)
            except Exception as e:  # im Test sichtbar machen
                errors.append(e)
                deploy.wire.send_json(b, {"type": "error", "message": str(e)})

        t = threading.Thread(target=agent_side, daemon=True)
        parts = [{"path": "/dev/sda3", "fstype": "ntfs", "size": 1 << 35}]
        lines = []
        with mock.patch.object(deploy, "_candidates", lambda disk: parts), \
                mock.patch.object(deploy.filebackup, "Mounts", FakeMounts({"/dev/sda3": self.win})), \
                mock.patch.object(deploy.subprocess, "run"), \
                mock.patch.object(agentclient, "_connect", lambda *_a: a):
            t.start()
            plan, result = jobs.send_software("127.0.0.1", b"k", 1, "/dev/sda", str(self.nas), names, "PC-1",
                                              lines.append, lambda f: None, threading.Event())
            t.join(10)
        b.close()
        self.assertEqual(errors, [])
        return plan, result, lines

    def test_files_and_startup_script_on_windows(self):
        plan, result, lines = self.transfer(["vlc-3.0.24-win64.exe", "Barco Tool"])
        target = self.win / "ProgramData/Okula/Software"
        self.assertEqual((target / "vlc-3.0.24-win64.exe").read_bytes(), NSIS)
        self.assertEqual((target / "Barco Tool/data/x.bin").read_bytes(), b"x" * 5000)
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["Barco Tool", "vlc-3.0.24-win64.exe"])
        startup = self.win / "Windows/System32/GroupPolicy/Machine/Scripts/Startup"
        ps1 = (startup / "okula-software.ps1").read_bytes()
        self.assertTrue(ps1.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Item = 'Barco Tool'".encode(), ps1)
        self.assertTrue((startup / "okula-software.cmd").read_bytes().isascii())
        self.assertEqual((result["part"], result["state"], result["files"]), ("/dev/sda3", "installed", 3))
        self.assertIn("ersten Windows-Start", "\n".join(lines))
        # zweite Auswahl ersetzt die noch nicht installierte erste
        self.transfer(["vlc-3.0.24-win64.exe"])
        self.assertEqual([p.name for p in target.iterdir()], ["vlc-3.0.24-win64.exe"])

    def test_bad_item_refused(self):
        from okula_recovery import deploy
        for bad in ("../x", "a/b", ".okula-x", "okula-software.ps1", ""):
            with self.assertRaises(deploy.ImagingError):
                deploy._software_item(bad)


class DirectInstallTest(unittest.TestCase):
    def test_install_cmd_and_setupcomplete(self):
        from okula_recovery import winsetup
        plain = winsetup.install_cmd("abcd", 1, "sources/install.wim", False, "de-DE")
        self.assertNotIn("okula\\software", plain)
        cmd = winsetup.install_cmd("abcd", 1, "sources/install.wim", False, "de-DE", software=True)
        self.assertTrue(cmd.isascii())
        self.assertIn('xcopy "%S%:\\okula\\software" "%W%:\\ProgramData\\Okula\\Software\\" /e /i /h /k /y /q', cmd)
        self.assertLess(cmd.index("okula\\software"), cmd.index("echo Okula: fertig"))
        self.assertLess(cmd.index("dism /Apply-Image"), cmd.index("okula\\software"))
        self.assertIn('copy /y "%OKGP%\\gpt.ini" "%OKGP%\\gpt.ini.okula-nachher"', cmd)
        sc = winsetup.setupcomplete_cmd("abcd", software=True)
        self.assertTrue(sc.isascii())
        self.assertLess(sc.index(":ende"), sc.index('if exist "%OKULA_SW%" cmd /c "%OKULA_SW%"'))
        self.assertNotIn("okula-software", winsetup.setupcomplete_cmd("abcd"))
        # Audit-Modus (I-038): auditUser ruft SetupComplete.cmd vor dem Löschen der Antwortdatei auf
        self.assertTrue(winsetup.AUDIT_CLEANUP.endswith('SetupComplete.cmd"'))


class AutomationSettingTest(unittest.TestCase):
    def test_selection_saved_and_in_templates(self):
        from okula_recovery import automation
        s = automation.Settings.from_dict({"install_software": ["vlc.exe", "", 3]})
        self.assertEqual(s.install_software, ["vlc.exe", "3"])
        self.assertEqual(automation.Settings.from_dict(s.to_dict()).install_software, ["vlc.exe", "3"])
        self.assertIn("install_software", automation.TEMPLATE_FIELDS)
        self.assertEqual(automation.Settings.from_dict({"install_software": "kaputt"}).install_software, [])
        self.assertEqual(automation.Settings().install_software, [])


def _gtk() -> bool:
    from tests.test_wintweaks import gtk_available
    return gtk_available()


@unittest.skipUnless(_gtk(), "braucht GTK mit Bildschirm")
class ChooserTest(unittest.TestCase):
    def test_only_ready_selectable_and_missing_shown(self):
        import time
        from gi.repository import GLib
        from okula_recovery.software_ui import SoftwareChooser
        with tempfile.TemporaryDirectory() as tmp:
            sw = distribute.ensure(tmp) / "Software"
            (sw / "vlc-3.0.24-win64.exe").write_bytes(NSIS)
            (sw / "unbekannt.exe").write_bytes(UNKNOWN)
            changes = []
            chooser = SoftwareChooser(on_change=lambda: changes.append(1))
            chooser.load(tmp, ["vlc-3.0.24-win64.exe", "unbekannt.exe", "weg.exe"])
            for _ in range(500):
                if chooser.loaded:
                    break
                GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
            self.assertTrue(chooser.loaded)
            self.assertEqual(chooser.selected(), ["vlc-3.0.24-win64.exe", "weg.exe"])   # „Parameter fehlt“ nie
            self.assertIn("Gewählt: 2 Programm(e)", chooser.total.get_text())
            self.assertTrue(changes)
            chooser.destroy()


if __name__ == "__main__":
    unittest.main()
