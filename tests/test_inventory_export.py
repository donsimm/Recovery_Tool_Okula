"""Inventar-Export (I-013): Auswahl, Spalten, Windows-Schlüssel, CSV (BOM, Semikolon), PDF je Ordner."""

import csv
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from okula_recovery import backups, devices, inventory_export as ie, nas, warranty

GB = 1024**3
DAY = date(2026, 10, 31)


def make_device(store, n, name, folder="", vendor="Dell Inc.", serial="ABC1234", cpu="Intel(R) Core(TM) i5-8250U CPU",
                key="", smart=True):
    inv = {"dmi": {"sys_vendor": vendor, "product_name": "Latitude 7490", "product_serial": serial,
                   "product_uuid": f"00000000-0000-0000-0000-00000000000{n}"},
           "cpu": {"model": cpu}, "memory": 16 * GB,
           "disks": [{"name": "nvme0n1", "model": "Samsung SSD 980", "size": 512_110_190_592,
                      "smart": {"passed": smart}},
                     {"name": "sda", "model": "WDC WD10", "size": 1_000_204_886_016, "smart": {}}],
           "systems": [{"family": "Windows", "name": "Windows 11 Pro 24H2", "hostname": name}],
           "platform": {"tpm": "2.0", "uefi": True, "secure_boot": True},
           "oem_key": key}
    dev, _ = store.register(f"agent{n}", "10.0.0.5", "", inv, name)
    dev.name = name
    store.save(dev)
    if folder:
        for i, part in enumerate(folder.split("/")):
            parent = "/".join(folder.split("/")[:i])
            if (f"{parent}/{part}" if parent else part) not in store.folders:
                store.make_folder(parent, part)
        store.move_device(dev, folder)
    return store.devices[dev.id]


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.store = devices.DeviceStore(self.base / "geraete")
        self.a = make_device(self.store, 1, "PC-01", "Kunde A/Zürich", key="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY")
        self.b = make_device(self.store, 2, "PC-02", "Kunde A", cpu="Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz",
                             smart=False)
        self.c = make_device(self.store, 3, "Büro; \"Chef\"", "Kunde B", vendor="LENOVO")
        self.d = make_device(self.store, 4, "Neu-PC")
        self.b.warranty = warranty.manual("15.12.2026")
        self.c.warranty = warranty.manual("01.01.2020")

    def tearDown(self):
        self.tmp.cleanup()

    def test_select(self):
        devs = self.store.devices.values()
        self.assertEqual(len(ie.select(devs)), 4)
        self.assertEqual({d.name for d in ie.select(devs, "folder", "Kunde A")}, {"PC-01", "PC-02"})   # mit Unterordner
        self.assertEqual([d.name for d in ie.select(devs, "folder", "Kunde A/Zürich")], ["PC-01"])
        self.assertEqual([d.name for d in ie.select(devs, "folder", "")], ["Neu-PC"])
        self.assertEqual([d.name for d in ie.select(devs, "marked", ids={self.c.id})], ['Büro; "Chef"'])
        self.assertEqual(ie.select(devs, "folder", "Kunde"), [])            # kein Präfix-Treffer
        self.assertEqual(ie.folder_title(self.a.folder), "Zürich")             # Name wie in der Geräteliste
        self.assertEqual(ie.folder_path(self.a.folder), "Kunde A › Zürich")
        self.assertEqual(ie.folder_title(""), "Neu / nicht einsortiert")

    def test_row(self):
        img = ie.Latest("PC-01_2026-10-30", datetime(2026, 10, 30, 14, 0))
        r = ie.row(self.a, image=img)
        self.assertEqual(tuple(r), ie.COLUMNS)
        self.assertEqual(r["Ordner"], "Kunde A/Zürich")
        self.assertEqual(r["Modell"], "Latitude 7490")
        self.assertEqual(r["RAM"], "16 GB")
        self.assertEqual(r["Disks"], ["Samsung SSD 980, 512 GB, SMART ok", "WDC WD10, 1.0 TB, SMART –"])
        self.assertEqual(r["OS"], "Windows 11 Pro 24H2")
        self.assertEqual(r["Win-11-tauglich"], "ja")
        self.assertEqual(r["Letztes Image"], "30.10.2026 – PC-01_2026-10-30")
        self.assertEqual(r["Garantie bis"], "")
        rb = ie.row(self.b)
        self.assertTrue(rb["Win-11-tauglich"].startswith("nein (Prozessor"))
        self.assertIn("SMART FEHLER", rb["Disks"][0])
        self.assertTrue(rb["Garantie bis"].startswith("15.12.2026"))

    def test_key_never_full(self):
        self.assertNotIn(ie.KEY_COLUMN, ie.row(self.a))
        r = ie.row(self.a, with_key=True)
        self.assertEqual(r[ie.KEY_COLUMN], "XXXXX-XXXXX-XXXXX-XXXXX-UVWXY")
        self.assertEqual(ie.row(self.b, with_key=True)[ie.KEY_COLUMN], "")
        out = self.base / "out"
        devs = ie.select(self.store.devices.values())
        files = ie.export(out, devs, ie.build(devs, {}, {}, True), "alle", True, ie.pdf_available(), True, DAY)
        for f in files:
            text = f.read_bytes() if f.suffix == ".csv" else _pdf_text(f).encode()
            self.assertNotIn(b"ABCDE-FGHIJ", text, f.name)

    def test_csv(self):
        devs = ie.select(self.store.devices.values())
        path = ie.write_csv(self.base / "x.csv", ie.build(devs, {}, {}))
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))                  # BOM für Excel
        self.assertIn(b"\r\n", raw)
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        self.assertEqual(rows[0], list(ie.COLUMNS))
        self.assertEqual(len(rows), 5)
        chef = next(r for r in rows if r[0].startswith("Büro"))
        self.assertEqual(chef[0], 'Büro; "Chef"')                          # Semikolon und Anführungszeichen sicher
        self.assertEqual(chef[7], "Samsung SSD 980, 512 GB, SMART ok | WDC WD10, 1.0 TB, SMART –")
        self.assertIn("abgelaufen", chef[10])

    @unittest.skipUnless(ie.pdf_available() and shutil.which("pdftotext"), "reportlab/pdftotext fehlt")
    def test_pdf_per_folder(self):
        """Je Ordner eine Datei (Unterordner eigene Datei), Titel = Ordnername wie in der Liste."""
        devs = ie.select(self.store.devices.values())
        files = ie.export(self.base / "out", devs, ie.build(devs, {}, {}), "Alle Geräte", day=DAY)
        names = [f.name for f in files]
        self.assertEqual(names, ["Inventar_Alle_Geräte_2026-10-31.csv", "Inventar_Kunde_A_2026-10-31.pdf",
                                 "Inventar_Kunde_A_Zürich_2026-10-31.pdf", "Inventar_Kunde_B_2026-10-31.pdf",
                                 "Inventar_Neu_nicht_einsortiert_2026-10-31.pdf"])
        text = _pdf_text(files[1])
        self.assertIn("Inventar – Kunde A", text)
        self.assertIn("Stand: 31.10.2026 · 1 Gerät", text)
        self.assertIn("PC-02", text)
        self.assertNotIn("PC-01", text)                                      # liegt im Unterordner
        self.assertIn("Seite 1", text)
        self.assertIn("Seriennummer", text)
        sub = _pdf_text(files[2])
        self.assertIn("Inventar – Zürich", sub)
        self.assertIn("Ordner: Kunde A › Zürich", sub)
        self.assertIn("PC-01", sub)
        self.assertIn("Büro", _pdf_text(files[3]))
        self.assertIn("Inventar – Neu / nicht einsortiert", _pdf_text(files[4]))
        info = subprocess.run(["pdfinfo", str(files[1])], capture_output=True, text=True).stdout
        self.assertRegex(info, r"Page size: +841\.89 x 595\.2\d* pts \(A4\)")   # A4 quer

    @unittest.skipUnless(ie.pdf_available() and shutil.which("pdftotext"), "reportlab/pdftotext fehlt")
    def test_pdf_single(self):
        """Option: alle gewählten Geräte in einem PDF."""
        devs = ie.select(self.store.devices.values())
        files = ie.export(self.base / "one", devs, ie.build(devs, {}, {}), "Alle Geräte", fmt_csv=False, day=DAY,
                          pdf_single=True)
        self.assertEqual([f.name for f in files], ["Inventar_Alle_Geräte_2026-10-31.pdf"])
        text = _pdf_text(files[0])
        self.assertIn("Inventar – Alle Geräte", text)
        self.assertIn("4 Geräte", text)
        for name in ("PC-01", "PC-02", "Büro", "Neu-PC"):
            self.assertIn(name, text)

    @unittest.skipUnless(ie.pdf_available(), "reportlab fehlt")
    def test_pdf_many_rows(self):
        """Lange Liste bricht auf mehrere Seiten um, Kopfzeile wiederholt sich."""
        rows = [ie.row(self.a)] * 60
        path = ie.write_pdf(self.base / "lang.pdf", "Kunde A", rows, day=DAY)
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout if \
            shutil.which("pdfinfo") else "Pages: 2"
        pages = int(next(ln.split()[-1] for ln in info.splitlines() if ln.startswith("Pages:")))
        self.assertGreater(pages, 1)

    def test_latest_image_and_backup(self):
        root = self.base / "nas"
        imgs = []
        for name, dev, when, source in (("old", self.a, datetime(2026, 1, 1), {"device_id": self.a.id}),
                                        ("new", self.a, datetime(2026, 9, 1), {"agent_id": "agent1"}),
                                        ("other", None, datetime(2026, 9, 2), {"device_id": "fremd"})):
            p = root / name
            p.mkdir(parents=True)
            (p / nas.OKULA_META).write_text(json.dumps({"source": source}))
            imgs.append(SimpleNamespace(kind="Disk-Image", path=p, name=name, mtime=when))
        imgs.append(SimpleNamespace(kind="ISO", path=root, name="iso", mtime=datetime(2027, 1, 1)))
        scan = lambda _root: SimpleNamespace(all_images=lambda: imgs)   # noqa: E731
        found = ie.latest_images(root, [self.a, self.b], scan)
        self.assertEqual(list(found), [self.a.id])
        self.assertEqual(found[self.a.id].name, "new")
        self.assertEqual(ie.latest_images(None, [self.a]), {})

        saved = [backups.BackupInfo(root / "b1", {"device_id": self.b.id, "created": "2026-10-01T10:00:00",
                                                  "note": "vor  Neuinstallation", "mode": "profiles"}),
                 backups.BackupInfo(root / "b2", {"device_name": "PC-02", "created": "2026-05-01T10:00:00"}),
                 backups.BackupInfo(root / "b3", {"device_name": "Fremd", "created": "2026-10-30T10:00:00"})]
        found = ie.latest_backups(saved, [self.a, self.b])
        self.assertEqual(found[self.b.id].text(), "01.10.2026 – vor Neuinstallation")
        self.assertNotIn(self.a.id, found)

    def test_file_names(self):
        self.assertEqual(ie.file_stem("Kunde A/Zürich", DAY), "Inventar_Kunde_A_Zürich_2026-10-31")
        self.assertEqual(ie.safe_name("../../etc"), "etc")
        self.assertEqual(ie.safe_name("///"), "Inventar")
        self.assertEqual(ie.safe_name("Neu / nicht einsortiert"), "Neu_nicht_einsortiert")


def _pdf_text(path: Path) -> str:
    if not shutil.which("pdftotext"):
        return path.read_bytes().decode("latin-1")
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


if __name__ == "__main__":
    unittest.main()
