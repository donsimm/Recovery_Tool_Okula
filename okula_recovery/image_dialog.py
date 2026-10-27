"""Dialog „Disk-Image erstellen“: Disk der Zielmaschine wählen, Image aufs NAS schreiben."""

from __future__ import annotations

import os
import threading
import time

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
    def __init__(self, parent: Gtk.Window, agent: discovery.AgentInfo, nas_root: str, on_done=None):
        super().__init__(title="Disk-Image erstellen", transient_for=parent, modal=True)
        self.set_default_size(760, 560)
        self.agent = agent
        self.nas_root = nas_root
        self.on_done = on_done
        self.key = agentclient.load_or_create_key()
        self.disks: dict[str, dict] = {}
        self.cancel = threading.Event()
        self.busy = False

        self.btn_close = self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.btn_start = self.add_button("Image erstellen", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("suggested-action")
        self.btn_start.set_sensitive(False)
        self.connect("response", self.on_response)
        self.connect("delete-event", lambda *_a: self.busy)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        row = 0
        title = Gtk.Label(xalign=0, wrap=True)
        title.set_markup(f"<b>{GLib.markup_escape_text(agent.hostname or agent.ip)}</b>  ({agent.ip})  "
                         f"{GLib.markup_escape_text(agent.hardware)}")
        grid.attach(title, 0, row, 2, 1)

        row += 1
        grid.attach(Gtk.Label(label="Name im Archiv", xalign=0), 0, row, 1, 1)
        self.name = Gtk.Entry(text=default_name(agent), hexpand=True,
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
        if not self.busy:
            self.btn_start.set_sensitive(bool(self.disks) and bool(self.name.get_text().strip()))

    # ---------- Image erstellen ----------

    def on_response(self, _dlg, response: int) -> None:
        if response == Gtk.ResponseType.APPLY:
            if self.busy:
                self.cancel.set()
                self.append_log("Abbruch angefordert …")
            else:
                self.start()
        elif not self.busy:
            self.destroy()

    def start(self) -> None:
        if not os.path.ismount(self.nas_root):
            self.append_log(f"NAS ist nicht eingehängt ({self.nas_root}) – links „Einhängen“ klicken.")
            return
        disk_path = self.disk_combo.get_active_id()
        disk = self.disks[disk_path]
        machine = self.name.get_text().strip()
        self.busy = True
        self.cancel.clear()
        for w in (self.name, self.disk_combo, self.shutdown, self.btn_close):
            w.set_sensitive(False)
        self.btn_start.set_label("Abbrechen")
        self.btn_start.get_style_context().remove_class("suggested-action")
        self.btn_start.get_style_context().add_class("destructive-action")
        self.append_log(f"Starte Disk-Image von {disk['name']} ({disk['model']}) …")

        sizes = {p["name"]: p["size"] for p in disk["partitions"] if p["fstype"] != "swap"}
        total = sum(sizes.values()) or 1
        done_parts: set[str] = set()
        state = {"part": ""}

        def progress(ev: dict) -> None:
            GLib.idle_add(self._on_progress, ev, sizes, total, done_parts, state)

        source = {"hostname": self.agent.hostname, "mac": self.agent.mac, "vendor": self.agent.vendor,
                  "product": self.agent.product, "agent_id": self.agent.agent_id}

        def work():
            try:
                path = agentclient.create_image(self.agent.ip, self.key, disk_path, self.nas_root, machine,
                                                progress, self.cancel, self.agent.control_port, source)
                GLib.idle_add(self._on_finished, path, None)
            except Exception as e:
                GLib.idle_add(self._on_finished, None, e)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, ev: dict, sizes, total, done_parts, state) -> bool:
        phase = ev.get("phase")
        if phase == "file":
            if state["part"] and state["part"] != ev.get("part"):
                done_parts.add(state["part"])
            state["part"] = ev.get("part", "")
            self.append_log(f"Übertrage {ev.get('file')}")
            return False
        if phase in ("begin", "done"):
            return False
        part = ev.get("part") or state["part"]
        pct = ev.get("pct")
        done = sum(sizes.get(p, 0) for p in done_parts)
        if part in sizes and pct is not None:
            done += sizes[part] * pct / 100
        frac = min(done / total, 1.0)
        speed = ev.get("speed", 0) / 1e6
        self.progress.set_fraction(frac)
        self.progress.set_text(f"{frac * 100:.0f} %  –  {part or 'Partitionstabelle'}  –  "
                               f"{nas.format_size(ev.get('total_bytes', 0))} übertragen  –  {speed:.0f} MB/s")
        return False

    def _on_finished(self, path, error) -> bool:
        self.busy = False
        for w in (self.name, self.disk_combo, self.shutdown, self.btn_close):
            w.set_sensitive(True)
        self.btn_start.set_label("Image erstellen")
        self.btn_start.get_style_context().remove_class("destructive-action")
        self.btn_start.get_style_context().add_class("suggested-action")
        if error:
            self.progress.set_text("Fehlgeschlagen" if not self.cancel.is_set() else "Abgebrochen")
            self.append_log(f"Fehler: {error}")
        else:
            self.progress.set_fraction(1.0)
            self.progress.set_text("Image fertig")
            self.append_log(f"Fertig: {path}")
            if self.on_done:
                self.on_done()
            self._power_off_after()
        return False

    def _power_off_after(self) -> None:
        """Nach erfolgreichem Auftrag: Zielmaschine herunterfahren, wenn gewünscht."""
        if not self.shutdown.get_active():
            return
        agent, key = self.agent, self.key

        def work():
            try:
                agentclient.power(agent.ip, key, "poweroff", agent.control_port)
                msg = "Maschine wird heruntergefahren."
            except Exception as e:
                msg = f"Herunterfahren fehlgeschlagen: {e}"
            GLib.idle_add(self.append_log, msg)

        threading.Thread(target=work, daemon=True).start()

