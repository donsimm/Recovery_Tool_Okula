"""Gerätefenster (Doppelklick in der Geräteliste): alle Infos, Aufträge mit Log, Verlauf, Notizen, Aktionen."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from okula_recovery import archive, devices, jobs, nas  # noqa: E402
from okula_recovery.uikit import ask_text, confirm_error, run_async, scrolled  # noqa: E402

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
                ("inventory", "Inventar neu einlesen", lambda: main.refresh_inventory(self.dev)),
                ("poweroff", "Herunterfahren", lambda: main.power(self.dev, "poweroff")),
                ("reboot", "Neu starten", lambda: main.power(self.dev, "reboot"))):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, h=handler: h())
            self.buttons[key] = b
        for key in ("image", "restore", "install", "backup", "inventory"):
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
        box.pack_start(self._build_netboot(), False, False, 0)
        # id, Auftrag, Status, Fortschritt (0–100), Detail, Start
        self.job_store = Gtk.ListStore(int, str, str, int, str, str)
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
                ("Mainboard", " ".join(p for p in (d.get("board_vendor"), d.get("board_name")) if p)),
                ("BIOS", " ".join(p for p in (d.get("bios_vendor"), d.get("bios_version"), d.get("bios_date")) if p)),
                ("Prozessor", f"{cpu.get('model', '')}  ({cpu.get('cores', '?')} Kerne / {cpu.get('threads', '?')} "
                              "Threads)" if cpu else ""),
                ("Arbeitsspeicher", f"{inv['memory'] / 1024**3:.0f} GB" if inv.get("memory") else "")]
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
        self.info_grid.show_all()

    def _build_netboot(self) -> Gtk.Widget:
        """Netzwerkstart (PXE) für dieses Gerät ein/aus; Zahnrad öffnet die PXE-Einstellungen.
        Ausgegraut, solange der Netzwerkstart nicht eingerichtet/eingeschaltet ist oder keine Kabel-Netzwerkkarte
        bekannt ist – ohne Freigabe bekommt das Gerät vom Tool nie eine Antwort."""
        box = Gtk.Box(spacing=8)
        box.get_style_context().add_class("nas-bar")   # gleiche dezente Leiste wie der NAS-Status
        label = Gtk.Label(label="Netzwerkstart", xalign=0)
        label.get_style_context().add_class("pane-title")
        box.pack_start(label, False, False, 0)
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

    def update_netboot(self) -> None:
        """Schalter auf den aktuellen Stand bringen (auch wenn der Netzwerkstart anderswo geändert wurde)."""
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
            text = "Ein – Gerät startet den Agent ohne Stick: F12 (Boot-Menü) → Netzwerk"
        else:
            text = "Aus"
        self.netboot_text.set_text(text)
        tip = reason or ("Nur freigeschaltete, registrierte Geräte bekommen beim Netzwerkstart eine Antwort. "
                         f"Kabel-Netzwerkkarten: {', '.join(wired)}")
        for w in (switch, self.netboot_text):
            w.set_tooltip_text(tip)

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
            values = [job.id, job.title, job.state, int(f * 100), text,
                      datetime.fromtimestamp(job.started).strftime("%H:%M:%S")]
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

    # ---------- Speichern ----------

    def _save_name(self) -> bool:
        name = self.name.get_text().strip()
        if name and name != self.dev.name:
            self.main.store.update(self.dev, name=name)
            self.main.refresh_devices()
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
