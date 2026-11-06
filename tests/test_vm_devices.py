"""VMs in der Geräteliste (I-001 Auftrag 2): Geräteeintrag mit Vor-Inventar, Wiedererkennung über die UUID,
Netzwerkstart-Freigabe der VM-MAC, Startart und fester Ordner „Virtuelle Maschinen“ – ohne libvirt und GTK."""

import random
import tempfile
import unittest
from pathlib import Path

from okula_recovery import devices, vm

FOLDER = devices.VM_FOLDER


def agent_inventory(p: vm.VmProfile) -> dict:
    """So meldet der Agent in der VM das Inventar (Namen wie im echten Linux, Disk mit Partitionen)."""
    return {"collected": "2026-11-06T10:00:00",
            "dmi": {"sys_vendor": "Okula", "product_name": p.name, "product_uuid": p.smbios.uuid.lower(),
                    "product_serial": p.smbios.serial},
            "network": [{"name": "enp1s0", "mac": p.nic.mac, "wireless": False, "driver": "e1000e"}],
            "disks": [{"name": "sda", "serial": p.disk.serial, "size": p.disk.size_gb * 10**9, "partitions": []}],
            "systems": [], "platform": {"tpm": "", "uefi": True, "secure_boot": False}}


class VmDeviceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = devices.DeviceStore(Path(self.tmp.name) / "geraete")
        self.p = vm.fill_identity(vm.PROFILES["VM-Klein"], rng=random.Random(7))
        self.dev = self.store.register_vm(self.p.name, vm.pre_inventory(self.p, devices.now()), "VM-Klein")

    def tearDown(self):
        self.tmp.cleanup()

    def test_entry_with_pre_inventory_in_vm_folder(self):
        dev = self.dev
        self.assertTrue(dev.is_vm)
        self.assertEqual((dev.name, dev.folder, dev.vm["name"]), ("VM-Klein", FOLDER, "VM-Klein"))
        self.assertEqual(dev.key, "uuid:" + self.p.smbios.uuid.lower())
        self.assertEqual(dev.agent_ids, [self.p.smbios.uuid.lower()])
        self.assertEqual(dev.hardware, "Okula VM-Klein")
        self.assertTrue(dev.inventory["provisional"])
        self.assertTrue((Path(self.tmp.name) / "geraete" / FOLDER / f"{dev.id}.json").is_file())
        # nach dem Neuladen (Tool-Neustart) wieder da und als VM markiert
        again = devices.DeviceStore(self.store.base).devices[dev.id]
        self.assertEqual((again.folder, again.vm["name"], again.netboot, again.netfirst), (FOLDER, "VM-Klein",
                                                                                          True, True))

    def test_netboot_free_and_mac_listed(self):
        # Falle: 52:54:00:… ist lokal vergeben – zählt nur, weil die Kabel-Karte im Vor-Inventar steht
        self.assertFalse(devices.real_mac(self.p.nic.mac))
        self.assertTrue(self.dev.netboot)
        self.assertEqual(devices.netboot_macs([self.dev]), [self.p.nic.mac])
        bare = devices.Device(id="x", netboot=True, macs=[self.p.nic.mac], inventory={})
        self.assertEqual(devices.netboot_macs([bare]), [])                 # ohne Inventar: keine Antwort
        self.assertEqual(devices.netboot_modes(self.store.devices.values()), {self.p.nic.mac: "local"})

    def test_boot_mode_like_netfirst(self):
        self.assertEqual(devices.boot_mode(self.dev), "local")             # ohne Auftrag: von der Disk
        self.dev.boot_request = True
        self.assertEqual(devices.boot_mode(self.dev), "once")              # einmal der Agent

    def test_first_agent_report_recognizes_entry(self):
        uuid = self.p.smbios.uuid.lower()
        # Beacon (Agent-ID = Board-UUID) ohne Inventar: schon über die Agent-ID gefunden
        self.assertIs(self.store.match(agent_id=uuid), self.dev)
        dev, new = self.store.register(uuid, "192.168.110.90", self.p.nic.mac, agent_inventory(self.p))
        self.assertFalse(new)
        self.assertIs(dev, self.dev)
        self.assertEqual(len(self.store.devices), 1)                       # kein zweites Gerät
        self.assertNotIn("provisional", dev.inventory)                     # echtes Inventar ersetzt das Vor-Inventar
        self.assertEqual((dev.folder, dev.vm["name"]), (FOLDER, "VM-Klein"))
        self.assertEqual(devices.netboot_macs([dev]), [self.p.nic.mac])    # weiterhin freigeschaltet
        # auch ohne Agent-ID-Treffer: über die UUID im Inventar
        dev2, new = self.store.register("andere-id", "192.168.110.90", "", agent_inventory(self.p))
        self.assertFalse(new)
        self.assertIs(dev2, self.dev)

    def test_second_vm_and_duplicate_uuid(self):
        p2 = vm.fill_identity(vm.PROFILES["VM-Klein"], rng=random.Random(8))
        other = self.store.register_vm("VM-Klein-2", vm.pre_inventory(p2), "VM-Klein")
        self.assertEqual([d.name for d in self.store.vm_devices()], ["VM-Klein", "VM-Klein-2"])
        self.assertIs(self.store.vm_device("VM-Klein-2"), other)
        with self.assertRaises(devices.DeviceError):
            self.store.register_vm("Kopie", vm.pre_inventory(self.p))

    def test_folder_fixed(self):
        s = self.store
        self.assertIn(FOLDER, s.folders)
        for op in (lambda: s.make_folder(FOLDER, "Unter"), lambda: s.make_folder("", FOLDER),
                   lambda: s.rename_folder(FOLDER, "VMs"), lambda: s.delete_folder(FOLDER),
                   lambda: s.move_folder(FOLDER, "")):
            with self.assertRaises(devices.DeviceError):
                op()
        s.make_folder("", "Zürich")
        with self.assertRaises(devices.DeviceError):
            s.move_folder("Zürich", FOLDER)                                # keine Unterordner
        with self.assertRaises(devices.DeviceError):
            s.rename_folder("Zürich", FOLDER)
        with self.assertRaises(devices.DeviceError):
            s.move_device(self.dev, "Zürich")                              # VM nicht herausziehbar
        with self.assertRaises(devices.DeviceError):
            s.move_device(self.dev, "")
        real, _ = s.register("uuid-r", "192.168.110.5", "3c:52:82:a0:a1:df",
                             {"dmi": {"sys_vendor": "HP", "product_uuid": "4c4c4544-0035-3010-8052-b3c04f4a3133"}})
        with self.assertRaises(devices.DeviceError):
            s.move_device(real, FOLDER)                                    # echte Geräte nicht hinein
        s.move_device(real, "Zürich")
        self.assertEqual(real.folder, "Zürich")

    def test_merge_keeps_vm_marker(self):
        twin = devices.Device(id="abc", name="alt", first_seen="2026-01-01T00:00:00")
        self.store.devices[twin.id] = twin
        self.store.save(twin)
        self.store.merge(twin, self.dev)
        self.assertTrue(twin.is_vm)


if __name__ == "__main__":
    unittest.main()
