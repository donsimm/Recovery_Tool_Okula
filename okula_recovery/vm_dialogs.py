"""Dialoge für virtuelle Maschinen (I-001): Neue virtuelle Maschine, Hardware ändern, ISO wählen."""

from __future__ import annotations

import copy

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from okula_recovery import nas, oslib, vm  # noqa: E402

RED = "#c62828"
GREY = "#757575"


def _hint(text: str = "") -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=70)
    lbl.get_style_context().add_class("status-idle")
    return lbl


def hardware_rows(p: vm.VmProfile) -> list[tuple[str, str]]:
    fw = {"uefi-sb": "UEFI mit Secure Boot", "uefi": "UEFI ohne Secure Boot", "bios": "BIOS (Legacy, SeaBIOS)"}
    disk = ("NVMe-SSD" if p.disk.bus == "nvme" else "SATA-HDD" if p.disk.rpm else "SATA-SSD") + \
        f" {p.disk.size_gb} GB" + (f" ({p.disk.model})" if p.disk.model and p.disk.bus == "sata" else "")
    nic = {"e1000e": "Intel e1000e (Treiber in Windows)", "e1000": "Intel e1000 (Treiber in Windows)",
           "rtl8139": "Realtek rtl8139 (nur Linux)"}[p.nic.model]
    return [("Firmware", fw[p.firmware] + (" · TPM 2.0" if p.tpm else "")),
            ("Chipsatz", "Q35 (modern)" if p.chipset == "q35" else "i440FX (alt)"),
            ("Disk", disk), ("Netzwerk", nic + " · im LAN sichtbar (Brücke br0)"),
            ("Prozessor", f"{p.cpu.cores * p.cpu.threads} Kerne"), ("Arbeitsspeicher", f"{p.ram_mb // 1024} GB"),
            ("Hersteller / Modell", f"{p.smbios.manufacturer} {p.smbios.product}")]


def _fill_grid(grid: Gtk.Grid, rows: list[tuple[str, str]]) -> None:
    for child in grid.get_children():
        grid.remove(child)
    for i, (k, v) in enumerate(rows):
        key = Gtk.Label(label=k, xalign=0)
        key.get_style_context().add_class("status-idle")
        grid.attach(key, 0, i, 1, 1)
        grid.attach(Gtk.Label(label=v, xalign=0, selectable=True), 1, i, 1, 1)
    grid.show_all()


def _notes_markup(errors: list[str], notes: list[str]) -> str:
    esc = GLib.markup_escape_text
    lines = [f'<span foreground="{RED}"><b>✗</b> {esc(e)}</span>' for e in errors]
    lines += [f'<span foreground="#6d5200">⚠ {esc(n)}</span>' for n in notes]
    return "\n".join(lines)


