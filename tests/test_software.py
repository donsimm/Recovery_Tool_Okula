"""I-020 Software installieren und Ä-041 Software-Bibliothek: Laden, Erkennung der Installer, neue Version,
Auswahl, Aufräumen von Verteilen/Software."""

import hashlib
import json
import os
import struct
import tempfile
import threading
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
PE_OTHER = pe(body=b"another program")
PE_THIRD = pe(body=b"a third program")
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
        self.assertEqual(software.split_name("Firefox Setup 120.0.1.exe"), ("Firefox", "120.0.1", "firefox"))
        self.assertEqual(software.split_name("AraneoInstaller.exe")[:2], ("Araneo", ""))           # Ä-043
        self.assertEqual(software.split_name("PB_Installer_V10.0.0-beta.128.exe")[:2], ("PB", "10.0.0"))
        self.assertEqual(software.split_name("App 2.1.msixbundle"), ("App", "2.1", "app"))
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


class Library:
    """Probe-NAS (root) und Quell-Ordner (src) für die Software-Bibliothek (Ä-041)."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "nas"
        self.src = base / "quelle"
        self.root.mkdir()
        self.src.mkdir()
        self.lib = software.library_dir(self.root)

    def put(self, rel: str, data: bytes) -> Path:
        path = self.src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def load(self, rel: str, data: bytes | None = None, **kw) -> software.Entry:
        path = self.put(rel, data) if data is not None else self.src / rel
        return software.load(self.root, path, **kw).entry


class CountingCancel(threading.Event):
    """Abbruch nach n Abfragen (mitten im Kopieren)."""

    def __init__(self, n: int):
        super().__init__()
        self.n = n

    def is_set(self) -> bool:
        self.n -= 1
        return self.n < 0


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.l = Library()
        self.root, self.lib = self.l.root, self.l.lib

    def tearDown(self):
        self.l.tmp.cleanup()

    def test_load_file_with_description(self):
        progress = []
        res = software.load(self.root, self.l.put("vlc-3.0.24-win64.exe", NSIS), lambda *a: progress.append(a))
        vlc = res.entry
        self.assertFalse(res.duplicate)
        self.assertEqual((vlc.name, vlc.is_dir, vlc.installer), ("vlc-3.0.24", False, "vlc-3.0.24-win64.exe"))
        self.assertEqual((vlc.program, vlc.version, vlc.kind, vlc.args, vlc.status, vlc.selectable),
                         ("VLC media player", "3.0.24", "nsis", "/S", software.READY, True))
        self.assertEqual((self.lib / "vlc-3.0.24/vlc-3.0.24-win64.exe").read_bytes(), NSIS)
        meta = json.loads((self.lib / "vlc-3.0.24/.okula.json").read_text())
        self.assertEqual((meta["format"], meta["kind"], meta["args"], meta["exit_codes"], meta["size"], meta["mode"],
                          meta["installer"]),
                         ("okula-software", "nsis", "/S", [0, 3010], len(NSIS), "install", "vlc-3.0.24-win64.exe"))
        self.assertEqual(meta["sha256"], hashlib.sha256(NSIS).hexdigest())
        self.assertEqual(meta["content_sha256"], meta["sha256"])
        self.assertEqual(meta["loaded_from"], str(self.l.src / "vlc-3.0.24-win64.exe"))
        self.assertEqual(progress[-1], (len(NSIS), len(NSIS), ""))
        again = software.scan(self.root)
        self.assertEqual([(e.name, e.size, e.status) for e in again], [("vlc-3.0.24", len(NSIS), software.READY)])
        self.assertEqual(sorted(p.name for p in self.lib.iterdir()), ["vlc-3.0.24"])   # kein .partial

    def test_msi_unknown_and_not_installer(self):
        self.assertEqual(self.l.load("AcroRdrDC_de_DE.msi", MSI).status, software.READY)
        unknown = self.l.load("Unbekannt-Setup.exe", UNKNOWN)
        self.assertEqual((unknown.name, unknown.status, unknown.selectable), ("unbekannt", software.MISSING, False))
        with self.assertRaisesRegex(software.SoftwareError, "kein Installer"):
            self.l.load("Liesmich.txt", b"kein Installer")
        with self.assertRaises(software.SoftwareError):
            software.inspect(self.lib / "unbekannt", self.root)   # liegt schon in der Bibliothek

    def test_duplicate_by_sha256(self):
        first = self.l.load("vlc-3.0.24-win64.exe", NSIS)
        res = software.load(self.root, self.l.put("anders/vlc-kopie.exe", NSIS))
        self.assertTrue(res.duplicate)
        self.assertEqual(res.entry.name, first.name)
        self.assertEqual(sorted(p.name for p in self.lib.iterdir()), ["vlc-3.0.24"])
        # Ordner: gleicher Inhalt → Doppel, andere Datei im Ordner → neuer Eintrag
        self.l.put("Tool 1.0/setup.exe", INNO)
        self.assertFalse(software.load(self.root, self.l.src / "Tool 1.0").duplicate)
        self.assertTrue(software.load(self.root, self.l.src / "Tool 1.0").duplicate)
        self.l.put("Tool 1.0/liesmich.txt", b"neu")
        self.assertFalse(software.load(self.root, self.l.src / "Tool 1.0").duplicate)
        self.assertEqual(sorted(p.name for p in self.lib.iterdir()), ["tool-1.0", "tool-1.0-2", "vlc-3.0.24"])

    def test_same_name_other_content_gets_own_entry(self):
        self.l.load("tool-1.0.exe", UNKNOWN)
        other = self.l.load("b/tool-1.0.exe", INNO)
        self.assertEqual(other.name, "tool-1.0-2")
        self.assertEqual(software.find(software.scan(self.root), "tool-1.0").kind, "")

    def test_cancel_leaves_nothing(self):
        self.l.put("Gross/setup.exe", INNO)
        self.l.put("Gross/daten.bin", b"x" * 1000)
        for n in (0, 1, 2):
            with self.subTest(n=n), self.assertRaisesRegex(software.SoftwareError, "Abgebrochen"):
                software.load(self.root, self.l.src / "Gross", cancel=CountingCancel(n))
            self.assertEqual(list(self.lib.iterdir()), [])
        self.assertEqual(software.scan(self.root), [])

    def test_folder_installer_unique_choice_and_copy(self):
        self.l.put("YSUSB_V213_Win/setup.exe", INNO)
        self.l.put("YSUSB_V213_Win/driver/ysusb.sys", b"x" * 100)
        yamaha = software.load(self.root, self.l.src / "YSUSB_V213_Win").entry
        self.assertEqual((yamaha.is_dir, yamaha.installer, yamaha.kind, yamaha.status, yamaha.size),
                         (True, "setup.exe", "inno", software.READY, len(INNO) + 100))
        self.assertEqual((self.lib / yamaha.name / "driver/ysusb.sys").read_bytes(), b"x" * 100)
        self.l.put("System Tools/a.exe", UNKNOWN)
        self.l.put("System Tools/b.msi", MSI)
        self.l.put("System Tools/sub/c.txt", b"c")
        src = software.inspect(self.l.src / "System Tools")
        self.assertEqual((src.candidates, src.installer, src.bytes), (["a.exe", "b.msi"], "",
                                                                      len(UNKNOWN) + len(MSI) + 1))
        with self.assertRaises(software.SoftwareError):
            software.load(self.root, src, installer="gibtsnicht.exe")
        tools = software.load(self.root, src).entry          # nicht eindeutig, keiner gewählt
        self.assertEqual((tools.name, tools.status), ("system-tools", software.MISSING))
        self.assertIn("Installer im Ordner wählen", tools.note)
        chosen = software.update(self.root, "system-tools", installer="b.msi")
        self.assertEqual((chosen.kind, chosen.status), ("msi", software.READY))
        copy = software.update(self.root, "system-tools", mode=software.COPY)
        self.assertEqual((copy.status, copy.selectable, copy.kind_label), (software.COPY_ONLY, True, "Ordner"))
        p = software.plan(self.root, [yamaha.name, "system-tools", "weg.exe"])
        self.assertEqual(p.missing, ["weg.exe"])
        rels = [(k, rel) for k, rel, *_r in p.files]
        self.assertIn(("dir", f"{yamaha.name}/driver"), rels)
        self.assertIn(("file", f"{yamaha.name}/driver/ysusb.sys"), rels)
        self.assertIn(("dir", "system-tools/sub"), rels)
        self.assertLess(rels.index(("dir", "system-tools/sub")), rels.index(("file", "system-tools/sub/c.txt")))
        self.assertFalse(any(r.endswith(".okula.json") for _k, r in rels))       # Beschreibung bleibt auf dem NAS
        self.assertEqual(p.bytes, len(INNO) + 100 + len(UNKNOWN) + len(MSI) + 1)

    def test_folder_with_chosen_installer(self):
        self.l.put("Sammlung/a.exe", UNKNOWN)
        self.l.put("Sammlung/b.msi", MSI)
        entry = software.load(self.root, self.l.src / "Sammlung", installer="b.msi").entry
        self.assertEqual((entry.installer, entry.kind, entry.status), ("b.msi", "msi", software.READY))

    def test_missing_parameters_become_selectable_after_edit(self):
        name = self.l.load("Unbekannt-Setup.exe", UNKNOWN).name
        plan = software.plan(self.root, [name])
        self.assertEqual((plan.entries, plan.blocked), ([], [(name, software.MISSING)]))
        entry = software.update(self.root, name, args="/silent", exit_codes="0, 3010, 1641", program="Tool X",
                                version="2.0")
        self.assertEqual((entry.status, entry.exit_codes, entry.label), (software.READY, [0, 3010, 1641], "Tool X 2.0"))
        again = software.find(software.scan(self.root), name)
        self.assertEqual((again.args, again.meta["edited"]), ("/silent", True))
        self.assertEqual(software.plan(self.root, [name]).names, [name])
        software.update(self.root, name, mode=software.MANUAL)
        hand = software.find(software.scan(self.root), name)
        self.assertEqual((hand.status, hand.selectable), (software.HAND, False))
        with self.assertRaises(software.SoftwareError):
            software.update(self.root, name, mode=software.COPY)   # nur Ordner
        with self.assertRaises(software.SoftwareError):
            software.update(self.root, "gibtsnicht", args="/S")

    def test_new_version_adopts_parameters_old_stays(self):
        old = self.l.load("vlc-3.0.23-win64.exe", UNKNOWN)
        software.update(self.root, old.name, args="/S /L=1031", exit_codes="0")
        new = self.l.load("vlc-3.0.24-win64.exe", NSIS)
        self.assertEqual((new.name, new.args, new.exit_codes, new.adopted_from),
                         ("vlc-3.0.24", "/S /L=1031", [0], "vlc-3.0.23"))
        self.assertIn("übernommen", new.note)
        self.assertEqual(new.status, software.READY)
        self.assertEqual([e.name for e in software.scan(self.root)], ["vlc-3.0.23", "vlc-3.0.24"])   # alte bleibt
        # alte gelöscht: gespeicherte Auswahl (Automatisierung) nimmt über den key die neue Version
        software.delete(self.root, "vlc-3.0.23")
        p = software.plan(self.root, ["vlc-3.0.23"])
        self.assertEqual((p.names, p.renamed), (["vlc-3.0.24"], [("vlc-3.0.23", "vlc-3.0.24")]))

    def test_info_saved_and_read(self):
        """Ä-050: freier Text „Info“ – mehrzeilig, getrennt vom automatischen Hinweis (note)."""
        name = self.l.load("vlc-3.0.24-win64.exe", NSIS).name
        entry = software.update(self.root, name, info="  Lizenz im Tresor\r\nnur für Lenovo-Modelle\x07  ")
        self.assertEqual(entry.info, "Lizenz im Tresor\nnur für Lenovo-Modelle")
        again = software.find(software.scan(self.root), name)
        self.assertEqual(again.info, "Lizenz im Tresor\nnur für Lenovo-Modelle")
        meta = json.loads((self.lib / name / ".okula.json").read_text())
        self.assertEqual(meta["info"], "Lizenz im Tresor\nnur für Lenovo-Modelle")
        self.assertFalse(meta["edited"])                     # nur Info → keine Rückfrage bei „Neu erkennen“
        self.assertNotIn("Tresor", again.note)
        self.assertEqual(software.first_line(again.info), "Lizenz im Tresor …")
        self.assertEqual(software.first_line("eine Zeile"), "eine Zeile")
        # Neu erkennen lässt die Info stehen
        self.assertEqual(software.redetect(self.root, name).info, "Lizenz im Tresor\nnur für Lenovo-Modelle")
        self.assertEqual(software.update(self.root, name, info="").info, "")
        # Parameter von Hand → edited wie bisher
        self.assertTrue(software.update(self.root, name, args="/S", info="x").meta["edited"])

    def test_info_length_limit(self):
        name = self.l.load("vlc-3.0.24-win64.exe", NSIS).name
        ok = "x" * software.MAX_INFO
        self.assertEqual(software.update(self.root, name, info=ok).info, ok)
        with self.assertRaisesRegex(software.SoftwareError, "Info zu lang"):
            software.update(self.root, name, info=ok + "y")
        self.assertEqual(software.find(software.scan(self.root), name).info, ok)   # nichts überschrieben

    def test_info_adopted_by_new_version(self):
        old = self.l.load("vlc-3.0.23-win64.exe", UNKNOWN)
        software.update(self.root, old.name, args="/S", info="vor Office installieren")
        new = self.l.load("vlc-3.0.24-win64.exe", NSIS)
        self.assertEqual((new.adopted_from, new.info), ("vlc-3.0.23", "vor Office installieren"))
        # vorige Version ohne Parameter: Info kommt trotzdem mit, Parameter nicht
        tool = self.l.load("tool-1.0.exe", PE_OTHER)
        self.assertEqual(tool.name, "tool-1.0")
        software.update(self.root, tool.name, info="nur Lenovo")
        newer = self.l.load("b/tool-1.1.exe", PE_OTHER + b" 1.1")
        self.assertEqual((newer.info, newer.args, newer.adopted_from), ("nur Lenovo", "", ""))
        self.assertEqual(self.l.load("7z2301-x64.exe", PE_THIRD).info, "")      # anderes Programm

    def test_info_found_by_search(self):
        name = self.l.load("vlc-3.0.24-win64.exe", NSIS).name
        entry = software.update(self.root, name, info="Lizenz im Tresor")
        self.assertIn("tresor", entry.search_text)
        self.assertIn("vlc media player", entry.search_text)
        self.assertNotIn("tresor", software.find(software.scan(self.root), name).note.lower())

    def test_saved_selection_resolved_by_key(self):
        self.l.load("vlc-3.0.24-win64.exe", NSIS)
        self.l.put("System Tools/a.exe", UNKNOWN)
        software.load(self.root, self.l.src / "System Tools")
        # Namen aus der Zeit von Verteilen\Software (I-020) und ein gelöschter Eintrag
        chosen, missing, renamed = software.resolve(software.scan(self.root),
                                                    ["vlc-3.0.23-win64.exe", "System Tools", "setup.exe", "weg.exe"])
        self.assertEqual([e.name for e in chosen], ["vlc-3.0.24", "system-tools"])
        self.assertEqual(missing, ["setup.exe", "weg.exe"])        # nicht still übersprungen, sondern gemeldet
        self.assertEqual(renamed, [("vlc-3.0.23-win64.exe", "vlc-3.0.24"), ("System Tools", "system-tools")])
        p = software.plan(self.root, ["weg.exe"])
        self.assertEqual(p.missing, ["weg.exe"])
        self.assertIn("weg.exe: fehlt in der Software-Bibliothek – übersprungen", p.lines())

    def test_unrelated_program_not_adopted(self):
        old = self.l.load("vlc-3.0.23-win64.exe", UNKNOWN)
        software.update(self.root, old.name, args="/S")
        self.assertEqual(self.l.load("setup.exe", PE_OTHER).status, software.MISSING)
        self.assertEqual(self.l.load("7z2301-x64.exe", PE_THIRD).args, "")

    def test_catalog_reads_only_library(self):
        sw = distribute.ensure(self.root) / "Software"
        (sw / "vlc-3.0.24-win64.exe").write_bytes(NSIS)
        (sw / "Tool").mkdir()
        (sw / "Tool/setup.exe").write_bytes(INNO)
        self.assertEqual(software.scan(self.root), [])
        self.assertEqual(sorted(p.name for p in sw.iterdir()), ["Tool", "vlc-3.0.24-win64.exe"])   # nichts angelegt
        self.assertEqual(software.plan(self.root, ["vlc-3.0.24-win64.exe"]).missing, ["vlc-3.0.24-win64.exe"])
        # aus Verteilen\Software laden geht (Kopie), der Ordner bleibt unverändert
        entry = software.load(self.root, sw / "vlc-3.0.24-win64.exe").entry
        self.assertEqual(entry.path.parent, self.lib)
        self.assertEqual(sorted(p.name for p in sw.iterdir()), ["Tool", "vlc-3.0.24-win64.exe"])

    def test_cleanup_distribute_only_i020_descriptions(self):
        sw = distribute.ensure(self.root) / "Software"
        i020 = {"format": "okula-software", "version": 1, "program": "VLC"}
        (sw / ".vlc.exe.okula.json").write_text(json.dumps(i020))
        (sw / ".OBS & plugin.okula.json").write_text(json.dumps(i020))
        (sw / ".fremd.okula.json").write_text(json.dumps({"format": "okula-os"}))
        (sw / ".kaputt.okula.json").write_text("{kein json")
        (sw / ".vlc.exe.okula.json.tmp").write_text(json.dumps(i020))
        (sw / "vlc.exe").write_bytes(NSIS)
        (sw / "Ordner").mkdir()
        (sw / "Ordner/.innen.okula.json").write_text(json.dumps(i020))
        (sw / ".link.okula.json").symlink_to(sw / ".fremd.okula.json")
        removed = software.cleanup_distribute(self.root)
        self.assertEqual(removed, [".OBS & plugin.okula.json", ".vlc.exe.okula.json"])
        self.assertEqual(sorted(p.name for p in sw.iterdir()),
                         [".fremd.okula.json", ".kaputt.okula.json", ".link.okula.json", ".vlc.exe.okula.json.tmp",
                          "Ordner", "vlc.exe"])
        self.assertTrue((sw / "Ordner/.innen.okula.json").exists())
        self.assertEqual(software.cleanup_distribute(self.root), [])
        self.assertEqual(software.cleanup_distribute(self.root / "gibtsnicht"), [])

    def test_delete(self):
        name = self.l.load("vlc-3.0.24-win64.exe", NSIS).name
        software.delete(self.root, name)
        self.assertEqual(list(self.lib.iterdir()), [])
        for bad in ("", "..", "../nas", ".x", "a/b", "gibtsnicht"):
            with self.subTest(bad=bad), self.assertRaises(software.SoftwareError):
                software.delete(self.root, bad)

    def test_hand_copied_folder_and_partial(self):
        (self.lib / "Manuell 1.0").mkdir(parents=True)
        (self.lib / "Manuell 1.0/setup.exe").write_bytes(INNO)
        (self.lib / ".abc.partial").mkdir()
        (self.lib / ".abc.partial/x.exe").write_bytes(NSIS)
        (self.lib / "lose.exe").write_bytes(NSIS)
        entries = software.scan(self.root)
        self.assertEqual([(e.name, e.kind, e.status) for e in entries], [("Manuell 1.0", "inno", software.READY)])
        self.assertTrue((self.lib / "Manuell 1.0/.okula.json").is_file())
        self.assertEqual(software.cleanup_partial(self.root), 0)              # zu jung – Laden läuft evtl. noch
        self.assertEqual(software.cleanup_partial(self.root, older_than=-1), 1)
        self.assertFalse((self.lib / ".abc.partial").exists())

    def test_symlinks_ignored(self):
        self.assertEqual(self.l.load("echt.exe", NSIS).name, "echt-3.0.24")      # Version aus der Versionsinfo
        (self.lib / "link").symlink_to(self.lib / "echt-3.0.24")
        self.assertEqual([e.name for e in software.scan(self.root)], ["echt-3.0.24"])
        self.l.put("Mit Link/setup.exe", INNO)
        (self.l.src / "Mit Link/link.exe").symlink_to(self.l.src / "echt.exe")
        src = software.inspect(self.l.src / "Mit Link")
        self.assertEqual((src.candidates, src.skipped), (["setup.exe"], ["link.exe"]))

    def test_texts(self):
        self.l.load("vlc-3.0.24-win64.exe", NSIS)
        self.l.load("AcroRdrDC_de_DE.msi", MSI)
        entries = software.scan(self.root)
        self.assertEqual(software.history_text(entries),
                         "Software: AcroRdrDC de DE, VLC media player 3.0.24 (wird beim ersten Start installiert)")


class DemoLibraryTest(unittest.TestCase):
    def test_demo_library_without_nas(self):
        from unittest import mock
        from okula_recovery import demostore
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            old = Path(tmp) / "okula-recovery/demo/Verteilen/Software"
            old.mkdir(parents=True)
            (old / "vlc-3.0.24-win64.exe").write_bytes(demostore.DEMO_INSTALLERS["vlc-3.0.24-win64.exe"])
            (old / ".vlc-3.0.24-win64.exe.okula.json").write_text(json.dumps({"format": "okula-software"}))
            root = demostore.ensure()
            entries = {e.name: e.status for e in software.scan(root)}
            self.assertEqual(entries, {"vlc-3.0.24": software.READY, "acrordrdc-de-de": software.READY,
                                       "demo-tool": software.MISSING})
            self.assertEqual(sorted(p.name for p in old.iterdir()), ["Demo-Installer.txt"])
            vlc = software.find(software.scan(root), "vlc-3.0.24")
            self.assertEqual(vlc.info, demostore.DEMO_INFO["vlc-3.0.24-win64.exe"])     # Ä-050
            demostore.ensure()                                        # zweites Mal: nichts doppelt
            self.assertEqual(len(software.scan(root)), 3)


class ScriptTest(unittest.TestCase):
    """Erzeugtes Installationsskript (PowerShell) und Startskript (cmd)."""

    def setUp(self):
        self.l = Library()
        self.root = self.l.root
        self.l.load("vlc-3.0.24-win64.exe", NSIS)
        self.l.load("AcroRdrDC_de_DE.msi", MSI)
        self.l.put("System Tools/a.exe", UNKNOWN)
        self.l.load("System Tools")
        self.l.put("Barco Tool 7.2/Setup.exe", INNO)
        self.l.load("Barco Tool 7.2")
        software.update(self.root, "system-tools", mode=software.COPY)
        software.update(self.root, "acrordrdc-de-de", exit_codes="0, 3010, 1641")
        self.entries = software.plan(self.root, ["vlc-3.0.24", "acrordrdc-de-de", "barco-tool-7.2",
                                                 "system-tools"]).entries
        self.script = software.build_script(self.entries, "PC-1 „Test“", created=0)

    def tearDown(self):
        self.l.tmp.cleanup()

    def test_programs_in_order_with_codes(self):
        s = self.script
        vlc = s.index("Item = 'vlc-3.0.24'")
        msi = s.index("Item = 'acrordrdc-de-de'")
        barco = s.index("Item = 'barco-tool-7.2'")
        tools = s.index("Item = 'system-tools'")
        self.assertLess(vlc, msi)
        self.assertLess(msi, barco)
        self.assertLess(barco, tools)
        self.assertIn("File = 'vlc-3.0.24\\vlc-3.0.24-win64.exe'; Kind = 'exe'; Args = '/S'; Ok = @(0, 3010)", s)
        self.assertIn("File = 'acrordrdc-de-de\\AcroRdrDC_de_DE.msi'; Kind = 'msi'; Args = '/qn /norestart'; "
                      "Ok = @(0, 3010, 1641)", s)
        self.assertIn("File = 'barco-tool-7.2\\Setup.exe'; Kind = 'exe'; "
                      "Args = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-'", s)
        self.assertIn("Item = 'system-tools'; File = 'system-tools'; Kind = 'copy'", s)
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

    def test_missing_files_count_as_error(self):
        """B-028 (R-win 2): fehlende Installer = FEHLER, „schon installiert“ nur mit ok-Eintrag im Protokoll."""
        body = self.script[self.script.index("function Install-OkulaProgram"):
                           self.script.index("function Install-Okula {")]
        missing = body[body.index("if (-not (Test-Path -LiteralPath $item)) {"):body.index("$t0 = Get-Date")]
        self.assertIn("if (Test-OkulaDone $P.Name) {", missing)
        self.assertIn("schon installiert (ok weiter oben im Protokoll) – übersprungen", missing)
        self.assertIn("$script:OkulaFailed++", missing)
        self.assertIn("FEHLER  {0}: Dateien fehlen ({1}) – nicht installiert", missing)
        self.assertLess(missing.index("Test-OkulaDone"), missing.index("$script:OkulaFailed++"))
        self.assertNotIn("schon erledigt?", self.script)
        done = self.script[self.script.index("function Test-OkulaDone"):self.script.index("function Install-OkulaProgram")]
        self.assertIn("$needle = '  ok      {0}:' -f $Name", done)          # genau die ok-Zeile dieses Programms
        self.assertIn("Select-String -LiteralPath $OkulaLog -SimpleMatch -Pattern $needle", done)

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
        e = software.find(self.entries, "vlc-3.0.24")
        e.meta["program"] = "O'Brien"
        self.assertIn("Name = 'O''Brien 3.0.24'", software.program_line(e))

    def test_missing_parameters_refused(self):
        entry = self.l.load("unbekannt.exe", PE_OTHER)
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
        self.nas.mkdir()
        src = base / "quelle"
        (src / "Barco Tool/data").mkdir(parents=True)
        (src / "vlc-3.0.24-win64.exe").write_bytes(NSIS)
        (src / "Barco Tool/Setup.exe").write_bytes(INNO)
        (src / "Barco Tool/data/x.bin").write_bytes(b"x" * 5000)
        software.load(self.nas, src / "vlc-3.0.24-win64.exe")
        software.load(self.nas, src / "Barco Tool")

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
        plan, result, lines = self.transfer(["vlc-3.0.24", "barco-tool"])
        target = self.win / "ProgramData/Okula/Software"
        self.assertEqual((target / "vlc-3.0.24/vlc-3.0.24-win64.exe").read_bytes(), NSIS)
        self.assertEqual((target / "barco-tool/data/x.bin").read_bytes(), b"x" * 5000)
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["barco-tool", "vlc-3.0.24"])
        self.assertFalse((target / "vlc-3.0.24/.okula.json").exists())      # Beschreibung bleibt auf dem NAS
        startup = self.win / "Windows/System32/GroupPolicy/Machine/Scripts/Startup"
        ps1 = (startup / "okula-software.ps1").read_bytes()
        self.assertTrue(ps1.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Item = 'barco-tool'".encode(), ps1)
        self.assertIn("File = 'vlc-3.0.24\\vlc-3.0.24-win64.exe'".encode(), ps1)
        self.assertTrue((startup / "okula-software.cmd").read_bytes().isascii())
        self.assertEqual((result["part"], result["state"], result["files"]), ("/dev/sda3", "installed", 3))
        self.assertIn("ersten Windows-Start", "\n".join(lines))
        # zweite Auswahl ersetzt die noch nicht installierte erste
        self.transfer(["vlc-3.0.24"])
        self.assertEqual([p.name for p in target.iterdir()], ["vlc-3.0.24"])

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
        lib = Library()
        with lib.tmp:
            lib.load("vlc-3.0.24-win64.exe", NSIS)
            lib.load("unbekannt.exe", UNKNOWN)
            tmp = str(lib.root)
            changes = []
            chooser = SoftwareChooser(on_change=lambda: changes.append(1))
            chooser.load(tmp, ["vlc-3.0.24", "unbekannt", "weg.exe"])
            for _ in range(500):
                if chooser.loaded:
                    break
                GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
            self.assertTrue(chooser.loaded)
            self.assertEqual(chooser.selected(), ["vlc-3.0.24", "weg.exe"])   # „Parameter fehlt“ nie
            self.assertIn("Gewählt: 2 Programm(e)", chooser.total.get_text())
            self.assertTrue(changes)
            chooser.destroy()

    def test_library_window_load_edit_delete(self):
        import time
        from unittest import mock
        from gi.repository import GLib
        from okula_recovery import software_ui
        from okula_recovery.software_ui import SoftwareLibraryWindow

        def wait(cond):
            for _ in range(1000):
                if cond():
                    return
                GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
            self.fail("Zeitüberschreitung")

        lib = Library()
        with lib.tmp:
            win = SoftwareLibraryWindow(None, str(lib.root))
            wait(lambda: "Noch keine Programme" in win.status.get_text())
            win.enqueue([str(lib.put("vlc-3.0.24-win64.exe", NSIS)), str(lib.put("unbekannt.exe", UNKNOWN))])
            wait(lambda: not win.running and len(win.store) == 2 and "Einträge" in win.status.get_text())
            self.assertEqual(sorted(row[win.C_NAME] for row in win.store), ["unbekannt", "vlc-3.0.24"])
            # Meldung bleibt nach dem Neulesen vor der Zählung stehen
            self.assertIn("geladen:", win.status.get_text())
            self.assertIn("2 Einträge", win.status.get_text())
            win.enqueue([str(lib.src / "vlc-3.0.24-win64.exe")])               # Doppel
            wait(lambda: not win.running and "Einträge" in win.status.get_text()
                 and "schon in der Bibliothek" in win.status.get_text())
            path = next(str(row.path) for row in win.sorted if row[win.C_NAME] == "unbekannt")
            win._on_edited(None, path, "/S", "args")
            wait(lambda: software.find(software.scan(lib.root), "unbekannt").args == "/S")
            wait(lambda: any(r[win.C_NAME] == "unbekannt" and r[win.C_STATUS] == software.READY for r in win.store))
            # Ä-050: Info in der Zeile (einzeilig), Suche, mehrzeilig nicht in der Zeile bearbeitbar
            self.assertEqual([c.get_title() for c in win.view.get_columns()][:2], ["Programm", "Info"])
            path = next(str(row.path) for row in win.sorted if row[win.C_NAME] == "unbekannt")
            win._on_edited(None, path, "Lizenz im Tresor", "info")
            wait(lambda: any(r[win.C_NAME] == "unbekannt" and r[win.C_INFO] == "Lizenz im Tresor" for r in win.store))
            win.search.set_text("tresor")
            win.filter.refilter()
            self.assertEqual([r[win.C_NAME] for r in win.filter], ["unbekannt"])
            win.search.set_text("")
            win.filter.refilter()
            software.update(lib.root, "unbekannt", info="Zeile 1\nZeile 2")
            win.reload(select="unbekannt")
            wait(lambda: any(r[win.C_INFO] == "Zeile 1 …" for r in win.store))
            row = next(r for r in win.store if r[win.C_NAME] == "unbekannt")
            self.assertFalse(row[win.C_INFO_EDIT])
            self.assertIn("Zeile 2", row[win.C_TIP])
            entry = software.find(software.scan(lib.root), "unbekannt")
            dlg = software_ui.SoftwareEditDialog(win, entry, software_ui.SoftwareEditDialog.PAGE_INFO)
            self.assertEqual([dlg.notebook.get_tab_label_text(dlg.notebook.get_nth_page(i)) for i in range(2)],
                             ["Angaben", "Info"])
            self.assertEqual(dlg.notebook.get_current_page(), 1)
            self.assertEqual(dlg.values()["info"], "Zeile 1\nZeile 2")
            dlg.destroy()
            win._select("unbekannt")
            with mock.patch.object(software_ui, "confirm", lambda *_a, **_k: True):
                win.on_delete()
            wait(lambda: len(win.store) == 1 and "1 Einträge" in win.status.get_text())
            self.assertIn("gelöscht", win.status.get_text())
            win.destroy()


class UiSourceTest(unittest.TestCase):
    def test_no_catalog_in_files_tab(self):
        """Keine zwei Orte: der Knopf „Software …“ im Reiter Dateien ist ersetzt durch Extras → Software-Bibliothek."""
        src = (Path(__file__).resolve().parent.parent / "okula_recovery/ui.py").read_text(encoding="utf-8")
        self.assertNotIn('"Software …"', src)
        self.assertNotIn("SoftwareCatalogDialog", src)
        self.assertIn('"_Software-Bibliothek …": (self.open_software_library', src)
        self.assertIn("cleanup_software_folder", src)


if __name__ == "__main__":
    unittest.main()
