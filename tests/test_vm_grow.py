"""Ä-037: VM-Disk beim Zurückspielen vergrössern – Entscheidung „welche Wege gehen, warum nicht“, Virsh-Schritte
mit nachgebildetem virsh, Ablauf des Auftrags mit gefälschtem Virsh/Agent und belegte Daten eines Images
(ohne libvirt und GTK)."""

import threading
import unittest
from dataclasses import dataclass
from unittest import mock

from okula_recovery import agentclient, jobs, shrink, vm
from tests.test_vm import FakeVirsh

GB = 10**9
L15_512 = 512110190592          # Quelldisk Lenovo L15 512 GB (Byte)


class DecisionTest(unittest.TestCase):
    def test_grow_size_rounds_up_to_whole_gb(self):
        self.assertEqual(vm.grow_size_gb(L15_512), 513)
        self.assertEqual(vm.grow_size_gb(256060514304), 257)
        self.assertEqual(vm.grow_size_gb(128 * GB), 128)
        self.assertEqual(vm.grow_size_gb(1_000_204_886_016), 1001)          # Samsung 970 EVO 1 TB

    def test_reserve_ten_percent_min_10_gb(self):
        self.assertEqual(vm.grow_reserve(20 * GB), 10 * GB)
        self.assertEqual(vm.grow_reserve(300 * GB), 30 * GB)

    def test_grow_why(self):
        self.assertEqual(vm.grow_why(0, 500 * GB, 100 * GB), "")
        self.assertEqual(vm.grow_why(2, 500 * GB, 100 * GB), vm.SNAPSHOTS_BLOCK_GROW)
        self.assertIn("Reiter „Snapshots“ löschen", vm.SNAPSHOTS_BLOCK_GROW)
        why = vm.grow_why(0, 100 * GB, 100 * GB)
        self.assertIn("Zu wenig Platz", why)
        self.assertIn("frei 100 GB, nötig 110 GB", why)
        self.assertIn("Daten im Image 100 GB + Reserve 10 GB", why)
        self.assertEqual(vm.grow_why(0, 110 * GB, 100 * GB), "")             # genau genug

    def test_both_ways_grow_is_default(self):
        w = vm.restore_ways(L15_512, {"snapshots": 0, "pool_free": 700 * GB, "image_used": 80 * GB},
                            ["C: wird verkleinert"])
        self.assertEqual((w.grow_gb, w.grow_ok, w.adapt_ok, w.pending), (513, True, True, False))
        self.assertEqual(w.default(), "grow")
        self.assertEqual(w.adapt_lines, ["C: wird verkleinert"])
        self.assertTrue(w.allowed("grow") and w.allowed("adapt"))

    def test_snapshots_block_grow_adapt_still_possible(self):
        w = vm.restore_ways(L15_512, {"snapshots": 1, "pool_free": 700 * GB, "image_used": 80 * GB}, ["ok"])
        self.assertFalse(w.grow_ok)
        self.assertEqual(w.grow_why, vm.SNAPSHOTS_BLOCK_GROW)
        self.assertEqual(w.default(), "adapt")
        self.assertFalse(w.allowed("grow"))

    def test_no_way(self):
        w = vm.restore_ways(L15_512, {"snapshots": 0, "pool_free": 50 * GB, "image_used": 80 * GB},
                            "Passt nicht: auf sda3 sind 300 GB belegt")
        self.assertEqual(w.default(), "")
        self.assertFalse(w.allowed("grow") or w.allowed("adapt"))
        self.assertIn("Passt nicht", w.adapt_why)

    def test_pending_and_errors(self):
        w = vm.restore_ways(L15_512, None, None)
        self.assertTrue(w.pending)
        self.assertFalse(w.grow_ok or w.adapt_ok)
        w = vm.restore_ways(L15_512, "Prüfung fehlgeschlagen: libvirt weg", ["ok"])
        self.assertEqual((w.grow_ok, w.adapt_ok, w.default()), (False, True, "adapt"))
        self.assertEqual(vm.grow_history(128, 513), "VM-Disk von 128 GB auf 513 GB vergrössert")