class NewVmDialog(Gtk.Dialog):
    """Profil wählen, Name, Hardware ansehen, Platz/RAM prüfen. run() → OK, danach values()."""

    def __init__(self, parent: Gtk.Window, taken: list[str], existing: list[vm.VmProfile], free_bytes: int,
                 ram: tuple[int, int]):
        super().__init__(title="Neue virtuelle Maschine", transient_for=parent, modal=True)
        self.set_default_size(620, -1)
        self.taken, self.existing, self.free, self.ram = taken, existing, free_bytes, ram
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.ok = self.add_button("Erstellen", Gtk.ResponseType.OK)
        self.ok.get_style_context().add_class("suggested-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        box.pack_start(Gtk.Label(label="Profil (Vorlage)", xalign=0), False, False, 0)
        self.radios: dict[str, Gtk.RadioButton] = {}
        group = None
        for name, p in vm.PROFILES.items():
            rb = Gtk.RadioButton.new_from_widget(group)
            group = group or rb
            lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
            lbl.set_markup(f"<b>{GLib.markup_escape_text(name)}</b> – "
                           f"{GLib.markup_escape_text(vm.PROFILE_NOTES.get(name, ''))}\n"
                           f'<small><span foreground="{GREY}">{GLib.markup_escape_text(vm.describe(p))}'
                           "</span></small>")
            rb.add(lbl)
            rb.connect("toggled", lambda b: b.get_active() and self._profile_changed())
            self.radios[name] = rb
            box.pack_start(rb, False, False, 0)
        row = Gtk.Box(spacing=8, margin_top=6)
        row.pack_start(Gtk.Label(label="Name", xalign=0), False, False, 0)
        self.name = Gtk.Entry(width_chars=30, activates_default=True)
        self.name.set_tooltip_text("Buchstaben, Ziffern, Punkt, Unterstrich und Bindestrich – höchstens 48 Zeichen")
        self.name.connect("changed", lambda _e: self._check())
        row.pack_start(self.name, False, False, 0)
        box.pack_start(row, False, False, 0)
        frame = Gtk.Frame(label="Hardware")
        self.grid = Gtk.Grid(column_spacing=16, row_spacing=3, margin=8)
        frame.add(self.grid)
        box.pack_start(frame, False, False, 0)
        self.check = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
        box.pack_start(self.check, False, False, 0)
        box.pack_start(_hint("Die Disk-Datei liegt auf der SSD des Servers und wächst mit dem belegten Platz. "
                             "Die VM ist sofort für den Netzwerkstart freigeschaltet; der Agent startet mit "
                             "„Einschalten und Agent starten“. Windows in der VM bleibt „nicht aktiviert“."),
                       False, False, 0)
        self.get_content_area().add(box)
        self.set_default_response(Gtk.ResponseType.OK)
        self._suggested = ""
        self._profile_changed()
        self.show_all()

    def profile_name(self) -> str:
        return next(n for n, rb in self.radios.items() if rb.get_active())

    def values(self) -> tuple[str, str]:
        return self.profile_name(), self.name.get_text().strip()

    def _profile_changed(self) -> None:
        p = vm.PROFILES[self.profile_name()]
        current = self.name.get_text().strip()
        if not current or current == self._suggested:
            self._suggested = vm.unique_name(p.name, self.taken)
            self.name.set_text(self._suggested)
        _fill_grid(self.grid, hardware_rows(p))
        self._check()

    def _check(self) -> None:
        p = vm.PROFILES[self.profile_name()]
        errors, notes = vm.check_resources(p, self.free, *self.ram, planned=self.existing)
        name = self.name.get_text().strip()
        if not vm.NAME_RE.match(name):
            errors.insert(0, "Name: Buchstaben, Ziffern, . _ - (ohne Leerzeichen, höchstens 48 Zeichen)")
        elif name.lower() in {t.lower() for t in self.taken}:
            errors.insert(0, f"Eine VM „{name}“ gibt es schon")
        free = f"{self.free / 10**9:.0f} GB frei auf dem Server · RAM {self.ram[1] / 1024:.1f} von " \
               f"{self.ram[0] / 1024:.0f} GB frei"
        self.check.set_markup(_notes_markup(errors, notes) + ("\n" if errors or notes else "") +
                              f'<span foreground="{GREY}">{GLib.markup_escape_text(free)}</span>')
        self.ok.set_sensitive(not errors)


FIRMWARE_LABELS = {"uefi-sb": "UEFI mit Secure Boot", "uefi": "UEFI ohne Secure Boot", "bios": "BIOS (Legacy)"}
NIC_LABELS = {"e1000e": "Intel e1000e", "e1000": "Intel e1000", "rtl8139": "Realtek rtl8139 – nur Linux"}
BUS_LABELS = {"nvme": "NVMe", "sata": "SATA"}


class HardwareDialog(Gtk.Dialog):
    """Hardware einer ausgeschalteten VM ändern. run() → OK, danach profile() und changes()."""

    def __init__(self, parent: Gtk.Window, name: str, p: vm.VmProfile, total_mb: int, cores: int):
        super().__init__(title=f"Hardware ändern – {name}", transient_for=parent, modal=True)
        self.old = p
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.ok = self.add_button("Übernehmen", Gtk.ResponseType.OK)
        self.ok.get_style_context().add_class("suggested-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        max_gb = max(1, (total_mb - vm.RAM_RESERVE_MB) // 1024) if total_mb else 64
        self.ram = Gtk.SpinButton.new_with_range(1, max(max_gb, p.ram_mb // 1024), 1)
        self.ram.set_value(p.ram_mb // 1024)
        self.cores = Gtk.SpinButton.new_with_range(1, max(cores or 8, p.cpu.cores), 1)
        self.cores.set_value(p.cpu.cores)
        self.disk = Gtk.SpinButton.new_with_range(p.disk.size_gb, 4000, 1)
        self.disk.set_value(p.disk.size_gb)
        self.disk.set_tooltip_text("Nur vergrössern – verkleinern geht nicht. Die Partitionen in der VM bleiben "
                                   "gleich gross (danach im Betriebssystem erweitern).")
        self.nic = Gtk.ComboBoxText()
        for key, label in NIC_LABELS.items():
            self.nic.append(key, label)
        self.nic.set_active_id(p.nic.model)
        for i, (label, widget, unit) in enumerate((("Arbeitsspeicher", self.ram, "GB"),
                                                   ("Prozessor", self.cores, "Kerne"),
                                                   ("Disk", self.disk, "GB (nur vergrössern)"),
                                                   ("Netzwerkkarte", self.nic, ""))):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
            if unit:
                grid.attach(Gtk.Label(label=unit, xalign=0), 2, i, 1, 1)
        box.pack_start(grid, False, False, 0)

        risky = Gtk.Expander(label="Firmware und Disk-Anschluss (Achtung)")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6)
        warn = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
        warn.set_markup(f'<span foreground="{RED}"><b>Ein installiertes System startet danach evtl. nicht mehr</b> '
                        "(z. B. Windows nach dem Wechsel von UEFI auf BIOS oder von SATA auf NVMe).</span>")
        inner.pack_start(warn, False, False, 0)
        g2 = Gtk.Grid(column_spacing=12, row_spacing=6)
        self.firmware = Gtk.ComboBoxText()
        for key, label in FIRMWARE_LABELS.items():
            self.firmware.append(key, label)
        self.firmware.set_active_id(p.firmware)
        self.bus = Gtk.ComboBoxText()
        for key, label in BUS_LABELS.items():
            self.bus.append(key, label)
        self.bus.set_active_id(p.disk.bus)
        g2.attach(Gtk.Label(label="Firmware", xalign=0), 0, 0, 1, 1)
        g2.attach(self.firmware, 1, 0, 1, 1)
        g2.attach(Gtk.Label(label="Disk-Anschluss", xalign=0), 0, 1, 1, 1)
        g2.attach(self.bus, 1, 1, 1, 1)
        inner.pack_start(g2, False, False, 0)
        risky.add(inner)
        risky.set_expanded(False)
        box.pack_start(risky, False, False, 0)
        self.check = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
        box.pack_start(self.check, False, False, 0)
        box.pack_start(_hint("Hersteller, Modell, Seriennummer, UUID und MAC bleiben. Das Inventar im Tool zeigt die "
                             "neue Hardware nach dem nächsten Start mit Agent."), False, False, 0)
        for w in (self.ram, self.cores, self.disk):
            w.connect("value-changed", lambda _w: self._check())
        for w in (self.nic, self.firmware, self.bus):
            w.connect("changed", lambda _w: self._check())
        self.get_content_area().add(box)
        self._check()
        self.show_all()

    def profile(self) -> vm.VmProfile:
        p = copy.deepcopy(self.old)
        p.ram_mb = int(self.ram.get_value()) * 1024
        p.cpu.cores = int(self.cores.get_value())
        p.disk.size_gb = int(self.disk.get_value())
        p.nic.model = self.nic.get_active_id() or p.nic.model
        p.firmware = self.firmware.get_active_id() or p.firmware
        p.disk.bus = self.bus.get_active_id() or p.disk.bus
        return p

    def changes(self) -> list[str]:
        """Für den Verlauf: „RAM 4 → 8 GB“ …"""
        a, b = self.old, self.profile()
        out = []
        for label, old, new in (("RAM", f"{a.ram_mb // 1024} GB", f"{b.ram_mb // 1024} GB"),
                                ("Kerne", a.cpu.cores, b.cpu.cores),
                                ("Disk", f"{a.disk.size_gb} GB", f"{b.disk.size_gb} GB"),
                                ("Netzwerkkarte", a.nic.model, b.nic.model),
                                ("Firmware", FIRMWARE_LABELS[a.firmware], FIRMWARE_LABELS[b.firmware]),
                                ("Disk-Anschluss", BUS_LABELS[a.disk.bus], BUS_LABELS[b.disk.bus])):
            if old != new:
                out.append(f"{label} {old} → {new}")
        return out

    def _check(self) -> None:
        p = self.profile()
        errors, notes = [], []
        try:
            p.validate()
        except vm.VmError as e:
            errors.append(str(e))
        if p.nic.model == "rtl8139":
            notes.append("rtl8139: Windows 10/11 bringt keinen Treiber mit – die VM hätte unter Windows kein "
                         "Netzwerk (nur für Linux)")
        if p.firmware != self.old.firmware or p.disk.bus != self.old.disk.bus:
            notes.append("Firmware bzw. Disk-Anschluss geändert – installiertes System startet evtl. nicht mehr")
        self.check.set_markup(_notes_markup(errors, notes))
        self.ok.set_sensitive(not errors and bool(self.changes()))


class IsoDialog(Gtk.Dialog):
    """ISO aus der ISO-Bibliothek (NAS) wählen, von der die VM einmal startet. run() → OK, danach path()."""

    def __init__(self, parent: Gtk.Window, name: str, isos: list[oslib.IsoInfo]):
        super().__init__(title=f"Von ISO starten – {name}", transient_for=parent, modal=True)
        self.set_default_size(640, 380)
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.ok = self.add_button("Einschalten", Gtk.ResponseType.OK)
        self.ok.get_style_context().add_class("suggested-action")
        self.ok.set_sensitive(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        box.pack_start(_hint("ISO aus der ISO-Bibliothek auf dem NAS (Reiter „Images“ → Betriebssysteme). Die VM "
                             "startet einmal von der ISO; nach dem Ausschalten wieder normal. Windows-ISOs verlangen beim Start "
                             "innert weniger Sekunden einen Tastendruck – vorher „Bildschirm“ öffnen."), False, False, 0)
        self.store = Gtk.ListStore(str, str, str, str)
        view = Gtk.TreeView(model=self.store)
        for i, title in enumerate(("ISO", "Ordner", "Grösse")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            col.set_expand(i == 0)
            view.append_column(col)
        for iso in sorted(isos, key=lambda i: (i.rel.lower(), i.display.lower())):
            self.store.append([iso.display, iso.rel, nas.format_size(iso.size), str(iso.path)])
        view.get_selection().connect("changed", lambda s: self.ok.set_sensitive(s.get_selected()[1] is not None))
        view.connect("row-activated", lambda *_a: self.response(Gtk.ResponseType.OK))
        self.view = view
        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.add(view)
        box.pack_start(sw, True, True, 0)
        self.get_content_area().add(box)
        self.show_all()

    def path(self) -> str:
        model, it = self.view.get_selection().get_selected()
        return model[it][3] if it is not None else ""
