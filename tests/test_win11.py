"""Windows-11-Tauglichkeit: Prozessorliste, Bewertung, TPM/Secure Boot aus sysfs."""

import tempfile
import unittest
from pathlib import Path

from okula_recovery import inventory, win11

GB = 1024**3


def inv(cpu="Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz", tpm="2.0", uefi=True, sb=True, ram=8 * GB, disk=256e9):
    return {"cpu": {"model": cpu}, "memory": ram, "disks": [{"size": disk}],
            "platform": {"tpm": tpm, "uefi": uefi, "secure_boot": sb}}


class CpuListTest(unittest.TestCase):
    def test_known_models(self):
        cases = {
            "Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz": True,
            "11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz": True,
            "12th Gen Intel(R) Core(TM) i5-1235U": True,
            "13th Gen Intel(R) Core(TM) i9-13900K": True,
            "Intel(R) Core(TM) Ultra 7 155H": True,
            "Intel(R) N100": True,
            "Intel(R) Pentium(R) Silver N5000 CPU @ 1.10GHz": True,
            "Intel(R) Celeron(R) N4020 CPU @ 1.10GHz": True,
            "Intel(R) Xeon(R) Gold 6230 CPU @ 2.10GHz": True,
            "AMD Ryzen 5 3500U with Radeon Vega Mobile Gfx": True,
            "AMD Ryzen 7 2700X Eight-Core Processor": True,
            "AMD Ryzen 7 PRO 4750U with Radeon Graphics": True,
            "AMD Athlon Silver 3050U with Radeon Graphics": True,
            "Intel(R) Core(TM) i7-7820HQ CPU @ 2.90GHz": False,    # früher Ausnahme, in keiner aktuellen Liste
            "Intel(R) Core(TM) i7-7800X CPU @ 3.50GHz": True,      # Core 7000X Series (Microsoft-Liste)
            "Intel(R) Core(TM) i7-14700K": True,
            "Intel(R) Core(TM) 7 150U": True,                      # Core Series 1
            "Intel(R) Core(TM) i3-N305": True,
            "Intel(R) Core(TM) m3-8100Y CPU @ 1.10GHz": True,
            "Intel(R) Core(TM) m3-7Y30 CPU @ 1.00GHz": False,
            "Intel(R) Pentium(R) CPU 4415U @ 2.30GHz": True,       # Pentium Gold 4000U Series
            "Intel(R) Pentium(R) Gold G5400 CPU @ 3.70GHz": True,
            "Intel(R) Celeron(R) CPU 3865U @ 1.80GHz": True,       # Celeron 3000 Series
            "Intel(R) Celeron(R) CPU G3900 @ 2.80GHz": False,
            "Intel(R) Xeon(R) W-2145 CPU @ 3.70GHz": True,
            "Intel(R) Xeon(R) E-2236 CPU @ 3.40GHz": True,
            "Intel(R) Xeon(R) CPU E5-2650 v4 @ 2.20GHz": False,
            "Intel(R) Atom(TM) x6425E Processor @ 2.00GHz": False,
            "AMD Ryzen 5 3400G with Radeon Vega Graphics": True,   # 21H2/24H2-Liste (25H2 nur für neue Geräte)
            "AMD Ryzen AI 9 HX 370 w/ Radeon 890M": True,
            "AMD Ryzen Z1 Extreme": True,
            "AMD Ryzen 7 260 w/ Radeon 780M Graphics": True,
            "AMD 3020e with Radeon Graphics": True,
            "AMD EPYC 7313 16-Core Processor": True,
            "AMD EPYC 7301 16-Core Processor": False,
            "Intel(R) Core(TM) i7-7700HQ CPU @ 2.80GHz": False,
            "Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz": False,
            "Intel(R) Core(TM) i5-650 CPU @ 3.20GHz": False,
            "Intel(R) Core(TM)2 Duo CPU E8400 @ 3.00GHz": False,
            "Intel(R) Pentium(R) CPU G4560 @ 3.50GHz": False,
            "Intel(R) Celeron(R) CPU N3350 @ 1.10GHz": False,
            "Intel(R) Xeon(R) Silver 4110 CPU @ 2.10GHz": True,    # Xeon Scalable (1. Gen.) in der Liste
            "AMD Ryzen 5 2400G with Radeon Vega Graphics": False,
            "AMD Ryzen 7 1700 Eight-Core Processor": False,
            "AMD Athlon 200GE with Radeon Vega Graphics": False,
            "AMD A10-9600P RADEON R5": False,
            "QEMU Virtual CPU version 2.5+": None,
        }
        for model, expected in cases.items():
            self.assertIs(win11.cpu_supported(model), expected, model)

    def test_rules_file_has_source(self):
        head = win11.CPU_RULES.read_text(encoding="utf-8")[:2500]
        self.assertIn("learn.microsoft.com", head)
        self.assertIn("25h2-supported-intel-processors", head)
        self.assertIn("abgeglichen am 31.10.2026", head)


