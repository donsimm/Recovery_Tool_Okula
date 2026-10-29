"""Linux-Direktinstallation: Bausteine und Ende-zu-Ende (Tool → Agent) auf einer Loop-Disk."""

import gzip
import re
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from okula_recovery import agent, jobs, linuxsetup, oslib, wininstall, wire
from tests.isofixtures import HAVE_TOOLS, fedora_iso, linux_iso
from tests.test_restore import can_run, loop_disks, sh

try:
    import yaml
except ImportError:  # nur für die YAML-Prüfung
    yaml = None

UBUNTU_INFO = 'Ubuntu 24.04.1 LTS "Noble Numbat" - Release amd64 (20240827)'
DEBIAN_INFO = 'Debian GNU/Linux 13.0.0 "Trixie" - Official amd64 NETINST with firmware 20250809-11:21'


def read_cpio(data: bytes) -> dict[str, bytes]:
    files, pos = {}, 0
    while True:
        h = data[pos:pos + 110].decode()
        assert h.startswith("070701"), h[:6]
        size, namesize = int(h[54:62], 16), int(h[94:102], 16)
        pos += 110
        name = data[pos:pos + namesize - 1].decode()
        pos += namesize + (-(110 + namesize) % 4)
        if name == "TRAILER!!!":
            return files
        files[name] = data[pos:pos + size]
        pos += size + (-size % 4)


@unittest.skipUnless(HAVE_TOOLS, "genisoimage oder xorriso fehlt")
class FedoraDetectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dvd_netinst_live_nobara(self):
        dvd = oslib.inspect(fedora_iso(self.d))
        self.assertEqual(dvd["linux"]["kind"], "anaconda")
        self.assertTrue(dvd["linux"]["repo"])
        self.assertEqual(linuxsetup.kind(dvd), "fedora")
        net = oslib.inspect(fedora_iso(self.d, "Fedora-Everything-netinst-x86_64-42.iso", "netinst"))
        self.assertFalse(net["linux"]["repo"])
        self.assertEqual(linuxsetup.kind(net), "fedora")
        live = oslib.inspect(fedora_iso(self.d, "Fedora-Workstation-Live-42.iso", "live",
                                        "Fedora-WS-Live-42", treeinfo=False))
        self.assertEqual(live["linux"]["kind"], "fedora-live")
        self.assertIn("Everything- oder Server-ISO", oslib.install_reason(live))
        nobara = oslib.inspect(fedora_iso(self.d, "Nobara-44-KDE.iso", "live", "Nobara-44-KDE", treeinfo=False))
        self.assertEqual(nobara["linux"]["distro"], "nobara")
        self.assertIn("Calamares", oslib.install_reason(nobara))

    def test_kickstart(self):
        dvd = oslib.inspect(fedora_iso(self.d))
        opts = linuxsetup.LinuxOptions("Okula", "pw1234", "Empfang 2", desktop=False)
        ks = linuxsetup.kickstart(opts, "$6$x$y", "/dev/nvme0n1", dvd)
        self.assertIn("ignoredisk --only-use=nvme0n1", ks)
        self.assertIn("clearpart --none\nautopart", ks)
        self.assertIn("user --name=okula --gecos=\"Okula\" --groups=wheel --iscrypted --password=$6$x$y", ks)
        self.assertIn("@^server-product-environment", ks)
        self.assertIn("# Pakete von der ISO", ks)          # DVD ohne Desktop: offline
        self.assertIn("keyboard --xlayouts='ch'", ks)
        self.assertIn("network --bootproto=dhcp --activate --hostname=empfang-2", ks)
        online = linuxsetup.kickstart(linuxsetup.LinuxOptions("Okula", "pw1234", "x"), "$6$x$y", "/dev/sda", dvd)
        self.assertIn("repo=fedora-$releasever&arch=$basearch", online)
        self.assertIn("repo=updates-released-f$releasever", online)
        self.assertIn("@^workstation-product-environment", online)


