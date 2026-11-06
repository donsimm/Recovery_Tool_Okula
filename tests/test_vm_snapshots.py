"""Snapshots der VMs (I-001 Auftrag 4): externe Overlays, Zurücksetzen, Löschen per block-stream – mit einem
nachgebildeten virsh, das qcow2-Ketten samt Inhalt im Speicher führt."""

import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from okula_recovery import vm
from tests.test_vm import FakeVirsh

POOL = vm.POOL_DIR + "/"


class ChainFake(FakeVirsh):
    """qcow2-Ketten: volumes (Name → Kapazität), backing (Name → Pfad), data (Name → {Block: Inhalt})."""

    def __init__(self):
        super().__init__()
        self.backing: dict[str, str] = {}
        self.data: dict[str, dict] = {}
        self.transient: dict[str, str] = {}     # Hilfs-VM → Disk-Pfad
        self.jobs: dict[str, list] = {}

    # --- Inhalt (wie der Gast die Disk sieht) ---
    def content(self, path: str) -> dict:
        name = Path(path).name
        result = dict(self.content(self.backing[name])) if self.backing.get(name) else {}
        result.update(self.data.get(name, {}))
        return result

    def top(self, dom: str) -> str:
        return vm.disk_from_xml(self.domains[dom])

    def write(self, dom: str, block: str, value: str) -> None:
        self.data.setdefault(Path(self.top(dom)).name, {})[block] = value

    def __call__(self, cmd, input_text=None):
        args = cmd[3:]
        op = args[0]
        if op in self.fail:
            return super().__call__(cmd, input_text)
        out = ""
        if op == "vol-create-as":
            self.calls.append(args)
            name = args[2]
            self.volumes[name] = int(args[3])
            if "--backing-vol" in args:
                back = args[args.index("--backing-vol") + 1]
                assert Path(back).name in self.volumes, back
                assert self.volumes[Path(back).name] == int(args[3])          # gleiche Grösse wie die Backing-Datei
                self.backing[name] = back
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if op == "vol-delete":
            self.calls.append(args)
            name = args[-1]
            users = [n for n, b in self.backing.items() if Path(b).name == name and n in self.volumes]
            assert not users, f"{name} wird noch von {users} gebraucht"
            self.volumes.pop(name, None)
            self.backing.pop(name, None)
            self.data.pop(name, None)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if op == "undefine":
            self.calls.append(args)
            top = Path(self.top(args[1])).name
            self.domains.pop(args[1])
            self.states.pop(args[1])
            if top in self.volumes:          # --remove-all-storage: nur die oberste Datei
                self.volumes.pop(top)
                self.backing.pop(top, None)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if op == "pool-refresh":
            pass
        elif op == "vol-list":
            out = " Name   Path\n" + "-" * 20 + "\n" + "".join(f" {n}   {POOL}{n}\n" for n in self.volumes)
        elif op == "vol-info":
            name = args[3]
            if name not in self.volumes:
                return subprocess.CompletedProcess(cmd, 1, "", "error: Storage volume not found")
            out = (f"Name:  {name}\nCapacity:       {self.volumes[name]} bytes\n"
                   f"Allocation:     {len(self.data.get(name, {})) * 1000 + 200} bytes\n")
        elif op == "vol-dumpxml":
            name = args[-1]
            back = self.backing.get(name)
            out = f"<volume><name>{name}</name>" + (f"<backingStore><path>{back}</path></backingStore>"
                                                    if back else "") + "</volume>"
        elif op == "snapshot-create-as":
            dom = args[1]
            assert self.states[dom] == "running"
            new = re.search(r"file=(\S+)", args[-1]).group(1)
            old = self.top(dom)
            self.volumes[Path(new).name] = self.volumes[Path(old).name]
            self.backing[Path(new).name] = old
            self.domains[dom] = self.domains[dom].replace(f"file=\"{old}\"", f"file=\"{new}\"")
        elif op == "metadata":
            dom, xml = args[1], args[args.index("--set") + 1]
            root = ET.fromstring(self.domains[dom])
            meta = root.find("metadata")
            for el in meta.findall(f"{{{vm.SNAP_NS}}}snapshots"):
                meta.remove(el)
            ET.SubElement(meta, f"{{{vm.SNAP_NS}}}snapshots").text = ET.fromstring(xml).text
            self.domains[dom] = ET.tostring(root, encoding="unicode")
        elif op == "create":
            assert "--paused" in args
            root = ET.fromstring(Path(args[1]).read_text())
            self.transient[root.find("name").text] = root.find("devices/disk/source").get("file")
        elif op == "blockpull":
            helper = args[1]
            target = Path(self.transient[helper]).name
            base = args[args.index("--base") + 1] if "--base" in args else ""
            merged, chain = {}, []
            node = self.backing.get(target)
            while node and node != base:
                chain.append(Path(node).name)
                node = self.backing.get(Path(node).name)
            for layer in reversed(chain):
                merged.update(self.data.get(layer, {}))
            merged.update(self.data.get(target, {}))
            self.data[target] = merged
            if base:
                self.backing[target] = base
            else:
                self.backing.pop(target, None)
            self.jobs[helper] = ["type=Pull cur=50 end=100", "type=Pull cur=100 end=100"]
        elif op == "blockjob":
            left = self.jobs.get(args[1]) or []
            out = left.pop(0) if left else "No current block job for hda\n"
        elif op == "destroy" and args[1] in self.transient:
            self.transient.pop(args[1])
        elif op == "list" and "--name" in args:
            out = "\n".join(list(self.domains) + list(self.transient)) + "\n"
        else:
            return super().__call__(cmd, input_text)
        self.calls.append(args)
        return subprocess.CompletedProcess(cmd, 0, out, "")


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.fake = ChainFake()
        self.v = vm.Virsh(run=self.fake, sleep=lambda _s: None)
        p = vm.profile("VM-Win11")
        p.disk.size_gb = 2
        self.v.create(p, "W")
        self.fake.write("W", "boot", "leer")

    def content(self):
        return self.fake.content(self.fake.top("W"))

    def test_create_revert_keeps_old_state(self):
        a = self.v.snapshot_create("W", "frisch installiert", info={"blank": False})
        self.assertEqual((a.id, a.file, a.parent, a.auto), (1, POOL + "W.qcow2", 0, False))
        self.assertEqual(self.fake.top("W"), POOL + "W.snap-1.qcow2")
        self.fake.write("W", "boot", "Windows")
        b = self.v.snapshot_create("W", "")                                  # Titel leer → Vorgabe
        self.assertRegex(b.title, r"^Snapshot \d\d\.\d\d\. \d\d:\d\d$")
        self.fake.write("W", "datei", "neu")
        self.assertEqual(self.content(), {"boot": "Windows", "datei": "neu"})
        self.v.snapshot_revert("W", a.id)
        self.assertEqual(self.content(), {"boot": "leer"})                   # alter Stand
        self.assertNotIn("W.snap-2.qcow2", self.fake.volumes)                # Änderungen seit b gelöscht
        snaps = self.v.snapshots("W")
        self.assertEqual([(s.title, s.current) for s in snaps], [("frisch installiert", True), (b.title, False)])
        self.assertEqual(snaps[0].info, {"blank": False})
        self.v.snapshot_revert("W", b.id)                                    # spätere Snapshots bleiben gültig
        self.assertEqual(self.content(), {"boot": "Windows"})
        # Profil, Metadaten und Disk bleiben beim Neu-Definieren (Start mit Agent definiert zweimal)
        self.v.start("W", "agent")
        self.assertEqual(self.fake.top("W"), self.v._layout("W")[0])
        self.assertEqual(len(self.v.snapshots("W")), 2)
        self.assertTrue(self.fake.top("W").startswith(POOL + "W.snap-"))

    def test_only_when_off(self):
        self.v.start("W")
        with self.assertRaisesRegex(vm.VmError, "ausgeschalteter VM"):
            self.v.snapshot_create("W", "x")
        self.v.poweroff("W")
        s = self.v.snapshot_create("W", "x")
        self.v.start("W")
        for action in (lambda: self.v.snapshot_revert("W", s.id), lambda: self.v.snapshot_delete("W", s.id)):
            with self.assertRaisesRegex(vm.VmError, "ausgeschalteter VM"):
                action()
        with self.assertRaisesRegex(vm.VmError, "höchstens 80"):
            self.v.poweroff("W") or self.v.snapshot_create("W", "x" * 81)

    def test_auto_snapshot_with_agent_running(self):
        self.v.start("W", "agent")
        s = self.v.snapshot_create("W", vm.auto_title("Zurückspielen", datetime(2026, 11, 6, 14, 5)), auto=True,
                                   running_ok=True)
        self.assertEqual(s.title, "vor Zurückspielen 06.11. 14:05")
        self.assertTrue(any(c[0] == "snapshot-create-as" and "--no-metadata" in c and "--disk-only" in c
                            for c in self.fake.calls))
        meta = next(c for c in self.fake.calls if c[0] == "metadata")
        self.assertIn("--live", meta)
        self.assertIn("--config", meta)
        self.fake.write("W", "boot", "Image")
        self.v.poweroff("W")
        snaps = self.v.snapshots("W")
        self.assertEqual([(x.auto, x.current) for x in snaps], [(True, True)])
        self.v.snapshot_revert("W", s.id)
        self.assertEqual(self.content(), {"boot": "leer"})

    def test_failed_live_snapshot_raises(self):
        self.v.start("W", "agent")
        self.fake.fail["snapshot-create-as"] = "error: internal error: unable to execute QEMU command"
        with self.assertRaises(vm.VmError):
            self.v.snapshot_create("W", "vor X", auto=True, running_ok=True)
        self.assertEqual(self.v.snapshots("W"), [])

    def test_delete_newest_oldest_and_middle(self):
        a = self.v.snapshot_create("W", "A")
        self.fake.write("W", "1", "a")
        b = self.v.snapshot_create("W", "B")
        self.fake.write("W", "2", "b")
        c = self.v.snapshot_create("W", "C")
        self.fake.write("W", "3", "c")
        now = self.content()
        steps = []
        self.v.snapshot_delete("W", b.id, progress=lambda f, t: steps.append((f, t)))     # mitten drin
        self.assertEqual(self.content(), now)
        self.assertEqual(steps[-1][0], 1.0)
        self.assertIn(["create", self.fake.calls[[c[0] for c in self.fake.calls].index("create")][1], "--paused"],
                      self.fake.calls)
        self.assertEqual(self.fake.transient, {})                                        # Hilfs-VM wieder weg
        self.v.snapshot_revert("W", c.id)                                                # C noch richtig
        self.assertEqual(self.content(), {"boot": "leer", "1": "a", "2": "b"})
        self.v.snapshot_revert("W", a.id)
        self.assertEqual(self.content(), {"boot": "leer"})
        self.fake.write("W", "4", "d")
        self.v.snapshot_delete("W", a.id)                                                # älteste (Disk-Datei)
        self.assertNotIn("W.qcow2", self.fake.volumes)
        self.assertEqual(self.content(), {"boot": "leer", "4": "d"})
        self.v.snapshot_revert("W", c.id)
        self.assertEqual(self.content(), {"boot": "leer", "1": "a", "2": "b"})
        self.v.snapshot_delete("W", c.id)                                                # letzte
        self.assertEqual(self.v.snapshots("W"), [])
        self.assertEqual(self.content(), {"boot": "leer", "1": "a", "2": "b"})
        self.assertEqual(len(self.fake.volumes), 1)                                      # nur noch die Disk
        # ohne Snapshots lässt sich die Disk wieder vergrössern (die oberste Datei)
        p = self.v.get_profile("W")
        p.disk.size_gb = 3
        self.v.set_profile("W", p)
        self.assertEqual(self.fake.volumes[Path(self.fake.top("W")).name], 3 * 10**9)

    def test_failed_stream_keeps_snapshot(self):
        a = self.v.snapshot_create("W", "A")
        self.fake.write("W", "x", "1")
        real = self.fake.__call__

        def broken(cmd, input_text=None):
            if cmd[3] == "blockpull":          # Job endet ohne Ergebnis
                self.fake.calls.append(cmd[3:])
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return real(cmd, input_text)

        v = vm.Virsh(run=broken, sleep=lambda _s: None)
        with self.assertRaisesRegex(vm.VmError, "nicht abgeschlossen"):
            v.snapshot_delete("W", a.id)
        self.assertEqual([s.id for s in self.v.snapshots("W")], [a.id])
        self.assertIn("W.qcow2", self.fake.volumes)
        self.assertEqual(self.fake.transient, {})

    def test_hardware_with_snapshots(self):
        self.v.snapshot_create("W", "A")
        p = self.v.get_profile("W")
        p.ram_mb, p.cpu.cores, p.nic.model = 4096, 2, "e1000"
        self.v.set_profile("W", p)                                       # RAM/CPU/Netzwerkkarte gehen
        self.assertEqual(len(self.v.snapshots("W")), 1)
        self.assertEqual(self.fake.top("W"), POOL + "W.snap-1.qcow2")
        p.disk.size_gb = 5
        with self.assertRaisesRegex(vm.VmError, "zuerst Snapshots löschen"):
            self.v.set_profile("W", p)

    def test_delete_vm_removes_all_files(self):
        a = self.v.snapshot_create("W", "A")
        self.v.snapshot_create("W", "B")
        self.v.snapshot_revert("W", a.id)
        self.v.start("W", "agent")
        self.v.snapshot_create("W", "vor C", auto=True, running_ok=True)
        self.fake.volumes["W.snap-99.qcow2"] = 1        # liegengebliebene Datei
        self.v.create(vm.profile("VM-Klein"), "W2")
        self.v.delete("W")
        self.assertEqual(sorted(self.fake.volumes), ["W2.qcow2"])
        self.assertNotIn("W", self.fake.domains)

    def test_sizes_and_changes(self):
        self.fake.write("W", "a", "1")
        self.v.snapshot_create("W", "A")
        self.fake.write("W", "b", "2")
        self.fake.write("W", "c", "3")
        self.assertEqual(self.v.snapshots("W")[0].size, 2 * 1000 + 200)
        self.assertEqual(self.v.snapshot_changes("W"), 2 * 1000 + 200)


