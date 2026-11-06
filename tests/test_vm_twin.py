"""Digitaler Zwilling (I-001 Auftrag 3): VM-Profil aus dem Inventar eines Geräts, abgewandelte Identität, die nie
auf das Original passt, Vorschau Gerät → VM und Ä-036 (leere Disk) – ohne libvirt und GTK."""

import copy
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from okula_recovery import devices, vm

SERVER = vm.ServerInfo(cores=8, ram_free_mb=28 * 1024)

# Echtes Inventar (CompactPlayer, gekürzt) – Beispiel aus docs/VM.md: OEM SHARKBAY, BIOS/MBR, Realtek
SHARKBAY = {
    "collected": "2026-11-05T22:06:12",
    "dmi": {"sys_vendor": "OEM", "product_name": "SHARKBAY", "product_version": "", "product_serial": "",
            "product_uuid": "", "product_sku": "", "product_family": "", "board_vendor": "OEM",
            "board_name": "SHARKBAY", "board_serial": "JH007", "bios_vendor": "American Megatrends Inc.",
            "bios_version": "4.6.5", "bios_date": "10/21/2014", "chassis_type": "3", "chassis_vendor": "",
            "chassis_serial": "", "chassis": "Desktop"},
    "cpu": {"model": "Intel(R) Core(TM) i5-4200U CPU @ 1.60GHz", "threads": 4, "cores": 2},
    "memory": 4050759680,
    "network": [{"name": "enp2s0", "mac": "24:1c:04:a0:4c:13", "wireless": False, "driver": "r8169"}],
    "disks": [{"name": "sda", "path": "/dev/sda", "size": 120034123776, "model": "KINGSTON SH103S3120G",
               "serial": "50026B725115B857", "transport": "sata", "pttype": "dos", "fstype": "",
               "partitions": [{"name": "sda1", "size": 367001600, "fstype": "ntfs"},
                              {"name": "sda2", "size": 119665590272, "fstype": "ntfs"}]}],
    "systems": [{"family": "Windows", "name": "Windows 8.1 Pro", "hostname": "PB33150378", "partition": "sda2",
                 "disk": "sda"}],
    "platform": {"tpm": "", "uefi": True, "secure_boot": None},
    "oem_key": "",
}

# Moderner Business-Laptop: UEFI/GPT, NVMe, Secure Boot, TPM 2.0, Intel-Karte, WLAN, OEM-Key
ELITEBOOK = {
    "collected": "2026-11-06T09:00:00",
    "dmi": {"sys_vendor": "HP", "product_name": "HP EliteBook 840 G8 Notebook PC", "product_version": "",
            "product_serial": "5CG1234XYZ", "product_uuid": "4ec1a1b2-93c4-4d5e-8f60-112233445566",
            "product_sku": "3C6D5EA#UUZ", "product_family": "103C_5336AN HP EliteBook", "board_vendor": "HP",
            "board_name": "880D", "board_serial": "PKABC0123", "bios_vendor": "HP", "bios_version": "T37 Ver. 01.10.00",
            "bios_date": "03/15/2022", "chassis_type": "10", "chassis_vendor": "HP", "chassis_serial": "5CG1234XYZ",
            "chassis": "Notebook"},
    "cpu": {"model": "11th Gen Intel(R) Core(TM) i5-1145G7 @ 2.60GHz", "threads": 8, "cores": 4},
    "memory": 16_600_000_000,
    "network": [{"name": "wlp0s20f3", "mac": "a4:b1:c1:00:11:22", "wireless": True, "driver": "iwlwifi"},
                {"name": "enp0s31f6", "mac": "a4:b1:c1:00:11:23", "wireless": False, "driver": "e1000e"}],
    "disks": [{"name": "nvme0n1", "path": "/dev/nvme0n1", "size": 256060514304, "model": "SAMSUNG MZVLB256HBHQ-000H1",
               "serial": "S4GENX0R123456", "transport": "nvme", "pttype": "gpt",
               "partitions": [{"name": "nvme0n1p1", "size": 272629760, "fstype": "vfat"},
                              {"name": "nvme0n1p3", "size": 254000000000, "fstype": "ntfs"}]}],
    "systems": [{"family": "Windows", "name": "Windows 11 Pro", "hostname": "OK-LAPTOP-07", "partition": "nvme0n1p3",
                 "disk": "nvme0n1"}],
    "platform": {"tpm": "2.0", "uefi": True, "secure_boot": True},
    "oem_key": "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
}