class PartsTest(unittest.TestCase):
    def test_names_and_password(self):
        self.assertEqual(linuxsetup.hostname("DoNs_EliteBook 2 Zürich"), "dons-elitebook-2-zuerich")
        self.assertEqual(linuxsetup.username("Okula"), "okula")
        with self.assertRaises(linuxsetup.LinuxSetupError):
            linuxsetup.username("1abc")
        with self.assertRaises(linuxsetup.LinuxSetupError):
            linuxsetup.username("root")
        h = linuxsetup.hash_password("Grüezi 2026")
        self.assertTrue(h.startswith("$6$"))
        with self.assertRaises(linuxsetup.LinuxSetupError):
            linuxsetup.hash_password("x")

    def test_kind_from_meta(self):
        ub = {"family": "linux", "linux": {"kind": "casper", "distro": "ubuntu", "version": "24.04.1", "info": UBUNTU_INFO}}
        self.assertEqual(linuxsetup.kind(ub), "ubuntu")
        self.assertEqual(linuxsetup.kind({"linux": {**ub["linux"], "version": "22.04.4"}}), "")
        deb = {"family": "linux", "linux": {"kind": "debian-installer", "distro": "debian", "version": "13.0.0", "info": DEBIAN_INFO}}
        self.assertEqual(linuxsetup.kind(deb), "debian")
        self.assertEqual(linuxsetup.codename(deb), "trixie")
        self.assertTrue(oslib.installable(ub) and oslib.installable(deb))

    def test_reasons_for_not_installable(self):
        def lx(info, kind="casper", distro="ubuntu", version="24.04.1", title="X"):
            return {"family": "linux", "title": title,
                    "linux": {"kind": kind, "distro": distro, "version": version, "info": info}}
        zorin = lx('Zorin OS 18.1 "Core" - amd64', title="Zorin-OS 18.1 Core 64bit")
        self.assertIn("Ubiquity/Calamares", oslib.install_reason(zorin))
        kubuntu = lx('Kubuntu 24.04.1 LTS "Noble Numbat" - Release amd64', distro="ubuntu")
        self.assertFalse(oslib.installable(kubuntu))
        self.assertIn("älter als 24.04", oslib.install_reason(lx('Ubuntu 22.04.4 LTS "Jammy"', version="22.04.4")))
        nobara = lx("Nobara 44 KDE", kind="fedora-live", distro="nobara", version="44", title="Nobara-44-KDE")
        self.assertIn("Calamares", oslib.install_reason(nobara))
        win32 = {"family": "windows", "windows": {"product": "Windows 10", "arch": "x86"}}
        self.assertIn("64-Bit", oslib.install_reason(win32))
        self.assertIn("nur als Boot-Stick", oslib.install_reason({"family": "other"}))

    def test_table_gap_and_sizes(self):
        tbl, parts = linuxsetup.table(256 * 1000**3, 7 * 1024**3)
        starts = [int(x) for x in re.findall(r"start=(\d+)", tbl)]
        sizes = [int(x) for x in re.findall(r"size=(\d+)", tbl)]
        self.assertEqual(starts[0], 2048)
        self.assertGreater(starts[1] - (starts[0] + sizes[0]), 200 * 1000**3 // 512)  # Lücke für das System
        self.assertEqual(starts[1] + sizes[1], starts[2])
        self.assertLessEqual(starts[2] + sizes[2], 256 * 1000**3 // 512 - 34)
        self.assertEqual([p["key"] for p in parts], ["esp", "setup", "cidata"])
        with self.assertRaisesRegex(linuxsetup.LinuxSetupError, "zu klein"):
            linuxsetup.table(30 * 1000**3, 7 * 1024**3)

    @unittest.skipUnless(yaml, "PyYAML fehlt")
    def test_ubuntu_userdata_is_valid_autoinstall(self):
        opts = linuxsetup.LinuxOptions("Okula", "pw1234", "DoNs EliteBook")
        data = yaml.safe_load(linuxsetup.ubuntu_userdata(opts, "$6$salz$hash"))
        ai = data["autoinstall"]
        self.assertEqual(ai["identity"], {"hostname": "dons-elitebook", "realname": "Okula", "username": "okula",
                                          "password": "$6$salz$hash"})
        self.assertEqual(ai["storage"], {"layout": {"name": "direct", "mode": "use_gap"}})
        self.assertEqual(ai["keyboard"], {"layout": "ch"})
        self.assertEqual(ai["timezone"], "Europe/Zurich")
        self.assertIn("okula-cleanup", " ".join(ai["late-commands"]))

    def test_software_selection(self):
        opts = linuxsetup.LinuxOptions("Okula", "pw1234", "Kasse 1", desktop_env="kde", ssh=True, web=True,
                                       standard=False, root_password="geheim",
                                       packages=linuxsetup.parse_packages("htop, curl  vim"))
        text = linuxsetup.debian_preseed(opts, "$6$x$y", "/dev/sda", "$6$r$s")
        self.assertIn("tasksel tasksel/first multiselect desktop, kde-desktop, web-server, ssh-server\n", text)
        self.assertIn("d-i passwd/root-login boolean true\nd-i passwd/root-password-crypted password $6$r$s", text)
        late = next(line for line in text.splitlines() if "late_command" in line)
        self.assertIn("usermod -aG sudo okula", late)
        self.assertIn("for p in htop curl vim; do apt-get install -y $p || true; done", late)
        self.assertNotIn("pkgsel/include", text)  # Tippfehler dürfen die Installation nicht anhalten
        server = linuxsetup.LinuxOptions("Okula", "pw1234", "x", desktop_env="")
        self.assertEqual(linuxsetup.debian_tasks(server), "standard")
        self.assertIn("passwd/root-login boolean false", linuxsetup.debian_preseed(server, "h", "/dev/sda"))
        # Ubuntu: SSH-Server, Pakete am Schluss
        ud = linuxsetup.ubuntu_userdata(opts, "h")
        self.assertIn("  ssh:\n    install-server: true\n    allow-pw: true\n", ud)
        if yaml:
            ai = yaml.safe_load(ud)["autoinstall"]
            self.assertEqual(ai["ssh"], {"install-server": True, "allow-pw": True})
            self.assertIn("apt-get install -y $p || true", ai["late-commands"][-1])
        # Fedora: sshd aktiv, fehlende Pakete überspringen
        ks = linuxsetup.kickstart(opts, "h", "/dev/sda", {"linux": {"distro": "fedora", "repo": True}})
        self.assertIn("services --enabled=sshd\nfirewall --enabled --service=ssh\n", ks)
        self.assertIn("%packages --ignoremissing\n@^workstation-product-environment\nopenssh-server\nhtop\n", ks)
        for bad in ("htop&rm", "a'b", "$(reboot)", "x|y", "-o"):
            with self.assertRaises(linuxsetup.LinuxSetupError):
                linuxsetup.parse_packages(bad)
        self.assertEqual(linuxsetup.parse_packages("@^server-product-environment g++ libc6:i386"),
                         ["@^server-product-environment", "g++", "libc6:i386"])

    def test_preseed_and_cpio(self):
        opts = linuxsetup.LinuxOptions("Okula", "pw1234", "Kasse 1", desktop=False)
        text = linuxsetup.debian_preseed(opts, "$6$x$y", "/dev/nvme0n1")
        self.assertIn("d-i partman-auto/disk string /dev/nvme0n1", text)
        self.assertIn("select biggest_free", text)
        self.assertIn("tasksel tasksel/first multiselect standard\n", text)
        self.assertIn("d-i netcfg/get_hostname string kasse-1", text)
        self.assertIn("d-i keyboard-configuration/xkb-keymap select ch", text)
        files = read_cpio(linuxsetup.cpio_newc({"preseed.cfg": text.encode()}))
        self.assertEqual(files["preseed.cfg"].decode(), text)

    def test_cleanup_script_removes_only_setup_partitions(self):
        s = linuxsetup.CLEANUP_SCRIPT
        self.assertIn("for label in OKULASETUP CIDATA", s)
        self.assertIn("resizepart", s)
        self.assertIn("resize2fs", s)


@unittest.skipUnless(can_run() and HAVE_TOOLS, "braucht root, Loop-Devices, genisoimage, xorriso")
class BootprepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        img = self.d / "disk.img"
        with open(img, "wb") as f:
            f.truncate(1536 * 1024 * 1024)
        self.dev = sh("losetup", "-fP", "--show", str(img)).strip()
        self.size = 1536 * 1024 * 1024
        self.key = bytes(range(32))
        self.efi = []
        (self.d / "efi").mkdir()

        def fake_efibootmgr(*args):
            self.efi.append(args)
            out = "Boot0000* Windows Boot Manager\n"
            if any("--create-only" in a for a in args) or len(self.efi) > 2:
                out += "Boot0003* Okula Linux-Installation\n"
            return out

        def mkfs(part, label=""):
            sh("mkfs.ext4", "-q", "-F", part)

        def mount(part, where, ntfs=False):
            where.mkdir(parents=True, exist_ok=True)
            sh("mount", part, str(where))

        self.patches = [
            mock.patch.object(wininstall, "EFI_DIR", self.d / "efi"),
            mock.patch.object(wininstall, "WORK", self.d / "work"),
            mock.patch.object(wininstall, "_mkfat", mkfs),
            mock.patch.object(wininstall, "_mount", mount),
            mock.patch.object(wininstall, "efibootmgr", fake_efibootmgr),
            mock.patch.object(linuxsetup, "MIN_GAP", 64 * 1024 * 1024),
            mock.patch.object(agent, "log", lambda *a, **k: None),
            mock.patch.object(agent.imaging, "list_disks", lambda: loop_disks(self.dev)),
            mock.patch.object(agent.threading, "Timer", lambda *a, **k: mock.Mock()),
        ]
        for p in self.patches:
            p.start()
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        ctx = wire.server_context(self.key)

        def serve():
            while True:
                try:
                    conn, addr = self.server.accept()
                except OSError:
                    return
                threading.Thread(target=agent.handle_connection, args=(ctx, conn, addr), daemon=True).start()

        threading.Thread(target=serve, daemon=True).start()

    def tearDown(self):
        self.server.close()
        for p in self.patches:
            p.stop()
        subprocess.run(["umount", str(self.d / "mnt")], capture_output=True)
        subprocess.run(["losetup", "-d", self.dev], capture_output=True)
        self.tmp.cleanup()

    def mounted(self, n):
        mnt = self.d / "mnt"
        mnt.mkdir(exist_ok=True)
        sh("mount", f"{self.dev}p{n}", str(mnt))
        return mnt

    def run_job(self, iso, meta, opts):
        jm = jobs.JobManager()
        results = []
        job = jm.start("dev", "linux", self.dev, "Linux",
                       jobs.linux_install_work("127.0.0.1", self.key, self.port, str(iso), meta, self.dev,
                                               self.size, opts, lambda j, b, e: results.append((b, e))))
        for _ in range(600):
            if not job.running:
                break
            threading.Event().wait(0.1)
        self.assertEqual(job.state, jobs.DONE, job.log)
        self.assertEqual(results, [("0003", None)])
        create = next(a for a in self.efi if "--create-only" in a)
        self.assertEqual(create[create.index("--part") + 1], "1")
        return job

    def test_ubuntu(self):
        iso = linux_iso(self.d, info=UBUNTU_INFO)
        meta = oslib.inspect(iso)
        self.run_job(iso, meta, linuxsetup.LinuxOptions("Okula", "pw1234", "PC Empfang"))
        table = sh("sfdisk", "-d", self.dev)
        self.assertEqual(len(re.findall(rf"^{self.dev}p\d", table, re.M)), 3)
        esp = self.mounted(1)
        try:
            self.assertTrue((esp / "EFI/boot/bootx64.efi").is_file())
            cfg = (esp / "boot/grub/grub.cfg").read_text()
            self.assertIn("loopback loop ($okula)/ubuntu.iso", cfg)
            self.assertIn("linux (loop)/casper/vmlinuz iso-scan/filename=/ubuntu.iso autoinstall", cfg)
        finally:
            sh("umount", str(esp))
        setup = self.mounted(2)
        try:
            self.assertEqual((setup / "ubuntu.iso").read_bytes(), iso.read_bytes())
        finally:
            sh("umount", str(setup))
        cidata = self.mounted(3)
        try:
            self.assertIn("mode: use_gap", (cidata / "user-data").read_text())
            self.assertTrue((cidata / "meta-data").read_text().startswith("instance-id: okula-"))
        finally:
            sh("umount", str(cidata))

    def test_fedora(self):
        iso = fedora_iso(self.d)
        meta = oslib.inspect(iso)
        self.run_job(iso, meta, linuxsetup.LinuxOptions("Okula", "pw1234", "Kasse 1", desktop=False))
        table = sh("sfdisk", "-d", self.dev)
        self.assertEqual(len(re.findall(rf"^{self.dev}p\d", table, re.M)), 2)  # EFI + Setup, kein CIDATA
        esp = self.mounted(1)
        try:
            self.assertEqual((esp / "okula/vmlinuz").read_bytes(), b"KERNEL" * 1000)
            cfg = (esp / "EFI/BOOT/grub.cfg").read_text()
            self.assertIn("inst.repo=hd:LABEL=OKULASETUP:/fedora.iso", cfg)
            self.assertIn("inst.ks=hd:LABEL=OKULAEFI:/okula/ks.cfg", cfg)
            self.assertIn(f"ignoredisk --only-use={self.dev.removeprefix('/dev/')}", (esp / "okula/ks.cfg").read_text())
        finally:
            sh("umount", str(esp))
        setup = self.mounted(2)
        try:
            self.assertEqual((setup / "fedora.iso").read_bytes(), iso.read_bytes())
        finally:
            sh("umount", str(setup))

    def test_debian(self):
        iso = linux_iso(self.d, "debian-13.0.0-amd64-netinst.iso", DEBIAN_INFO, kind="install.amd")
        meta = oslib.inspect(iso)
        kernel, initrd = self.d / "linux", self.d / "initrd.gz"
        kernel.write_bytes(b"KERNEL" * 1000)
        initrd.write_bytes(b"INITRD" * 1000)
        with mock.patch.object(linuxsetup, "netboot", lambda code: (kernel, initrd)):
            self.run_job(iso, meta, linuxsetup.LinuxOptions("Okula", "pw1234", "Kasse 1"))
        table = sh("sfdisk", "-d", self.dev)
        self.assertEqual(len(re.findall(rf"^{self.dev}p\d", table, re.M)), 1)  # Rest bleibt frei
        esp = self.mounted(1)
        try:
            self.assertEqual((esp / "okula/linux").read_bytes(), kernel.read_bytes())
            pre = read_cpio(gzip.decompress((esp / "okula/preseed.cpio.gz").read_bytes()))["preseed.cfg"].decode()
            self.assertIn(f"d-i partman-auto/disk string {self.dev}", pre)
            self.assertIn("gnome-desktop", pre)
            cfg = (esp / "boot/grub/grub.cfg").read_text()
            self.assertIn("initrd /okula/initrd.gz /okula/preseed.cpio.gz", cfg)
            self.assertTrue((esp / "EFI/boot/grub.cfg").is_file())
        finally:
            sh("umount", str(esp))


if __name__ == "__main__":
    unittest.main()
