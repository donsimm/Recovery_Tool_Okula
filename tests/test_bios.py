"""BIOS-Reiter (I-032): firmware-attributes lesen/setzen (nachgebautes sysfs), Vergleich, CSV, Demo-Agent."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agentclient, biosinfo, biosread, devices, discovery, wire

ROOT = Path(__file__).resolve().parent.parent


def make_sysfs(root: Path, admin: bool = False) -> Path:
    """Aufbau wie /sys mit hp-bioscfg (Dokumentation: sysfs-class-firmware-attributes)."""
    dmi = root / "class" / "dmi" / "id"
    dmi.mkdir(parents=True)
    for k, v in {"bios_vendor": "Hewlett-Packard", "bios_version": "L71 Ver. 01.44", "bios_date": "08/22/2018"}.items():
        (dmi / k).write_text(v + "\n")
    (root / "firmware" / "efi").mkdir(parents=True)
    base = root / "class" / "firmware-attributes" / "hp-bioscfg"
    for name, display, value, possible in (
            ("Boot_Mode", "Boot Mode", "UEFI Native (Without CSM)", "Legacy;UEFI Hybrid (With CSM);UEFI Native (Without CSM)"),
            ("PXE_Internal_IPV4_NIC_boot", "PXE Internal IPV4 NIC boot", "Disable", "Disable;Enable"),
            ("Fast_Boot", "Fast Boot", "Disable", "Disable;Enable")):
        d = base / "attributes" / name
        d.mkdir(parents=True)
        (d / "type").write_text("enumeration\n")
        (d / "current_value").write_text(value + "\n")
        (d / "display_name").write_text(display + "\n")
        (d / "possible_values").write_text(possible + "\n")
    s = base / "attributes" / "Asset_Tracking_Number"
    s.mkdir()
    (s / "type").write_text("string\n")
    (s / "current_value").write_text("OKULA-0815\n")
    (s / "max_length").write_text("18\n")
    (base / "attributes" / "pending_reboot").write_text("0\n")
    auth = base / "authentication" / "Setup Password"
    auth.mkdir(parents=True)
    (auth / "is_enabled").write_text("1\n" if admin else "0\n")
    (auth / "current_password").write_text("")
    return root


class BiosReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read(self):
        data = biosread.read(make_sysfs(self.root), drivers=False)
        self.assertEqual(data["interfaces"], ["hp-bioscfg"])
        self.assertEqual(data["bios"]["version"], "L71 Ver. 01.44")
        self.assertTrue(data["platform"]["uefi"])
        attrs = {a["display"]: a for a in data["attributes"]}
        self.assertEqual(attrs["PXE Internal IPV4 NIC boot"]["value"], "Disable")
        self.assertEqual(attrs["Boot Mode"]["possible"][0], "Legacy")
        self.assertEqual(attrs["Asset_Tracking_Number"]["max_length"], "18")
        self.assertEqual(data["auth"], {"Setup Password": False})

    def test_no_interface_only_basics(self):
        (self.root / "class" / "dmi" / "id").mkdir(parents=True)
        data = biosread.read(self.root, drivers=False)
        self.assertEqual((data["interfaces"], data["attributes"]), ([], []))
        self.assertIn("nur Grundangaben", biosinfo.summary(data))
        self.assertEqual(biosinfo.boot_rows(data)[0][0], "–")

    def test_write_with_and_without_password(self):
        root = make_sysfs(self.root, admin=True)
        attr = root / "class/firmware-attributes/hp-bioscfg/attributes/PXE_Internal_IPV4_NIC_boot"
        pw = root / "class/firmware-attributes/hp-bioscfg/authentication/Setup Password/current_password"
        with self.assertRaisesRegex(biosread.BiosError, "Passwort"):
            biosread.write("PXE_Internal_IPV4_NIC_boot", "Enable", "", root)
        with self.assertRaisesRegex(biosread.BiosError, "nicht erlaubt"):
            biosread.write("PXE_Internal_IPV4_NIC_boot", "Vielleicht", "geheim", root)
        with self.assertRaisesRegex(biosread.BiosError, "gibt es"):
            biosread.write("../../etc", "x", "geheim", root)
        written = []
        real_text, real_bytes = Path.write_text, Path.write_bytes

        def spy(self_, text, *a, **k):
            written.append((self_.name, text))
            return real_text(self_, text, *a, **k)

        def spy_bytes(self_, data, *a, **k):
            written.append((self_.name, data.decode()))
            return real_bytes(self_, data, *a, **k)
        with mock.patch.object(Path, "write_text", spy), mock.patch.object(Path, "write_bytes", spy_bytes):
            res = biosread.write("PXE_Internal_IPV4_NIC_boot", "Enable", "geheim", root)
        self.assertEqual(res["value"], "Enable")
        self.assertEqual(attr.joinpath("current_value").read_text(), "Enable")
        self.assertEqual(written, [("current_password", "geheim"), ("current_value", "Enable"),
                                   ("current_password", "")])               # Passwort danach gelöscht
        self.assertEqual(pw.read_text(), "")


class OldEncodingTest(unittest.TestCase):
    """B-005: HP EliteBook 850 G1 meldet Namen in Windows-1252 (Byte 0xCE) – vorher brach der Agent beim Senden ab."""

    def test_cp1252_names_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_sysfs(Path(tmp))
            attrs = os.fsencode(root / "class/firmware-attributes/hp-bioscfg/attributes")
            d = attrs + b"/Langue \xce"                        # „Langue Î“ in Windows-1252
            os.mkdir(d)
            for f, v in ((b"type", b"enumeration"), (b"current_value", b"Fran\xe7ais"),
                         (b"possible_values", b"English;Fran\xe7ais;Deutsch")):
                with open(d + b"/" + f, "wb") as fh:
                    fh.write(v + b"\n")
            data = biosread.read(root, drivers=False)
            a = next(x for x in data["attributes"] if x["name"].startswith("Langue"))
            self.assertEqual((a["name"], a["value"], a["possible"][1]), ("Langue Î", "Français", "Français"))
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")      # vorher: UnicodeEncodeError
            self.assertIn("Langue Î".encode(), payload)
            res = biosread.write("Langue Î", "Deutsch", "", root)
            self.assertEqual(res["value"], "Deutsch")
            biosread.write("Langue Î", "Français", "", root)
            with open(d + b"/current_value", "rb") as fh:
                self.assertEqual(fh.read(), "Français".encode("cp1252"))   # in der Kodierung des BIOS zurück

    def test_wire_never_fails_on_surrogates(self):
        a, b = socket.socketpair()
        with a, b:
            wire.send_json(a, {"name": "x\udcce"})
            self.assertEqual(wire.recv_json(b), {"name": "x?"})

    def test_only_matching_driver_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_sysfs(Path(tmp))
            (root / "class/dmi/id/sys_vendor").write_text("Hewlett-Packard\n")
            calls = []
            with mock.patch.object(biosread.subprocess, "run", lambda cmd, **k: calls.append(cmd)):
                biosread.load_drivers(root)
            self.assertEqual(calls, [["modprobe", "-q", "hp_bioscfg"]])


class GarbledDriverTest(unittest.TestCase):
    """B-006: hp-bioscfg auf dem HP EliteBook 850 G1 (BIOS L71 01.11/01.49) liefert kaputte Namen und leere Werte."""

    def data(self, version, ati):
        return {"read": "2026-11-05T16:08:00", "bios": {"vendor": "Hewlett-Packard", "version": version},
                "platform": {"uefi": False, "tpm": "1.2"}, "interfaces": ["hp-bioscfg"],
                "auth": {"SPM": False, "\r": False},
                "attributes": [{"name": "\x02\x03", "display": "\x02\x03", "type": "string", "value": ati,
                                "max_length": "0"},
                               {"name": "\x08\x08", "display": "\x08\x08", "type": "enumeration", "value": ""},
                               {"name": "\r", "display": "\r", "type": "string", "value": "QDS-BRCM1058"},
                               {"name": "Sure_Start", "display": "Sure_Start", "type": "enumeration", "value": ""},
                               {"name": "í", "display": "í", "type": "string", "value": ""},
                               {"name": "Î", "display": "Î", "type": "enumeration", "value": ""},
                               {"name": "þ", "display": "þ", "type": "enumeration", "value": ""}]}

    def test_hidden_and_explained(self):
        bad, good = self.data("L71 Ver. 01.49", "ATI 08/22/14"), self.data("L71 Ver. 01.11", "ATI 12/30/13")
        basics = dict(biosinfo.basics(bad))
        self.assertEqual(basics["BIOS-Passwort"], "unbekannt")
        self.assertEqual(basics["Secure Platform Management (HP)"], "nicht eingerichtet")
        self.assertEqual(basics["Secure Boot"], "– (nur im UEFI-Modus)")
        self.assertIn("unlesbare Daten (6 von 7", basics["Schnittstelle"])
        rows = biosinfo.compare(bad, good)
        names = [r["name"] for r in rows]
        self.assertNotIn("\r", names)
        self.assertIn("Sure_Start", names)
        self.assertEqual(next(r for r in rows if r["name"] == "Sure_Start")["here"], "–")
        self.assertEqual([r["name"] for r in biosinfo.compare(bad, good, only_diff=True)], ["BIOS"])
        self.assertIn("1 Einstellung", biosinfo.summary(bad))
        self.assertEqual(biosinfo.possible_text({"type": "string", "max_length": "0"}), "Text")
        self.assertEqual(biosinfo.possible_text({"type": "enumeration"}), "")
        for ok in ("Boot Mode", "PXE Internal IPV4 NIC boot", "Virtualization Technology (VTx)", "Sure_Start"):
            self.assertTrue(biosinfo.plausible(ok), ok)


class CompareTest(unittest.TestCase):
    def data(self, ipv4="Enable", mode="UEFI Native (Without CSM)", uefi=True):
        return {"read": "2026-11-05T14:00:00", "bios": {"vendor": "HP", "version": "L71 01.44"},
                "platform": {"uefi": uefi, "secure_boot": False, "tpm": "1.2"}, "interfaces": ["hp-bioscfg"],
                "auth": {"Setup Password": False},
                "attributes": [{"name": "PXE_IPV4", "display": "PXE Internal IPV4 NIC boot", "value": ipv4,
                                "possible": ["Disable", "Enable"]},
                               {"name": "Boot_Mode", "display": "Boot Mode", "value": mode},
                               {"name": "Asset", "display": "Asset Tracking Number", "value": "X"}],
                "boot": {"order": ["0001", "0002"], "network": "0002",
                         "labels": {"0001": "Windows Boot Manager", "0002": "IPV4 Network"}}}

    def test_compare_two_elitebooks(self):
        ok, bad = self.data(), self.data(ipv4="Disable")
        rows = biosinfo.compare(bad, ok, only_diff=True)
        self.assertEqual([(r["name"], r["here"], r["other"]) for r in rows],
                         [("PXE Internal IPV4 NIC boot", "Disable", "Enable")])
        self.assertTrue(rows[0]["important"])
        self.assertIn("1 Unterschied", biosinfo.summary(bad, ok, "EliteBook 1"))
        allrows = biosinfo.compare(bad, ok)
        self.assertEqual(allrows[0]["name"], "BIOS")                          # Grundangaben zuerst
        self.assertEqual(allrows[-1]["name"], "Asset Tracking Number")        # Unwichtiges zuletzt
        self.assertEqual([r["name"] for r in biosinfo.compare(bad, None, text="ipv4")],
                         ["UEFI-Startreihenfolge", "PXE Internal IPV4 NIC boot"])     # sucht auch in den Werten
        legacy = self.data(uefi=False)
        diff = {r["name"] for r in biosinfo.compare(legacy, ok, only_diff=True)}
        self.assertIn("Boot-Modus", diff)
        self.assertIn("UEFI-Startreihenfolge", diff)
        self.assertEqual(biosinfo.boot_rows(ok)[1], ("2", "IPV4 Network  ← Netzwerkstart"))

    def test_csv_and_risk(self):
        text = biosinfo.to_csv(biosinfo.compare(self.data("Disable"), self.data(), True), "HP-2", "HP-1")
        self.assertTrue(text.startswith("﻿Einstellung;HP-2;HP-1;Unterschied"))
        self.assertIn("PXE Internal IPV4 NIC boot;Disable;Enable;ja", text)
        self.assertIn("Boot-Modus", biosinfo.risky("Boot Mode"))
        self.assertIn("Bestätigung", biosinfo.risky("SecureBoot"))
        self.assertEqual(biosinfo.risky("Fast Boot"), "")

    def test_saved_with_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = devices.DeviceStore(Path(tmp))
            dev, _ = store.register("a", "1.1.1.1", "", {"dmi": {"product_uuid": "4c4c4544-0035-3010-8052-b3c04f4a3133"}})
            dev.bios = self.data()
            store.save(dev)
            self.assertEqual(devices.DeviceStore(Path(tmp)).devices[dev.id].bios["bios"]["version"], "L71 01.44")


class DemoAgentBiosTest(unittest.TestCase):
    """Ende-zu-Ende über den echten Demo-Agent (simuliertes HP-BIOS)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.key = bytes(range(32))
        (d / "agent.key").write_text(self.key.hex() + "\n")
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", 0))
        self.udp.settimeout(10)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "okula_recovery.demo_agent", "--key-file", str(d / "agent.key"),
             "--port", str(self.udp.getsockname()[1]), "--control-port", str(self.port), "--duration", "1"],
            env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.udp.recvfrom(discovery.MAX_PACKET + 1)

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(5)
        self.udp.close()
        self.tmp.cleanup()

    def test_read_set_read(self):
        data = agentclient.bios("127.0.0.1", self.key, self.port)
        self.assertEqual(data["interfaces"], ["hp-bioscfg"])
        ipv4 = next(a for a in data["attributes"] if a["name"] == "PXE Internal IPV4 NIC boot")
        self.assertEqual(ipv4["value"], "Enable")
        res = agentclient.bios_set("127.0.0.1", self.key, "PXE Internal IPV4 NIC boot", "Disable", "", self.port)
        self.assertTrue(res["pending_reboot"])
        with self.assertRaisesRegex(agentclient.AgentError, "nicht erlaubt"):
            agentclient.bios_set("127.0.0.1", self.key, "Fast Boot", "Turbo", "", self.port)
        again = agentclient.bios("127.0.0.1", self.key, self.port)
        rows = biosinfo.compare(again, data, only_diff=True)
        self.assertEqual([(r["name"], r["here"], r["other"]) for r in rows],
                         [("PXE Internal IPV4 NIC boot", "Disable", "Enable")])
        self.assertEqual(dict(biosinfo.basics(again))["Änderungen"], "warten auf Neustart")

    def test_old_agent_message(self):
        with mock.patch.object(agentclient, "_connect") as conn, \
                mock.patch.object(agentclient.wire, "send_json"), \
                mock.patch.object(agentclient.wire, "recv_json", return_value={"type": "error",
                                                                               "message": "Unbekannter Befehl: bios"}):
            conn.return_value.__enter__.return_value = object()
            with self.assertRaisesRegex(agentclient.AgentError, "Agent zu alt"):
                agentclient.bios("10.0.0.1", self.key)


if __name__ == "__main__":
    unittest.main()
