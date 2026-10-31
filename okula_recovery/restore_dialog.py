"""Dialog „Image zurückspielen“: Image vom NAS auf eine Disk der Zielmaschine schreiben."""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from okula_recovery import agentclient, archive, clonezilla, devices, discovery, nas, winunattend  # noqa: E402


def _gb(n: int) -> str:
    return f"{n / 1000**3:.1f} GB"


class RestoreDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, agent: discovery.AgentInfo, nas_root: str,
                 start_job: Callable[..., None], preselect: str | None = None,
                 device_name: str = "", device: devices.Device | None = None):
        """start_job(image, quelldisk, zieldisk, prüfen, herunterfahren, bezeichnung, anpassen) startet den Auftrag;
        anpassen = {"swiss", "account"} oder None."""
        super().__init__(title="Image zurückspielen", transient_for=parent, modal=True)
        self.start_job = start_job
        self.set_default_size(820, 640)
        self.agent = agent
        self.nas_root = nas_root
        self.preselect = preselect
        self.key = agentclient.load_or_create_key()
        # Auswahl-ID („Pfad<TAB>Disk“) → {"path", "disk", "machine", "completed", "disk_info", "format"}
        self.images: dict[str, dict] = {}
        self.disks: dict[str, dict] = {}
        self.btn_close = self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn_start = self.add_button("Zurückspielen", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("destructive-action")
        self.btn_start.set_sensitive(False)
        self.connect("response", self.on_response)

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
        title.set_markup(f"Zielgerät: <b>{GLib.markup_escape_text(device_name or agent.hostname or agent.ip)}</b> "
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
        # Master-Image: danach Gerätename, Windows-Key (und Region/Konto) setzen
        self.device = device
        name = device.name if device else device_name
        key = device.windows_key[0] if device else ""
        self.custom = Gtk.CheckButton(label=f"Danach anpassen: Gerätename „{name}“ "
                                            f"(Windows: {winunattend.computer_name(name) or '–'})"
                                            + (", Windows-Key" if key else "") + " – nur Master-Image mit Sysprep")
        self.custom.connect("toggled", lambda _c: self._update())
        grid.attach(self.custom, 0, row, 2, 1)
        row += 1
        custom_box = Gtk.Box(spacing=8, margin_start=24)
        self.custom_swiss = Gtk.CheckButton(label="Region Schweiz", active=True)
        custom_box.pack_start(self.custom_swiss, False, False, 0)
        custom_box.pack_start(Gtk.Label(label="Lokales Konto"), False, False, 0)
        self.custom_account = Gtk.Entry(placeholder_text="leer = Windows fragt", width_chars=18)
        custom_box.pack_start(self.custom_account, False, False, 0)
        self.custom_box = custom_box
        grid.attach(custom_box, 0, row, 2, 1)
        row += 1
        # Ä-002: Zieldisk kleiner → Image dafür anpassen (neues Image, Original bleibt)
        self.adapt = Gtk.CheckButton(label="Für diese Disk anpassen (neues Image wird erstellt, Original bleibt)",
                                     no_show_all=True)
        self.adapt.connect("toggled", lambda _c: self._update())
        grid.attach(self.adapt, 0, row, 2, 1)
        self._shrink_checked: dict = {}   # (Image, Disk-Grösse) → Plan-Zeilen oder Fehlertext
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
                        "product": meta.get("source", {}).get("product", ""), "master": img.master}
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
                            "format": "Clonezilla", "product": "", "master": img.master}
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
            self.image_combo.append(key, f"{'★ Master ' if meta.get('master') else ''}"
                                         f"[{meta['format']}] {meta['machine']} – {d.get('name', '?')} "
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
        image_id = self.image_combo.get_active_id() or ""
        if meta and image_id != getattr(self, "_custom_for", None):  # Master-Image: Anpassen vorschlagen
            self._custom_for = image_id
            self.custom.set_active(bool(meta.get("master")))
        self.custom_box.set_sensitive(self.custom.get_active())
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
        self.adapt.set_visible(False)
        if meta and disk:
            need = int(meta["disk_info"].get("size") or 0)
            if disk["size"] < need:
                ok = self._smaller_disk(meta, disk, need)
            elif any(p["mounted"] for p in disk["partitions"]):
                self.check.set_markup("<b>Eine Partition der Zieldisk ist eingehängt.</b>")
            else:
                extra = " (grösser – der Rest bleibt frei)" if disk["size"] > need else ""
                self.check.set_text(f"Grösse passt: {_gb(disk['size'])}{extra}")
                ok = True
        typed = disk is not None and self.confirm.get_text().strip() == disk["name"]
        self.btn_start.set_sensitive(ok and typed)

    def _smaller_disk(self, meta: dict, disk: dict, need: int) -> bool:
        """Zieldisk kleiner: prüfen (im Hintergrund), ob sich das Image anpassen lässt, und das anbieten."""
        key = (meta["path"], meta.get("disk"), disk["size"])
        result = self._shrink_checked.get(key)
        intro = f"<b>Zieldisk kleiner als das Image:</b> {_gb(disk['size'])} &lt; {_gb(need)}. "
        if result is None:
            self._shrink_checked[key] = "…"
            self.check.set_markup(intro + "Prüfe, ob sich das Image anpassen lässt …")

            def work():
                from okula_recovery import shrink
                try:
                    res = shrink.plan(meta["path"], disk["size"], meta.get("disk")).lines()
                except shrink.ShrinkError as e:
                    res = str(e)
                except Exception as e:  # z. B. NAS nicht erreichbar
                    res = f"Prüfung fehlgeschlagen: {e}"
                GLib.idle_add(self._shrink_result, key, res)

            threading.Thread(target=work, daemon=True).start()
            return False
        if result == "…":
            return False
        if isinstance(result, str):
            self.check.set_markup(intro + "Anpassen geht nicht: " + GLib.markup_escape_text(result))
            return False
        self.check.set_markup(intro + "Das Image lässt sich anpassen:\n" +
                              "\n".join("• " + GLib.markup_escape_text(x) for x in result))
        self.adapt.set_visible(True)
        return self.adapt.get_active()

    def _shrink_result(self, key, result) -> bool:
        self._shrink_checked[key] = result
        self._update()
        return False

    # ---------- Zurückspielen ----------

    def on_response(self, _dlg, response: int) -> None:
        if response != Gtk.ResponseType.APPLY:
            self.destroy()
            return
        if not os.path.ismount(self.nas_root):
            self.append_log("NAS ist nicht eingehängt.")
            return
        chosen = self.images[self.image_combo.get_active_id()]
        target = self.disk_combo.get_active_id()
        label = f"{chosen['machine']} ({chosen['disk_info'].get('name', '?')})"
        try:
            custom = {"swiss": self.custom_swiss.get_active(), "account": self.custom_account.get_text().strip()} \
                if self.custom.get_active() else None
            adapt = self.disks[target]["size"] if self.adapt.get_visible() and self.adapt.get_active() else None
            self.start_job(chosen["path"], chosen["disk"], target, self.verify.get_active(),
                           self.shutdown.get_active(), label, custom, adapt)
        except Exception as e:
            self.append_log(f"Nicht gestartet: {e}")
            return
        self.destroy()
