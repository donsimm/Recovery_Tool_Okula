import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from okula_recovery import isofetch, stick

LSBLK = json.dumps({"blockdevices": [
    {"name": "sda", "path": "/dev/sda", "size": 120034123776, "model": "SH103S3120G", "vendor": "ATA",
     "tran": "sata", "rm": False, "hotplug": False, "type": "disk", "mountpoints": [None],
     "children": [{"name": "sda3", "path": "/dev/sda3", "type": "part", "mountpoints": ["/"]}]},
    {"name": "sdb", "path": "/dev/sdb", "size": 16008609792, "model": "Cruzer Blade", "vendor": "SanDisk ",
     "tran": "usb", "rm": True, "hotplug": True, "type": "disk", "mountpoints": [None],
     "children": [{"name": "sdb1", "path": "/dev/sdb1", "type": "part", "mountpoints": ["/media/user/STICK"]}]},
    # USB-Platte, von der das System läuft: nie anbieten
    {"name": "sdc", "path": "/dev/sdc", "size": 500107862016, "model": "Ext", "vendor": "WD",
     "tran": "usb", "rm": False, "hotplug": True, "type": "disk", "mountpoints": [None],
     "children": [{"name": "sdc1", "path": "/dev/sdc1", "type": "part", "mountpoints": ["/boot/efi"]}]},
    {"name": "sr0", "path": "/dev/sr0", "size": 1073741312, "tran": "sata", "rm": "1", "type": "rom",
     "mountpoints": [None]},
]})


class DiskListTest(unittest.TestCase):
    def test_only_removable_non_system_disks(self):
        disks = stick.parse_lsblk_disks(LSBLK)
        self.assertEqual([d.path for d in disks], ["/dev/sdb"])
        self.assertEqual(disks[0].mountpoints, ["/media/user/STICK"])
        self.assertEqual(disks[0].label, "/dev/sdb – SanDisk Cruzer Blade (16.0 GB)")

    def test_garbage(self):
        self.assertEqual(stick.parse_lsblk_disks(""), [])


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_partition_path(self):
        self.assertEqual(stick.partition_path("/dev/sdb"), "/dev/sdb1")
        self.assertEqual(stick.partition_path("/dev/mmcblk0"), "/dev/mmcblk0p1")
        self.assertEqual(stick.partition_path("/dev/nvme1n1"), "/dev/nvme1n1p1")

    def test_find_kernel_prefers_unversioned(self):
        live = self.root / "live"
        live.mkdir()
        for n in ("vmlinuz-6.12.48+deb13-amd64", "initrd.img-6.12.48+deb13-amd64", "filesystem.squashfs"):
            (live / n).touch()
        self.assertEqual(stick.find_kernel(live), ("vmlinuz-6.12.48+deb13-amd64", "initrd.img-6.12.48+deb13-amd64"))
        (live / "vmlinuz").touch()
        self.assertEqual(stick.find_kernel(live)[0], "vmlinuz")

    def test_find_kernel_missing(self):
        with self.assertRaises(stick.StickError):
            stick.find_kernel(self.root)

    def test_grub_cfg(self):
        cfg = stick.grub_cfg("vmlinuz", "initrd.img")
        self.assertIn("linux /live/vmlinuz boot=live components live-config.hooks=medium", cfg)
        self.assertIn("initrd /live/initrd.img", cfg)
        self.assertIn("--label --set=root OKULAAGENT", cfg)
        self.assertEqual(cfg.count("menuentry"), 2)

    def test_copy_tree_follows_symlinks(self):
        src, dst = self.root / "src", self.root / "dst"
        (src / "live").mkdir(parents=True)
        (src / "live" / "vmlinuz-6").write_bytes(b"k" * 1000)
        os.symlink("vmlinuz-6", src / "live" / "vmlinuz")
        os.symlink("missing", src / "broken")
        seen = []
        stick.copy_tree(src, dst, lambda d, t: seen.append((d, t)))
        self.assertFalse((dst / "live" / "vmlinuz").is_symlink())
        self.assertEqual((dst / "live" / "vmlinuz").read_bytes(), b"k" * 1000)
        self.assertFalse((dst / "broken").exists())
        self.assertEqual(seen[-1], (2000, 2000))

    def test_install_agent(self):
        stick.install_agent(self.root, "192.168.1.20")
        pkg = self.root / "live/okula/okula_recovery"
        self.assertEqual(sorted(p.name for p in pkg.iterdir()), sorted(stick.AGENT_MODULES))
        self.assertEqual((self.root / "live/okula/agent.conf").read_text(), 'AGENT_ARGS="--server 192.168.1.20"\n')
        self.assertIn("EnvironmentFile", (self.root / "live/okula/okula-agent.service").read_text())
        hook = self.root / "live/config-hooks/9990-okula-agent"
        self.assertEqual(subprocess.run(["sh", "-n", str(hook)]).returncode, 0)
        # Agent-Module dürfen nichts ausserhalb der kopierten Dateien brauchen (kein GTK auf dem Stick)
        r = subprocess.run(["python3", "-c", "import okula_recovery.agent"], cwd=self.root / "live/okula",
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_main_requires_root_or_reports(self):
        if os.geteuid() == 0:
            self.skipTest("läuft als root")
        self.assertEqual(stick.main(["--device", "/dev/sdx", "--iso", "x.iso"]), 1)


class IsoFetchTest(unittest.TestCase):
    SUMS = (
        "aaa  debian-live-13.7.0-amd64-gnome.iso\n"
        "BBB  debian-live-13.7.0-amd64-standard.iso\n"
        "ccc  debian-live-13.7.0-amd64-standard.iso.contents\n"
    )

    def test_parse_sums(self):
        self.assertEqual(isofetch.parse_sums(self.SUMS), ("debian-live-13.7.0-amd64-standard.iso", "bbb"))
        with self.assertRaises(ValueError):
            isofetch.parse_sums(self.SUMS, flavour="kde")

    def test_fetch_from_local_mirror(self):
        with tempfile.TemporaryDirectory() as mirror, tempfile.TemporaryDirectory() as dest:
            iso = Path(mirror) / "debian-live-13.7.0-amd64-standard.iso"
            iso.write_bytes(b"iso-data" * 1000)
            (Path(mirror) / "SHA512SUMS").write_text(f"{isofetch.sha512_file(iso)}  {iso.name}\n")
            msgs = []
            path = isofetch.fetch(lambda f, m: msgs.append(m), base_url=Path(mirror).as_uri() + "/", dest=Path(dest))
            self.assertEqual(path.read_bytes(), iso.read_bytes())
            # Zweiter Aufruf nutzt die vorhandene Datei
            isofetch.fetch(lambda f, m: msgs.append(m), base_url=Path(mirror).as_uri() + "/", dest=Path(dest))
            self.assertIn("ist aktuell", msgs[-1])

    def test_fetch_rejects_bad_checksum(self):
        with tempfile.TemporaryDirectory() as mirror, tempfile.TemporaryDirectory() as dest:
            iso = Path(mirror) / "debian-live-13.7.0-amd64-standard.iso"
            iso.write_bytes(b"x")
            (Path(mirror) / "SHA512SUMS").write_text(f"{'0' * 128}  {iso.name}\n")
            with self.assertRaises(ValueError):
                isofetch.fetch(lambda f, m: None, base_url=Path(mirror).as_uri() + "/", dest=Path(dest))
            self.assertEqual(list(Path(dest).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
