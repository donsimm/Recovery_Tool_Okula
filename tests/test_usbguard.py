"""B-029: USB-Vorgänge abbrechen erzwingen, Datenträger getrennt, Seriennummer statt Gerätename."""

import io
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from okula_recovery import isostick, stick, usbguard, usbjobs, usbtools
from okula_recovery.usbguard import Ident

SANDISK = Ident("/dev/sdx", "4C530001234567", "SanDisk Cruzer Blade", 16_000_000_000)


def probe_of(table: dict):
    return lambda path: table.get(path)


class IdentTest(unittest.TestCase):
    def tearDown(self):
        usbguard.reset()

    def test_arg_roundtrip_and_text(self):
        self.assertEqual(Ident.parse(SANDISK.arg()), SANDISK)
        self.assertEqual(SANDISK.text(), "SanDisk Cruzer Blade, SN 4C530001234567")
        with self.assertRaises(ValueError):
            Ident.parse("kein json")

    def test_short_serial_in_label(self):
        d = stick.UsbDisk("/dev/sdb", 16_008_609_792, "Cruzer Blade", "SanDisk", serial="4C530001234567")
        self.assertEqual(d.label, "/dev/sdb – SanDisk Cruzer Blade (16.0 GB) · SN …01234567")
        self.assertEqual(d.ident(), Ident("/dev/sdb", "4C530001234567", "SanDisk Cruzer Blade", 16_008_609_792))
        self.assertEqual(stick.UsbDisk("/dev/sdc", 1, serial="AB12").label, "/dev/sdc – USB-Datenträger (0.0 GB) · SN AB12")

    def test_check_same_disk(self):
        usbguard.check(SANDISK, probe_of({"/dev/sdx": SANDISK}))
        no_serial = Ident("/dev/sdx", "", "X", 100)
        usbguard.check(no_serial, probe_of({"/dev/sdx": Ident("/dev/sdx", "", "Y", 100)}))

    def test_check_gone(self):
        for found in (None, Ident("/dev/sdx", SANDISK.serial, SANDISK.model, 0)):
            with self.assertRaises(usbguard.DiskGone) as ctx:
                usbguard.check(SANDISK, probe_of({"/dev/sdx": found}))
            self.assertTrue(str(ctx.exception).startswith(
                "Datenträger getrennt – abgebrochen (SanDisk Cruzer Blade, SN 4C530001234567)"))
            self.assertIn("unvollständig", str(ctx.exception))

    def test_check_other_disk(self):
        other = Ident("/dev/sdx", "OTHER999", "SanDisk Cruzer Blade", SANDISK.size)
        with self.assertRaises(usbguard.WrongDisk) as ctx:
            usbguard.check(SANDISK, probe_of({"/dev/sdx": other}))
        self.assertIn("nicht mehr derselbe Datenträger", str(ctx.exception))
        self.assertIn("nichts geschrieben", str(ctx.exception))
        with self.assertRaises(usbguard.WrongDisk):     # ohne Seriennummer: Grösse muss passen
            usbguard.check(Ident("/dev/sdx", "", "", 100), probe_of({"/dev/sdx": Ident("/dev/sdx", "", "", 200)}))

    def test_partition_belongs_to_disk(self):
        self.assertTrue(usbguard._belongs("/dev/sdb1", "/dev/sdb"))
        self.assertTrue(usbguard._belongs("/dev/nvme0n1p2", "/dev/nvme0n1"))
        self.assertFalse(usbguard._belongs("/dev/sdba", "/dev/sdb"))
        self.assertFalse(usbguard._belongs("/dev/sdc1", "/dev/sdb"))

    def test_idents_for_prefers_tool(self):
        got = usbguard.idents_for(["/dev/sdx", "/dev/sdy"], [SANDISK.arg()],
                                  probe_of({"/dev/sdy": Ident("/dev/sdy", "Y", "Y", 1)}))
        self.assertEqual(got, [SANDISK, Ident("/dev/sdy", "Y", "Y", 1)])


