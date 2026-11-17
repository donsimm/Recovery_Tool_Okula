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


if __name__ == "__main__":
    unittest.main()
