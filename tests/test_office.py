"""I-042: Office (Microsoft 365 Apps, Click-to-Run) – Erkennung des ODT-Ordners (Quelle A mit Office\\Data, Quelle B
nur setup.exe), fremde setup.exe nicht als Office."""

import tempfile
import unittest
from pathlib import Path

from okula_recovery import software
from tests.test_installerinfo import pe_file, version_resource

ODT_INFO = {"CompanyName": "Microsoft Corporation", "ProductName": "Microsoft Office",
            "FileDescription": "Microsoft Office Click-to-Run Bootstrapper", "ProductVersion": "16.0.18925.20076"}
DOWNLOAD_XML = ('<Configuration><Add OfficeClientEdition="64" Channel="Current"><Product ID="O365BusinessRetail">'
                '<Language ID="de-de"/></Product></Add></Configuration>')


def odt_exe(info: dict | None = None) -> bytes:
    return pe_file(body=b"setup", resources={16: version_resource(info or ODT_INFO)})


def odt_folder(base: Path, version: str = "16.0.19328.20000", data: bool = True, info: dict | None = None,
               name: str = "Office") -> Path:
    """Ordner wie nach „setup.exe /download download.xml“ (Quelle A) bzw. ohne Office\\Data (Quelle B)."""
    folder = base / name
    folder.mkdir(parents=True)
    (folder / "setup.exe").write_bytes(odt_exe(info))
    (folder / "download.xml").write_text(DOWNLOAD_XML)
    if data:
        d = folder / "Office" / "Data"
        (d / version).mkdir(parents=True)
        (d / f"v64_{version}.cab").write_bytes(b"cab")
        (d / "v64.cab").write_bytes(b"cab")
        (d / version / "stream.x64.x-none.dat").write_bytes(b"x" * 4000)
        (d / version / "stream.x64.de-de.dat").write_bytes(b"d" * 1000)
    return folder


