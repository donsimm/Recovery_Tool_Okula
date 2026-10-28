"""Dialog „Image zurückspielen“: Image vom NAS auf eine Disk der Zielmaschine schreiben."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import agentclient, archive, clonezilla, discovery, nas  # noqa: E402


def _gb(n: int) -> str:
    return f"{n / 1000**3:.1f} GB"


class RestoreDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, agent: discovery.AgentInfo, nas_root: str,
                 preselect: str | None = None):
        super().__init__(title="Image zurückspielen", transient_for=parent, modal=True)
        self.set_default_size(820, 640)
        self.agent = agent
        self.nas_root = nas_root
        self.preselect = preselect
        self.key = agentclient.load_or_create_key()
        # Auswahl-ID („Pfad<TAB>Disk“) → {"path", "disk", "machine", "completed", "disk_info", "format"}
        self.images: dict[str, dict] = {}
        self.disks: dict[str, dict] = {}
        self.cancel = threading.Event()
        self.busy = False

        self.btn_close = self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.btn_start = self.add_button("Zurückspielen", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("destructive-action")
        self.btn_start.set_sensitive(False)
        self.connect("response", self.on_response)
        self.connect("delete-event", lambda *_a: self.busy)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        row = 0
        grid.attach(Gtk.Label(label="Image", xalign=0), 0, row, 1, 1)
        self.image_combo = Gtk.ComboBoxText(hexpand=True)
        self.image_combo.connect("changed", lambda _c: self._update())
        grid.attach(self.image_combo, 1, row, 1, 1)
        row += 1
        self.source_info = Gtk.Label(xalign=0, wrap=True, selectable=True)
        grid.attach(self.source_info, 1, row, 1, 1)

        row += 1
        title = Gtk.Label(xalign=0)
        title.set_markup(f"Zielmaschine: <b>{GLib.markup_escape_text(agent.hostname or agent.ip)}</b> "
                         f"({agent.ip}) {GLib.markup_escape_text(agent.hardware)}")
        grid.attach(title, 0, row, 2, 1)
        row += 1
        grid.attach(Gtk.Label(label="Zieldisk", xalign=0), 0, row, 1, 1)
        self.disk_combo = Gtk.ComboBoxText(hexpand=True)
        self.disk_combo.connect("changed", lambda _c: self._update())
        grid.attach(self.disk_combo, 1, row, 1, 1)

        row += 1
        warn = Gtk.Label(xalign=0)
        warn.set_markup("<b>Wird vollständig überschrieben:</b>")
        warn.get_style_context().add_class("status-fail")
        grid.attach(warn, 0, row, 2, 1)
        row += 1
        self.target_store = Gtk.ListStore(str, str, str, str)
        view = Gtk.TreeView(model=self.target_store)
        for i, t in enumerate(("Partition", "Dateisystem", "Grösse", "Label")):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_expand(i == 3)
            view.append_column(col)
        view.get_selection().set_mode(Gtk.SelectionMode.NONE)
        sw = Gtk.ScrolledWindow(hexpand=True)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.set_min_content_height(110)
        sw.add(view)
        grid.attach(sw, 0, row, 2, 1)

        row += 1
        self.check = Gtk.Label(xalign=0, wrap=True)
        grid.attach(self.check, 0, row, 2, 1)
        row += 1
        self.verify = Gtk.CheckButton(label="Image vor dem Schreiben vollständig prüfen (empfohlen)", active=True)
        grid.attach(self.verify, 0, row, 2, 1)
        row += 1
        self.shutdown = Gtk.CheckButton(label="Maschine danach herunterfahren (Stick dann abziehen und einschalten)")
        grid.attach(self.shutdown, 0, row, 2, 1)
        row += 1
        self.confirm_label = Gtk.Label(xalign=0)
        grid.attach(self.confirm_label, 0, row, 1, 1)
        self.confirm = Gtk.Entry(placeholder_text="Disk-Namen eintippen")
        self.confirm.connect("changed", lambda _e: self._update())
        grid.attach(self.confirm, 1, row, 1, 1)

        row += 1
        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_text("Lade Images und Disks …")
        grid.attach(self.progress, 0, row, 2, 1)
        row += 1
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.log)
        grid.attach(sw, 0, row, 2, 1)

        self.get_content_area().add(grid)
        self.show_all()
        self._load()

    def append_log(self, text: str) -> bool:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), time.strftime("%H:%M:%S ") + text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        return False

    # ---------- Laden ----------

    def _load(self) -> None:
        root, agent, key = self.nas_root, self.agent, self.key

        def work():
            images, problems = {}, []
            for img in archive.scan(root).all_images():  # auch Images in Archiv-Ordnern
                if img.kind == "Disk-Image":
                    try:
                        meta = agentclient.load_image(img.path)
                    except agentclient.AgentError:
                        continue
                    disk = meta.get("disk", {})
                    images[f"{img.path}\t{disk.get('name', '')}"] = {
                        "path": str(img.path), "disk": None, "machine": meta.get("machine", "?"),
                        "completed": meta.get("completed", ""), "disk_info": disk, "format": "Okula",
                        "product": meta.get("source", {}).get("product", "")}
                elif img.kind == "Clonezilla":
                    for d in clonezilla.disks(img.path):
                        try:
                            src = clonezilla.build(img.path, d)
                        except (clonezilla.ClonezillaError, OSError) as e:
                            problems.append(f"{img.name} ({d}): {e}")
                            continue
                        images[f"{img.path}\t{d}"] = {
                            "path": str(img.path), "disk": d, "machine": img.path.name,
                            "completed": img.mtime.isoformat(timespec="minutes"), "disk_info": src["source"],
                            "format": "Clonezilla", "product": ""}
            try:
                info = agentclient.get_info(agent.ip, key, agent.control_port)
            except Exception as e:
                info = e
            GLib.idle_add(self._on_loaded, images, info, problems)

        threading.Thread(target=work, daemon=True).start()

    def _on_loaded(self, images: dict, info, problems: list[str]) -> bool:
        self.images = images
        for key, meta in sorted(images.items(), key=lambda kv: kv[1].get("completed", ""), reverse=True):
            d = meta["disk_info"]
            when = meta.get("completed", "")[:16].replace("T", " ")
            self.image_combo.append(key, f"[{meta['format']}] {meta['machine']} – {d.get('name', '?')} "
                                         f"{d.get('model', '')} ({_gb(int(d.get('size') or 0))}) – {when}")
        for msg in problems:
            self.append_log(f"Nicht zurückspielbar: {msg}")
        match = [k for k in images if k.split("\t")[0] == self.preselect]
        if match:
            self.image_combo.set_active_id(match[0])
        elif images:
            self.image_combo.set_active(0)
        else:
            self.append_log("Keine Okula-Disk-Images auf dem NAS gefunden.")
        if isinstance(info, Exception):
            self.append_log(f"Agent nicht erreichbar: {info}")
        else:
            self.disks = {d["path"]: d for d in info.get("disks", [])}
            for path, d in self.disks.items():
                self.disk_combo.append(path, f"{d['name']} – {d['model'] or 'Disk'} ({_gb(d['size'])})")
            if self.disks:
                self.disk_combo.set_active(0)
        self.progress.set_text("Bereit")
        self._update()
        return False

    # ---------- Prüfen ----------

    def _update(self) -> None:
        meta = self.images.get(self.image_combo.get_active_id() or "")
        disk = self.disks.get(self.disk_combo.get_active_id() or "")
        if meta:
            d = meta["disk_info"]
            parts = ", ".join(f"{p['name']} {p.get('fstype') or 'roh'}" for p in d.get("partitions", []))
            self.source_info.set_text(f"Quelle ({meta['format']}): {meta['product'] or meta['machine']} · "
                                      f"{d.get('model', '')} {_gb(int(d.get('size') or 0))} · "
                                      f"{d.get('pttype', '')} · {parts}")
        self.target_store.clear()
        if disk:
            for p in disk["partitions"] or [{"name": disk["name"], "fstype": disk["fstype"], "size": disk["size"],
                                             "label": ""}]:
                self.target_store.append([p["name"], p["fstype"] or "leer/unbekannt", nas.format_size(p["size"]),
                                          p.get("label", "")])
            self.confirm_label.set_markup(f"Bestätigung: <b>{GLib.markup_escape_text(disk['name'])}</b> eintippen")
        ok = False
        if meta and disk:
            need = int(meta["disk_info"].get("size") or 0)
            if disk["size"] < need:
                self.check.set_markup(f"<b>Zieldisk zu klein:</b> {_gb(disk['size'])} &lt; {_gb(need)} "
                                      "(Image braucht mindestens die Grösse der Quelldisk)")
            elif any(p["mounted"] for p in disk["partitions"]):
                self.check.set_markup("<b>Eine Partition der Zieldisk ist eingehängt.</b>")
            else:
                extra = " (grösser – der Rest bleibt frei)" if disk["size"] > need else ""
                self.check.set_text(f"Grösse passt: {_gb(disk['size'])}{extra}")
                ok = True
        typed = disk is not None and self.confirm.get_text().strip() == disk["name"]
        if not self.busy:
            self.btn_start.set_sensitive(ok and typed)

    # ---------- Zurückspielen ----------

    def on_response(self, _dlg, response: int) -> None:
        if response == Gtk.ResponseType.APPLY:
            if self.busy:
                self.cancel.set()
                self.append_log("Abbruch angefordert – die Zieldisk bleibt unvollständig.")
            else:
                self.start()
        elif not self.busy:
            self.destroy()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for w in (self.image_combo, self.disk_combo, self.verify, self.shutdown, self.confirm, self.btn_close):
            w.set_sensitive(not busy)
        self.btn_start.set_label("Abbrechen" if busy else "Zurückspielen")
        if not busy:
            self._update()

    def start(self) -> None:
        if not os.path.ismount(self.nas_root):
            self.append_log("NAS ist nicht eingehängt.")
            return
        chosen = self.images[self.image_combo.get_active_id()]
        image, source_disk = chosen["path"], chosen["disk"]
        disk = self.disk_combo.get_active_id()
        verify = self.verify.get_active()
        self.cancel.clear()
        self._set_busy(True)
        self.append_log(f"Spiele {os.path.basename(image)} auf {disk} zurück …")

        def progress(ev: dict) -> None:
            GLib.idle_add(self._on_progress, ev)

        def work():
            try:
                agentclient.restore_image(self.agent.ip, self.key, image, disk, progress, self.cancel,
                                          self.agent.control_port, verify, source_disk)
                GLib.idle_add(self._on_finished, None)
            except Exception as e:
                GLib.idle_add(self._on_finished, e)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, ev: dict) -> bool:
        phase = ev.get("phase")
        if phase == "note":
            self.append_log(ev.get("message", ""))
        elif phase == "verify":
            self.progress.set_fraction(ev.get("fraction", 0))
            self.progress.set_text(f"Prüfe Image: {ev.get('fraction', 0) * 100:.0f} %")
        elif phase == "table":
            self.append_log("Image geprüft – schreibe Partitionstabelle und Bootcode")
            self.progress.set_fraction(0)
        elif phase == "file":
            self.append_log(f"Schreibe {ev.get('part')} ({ev.get('file')})")
        elif phase == "data":
            frac = ev.get("fraction", 0)
            self.progress.set_fraction(frac)
            self.progress.set_text(f"{frac * 100:.0f} %  –  {ev.get('part')}  –  "
                                   f"{ev.get('speed', 0) / 1e6:.0f} MB/s")
        return False

    def _on_finished(self, error) -> bool:
        self._set_busy(False)
        if error:
            self.progress.set_text("Abgebrochen" if self.cancel.is_set() else "Fehlgeschlagen")
            self.append_log(f"Fehler: {error}")
        else:
            self.progress.set_fraction(1.0)
            self.progress.set_text("Zurückgespielt")
            self.append_log(f"Fertig {datetime.now():%H:%M}. Stick abziehen und die Maschine neu starten.")
            self._power_off_after()
        self.confirm.set_text("")
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

