"""Dialog „Disk-Image erstellen“: Disk und Name wählen – der Auftrag läuft danach im Hintergrund."""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import agentclient, discovery, imaging, nas  # noqa: E402


def method_label(part: dict) -> str:
    fs = part.get("fstype") or ""
    if fs == "swap":
        return "übersprungen (Swap)"
    if fs in imaging.PARTCLONE:
        return "partclone (nur belegte Blöcke)"
    return "Rohkopie (alle Blöcke)"


def default_name(info: discovery.AgentInfo) -> str:
    base = info.product or info.hostname or info.ip
    tail = info.mac.replace(":", "")[-6:]
    return agentclient.safe_name(f"{base}_{tail}" if tail else base)


class ImageDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, agent: discovery.AgentInfo, nas_root: str,
                 start_job: Callable[[dict, str, bool], None], name: str = ""):
        """start_job(disk, archivname, danach_herunterfahren) startet den Hintergrund-Auftrag."""
        super().__init__(title="Disk-Image erstellen", transient_for=parent, modal=True)
        self.set_default_size(760, 520)
        self.agent = agent
        self.nas_root = nas_root
        self.start_job = start_job
        self.key = agentclient.load_or_create_key()
        self.disks: dict[str, dict] = {}

        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn_start = self.add_button("Image erstellen", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("suggested-action")
        self.btn_start.set_sensitive(False)
        self.connect("response", self.on_response)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        row = 0
        title = Gtk.Label(xalign=0, wrap=True)
        title.set_markup(f"<b>{GLib.markup_escape_text(name or agent.hostname or agent.ip)}</b>  ({agent.ip})  "
                         f"{GLib.markup_escape_text(agent.hardware)}")
        grid.attach(title, 0, row, 2, 1)

        row += 1
        grid.attach(Gtk.Label(label="Name im Archiv", xalign=0), 0, row, 1, 1)
        self.name = Gtk.Entry(text=agentclient.safe_name(name) if name else default_name(agent), hexpand=True,
                              placeholder_text="z. B. PC-Buchhaltung")
        self.name.set_tooltip_text("Ordnername auf dem NAS (Gerät oder Inventarnummer)")
        self.name.connect("changed", lambda _e: self._update_target())
        grid.attach(self.name, 1, row, 1, 1)

        row += 1
        grid.attach(Gtk.Label(label="Disk", xalign=0), 0, row, 1, 1)
        self.disk_combo = Gtk.ComboBoxText(hexpand=True)
        self.disk_combo.connect("changed", lambda _c: self._on_disk_changed())
        grid.attach(self.disk_combo, 1, row, 1, 1)

        row += 1
        # Partition, Dateisystem, Grösse, Label, Methode
        self.part_store = Gtk.ListStore(str, str, str, str, str)
        view = Gtk.TreeView(model=self.part_store)
        for i, title_ in enumerate(("Partition", "Dateisystem", "Grösse", "Label", "Sicherung")):
            cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END if i == 3 else Pango.EllipsizeMode.NONE)
            col = Gtk.TreeViewColumn(title_, cell, text=i)
            col.set_expand(i == 3)
            view.append_column(col)
        view.get_selection().set_mode(Gtk.SelectionMode.NONE)
        sw = Gtk.ScrolledWindow(hexpand=True)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_min_content_height(130)
        sw.add(view)
        grid.attach(sw, 0, row, 2, 1)

        row += 1
        grid.attach(Gtk.Label(label="Ziel", xalign=0), 0, row, 1, 1)
        self.target = Gtk.Label(xalign=0, selectable=True, ellipsize=Pango.EllipsizeMode.MIDDLE)
        grid.attach(self.target, 1, row, 1, 1)

        row += 1
        self.shutdown = Gtk.CheckButton(label="Maschine danach herunterfahren (nur wenn das Image fertig ist)")
        grid.attach(self.shutdown, 0, row, 2, 1)

        row += 1
        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_text("Lese Disks vom Agent …")
        self.progress.set_tooltip_text("Der Auftrag läuft nach dem Start im Hintergrund – Fortschritt und Log "
                                       "im Gerätefenster")
        grid.attach(self.progress, 0, row, 2, 1)

        row += 1
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.log)
        grid.attach(sw, 0, row, 2, 1)

        self.get_content_area().add(grid)
        self._update_target()
        self.show_all()
        self._load_info()

    # ---------- Infos vom Agent ----------

    def append_log(self, text: str) -> bool:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), time.strftime("%H:%M:%S ") + text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        return False

    def _load_info(self) -> None:
        agent, key = self.agent, self.key

        def work():
            try:
                result = agentclient.get_info(agent.ip, key, agent.control_port)
            except Exception as e:  # Netzwerk, Schlüssel, Protokoll
                result = e
            GLib.idle_add(self._on_info, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_info(self, result) -> bool:
        if isinstance(result, Exception):
            self.progress.set_text("Agent nicht erreichbar")
            self.append_log(f"Fehler: {result}")
            return False
        if not result.get("tools", {}).get("partclone"):
            self.append_log("Auf diesem Agent-Stick fehlt partclone – Stick mit aktuellem Tool neu erstellen.")
        self.disks = {d["path"]: d for d in result.get("disks", [])}
        for path, d in self.disks.items():
            label = f"{d['name']} – {d['model'] or 'Disk'} ({d['size'] / 1000**3:.1f} GB, {d['pttype'] or 'ohne Tabelle'})"
            self.disk_combo.append(path, label)
        if self.disks:
            self.disk_combo.set_active(0)
            self.progress.set_text("Bereit")
        else:
            self.progress.set_text("Keine Disk gefunden")
            self.append_log("Der Agent meldet keine interne Disk.")
        return False

    def _on_disk_changed(self) -> None:
        self.part_store.clear()
        disk = self.disks.get(self.disk_combo.get_active_id() or "")
        if disk:
            for p in disk["partitions"]:
                self.part_store.append([p["name"], p["fstype"] or "unbekannt", nas.format_size(p["size"]),
                                        p["label"], method_label(p)])
        self._update_target()

    def _update_target(self) -> None:
        disk = self.disk_combo.get_active_id() or "<disk>"
        path = agentclient.image_dir(self.nas_root, self.name.get_text().strip() or "maschine", disk)
        self.target.set_text(f"{path.parent}/{path.name[:16]}…")
        self.btn_start.set_sensitive(bool(self.disks) and bool(self.name.get_text().strip()))

    # ---------- Image erstellen ----------

    def on_response(self, _dlg, response: int) -> None:
        if response != Gtk.ResponseType.APPLY:
            self.destroy()
            return
        if not os.path.ismount(self.nas_root):
            self.append_log(f"NAS ist nicht eingehängt ({self.nas_root}) – Menü → NAS-Verbindung …")
            return
        disk = self.disks[self.disk_combo.get_active_id()]
        try:
            self.start_job(disk, self.name.get_text().strip(), self.shutdown.get_active())
        except Exception as e:
            self.append_log(f"Nicht gestartet: {e}")
            return
        self.destroy()
