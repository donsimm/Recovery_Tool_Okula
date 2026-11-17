"""I-037: Grafikkarten im Inventar (lspci bzw. /sys + pci.ids), Anzeige in der Übersicht, Demo-Gerät, Zwilling."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import demo_agent, inventory, vm
from tests.test_vm_twin import SERVER, SHARKBAY

NVIDIA_GT740 = """Slot:\t0000:00:02.0
Class:\tVGA compatible controller [0300]
Vendor:\tIntel Corporation [8086]
Device:\tXeon E3-1200 v3/4th Gen Core Processor Integrated Graphics Controller [0412]
SVendor:\tASUSTeK Computer Inc. [1043]
SDevice:\tDevice [8534]
Rev:\t06
Driver:\ti915

Slot:\t0000:00:1b.0
Class:\tAudio device [0403]
Vendor:\tIntel Corporation [8086]
Device:\t8 Series/C220 Series Chipset High Definition Audio Controller [8c20]
Driver:\tsnd_hda_intel

Slot:\t0000:01:00.0
Class:\tVGA compatible controller [0300]
Vendor:\tNVIDIA Corporation [10de]
Device:\tGK107 [GeForce GT 740] [0fc8]
SVendor:\tASUSTeK Computer Inc. [1043]
SDevice:\tDevice [8486]
Rev:\ta1
Driver:\tnouveau
Module:\tnouveau

Slot:\t0000:01:00.1
Class:\tAudio device [0403]
Vendor:\tNVIDIA Corporation [10de]
Device:\tGK107 HDMI Audio Controller [0e1b]
SVendor:\tASUSTeK Computer Inc. [1043]
SDevice:\tDevice [8486]
Driver:\tsnd_hda_intel
"""

INTEL_ONLY = """Slot:\t0000:00:00.0
Class:\tHost bridge [0600]
Vendor:\tIntel Corporation [8086]
Device:\t11th Gen Core Processor Host Bridge/DRAM Registers [9a14]

Slot:\t0000:00:02.0
Class:\tVGA compatible controller [0300]
Vendor:\tIntel Corporation [8086]
Device:\tTigerLake-LP GT2 [Iris Xe Graphics] [9a49]
SVendor:\tHewlett-Packard Company [103c]
SDevice:\tDevice [880d]
Driver:\ti915
"""

NO_GPU = """Slot:\t0000:00:00.0
Class:\tHost bridge [0600]
Vendor:\tIntel Corporation [8086]
Device:\tSky Lake-E DMI3 Registers [2020]

Slot:\t0000:02:00.0
Class:\tEthernet controller [0200]
Vendor:\tIntel Corporation [8086]
Device:\tEthernet Controller X710 for 10GbE SFP+ [1572]
"""

# Video-Server: zwei gleiche NVIDIA-Karten (mit HDMI-Audio), Onboard-Grafik ASPEED (absichtlich nicht sortiert)
VIDEO_SERVER = """Slot:\t0000:65:00.0
Class:\tVGA compatible controller [0300]
Vendor:\tNVIDIA Corporation [10de]
Device:\tTU104GL [Quadro RTX 4000] [1eb1]
SVendor:\tNVIDIA Corporation [10de]
SDevice:\tDevice [12a0]
Driver:\tnvidia

Slot:\t0000:65:00.1
Class:\tAudio device [0403]
Vendor:\tNVIDIA Corporation [10de]
Device:\tTU104 HD Audio Controller [10f8]

Slot:\t0000:03:00.0
Class:\tVGA compatible controller [0300]
Vendor:\tASPEED Technology, Inc. [1a03]
Device:\tASPEED Graphics Family [2000]
SVendor:\tSuper Micro Computer Inc [15d9]
SDevice:\tDevice [1b95]
Driver:\tast

Slot:\t0000:17:00.0
Class:\tVGA compatible controller [0300]
Vendor:\tNVIDIA Corporation [10de]
Device:\tTU104GL [Quadro RTX 4000] [1eb1]
SVendor:\tNVIDIA Corporation [10de]
SDevice:\tDevice [12a0]
Driver:\tnvidia

