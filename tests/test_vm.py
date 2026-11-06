"""Virtuelle Maschinen (I-001): Profile, libvirt-XML, MAC-Eindeutigkeit, Aktionen mit nachgebildetem virsh."""

import random
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from okula_recovery import vm

Q = f"{{{vm.QEMU_NS}}}"


def parse(p, **kw):
    return ET.fromstring(vm.domain_xml(vm.fill_identity(p, rng=random.Random(1)), **kw))


def sysinfo(root, block):
    return {e.get("name"): e.text for e in root.findall(f"sysinfo/{block}/entry")}


class ProfileXmlTest(unittest.TestCase):
    def test_three_profiles_as_in_concept(self):
        self.assertEqual(list(vm.PROFILES), ["VM-Win11", "VM-Legacy", "VM-Klein"])
        w, l, k = (vm.PROFILES[n] for n in vm.PROFILES)
        self.assertEqual((w.firmware, w.tpm, w.chipset, w.disk.bus, w.disk.size_gb, w.nic.model, w.cpu.cores,
                          w.ram_mb), ("uefi-sb", True, "q35", "nvme", 128, "e1000e", 4, 8192))
        self.assertEqual((l.firmware, l.tpm, l.chipset, l.disk.bus, l.disk.size_gb, l.disk.rpm, l.nic.model,
                          l.cpu.cores, l.ram_mb), ("bios", False, "i440fx", "sata", 80, 7200, "e1000", 2, 4096))
        self.assertEqual((k.firmware, k.tpm, k.chipset, k.disk.bus, k.disk.size_gb, k.disk.rpm, k.nic.model,
                          k.cpu.cores, k.ram_mb), ("uefi", False, "q35", "sata", 64, 0, "e1000e", 2, 4096))
        for p in vm.PROFILES.values():
            self.assertEqual((p.smbios.manufacturer, p.smbios.product), ("Okula", p.name))
            p.validate()

    def test_no_virtio_anywhere(self):
        for p in vm.PROFILES.values():
            for boot in ("normal", "pxe"):
                self.assertNotIn("virtio", vm.domain_xml(vm.fill_identity(p), boot=boot))
            self.assertNotIn("virtio", vm.domain_xml(vm.fill_identity(p), boot="iso", iso="/x.iso"))
            self.assertEqual(parse(p).find("devices/memballoon").get("model"), "none")

    def test_win11_uefi_secure_boot_tpm_nvme(self):
        r = parse(vm.PROFILES["VM-Win11"])
        self.assertEqual(r.get("type"), "kvm")
        os_el = r.find("os")
        self.assertEqual(os_el.get("firmware"), "efi")
        self.assertEqual(os_el.find("type").get("machine"), "q35")
        feats = {f.get("name"): f.get("enabled") for f in os_el.findall("firmware/feature")}
        self.assertEqual(feats, {"secure-boot": "yes", "enrolled-keys": "yes"})
        self.assertEqual(os_el.find("loader").get("secure"), "yes")
        self.assertEqual(r.find("features/smm").get("state"), "on")
        tpm = r.find("devices/tpm")
        self.assertEqual((tpm.get("model"), tpm.find("backend").get("type"), tpm.find("backend").get("version")),
                         ("tpm-crb", "emulator", "2.0"))
        self.assertEqual(r.find("vcpu").text, "4")
        self.assertEqual(r.find("memory").text, "8192")
        # NVMe: libvirt 11.3 kennt den Bus nicht → SATA-Disk, per qemu:override zum Gerät „nvme“
        props = {p.get("name"): (p.get("type"), p.get("value"))
                 for p in r.findall(f"{Q}override/{Q}device[@alias='ua-disk0']/{Q}frontend/{Q}property")}
        self.assertEqual(props["driver"], ("string", "nvme"))
        self.assertEqual(props["bus"], ("string", "pcie.0"))
        self.assertEqual(props["model"], ("remove", None))
        self.assertEqual(r.find("devices/disk/alias").get("name"), "ua-disk0")
        self.assertIsNone(r.find("devices/disk/product"))
        meta = vm.profile_from_xml(ET.tostring(r, encoding="unicode"))
        self.assertEqual((meta.disk.bus, meta.disk.size_gb), ("nvme", 128))

    def test_legacy_bios_i440fx_sata_hdd_e1000(self):
        r = parse(vm.PROFILES["VM-Legacy"])
        self.assertIsNone(r.find("os").get("firmware"))            # SeaBIOS
        self.assertIsNone(r.find("os/firmware"))
        self.assertEqual(r.find("os/type").get("machine"), "pc")
        self.assertIsNone(r.find("devices/tpm"))
        target = r.find("devices/disk/target")
        self.assertEqual((target.get("bus"), target.get("rotation_rate")), ("sata", "7200"))
        self.assertEqual(r.find("devices/disk/product").text, "Okula SATA HDD 80GB")
        self.assertEqual(r.find("devices/interface/model").get("type"), "e1000")     # Treiber in Windows
        self.assertIsNone(r.find(f"{Q}override"))

    def test_disk_as_file_in_pool_dir(self):
        # Pool-Volume (type="volume") bekommt keine AppArmor-Freigabe → Datei im Pool-Verzeichnis
        for p in vm.PROFILES.values():
            xml = vm.domain_xml(vm.fill_identity(p))
            disk = ET.fromstring(xml).find("devices/disk[@device='disk']")
            self.assertEqual(disk.get("type"), "file")
            self.assertEqual(disk.find("source").attrib,
                             {"file": f"/var/lib/libvirt/images/okula/{p.name}.qcow2"})
            self.assertEqual(disk.find("driver").get("type"), "qcow2")
            self.assertEqual(disk.find("alias").get("name"), "ua-disk0")
            self.assertNotIn("pool=", xml)
            self.assertNotIn('type="volume"', xml)

    def test_nic_models(self):
        self.assertEqual(vm.NIC_MODELS, ("e1000e", "e1000", "rtl8139"))
        p = vm.profile("VM-Klein")
        p.nic.model = "rtl8139"                         # bleibt erlaubt (Linux)
        p.validate()

    def test_install_has_spice_module(self):
        install = (Path(__file__).resolve().parent.parent / "install.sh").read_text()
        self.assertIn("qemu-system-modules-spice", install)

    def test_klein_uefi_without_secure_boot(self):
        r = parse(vm.PROFILES["VM-Klein"])
        self.assertEqual(r.find("os").get("firmware"), "efi")
        feats = {f.get("name"): f.get("enabled") for f in r.findall("os/firmware/feature")}
        self.assertEqual(feats, {"secure-boot": "no", "enrolled-keys": "no"})
        self.assertIsNone(r.find("features/smm"))
        self.assertIsNone(r.find("devices/tpm"))
        self.assertEqual(r.find("devices/disk/target").get("rotation_rate"), "1")   # SSD
        self.assertEqual(vm.profile_from_xml(vm.domain_xml(vm.fill_identity(vm.PROFILES["VM-Klein"]))).disk.size_gb, 64)

    def test_network_bridge_mac_and_boot_order(self):
        p = vm.fill_identity(vm.PROFILES["VM-Klein"])
        r = ET.fromstring(vm.domain_xml(p))
        nic = r.find("devices/interface")
        self.assertEqual(nic.get("type"), "bridge")
        self.assertEqual(nic.find("source").get("bridge"), "br0")
        self.assertEqual(nic.find("mac").get("address"), p.nic.mac)
        self.assertEqual(nic.find("model").get("type"), "e1000e")
        self.assertEqual((r.find("devices/disk/boot").get("order"), nic.find("boot").get("order")), ("1", "2"))
        pxe = ET.fromstring(vm.domain_xml(p, boot="pxe"))
        self.assertEqual((pxe.find("devices/disk/boot").get("order"),
                          pxe.find("devices/interface/boot").get("order")), ("2", "1"))
        iso = ET.fromstring(vm.domain_xml(p, boot="iso", iso="/srv/win11.iso"))
        cd = iso.find("devices/disk[@device='cdrom']")
        self.assertEqual((cd.find("source").get("file"), cd.find("boot").get("order")), ("/srv/win11.iso", "1"))
        self.assertIsNotNone(cd.find("readonly"))
        self.assertEqual(r.find("devices/graphics").get("type"), "spice")
        self.assertEqual(r.find("devices/graphics/listen").get("address"), "127.0.0.1")

    def test_smbios_values(self):
        p = vm.fill_identity(vm.PROFILES["VM-Win11"], rng=random.Random(5))
        r = ET.fromstring(vm.domain_xml(p))
        self.assertEqual(r.find("sysinfo").get("type"), "smbios")
        self.assertEqual(r.find("os/smbios").get("mode"), "sysinfo")
        system = sysinfo(r, "system")
        self.assertEqual((system["manufacturer"], system["product"], system["family"]), ("Okula", "VM-Win11", "Okula VM"))
        self.assertEqual(system["uuid"], r.find("uuid").text)                 # libvirt verlangt Gleichheit
        self.assertTrue(system["serial"].startswith("VM-"))
        self.assertEqual(sysinfo(r, "bios"), {"vendor": "Okula", "version": "1.0", "date": "11/06/2026"})
        self.assertEqual(sysinfo(r, "baseBoard")["product"], "VM-Win11-Board")
        self.assertEqual(sysinfo(r, "chassis")["manufacturer"], "Okula")

    def test_cpu_name_and_topology(self):
        p = vm.profile("VM-Klein")
        p.cpu = vm.CpuSpec(cores=2, threads=2, name="Intel(R) Core(TM) i5-4200U CPU @ 1.60GHz, test")
        r = parse(p)
        self.assertEqual(r.find("vcpu").text, "4")
        topo = r.find("cpu/topology")
        self.assertEqual((topo.get("cores"), topo.get("threads")), ("2", "2"))
        args = [a.get("value") for a in r.findall(f"{Q}commandline/{Q}arg")]
        self.assertEqual(args[0], "-global")
        self.assertIn("property=model-id,value=Intel(R) Core(TM) i5-4200U CPU @ 1.60GHz,, test", args[1])
        self.assertIsNone(parse(vm.PROFILES["VM-Klein"]).find(f"{Q}commandline"))

    def test_validation(self):
        for change in (lambda p: setattr(p, "name", "a b"), lambda p: setattr(p.disk, "bus", "virtio"),
                       lambda p: setattr(p.nic, "model", "virtio"), lambda p: setattr(p, "chipset", "i440fx"),
                       lambda p: setattr(p.nic, "mac", "aa:bb:cc:dd:ee:ff")):
            p = vm.profile("VM-Win11")
            change(p)
            with self.assertRaises(vm.VmError):
                p.validate()

    def test_profile_roundtrip(self):
        p = vm.fill_identity(vm.PROFILES["VM-Legacy"])
        self.assertEqual(vm.profile_from_xml(vm.domain_xml(p)), p)
        self.assertIsNone(vm.profile_from_xml("<domain><name>fremd</name></domain>"))
        self.assertIsNone(vm.profile_from_xml("kein xml"))


