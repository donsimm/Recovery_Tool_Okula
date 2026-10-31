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
            "Intel(R) Core(TM) i7-7820HQ CPU @ 2.90GHz": True,     # Ausnahme in Microsofts Liste
            "Intel(R) Core(TM) i7-7700HQ CPU @ 2.80GHz": False,
            "Intel(R) Core(TM) i5-4590 CPU @ 3.30GHz": False,
            "Intel(R) Core(TM) i5-650 CPU @ 3.20GHz": False,
            "Intel(R) Core(TM)2 Duo CPU E8400 @ 3.00GHz": False,
            "Intel(R) Pentium(R) CPU G4560 @ 3.50GHz": False,
            "Intel(R) Celeron(R) CPU N3350 @ 1.10GHz": False,
            "Intel(R) Xeon(R) Silver 4110 CPU @ 2.10GHz": False,
            "AMD Ryzen 5 2400G with Radeon Vega Graphics": False,
            "AMD Ryzen 7 1700 Eight-Core Processor": False,
            "AMD Athlon 200GE with Radeon Vega Graphics": False,
            "AMD A10-9600P RADEON R5": False,
            "QEMU Virtual CPU version 2.5+": None,
        }
        for model, expected in cases.items():
            self.assertIs(win11.cpu_supported(model), expected, model)

    def test_rules_file_has_source(self):
        head = win11.CPU_RULES.read_text(encoding="utf-8")[:1500]
        self.assertIn("learn.microsoft.com", head)


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