Slot:\t0000:17:00.1
Class:\tAudio device [0403]
Vendor:\tNVIDIA Corporation [10de]
Device:\tTU104 HD Audio Controller [10f8]
"""

PCI_IDS = """# pci.ids (Auszug)
8086  Intel Corporation
\t0412  Xeon E3-1200 v3/4th Gen Core Processor Integrated Graphics Controller
\t8c20  8 Series/C220 Series Chipset High Definition Audio Controller
1043  ASUSTeK Computer Inc.
10de  NVIDIA Corporation
\t0e1b  GK107 HDMI Audio Controller
\t0fc8  GK107 [GeForce GT 740]
\t\t1043 8486  GT740-2GD3
C 03  Display controller
\t00  VGA compatible controller
"""


def sys_tree(root: Path, devices: dict) -> Path:
    """Nachgebauter /sys/bus/pci/devices: {Adresse: (Klasse, Hersteller, Gerät, Sub-Hersteller, Sub-Gerät, Treiber)}."""
    base = root / "devices"
    drivers = root / "drivers"
    for slot, (cls, vendor, device, sv, sd, driver) in devices.items():
        d = base / slot
        d.mkdir(parents=True)
        for name, value in (("class", cls), ("vendor", vendor), ("device", device), ("subsystem_vendor", sv),
                            ("subsystem_device", sd)):
            (d / name).write_text(value + "\n")
        if driver:
            (drivers / driver).mkdir(parents=True, exist_ok=True)
            (d / "driver").symlink_to(drivers / driver)
    return base


CP_SYS = {"0000:00:02.0": ("0x030000", "0x8086", "0x0412", "0x1043", "0x8534", "i915"),
          "0000:00:1b.0": ("0x040300", "0x8086", "0x8c20", "0x1043", "0x8534", "snd_hda_intel"),
          "0000:01:00.0": ("0x030000", "0x10de", "0x0fc8", "0x1043", "0x8486", ""),
          "0000:01:00.1": ("0x040300", "0x10de", "0x0e1b", "0x1043", "0x8486", "snd_hda_intel")}


class LspciTest(unittest.TestCase):
    def gpus(self, text):
        with tempfile.TemporaryDirectory() as d:
            return inventory.gpus(text, Path(d), ())

    def test_intel_and_nvidia_without_hdmi_audio(self):
        intel, nvidia = self.gpus(NVIDIA_GT740)
        self.assertEqual((nvidia["slot"], nvidia["class"], nvidia["vendor"], nvidia["device"]),
                         ("0000:01:00.0", "0300", "10de", "0fc8"))
        self.assertEqual((nvidia["vendor_name"], nvidia["device_name"]), ("NVIDIA Corporation", "GK107 [GeForce GT 740]"))
        self.assertEqual((nvidia["subsystem_vendor"], nvidia["subsystem_device"]), ("1043", "8486"))
        self.assertEqual((nvidia["subsystem_vendor_name"], nvidia["subsystem_name"]), ("ASUSTeK Computer Inc.", ""))
        self.assertEqual(nvidia["driver"], "nouveau")
        self.assertEqual(inventory.gpu_text(nvidia), "NVIDIA GeForce GT 740 (GK107)")
        self.assertEqual(intel["driver"], "i915")
        self.assertTrue(inventory.gpu_text(intel).startswith("Intel Xeon E3-1200 v3"))

    def test_intel_only(self):
        [g] = self.gpus(INTEL_ONLY)
        self.assertEqual(inventory.gpu_text(g), "Intel Iris Xe Graphics (TigerLake-LP GT2)")

    def test_no_gpu(self):
        self.assertEqual(self.gpus(NO_GPU), [])

    def test_video_server_each_card_sorted_by_address(self):
        cards = self.gpus(VIDEO_SERVER)
        self.assertEqual([g["slot"] for g in cards], ["0000:03:00.0", "0000:17:00.0", "0000:65:00.0"])
        self.assertEqual([inventory.gpu_text(g) for g in cards],
                         ["ASPEED Graphics Family", "NVIDIA Quadro RTX 4000 (TU104GL)",
                          "NVIDIA Quadro RTX 4000 (TU104GL)"])
        self.assertTrue(all(g["class"].startswith("03") for g in cards))

    def test_driver_from_sys_when_lspci_has_none(self):
        text = NVIDIA_GT740.replace("Driver:\tnouveau\n", "")
        with tempfile.TemporaryDirectory() as d:
            base = sys_tree(Path(d), {"0000:01:00.0": ("0x030000", "0x10de", "0x0fc8", "", "", "nvidia")})
            cards = inventory.gpus(text, base, ())
        self.assertEqual(cards[1]["driver"], "nvidia")

    def test_lspci_missing_is_no_error(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(inventory.shutil, "which", lambda n: None):
            self.assertEqual(inventory.gpus(None, Path(d, "fehlt"), ()), [])


class SysfsTest(unittest.TestCase):
    def test_with_pci_ids(self):
        with tempfile.TemporaryDirectory() as d:
            base = sys_tree(Path(d), CP_SYS)
            ids = Path(d, "pci.ids")
            ids.write_text(PCI_IDS)
            intel, nvidia = inventory.gpus("", base, (Path(d, "fehlt.ids"), ids))
        self.assertEqual((nvidia["vendor"], nvidia["device"], nvidia["class"]), ("10de", "0fc8", "0300"))
        self.assertEqual(nvidia["device_name"], "GK107 [GeForce GT 740]")
        self.assertEqual(nvidia["subsystem_vendor_name"], "ASUSTeK Computer Inc.")
        self.assertEqual(nvidia["subsystem_name"], "GT740-2GD3")
        self.assertEqual(nvidia["driver"], "")
        self.assertEqual(intel["driver"], "i915")
        self.assertEqual(inventory.gpu_text(nvidia), "NVIDIA GeForce GT 740 (GK107)")

    def test_without_pci_ids_only_ids(self):
        with tempfile.TemporaryDirectory() as d:
            base = sys_tree(Path(d), CP_SYS)
            cards = inventory.gpus("", base, (Path(d, "fehlt.ids"),))
        self.assertEqual([(g["vendor"], g["device"]) for g in cards], [("8086", "0412"), ("10de", "0fc8")])
        self.assertEqual(cards[1]["vendor_name"], "")
        self.assertEqual(inventory.gpu_text(cards[1]), "NVIDIA (PCI 10de:0fc8)")
        self.assertEqual(inventory.gpu_text({"vendor": "abcd", "device": "0001"}), "PCI abcd:0001")

    def test_no_sys_no_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(inventory.gpus("", Path(d, "fehlt"), ()), [])


class OverviewTest(unittest.TestCase):
    def test_one_card(self):
        with tempfile.TemporaryDirectory() as d:
            cards = inventory.gpus(INTEL_ONLY, Path(d), ())
        [(label, text, tip)] = inventory.gpu_rows({"gpus": cards})
        self.assertEqual(label, "Grafikkarte")
        self.assertEqual(text, "Intel Iris Xe Graphics (TigerLake-LP GT2)  (0000:00:02.0)")
        self.assertIn("Karte von Hewlett-Packard Company", tip)
        self.assertIn("Treiber i915", tip)

    def test_several_cards_numbered_with_address(self):
        with tempfile.TemporaryDirectory() as d:
            cards = inventory.gpus(VIDEO_SERVER, Path(d), ())
        rows = inventory.gpu_rows({"gpus": list(reversed(cards))})
        self.assertEqual([r[0] for r in rows], ["Grafikkarte 1", "Grafikkarte 2", "Grafikkarte 3"])
        self.assertEqual(rows[1][1], "NVIDIA Quadro RTX 4000 (TU104GL)  (0000:17:00.0)")
        self.assertEqual(rows[2][1], "NVIDIA Quadro RTX 4000 (TU104GL)  (0000:65:00.0)")
        self.assertIn("Karte von Super Micro Computer", rows[0][2])

    def test_old_inventory_and_none_found(self):
        self.assertEqual(inventory.gpu_rows(copy.deepcopy(SHARKBAY)), [])
        self.assertEqual(inventory.gpu_rows({}), [])
        self.assertEqual(inventory.gpu_rows({"gpus": []}), [("Grafikkarte", "", "")])

    def test_model_name_formatting(self):
        self.assertEqual(inventory.gpu_model("GK107 [GeForce GT 740]"), "GeForce GT 740 (GK107)")
        self.assertEqual(inventory.gpu_model("HD Graphics 530"), "HD Graphics 530")
        self.assertEqual(inventory.gpu_text({"vendor": "1002", "vendor_name": "Advanced Micro Devices, Inc. [AMD/ATI]",
                                             "device_name": "Ellesmere [Radeon RX 470/480/570/570X/580/580X/590]"}),
                         "AMD Radeon RX 470/480/570/570X/580/580X/590 (Ellesmere)")
        self.assertEqual(inventory.gpu_text({"vendor": "5333", "vendor_name": "S3 Graphics Ltd.",
                                             "device_name": "86c368 [Trio 3D/2X]"}),
                         "S3 Graphics Trio 3D/2X (86c368)")


class DemoAndTwinTest(unittest.TestCase):
    def test_demo_inventory_has_gpu(self):
        inv = demo_agent.collect_inventory()
        [(label, text, _tip)] = inventory.gpu_rows(inv)
        self.assertEqual(label, "Grafikkarte")
        self.assertTrue(text.startswith("Intel Iris Xe Graphics (TigerLake-LP GT2)"))

    def test_twin_only_information(self):
        with tempfile.TemporaryDirectory() as d:
            cards = inventory.gpus(NVIDIA_GT740, Path(d), ())
        inv = {**copy.deepcopy(SHARKBAY), "gpus": cards}
        p, notes = vm.profile_from_inventory(inv, SERVER, "CompactPlayer")
        plain, _ = vm.profile_from_inventory(copy.deepcopy(SHARKBAY), SERVER, "CompactPlayer")
        hw, hw_plain = vm.asdict(p), vm.asdict(plain)
        for d in (hw, hw_plain):                                          # Identität ggf. zufällig neu
            d["smbios"].pop("uuid")
            d["smbios"].pop("serial")
        self.assertEqual(hw, hw_plain)                                    # VM-Hardware unverändert
        self.assertIn("Grafikkarte NVIDIA GeForce GT 740 (GK107) nicht nachgebildet (Standard-Grafik der VM)", notes)
        rows = {r[0]: r for r in vm.twin_rows(inv, p)}
        self.assertEqual(rows["Grafikkarte"][3], vm.SKIPPED)
        self.assertIn("NVIDIA GeForce GT 740 (GK107)", rows["Grafikkarte"][1])
        self.assertIn("Akku, WLAN, Sound, SMART", rows)
        rows = {r[0]: r for r in vm.twin_rows(SHARKBAY, plain)}
        self.assertNotIn("Grafikkarte", rows)
        self.assertIn("Akku, WLAN, Grafik, Sound, SMART", rows)


if __name__ == "__main__":
    unittest.main()