class NoWriteOnWrongDiskTest(unittest.TestCase):
    """Seriennummer passt nicht → der Helfer öffnet das Gerät gar nicht erst (kein Schreiben)."""

    def setUp(self):
        usbguard.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "src")
        with open(self.src, "wb") as f:
            f.write(b"x" * 4096)

    def tearDown(self):
        usbguard.reset()
        self.tmp.cleanup()

    def test_copy_range_refuses_other_disk(self):
        usbguard.guard([SANDISK])
        other = Ident("/dev/sdx", "FREMD", "Anderer Stick", SANDISK.size)
        with mock.patch.object(usbguard, "current", probe_of({"/dev/sdx": other})), \
                mock.patch.object(usbguard, "_settle", lambda: None), \
                mock.patch.object(usbguard.os, "open", wraps=os.open) as opened:
            with self.assertRaises(usbguard.WrongDisk):
                usbtools.copy_range(self.src, "/dev/sdx", 4096, lambda *_a: None, "Test")
        self.assertNotIn("/dev/sdx", [c.args[0] for c in opened.call_args_list])

    def test_run_refuses_other_disk(self):
        usbguard.guard([SANDISK])
        with mock.patch.object(usbguard, "current", probe_of({"/dev/sdx": None})), \
                mock.patch.object(usbtools.subprocess, "run") as run:
            with self.assertRaises(usbguard.DiskGone):
                usbtools._run(["wipefs", "-a", "/dev/sdx1"])
            with self.assertRaises(usbguard.DiskGone):
                stick._run(["mkfs.vfat", "-F", "32", "/dev/sdx1"])
        run.assert_not_called()

    def test_explain_io_error(self):
        usbguard.guard([SANDISK])
        with mock.patch.object(usbguard, "current", probe_of({})):
            e = usbguard.explain(OSError(5, "Input/output error"))
        self.assertIsInstance(e, usbguard.DiskGone)
        with mock.patch.object(usbguard, "current", probe_of({"/dev/sdx": SANDISK})):
            other = OSError(28, "No space left on device")
            self.assertIs(usbguard.explain(other), other)


class HelperSelfStopTest(unittest.TestCase):
    """Im Root-Helfer: CANCEL/EOF → SIGTERM an sich selbst; hängt er, Kinder und sich selbst hart beenden."""

    def tearDown(self):
        usbguard.reset()

    def test_request_stop_hard_after_grace(self):
        killed, exited, lines = [], threading.Event(), []
        with mock.patch.object(usbguard, "_descendants", lambda _pid: [111, 222]):
            usbguard.request_stop("Abgebrochen – Test", lambda k, t: lines.append((k, t)), grace=0.05,
                                  kill=lambda pid, sig: killed.append((pid, sig)), exit_=lambda _c: exited.set())
            self.assertTrue(exited.wait(2))
        self.assertEqual(killed[0], (os.getpid(), signal.SIGTERM))
        self.assertIn((222, signal.SIGKILL), killed)
        self.assertIn((111, signal.SIGKILL), killed)
        self.assertEqual(lines, [("ERROR", "Abgebrochen – Test (Hilfsprogramm hart beendet)")])
        self.assertEqual(usbguard.reason(), "Abgebrochen – Test")

    def test_watch_cancel_line(self):
        calls = []
        with mock.patch.object(usbguard, "request_stop", lambda why, emit=None: calls.append(why)):
            usbguard.watch(None, io.StringIO("CANCEL\n"), every=0.01, probe=lambda _p: None)
            time.sleep(0.2)
        self.assertEqual(calls[:1], [usbguard.CANCELLED])

    def test_watch_device_gone(self):
        usbguard.guard([SANDISK])
        calls = []
        with mock.patch.object(usbguard, "request_stop", lambda why, emit=None: calls.append(why)):
            usbguard.watch(None, io.StringIO(""), every=0.01, probe=lambda _p: None)
            for _ in range(100):
                if calls:
                    break
                time.sleep(0.02)
        self.assertTrue(calls and calls[0].startswith("Datenträger getrennt – abgebrochen (SanDisk"))

    def test_descendants_of_self(self):
        child = __import__("subprocess").Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            self.assertIn(child.pid, usbguard._descendants(os.getpid()))
        finally:
            child.kill()
            child.wait()


class UnattendLineTest(unittest.TestCase):
    def test_roundtrip(self):
        xml = '<?xml version="1.0"?>\n<unattend>Zürich</unattend>\n'
        line = isostick.unattend_line(xml)
        self.assertEqual(line.count("\n"), 1)
        self.assertEqual(isostick.read_unattend(line), xml)
        with self.assertRaises(ValueError):
            isostick.read_unattend("kein base64!")


def script(body: str) -> list[str]:
    return [sys.executable, "-c", body]