class SleeplessFake(FakeVirsh):
    """virsh, bei dem „shutdown“ erst nach einigen Abfragen wirkt (oder nie)."""

    def __init__(self, polls_until_off: int | None = 1):
        super().__init__()
        self.polls_until_off = polls_until_off
        self.pending_off: str | None = None
        self.pool_out = ""

    def __call__(self, cmd, input_text=None):
        import subprocess
        args = cmd[3:]
        if args[0] == "shutdown":
            self.calls.append(args)
            self.pending_off, self.left = args[1], self.polls_until_off
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if args[0] == "domstate" and self.pending_off == args[1] and self.left is not None:
            if self.left <= 0:
                self.states[args[1]] = "shut off"
                self.pending_off = None
            self.left -= 1
        if args[0] == "pool-info":
            self.calls.append(args)
            return subprocess.CompletedProcess(cmd, 0 if self.pool_out else 1, self.pool_out, "")
        return super().__call__(cmd, input_text)


class VirshGrowTest(unittest.TestCase):
    def setUp(self):
        self.fake = SleeplessFake()
        self.v = vm.Virsh(run=self.fake, sleep=lambda s: None)
        self.p = self.v.create(vm.profile("VM-Klein"), name="VM-T")

    def test_power_down_clean(self):
        self.v.start("VM-T")
        self.assertEqual(self.v.power_down("VM-T"), "clean")
        self.assertIn(["shutdown", "VM-T", "--mode", "acpi"], self.fake.calls)
        self.assertNotIn(["destroy", "VM-T"], self.fake.calls)
        self.assertEqual(self.v.power_down("VM-T"), "off")

    def test_power_down_hard_after_timeout(self):
        self.fake.polls_until_off = None                      # reagiert nicht auf ACPI
        self.v.start("VM-T")
        self.assertEqual(self.v.power_down("VM-T", timeout=6), "hard")
        self.assertIn(["destroy", "VM-T"], self.fake.calls)

    def test_power_down_cancel(self):
        self.fake.polls_until_off = None
        self.v.start("VM-T")
        with self.assertRaisesRegex(vm.VmError, "abgebrochen"):
            self.v.power_down("VM-T", cancelled=lambda: True)

    def test_grow_disk_keeps_model_and_identity(self):
        old, new = self.v.grow_disk("VM-T", 513)
        self.assertEqual((old, new), (64, 513))
        self.assertEqual(self.fake.volumes["VM-T.qcow2"], 513 * GB)
        p = self.v.get_profile("VM-T")
        self.assertEqual((p.disk.size_gb, p.disk.model, p.disk.serial, p.nic.mac, p.smbios.uuid, p.ram_mb),
                         (513, "Okula SATA SSD 64GB", self.p.disk.serial, self.p.nic.mac, self.p.smbios.uuid,
                          self.p.ram_mb))
        self.assertEqual(self.v.grow_disk("VM-T", 200), (513, 513))         # schon gross genug: nichts
        self.assertEqual(self.fake.volumes["VM-T.qcow2"], 513 * GB)

    def test_grow_disk_refused_with_snapshots(self):
        from tests.test_vm_snapshots import ChainFake
        v = vm.Virsh(run=ChainFake(), sleep=lambda _s: None)
        v.create(vm.profile("VM-Win11"), "W")
        self.assertEqual(v.snapshot_count("W"), 0)
        v.snapshot_create("W", "vorher")
        self.assertEqual(v.snapshot_count("W"), 1)
        with self.assertRaisesRegex(vm.VmError, "Snapshots"):
            v.grow_disk("W", 513)

    def test_pool_free(self):
        self.fake.pool_out = "Name:           okula\nState:          running\nAvailable:      812345678901\n"
        self.assertEqual(self.v.pool_free(), 812345678901)
        self.fake.pool_out = ""
        with mock.patch.object(vm, "free_disk", lambda: 42):
            self.assertEqual(self.v.pool_free(), 42)


# ---------- Ablauf des Auftrags ----------

@dataclass
class Agent:
    ip: str = "10.0.0.50"
    control_port: int = 9701
    last_seen: float = 0.0


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class FakeJM:
    def __init__(self):
        self.lines, self.phases = [], []

    def log(self, job, line):
        self.lines.append(line)

    def progress(self, job, fraction, detail, phase="", phase_fraction=0.0):
        if not self.phases or self.phases[-1] != phase:
            self.phases.append(phase)