class DetectTest(unittest.TestCase):
    def test_kind_in_kinds(self):
        label, args, codes, hint = software.KINDS[software.OFFICE]
        self.assertEqual(label, "Office (Microsoft 365 Apps)")
        self.assertIn("/configure", args)
        self.assertIn(software.OFFICE_XML, args)
        self.assertEqual(codes, (0,))

    def test_source_a_folder_with_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            src = odt_folder(Path(tmp) / "q")
            e = software.load(root, src).entry
            self.assertEqual((e.kind, e.program, e.version, e.publisher, e.status),
                             (software.OFFICE, "Microsoft 365 Apps", "16.0.19328.20000", "Microsoft", software.READY))
            self.assertEqual(e.name, "office-16.0.19328.20000")
            self.assertEqual((e.key, e.installer, e.kind_label, e.info), ("office", "setup.exe", "Office", ""))
            self.assertTrue(e.is_office and e.office_local and e.selectable)
            self.assertIn("lokal, Version 16.0.19328.20000", e.note)
            self.assertTrue(e.office_note.startswith("Quelle: lokal"))
            self.assertIn("kB", e.office_note)                    # Grösse des Eintrags (hier klein)
            self.assertEqual(e.hint, "")

    def test_source_b_setup_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            src = Path(tmp) / "q" / "setup.exe"
            src.parent.mkdir()
            src.write_bytes(odt_exe())
            e = software.load(root, src).entry                    # „Ins Tool laden …“ nur setup.exe
            self.assertEqual((e.kind, e.status, e.version, e.office_local), (software.OFFICE, software.READY, "",
                                                                             False))
            self.assertIn("lädt beim Installieren aus dem Internet", e.note)
            folder = odt_folder(Path(tmp) / "q2", data=False)    # Ordner ohne Office\Data
            f = software.load(root, folder).entry
            self.assertEqual((f.kind, f.office_local), (software.OFFICE, False))

    def test_office_word_with_data_or_xml_suffices(self):
        info = {"CompanyName": "Microsoft Corporation", "ProductName": "Microsoft Office"}
        with tempfile.TemporaryDirectory() as tmp:
            a = odt_folder(Path(tmp) / "a", info=info)
            self.assertEqual(software.office_detect(a / "setup.exe")["source"], software.OFFICE_LOCAL)
            b = odt_folder(Path(tmp) / "b", info=info, data=False)          # download.xml daneben
            self.assertEqual(software.office_detect(b / "setup.exe")["source"], software.OFFICE_ONLINE)
            (b / "download.xml").unlink()
            self.assertIsNone(software.office_detect(b / "setup.exe"))     # Zweifel → nicht Office

    def test_foreign_setup_not_office(self):
        cases = {
            "Hersteller nicht Microsoft": {"CompanyName": "Okula AG", "ProductName": "Office Click-to-Run Probe"},
            "Visual Studio": {"CompanyName": "Microsoft Corporation", "ProductName": "Visual Studio Installer",
                              "FileDescription": "Bootstrapper"},
            "Office-MSI (2016)": {"CompanyName": "Microsoft Corporation", "ProductName": "Microsoft Office 2016"},
            "ohne Versionsinfo": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            for i, (what, info) in enumerate(cases.items()):
                with self.subTest(what=what):
                    folder = Path(tmp) / str(i)
                    folder.mkdir()
                    (folder / "setup.exe").write_bytes(pe_file(body=b"x", resources={16: version_resource(info)})
                                                       if info else pe_file(body=b"x"))
                    (folder / "proplus.ww").mkdir()
                    (folder / "config.xml").write_text('<Configuration Product="ProPlus"/>')
                    self.assertIsNone(software.office_detect(folder / "setup.exe"))
                    e = software.load(Path(tmp) / "nas", folder).entry
                    self.assertNotEqual(e.kind, software.OFFICE)
            # ODT-Kennung, aber Datei heisst anders (z. B. officedeploymenttool_….exe zum Entpacken)
            other = Path(tmp) / "officedeploymenttool_18925-20076.exe"
            other.write_bytes(odt_exe())
            self.assertIsNone(software.office_detect(other))

    def test_new_version_replaces_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            old = software.load(root, odt_folder(Path(tmp) / "q1")).entry
            new = software.load(root, odt_folder(Path(tmp) / "q2", version="16.0.19428.20120")).entry
            self.assertEqual(new.name, "office-16.0.19428.20120")
            self.assertEqual(new.adopted_from, "")                # feste Parameter, nichts übernommen
            entries = software.scan(root)
            self.assertEqual(len(entries), 2)                    # alte bleibt bis zum Löschen
            software.delete(root, old.name)
            chosen, missing, renamed = software.resolve(software.scan(root), [old.name])
            self.assertEqual(([e.name for e in chosen], missing, renamed),
                             ([new.name], [], [(old.name, new.name)]))

    def test_info_goes_to_new_version_and_redetect_keeps_office(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            old = software.load(root, odt_folder(Path(tmp) / "q1")).entry
            software.update(root, old.name, info="Lizenz: Mieter")
            new = software.load(root, odt_folder(Path(tmp) / "q2", version="16.0.19428.20120")).entry
            self.assertEqual(new.info, "Lizenz: Mieter")
            again = software.redetect(root, new.name)
            self.assertEqual((again.kind, again.key, again.version, again.status),
                             (software.OFFICE, "office", "16.0.19428.20120", software.READY))

    def test_several_data_versions_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = odt_folder(Path(tmp) / "q")
            (folder / "Office" / "Data" / "16.0.19500.20000").mkdir()
            (folder / "Office" / "Data" / "16.0.19500.20000" / "stream.x64.x-none.dat").write_bytes(b"n")
            (folder / "Office" / "Data" / "keine-version").mkdir()
            self.assertEqual(software.office_data_versions(folder), ["16.0.19328.20000", "16.0.19500.20000"])
            e = software.load(Path(tmp) / "nas", folder).entry
            self.assertEqual(e.version, "16.0.19500.20000")


if __name__ == "__main__":
    unittest.main()
