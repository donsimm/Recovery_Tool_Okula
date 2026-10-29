"""Einstellungen exportieren/importieren: alter Rechner → neuer Rechner (je eigene XDG-Ordner)."""

import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, config, devices, transfer


class Machine:
    """Eigene Konfigurations- und Datenordner, wie ein separater Rechner."""

    def __init__(self, root: Path):
        self.env = {"XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data")}

    def __enter__(self):
        self.patch = mock.patch.dict(os.environ, self.env)
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()


def write_device(base: Path, folder: str, dev_id: str, name: str, last_seen: str, **extra) -> Path:
    path = base / folder / f"{dev_id}.json" if folder else base / f"{dev_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": dev_id, "name": name, "last_seen": last_seen, **extra}))
    return path


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old = Machine(self.root / "alt")
        self.new = Machine(self.root / "neu")
        with self.old:
            cfg = config.Config()
            cfg.nas = config.NasConfig("smb", "192.168.110.154", "recovery", "/mnt/okula-nas", "okula")
            config.save(cfg)
            self.key = agentclient.load_or_create_key()
            base = devices.default_base()
            write_device(base, "Kunde A/Zürich", "d1", "PC Empfang", "2026-10-20T10:00:00",
                         notes="Lüfter laut", product_key="AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
            write_device(base, "", "d2", "Laptop", "2026-10-21T10:00:00")
            (base / "Kunde B").mkdir()  # leerer Ordner bleibt erhalten

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_roundtrip_to_new_machine(self):
        out = self.root / "export.okula.zip"
        with self.old:
            manifest = transfer.export_all(out)
        self.assertEqual(manifest["devices"], 2)
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)  # enthält den Schlüssel
        exp = transfer.read_export(out)
        self.assertIn("Geräte: 2 (in 3 Ordnern)", exp.describe())
        with self.new:
            result = transfer.import_all(exp)
            self.assertEqual((result.config, result.key, result.added), (True, "neu", 2))
            self.assertEqual(config.load().nas.host, "192.168.110.154")
            self.assertEqual(agentclient.load_or_create_key(), self.key)
            store = devices.DeviceStore()
            self.assertEqual(store.devices["d1"].folder, "Kunde A/Zürich")
            self.assertEqual(store.devices["d1"].notes, "Lüfter laut")
            self.assertEqual(store.devices["d1"].product_key, "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
            self.assertIn("Kunde B", store.folders)
            self.assertEqual(result.backup_dir, "")  # nichts vorhanden → nichts zu sichern

    def test_merge_keeps_newer_and_backs_up(self):
        out = self.root / "export.okula.zip"
        with self.old:
            transfer.export_all(out)
        with self.new:
            other_key = agentclient.load_or_create_key()
            base = devices.default_base()
            write_device(base, "", "d1", "PC Empfang (alt)", "2026-10-01T10:00:00")       # älter → ersetzt
            write_device(base, "Neu", "d2", "Laptop (neuer)", "2026-10-28T10:00:00")       # neuer → bleibt
            result = transfer.import_all(transfer.read_export(out), use_config=False)
            self.assertEqual((result.updated, result.kept, result.key), (1, 1, "ersetzt"))
            self.assertFalse(result.config)
            store = devices.DeviceStore()
            self.assertEqual((store.devices["d1"].name, store.devices["d1"].folder), ("PC Empfang", "Kunde A/Zürich"))
            self.assertEqual(store.devices["d2"].name, "Laptop (neuer)")
            backup = Path(result.backup_dir)
            self.assertEqual(bytes.fromhex((backup / "agent.key").read_text().strip()), other_key)
            self.assertTrue((backup / "geraete" / "d1.json").is_file())

    def test_export_without_key_and_nas_file(self):
        out = self.root / "ohne-schluessel.okula.zip"
        nas_file = self.root / "nas.json"
        with self.old:
            transfer.export_all(out, include_key=False, include_devices=False)
            transfer.export_nas(config.load().nas, nas_file)
        exp = transfer.read_export(out)
        self.assertIsNone(exp.key)
        self.assertEqual(exp.device_files, {})
        self.assertNotIn("password", nas_file.read_text().lower())
        for source in (nas_file, out):  # NAS-Fenster liest beide Arten
            nas = transfer.read_nas(source)
            self.assertEqual((nas.host, nas.share, nas.username), ("192.168.110.154", "recovery", "okula"))

    def test_rejects_bad_files(self):
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("manifest.json", json.dumps({"format": transfer.EXPORT_FORMAT, "version": 1}))
            z.writestr("geraete/../../.bashrc", "x")
        with self.assertRaises(transfer.TransferError):
            transfer.read_export(bad)
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("manifest.json", json.dumps({"format": transfer.EXPORT_FORMAT, "version": 1}))
            z.writestr("geraete/d9.json", json.dumps({"id": "anders"}))
        with self.assertRaises(transfer.TransferError):
            transfer.read_export(bad)
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("manifest.json", json.dumps({"format": transfer.EXPORT_FORMAT, "version": 99}))
        with self.assertRaises(transfer.TransferError):
            transfer.read_export(bad)
        other = self.root / "other.json"
        other.write_text('{"hallo": 1}')
        with self.assertRaises(transfer.TransferError):
            transfer.read_nas(other)


if __name__ == "__main__":
    unittest.main()
