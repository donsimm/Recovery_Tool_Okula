"""Ä-045: Zwei Neustart-Knöpfe – „Neustart in Windows“ und „Neustart in den Agent“.

Startziel am Agent (BootNext), Texte und Regeln (neustart.py) ohne GTK; der Ablauf in der Oberfläche (ui.py) mit
nachgebildetem Fenster, Agent und virsh (braucht nur PyGObject, keinen Bildschirm).
"""

import types
import unittest
from unittest import mock

from okula_recovery import devices, neustart, wininstall

# efibootmgr -v eines UEFI-Geräts: Windows-Boot-Manager, Agent-Stick (läuft gerade), Netzwerkstart
EFI_STICK = """BootCurrent: 0005
Timeout: 0 seconds
BootOrder: 0003,0001,0005
Boot0001* Windows Boot Manager\tHD(1,GPT,1c2a…,0x800,0x32000)/File(\\EFI\\Microsoft\\Boot\\bootmgfw.efi)
Boot0003* UEFI: PXE IPv4 Intel(R) Ethernet Connection\tPciRoot(0x0)/Pci(0x1f,0x6)/MAC(001122334455,0)/IPv4(0.0.0.0)
Boot0005* UEFI: SanDisk Cruzer 1.00\tPciRoot(0x0)/Pci(0x14,0x0)/USB(1,0)/HD(1,MBR,0x1234,0x800,0x1000)
"""


def info(text: str = EFI_STICK) -> dict:
    return wininstall.parse_boot(text)


class BootNextChoiceTest(unittest.TestCase):
    def test_windows_is_windows_boot_manager(self):
        self.assertEqual(wininstall.boot_next_choice(info(), "windows"),
                         {"set": "0001", "label": "Windows Boot Manager", "via": "disk"})

    def test_windows_found_by_path_with_other_label(self):
        text = EFI_STICK.replace("Windows Boot Manager", "Disk 0 (OEM)") \
            .replace("\\EFI\\Microsoft\\Boot\\bootmgfw.efi", "\\EFI\\MICROSOFT\\BOOT\\BOOTMGFW.EFI")
        self.assertEqual(wininstall.boot_next_choice(info(text), "windows")["set"], "0001")

    def test_windows_prefers_active_then_boot_order(self):
        text = EFI_STICK + "Boot0007  Windows Boot Manager\tHD(1,GPT,ffff…)/File(\\EFI\\Microsoft\\Boot\\bootmgfw.efi)\n" \
                           "Boot0008* Windows Boot Manager\tHD(1,GPT,eeee…)/File(\\EFI\\Microsoft\\Boot\\bootmgfw.efi)\n"
        text = text.replace("BootOrder: 0003,0001,0005", "BootOrder: 0007,0008,0003,0001,0005")
        self.assertEqual(wininstall.boot_next_choice(info(text), "windows")["set"], "0008")   # 0007 inaktiv

    def test_windows_missing_gives_reason(self):
        text = "\n".join(line for line in EFI_STICK.splitlines() if not line.startswith("Boot0001"))
        choice = wininstall.boot_next_choice(info(text), "windows")
        self.assertEqual(choice["set"], "")
        self.assertIn("Windows Boot Manager", choice["message"])

    def test_agent_is_the_stick_it_runs_from(self):
        self.assertEqual(wininstall.boot_next_choice(info(), "agent"),
                         {"set": "0005", "label": "UEFI: SanDisk Cruzer 1.00", "via": "stick"})

    def test_agent_from_network(self):
        text = EFI_STICK.replace("BootCurrent: 0005", "BootCurrent: 0003")
        self.assertEqual(wininstall.boot_next_choice(info(text), "agent")["via"], "network")

    def test_agent_transient_stick_entry_falls_back_to_network(self):
        text = EFI_STICK.replace("BootCurrent: 0005", "BootCurrent: 0009")     # Eintrag gibt es nicht mehr
        self.assertEqual(wininstall.boot_next_choice(info(text), "agent")["set"], "0003")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("Boot0003"))
        choice = wininstall.boot_next_choice(info(text), "agent")
        self.assertEqual(choice["set"], "")
        self.assertIn("Startquelle", choice["message"])

    def test_unknown_target(self):
        with self.assertRaises(wininstall.ImagingError):
            wininstall.boot_next_choice(info(), "bios")


