"""Gerätefenster (Doppelklick in der Geräteliste): alle Infos, Aufträge mit Log, Verlauf, Notizen, Aktionen."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import archive, devices, jobs, nas  # noqa: E402
from okula_recovery.uikit import run_async, scrolled  # noqa: E402

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
                ("inventory", "Inventar neu einlesen", lambda: main.refresh_inventory(self.dev)),
                ("poweroff", "Herunterfahren", lambda: main.power(self.dev, "poweroff")),
                ("reboot", "Neu starten", lambda: main.power(self.dev, "reboot"))):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, h=handler: h())
            actions.pack_start(b, False, False, 0)
            self.buttons[key] = b
        root.pack_start(actions, False, False, 0)

        self.tabs = Gtk.Notebook()
        self.tabs.append_page(self._build_jobs(), Gtk.Label(label="Aufträge"))
        self.tabs.append_page(self._build_overview(), Gtk.Label(label="Übersicht"))
        self.disk_view, self.disk_store = table(
            ["Disk", "Modell", "Seriennummer", "Grösse", "Partitionen", "SMART", "Betriebsstunden", "Temperatur"],
            (str,) * 8, expand=4)
        self.tabs.append_page(scrolled(self.disk_view), Gtk.Label(label="Disks"))
        self.tabs.append_page(self._build_images(), Gtk.Label(label="Images"))
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
        self.show_all()
        self.set_focus(None)  # Name nicht gleich markiert – Bearbeiten erst per Klick

    # ---------- Aufbau ----------

    def _build_jobs(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        # id, Auftrag, Status, Fortschritt (0–100), Detail, Start
        self.job_store = Gtk.ListStore(int, str, str, int, str, str)
        view = Gtk.TreeView(model=self.job_store)
        for i, title in ((1, "Auftrag"), (2, "Status")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            view.append_column(col)
        prog = Gtk.CellRendererProgress()
        col = Gtk.TreeViewColumn("Fortschritt", prog, value=3, text=4)
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
                                       "„Disk-Image erstellen“ oder „Image zurückspielen“.", xalign=0, wrap=True)
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
        self.info_grid.show_all()

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
            pct = f"{job.fraction * 100:.0f} %"
            values = [job.id, job.title, job.state, int(job.fraction * 100), f"{pct} · {job.detail}" if job.detail else pct,
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
