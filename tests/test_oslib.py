import tempfile
import threading
import unittest
from pathlib import Path

from okula_recovery import oslib, udf
from tests.isofixtures import HAVE_TOOLS, linux_iso, windows_iso


@unittest.skipUnless(HAVE_TOOLS, "genisoimage, wimlib-imagex oder xorriso fehlt")
class InspectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_windows_iso_editions_from_udf(self):
        iso = windows_iso(self.d)
        with udf.UdfImage.open(str(iso)) as img:
            self.assertIsNotNone(img.lookup("/SOURCES/INSTALL.WIM"))  # Gross-/Kleinschreibung egal
        meta = oslib.inspect(iso)
        self.assertEqual(meta["family"], "windows")
        self.assertEqual(meta["title"], "Windows 11 24H2 (de-DE)")
        self.assertEqual([e["name"] for e in meta["windows"]["editions"]], ["Windows 11 Home", "Windows 11 Pro"])
        self.assertEqual(meta["windows"]["editions"][1]["edition_id"], "Professional")
        self.assertEqual(meta["windows"]["arch"], "amd64")
        self.assertTrue(meta["uefi"] and meta["bios"])
        self.assertFalse(meta["hybrid"])
        self.assertTrue(oslib.installable(meta))
        self.assertEqual(oslib.stick_modes(meta), ["windows"])
        self.assertEqual(oslib.describe(meta), "Windows-ISO · 2 Editionen")

    def test_windows_10_build(self):
        meta = oslib.inspect(windows_iso(self.d, "w10.iso", build=19045,
                                         editions=(("Windows 10 Pro", "Professional"),)))
        self.assertEqual(meta["windows"]["product"], "Windows 10")
        self.assertEqual(meta["windows"]["version"], "22H2")

    def test_ubuntu_hybrid(self):
        meta = oslib.inspect(linux_iso(self.d))
        self.assertEqual(meta["family"], "linux")
        self.assertEqual(meta["title"], "Ubuntu 24.04.1 LTS")
        self.assertEqual(meta["linux"]["distro"], "ubuntu")
        self.assertEqual(meta["linux"]["kind"], "casper")
        self.assertEqual(meta["linux"]["version"], "24.04.1")
        self.assertTrue(meta["hybrid"] and meta["uefi"])
        self.assertTrue(oslib.installable(meta))
        self.assertEqual(oslib.stick_modes(meta), ["dd", "files"])

    def test_debian_netinst(self):
        meta = oslib.inspect(linux_iso(
            self.d, "debian-13.0.0-amd64-netinst.iso",
            'Debian GNU/Linux 13.0.0 "Trixie" - Official amd64 NETINST with firmware 20250809-11:21',
            kind="install.amd"))
        self.assertEqual(meta["title"], "Debian GNU/Linux 13.0.0 (Netinstall)")
        self.assertEqual(meta["linux"]["kind"], "debian-installer")

    def test_unknown_iso_and_img(self):
        src = self.d / "x"
        src.mkdir()
        (src / "README.TXT").write_text("hi")
        import subprocess
        iso = self.d / "tool.iso"
        subprocess.run(["genisoimage", "-quiet", "-R", "-V", "HPTOOLS", "-o", str(iso), str(src)], check=True)
        meta = oslib.inspect(iso)
        self.assertEqual((meta["family"], meta["title"]), ("other", "HPTOOLS"))
        self.assertEqual(oslib.stick_modes(meta), [])
        img = self.d / "freedos.img.xz"
        img.write_bytes(b"\xfd7zXZ")
        meta = oslib.inspect(img)
        self.assertEqual((meta["family"], meta["compression"]), ("other", "xz"))
        self.assertEqual(oslib.stick_modes(meta), ["dd"])


@unittest.skipUnless(HAVE_TOOLS, "genisoimage, wimlib-imagex oder xorriso fehlt")
class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.nas = self.d / "nas"
        self.nas.mkdir()
        self.src = self.d / "upload"
        self.src.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_upload_sorts_by_family_and_remembers_checksum(self):
        win, lin = windows_iso(self.src), linux_iso(self.src)
        seen = []
        p1 = oslib.add_iso(self.nas, win, None, lambda d, t: seen.append((d, t)), threading.Event())
        p2 = oslib.add_iso(self.nas, lin, None, lambda d, t: None, threading.Event())
        self.assertEqual(p1.parent, self.nas / "OS" / "Windows")
        self.assertEqual(p2.parent, self.nas / "OS" / "Linux")
        self.assertEqual(seen[-1][0], seen[-1][1])
        self.assertFalse(list((self.nas / "OS" / "Windows").glob("*.partial")))
        tree = {f.name: f for f in oslib.scan(self.nas)}
        self.assertEqual(sorted(tree), ["Linux", "Sonstige", "Windows"])
        info = tree["Windows"].isos[0]
        import hashlib
        self.assertEqual(info.meta["sha256"], hashlib.sha256(win.read_bytes()).hexdigest())
        self.assertEqual(info.title, "Windows 11 24H2 (de-DE)")
        # Prüfsummen auf Wunsch: alle vier, SHA-256 bleibt gleich
        sums = oslib.checksums(info.path, lambda d, t: None, threading.Event())
        self.assertEqual(sums["sha256"], info.meta["sha256"])
        self.assertEqual(len(sums["sha512"]), 128)

    def test_folders_move_rename_delete(self):
        p = oslib.add_iso(self.nas, linux_iso(self.src), None, lambda d, t: None, threading.Event())
        rel = oslib.make_folder(self.nas, "Linux", "Ubuntu")
        moved = oslib.move_iso(self.nas, p, rel)
        self.assertTrue(oslib.meta_path(moved).is_file())  # Beschreibung zieht mit
        renamed = oslib.rename_iso(self.nas, moved, "Ubuntu Kasse")
        self.assertEqual(renamed.name, "Ubuntu Kasse.iso")
        info = next(i for f in oslib.scan(self.nas) for i in f.all_isos())
        self.assertEqual(info.display, "Ubuntu Kasse")       # neuer Name in der Übersicht
        self.assertEqual(info.title, "Ubuntu 24.04.1 LTS")   # Erkennung bleibt erhalten
        with self.assertRaisesRegex(oslib.OsLibError, "nicht leer"):
            oslib.delete_folder(self.nas, rel)
        with self.assertRaisesRegex(oslib.OsLibError, "Kategorien"):
            oslib.delete_folder(self.nas, "Linux")
        with self.assertRaisesRegex(oslib.OsLibError, "nicht im OS-Ordner"):
            oslib.delete_iso(self.nas, self.src / "x.iso")
        oslib.delete_iso(self.nas, renamed)
        self.assertFalse(oslib.meta_path(renamed).exists())
        oslib.delete_folder(self.nas, rel)
        with self.assertRaises(oslib.OsLibError):
            oslib.make_folder(self.nas, "Linux/a/b", "c")  # 4. Ebene

    def test_iso_copied_by_hand_is_inspected_on_scan(self):
        oslib.ensure_layout(self.nas)
        dest = self.nas / "OS" / "Sonstige" / "ubuntu.iso"
        dest.write_bytes(linux_iso(self.src).read_bytes())
        tree = {f.name: f for f in oslib.scan(self.nas)}
        self.assertEqual(tree["Sonstige"].isos[0].family, "linux")
        self.assertTrue(oslib.meta_path(dest).is_file())


if __name__ == "__main__":
    unittest.main()