class SetBootNextTest(unittest.TestCase):
    def test_sets_bootnext_once(self):
        calls = []

        def fake(*args):
            calls.append(args)
            return EFI_STICK if args == ("-v",) else ""
        with mock.patch.object(wininstall, "efibootmgr", fake), \
                mock.patch.object(wininstall.Path, "is_dir", return_value=True):
            result = wininstall.set_boot_next("windows")
        self.assertEqual(result["set"], "0001")
        self.assertTrue(result["uefi"])
        self.assertEqual(calls, [("-v",), ("--bootnext", "0001")])     # BootOrder bleibt unverändert

    def test_nothing_set_without_entry(self):
        calls = []
        text = "\n".join(line for line in EFI_STICK.splitlines() if not line.startswith("Boot0001"))
        with mock.patch.object(wininstall, "efibootmgr", lambda *a: calls.append(a) or text), \
                mock.patch.object(wininstall.Path, "is_dir", return_value=True):
            self.assertEqual(wininstall.set_boot_next("windows")["set"], "")
        self.assertEqual(calls, [("-v",)])

    def test_bios_mode_not_controllable(self):
        with mock.patch.object(wininstall, "efibootmgr", side_effect=AssertionError("kein efibootmgr")), \
                mock.patch.object(wininstall.Path, "is_dir", return_value=False):
            result = wininstall.set_boot_next("agent")
        self.assertEqual((result["set"], result["uefi"]), ("", False))
        self.assertIn("BIOS-Modus", result["message"])


class TextsTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(neustart.LABELS, {"windows": "Neustart in Windows", "agent": "Neustart in den Agent"})
        self.assertEqual((neustart.AFTER_SEND_TITLE, neustart.LATER), ("Jetzt in Windows neu starten?", "Später"))
        self.assertEqual(neustart.AFTER_SEND_KINDS, ("tweak", "software"))

    def test_vm_order_per_button(self):
        self.assertFalse(neustart.vm_network_first("windows"))
        self.assertTrue(neustart.vm_network_first("agent"))
        with self.assertRaises(ValueError):
            neustart.vm_network_first("reboot")

    def test_why_not(self):
        self.assertIn("Gerät wählen", neustart.why_not("windows", selected=False))
        self.assertIn("nicht mit dem Agent verbunden", neustart.why_not("windows"))
        self.assertEqual(neustart.why_not("agent", online=True), "")
        # VM: ohne Agent über libvirt, aber nur, wenn sie läuft
        self.assertEqual(neustart.why_not("windows", is_vm=True), "")
        self.assertEqual(neustart.why_not("windows", is_vm=True, vm_stop_why="VM ist ausgeschaltet"),
                         "VM ist ausgeschaltet")
        self.assertEqual(neustart.why_not("windows", is_vm=True, online=True, vm_stop_why="x"), "")
        # VM in den Agent: nur mit Netzwerkstart
        self.assertIn("Netzwerkstart ist aus",
                      neustart.why_not("agent", is_vm=True, netboot_why="Netzwerkstart ist aus"))
        self.assertEqual(neustart.why_not("windows", is_vm=True, netboot_why="Netzwerkstart ist aus"), "")

    def test_confirm_text(self):
        title, body, ok = neustart.confirm_text("windows", "PC-1", "HP EliteBook (10.0.0.5)")
        self.assertEqual((title, ok), ("„PC-1“ in Windows neu starten?", "Neustart in Windows"))
        self.assertTrue(body.startswith("HP EliteBook (10.0.0.5)\n\n"))
        self.assertIn("Disk zuerst", neustart.confirm_text("windows", "VM", is_vm=True)[1])
        title, body, ok = neustart.confirm_text("agent", "VM", is_vm=True)
        self.assertEqual(ok, "Neustart in den Agent")
        self.assertIn("Netzwerk zuerst", body)

    def test_fallback_is_honest(self):
        text = neustart.fallback_text("windows", "Gerät startet im BIOS-Modus.")
        self.assertIn("nicht festlegen: Gerät startet im BIOS-Modus.", text)
        self.assertIn("Stick abziehen", text)
        self.assertNotIn("2 Sekunden", text)
        self.assertIn("2 Sekunden", neustart.fallback_text("windows", "x", netboot_first=True))
        text = neustart.fallback_text("agent", "Agent zu alt")
        self.assertIn("stecken lassen", text)
        self.assertIn("F12", text)

    def test_done_text(self):
        self.assertEqual(neustart.done_text("windows", {"set": "0001", "label": "Windows Boot Manager"}),
                         "Neustart in Windows (vom Tool, einmalig über Windows Boot Manager)")
        self.assertIn("VM: Netzwerk zuerst", neustart.done_text("agent", {"vm": True}))
        self.assertIn("nicht festgelegt", neustart.done_text("agent", {"set": ""}))


