"""Gerätefenster (Doppelklick in der Geräteliste): alle Infos, Aufträge mit Log, Verlauf, Notizen, Aktionen."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from okula_recovery import archive, bootkeys, devices, jobs, nas, warranty, win11  # noqa: E402
from okula_recovery.automation_tab import AutomationTab  # noqa: E402
from okula_recovery.uikit import ask_text, confirm_error, numbered_section, run_async, scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow


def gb(n: int | float | None) -> str:
    return f"{(n or 0) / 1000**3:.1f} GB"


def table(columns: list[str], types: tuple, expand: int = 0) -> tuple[Gtk.TreeView, Gtk.ListStore]:
    store = Gtk.ListStore(*types)
    view = Gtk.TreeView(model=store)
    for i, title in enumerate(columns):
        cell = Gtk.CellRendererText()
        if i == expand:
            cell.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn(title, cell, text=i)
        col.set_resizable(True)
        col.set_expand(i == expand)
        view.append_column(col)
    return view, store



def platform_text(p: dict | None) -> str:
    """„TPM 2.0 · UEFI · Secure Boot an“ aus dem Inventar (älterer Agent: leer)."""
    if not isinstance(p, dict):
        return "unbekannt – Agent-Stick neu erstellen und Inventar neu einlesen"
    tpm = f"TPM {p['tpm']}" if p.get("tpm") else "kein TPM"
    boot = "UEFI" if p.get("uefi") else "BIOS-Modus (Legacy)"
    sb = {True: " · Secure Boot an", False: " · Secure Boot aus"}.get(p.get("secure_boot"), "")
    return f"{tpm} · {boot}{sb if p.get('uefi') else ''}"

class DeviceWindow(Gtk.Window):
    def __init__(self, main: "MainWindow", dev: devices.Device):
        super().__init__(title=f"Gerät – {dev.name}")
        self.set_transient_for(main)
        self.set_default_size(1000, 720)
        self.main = main
        self.dev = dev
        self.connect("delete-event", self._on_close)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        # Kopf: LED, Name (änderbar), Status
        head = Gtk.Box(spacing=10)
        self.led = Gtk.Image()
        head.pack_start(self.led, False, False, 0)
        self.name = Gtk.Entry(text=dev.name, width_chars=28)
        self.name.get_style_context().add_class("device-name")
        self.name.set_tooltip_text("Bezeichnung des Geräts – Enter speichert")
        self.name.connect("activate", lambda _e: self._save_name())
        self.name.connect("focus-out-event", lambda *_a: self._save_name())
        head.pack_start(self.name, False, False, 0)
        self.state = Gtk.Label(xalign=0)
        head.pack_start(self.state, True, True, 0)
        root.pack_start(head, False, False, 0)
        self.summary = Gtk.Label(xalign=0, selectable=True, wrap=True)
        root.pack_start(self.summary, False, False, 0)

        # Aktionen
        actions = Gtk.Box(spacing=6)
        self.buttons = {}
        for key, label, handler in (
                ("image", "Disk-Image erstellen …", lambda: main.start_image(self.dev)),
                ("restore", "Image zurückspielen …", lambda: main.start_restore(self.dev)),
                ("install", "OS installieren …", lambda: main.start_install(self.dev)),
                ("backup", "Backup erstellen …", lambda: main.start_backup(self.dev)),
                ("send", "Ordner senden …", lambda: main.on_send_folders(self.dev)),
                ("inventory", "Inventar neu einlesen", lambda: main.refresh_inventory(self.dev)),
                ("poweroff", "Herunterfahren", lambda: main.power(self.dev, "poweroff")),
                ("reboot", "Neu starten", lambda: main.power(self.dev, "reboot"))):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, h=handler: h())
            self.buttons[key] = b
        for key in ("image", "restore", "install", "backup", "send", "inventory"):
            actions.pack_start(self.buttons[key], False, False, 0)
        for key in ("reboot", "poweroff"):  # rechts, abgesetzt von den Aufträgen
            actions.pack_end(self.buttons[key], False, False, 0)
        root.pack_start(actions, False, False, 0)

        self.tabs = Gtk.Notebook()
        self.tabs.append_page(self._build_jobs(), Gtk.Label(label="Aufträge"))
        self.tabs.append_page(self._build_overview(), Gtk.Label(label="Übersicht"))
        self.disk_view, self.disk_store = table(
            ["Disk", "Modell", "Seriennummer", "Grösse", "Partitionen", "SMART", "Betriebsstunden", "Temperatur"],
            (str,) * 8, expand=4)
        self.tabs.append_page(scrolled(self.disk_view), Gtk.Label(label="Disks"))
        self.tabs.append_page(self._build_images(), Gtk.Label(label="Images"))
        self.tabs.append_page(self._build_backups(), Gtk.Label(label="Backups"))
        self.tabs.append_page(self._build_network(), Gtk.Label(label="Netzwerk"))
        self.automation_tab = AutomationTab(main, dev)
        self.automation_page = self.tabs.append_page(self.automation_tab, Gtk.Label(label="Automatisierung"))
        self.history_view, self.history_store = table(["Zeit", "Ereignis", "Ergebnis"], (str, str, str), expand=1)
        self.tabs.append_page(scrolled(self.history_view), Gtk.Label(label="Verlauf"))
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.notes.get_buffer().set_text(dev.notes)
        self.notes.connect("focus-out-event", lambda *_a: self._save_notes())
        self.tabs.append_page(scrolled(self.notes), Gtk.Label(label="Notizen"))
        root.pack_start(self.tabs, True, True, 0)
        self.add(root)

        self.refresh()
        self.refresh_jobs()
        self.load_images()
        self.set_focus(self.tabs)  # Name nicht gleich markiert – Bearbeiten erst per Klick
        self.show_all()

    # ---------- Aufbau ----------

    def _build_jobs(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        # id, Auftrag, Status, Fortschritt (0–100), Detail, Start
        self.job_store = Gtk.ListStore(int, str, str, int, str, str, bool)   # …, Balken grün (False = rot)
        view = Gtk.TreeView(model=self.job_store)
        for i, title in ((1, "Auftrag"), (2, "Status")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            view.append_column(col)
        # Balken ohne Text (über der Farbgrenze schlecht lesbar), Prozent fett daneben
        col = Gtk.TreeViewColumn("Fortschritt")
        prog = Gtk.CellRendererProgress(text="")
        prog.set_fixed_size(120, -1)
        col.pack_start(prog, False)
        col.add_attribute(prog, "value", 3)
        col.add_attribute(prog, "sensitive", 6)   # nicht „sensitive“ = Fehler → roter Balken (CSS :disabled)
        info = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col.pack_start(info, True)
        col.add_attribute(info, "markup", 4)
        col.set_expand(True)
        view.append_column(col)
        view.append_column(Gtk.TreeViewColumn("Start", Gtk.CellRendererText(), text=5))
        view.get_selection().connect("changed", lambda _s: self._show_log())
        self.job_view = view
        sw = scrolled(view)
        sw.set_min_content_height(120)
        sw.set_vexpand(False)
        box.pack_start(sw, False, False, 0)
        bar = Gtk.Box(spacing=6)
        bar.pack_start(Gtk.Label(label="Log des gewählten Auftrags", xalign=0), True, True, 0)
        self.btn_cancel = Gtk.Button(label="Auftrag abbrechen", sensitive=False)
        self.btn_cancel.get_style_context().add_class("destructive-action")
        self.btn_cancel.connect("clicked", self._cancel_job)
        bar.pack_end(self.btn_cancel, False, False, 0)
        box.pack_start(bar, False, False, 0)
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR)
        box.pack_start(scrolled(self.log), True, True, 0)
        self.no_jobs = Gtk.Label(label="Noch keine Aufträge in dieser Sitzung. Aufträge starten Sie oben über "
                                       "„Disk-Image erstellen“ oder „Image zurückspielen“.", xalign=0, wrap=True,
                                 no_show_all=True)  # Sichtbarkeit steuert refresh_jobs, nicht show_all
        self.no_jobs.get_style_context().add_class("status-idle")
        box.pack_start(self.no_jobs, False, False, 0)
        return box

    def _build_overview(self) -> Gtk.Widget:
        self.info_grid = Gtk.Grid(column_spacing=16, row_spacing=4, margin=12)
        return scrolled(self.info_grid)

    def _build_images(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        self.image_view, self.image_store = table(["Image", "Datum", "Grösse", "Ablage"], (str, str, str, str, str))
        self.image_view.connect("row-activated", lambda *_a: self.main.start_restore(self.dev, self._sel_image()))
        box.pack_start(scrolled(self.image_view), True, True, 0)
        hint = Gtk.Label(label="Doppelklick: dieses Image auf das Gerät zurückspielen", xalign=0)
        hint.get_style_context().add_class("status-idle")
        box.pack_start(hint, False, False, 0)
        return box

    def _build_backups(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        self.backup_view, self.backup_store = table(["Datum", "Notiz", "Inhalt", "Grösse", "Ablage"],
                                                    (str, str, str, str, str, str), expand=1)
        self.backup_view.connect("row-activated", lambda *_a: self._restore_backup())
        box.pack_start(scrolled(self.backup_view), True, True, 0)
        bar = Gtk.Box(spacing=6)
        for label, handler in (("Zurückspielen / herunterladen …", self._restore_backup),
                               ("Notiz …", self._backup_note), ("Details …", self._backup_details)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, h=handler: h())
            bar.pack_start(b, False, False, 0)
        delete = Gtk.Button(label="Löschen …")
        delete.connect("clicked", lambda _b: self._backup_delete())
        bar.pack_end(delete, False, False, 0)
        box.pack_start(bar, False, False, 0)
        return box

    def load_backups(self) -> None:
        self.backup_store.clear()
        mine = [b for b in self.main._backups.values()
                if b.manifest.get("device_id") == self.dev.id or b.device == self.dev.name]
        for b in sorted(mine, key=lambda b: b.created, reverse=True):
            self.backup_store.append([b.created.strftime("%d.%m.%Y %H:%M"), " ".join(b.note.split()), b.summary,
                                      nas.format_size(b.size), "Dateien" if b.storage == "files" else "tar.zst",
                                      str(b.path)])

    def _sel_backup(self):
        model, it = self.backup_view.get_selection().get_selected()
        return self.main._backups.get(model[it][5]) if it is not None else None

    def _restore_backup(self) -> None:
        b = self._sel_backup()
        if b is not None:
            self.main.start_file_restore(b, self.dev)

    def _backup_note(self) -> None:
        b = self._sel_backup()
        if b is not None:
            self.main.edit_backup_note(b, self)

    def _backup_delete(self) -> None:
        b = self._sel_backup()
        if b is not None:
            self.main.delete_backup(b, self)

    def _backup_details(self) -> None:
        from okula_recovery.backup_dialogs import BackupDetailsDialog
        b = self._sel_backup()
        if b is not None:
            BackupDetailsDialog(self, b)

    # ---------- Inhalte ----------

    def refresh(self) -> None:
        """Kopf, Aktionen, Übersicht, Disks und Verlauf aus dem gespeicherten Gerät neu füllen."""
        self.refresh_head()
        self.update_netboot()
        if hasattr(self, "automation_tab"):
            self.automation_tab.refresh()
        self._fill_overview()
        self._fill_disks()
        self.history_store.clear()
        for h in reversed(self.dev.history):
            ok = "" if h.get("ok") is None else ("✓ ok" if h["ok"] else "✗ Fehler")
            self.history_store.append([devices.short_time(h.get("time", "")), h.get("text", ""), ok])

    def refresh_head(self) -> None:
        """Nur LED, Status und Aktionen – günstig genug für jeden Beacon und Fortschritt."""
        dev = self.dev
        agent = self.main.online_agent(dev)
        self.set_title(f"Gerät – {dev.name}")
        self.led.set_from_icon_name("okula-led-on" if agent else "okula-led-off", Gtk.IconSize.LARGE_TOOLBAR)
        if agent:
            busy = self.main.device_status(dev)
            self.state.set_markup(f"<b>verbunden</b>  {GLib.markup_escape_text(agent.ip)}"
                                  + (f"  ·  {GLib.markup_escape_text(busy)}" if busy else ""))
        else:
            self.state.set_markup(f"<b>nicht verbunden</b>  ·  zuletzt verbunden "
                                  f"{devices.short_time(dev.last_seen) or '–'}")
        self.summary.set_text(" · ".join(p for p in (dev.os_name or "Betriebssystem unbekannt", dev.hardware) if p))
        online = agent is not None and agent.control_port > 0
        for b in self.buttons.values():
            b.set_sensitive(online)

    def _fill_overview(self) -> None:
        for child in self.info_grid.get_children():
            self.info_grid.remove(child)
        inv, dev = self.dev.inventory, self.dev
        d, cpu = inv.get("dmi") or {}, inv.get("cpu") or {}
        systems = inv.get("systems") or []
        rows = [("Betriebssystem", "\n".join(f"{s['name']}  ({s.get('disk', '')}/{s.get('partition', '')})"
                                              for s in systems) or "nicht erkannt"),
                ("Computername", ", ".join(s["hostname"] for s in systems if s.get("hostname")) or "–"),
                ("Hersteller", d.get("sys_vendor", "")), ("Modell", " ".join(
                    p for p in (d.get("product_name"), d.get("product_version")) if p)),
                ("Seriennummer", d.get("product_serial", "")), ("System-UUID", d.get("product_uuid", "")),
                ("Gehäuse", d.get("chassis", "")),
                ("Starttasten", bootkeys.short(bootkeys.lookup(d)) or "Hersteller unbekannt – meist F12, F11, F8 "
                                                                       "oder Esc"),
                ("Mainboard", " ".join(p for p in (d.get("board_vendor"), d.get("board_name")) if p)),
                ("BIOS", " ".join(p for p in (d.get("bios_vendor"), d.get("bios_version"), d.get("bios_date")) if p)),
                ("Prozessor", f"{cpu.get('model', '')}  ({cpu.get('cores', '?')} Kerne / {cpu.get('threads', '?')} "
                              "Threads)" if cpu else ""),
                ("Arbeitsspeicher", f"{inv['memory'] / 1024**3:.0f} GB" if inv.get("memory") else ""),
                ("Windows 11", win11.check(inv).text()),
                ("TPM / Start", platform_text(inv.get("platform")))]
        for b in inv.get("batteries") or []:
            rows.append((f"Akku {b.get('name', '')}", f"{b.get('manufacturer', '')} {b.get('model', '')} – Zustand "
                         f"{b['health_percent']} %" if b.get("health_percent") is not None else b.get("model", "")))
        rows += [("Netzwerk", "\n".join(f"{n['name']}: {n['mac']}" + (" (WLAN)" if n.get("wireless") else "")
                                        for n in inv.get("network") or [])),
                 ("Erstmals erfasst", devices.short_time(dev.first_seen)),
                 ("Zuletzt verbunden", devices.short_time(dev.last_seen)),
                 ("Letzte IP", dev.last_ip), ("Inventar vom", devices.short_time(inv.get("collected", ""))),
                 ("Geräte-ID", f"{dev.id}  ({dev.key})")]
        for i, (k, v) in enumerate(rows):
            key = Gtk.Label(label=k, xalign=0, yalign=0)
            key.get_style_context().add_class("status-idle")
            val = Gtk.Label(label=v or "–", xalign=0, selectable=True, wrap=True)
            self.info_grid.attach(key, 0, i, 1, 1)
            self.info_grid.attach(val, 1, i, 1, 1)
        self._key_row(len(rows))
        self._warranty_row(len(rows) + 1)
        self.info_grid.show_all()

    def _build_netboot(self) -> Gtk.Widget:
        """Netzwerkstart (PXE) für dieses Gerät ein/aus; Zahnrad öffnet die PXE-Einstellungen.
        Ausgegraut, solange der Netzwerkstart nicht eingerichtet/eingeschaltet ist oder keine Kabel-Netzwerkkarte
        bekannt ist – ohne Freigabe bekommt das Gerät vom Tool nie eine Antwort."""
        box = Gtk.Box(spacing=8)
        self.netboot_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.netboot_switch.connect("notify::active", self._on_netboot_switch)
        box.pack_start(self.netboot_switch, False, False, 0)
        self.netboot_text = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(self.netboot_text, False, False, 0)
        gear = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON)
        gear.set_relief(Gtk.ReliefStyle.NONE)
        gear.set_tooltip_text("Netzwerkstart einrichten, ein-/ausschalten (Tools → Netzwerkstart (PXE))")
        gear.connect("clicked", lambda _b: self.main.open_pxe_dialog())
        box.pack_end(gear, False, False, 0)
        self.update_netboot()
        return box

    def _build_network(self) -> Gtk.Widget:
        """Reiter „Netzwerk“: Netzwerkstart, Netzwerkkarten, Wake-on-LAN, Netzwerkstart zuerst."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        numbered_section(box, "", "Netzwerkstart", "Agent ohne Stick starten (PXE)").pack_start(
            self._build_netboot(), False, False, 0)

        # Netzwerkkarten: Name, MAC, Art, für Netzwerkstart/WoL
        self.nic_view, self.nic_store = table(["Netzwerkkarte", "MAC-Adresse", "Art", "Netzwerkstart / Wake-on-LAN"],
                                              (str, str, str, str), expand=3)
        sw = scrolled(self.nic_view)
        sw.set_vexpand(False)                 # nur so hoch wie nötig – kein Leerraum zwischen den Abschnitten
        sw.set_propagate_natural_height(True)
        sw.set_max_content_height(160)
        numbered_section(box, "", "Netzwerkkarten").pack_start(sw, False, False, 0)

        wake = numbered_section(box, "", "Aus der Ferne einschalten", "Wake-on-LAN")
        row = Gtk.Box(spacing=6)
        self.btn_wake = Gtk.Button(label="Einschalten")
        self.btn_wake.set_tooltip_text("Gerät per Wake-on-LAN einschalten – es startet wie gewohnt (z. B. Windows)")
        self.btn_wake.connect("clicked", lambda _b: self.main.wake_device(self.dev))
        self.btn_wake_agent = Gtk.Button(label="Einschalten und Agent starten")
        self.btn_wake_agent.set_tooltip_text("Agent beim nächsten Start vormerken und Gerät einschalten – es "
                                             "verbindet sich danach mit dem Tool (braucht „Netzwerkstart zuerst“)")
        self.btn_wake_agent.connect("clicked", lambda _b: self.main.wake_device(self.dev, with_agent=True))
        row.pack_start(self.btn_wake, False, False, 0)
        row.pack_start(self.btn_wake_agent, False, False, 0)
        wake.pack_start(row, False, False, 0)
        self.wake_text = self._hint("Am Gerät muss Wake-on-LAN im BIOS/UEFI aktiv sein und das Netzwerkkabel stecken. "
                                    "Das Gerät muss im selben Netz wie der Server sein.")
        wake.pack_start(self.wake_text, False, False, 0)

        first = numbered_section(box, "", "Netzwerkstart zuerst", "Startreihenfolge im Gerät")
        row = Gtk.Box(spacing=8)
        self.netfirst_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.netfirst_switch.connect("notify::active", self._on_netfirst_switch)
        row.pack_start(self.netfirst_switch, False, False, 0)
        self.netfirst_text = Gtk.Label(xalign=0, wrap=True)
        row.pack_start(self.netfirst_text, True, True, 0)
        self.btn_bootcheck = Gtk.Button(label="Prüfen")
        self.btn_bootcheck.set_tooltip_text("Startreihenfolge vom Gerät lesen (Windows-Updates können sie zurücksetzen)")
        self.btn_bootcheck.connect("clicked", lambda _b: self.main.check_bootorder(self.dev))
        row.pack_end(self.btn_bootcheck, False, False, 0)
        first.pack_start(row, False, False, 0)
        self.request_check = Gtk.CheckButton(label="Beim nächsten Start den Agent laden (danach wieder normal)")
        self.request_check.connect("toggled", self._on_request_toggled)
        first.pack_start(self.request_check, False, False, 0)
        first.pack_start(self._hint(
            "Das Gerät fragt bei jedem Start zuerst das Tool. Ohne Auftrag startet es nach etwa 2 Sekunden normal von "
            "der Festplatte; ist ein Agent angefordert, startet der Agent. Ändern nur, während das Gerät mit dem "
            "Agent verbunden ist (UEFI). Ist der Server aus, dauert der Start etwas länger (Netzwerk-Wartezeit)."),
            False, False, 0)
        self.update_netboot()
        return box

    @staticmethod
    def _hint(text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, xalign=0, wrap=True)
        lbl.get_style_context().add_class("status-idle")
        return lbl

    def _on_netfirst_switch(self, switch, _param) -> None:
        if getattr(self, "_netboot_updating", False):
            return
        on = switch.get_active()
        if on != self.dev.netfirst:
            self.main.set_netfirst(self.dev, on)

    def _on_request_toggled(self, check) -> None:
        if getattr(self, "_netboot_updating", False):
            return
        self.main.request_agent(self.dev, check.get_active())

    def update_netboot(self) -> None:
        """Alle Netzwerk-Schalter auf den aktuellen Stand bringen (auch nach Änderungen anderswo)."""
        switch = getattr(self, "netboot_switch", None)
        if switch is None:
            return
        wired = devices.netboot_macs([devices.Device(id="x", netboot=True, macs=self.dev.macs,
                                                     inventory=self.dev.inventory)])
        ready, reason = self.main.netboot_ready()
        if not wired:
            reason = "Keine Kabel-Netzwerkkarte bekannt – Gerät einmal mit dem Agent-Stick starten"
        self._netboot_updating = True
        switch.set_active(self.dev.netboot)
        self._netboot_updating = False
        switch.set_sensitive(ready and bool(wired))
        if reason:
            text = reason.split(" – ")[0]
        elif self.dev.netboot:
            keys = bootkeys.lookup(self.dev.inventory.get("dmi"))
            text = f"Ein – Gerät startet den Agent ohne Stick: {keys.boot if keys else 'Boot-Menü'} → Netzwerk"
        else:
            text = "Aus"
        self.netboot_text.set_text(text)
        tip = reason or ("Nur freigeschaltete, registrierte Geräte bekommen beim Netzwerkstart eine Antwort. "
                         f"Kabel-Netzwerkkarten: {', '.join(wired)}")
        for w in (switch, self.netboot_text):
            w.set_tooltip_text(tip)
        if getattr(self, "nic_store", None) is None:
            return
        # Netzwerkkarten
        self.nic_store.clear()
        nics = self.dev.inventory.get("network") or []
        known = {n.get("mac", "").lower() for n in nics}
        for n in nics + [{"name": "–", "mac": m} for m in self.dev.macs if m.lower() not in known]:
            mac = (n.get("mac") or "").lower()
            self.nic_store.append([n.get("name", ""), mac, "WLAN" if n.get("wireless") else "Kabel",
                                   "ja" if mac in wired else "nein (WLAN kann kein PXE/Wake-on-LAN)"
                                   if n.get("wireless") else "–"])
        # Wake-on-LAN
        connected = self.main.online_agent(self.dev) is not None
        usable = ready and bool(wired) and self.dev.netboot
        self.btn_wake.set_sensitive(bool(wired) and not connected)
        self.btn_wake_agent.set_sensitive(usable and self.dev.netfirst and not connected)
        self.btn_wake.set_tooltip_text("Gerät ist schon eingeschaltet und verbunden" if connected else
                                       "Gerät per Wake-on-LAN einschalten – es startet wie gewohnt (z. B. Windows)")
        # Netzwerkstart zuerst
        st = self.dev.boot_status or {}
        self._netboot_updating = True
        self.netfirst_switch.set_active(self.dev.netfirst)
        self.request_check.set_active(self.dev.boot_request)
        self._netboot_updating = False
        self.netfirst_switch.set_sensitive(usable and connected)
        self.request_check.set_sensitive(usable and self.dev.netfirst)
        self.btn_bootcheck.set_sensitive(connected)
        if not usable:
            text = "Erst den Netzwerkstart oben einschalten" if not reason else reason.split(" – ")[0]
        elif st.get("uefi") is False:
            text = "Gerät startet im BIOS-Modus – Startreihenfolge nur im BIOS-Setup änderbar"
        elif self.dev.netfirst:
            ok = st.get("netfirst")
            checked = devices.short_time(st.get("checked", "")) if st.get("checked") else ""
            text = ("Ein – Netzwerk steht an erster Stelle" if ok else
                    "Ein – aber Netzwerk steht NICHT mehr an erster Stelle (z. B. nach Windows-Update): aus- und "
                    "wieder einschalten") + (f" (geprüft {checked})" if checked else "")
            if self.dev.boot_request:
                text += " · Agent beim nächsten Start angefordert"
        else:
            text = "Aus" + ("" if connected else " – zum Ändern das Gerät verbinden (Agent)")
        self.netfirst_text.set_text(text)

    def _on_netboot_switch(self, switch, _param) -> None:
        if getattr(self, "_netboot_updating", False):
            return
        self.main.set_netboot(self.dev, switch.get_active(), self)

    def _key_row(self, row: int) -> None:
        """Windows-Produktschlüssel: maskiert, auf Wunsch anzeigen/kopieren, von Hand hinterlegen."""
        key, source = self.dev.windows_key
        label = Gtk.Label(label="Windows-Schlüssel", xalign=0, yalign=0.5)
        label.get_style_context().add_class("status-idle")
        self.info_grid.attach(label, 0, row, 1, 1)
        box = Gtk.Box(spacing=6)
        text = Gtk.Label(label=f"{devices.mask_key(key)}  ({source})" if key else "keiner bekannt", xalign=0,
                         selectable=True)
        text.get_style_context().add_class("monospace")
        box.pack_start(text, False, False, 0)
        if key:
            show = Gtk.ToggleButton(label="Anzeigen")
            show.connect("toggled", lambda b: text.set_text(
                f"{key if b.get_active() else devices.mask_key(key)}  ({source})"))
            box.pack_start(show, False, False, 0)
            copy = Gtk.Button(label="Kopieren")
            copy.connect("clicked", lambda _b: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(key, -1))
            box.pack_start(copy, False, False, 0)
        change = Gtk.Button(label="Ändern …" if self.dev.product_key else "Hinterlegen …")
        change.set_tooltip_text("Retail-/Volumenschlüssel von Hand hinterlegen (hat Vorrang vor dem OEM-Schlüssel "
                                "aus dem BIOS); leer lassen = löschen")
        change.connect("clicked", lambda _b: self._edit_key())
        box.pack_start(change, False, False, 0)
        self.info_grid.attach(box, 1, row, 1, 1)

    def _warranty_row(self, row: int) -> None:
        """Garantie: Datum (gelb ≤ 90 Tage, rot abgelaufen), Abfragen beim Hersteller, „Garantie bis“ von Hand."""
        w = self.dev.warranty
        label = Gtk.Label(label="Garantie bis", xalign=0, yalign=0)
        label.get_style_context().add_class("status-idle")
        self.info_grid.attach(label, 0, row, 1, 1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        level, text = warranty.status(w)
        line = Gtk.Box(spacing=8)
        state = Gtk.Label(label=text, xalign=0, selectable=True)
        if level != "unknown":
            state.get_style_context().add_class(f"warranty-{level}")
        line.pack_start(state, False, False, 0)
        details = warranty.describe(w)
        details = details[len(text):].strip(" ") if details.startswith(text) else ""
        if details:
            extra = Gtk.Label(label=details, xalign=0, selectable=True, wrap=True)
            extra.get_style_context().add_class("status-idle")
            line.pack_start(extra, False, False, 0)
        box.pack_start(line, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        inv = self.dev.inventory
        ask = Gtk.Button(label="Beim Hersteller abfragen")
        vendor = warranty.vendor_of(inv)
        if warranty.supported(inv):
            ask.set_tooltip_text(f"{warranty.NAMES[vendor]}: Garantie per Seriennummer abfragen"
                                 + (" (Schlüssel in Menü → Einstellungen)" if vendor in warranty.KEY_VENDORS else
                                    " (öffentliche Abfrage, ohne Schlüssel)"))
        else:
            ask.set_sensitive(False)
            ask.set_tooltip_text("Nur für Dell, HP und Lenovo mit gültiger Seriennummer – „Garantie bis“ von Hand "
                                 "eintragen")
        ask.connect("clicked", lambda b: self.main.query_warranty(self.dev, b))
        buttons.pack_start(ask, False, False, 0)
        hand = Gtk.Button(label="Von Hand …")
        hand.set_tooltip_text("„Garantie bis“ selbst eintragen (z. B. ohne Schlüssel oder ohne Internet)")
        hand.connect("clicked", lambda _b: self._edit_warranty())
        buttons.pack_start(hand, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.info_grid.attach(box, 1, row, 1, 1)

    def _edit_warranty(self) -> None:
        w = self.dev.warranty
        current = warranty.parse_date(w.get("until")) if w else None
        new = ask_text(self, "Garantie bis", "Garantie bis (TT.MM.JJJJ), leer = löschen:",
                       current.strftime("%d.%m.%Y") if current else "")
        if new is None:
            return
        try:
            self.dev.warranty = warranty.manual(new)
        except warranty.WarrantyError as e:
            confirm_error(self, str(e))
            return
        self.main.store.save(self.dev)
        self.main.store.add_history(self.dev, "notiz", "Garantie bis " + (
            warranty.status(self.dev.warranty)[1] + " von Hand eingetragen" if self.dev.warranty else "gelöscht"))
        self.refresh()

    def _edit_key(self) -> None:
        new = ask_text(self, "Windows-Produktschlüssel", "Schlüssel (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX), leer = löschen:",
                       self.dev.product_key)
        if new is None:
            return
        try:
            self.main.store.update(self.dev, product_key=new)
        except devices.DeviceError as e:
            confirm_error(self, str(e))
            return
        self.main.store.add_history(self.dev, "notiz", "Windows-Schlüssel " +
                                    ("hinterlegt" if self.dev.product_key else "gelöscht"))
        self.refresh()

    def _fill_disks(self) -> None:
        self.disk_store.clear()
        for disk in self.dev.inventory.get("disks") or []:
            sm = disk.get("smart") or {}
            health = {True: "OK", False: "FEHLER"}.get(sm.get("passed"), "–")
            parts = ", ".join(f"{p['name']} {p.get('fstype') or '?'} {gb(p.get('size'))}"
                              for p in disk.get("partitions", []))
            self.disk_store.append([disk.get("name", ""), disk.get("model", ""), disk.get("serial", ""),
                                    gb(disk.get("size")), parts or "leer", health,
                                    str(sm.get("power_on_hours") or "–"),
                                    f"{sm['temperature']} °C" if sm.get("temperature") else "–"])

    def load_images(self) -> None:
        self.load_backups()
        root = self.main._nas_root()
        if root is None:
            return
        dev = self.dev

        def work():
            mine = []
            for img in archive.scan(root).all_images():
                if img.kind != "Disk-Image":
                    continue
                try:
                    src = json.loads((img.path / nas.OKULA_META).read_text()).get("source") or {}
                except (OSError, ValueError):
                    continue
                if src.get("device_id") == dev.id or (src.get("agent_id") and src["agent_id"] in dev.agent_ids):
                    mine.append(img)
            return mine, root

        run_async(work, self._on_images)

    def _on_images(self, result) -> None:
        if isinstance(result, Exception):
            return
        images, root = result
        self.image_store.clear()
        for img in images:
            rel = str(img.path.parent.relative_to(root)) if img.path.is_relative_to(root) else ""
            self.image_store.append([img.name, img.mtime.strftime("%d.%m.%Y %H:%M"), nas.format_size(img.size),
                                     rel, str(img.path)])

    def _sel_image(self) -> str | None:
        model, it = self.image_view.get_selection().get_selected()
        return model[it][4] if it is not None else None

    # ---------- Aufträge ----------

    def refresh_jobs(self, changed: jobs.Job | None = None) -> None:
        all_jobs = self.main.jobs.for_device(self.dev.id)
        rows = {row[0]: row for row in self.job_store}
        for job in all_jobs:
            f = job.shown_fraction if job.running else job.fraction
            rest = " · ".join(p for p in (job.phase if job.running else "", jobs.eta_text(job.remaining),
                                          job.detail if job.running else "") if p)
            text = f"<b>{f * 100:.0f} %</b>  {GLib.markup_escape_text(rest)}"
            values = [job.id, job.title, job.state, 100 if job.state == jobs.FAILED else int(f * 100), text,
                      datetime.fromtimestamp(job.started).strftime("%H:%M:%S"), job.state != jobs.FAILED]
            if job.id in rows:
                for i, v in enumerate(values):
                    rows[job.id][i] = v
            else:
                it = self.job_store.prepend(values)
                self.job_view.get_selection().select_iter(it)  # neuester Auftrag gleich sichtbar
        self.no_jobs.set_visible(not all_jobs)
        if changed is None or self._selected_job_id() == changed.id:
            self._show_log()
        if changed is not None and not changed.running:
            self.refresh()  # Ergebnis steht jetzt im Verlauf
        else:
            self.refresh_head()

    def _selected_job_id(self) -> int | None:
        model, it = self.job_view.get_selection().get_selected()
        return model[it][0] if it is not None else None

    def _show_log(self) -> None:
        job_id = self._selected_job_id()
        job = next((j for j in self.main.jobs.for_device(self.dev.id) if j.id == job_id), None)
        self.btn_cancel.set_sensitive(bool(job and job.running))
        buf = self.log.get_buffer()
        text = "\n".join(job.log) if job else ""
        if buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) != text:
            buf.set_text(text)
            self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)

    def _cancel_job(self, _btn) -> None:
        job_id = self._selected_job_id()
        for job in self.main.jobs.for_device(self.dev.id):
            if job.id == job_id and job.running:
                job.cancel.set()
                self.main.jobs.log(job, "Abbruch angefordert …")

    def show_jobs(self) -> None:
        self.tabs.set_current_page(0)
        self.present()

    def show_automation(self) -> None:
        self.automation_tab.reload()
        self.tabs.set_current_page(self.automation_page)
        self.present()

    def refresh_automation(self, reload: bool = False) -> None:
        (self.automation_tab.reload if reload else self.automation_tab.refresh)()

    # ---------- Speichern ----------

    def _save_name(self) -> bool:
        name = self.name.get_text().strip()
        if name and name != self.dev.name:
            self.main.store.update(self.dev, name=name)
            self.main.refresh_devices()
            self.automation_tab.refresh()   # Gerätename = Computername bei Neuinstallation/Anpassen
        return False

    def _save_notes(self) -> bool:
        buf = self.notes.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if text != self.dev.notes:
            self.main.store.update(self.dev, notes=text)
        return False

    def _on_close(self, *_a) -> bool:
        self._save_name()
        self._save_notes()
        self.main.device_windows.pop(self.dev.id, None)
        return False
