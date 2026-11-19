"""I-041: Test-VMs mit QEMU-Gastagent – Option im Profil (Standard aus), XML mit/ohne Kanal, Ein-/Ausschalten ändert
nur Kanal und Controller, Snapshots/Zwilling/Start mit Overlay-Kette unverändert, guest-ping, Gasttools über die
Software-Bibliothek (Erkennung mit Probe-Dateien), Warnung beim Master, Hilfe."""

import copy
import json
import random
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from okula_recovery import software, vm
from tests.test_help import CHAPTERS
from tests.test_installerinfo import msi, pe_file, version_resource
from tests.test_vm import FakeVirsh
from tests.test_vm_snapshots import POOL, ChainFake

CHANNEL = "org.qemu.guest_agent.0"


def full(p: vm.VmProfile) -> vm.VmProfile:
    return vm.fill_identity(p, rng=random.Random(7))


def guest_parts(root: ET.Element) -> tuple[list, list]:
    dev = root.find("devices")
    return dev.findall("controller[@type='virtio-serial']"), dev.findall("channel")


def without_guest(xml: str) -> str:
    """XML ohne Kanal, Controller und Profil-Metadaten (für den Vergleich „ändert nur das“)."""
    root = ET.fromstring(xml)
    dev = root.find("devices")
    for el in dev.findall("controller[@type='virtio-serial']") + dev.findall("channel"):
        dev.remove(el)
    meta = root.find("metadata")
    for el in meta.findall(f"{{{vm.OKULA_NS}}}profile"):
        meta.remove(el)
    return ET.tostring(root, encoding="unicode")


class ProfileOptionTest(unittest.TestCase):
    def test_default_off_everywhere(self):
        self.assertFalse(vm.VmProfile(name="X").guest_agent)
        for p in vm.PROFILES.values():
            self.assertFalse(p.guest_agent)
            ctrl, chan = guest_parts(ET.fromstring(vm.domain_xml(full(p))))
            self.assertEqual((ctrl, chan), ([], []))
        twin, _notes = vm.profile_from_inventory({"dmi": {"sys_vendor": "HP", "product_name": "EliteBook"},
                                                  "disks": [{"name": "sda", "size": 128 * 10**9, "pttype": "gpt",
                                                             "transport": "sata"}]}, vm.ServerInfo(), "Probe")
        self.assertFalse(twin.guest_agent)                          # Zwilling: nie mit Gastagent

    def test_old_profile_json_without_field(self):
        data = json.loads(full(vm.profile("VM-Klein")).to_json())
        data.pop("guest_agent")
        self.assertFalse(vm.VmProfile.from_dict(data).guest_agent)
        on = full(vm.profile("VM-Klein"))
        on.guest_agent = True
        self.assertTrue(vm.profile_from_xml(vm.domain_xml(on)).guest_agent)

    def test_xml_with_channel(self):
        for name in vm.PROFILES:
            with self.subTest(profile=name):
                p = full(vm.profile(name))
                p.guest_agent = True
                xml = vm.domain_xml(p)
                root = ET.fromstring(xml)
                ctrl, chan = guest_parts(root)
                self.assertEqual(len(ctrl), 1)
                self.assertEqual(ctrl[0].get("index"), "0")
                self.assertEqual(len(chan), 1)
                self.assertEqual(chan[0].get("type"), "unix")
                self.assertIsNone(chan[0].find("source"))               # Socket legt libvirt selbst an
                self.assertEqual(chan[0].find("target").attrib, {"type": "virtio", "name": CHANNEL})
                self.assertEqual(root.find("devices/memballoon").get("model"), "none")
                # sonst bleibt alles Standard-Hardware: virtio nur im Kanal und im Controller
                self.assertEqual(without_guest(xml).count("virtio"), 0)
                p.guest_agent = False
                self.assertEqual(without_guest(xml), without_guest(vm.domain_xml(p)))
                # auch für einen Start mit Agent bzw. von ISO
                p.guest_agent = True
                for boot in ("agent", "iso"):
                    self.assertEqual(len(guest_parts(ET.fromstring(vm.domain_xml(p, boot=boot, iso="/x.iso")))[1]),
                                     1)

    def test_texts(self):
        self.assertEqual(vm.GUEST_AGENT_LABEL, "Gastagent (nur Test-VMs)")
        self.assertEqual(vm.GUEST_AGENT_MASTER_WARNING, "VM mit Gastagent – virtio-Treiber und qemu-ga sind im "
                                                        "Image. Für Master-Images ohne Gastagent arbeiten.")
        self.assertIn("Standard-Hardware", vm.GUEST_AGENT_TIP)
        a = vm.profile("VM-Klein")
        b = copy.deepcopy(a)
        b.guest_agent = True
        self.assertEqual(vm.profile_changes(a, b), ["Gastagent aus → an"])
        self.assertEqual(vm.profile_changes(b, a), ["Gastagent an → aus"])
        self.assertEqual(vm.profile_changes(a, a), [])
        self.assertTrue(vm.describe(b).endswith(" · Gastagent"))
        self.assertNotIn("Gastagent", vm.describe(a))
        self.assertEqual(vm.guest_agent_text(True), "Gastagent: antwortet")
        self.assertEqual(vm.guest_agent_text(False), "Gastagent: keine Antwort")
        self.assertEqual(vm.guest_agent_text(None), "Gastagent: wird geprüft …")
        self.assertEqual(vm.guest_agent_text(True, "shut off"), "Gastagent: VM nicht eingeschaltet")


