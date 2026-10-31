import unittest

from okula_recovery import bootkeys


def keys(**dmi):
    found = bootkeys.lookup(dmi)
    return found.vendor if found else None


class BootKeysTest(unittest.TestCase):
    def test_vendor_spellings(self):
        self.assertEqual(keys(sys_vendor="Hewlett-Packard", product_name="HP EliteBook 850 G1"), "HP")
        self.assertEqual(keys(sys_vendor="HP", product_name="HP ProBook 450 G8"), "HP")
        self.assertEqual(keys(sys_vendor="Dell Inc.", product_name="Latitude 5420"), "Dell")
        self.assertEqual(keys(sys_vendor="LENOVO", product_name="20XW0055MZ", product_version="ThinkPad X1 Carbon Gen 9",
                              product_family="ThinkPad X1 Carbon Gen 9"), "Lenovo ThinkPad / ThinkCentre")
        self.assertEqual(keys(sys_vendor="LENOVO", product_name="82H8", product_version="IdeaPad 3 15ITL6"),
                         "Lenovo IdeaPad / Yoga / Legion")
        self.assertEqual(keys(sys_vendor="ASUSTeK COMPUTER INC.", product_name="ZenBook UX425EA", chassis="Notebook"),
                         "Asus Notebook")
        self.assertEqual(keys(sys_vendor="ASUSTeK COMPUTER INC.", product_name="ASUS VivoPC", chassis="Desktop"),
                         "Asus Desktop / Mainboard")
        self.assertEqual(keys(sys_vendor="Acer", product_name="Aspire A515-56"), "Acer")
        self.assertEqual(keys(sys_vendor="Micro-Star International Co., Ltd.", product_name="GF63 Thin"), "MSI")
        self.assertEqual(keys(sys_vendor="Gigabyte Technology Co., Ltd.", product_name="B550 AORUS"), "Gigabyte")
        self.assertEqual(keys(sys_vendor="FUJITSU CLIENT COMPUTING LIMITED", product_name="LIFEBOOK U7411"),
                         "Fujitsu LifeBook / Esprimo")
        self.assertEqual(keys(sys_vendor="MEDION", product_name="E15308"), "Medion")
        self.assertEqual(keys(sys_vendor="TOSHIBA", product_name="SATELLITE C55"), "Toshiba / Dynabook")
        self.assertEqual(keys(sys_vendor="Dynabook Inc.", product_name="dynabook Tecra A40-J"), "Toshiba / Dynabook")
        self.assertEqual(keys(sys_vendor="Microsoft Corporation", product_name="Surface Laptop 4"), "Microsoft Surface")
        self.assertEqual(keys(sys_vendor="Apple Inc.", product_name="MacBookPro16,1"), "Apple Mac (Intel)")

    def test_own_build_uses_board_and_unknown(self):
        # Eigenbau: „System manufacturer“ → Mainboard-Hersteller, immer Desktop-Tasten
        self.assertEqual(keys(sys_vendor="System manufacturer", board_vendor="ASUSTeK COMPUTER INC.",
                              chassis="Notebook"), "Asus Desktop / Mainboard")
        self.assertEqual(keys(sys_vendor="To Be Filled By O.E.M.", board_vendor="Micro-Star International Co., Ltd."),
                         "MSI")
        self.assertIsNone(keys(sys_vendor="Microsoft Corporation", product_name="Virtual Machine"))  # Hyper-V
        self.assertIsNone(keys(sys_vendor="QEMU", product_name="Standard PC"))
        self.assertIsNone(bootkeys.lookup(None))

    def test_short_text_and_table(self):
        self.assertEqual(bootkeys.short(bootkeys.lookup({"sys_vendor": "Dell Inc."})), "Boot-Menü: F12 · BIOS: F2")
        self.assertIn("F12 Boot Menu", bootkeys.short(bootkeys.lookup({"sys_vendor": "Acer"})))
        self.assertEqual(bootkeys.short(None), "")
        self.assertGreaterEqual(len(bootkeys.TABLE), 12)