class HelperProcessTest(unittest.TestCase):
    """Tool-Seite: Abbrechen erzwingen, Ende immer gemeldet."""

    def run_helper(self, cmd, cancel_after=None, **kw):
        kw.setdefault("cancel_timeout", 0.3)
        kw.setdefault("kill_timeout", 0.3)
        kw.setdefault("exit_timeout", 0.3)
        kw.setdefault("tick", 0.02)
        proc = usbjobs.HelperProcess(cmd, **kw)
        cancel, progress, lines = threading.Event(), [], []
        if cancel_after is not None:
            threading.Timer(cancel_after, cancel.set).start()
        t0 = time.monotonic()
        ok, error = proc.run(cancel, lambda f, m: progress.append((f, m)), lines.append)
        return ok, error, lines, time.monotonic() - t0, proc

    def test_done(self):
        ok, error, lines, _t, proc = self.run_helper(script(
            "print('PROGRESS 0.5 halb', flush=True); print('WARN achtung', flush=True); print('DONE fertig')"))
        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.assertEqual(lines, ["WARN achtung", "DONE fertig"])
        self.assertEqual(proc.done_text, "fertig")

    def test_cancel_answered(self):
        ok, error, _l, _t, _p = self.run_helper(script(
            "import sys\nfor l in sys.stdin:\n  if l.strip()=='CANCEL':\n"
            "    print('ERROR Abgebrochen – Ziel unvollständig', flush=True); sys.exit(1)"), cancel_after=0.1)
        self.assertFalse(ok)
        self.assertEqual(error, "Abgebrochen – Ziel unvollständig")

    def test_cancel_ignored_then_terminated(self):
        """Helfer reagiert nicht auf CANCEL → nach der Frist SIGTERM, Ergebnis „Abgebrochen“."""
        ok, error, lines, took, _p = self.run_helper(script(
            "import time\nprint('PROGRESS 0.1 x', flush=True)\ntime.sleep(30)"), cancel_after=0.1)
        self.assertFalse(ok)
        self.assertTrue(error.startswith("Abgebrochen"))
        self.assertIn("WARN Hilfsprogramm reagiert nicht – wird beendet", lines)
        self.assertLess(took, 10)

    def test_sigterm_ignored_then_killed(self):
        ok, error, _l, took, proc = self.run_helper(script(
            "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('PROGRESS 0.1 x', flush=True)\n"
            "time.sleep(30)"), cancel_after=0.2)
        self.assertFalse(ok)
        self.assertEqual(error, usbjobs.FORCED)
        self.assertTrue(proc.forced)
        self.assertLess(took, 10)
        proc.proc.wait(5)
        time.sleep(0.1)          # Leser hat EOF gesehen
        proc.proc.stdout.close()

    def test_hanging_process_never_blocks(self):
        """Prozess hängt im Kernel (kein EOF, Signale wirkungslos): run() kehrt trotzdem zurück."""
        class Stuck:
            def __init__(self, *_a, **_k):
                self.stdin = io.StringIO()
                self.stdout = self
                self.signals = []
                self.block = threading.Event()

            def __iter__(self):
                yield "PROGRESS 0.2 schreiben\n"
                self.block.wait(30)

            def poll(self):
                return None

            def wait(self, timeout=None):
                raise __import__("subprocess").TimeoutExpired("x", timeout)

            def send_signal(self, sig):
                self.signals.append(sig)

        made = []
        ok, error, _l, took, proc = self.run_helper(["x"], cancel_after=0.1,
                                                    popen=lambda *a, **k: made.append(Stuck()) or made[-1])
        made[0].block.set()
        self.assertFalse(ok)
        self.assertEqual(error, usbjobs.FORCED)
        self.assertEqual(made[0].signals, [signal.SIGTERM, signal.SIGKILL])
        self.assertLess(took, 5)

    def test_device_gone(self):
        """Stick verschwindet während des Vorgangs → Abbruch mit „Datenträger getrennt“."""
        ok, error, lines, _t, _p = self.run_helper(script(
            "import sys\nfor l in sys.stdin:\n  if l.strip()=='CANCEL':\n"
            "    print('ERROR Abgebrochen', flush=True); sys.exit(1)"),
            idents=[SANDISK], probe=probe_of({}), probe_every=0.05)
        self.assertFalse(ok)
        self.assertTrue(error.startswith("Datenträger getrennt – abgebrochen (SanDisk Cruzer Blade, SN "))
        self.assertTrue(any("ist nicht mehr da" in line for line in lines))

    def test_start_fails(self):
        def boom(*_a, **_k):
            raise OSError("sudo fehlt")
        ok, error, _l, _t, _p = self.run_helper(["x"], popen=boom)
        self.assertEqual((ok, error), (False, "sudo fehlt"))

    def test_exit_code_without_error(self):
        ok, error, _l, _t, _p = self.run_helper(script("import sys; sys.exit(3)"))
        self.assertFalse(ok)
        self.assertIn("Code 3", error)


class RunUsbHelperTest(unittest.TestCase):
    """Dialog-Seite: on_done kommt genau einmal, auch wenn der Helfer nicht reagiert."""

    def test_done_called_once_after_forced_cancel(self):
        from okula_recovery import stick_dialog
        done = []
        finished = threading.Event()

        def on_done(ok, error):
            done.append((ok, error))
            finished.set()

        with mock.patch.object(stick_dialog.GLib, "idle_add", lambda f, *a: f(*a)), \
                mock.patch.multiple(usbjobs, CANCEL_TIMEOUT=0.2, KILL_TIMEOUT=0.2):
            handle = stick_dialog.run_usb_helper(script(
                "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(30)"),
                "", [], lambda *_a: None, lambda *_a: None, on_done)
            handle.cancel()
            self.assertTrue(finished.wait(10))
        time.sleep(0.3)
        self.assertEqual(len(done), 1)
        self.assertFalse(done[0][0])
        self.assertTrue(done[0][1].startswith("Abgebrochen"))
        self.assertEqual(stick_dialog.result_status(*done[0]), "Abgebrochen")
        self.assertEqual(stick_dialog.result_status(False, "Datenträger getrennt – abgebrochen (X)"),
                         "Datenträger getrennt – abgebrochen")


if __name__ == "__main__":
    unittest.main()
