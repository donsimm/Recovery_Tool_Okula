"""Netzwerkstart: Bausteine, MAC-Prüfung des HTTP-Dienstes, live-boot-Zusatz, Vorbereitung mit Test-ISO."""

import gzip
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from okula_recovery import linuxsetup, pxe, stick

ALLOWED = "52:54:00:12:34:56"


class RulesTest(unittest.TestCase):
    def test_macs_and_hosts_file(self):
        self.assertEqual(pxe.normalize_macs(["52-54-00-12-34-56", " 52:54:00:12:34:56 ", "", "AA:BB:CC:DD:EE:FF"]),
                         ["52:54:00:12:34:56", "aa:bb:cc:dd:ee:ff"])
        for bad in ("52:54:00:12:34", "zz:54:00:12:34:56", "52:54:00:12:34:56,set:x"):
            with self.assertRaises(pxe.PxeError):
                pxe.normalize_macs([bad])
        self.assertEqual(pxe.hosts_file([ALLOWED]), f"{ALLOWED},set:okula\n")

    def test_dnsmasq_conf_only_proxy_for_allowed(self):
        import ipaddress
        conf = pxe.dnsmasq_conf("eth0", ipaddress.IPv4Network("192.168.110.0/24"), Path("/var/lib/x"))
        self.assertIn("port=0\n", conf)                                   # kein DNS
        self.assertIn("dhcp-range=192.168.110.0,proxy,255.255.255.0\n", conf)  # keine IP-Vergabe
        self.assertIn("dhcp-ignore=tag:!okula\n", conf)                   # nur freigeschaltete MACs
        self.assertTrue(all("tag:okula" in line for line in conf.splitlines() if line.startswith("pxe-")))
        if shutil.which("dnsmasq") or os.path.exists("/usr/sbin/dnsmasq"):
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "c.conf").write_text(conf.replace("/var/lib/x", d))
                (Path(d) / "allowed").write_text(pxe.hosts_file([ALLOWED]))
                (Path(d) / "tftp").mkdir()
                r = subprocess.run(["/usr/sbin/dnsmasq", "--test", f"--conf-file={d}/c.conf"],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_kernel_params_and_overlay(self):
        params = pxe.kernel_params("192.168.110.10")
        self.assertIn("boot=live components", params)
        self.assertIn("fetch=http://192.168.110.10:47813/filesystem.squashfs", params)
        self.assertIn(f"okula.layer=http://192.168.110.10:47813/{stick.AGENT_LAYER}", params)
        cpio = pxe.overlay_cpio()
        self.assertIn(b"lib/live/boot/9999-okula\0", cpio)
        self.assertTrue(cpio.rstrip(b"\0").endswith(b"TRAILER!!!"))

    def test_overlay_starts_aligned(self):
        for n in range(8):  # beliebige Länge des Original-initrd
            data = pxe.combine_initrd(b"x" * (100 + n))
            start = len(data) - len(pxe.overlay_cpio())
            self.assertEqual((start % 4, data[100 + n:start].strip(b"\0")), (0, b""))

    def test_mac_of(self):
        with tempfile.NamedTemporaryFile("w", suffix="arp", delete=False) as f:
            f.write("IP address       HW type     Flags       HW address            Mask     Device\n"
                    f"192.168.110.50   0x1         0x2         {ALLOWED.upper()}     *        eth0\n"
                    "192.168.110.51   0x1         0x0         00:00:00:00:00:00     *        eth0\n")
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(pxe.mac_of("192.168.110.50", f.name), ALLOWED)
        self.assertEqual(pxe.mac_of("192.168.110.51", f.name), "")   # unvollständig
        self.assertEqual(pxe.mac_of("192.168.110.99", f.name), "")


class HttpTest(unittest.TestCase):
    """Der HTTP-Dienst liefert den Agent-Teil (mit Schlüssel) nur an freigeschaltete MACs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "http").mkdir()
        (self.base / "http" / stick.AGENT_LAYER).write_bytes(b"geheim" * 1000)
        (self.base / "http" / "filesystem.squashfs").write_bytes(b"live" * 100)
        (self.base / "secret.txt").write_text("nein")
        self.arp = self.base / "arp"

        class H(pxe.Handler):
            base = self.base
            arp = str(self.arp)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url + path, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def set_arp(self, mac):
        self.arp.write_text("IP address HW type Flags HW address Mask Device\n"
                            f"127.0.0.1 0x1 0x2 {mac} * lo\n")

    def test_only_allowed_mac(self):
        self.set_arp(ALLOWED)
        pxe.write_allowed([], self.base)
        self.assertEqual(self.get(f"/{stick.AGENT_LAYER}")[0], 403)           # nicht freigeschaltet
        pxe.write_allowed([ALLOWED], self.base)
        self.assertEqual(self.get(f"/{stick.AGENT_LAYER}"), (200, b"geheim" * 1000))
        self.assertEqual(self.get("/filesystem.squashfs")[0], 200)
        self.set_arp("aa:bb:cc:dd:ee:ff")                                      # anderes Gerät
        self.assertEqual(self.get(f"/{stick.AGENT_LAYER}")[0], 403)
        self.set_arp(ALLOWED)
        for path in ("/../secret.txt", "/secret.txt", "/http/okula-agent.squashfs", "/allowed"):
            self.assertEqual(self.get(path)[0], 404, path)                   # nur feste Dateien


@unittest.skipUnless(shutil.which("dash"), "dash fehlt")
class LiveBootHookTest(unittest.TestCase):
    """Das Zusatzskript im initrd, so wie live-boot es ausführt (dash, Funktionen von live-boot als Attrappen)."""

    def run_hook(self, cmdline: str, fail: str = "") -> tuple[int, list[str], str]:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "cmdline").write_text(cmdline + "\n")
            (d / "hook").write_text(pxe.LIVE_BOOT_HOOK)
            script = f"""
mount() {{ :; }}
umount() {{ echo umount >> {d}/log; }}
log_begin_msg() {{ :; }}
log_end_msg() {{ :; }}
wget() {{ case "$1" in *{fail or 'NIE'}*) return 1;; esac; echo "$1" > "$3"; }}
do_httpmount() {{ echo original; }}
mountpoint={d}/medium
LIVE_MEDIA_PATH=live
FETCH=http://10.0.0.1:47813/filesystem.squashfs
OKULA_CMDLINE={d}/cmdline
. {d}/hook
do_httpmount > /dev/null 2>&1
echo $? > {d}/rc
"""
            r = subprocess.run(["dash", "-c", script], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            files = sorted(p.name for p in (d / "medium" / "live").iterdir()) if (d / "medium" / "live").is_dir() else []
            log = (d / "log").read_text() if (d / "log").exists() else ""
            return int((d / "rc").read_text()), files, log

    def test_loads_live_system_and_agent_layer(self):
        layer = f"okula.layer=http://10.0.0.1:47813/{stick.AGENT_LAYER}"
        rc, files, _log = self.run_hook(f"boot=live components quiet {layer}")
        self.assertEqual((rc, files), (0, ["filesystem.squashfs", stick.AGENT_LAYER]))
        rc, _files, log = self.run_hook(f"boot=live {layer}", fail=stick.AGENT_LAYER)   # Gerät nicht freigeschaltet
        self.assertEqual((rc, log), (1, "umount\n"))

    def test_without_layer_keeps_live_boot(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "c").write_text("boot=live\n")
            (Path(d) / "hook").write_text(pxe.LIVE_BOOT_HOOK)
            r = subprocess.run(["dash", "-c", f"do_httpmount() {{ echo original; }}; OKULA_CMDLINE={d}/c; "
                                              f". {d}/hook; do_httpmount"], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "original")


@unittest.skipUnless(os.geteuid() == 0 and all(shutil.which(t) for t in ("genisoimage", "xorriso", "mksquashfs")),
                     "braucht root, genisoimage, xorriso, mksquashfs")
class PrepareTest(unittest.TestCase):
    def test_prepare_from_live_iso(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "iso" / "live"
            src.mkdir(parents=True)
            (src / "vmlinuz").write_bytes(b"KERNEL" * 100)
            initrd = gzip.compress(linuxsetup.cpio_newc({"init": b"#!/bin/sh\n"}))
            (src / "initrd.img").write_bytes(initrd)
            (src / "filesystem.squashfs").write_bytes(b"SQUASH" * 1000)
            (src / "filesystem.packages").write_text("partclone\t0.3\nzstd\t1.5\npython3\t3.13\n")
            iso = d / "debian-live-13.1.0-amd64-standard.iso"
            subprocess.run(["genisoimage", "-quiet", "-R", "-J", "-o", str(iso), str(d / "iso")], check=True)

            def fake_loaders(dest, emit):
                for name in ("bootx64.efi", "grubx64.efi", "pxelinux.0", "ldlinux.c32"):
                    (dest / name).write_bytes(name.encode())

            base = d / "pxe"
            events = []
            with mock.patch.object(stick, "bundle_packages", lambda names, tree: None):
                state = pxe.prepare(str(iso), "192.168.110.10", bytes(range(32)),
                                    lambda k, t: events.append((k, t)), base, fake_loaders)
            self.assertEqual((state["server"], state["iso"]), ("192.168.110.10", iso.name))
            tftp, http = base / "tftp", base / "http"
            self.assertEqual((tftp / "okula" / "vmlinuz").read_bytes(), b"KERNEL" * 100)
            data = (tftp / "okula" / "initrd.img").read_bytes()
            self.assertTrue(data.startswith(initrd) and data.endswith(pxe.overlay_cpio()))
            self.assertEqual((len(data) - len(pxe.overlay_cpio())) % 4, 0)
            for rel in pxe.GRUB_CFG_PATHS:
                self.assertIn("okula.layer=http://192.168.110.10:47813/", (tftp / rel).read_text())
            self.assertIn("APPEND boot=live", (tftp / "pxelinux.cfg" / "default").read_text())
            self.assertEqual(sorted(p.name for p in http.iterdir()), sorted(pxe.HTTP_FILES))
            self.assertEqual(stat.S_IMODE(http.stat().st_mode), 0o700)               # Schlüssel nur für root
            self.assertEqual(stat.S_IMODE((http / stick.AGENT_LAYER).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((tftp / "okula" / "initrd.img").stat().st_mode), 0o644)
            listing = subprocess.run(["unsquashfs", "-l", str(http / stick.AGENT_LAYER)],
                                     capture_output=True, text=True).stdout
            self.assertIn("etc/okula-agent.key", listing)
            self.assertIn("--server 192.168.110.10",
                          subprocess.run(["unsquashfs", "-cat", str(http / stick.AGENT_LAYER), "etc/okula-agent.conf"],
                                         capture_output=True, text=True).stdout)
            self.assertFalse((base / ".neu").exists())
            self.assertEqual(pxe.read_allowed(base), set())


if __name__ == "__main__":
    unittest.main()