class FlowVirsh:
    """Gefälschtes Virsh mit Protokoll der Aufrufe."""

    def __init__(self, size_gb=128, snapshots=0, fail=""):
        self.size_gb, self.snapshots, self.fail = size_gb, snapshots, fail
        self.calls = []

    def power_down(self, name, cancelled=lambda: False):
        self.calls.append("power_down")
        if self.fail == "power_down":
            raise vm.VmError("VM lässt sich nicht ausschalten")
        return "clean"

    def grow_disk(self, name, size_gb):
        self.calls.append(f"grow {size_gb}")
        if self.snapshots:
            raise vm.VmError("Disk lässt sich nicht vergrössern, solange es Snapshots gibt")
        old = self.size_gb
        self.size_gb = max(old, size_gb)
        return old, self.size_gb

    def start(self, name, mode="normal"):
        self.calls.append(f"start {mode}")


class FlowTest(unittest.TestCase):
    def run_flow(self, virsh, agents, disk_size=None, snapshot=True, cancel_at=None, timeout=300):
        clock = Clock()
        events = virsh.calls
        job = jobs.Job(1, "dev", "restore", "/dev/nvme0n1", "VM-Disk vergrössern und zurückspielen")
        jm = FakeJM()
        result = {}
        seq = iter(agents)

        def find_agent():
            if cancel_at == "agent":
                job.cancel.set()
            try:
                a = next(seq)
            except StopIteration:
                return None
            return a(clock) if callable(a) else a

        def get_disks(agent):
            size = disk_size if disk_size is not None else virsh.size_gb * GB
            return [{"path": "/dev/nvme0n1", "size": size}]

        def restore(agent):
            def work(job_, jm_):
                events.append(f"restore via {agent.ip}")
                jm_.progress(job_, 0.5, "x", "Image prüfen (1/2)", 0.5)
                return "/dev/nvme0n1 zurückgespielt"
            return work

        work = jobs.grow_restore_work(
            virsh, "VM-T", 513, "/dev/nvme0n1", find_agent, get_disks, restore,
            snapshot=(lambda: events.append("snapshot")) if snapshot else None,
            grown=lambda o, n: result.setdefault("grown", (o, n)),
            failed=lambda m, c: result.setdefault("failed", (m, c)),
            agent_timeout=timeout, clock=clock, sleep=lambda s: setattr(clock, "t", clock.t + s))
        try:
            result["return"] = work(job, jm)
        except Exception as e:
            result["error"] = str(e)
        return result, jm

    def test_four_steps_snapshot_after_grow(self):
        stale = Agent(ip="10.0.0.9", last_seen=50.0)          # alter Agent vor dem Herunterfahren
        fresh = lambda clock: Agent(last_seen=clock.t)        # noqa: E731 – meldet sich nach dem Einschalten
        virsh = FlowVirsh()
        result, jm = self.run_flow(virsh, [stale, None, fresh])
        self.assertEqual(result.get("return"), "/dev/nvme0n1 zurückgespielt")
        self.assertEqual(virsh.calls, ["power_down", "grow 513", "start agent", "snapshot", "restore via 10.0.0.50"])
        self.assertEqual(result["grown"], (128, 513))
        self.assertNotIn("failed", result)
        self.assertEqual(jm.phases[:3], list(vm.GROW_STEPS[:3]))
        self.assertIn("Zurückspielen (4/4) · Image prüfen (1/2)", jm.phases)
        self.assertIn("VM-Disk von 128 GB auf 513 GB vergrössert (Daten unverändert)", jm.lines)

    def test_without_snapshot(self):
        virsh = FlowVirsh()
        result, _ = self.run_flow(virsh, [lambda c: Agent(last_seen=c.t)], snapshot=False)
        self.assertNotIn("snapshot", virsh.calls)
        self.assertIn("return", result)

    def test_snapshots_block_nothing_restored(self):
        virsh = FlowVirsh(snapshots=1)
        result, jm = self.run_flow(virsh, [])
        self.assertIn("Snapshots", result["error"])
        self.assertEqual(result["failed"][1], False)
        self.assertEqual(virsh.calls, ["power_down", "grow 513"])
        self.assertIn("Nichts zurückgespielt.", jm.lines)

    def test_agent_timeout_disk_stays_grown(self):
        virsh = FlowVirsh()
        result, jm = self.run_flow(virsh, [], timeout=10)
        self.assertIn("nicht gemeldet", result["error"])
        self.assertIn("nicht gemeldet", result["failed"][0])
        self.assertNotIn("restore via 10.0.0.50", virsh.calls)
        self.assertTrue(any("bleibt vergrössert (513 GB" in line for line in jm.lines))

    def test_disk_still_too_small(self):
        virsh = FlowVirsh()
        result, _ = self.run_flow(virsh, [lambda c: Agent(last_seen=c.t)], disk_size=128 * GB)
        self.assertIn("nötig 513 GB", result["error"])
        self.assertNotIn("snapshot", virsh.calls)

    def test_cancel_while_waiting(self):
        virsh = FlowVirsh()
        result, _ = self.run_flow(virsh, [None, None], cancel_at="agent")
        self.assertEqual(result["error"], "abgebrochen")
        self.assertEqual(result["failed"], ("abgebrochen", True))

    def test_shutdown_fails(self):
        virsh = FlowVirsh(fail="power_down")
        result, jm = self.run_flow(virsh, [])
        self.assertEqual(virsh.calls, ["power_down"])
        self.assertNotIn("grown", result)
        self.assertIn("ausschalten", result["failed"][0])

    def test_already_big_enough(self):
        virsh = FlowVirsh(size_gb=600)
        result, jm = self.run_flow(virsh, [lambda c: Agent(last_seen=c.t)])
        self.assertNotIn("grown", result)
        self.assertIn("Disk ist schon 600 GB gross – nichts zu vergrössern", jm.lines)
        self.assertIn("return", result)