class SwitchTest(unittest.TestCase):
    """Ein-/Ausschalten über „Hardware ändern …“ (set_profile, VM aus) ändert nur Kanal und Controller."""

    def setUp(self):
        self.fake = FakeVirsh()
        self.v = vm.Virsh(run=self.fake, sleep=lambda _s: None)
        self.p = self.v.create(vm.profile("VM-Win11"), "T")

    def test_on_off_changes_only_channel(self):
        before = self.fake.domains["T"]
        on = self.v.get_profile("T")
        on.guest_agent = True
        self.v.set_profile("T", on)
        xml = self.fake.domains["T"]
        self.assertEqual([len(x) for x in guest_parts(ET.fromstring(xml))], [1, 1])
        self.assertEqual(without_guest(xml), without_guest(before))
        got = self.v.get_profile("T")
        self.assertTrue(got.guest_agent)
        self.assertEqual((got.nic.mac, got.smbios.uuid, got.disk.serial), (self.p.nic.mac, self.p.smbios.uuid,
                                                                         self.p.disk.serial))
        self.assertFalse(any(c[0] == "vol-resize" for c in self.fake.calls))
        got.guest_agent = False
        self.v.set_profile("T", got)
        self.assertEqual(self.fake.domains["T"], before)                  # aus → genau wie vorher

    def test_only_when_off(self):
        self.v.start("T")
        on = self.v.get_profile("T")
        on.guest_agent = True
        with self.assertRaisesRegex(vm.VmError, "ausgeschalteter VM"):
            self.v.set_profile("T", on)

    def test_start_keeps_channel(self):
        on = self.v.get_profile("T")
        on.guest_agent = True
        self.v.set_profile("T", on)
        self.v.start("T", "agent")                       # definiert zweimal neu (Startreihenfolge)
        self.assertEqual(len(guest_parts(ET.fromstring(self.fake.started_xml["T"]))[1]), 1)
        self.assertEqual(len(guest_parts(ET.fromstring(self.fake.domains["T"]))[1]), 1)


class ChainTest(unittest.TestCase):
    """Snapshots, Start mit Overlay-Kette und Löschen funktionieren mit Gastagent wie ohne."""

    def setUp(self):
        self.fake = ChainFake()
        self.v = vm.Virsh(run=self.fake, sleep=lambda _s: None)
        p = vm.profile("VM-Legacy")
        p.disk.size_gb = 2
        p.guest_agent = True
        self.v.create(p, "G")
        self.fake.write("G", "boot", "Windows")

    def channel(self, xml: str) -> int:
        return len(guest_parts(ET.fromstring(xml))[1])

    def test_snapshots_and_chain(self):
        a = self.v.snapshot_create("G", "vor Test")
        self.assertEqual(self.channel(self.fake.domains["G"]), 1)
        self.assertEqual(self.fake.top("G"), POOL + "G.snap-1.qcow2")
        self.fake.write("G", "boot", "kaputt")
        self.v.start("G", "agent")                                    # Start mit Overlay-Kette
        self.assertIn(POOL + "G.snap-1.qcow2", self.fake.started_xml["G"])
        self.assertEqual(self.channel(self.fake.started_xml["G"]), 1)
        b = self.v.snapshot_create("G", "auto", auto=True, running_ok=True)     # bei laufender VM (libvirt)
        self.assertEqual(self.channel(self.fake.domains["G"]), 1)
        self.v.poweroff("G")
        self.v.snapshot_revert("G", a.id)
        self.assertEqual(self.fake.content(self.fake.top("G")), {"boot": "Windows"})
        self.assertEqual(self.channel(self.fake.domains["G"]), 1)
        self.v.snapshot_delete("G", b.id)
        self.v.snapshot_delete("G", a.id)
        self.assertEqual(self.v.snapshots("G"), [])
        self.assertEqual(self.channel(self.fake.domains["G"]), 1)
        self.assertTrue(self.v.get_profile("G").guest_agent)
        # Hilfs-VM zum Zusammenführen: nur die Disk, nie ein Kanal
        self.assertNotIn("channel", vm.helper_xml("okula-merge-G", POOL + "G.qcow2"))

    def test_switch_off_with_snapshots_keeps_chain(self):
        self.v.snapshot_create("G", "x")
        top = self.fake.top("G")
        p = self.v.get_profile("G")
        p.guest_agent = False
        self.v.set_profile("G", p)
        self.assertEqual(self.fake.top("G"), top)                      # Disk-Datei bleibt das Overlay
        self.assertEqual(len(self.v.snapshots("G")), 1)
        self.assertEqual(self.channel(self.fake.domains["G"]), 0)