class SnapshotHelpersTest(unittest.TestCase):
    def test_titles_and_texts(self):
        t = datetime(2026, 11, 6, 9, 7)
        self.assertEqual(vm.snapshot_title(t), "Snapshot 06.11. 09:07")
        self.assertEqual(vm.auto_title("Automatisierung", t), "vor Automatisierung 06.11. 09:07")
        self.assertEqual(vm.history_text("erstellt", "vor Sysprep"), "Snapshot ‚vor Sysprep‘ erstellt")
        self.assertEqual(vm.low_space_text(60 * 10**9), "")
        self.assertIn("unter 50 GB", vm.low_space_text(49 * 10**9))

    def test_state_roundtrip_and_xml(self):
        st = vm.SnapState(seq=3, current=2, items=[vm.Snapshot(id=2, title="Ä „x“ <y>", created="2026-11-06T10:00:00",
                                                               file="/f", parent=0, size=5, current=True)])
        back = vm.SnapState.from_json(st.to_json())
        self.assertEqual((back.seq, back.current, back.items[0].title, back.items[0].size), (3, 2, "Ä „x“ <y>", 0))
        p = vm.fill_identity(vm.profile("VM-Klein"))
        xml = vm.domain_xml(p, disk_file="/x/VM-Klein.snap-3.qcow2", snapshots=st)
        self.assertEqual(vm.disk_from_xml(xml), "/x/VM-Klein.snap-3.qcow2")
        self.assertEqual(vm.snapshots_from_xml(xml).items[0].title, "Ä „x“ <y>")
        self.assertEqual(vm.profile_from_xml(xml).name, "VM-Klein")
        self.assertEqual(vm.snapshots_from_xml(vm.domain_xml(p)).items, [])
        self.assertEqual(ET.fromstring(vm.snap_element(st)).tag, "snapshots")
        helper = ET.fromstring(vm.helper_xml("okula-merge-X", "/x/a.qcow2"))
        self.assertIsNone(helper.find("devices/interface"))
        self.assertEqual(helper.find("devices/disk/source").get("file"), "/x/a.qcow2")

    def test_blank_disk_after_revert(self):
        hist = [{"kind": "install", "text": "Windows-Installation", "ok": True}]
        self.assertFalse(vm.blank_disk({}, hist))
        hist.append({"kind": "vm", "text": "Snapshot ‚leer‘ zurückgesetzt", "ok": None, "snapshot_blank": True})
        self.assertTrue(vm.blank_disk({}, hist))
        hist.append({"kind": "vm", "text": "VM von ISO gestartet (x.iso)", "ok": None})
        self.assertFalse(vm.blank_disk({}, hist))
        self.assertFalse(vm.blank_disk({}, [{"kind": "vm", "text": "…", "snapshot_blank": False}]))


if __name__ == "__main__":
    unittest.main()