class MacTest(unittest.TestCase):
    def test_format_and_unique(self):
        rng = random.Random(3)
        mac = vm.new_mac(set(), rng)
        self.assertRegex(mac, r"^52:54:00(:[0-9a-f]{2}){3}$")
        taken = {vm.new_mac(set(), random.Random(3))}
        self.assertNotIn(vm.new_mac(taken, random.Random(3)), taken)

    def test_all_taken_fails(self):
        class Fixed(random.Random):
            def randrange(self, *_):
                return 7
        with self.assertRaises(vm.VmError):
            vm.new_mac({"52:54:00:07:07:07"}, Fixed())


class FakeVirsh:
    """Nachgebildetes virsh: Domains und Volumes im Speicher."""

    def __init__(self):
        self.domains: dict[str, str] = {}
        self.states: dict[str, str] = {}
        self.volumes: dict[str, int] = {}
        self.calls: list[list[str]] = []
        self.started_xml: dict[str, str] = {}
        self.fail: dict[str, str] = {}

    def __call__(self, cmd, input_text=None):
        self.assertPrefix(cmd)
        args = cmd[3:]
        self.calls.append(args)
        op = args[0]
        if op in self.fail:
            return subprocess.CompletedProcess(cmd, 1, "", self.fail[op])
        out = ""
        if op == "list":
            out = "\n".join(self.domains) + "\n"
        elif op == "dumpxml":
            name = args[-1]
            if name not in self.domains:
                return subprocess.CompletedProcess(cmd, 1, "", f"error: failed to get domain '{name}'\nerror: Domain not found")
            out = self.domains[name]
        elif op == "domstate":
            out = self.states[args[1]] + "\n"
        elif op == "define":
            xml = Path(args[1]).read_text()
            name = ET.fromstring(xml).find("name").text
            self.domains[name] = xml
            self.states.setdefault(name, "shut off")
        elif op == "vol-create-as":
            self.volumes[args[2]] = int(args[3])
        elif op == "vol-resize":
            self.volumes[args[3]] = int(args[4])
        elif op == "vol-delete":
            self.volumes.pop(args[-1], None)
        elif op == "start":
            self.states[args[1]] = "running"
            self.started_xml[args[1]] = self.domains[args[1]]
        elif op in ("destroy", "shutdown"):
            self.states[args[1]] = "shut off"
        elif op == "undefine":
            self.domains.pop(args[1])
            self.states.pop(args[1])
            self.volumes.pop(vm.volume_name(args[1]), None)
        return subprocess.CompletedProcess(cmd, 0, out, "")

    @staticmethod
    def assertPrefix(cmd):
        assert cmd[:3] == ["virsh", "-c", "qemu:///system"], cmd


class ActionsTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeVirsh()
        self.v = vm.Virsh(run=self.fake)

    def test_create_list_state(self):
        p = self.v.create(vm.PROFILES["VM-Win11"])
        self.assertIn(["vol-create-as", "okula", "VM-Win11.qcow2", str(128 * 10**9), "--format", "qcow2"],
                      self.fake.calls)
        self.assertRegex(p.nic.mac, r"^52:54:00")
        self.assertFalse(vm.PROFILES["VM-Win11"].nic.mac)                  # Vorlage unverändert
        vms = self.v.list()
        self.assertEqual([(x["name"], x["state"]) for x in vms], [("VM-Win11", "shut off")])
        self.assertEqual(vms[0]["profile"], p)

    def test_foreign_domains_ignored(self):
        self.fake.domains["fremd"] = "<domain><name>fremd</name><devices><interface><mac address='52:54:00:aa:bb:cc'/></interface></devices></domain>"
        self.fake.states["fremd"] = "running"
        self.assertEqual(self.v.list(), [])
        self.assertIn("52:54:00:aa:bb:cc", self.v.used_macs())
        with self.assertRaises(vm.VmError):
            self.v.delete("fremd")

    def test_macs_unique_across_vms(self):
        macs = {self.v.create(vm.PROFILES["VM-Klein"], name=f"Klein-{i}").nic.mac for i in range(20)}
        self.assertEqual(len(macs), 20)
        p = vm.profile("VM-Legacy")
        p.nic.mac = next(iter(macs))
        with self.assertRaises(vm.VmError):
            self.v.create(p)

    def test_duplicate_name_refused(self):
        self.v.create(vm.PROFILES["VM-Klein"])
        with self.assertRaisesRegex(vm.VmError, "gibt es schon"):
            self.v.create(vm.PROFILES["VM-Klein"])

    def test_define_failure_removes_volume(self):
        self.fake.fail["define"] = "error: XML error: bad"
        with self.assertRaises(vm.VmError):
            self.v.create(vm.PROFILES["VM-Klein"])
        self.assertEqual(self.fake.volumes, {})

    def test_start_modes_once(self):
        self.v.create(vm.PROFILES["VM-Klein"])
        self.v.start("VM-Klein", "pxe")
        started = ET.fromstring(self.fake.started_xml["VM-Klein"])
        self.assertEqual(started.find("devices/interface/boot").get("order"), "1")
        after = ET.fromstring(self.fake.domains["VM-Klein"])              # nächster Start wieder normal
        self.assertEqual(after.find("devices/disk/boot").get("order"), "1")
        with self.assertRaisesRegex(vm.VmError, "läuft bereits"):
            self.v.start("VM-Klein")
        self.v.shutdown("VM-Klein")
        self.assertIn(["shutdown", "VM-Klein", "--mode", "acpi"], self.fake.calls)
        with tempfile.NamedTemporaryFile(suffix=".iso") as iso:
            self.v.start("VM-Klein", "iso", iso.name)
            cd = ET.fromstring(self.fake.started_xml["VM-Klein"]).find("devices/disk[@device='cdrom']")
            self.assertEqual(cd.find("source").get("file"), iso.name)
        self.assertIsNone(ET.fromstring(self.fake.domains["VM-Klein"]).find("devices/disk[@device='cdrom']"))
        self.v.poweroff("VM-Klein")
        self.assertIn(["destroy", "VM-Klein"], self.fake.calls)
        with self.assertRaisesRegex(vm.VmError, "ISO-Datei nicht gefunden"):
            self.v.start("VM-Klein", "iso", "/gibt/es/nicht.iso")
        with self.assertRaises(vm.VmError):
            self.v.start("VM-Klein", "usb")

    def test_delete_with_disk(self):
        self.v.create(vm.PROFILES["VM-Win11"])
        self.v.start("VM-Win11")
        self.v.delete("VM-Win11")
        self.assertIn(["undefine", "VM-Win11", "--nvram", "--tpm", "--remove-all-storage"], self.fake.calls)
        self.assertEqual((self.fake.domains, self.fake.volumes), ({}, {}))

    def test_set_profile(self):
        p = self.v.create(vm.PROFILES["VM-Klein"])
        new = vm.profile("VM-Klein")
        new.disk.size_gb, new.ram_mb = 100, 6144
        changed = self.v.set_profile("VM-Klein", new)
        self.assertEqual((changed.nic.mac, changed.smbios.uuid), (p.nic.mac, p.smbios.uuid))
        self.assertEqual(self.fake.volumes["VM-Klein.qcow2"], 100 * 10**9)
        self.assertEqual(self.v.get_profile("VM-Klein").ram_mb, 6144)
        new.disk.size_gb = 50
        with self.assertRaisesRegex(vm.VmError, "verkleinern"):
            self.v.set_profile("VM-Klein", new)
        self.v.start("VM-Klein")
        with self.assertRaisesRegex(vm.VmError, "ausgeschalteter"):
            self.v.set_profile("VM-Klein", vm.profile("VM-Klein"))

    def test_errors_are_german_messages(self):
        self.fake.fail["list"] = "error: failed to connect to the hypervisor\nerror: Permission denied"
        with self.assertRaisesRegex(vm.VmError, "libvirt nicht erreichbar"):
            self.v.list()
        with self.assertRaisesRegex(vm.VmError, "VM nicht gefunden"):
            vm.Virsh(run=FakeVirsh()).get_profile("weg")
        msg = vm.Virsh._message("start", "error: Failed to start domain 'X'\nerror: internal error: qemu "
                                "unexpectedly closed the monitor: Could not open "
                                "'/var/lib/libvirt/images/okula/X.qcow2': Permission denied")
        self.assertIn("Disk-Datei der VM nicht lesbar", msg)
        msg = vm.Virsh._message("define", "error: unsupported configuration: spice graphics are not "
                                "supported with this QEMU")
        self.assertIn("SPICE", msg)

        def missing(cmd, input_text=None):
            raise FileNotFoundError("virsh")
        with self.assertRaisesRegex(vm.VmError, "virsh nicht gefunden"):
            vm.Virsh(run=missing).list()


if __name__ == "__main__":
    unittest.main()
