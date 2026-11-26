"""Ä-052: USB-Vorgänge als Auftrag (Auftragsliste „USB-Vorgänge“), belegte Datenträger gesperrt."""

import threading
import time
import unittest

from okula_recovery import jobs, stick, usbjobs
from okula_recovery.usbguard import Ident

A = Ident("/dev/sdb", "SERIAL-A", "SanDisk Ultra", 32_000_000_000)
B = Ident("/dev/sdc", "SERIAL-B", "SanDisk Ultra", 32_000_000_000)


class FakeRunner:
    """Statt des Root-Helfers: meldet Fortschritt, wartet auf release oder Abbrechen."""
    instances: list["FakeRunner"] = []

    def __init__(self, cmd, stdin_text="", cwd=None, idents=()):
        self.cmd, self.idents = cmd, tuple(idents)
        self.release = threading.Event()
        self.result = (True, "")
        self.done_text = "fertig geklont"
        self.started = threading.Event()
        FakeRunner.instances.append(self)

    def run(self, cancel, on_progress, on_line):
        self.started.set()
        on_progress(0.25, "1:1-Kopie · 1.0 / 4.0 GB")
        on_line("WARN Hinweis vom Helfer")
        on_line("INFO Mitgeliefert: nichts")
        while not self.release.wait(0.01):
            if cancel.is_set():
                return False, "Abgebrochen – Ziel unvollständig"
        return self.result


def wait_until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class UsbJobsTest(unittest.TestCase):
    def setUp(self):
        FakeRunner.instances.clear()
        self.jm = jobs.JobManager()
        self.done: list[tuple[bool, str]] = []
        self.progress: list[float] = []

    def start(self, idents, title="USB klonen SanDisk Ultra → SanDisk Ultra"):
        return usbjobs.start(self.jm, title, ["x"], "", idents, lambda f, m: self.progress.append(f),
                             lambda _l: None, lambda ok, err: self.done.append((ok, err)), runner=FakeRunner)

    def test_job_in_list_with_progress_and_result(self):
        job = self.start([A, B])
        self.assertTrue(FakeRunner.instances[0].started.wait(5))
        self.assertTrue(wait_until(lambda: job.fraction == 0.25))
        self.assertEqual((job.device_id, job.kind, job.label), (usbjobs.USB_DEVICE, usbjobs.KIND, "USB-Vorgang"))
        self.assertEqual(usbjobs.running(self.jm), [job])
        self.assertTrue(any("Hinweis: Hinweis vom Helfer" in line for line in job.log))
        self.assertTrue(any(line.endswith("Mitgeliefert: nichts") for line in job.log))
        FakeRunner.instances[0].release.set()
        self.assertTrue(wait_until(lambda: not job.running))
        self.assertEqual(job.state, jobs.DONE)
        self.assertEqual(job.result, "fertig geklont")
        self.assertEqual(self.done, [(True, "")])
        self.assertEqual(self.progress, [0.25])

    def test_disks_in_use_by_path_and_serial(self):
        job = self.start([A, B])
        self.assertTrue(FakeRunner.instances[0].started.wait(5))
        self.assertIs(usbjobs.in_use(stick.UsbDisk("/dev/sdb", 1)), job)
        # umgesteckt: anderer Name, gleiche Seriennummer → weiter belegt
        self.assertIs(usbjobs.in_use(stick.UsbDisk("/dev/sdd", 1, serial="SERIAL-B")), job)
        self.assertIsNone(usbjobs.in_use(stick.UsbDisk("/dev/sde", 1, serial="ANDERS")))
        self.assertIsNone(usbjobs.in_use(stick.UsbDisk("/dev/sdb", 1), exclude=job))
        with self.assertRaises(usbjobs.Busy) as ctx:
            self.start([Ident("/dev/sdx", "SERIAL-A")], "USB formatieren")
        self.assertIn(usbjobs.IN_USE, str(ctx.exception))
        FakeRunner.instances[0].release.set()
        self.assertTrue(wait_until(lambda: not job.running))
        self.assertIsNone(usbjobs.in_use(stick.UsbDisk("/dev/sdb", 1)))

    def test_parallel_on_different_disks(self):
        one = self.start([A], "USB formatieren A")
        two = self.start([B], "USB formatieren B")
        self.assertTrue(one.running and two.running)
        for r in FakeRunner.instances:
            r.release.set()
        self.assertTrue(wait_until(lambda: not one.running and not two.running))

    def test_cancel_from_list(self):
        job = self.start([A])
        self.assertTrue(FakeRunner.instances[0].started.wait(5))
        usbjobs.cancel(self.jm, job)
        self.assertTrue(wait_until(lambda: not job.running))
        self.assertEqual(job.state, jobs.CANCELLED)
        self.assertTrue(any(line.endswith("Abbruch angefordert …") for line in job.log))
        self.assertEqual(self.done, [(False, "Abgebrochen – Ziel unvollständig")])

    def test_failed_and_disk_gone(self):
        job = self.start([A])
        runner = FakeRunner.instances[0]
        runner.result = (False, "Datenträger getrennt – abgebrochen (SanDisk Ultra, SN SERIAL-A)")
        runner.release.set()
        self.assertTrue(wait_until(lambda: not job.running))
        self.assertEqual(job.state, jobs.FAILED)          # getrennt ist kein Abbruch durch den Benutzer
        self.assertIn("Datenträger getrennt", job.log[-1])

    def test_listeners_notified(self):
        calls = []
        fn = lambda: calls.append(1)  # noqa: E731
        usbjobs.subscribe(fn)
        try:
            job = self.start([A])
            self.assertEqual(len(calls), 1)
            FakeRunner.instances[0].release.set()
            self.assertTrue(wait_until(lambda: len(calls) == 2))
            self.assertTrue(wait_until(lambda: not job.running))
        finally:
            usbjobs.unsubscribe(fn)

    def test_manager_of_main_window(self):
        class Main:
            jobs = jobs.JobManager()
        self.assertIs(usbjobs.manager(Main()), Main.jobs)
        self.assertIs(usbjobs.manager(None), usbjobs.manager(object()))

    def test_log_text(self):
        self.assertEqual(usbjobs.log_text("WARN x"), "Hinweis: x")
        self.assertIsNone(usbjobs.log_text("DONE fertig"))
        self.assertIsNone(usbjobs.log_text("ERROR kaputt"))
        self.assertEqual(usbjobs.log_text("irgendwas"), "irgendwas")


class JobStatusTest(unittest.TestCase):
    def test_texts(self):
        from okula_recovery import usb_dialogs
        job = jobs.Job(1, usbjobs.USB_DEVICE, usbjobs.KIND, "/dev/sdb", "USB formatieren")
        job.fraction, job.detail = 0.4, "Formatieren (FAT32)"
        self.assertEqual(usb_dialogs.job_status(job), (0.4, "40 %  Formatieren (FAT32)"))
        job.cancel.set()
        self.assertEqual(usb_dialogs.job_status(job)[1], "40 %  Wird abgebrochen …")
        job.state, job.result = jobs.DONE, "/dev/sdb ist als FAT32 formatiert"
        self.assertEqual(usb_dialogs.job_status(job), (1.0, "Fertig: /dev/sdb ist als FAT32 formatiert"))
        job.state = jobs.FAILED
        job.log.append("12:00:00 Fehler: Datenträger getrennt – abgebrochen (X)")
        self.assertEqual(usb_dialogs.job_status(job)[1], "Fehler: Datenträger getrennt – abgebrochen (X)")


if __name__ == "__main__":
    unittest.main()
