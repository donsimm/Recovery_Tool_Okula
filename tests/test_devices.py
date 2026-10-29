import json
import tempfile
import unittest
from pathlib import Path

from okula_recovery import devices


def inv(uuid="4c4c4544-0035-3010-8052-b3c04f4a3133", serial="7XQ2B53", mac="3c:52:82:a0:a1:df",
        disk_serial="S6ABC123", hostname="BUCHHALTUNG-01", os_name="Windows 11 Pro 23H2"):
    return {"dmi": {"sys_vendor": "Dell Inc.", "product_name": "Latitude 5420", "product_uuid": uuid,
                    "product_serial": serial},
            "network": [{"name": "eth0", "mac": mac}],
            "disks": [{"name": "nvme0n1", "serial": disk_serial}],
            "systems": [{"family": "Windows", "name": os_name, "hostname": hostname}] if os_name else []}


class DeviceStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = devices.DeviceStore(Path(self.tmp.name) / "geraete")

    def tearDown(self):
        self.tmp.cleanup()

    def test_identity_priority(self):
        self.assertEqual(devices.identity(inv()), "uuid:4c4c4544-0035-3010-8052-b3c04f4a3133")
        self.assertEqual(devices.identity(inv(uuid="")), "sn:dell inc.:7xq2b53")
        self.assertEqual(devices.identity(inv(uuid="", serial="")), "mac:3c:52:82:a0:a1:df")

    def test_register_new_then_recognize(self):
        dev, new = self.store.register("uuid-a", "192.168.110.171", "3c:52:82:a0:a1:df", inv())
        self.assertTrue(new)
        self.assertEqual(dev.name, "BUCHHALTUNG-01")
        self.assertEqual(dev.os_name, "Windows 11 Pro 23H2")
        self.assertTrue((Path(self.tmp.name) / f"geraete/{dev.id}.json").is_file())
        # Nächster Boot: neues Inventar (anderes OS nach Restore) → gleiches Gerät
        again, new = self.store.register("uuid-a", "192.168.110.180", "3c:52:82:a0:a1:df",
                                         inv(os_name="Windows 10 Pro 22H2"))
        self.assertFalse(new)
        self.assertEqual(again.id, dev.id)
        self.assertEqual(again.os_name, "Windows 10 Pro 22H2")
        self.assertEqual([h["kind"] for h in again.history], ["erfasst", "inventar"])

    def test_recognize_after_board_swap_by_disk_serial(self):
        dev, _ = self.store.register("a", "1.1.1.1", "", inv())
        same, new = self.store.register("b", "1.1.1.2", "", inv(uuid="11111111-2222-3333-4444-555555555555",
                                                               serial="NEU", mac="aa:bb:cc:dd:ee:ff"))
        self.assertFalse(new)
        self.assertEqual(same.id, dev.id)

    def test_shared_usb_adapter_does_not_merge_devices(self):
        # gleicher USB-Netzwerkadapter an zwei Laptops: verschiedene UUIDs → zwei Geräte
        a, _ = self.store.register("uuid-a", "10.0.0.5", "00:e0:4c:68:00:01", inv(mac="00:e0:4c:68:00:01"))
        b, new = self.store.register("uuid-b", "10.0.0.6", "00:e0:4c:68:00:01",
                                     inv(uuid="11111111-2222-3333-4444-555555555555", serial="ABC",
                                         mac="00:e0:4c:68:00:01", disk_serial="OTHER"))
        self.assertTrue(new)
        self.assertNotEqual(a.id, b.id)

    def test_folder_ops_keep_device_objects(self):
        dev, _ = self.store.register("uuid-a", "10.0.0.5", "", inv())
        self.store.make_folder("", "Kunde")
        self.store.move_device(dev, "Kunde")
        self.store.rename_folder("Kunde", "Kunde Neu")
        self.assertIs(self.store.devices[dev.id], dev)  # offenes Gerätefenster speichert weiter richtig
        self.assertEqual(dev.folder, "Kunde Neu")
        self.store.update(dev, notes="Akku tauschen")
        self.assertEqual(json.loads((self.store.base / "Kunde Neu" / f"{dev.id}.json").read_text())["notes"],
                         "Akku tauschen")

    def test_same_inventory_no_duplicate_history(self):
        dev, _ = self.store.register("uuid-a", "10.0.0.5", "", dict(inv(), collected="2026-10-28T10:00:00"))
        self.store.register("uuid-a", "10.0.0.5", "", dict(inv(), collected="2026-10-28T11:00:00"))
        self.assertEqual([h["kind"] for h in dev.history], ["erfasst"])
        self.store.register("uuid-a", "10.0.0.5", "", inv(os_name="Ubuntu 24.04 LTS"))
        self.assertEqual([h["kind"] for h in dev.history], ["erfasst", "inventar"])

    def test_folders_move_and_reload(self):
        dev, _ = self.store.register("a", "1.1.1.1", "", inv())
        self.store.make_folder("", "Kunde A")
        self.store.make_folder("Kunde A", "Zürich")
        self.store.make_folder("Kunde A/Zürich", "Buchhaltung")
        with self.assertRaisesRegex(devices.DeviceError, "3 Ebenen"):
            self.store.make_folder("Kunde A/Zürich/Buchhaltung", "zu tief")
        self.store.move_device(dev, "Kunde A/Zürich")
        self.store.update(dev, name="PC Buchhaltung", notes="Akku schwach")
        self.store.touch(dev, "192.168.110.171", connected=True)
        reloaded = devices.DeviceStore(Path(self.tmp.name) / "geraete")
        d = reloaded.devices[dev.id]
        self.assertEqual((d.folder, d.name, d.notes), ("Kunde A/Zürich", "PC Buchhaltung", "Akku schwach"))
        self.assertEqual(d.history[-1]["text"], "Verbunden (192.168.110.171)")
        self.assertIn("Kunde A/Zürich/Buchhaltung", reloaded.folders)
        with self.assertRaisesRegex(devices.DeviceError, "nicht leer"):
            reloaded.delete_folder("Kunde A/Zürich")
        self.assertEqual(reloaded.rename_folder("Kunde A", "Kunde B"), "Kunde B")
        self.assertEqual(reloaded.devices[dev.id].folder, "Kunde B/Zürich")

    def test_move_folder_depth_and_history_cap(self):
        for parent, name in (("", "A"), ("A", "B"), ("A/B", "C"), ("", "X")):
            self.store.make_folder(parent, name)
        with self.assertRaisesRegex(devices.DeviceError, "3 Ebenen"):
            self.store.move_folder("A", "X")
        self.assertEqual(self.store.move_folder("A/B/C", "X"), "X/C")
        dev, _ = self.store.register("a", "", "", inv())
        for i in range(devices.MAX_HISTORY + 20):
            self.store.add_history(dev, "test", str(i), save=False)
        self.assertEqual(len(dev.history), devices.MAX_HISTORY)

    def test_corrupt_file_ignored(self):
        (Path(self.tmp.name) / "geraete/kaputt.json").write_text("{nicht json")
        self.store.load()
        self.assertEqual(self.store.devices, {})


    def test_merge_duplicates_same_board(self):
        # alter Eintrag (einsortiert, Notiz) und ein zweiter mit anderer ID – z. B. vor dem Import neu erfasst
        old, _ = self.store.register("4c4c4544-0035-3010-8052-b3c04f4a3133", "10.0.0.5", "", inv())
        self.store.move_device(old, self.store.make_folder("", "XX"))
        self.store.update(old, name="DoNs_EliteBook_1", notes="Akku schwach")
        old.netboot = True
        self.store.save(old)
        dup = devices.Device(id="neu123", key=old.key, name="Hewlett-Packard HP EliteBook 850 G1",
                             first_seen="2099-01-01T10:00:00", last_seen="2099-01-01T10:00:00", last_ip="10.0.0.9",
                             agent_ids=list(old.agent_ids), macs=["aa:bb:cc:dd:ee:01"],
                             inventory=inv(os_name=""), history=[{"time": "2099-01-01T10:00:00", "kind": "erfasst",
                                                                  "text": "Erstmals erfasst", "ok": None}])
        self.store.devices[dup.id] = dup
        self.store.save(dup)
        self.assertEqual([(a.id, b.id) for a, b in self.store.duplicates()], [(old.id, "neu123")])
        self.assertEqual(self.store.merge_duplicates(), ["DoNs_EliteBook_1"])
        store = devices.DeviceStore(self.store.base)  # auch auf der Platte nur noch ein Eintrag
        self.assertEqual(list(store.devices), [old.id])
        merged = store.devices[old.id]
        self.assertEqual((merged.name, merged.folder, merged.notes), ("DoNs_EliteBook_1", "XX", "Akku schwach"))
        self.assertEqual((merged.last_ip, merged.os_name), ("10.0.0.9", ""))  # Inventar vom zuletzt gesehenen
        self.assertIn("aa:bb:cc:dd:ee:01", merged.macs)
        self.assertTrue(merged.netboot)
        self.assertEqual([h["kind"] for h in merged.history][-2:], ["erfasst", "zusammengeführt"])
        self.assertEqual(store.duplicates(), [])

    def test_no_auto_merge_for_different_boards_or_mac_ids(self):
        a, _ = self.store.register("uuid-a", "10.0.0.5", "", inv())
        b, _ = self.store.register("uuid-b", "10.0.0.6", "", inv(uuid="11111111-2222-3333-4444-555555555555",
                                                                serial="ABC", mac="aa:aa:aa:aa:aa:aa",
                                                                disk_serial="OTHER"))
        # Agent-ID = MAC (kein DMI): geteilter USB-Adapter darf nicht automatisch zusammenführen
        for d, key in ((a, "mac:aa"), (b, "mac:bb")):
            d.key, d.agent_ids = key, ["00:e0:4c:68:00:01"]
        self.assertEqual(self.store.duplicates(), [])
        with self.assertRaises(devices.DeviceError):
            self.store.merge(a, a)