class CheckTest(unittest.TestCase):
    def test_ok_and_notes(self):
        r = win11.check(inv())
        self.assertEqual((r.status, r.symbol), ("ok", "✔"))
        r = win11.check(inv(sb=False))
        self.assertEqual(r.status, "ok")
        self.assertIn("Secure Boot ist aus", r.text())

    def test_failures(self):
        r = win11.check(inv(tpm="1.2"))
        self.assertEqual((r.status, r.text()), ("no", "✖ TPM 1.2 (2.0 nötig)"))
        self.assertIn("kein TPM", win11.check(inv(tpm="")).text())
        self.assertIn("RAM", win11.check(inv(ram=2 * GB)).text())
        self.assertIn("64 GB", win11.check(inv(disk=32e9)).text())
        r = win11.check(inv(cpu="Intel(R) Core(TM) i7-7700HQ CPU"))
        self.assertEqual(r.status, "no")
        self.assertIn("Prozessor nicht unterstützt", r.text())

    def test_unknown(self):
        self.assertEqual(win11.check({"cpu": {"model": "x"}}).status, "unknown")     # alter Agent
        self.assertIn("Agent-Stick neu erstellen", win11.check({}).text())
        self.assertEqual(win11.check(inv(cpu="QEMU Virtual CPU")).status, "unknown")
        self.assertIn("BIOS-Modus", win11.check(inv(uefi=False, sb=None)).text())
        # ✖ überwiegt ?
        self.assertEqual(win11.check(inv(cpu="QEMU", tpm="1.2")).status, "no")


class PlatformTest(unittest.TestCase):
    def test_sysfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(inventory.platform(root), {"tpm": "", "uefi": False, "secure_boot": None})
            (root / "class/tpm/tpm0").mkdir(parents=True)
            (root / "class/tpm/tpm0/tpm_version_major").write_text("2\n")
            efivars = root / "firmware/efi/efivars"
            efivars.mkdir(parents=True)
            (efivars / inventory.SECURE_BOOT_VAR).write_bytes(b"\x06\x00\x00\x00\x01")
            self.assertEqual(inventory.platform(root), {"tpm": "2.0", "uefi": True, "secure_boot": True})
            (efivars / inventory.SECURE_BOOT_VAR).write_bytes(b"\x06\x00\x00\x00\x00")
            (root / "class/tpm/tpm0/tpm_version_major").write_text("1\n")
            self.assertEqual(inventory.platform(root), {"tpm": "1.2", "uefi": True, "secure_boot": False})


class UnsupportedInstallTest(unittest.TestCase):
    """Windows 11 trotz „nicht tauglich“: nur von Hand, Warnung, Vermerk am Gerät und im Export."""

    def test_note_and_export(self):
        from okula_recovery import inventory_export
        self.assertEqual(win11.unsupported_note(""), "")
        self.assertIn("Am 31.10.2026 trotzdem installiert", win11.unsupported_note("2026-10-31"))
        self.assertIn("Updates nicht garantiert", win11.unsupported_note("2026-10-31"))
        text = inventory_export.win11_text(inv(tpm="1.2"), "2026-10-31")
        self.assertEqual(text, "nein (TPM 1.2 (2.0 nötig)) – trotzdem installiert 31.10.2026, Updates nicht garantiert")
        self.assertEqual(inventory_export.win11_text(inv()), "ja")

    def test_options_default_off_and_summary(self):
        from okula_recovery import winunattend
        opts = winunattend.WinOptions()
        self.assertFalse(opts.bypass_requirements)
        self.assertFalse(opts.unsupported_hardware)
        lines = winunattend.summary(winunattend.WinOptions(bypass_requirements=True, unsupported_hardware=True))
        self.assertTrue(any("nicht garantiert" in line for line in lines))
        self.assertIn("Herstellergarantie", winunattend.UNSUPPORTED_WARNING)

    def test_device_field_saved_and_merged(self):
        from okula_recovery import devices
        with tempfile.TemporaryDirectory() as tmp:
            store = devices.DeviceStore(Path(tmp))
            a, _ = store.register("a", "10.0.0.5", "", {"dmi": {"product_uuid": "11111111-1111-1111-1111-111111111111"}})
            a.win11_unsupported = "2026-10-31"
            store.save(a)
            self.assertEqual(devices.DeviceStore(Path(tmp)).devices[a.id].win11_unsupported, "2026-10-31")
            b, _ = store.register("b", "10.0.0.6", "", {"dmi": {"product_uuid": "22222222-2222-2222-2222-222222222222"}})
            store.merge(b, a)
            self.assertEqual(b.win11_unsupported, "2026-10-31")