class SourceTest(unittest.TestCase):
    """Dialog und Hauptfenster brauchen GTK – hier nur Syntax und Texte laut Prompt (ohne GTK)."""

    def test_dialog_and_ui_texts(self):
        import ast
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "okula_recovery"
        dialog = (root / "restore_dialog.py").read_text(encoding="utf-8")
        ui = (root / "ui.py").read_text(encoding="utf-8")
        ast.parse(dialog)
        ast.parse(ui)
        self.assertIn("VM-Disk auf {n} GB vergrössern und zurückspielen", dialog)
        self.assertIn("Image an die kleinere Disk anpassen", dialog)
        self.assertIn("vm_info=vm_info", ui)
        self.assertIn("VM-Disk vergrössern und zurückspielen {label} → {target}", ui)
        self.assertEqual(vm.GROW_STEPS, ("VM wird heruntergefahren (1/4)", "Disk wird vergrössert (2/4)",
                                         "Agent wird gestartet (3/4)", "Zurückspielen (4/4)"))


class UsedBytesTest(unittest.TestCase):
    def test_used_bytes_from_headers_dd_and_files(self):
        src = {"source": {"name": "sda", "size": L15_512,
                          "partitions": [{"name": "sda1", "size": 300 * 2**20}, {"name": "sda2", "size": 16 * 2**20},
                                         {"name": "sda3", "size": 500 * GB}]},
               "head": b"\0" * 1024,
               "steps": [{"kind": "pcl", "part": "sda1", "size": 5_000_000},
                         {"kind": "dd", "part": "sda2", "size": 1000},
                         {"kind": "pcl", "part": "sda3", "size": 40 * GB},
                         {"kind": "swap", "part": "sda4"}]}

        def header(step):
            if step["part"] == "sda3":
                raise shrink.ShrinkError("Unbekanntes partclone-Format")
            return {"used": 30_000_000}

        with mock.patch.object(agentclient, "image_source", lambda path, disk=None: src), \
                mock.patch.object(shrink, "read_header", header):
            self.assertEqual(shrink.used_bytes("/nas/img"), 1024 + 30_000_000 + 16 * 2**20 + 40 * GB)

    def test_used_bytes_bad_image(self):
        def bad(path, disk=None):
            raise agentclient.AgentError("Image ohne Kopfbereich")
        with mock.patch.object(agentclient, "image_source", bad):
            with self.assertRaisesRegex(shrink.ShrinkError, "Kopfbereich"):
                shrink.used_bytes("/nas/img")


if __name__ == "__main__":
    unittest.main()