class ProductKeyTest(unittest.TestCase):
    def test_oem_key_from_msdm_and_precedence(self):
        from okula_recovery import inventory
        with tempfile.TemporaryDirectory() as tmp:
            msdm = Path(tmp) / "MSDM"
            msdm.write_bytes(b"MSDM" + bytes(52) + b"ABCDE-FGHJK-MNPQR-TVWXY-23456")
            self.assertEqual(inventory.oem_key(msdm), "ABCDE-FGHJK-MNPQR-TVWXY-23456")
            msdm.write_bytes(b"MSDM" + bytes(80))
            self.assertEqual(inventory.oem_key(msdm), "")
            self.assertEqual(inventory.oem_key(Path(tmp) / "fehlt"), "")
        dev = devices.Device(id="x", inventory={"oem_key": "ABCDE-FGHJK-MNPQR-TVWXY-23456",
                                                "systems": [{"family": "Windows", "edition": "Professional"}]})
        self.assertEqual(dev.windows_key, ("ABCDE-FGHJK-MNPQR-TVWXY-23456", "BIOS (OEM)"))
        self.assertEqual(dev.windows_edition, "Professional")
        dev.product_key = "VK7JG-NPHTM-C97JM-9MPGT-3V66T"
        self.assertEqual(dev.windows_key[1], "hinterlegt")
        self.assertEqual(devices.mask_key(dev.windows_key[0]), "XXXXX-XXXXX-XXXXX-XXXXX-3V66T")

    def test_normalize_key(self):
        self.assertEqual(devices.normalize_key(" vk7jg npHTM-c97jm 9mpgt 3v66t "), "VK7JG-NPHTM-C97JM-9MPGT-3V66T")
        self.assertEqual(devices.normalize_key(""), "")
        with self.assertRaisesRegex(devices.DeviceError, "25 Zeichen"):
            devices.normalize_key("ABC-123")


if __name__ == "__main__":
    unittest.main()