class PingTest(unittest.TestCase):
    def run_with(self, returncode: int, out: str, err: str = ""):
        calls = []

        def run(cmd, _input=None):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, returncode, out, err)

        return vm.Virsh(run=run).guest_ping("T"), calls

    def test_ping(self):
        ok, calls = self.run_with(0, '{"return":{}}\n')
        self.assertTrue(ok)
        cmd = calls[0]
        self.assertEqual(cmd[:4], ["virsh", "-c", vm.URI, "qemu-agent-command"])
        self.assertIn("T", cmd)
        self.assertEqual(cmd[cmd.index("--timeout") + 1], str(vm.GUEST_PING_TIMEOUT))
        self.assertEqual(json.loads(cmd[-1]), {"execute": "guest-ping"})
        self.assertFalse(self.run_with(1, "", "error: Guest agent is not responding: QEMU guest agent is not "
                                              "connected")[0])
        self.assertFalse(self.run_with(1, "", "error: argument unsupported: QEMU guest agent is not configured")[0])
        self.assertFalse(self.run_with(0, "Unsinn")[0])

        def missing(cmd, _input=None):
            raise FileNotFoundError("virsh")

        self.assertFalse(vm.Virsh(run=missing).guest_ping("T"))


class GuestToolsLibraryTest(unittest.TestCase):
    """Gasttools aus Fedora virtio-win über die Software-Bibliothek: Typ und stille Parameter."""

    BURN = pe_file(sections=(".text", ".wixburn"), resources={16: version_resource(
        {"CompanyName": "Red Hat, Inc.", "ProductName": "Virtio-win-guest-tools", "ProductVersion": "0.1.271.1"})})

    def test_burn_bundle(self):
        found = software.detect_bytes(self.BURN, "virtio-win-guest-tools.exe")
        self.assertEqual((found["kind"], found["args"], found["exit_codes"], found["hint"]),
                         ("virtio", "/install /quiet /norestart", [0, 1638, 1641, 3010], ""))
        self.assertEqual((found["program"], found["version"], found["publisher"]),
                         ("Virtio-win-guest-tools", "0.1.271.1", "Red Hat, Inc."))
        # ohne Versionsinfo: am Dateinamen
        bare = software.detect_bytes(pe_file(sections=(".text", ".wixburn")), "virtio-win-guest-tools.exe")
        self.assertEqual((bare["kind"], bare["args"]), ("virtio", "/install /quiet /norestart"))
        # andere Burn-Pakete bleiben wie bisher
        self.assertEqual(software.detect_bytes(pe_file(sections=(".text", ".wixburn")), "setup.exe")["kind"], "wix")

    def test_msi_packages(self):
        for name, props in (("virtio-win-gt-x64.msi", {"ProductName": "Virtio-win-driver-installer",
                                                       "ProductVersion": "0.1.271", "Manufacturer": "Red Hat, Inc."}),
                            ("qemu-ga-x86_64.msi", {"ProductName": "QEMU guest agent", "ProductVersion": "109.0.0",
                                                    "Manufacturer": "RedHat"})):
            with self.subTest(name=name):
                found = software.detect_bytes(msi(props), name)
                self.assertEqual((found["kind"], found["args"], found["exit_codes"]),
                                 ("msi", "/qn /norestart", [0, 1641, 3010]))
                self.assertEqual(found["program"], props["ProductName"])

    def test_loaded_into_library_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "quelle" / "virtio-win-guest-tools.exe"
            src.parent.mkdir()
            src.write_bytes(self.BURN)
            e = software.load(Path(tmp) / "nas", src).entry
            self.assertEqual((e.status, e.args, e.kind_label), (software.READY, "/install /quiet /norestart",
                                                                "virtio-win-Gasttools (Burn)"))
            self.assertEqual(software.script_kind(e), "exe")


class HelpTest(unittest.TestCase):
    def test_help_describes_option_and_tools(self):
        text = dict(CHAPTERS)["Virtuelle Maschinen"]
        for needle in ("Gastagent (nur Test-VMs)", "virtio-win-guest-tools.exe", "qemu-agent-command", "guest-ping",
                       "Hardware ändern", "VM mit Gastagent"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