def twin(inv, server=SERVER, name="Gerät"):
    return vm.profile_from_inventory(copy.deepcopy(inv), server, name)


def agent_view(p: vm.VmProfile, systems=()) -> dict:
    """So meldet der Agent in der laufenden Zwillings-VM das Inventar (nach dem Zurückspielen mit dem System des
    Originals – derselbe Computername)."""
    inv = vm.pre_inventory(p, "2026-11-06T12:00:00")
    inv.pop("provisional")
    inv["network"][0]["name"] = "enp1s0"
    inv["disks"][0]["partitions"] = [{"name": "sda1"}]
    inv["systems"] = list(systems)
    return inv


class ProfileFromInventoryTest(unittest.TestCase):
    def test_sharkbay_bios_mbr(self):
        p, notes = twin(SHARKBAY, name="CompactPlayer 2")
        self.assertEqual((p.firmware, p.chipset, p.tpm), ("bios", "i440fx", False))
        self.assertEqual((p.disk.bus, p.disk.size_gb, p.disk.model, p.disk.rpm), ("sata", 121, "KINGSTON SH103S3120G", 0))
        self.assertEqual(p.disk.serial, "VM50026B725115B857")
        self.assertEqual((p.cpu.name, p.cpu.cores, p.cpu.threads), ("Intel(R) Core(TM) i5-4200U CPU @ 1.60GHz", 2, 2))
        self.assertEqual(p.ram_mb, 4096)
        s = p.smbios
        self.assertEqual((s.manufacturer, s.product, s.board_vendor, s.board_product), ("OEM", "SHARKBAY", "OEM",
                                                                                         "SHARKBAY"))
        self.assertEqual((s.bios_vendor, s.bios_version, s.bios_date), ("American Megatrends Inc.", "4.6.5",
                                                                        "10/21/2014"))
        self.assertEqual((s.version, s.sku, s.family, s.chassis_vendor), ("", "", "", ""))   # keine „Okula“-Werte
        self.assertEqual(s.chassis_type, 3)
        self.assertEqual((s.serial, s.uuid), ("", ""))       # fehlt im Gerät → beim Erstellen neu
        self.assertEqual(s.board_serial, "VM-JH007")
        self.assertEqual(p.nic.model, "e1000")
        self.assertEqual(p.name, "VM-CompactPlayer-2")
        self.assertIn("Netzwerkkarte Realtek r8169 → Intel e1000", notes)
        self.assertIn("Gehäusetyp nur im Profil (in der VM nicht einstellbar)", notes)
        self.assertFalse(any("RAM" in n or "Prozessor" in n for n in notes))
        root = ET.fromstring(vm.domain_xml(vm.fill_identity(p, rng=random.Random(3))))
        system = {e.get("name"): e.text for e in root.findall("sysinfo/system/entry")}
        self.assertEqual((system["manufacturer"], system["product"]), ("OEM", "SHARKBAY"))
        self.assertNotIn("Okula", ET.tostring(root.find("sysinfo"), encoding="unicode"))
        self.assertIsNone(root.find("os").get("firmware"))                    # SeaBIOS
        self.assertIn("i5-4200U", vm.domain_xml(vm.fill_identity(p)))

    def test_uefi_nvme_secure_boot_tpm(self):
        p, notes = twin(ELITEBOOK, name="OK-Laptop 07")
        self.assertEqual((p.firmware, p.chipset, p.tpm), ("uefi-sb", "q35", True))
        self.assertEqual((p.disk.bus, p.disk.size_gb), ("nvme", 257))
        self.assertEqual(p.nic.model, "e1000e")
        self.assertEqual((p.cpu.cores, p.cpu.threads), (3, 2))     # 8 Threads > Server-Kerne − 2
        self.assertIn("Prozessor 4 Kerne / 8 Threads → 3 Kerne / 6 Threads (Server)", notes)
        self.assertEqual(p.ram_mb, 16 * 1024)
        s = p.smbios
        self.assertEqual(s.serial, "VM-5CG1234XYZ")
        self.assertEqual(s.chassis_serial, "VM-5CG1234XYZ")
        self.assertEqual(s.board_serial, "VM-PKABC0123")
        self.assertEqual(s.uuid, "0c1a0000-93c4-4d5e-8f60-112233445566")
        self.assertEqual((s.sku, s.family, s.chassis_type), ("3C6D5EA#UUZ", "103C_5336AN HP EliteBook", 10))
        self.assertEqual(p.name, "VM-OK-Laptop-07")
        self.assertTrue(any("QEMU NVMe Ctrl" in n for n in notes))
        self.assertIn("OEM-Key nicht übernommen – Windows bleibt „nicht aktiviert“", notes)
        self.assertFalse(any(n.startswith("Netzwerkkarte") for n in notes))     # Intel e1000e wie im Gerät
        xml = vm.domain_xml(vm.fill_identity(p))
        self.assertIn('secure="yes"', xml)
        self.assertNotIn("ABCDE", xml)

    def test_device_without_system_uses_first_disk_and_platform(self):
        inv = copy.deepcopy(ELITEBOOK)
        inv["systems"] = []
        inv["disks"][0].update(pttype="", partitions=[])
        inv["platform"] = {"tpm": "", "uefi": False, "secure_boot": None}
        p, notes = twin(inv)
        self.assertEqual((p.firmware, p.chipset, p.tpm), ("bios", "i440fx", False))
        self.assertEqual(p.disk.bus, "nvme")
        self.assertTrue(any("ohne Partitionstabelle" in n for n in notes))
        inv["platform"]["uefi"] = True
        self.assertEqual(twin(inv)[0].firmware, "uefi")

    def test_system_disk_is_the_one_with_windows(self):
        inv = copy.deepcopy(SHARKBAY)
        inv["disks"].insert(0, {"name": "sdb", "size": 2 * 10**12, "transport": "usb", "pttype": "gpt",
                                "model": "Daten", "serial": "X1"})
        inv["systems"][0]["disk"] = "sda"
        p, _notes = twin(inv)
        self.assertEqual((p.disk.size_gb, p.firmware), (121, "bios"))

    def test_placeholders_get_new_identity(self):
        inv = copy.deepcopy(ELITEBOOK)
        inv["dmi"].update(product_serial="To be filled by O.E.M.", board_serial="Default string",
                          chassis_serial="0000000000", product_uuid="03000200-0400-0500-0006-000700080009")
        inv["disks"][0]["serial"] = "0"
        p, notes = twin(inv)
        s = p.smbios
        self.assertEqual((s.serial, s.board_serial, s.chassis_serial, s.uuid, p.disk.serial), ("", "", "", "", ""))
        self.assertTrue(any("Seriennummer" in n for n in notes))
        self.assertTrue(any("UUID" in n for n in notes))
        full = vm.fill_identity(p, rng=random.Random(5))
        self.assertTrue(full.smbios.serial.startswith("VM-"))
        self.assertTrue(full.disk.serial.startswith("OKVM"))

    def test_cpu_and_ram_limited_by_server(self):
        inv = copy.deepcopy(ELITEBOOK)
        inv["cpu"] = {"model": "AMD Ryzen 9 7950X", "cores": 16, "threads": 32}
        inv["memory"] = 64 * 2**30
        p, notes = twin(inv, vm.ServerInfo(cores=8, ram_free_mb=20 * 1024))
        self.assertEqual(p.cpu.cores * p.cpu.threads, 6)            # Server-Kerne − 2
        self.assertEqual((p.cpu.cores, p.cpu.threads), (3, 2))
        self.assertEqual(p.ram_mb, 16 * 1024)                       # frei − 4 GB
        self.assertIn("Prozessor 16 Kerne / 32 Threads → 3 Kerne / 6 Threads (Server)", notes)
        self.assertIn("RAM 64 GB → 16 GB (Server)", notes)
        p, _ = twin(inv, vm.ServerInfo(cores=2, ram_free_mb=3000))
        self.assertEqual((p.cpu.cores, p.cpu.threads, p.ram_mb), (1, 1, 1024))

    def test_long_values_are_cut(self):
        inv = copy.deepcopy(SHARKBAY)
        inv["disks"][0].update(model="X" * 60, serial="ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        inv["dmi"]["product_serial"] = "S" * 80
        p, notes = twin(inv, name="Gerät mit Ümlaut / Sonderzeichen und einem sehr langen Namen 12345")
        self.assertEqual(len(p.disk.model), 40)
        self.assertEqual(p.disk.serial, "VMIJKLMNOPQRSTUVWXYZ")
        self.assertLessEqual(len(p.disk.serial), 20)
        self.assertLessEqual(len(p.smbios.serial), vm.SMBIOS_MAX)
        self.assertTrue(vm.NAME_RE.match(p.name), p.name)
        self.assertTrue(p.name.startswith("VM-Geraet-mit-Uemlaut-Sonderzeichen"))
        p.validate()

    def test_name_and_uuid_unique_for_second_twin(self):
        first, _ = twin(ELITEBOOK, name="Laptop")
        second, _ = twin(ELITEBOOK, vm.ServerInfo(cores=8, ram_free_mb=28 * 1024, taken_names=(first.name,),
                                                  taken_uuids=(first.smbios.uuid,)), name="Laptop")
        self.assertEqual(second.name, "VM-Laptop-2")
        self.assertNotEqual(second.smbios.uuid, first.smbios.uuid)
        self.assertTrue(second.smbios.uuid.startswith("0c1a0001"))

    def test_preview_rows(self):
        p, _ = twin(SHARKBAY)
        rows = {r[0]: r for r in vm.twin_rows(SHARKBAY, p)}
        self.assertEqual(rows["Hersteller / Modell"][3], vm.EXACT)
        self.assertEqual(rows["BIOS"][3], vm.EXACT)
        self.assertEqual(rows["Firmware"][1:3], ("BIOS (MBR)", "BIOS (Legacy) · i440FX"))
        self.assertEqual(rows["Arbeitsspeicher"][3], vm.EXACT)
        self.assertEqual(rows["Disk"][3], vm.EXACT)
        self.assertEqual(rows["Netzwerkkarte"][3], vm.ADAPTED)
        self.assertEqual(rows["Seriennummer"][3], vm.ADAPTED)
        self.assertEqual(rows["Windows-Schlüssel (OEM)"][3], vm.SKIPPED)
        p, _ = twin(ELITEBOOK, vm.ServerInfo(cores=16, ram_free_mb=64 * 1024))
        rows = {r[0]: r for r in vm.twin_rows(ELITEBOOK, p)}
        self.assertEqual(rows["Disk"][3], vm.ADAPTED)            # NVMe: Modellname bleibt „QEMU NVMe Ctrl“
        self.assertEqual(rows["TPM"][3], vm.EXACT)
        self.assertEqual(rows["Prozessor"][3], vm.EXACT)


class TwinIdentityTest(unittest.TestCase):
    """Der Zwilling darf nie mit dem Original zusammengeführt werden (UUID, Seriennummer, MAC, Disk-Seriennummer)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = devices.DeviceStore(Path(self.tmp.name) / "geraete")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, inv: dict, agent_id: str) -> None:
        original, new = self.store.register(agent_id, "10.0.0.5", inv["network"][-1]["mac"], copy.deepcopy(inv))
        self.assertTrue(new)
        p, _ = twin(inv, name=original.name)
        p = vm.fill_identity(p, rng=random.Random(11))
        pre = vm.pre_inventory(p, devices.now())
        self.assertIsNone(self.store.match(inv=pre))                           # vor dem Anlegen: kein Treffer
        dev = self.store.register_vm(p.name, pre, twin_of=original.id)
        self.assertEqual(dev.vm["twin_of"], original.id)
        self.assertEqual(dev.folder, devices.VM_FOLDER)
        self.assertNotEqual(dev.key, original.key)
        self.assertFalse(set(dev.disk_serials) & set(original.disk_serials))
        self.assertFalse(set(dev.macs) & set(original.macs))
        # Agent in der VM meldet sich – mit dem System des Originals (gleicher Computername)
        seen = agent_view(p, inv["systems"])
        found = self.store.match(agent_id=p.smbios.uuid.lower(), mac=p.nic.mac, inv=seen)
        self.assertIs(found, dev)
        self.assertIsNot(self.store.match(inv=seen), original)
        got, new = self.store.register(p.smbios.uuid.lower(), "10.0.0.9", p.nic.mac, seen)
        self.assertIs(got, dev)
        self.assertFalse(new)
        self.assertEqual(len(self.store.devices), 2)
        # das Original meldet sich wieder: bleibt das Original
        self.assertIs(self.store.match(agent_id=agent_id, mac=inv["network"][-1]["mac"], inv=inv), original)

    def test_sharkbay_never_matches(self):
        self.check(SHARKBAY, "agent-sharkbay")

    def test_uefi_nvme_never_matches(self):
        self.check(ELITEBOOK, "agent-elitebook")

    def test_twin_identity_differs_in_every_key(self):
        p, _ = twin(ELITEBOOK)
        p = vm.fill_identity(p, rng=random.Random(2))
        pre = vm.pre_inventory(p)
        d, o = pre["dmi"], ELITEBOOK["dmi"]
        for key in ("product_serial", "product_uuid", "board_serial", "chassis_serial"):
            self.assertNotEqual(d[key].lower(), o[key].lower(), key)
        self.assertNotEqual(devices.identity(pre), devices.identity(ELITEBOOK))
        self.assertNotEqual(pre["disks"][0]["serial"], ELITEBOOK["disks"][0]["serial"])
        self.assertFalse(devices.real_mac(pre["network"][0]["mac"]))


class BlankDiskTest(unittest.TestCase):
    """Ä-036: „Einschalten“ einer VM ohne System fragt nach."""

    def setUp(self):
        self.inv = vm.pre_inventory(vm.fill_identity(vm.PROFILES["VM-Win11"], rng=random.Random(1)))

    def test_new_vm_is_blank(self):
        self.assertTrue(vm.blank_disk(self.inv, [{"kind": "erfasst", "text": "Virtuelle Maschine angelegt"},
                                                 {"kind": "vm", "text": "VM eingeschaltet"}]))

    def test_partitions_or_table_means_system(self):
        inv = copy.deepcopy(self.inv)
        inv["disks"][0]["partitions"] = [{"name": "nvme0n1p1"}]
        self.assertFalse(vm.blank_disk(inv, []))
        inv["disks"][0].update(partitions=[], pttype="gpt")
        self.assertFalse(vm.blank_disk(inv, []))

    def test_history_install_restore_or_iso(self):
        for h in ({"kind": "install", "text": "Windows-Installation …: vorbereitet", "ok": True},
                  {"kind": "linux", "text": "Linux-Installation", "ok": True},
                  {"kind": "restore", "text": "Zurückspielen … erfolgreich", "ok": True},
                  {"kind": "auto", "text": "Automatisierung fertig", "ok": True},
                  {"kind": "vm", "text": "VM von ISO gestartet (Win11.iso)"}):
            self.assertFalse(vm.blank_disk(self.inv, [h]), h)

    def test_failed_restore_still_blank(self):
        self.assertTrue(vm.blank_disk(self.inv, [{"kind": "restore", "text": "Zurückspielen fehlgeschlagen",
                                                  "ok": False}]))


if __name__ == "__main__":
    unittest.main()
