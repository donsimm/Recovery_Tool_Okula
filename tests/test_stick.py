import json
import os
import shutil
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
        self.assertIn("linux /live/vmlinuz boot=live components locales=de_CH.UTF-8", cfg)
        self.assertIn("initrd /live/initrd.img", cfg)
        self.assertIn("--label --set=root OKULAAGENT", cfg)
        self.assertEqual(cfg.count("menuentry"), 2)
        self.assertIn("set theme=/boot/grub/themes/okula/theme.txt", cfg)
        self.assertNotIn("||", cfg)  # kennt das GRUB-Skript nicht
        self.assertTrue(cfg.isascii(), "Menü muss auch ohne Unicode-Font lesbar sein")

    def test_write_boot_config_copies_theme(self):
        stick.write_boot_config(self.root, "vmlinuz", "initrd.img")
        theme = self.root / "boot/grub/themes/okula"
        self.assertTrue((theme / "theme.txt").is_file())
        self.assertEqual((theme / "okula-logo.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn('file = "okula-logo.png"', (theme / "theme.txt").read_text())

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

    def test_agent_tree(self):
        tree = self.root / "tree"
        stick.build_agent_tree(tree, "192.168.1.20")
        pkg = tree / "opt/okula-recovery/okula_recovery"
        self.assertEqual(sorted(p.name for p in pkg.iterdir()), sorted(stick.AGENT_MODULES))
        self.assertEqual((tree / "etc/okula-agent.conf").read_text(), 'AGENT_ARGS="--server 192.168.1.20"\n')
        link = tree / "etc/systemd/system/multi-user.target.wants/okula-agent.service"
        self.assertEqual(os.readlink(link), "/etc/systemd/system/okula-agent.service")
        self.assertIn("start-agent.sh", (tree / "etc/systemd/system/okula-agent.service").read_text())
        self.assertIn("Recovery Agent", (tree / "etc/issue").read_text())
        start = tree / "opt/okula-recovery/start-agent.sh"
        self.assertTrue(os.access(start, os.X_OK))
        self.assertEqual(subprocess.run(["sh", "-n", str(start)]).returncode, 0)
        # Agent darf auf dem Stick nichts ausser den kopierten Modulen brauchen (kein GTK)
        r = subprocess.run(["python3", "-c", "import okula_recovery.agent"], cwd=tree / "opt/okula-recovery",
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_merge_usr_never_shadows_symlinks(self):
        tree = self.root / "tree"
        (tree / "lib/x86_64-linux-gnu").mkdir(parents=True)
        (tree / "lib/x86_64-linux-gnu/libntfs-3g.so.89.0.0").write_text("x")
        os.symlink("libntfs-3g.so.89.0.0", tree / "lib/x86_64-linux-gnu/libntfs-3g.so.89")
        (tree / "usr/sbin").mkdir(parents=True)
        (tree / "usr/sbin/partclone.ntfs").write_text("y")
        (tree / "sbin").mkdir()
        (tree / "sbin/tool").write_text("z")
        stick.merge_usr(tree)
        self.assertEqual(sorted(p.name for p in tree.iterdir()), ["usr"])
        lib = tree / "usr/lib/x86_64-linux-gnu"
        self.assertEqual((lib / "libntfs-3g.so.89.0.0").read_text(), "x")
        self.assertEqual(os.readlink(lib / "libntfs-3g.so.89"), "libntfs-3g.so.89.0.0")
        self.assertTrue((tree / "usr/sbin/tool").is_file())
        self.assertTrue((tree / "usr/sbin/partclone.ntfs").is_file())

    def test_parse_apt_depends(self):
        out = "partclone\n  Depends: libc6\n  Depends: <libfoo>\nlibc6\n<libfoo>\nlibntfs-3g89t64:amd64\n"
        self.assertEqual(stick.parse_apt_depends(out), ["partclone", "libc6", "libntfs-3g89t64"])

    def test_read_installed_packages(self):
        f = self.root / "filesystem.packages"
        f.write_text("libc6:amd64\t2.41-12\nzstd\t1.5.7\n\n")
        self.assertEqual(stick.read_installed_packages(f), {"libc6", "zstd"})
        self.assertIsNone(stick.read_installed_packages(self.root / "missing"))

    @unittest.skipUnless(shutil.which("mksquashfs"), "mksquashfs fehlt")
    def test_install_agent_builds_layer_and_updates_module(self):
        (self.root / "live").mkdir()
        (self.root / "live/filesystem.module").write_text("filesystem.squashfs\n")
        stick.install_agent(self.root, "")
        layer = self.root / "live" / stick.AGENT_LAYER
        listing = subprocess.run(["unsquashfs", "-l", str(layer)], capture_output=True, text=True).stdout
        for path in ("opt/okula-recovery/okula_recovery/agent.py", "opt/okula-recovery/start-agent.sh",
                     "etc/systemd/system/multi-user.target.wants/okula-agent.service", "etc/issue"):
            self.assertIn(path, listing)
        self.assertEqual((self.root / "live/filesystem.module").read_text().split(),
                         ["filesystem.squashfs", stick.AGENT_LAYER])
        # Alphabetisch nach filesystem.squashfs → liegt im Overlay oben
        self.assertGreater(stick.AGENT_LAYER, "filesystem.squashfs")

    def test_main_requires_root_or_reports(self):
        if os.geteuid() == 0:
            self.skipTest("läuft als root")
        self.assertEqual(stick.main(["--device", "/dev/sdx", "--iso", "x.iso"]), 1)


class VerifyStickTest(unittest.TestCase):
    """Ä-038: Prüfung am Schluss (Ordner statt eingehängtem Stick)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.iso, self.root, self.data = base / "iso", base / "stick", base / "data"
        for d in (self.iso / "live", self.root / "live", self.data / "image"):
            d.mkdir(parents=True)
        (self.iso / "live/filesystem.squashfs").write_bytes(b"hsqs" + b"x" * 1000)
        shutil.copy(self.iso / "live/filesystem.squashfs", self.root / "live/filesystem.squashfs")
        (self.root / "live" / stick.AGENT_LAYER).write_bytes(b"hsqs" + b"\0" * 100)
        (self.root / "live/vmlinuz").write_bytes(b"k")
        (self.root / "live/initrd.img").write_bytes(b"i")
        (self.data / "image/sda1.ntfs-ptcl-img.zst").write_bytes(b"img")

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, data=False):
        stick.verify_stick(self.root, self.iso, "vmlinuz", "initrd.img", self.data if data else None)

    def assertFails(self, text, data=False):
        with self.assertRaises(stick.StickError) as cm:
            self.verify(data)
        self.assertIn(text, str(cm.exception))

    def test_valid_stick(self):
        self.verify()
        self.verify(data=True)

    def test_agent_layer_empty(self):
        (self.root / "live" / stick.AGENT_LAYER).write_bytes(b"")
        self.assertFails("leer (0 Byte)")

    def test_agent_layer_missing(self):
        (self.root / "live" / stick.AGENT_LAYER).unlink()
        self.assertFails("fehlt")

    def test_agent_layer_wrong_header(self):
        (self.root / "live" / stick.AGENT_LAYER).write_bytes(b"\0" * 100)
        self.assertFails("kein gültiges Squashfs")

    def test_filesystem_too_small(self):
        (self.root / "live/filesystem.squashfs").write_bytes(b"hsqs" + b"x" * 10)
        self.assertFails("filesystem.squashfs unvollständig")

    def test_kernel_missing(self):
        (self.root / "live/initrd.img").unlink()
        self.assertFails("initrd.img fehlt")

    def test_restore_image_missing(self):
        shutil.rmtree(self.data / "image")
        self.assertFails("Image fehlt", data=True)

    def test_restore_image_empty(self):
        (self.data / "image/sda1.ntfs-ptcl-img.zst").write_bytes(b"")
        self.assertFails("leer", data=True)


class UnpluggedTest(unittest.TestCase):
    """Ä-038: Abziehen während des Baus → verständliche Meldung."""

    def test_device_gone(self):
        err = stick.explain_unplugged("/dev/okula-test-gibt-es-nicht", stick.StickError("mount: irgendwas"))
        self.assertEqual(str(err), stick.UNPLUGGED)
        self.assertEqual(stick.UNPLUGGED, "Stick wurde während des Schreibens abgezogen – Stick neu erstellen.")

    def test_io_error(self):
        with tempfile.NamedTemporaryFile() as dev:
            err = stick.explain_unplugged(dev.name, OSError(5, "Input/output error"))
            self.assertEqual(str(err), stick.UNPLUGGED)
            err = stick.explain_unplugged(dev.name, stick.StickError("mksquashfs: write failed: Input/output error"))
            self.assertEqual(str(err), stick.UNPLUGGED)

    def test_other_error_unchanged(self):
        with tempfile.NamedTemporaryFile() as dev:
            orig = stick.StickError("apt-cache: kaputt")
            self.assertIs(stick.explain_unplugged(dev.name, orig), orig)


class StickResultTextTest(unittest.TestCase):
    """Ä-038: Texte des Popups am Ende."""

    def setUp(self):
        try:
            from okula_recovery import stick_dialog
        except (ImportError, ValueError) as e:
            self.skipTest(f"GTK fehlt: {e}")
        self.sd = stick_dialog

    def test_texts(self):
        self.assertEqual(self.sd.stick_result_texts(True, "", "Agent-Stick fertig"),
                         ("Agent-Stick fertig", "Der Stick kann jetzt abgezogen werden."))
        title, text = self.sd.stick_result_texts(False, stick.UNPLUGGED, "Agent-Stick fertig")
        self.assertEqual(title, "Stick nicht fertig")
        self.assertIn(stick.UNPLUGGED, text)
        self.assertTrue(text.endswith("Stick nicht verwenden – neu erstellen."))
        self.assertEqual(self.sd.UNPLUG_HINT, "Stick erst abziehen, wenn „Stick fertig“ erscheint.")


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