# ---------- Ablauf in der Oberfläche (nachgebildet) ----------

def load_ui():
    try:
        from okula_recovery import ui
    except Exception:          # kein PyGObject/GTK installiert
        return None
    return ui


ui = load_ui()


class FakeStore:
    def __init__(self):
        self.history, self.saved = [], 0

    def update(self, dev, **fields):
        for k, v in fields.items():
            setattr(dev, k, v)

    def save(self, _dev):
        self.saved += 1

    def add_history(self, _dev, kind, text, ok=True):
        self.history.append((kind, text))


class FakeVirsh:
    def __init__(self, log):
        self.log = log

    def set_boot_runtime(self, name, network_first):
        self.log.append(("order", name, "network" if network_first else "disk"))
        return True

    def reboot(self, name):
        self.log.append(("acpi-reboot", name))


def make_window(agent=None, running_jobs="", netboot_ready=(True, "")):
    log = []
    fake = types.SimpleNamespace()
    for name in ("reboot_why", "reboot_to", "_reboot_go", "_reboot_done", "ask_reboot_after_send"):
        setattr(fake, name, getattr(ui.MainWindow, name).__get__(fake))
    fake.log = log
    fake.key = b"k" * 32
    fake.store = FakeStore()
    fake.jobs = types.SimpleNamespace(summary=lambda _id: running_jobs)
    fake.online_agent = lambda _dev: agent
    fake.vm_why = lambda _dev, _what: ""
    fake.netboot_ready = lambda: netboot_ready
    fake._parent_for = lambda _dev: None
    fake.sync_netboot = lambda after=None: (log.append(("sync",)), after and after())
    fake.netboot_changed = lambda: None
    fake.status = lambda text: log.append(("status", text))
    fake.device_windows = {}
    fake.virsh = FakeVirsh(log)
    return fake


def sync_run(work, done):
    try:
        result = work()
    except Exception as e:      # wie uikit.run_async
        result = e
    done(result)


