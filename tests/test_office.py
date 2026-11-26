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


def parse_xml(text: str):
    import xml.etree.ElementTree as ET
    return ET.fromstring(text)


class ConfigXmlTest(unittest.TestCase):
    def test_default_business_local(self):
        root = parse_xml(software.office_config_xml(software.OfficeOptions(), r"C:\ProgramData\Okula\Software\o"))
        add = root.find("Add")
        self.assertEqual(add.attrib, {"SourcePath": r"C:\ProgramData\Okula\Software\o", "OfficeClientEdition": "64",
                                      "Channel": "Current"})
        product = add.find("Product")
        self.assertEqual(product.get("ID"), "O365BusinessRetail")
        self.assertEqual([lang.get("ID") for lang in product.findall("Language")], ["de-de"])
        self.assertEqual([x.get("ID") for x in product.findall("ExcludeApp")],
                         ["Access", "Publisher", "Lync", "OutlookForWindows", "Teams"])
        self.assertEqual(root.find("Updates").attrib, {"Enabled": "TRUE"})
        self.assertEqual(root.find("Display").attrib, {"Level": "None", "AcceptEULA": "TRUE"})
        self.assertEqual(root.find("Property").attrib, {"Name": "FORCEAPPSHUTDOWN", "Value": "TRUE"})

    def test_enterprise_word_excel_online(self):
        opts = software.OfficeOptions("O365ProPlusRetail", ("Excel", "Word"))
        text = software.office_config_xml(opts, None)
        root = parse_xml(text)
        self.assertNotIn("SourcePath", root.find("Add").attrib)             # Quelle B: lädt aus dem Internet
        self.assertEqual(root.find("Add/Product").get("ID"), "O365ProPlusRetail")
        self.assertEqual([x.get("ID") for x in root.findall("Add/Product/ExcludeApp")],
                         ["PowerPoint", "Outlook", "OneNote", "Groove", "Access", "Publisher", "Lync",
                          "OutlookForWindows", "Teams"])
        for word in ("PIDKEY", "Activation", "AUTOACTIVATE", "Key"):    # keine Schlüssel, keine Aktivierung
            self.assertNotIn(word, text)

    def test_always_excluded_even_if_asked(self):
        opts = software.OfficeOptions(apps=("Word", "Teams", "Lync", "OutlookForWindows", "OneDrive", "Unsinn"))
        self.assertEqual(opts.apps, ("Word",))                              # nur bekannte App-IDs
        ids = [x.get("ID") for x in parse_xml(software.office_config_xml(opts, None)).findall("Add/Product/ExcludeApp")]
        for always in ("Lync", "OutlookForWindows", "Teams", "Groove"):
            self.assertIn(always, ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_source_path_escaped_and_no_apps(self):
        root = parse_xml(software.office_config_xml(software.OfficeOptions(), 'C:\\A & B\\"x"'))
        self.assertEqual(root.find("Add").get("SourcePath"), 'C:\\A & B\\"x"')
        with self.assertRaisesRegex(software.SoftwareError, "keine App"):
            software.office_config_xml(software.OfficeOptions(apps=()), None)

    def test_unknown_product_falls_back(self):
        self.assertEqual(software.OfficeOptions("HomeBusiness2024Retail").product, "O365BusinessRetail")


class ChoiceTest(unittest.TestCase):
    """Optionen in der gespeicherten Auswahl (Vorlagen, Automatisierung, Gerät)."""

    def test_roundtrip(self):
        opts = software.OfficeOptions("O365ProPlusRetail", ("Word", "Excel", "Access"))
        text = software.choice_text("office-16.0.19328.20000", opts)
        self.assertEqual(text, "office-16.0.19328.20000|O365ProPlusRetail:Word,Excel,Access")
        self.assertEqual(software.split_choice(text), ("office-16.0.19328.20000", opts))
        self.assertEqual(software.split_choice("vlc-3.0.24"), ("vlc-3.0.24", None))       # alte Auswahl
        self.assertEqual(software.split_choice("office-1|Unsinn"), ("office-1", None))   # unlesbar → Vorauswahl
        self.assertEqual(software.split_choice("office-1|O365BusinessRetail:"),
                         ("office-1", software.OfficeOptions(apps=())))

    def test_resolve_plan_and_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            name = software.load(root, odt_folder(Path(tmp) / "q")).entry.name
            entries = software.scan(root)
            # alte Auswahl ohne Optionen = Vorauswahl
            [e], _m, _r = software.resolve(entries, [name])
            self.assertEqual(e.office_options, software.OfficeOptions())
            self.assertIsNone(software.find(entries, name).office)        # Bibliothek bleibt unverändert
            opts = software.OfficeOptions("O365ProPlusRetail", ("Word", "Excel"))
            p = software.plan(root, [software.choice_text(name, opts)])
            self.assertEqual(p.entries[0].office, opts)
            self.assertEqual(p.entries[0].choice, software.choice_text(name, opts))
            self.assertIn("Apps for enterprise: Word, Excel · lokal (ohne Internet)", p.lines()[0])
            self.assertIn("(Apps for enterprise: Word, Excel)", software.summary(p.entries))
            self.assertGreater(p.bytes, 4000)                             # Office\Data kommt mit aufs Gerät
            self.assertTrue(any(f[1].endswith("stream.x64.x-none.dat") for f in p.files))
            none = software.plan(root, [software.choice_text(name, software.OfficeOptions(apps=()))])
            self.assertEqual((none.entries, none.blocked), ([], [(name, "Office: keine App gewählt")]))

    def test_saved_in_automation_settings_and_template(self):
        from okula_recovery import automation
        text = software.choice_text("office-16.0.19328.20000", software.OfficeOptions(apps=("Word",)))
        s = automation.Settings.from_dict({"install_software": ["vlc-3.0.24", text]})
        again = automation.Settings.from_dict(s.to_dict())
        self.assertEqual(again.install_software, ["vlc-3.0.24", text])
        self.assertIn("install_software", automation.TEMPLATE_FIELDS)


def _gtk() -> bool:
    from tests.test_wintweaks import gtk_available
    return gtk_available()


@unittest.skipUnless(_gtk(), "braucht GTK mit Bildschirm")
class ChooserTest(unittest.TestCase):
    def test_options_shown_saved_and_loaded(self):
        import time
        from gi.repository import GLib
        from okula_recovery import software_ui

        def wait(cond):
            for _ in range(1000):
                if cond():
                    return
                GLib.MainContext.default().iteration(False)
                time.sleep(0.01)
            self.fail("Zeitüberschreitung")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nas"
            name = software.load(root, odt_folder(Path(tmp) / "q")).entry.name
            chooser = software_ui.SoftwareChooser()
            chooser.load(str(root), [name])                         # ohne Optionen gespeichert
            wait(lambda: chooser.loaded)
            self.assertTrue(chooser.office_box.get_visible())
            self.assertEqual(chooser.selected(), [software.choice_text(name, software.OfficeOptions())])
            chooser.office_product.set_active_id("O365ProPlusRetail")
            chooser.office_apps["Outlook"].set_active(False)
            chooser.office_apps["Access"].set_active(True)
            saved = chooser.selected()
            self.assertEqual(software.split_choice(saved[0])[1].apps,
                             ("Word", "Excel", "PowerPoint", "OneNote", "Groove", "Access"))
            other = software_ui.SoftwareChooser()
            other.load(str(root), saved)
            wait(lambda: other.loaded)
            self.assertEqual(other.selected(), saved)
            self.assertFalse(other.office_apps["Outlook"].get_active())
            other.load(str(root), [])
            wait(lambda: other.loaded)
            self.assertFalse(other.office_box.get_visible())        # nur sichtbar, wenn Office angehakt


if __name__ == "__main__":
    unittest.main()