@unittest.skipIf(ui is None, "braucht PyGObject (GTK 3)")
class UiFlowTest(unittest.TestCase):
    def setUp(self):
        self.confirms = []
        self.answer = True
        self.errors = []
        self.calls = []
        patches = [mock.patch.object(ui, "run_async", sync_run),
                   mock.patch.object(ui, "confirm", self._confirm),
                   mock.patch.object(ui, "confirm_error", lambda _p, text: self.errors.append(text)),
                   mock.patch.object(ui.agentclient, "power", self._power),
                   mock.patch.object(ui.agentclient, "bootnext", self._bootnext)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.bootnext_reply = {"set": "0001", "label": "Windows Boot Manager", "uefi": True}

    def _confirm(self, _parent, title, text, ok_label="", red=False, cancel_label="Abbrechen"):
        self.confirms.append((title, text, ok_label, cancel_label))
        return self.answer

    def _power(self, ip, key, action, port=0, delay=5):
        self.calls.append(("power", action))

    def _bootnext(self, ip, key, target, port=0):
        self.calls.append(("bootnext", target))
        if isinstance(self.bootnext_reply, Exception):
            raise self.bootnext_reply
        return self.bootnext_reply

    @staticmethod
    def agent():
        return types.SimpleNamespace(ip="10.0.0.5", control_port=8471, busy=False, hardware="HP EliteBook")

    def vm(self, **kw):
        return devices.Device(id="v1", name="VM-Win11-clean", vm={"name": "VM-Win11-clean"}, **kw)

    # --- VM: Startreihenfolge eindeutig je Knopf ---

    def test_vm_windows_sets_disk_first_and_cancels_agent(self):
        dev = self.vm(netboot=True, boot_request=True)          # Agent war angefordert – zählt nicht mehr
        win = make_window()
        win.reboot_to(dev, "windows")
        self.assertFalse(dev.boot_request)
        self.assertEqual(win.log[:3], [("sync",), ("order", "VM-Win11-clean", "disk"),
                                       ("acpi-reboot", "VM-Win11-clean")])
        self.assertEqual(self.confirms[0][2], "Neustart in Windows")
        self.assertIn("Neustart in Windows", win.store.history[-1][1])

    def test_vm_agent_sets_network_first_and_requests_agent(self):
        dev = self.vm()
        win = make_window(agent=self.agent())              # Agent verbunden: Neustart über den Agent
        win.reboot_to(dev, "agent")
        self.assertTrue(dev.netboot and dev.boot_request)
        self.assertIn(("order", "VM-Win11-clean", "network"), win.log)
        self.assertEqual(self.calls, [("power", "reboot")])           # kein BootNext bei VMs
        self.assertNotIn(("acpi-reboot", "VM-Win11-clean"), win.log)

    def test_vm_agent_greyed_without_netboot(self):
        win = make_window(netboot_ready=(False, "Netzwerkstart ist aus – Tools → Netzwerkstart (PXE) …"))
        why = win.reboot_why(self.vm(), "agent")
        self.assertIn("Netzwerkstart ist aus", why)
        self.assertNotIn("Tools →", why)
        self.assertEqual(win.reboot_why(self.vm(), "windows"), "")
        win.reboot_to(self.vm(), "agent")
        self.assertEqual(self.errors, [why])
        self.assertEqual(win.log, [])

    def test_cancel_changes_nothing(self):
        self.answer = False
        dev = self.vm(boot_request=True)
        win = make_window()
        win.reboot_to(dev, "windows")
        self.assertTrue(dev.boot_request)
        self.assertEqual(win.log, [])

    # --- echtes Gerät (nachgebildet) ---

    def test_real_device_windows_via_bootnext(self):
        dev = devices.Device(id="d1", name="PC-1")
        win = make_window(agent=self.agent())
        win.reboot_to(dev, "windows")
        self.assertEqual(self.calls, [("bootnext", "windows"), ("power", "reboot")])
        self.assertEqual(len(self.confirms), 1)                        # nur die Rückfrage vorher
        self.assertIn("einmalig über Windows Boot Manager", win.store.history[-1][1])

    def test_real_device_agent_with_netboot_requests_agent(self):
        dev = devices.Device(id="d1", name="PC-1", netboot=True, netfirst=True)
        self.bootnext_reply = {"set": "0003", "label": "UEFI: PXE IPv4", "via": "network"}
        win = make_window(agent=self.agent())
        win.reboot_to(dev, "agent")
        self.assertTrue(dev.boot_request)
        self.assertEqual(self.calls, [("bootnext", "agent"), ("power", "reboot")])

    def test_real_device_not_controllable_asks_with_hint(self):
        dev = devices.Device(id="d1", name="PC-1")
        self.bootnext_reply = {"set": "", "uefi": False, "message": "Gerät startet im BIOS-Modus"}
        win = make_window(agent=self.agent())
        win.reboot_to(dev, "windows")
        self.assertEqual(len(self.confirms), 2)
        title, text, ok, _cancel = self.confirms[1]
        self.assertEqual((title, ok), ("Startziel nicht festgelegt", "Trotzdem neu starten"))
        self.assertIn("Stick abziehen", text)
        self.assertEqual(self.calls[-1], ("power", "reboot"))
        self.assertIn("nicht festgelegt", win.store.history[-1][1])

    def test_old_agent_hint_and_cancel(self):
        dev = devices.Device(id="d1", name="PC-1")
        self.bootnext_reply = ui.agentclient.AgentError("Agent zu alt – Agent-Stick neu erstellen")
        win = make_window(agent=self.agent())
        answers = iter([True, False])
        self.answer = None
        with mock.patch.object(ui, "confirm", lambda *a, **k: (self.confirms.append(a), next(answers))[1]):
            win.reboot_to(dev, "agent")
        self.assertIn("Agent zu alt", self.confirms[1][2])
        self.assertEqual(self.calls, [("bootnext", "agent")])         # abgebrochen: kein Neustart

    def test_real_device_offline_or_busy(self):
        win = make_window()
        why = win.reboot_why(devices.Device(id="d1", name="PC-1"), "windows")
        self.assertIn("nicht mit dem Agent verbunden", why)
        win = make_window(agent=self.agent(), running_jobs="Windows anpassen")
        win.reboot_to(devices.Device(id="d1", name="PC-1"), "windows")
        self.assertIn("läuft ein Auftrag", self.errors[-1])
        self.assertEqual(self.calls, [])

    # --- Dialog nach dem Senden ---

    def test_after_send_asks_directly(self):
        dev = devices.Device(id="d1", name="PC-1")
        win = make_window(agent=self.agent())
        job = types.SimpleNamespace(running=False)
        win.ask_reboot_after_send(dev, job)
        title, _text, ok, cancel = self.confirms[0]
        self.assertEqual((title, ok, cancel), ("Jetzt in Windows neu starten?", "Neustart in Windows", "Später"))
        self.assertEqual(len(self.confirms), 1)                        # keine zweite Rückfrage
        self.assertEqual(self.calls, [("bootnext", "windows"), ("power", "reboot")])

    def test_after_send_later(self):
        self.answer = False
        win = make_window(agent=self.agent())
        win.ask_reboot_after_send(devices.Device(id="d1", name="PC-1"), types.SimpleNamespace(running=False))
        self.assertEqual(self.calls, [])

    def test_after_send_waits_for_job_end(self):
        win = make_window(agent=self.agent())
        job = types.SimpleNamespace(running=True)
        with mock.patch.object(ui.GLib, "timeout_add") as later:
            win.ask_reboot_after_send(devices.Device(id="d1", name="PC-1"), job)
        later.assert_called_once()
        self.assertEqual(self.confirms, [])

    def test_after_send_not_when_offline(self):
        win = make_window()
        win.ask_reboot_after_send(devices.Device(id="d1", name="PC-1"), types.SimpleNamespace(running=False))
        self.assertEqual(self.confirms, [])


class SourcesTest(unittest.TestCase):
    """Überall die zwei Knöpfe, nirgends mehr ein „Neu starten“ ohne Ziel."""

    def test_no_plain_restart_in_ui(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "okula_recovery"
        for name in ("ui.py", "device_window.py", "uikit.py"):
            src = (root / name).read_text(encoding="utf-8")
            self.assertNotIn('"Neu starten"', src, name)
            self.assertNotIn('power(dev, "reboot")', src, name)
        uikit = (root / "uikit.py").read_text(encoding="utf-8")
        self.assertIn('"reboot-windows"', uikit)
        self.assertIn('"reboot-agent"', uikit)
        self.assertIn("Neustart in Windows", (root / "help_window.py").read_text(encoding="utf-8"))
        self.assertIn("Neustart in den Agent", (root / "help_window.py").read_text(encoding="utf-8"))
        self.assertIn('cmd == "bootnext"', (root / "agent.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
