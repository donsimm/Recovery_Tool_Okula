"""Reiter „BIOS“ im Gerätefenster (I-032): lesen, beim Gerät speichern, mit einem anderen Gerät vergleichen,
als CSV speichern und – wo das Modell es unter Linux erlaubt – einzelne Einstellungen ändern."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import agentclient, biosinfo, devices  # noqa: E402
from okula_recovery.uikit import confirm_error, numbered_section, remember_columns, run_async, scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow

RED, GREEN, GREY = "#c62828", "#2e7d32", "#757575"


def _esc(text: str) -> str:
    return GLib.markup_escape_text(text or "")


class BiosTab(Gtk.Box):
    # Spalten: Einstellung (Markup), hier (Markup), Vergleich (Markup), mögliche Werte, Name für „Ändern“, Tooltip
    def __init__(self, main: "MainWindow", dev: devices.Device):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        self.main, self.dev = main, dev
        self.busy = False

        head = Gtk.Box(spacing=8)
        self.summary = Gtk.Label(xalign=0, wrap=True)
        head.pack_start(self.summary, True, True, 0)
        self.btn_read = Gtk.Button(label="BIOS lesen")
        self.btn_read.set_tooltip_text("Einstellungen über den Agent lesen und beim Gerät speichern (ändert nichts)")
        self.btn_read.connect("clicked", lambda _b: self.read())
        self.btn_csv = Gtk.Button(label="Als CSV speichern …")
        self.btn_csv.connect("clicked", lambda _b: self.save_csv())
        for b in (self.btn_csv, self.btn_read):
            head.pack_end(b, False, False, 0)
        self.pack_start(head, False, False, 0)

        basics = numbered_section(self, "", "Grundangaben", "auch bei Modellen ohne BIOS-Schnittstelle")
        self.grid = Gtk.Grid(column_spacing=16, row_spacing=4)
        basics.pack_start(self.grid, False, False, 0)

        sec = numbered_section(self, "", "Einstellungen", "Doppelklick: ändern (gilt nach dem Neustart)")
        bar = Gtk.Box(spacing=8)
        bar.pack_start(Gtk.Label(label="Vergleichen mit"), False, False, 0)
        self.other = Gtk.ComboBoxText()
        self.other.connect("changed", lambda _c: self.fill())
        bar.pack_start(self.other, False, False, 0)
        self.only_diff = Gtk.CheckButton(label="Nur Unterschiede", active=True)
        self.only_diff.connect("toggled", lambda _c: self.fill())
        bar.pack_start(self.only_diff, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Einstellung suchen", width_chars=22)
        self.search.connect("search-changed", lambda _e: self.fill())
        bar.pack_end(self.search, False, False, 0)
        self.btn_set = Gtk.Button(label="Ändern …", sensitive=False)
        self.btn_set.connect("clicked", lambda _b: self.change_selected())
        bar.pack_end(self.btn_set, False, False, 0)
        sec.pack_start(bar, False, False, 0)

        self.store = Gtk.ListStore(str, str, str, str, str, str)
        self.view = Gtk.TreeView(model=self.store)
        self.cols = []
        for i, title in enumerate(("Einstellung", "Dieses Gerät", "Vergleichsgerät", "Mögliche Werte")):
            cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, cell, **({"markup": i} if i < 3 else {"text": i}))
            self.view.append_column(col)
            self.cols.append(col)
        remember_columns(self.view, "geraet_bios", {"Einstellung": 260, "Dieses Gerät": 200, "Vergleichsgerät": 200})
        self.view.set_tooltip_column(5)
        self.view.connect("row-activated", lambda *_a: self.change_selected())
        self.view.get_selection().connect("changed", lambda _s: self._update_buttons())
        sec.pack_start(scrolled(self.view), True, True, 0)
        self.child_set_property(sec, "expand", True)       # Tabelle nimmt den Rest der Höhe
        self.child_set_property(sec, "fill", True)
        self.refresh()

    # ---------- Anzeige ----------

    def connected(self):
        agent = self.main.online_agent(self.dev)
        return agent if agent is not None and agent.control_port else None

    def refresh(self) -> None:
        """Vergleichsliste, Grundangaben und Tabelle aus dem gespeicherten Stand (dev.bios) neu aufbauen."""
        current = self.other.get_active_id()
        self.other.remove_all()
        self.other.append("", "– kein Vergleich –")
        for d in sorted(self.main.store.devices.values(), key=lambda d: d.name.lower()):
            if d.id != self.dev.id and d.bios:
                self.other.append(d.id, f"{d.name} ({biosinfo.short_time(d.bios.get('read', ''))})")
        if not self.other.set_active_id(current or ""):
            self.other.set_active_id("")
        for child in self.grid.get_children():
            self.grid.remove(child)
        data = self.dev.bios
        if data:
            for row, (label, value) in enumerate(biosinfo.basics(data) +
                                                 [("UEFI-Startreihenfolge", biosinfo.boot_text(data))]):
                name = Gtk.Label(label=label, xalign=0, yalign=0)
                name.get_style_context().add_class("status-idle")
                text = Gtk.Label(label=value, xalign=0, wrap=True, selectable=True)
                text.set_max_width_chars(110)
                self.grid.attach(name, 0, row, 1, 1)
                self.grid.attach(text, 1, row, 1, 1)
        self.grid.show_all()
        self.btn_read.set_sensitive(self.connected() is not None and not self.busy)
        self.btn_csv.set_sensitive(bool(data))
        self.fill()
        if not data and not self.busy:
            self.summary.set_text("Noch nicht gelesen – Gerät mit dem Agent verbinden und „BIOS lesen“ klicken"
                                  if self.connected() is None else "Noch nicht gelesen")

    def _other(self) -> tuple[dict | None, str]:
        dev = self.main.store.devices.get(self.other.get_active_id() or "")
        return (dev.bios, dev.name) if dev is not None and dev.bios else (None, "")

    def fill(self) -> None:
        data = self.dev.bios
        self.store.clear()
        other, other_name = self._other()
        self.cols[2].set_visible(other is not None)
        self.cols[2].set_title((other_name or "Vergleichsgerät").replace("_", "__"))   # „_“ ist sonst ein Kürzel
        self.only_diff.set_sensitive(other is not None)
        if not data:
            return
        self.summary.set_text(biosinfo.summary(data, other, other_name))
        for r in biosinfo.compare(data, other, self.only_diff.get_active(), self.search.get_text()):
            name = f"<b>{_esc(r['name'])}</b>" if r["important"] else _esc(r["name"])
            here, there = _esc(r["here"]), _esc(r["other"])
            if r["diff"]:
                here, there = (f'<span foreground="{RED}"><b>{x}</b></span>' for x in (here, there))
            attr = r.get("attr") or {}
            tip = (f"{r['name']} (intern: {attr.get('name')})" if attr else r["name"]) + \
                f"\n{self.dev.name}: {r['here'] or '–'}" + (f"\n{other_name}: {r['other'] or '–'}" if other else "") + \
                (f"\nStandard: {attr['default']}" if attr.get("default") else "")
            self.store.append([name, here, there, biosinfo.possible_text(attr) if attr else "",
                               attr.get("name", "") if attr else "", tip])
        self._update_buttons()

    def _selected_attr(self) -> dict | None:
        model, it = self.view.get_selection().get_selected()
        if it is None or not model[it][4]:
            return None
        return next((a for a in self.dev.bios.get("attributes") or [] if a.get("name") == model[it][4]), None)

    def _update_buttons(self) -> None:
        self.btn_set.set_sensitive(self._selected_attr() is not None and self.connected() is not None)

    # ---------- Lesen ----------

    def read(self) -> None:
        agent = self.connected()
        if agent is None or self.busy:
            return
        self.busy = True
        self.btn_read.set_sensitive(False)
        self.summary.set_text("BIOS wird gelesen …")
        key = self.main.key
        run_async(lambda: agentclient.bios(agent.ip, key, agent.control_port), self._read_done)

    def _read_done(self, result) -> bool:
        self.busy = False
        if isinstance(result, Exception):
            self.summary.set_markup(f'<span foreground="{RED}">BIOS nicht lesbar: {_esc(str(result))}</span>')
            self.btn_read.set_sensitive(self.connected() is not None)
            return False
        first = not self.dev.bios
        self.dev.bios = result
        self.main.store.save(self.dev)
        if first:
            self.main.store.add_history(self.dev, "notiz", "BIOS gelesen" +
                                        (f" ({len(result.get('attributes') or [])} Einstellungen)"
                                         if result.get("interfaces") else " (nur Grundangaben)"))
        self.refresh()
        return False

    # ---------- Ändern ----------

    def change_selected(self) -> None:
        attr, agent = self._selected_attr(), self.connected()
        if attr is None or agent is None:
            return
        win = self.get_toplevel()
        dlg = Gtk.Dialog(title="BIOS-Einstellung ändern", transient_for=win, modal=True)
        dlg.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        ok = dlg.add_button("Setzen", Gtk.ResponseType.OK)
        ok.get_style_context().add_class("destructive-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"<b>{_esc(attr.get('display') or attr['name'])}</b> auf „{_esc(self.dev.name)}“\n"
                        f"Jetzt: {_esc(attr.get('value', ''))}")
        box.pack_start(head, False, False, 0)
        if attr.get("possible"):
            value = Gtk.ComboBoxText()
            for p in attr["possible"]:
                value.append(p, p)
            value.set_active_id(attr.get("value"))
            get = value.get_active_id
        else:
            value = Gtk.Entry(text=attr.get("value", ""), activates_default=True)
            get = value.get_text
        box.pack_start(value, False, False, 0)
        need_pw = any((self.dev.bios.get("auth") or {}).values())
        pw = Gtk.Entry(visibility=False, placeholder_text="BIOS-Admin-Passwort" + ("" if need_pw else " (falls gesetzt)"),
                       activates_default=True)
        pw.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        box.pack_start(pw, False, False, 0)
        warn = biosinfo.risky(attr.get("display") or attr["name"])
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_max_width_chars(70)
        note.set_markup((f'<span foreground="{RED}">⚠ {_esc(warn)}</span>\n' if warn else "") +
                        "Gilt nach dem nächsten Neustart. Das Passwort geht verschlüsselt an den Agent und wird nicht "
                        "gespeichert.")
        box.pack_start(note, False, False, 0)
        dlg.get_content_area().add(box)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()
        answer, new, password = dlg.run(), get() or "", pw.get_text()
        dlg.destroy()
        if answer != Gtk.ResponseType.OK or new == attr.get("value"):
            return
        key, name = self.main.key, attr["name"]

        def done(result) -> bool:
            if isinstance(result, Exception):
                confirm_error(win, f"BIOS-Einstellung nicht gesetzt: {result}")
                return False
            self.main.store.add_history(self.dev, "notiz", f"BIOS: {attr.get('display') or name} = {new} "
                                                           "(gilt nach dem Neustart)", ok=True)
            self.main.status(f"{self.dev.name}: BIOS „{attr.get('display') or name}“ = {new} – gilt nach dem Neustart")
            self.read()
            return False

        run_async(lambda: agentclient.bios_set(agent.ip, key, name, new, password, agent.control_port), done)

    # ---------- CSV ----------

    def save_csv(self) -> None:
        data = self.dev.bios
        if not data:
            return
        other, other_name = self._other()
        rows = biosinfo.compare(data, other, self.only_diff.get_active() and other is not None, self.search.get_text())
        dlg = Gtk.FileChooserDialog(title="BIOS als CSV speichern", transient_for=self.get_toplevel(),
                                    action=Gtk.FileChooserAction.SAVE)
        dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Speichern", Gtk.ResponseType.OK)
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_current_name(f"BIOS_{self.dev.name}" + (f"_vs_{other_name}" if other else "") + ".csv")
        if dlg.run() == Gtk.ResponseType.OK:
            path = Path(dlg.get_filename())
            try:
                path.write_text(biosinfo.to_csv(rows, self.dev.name, other_name), encoding="utf-8")
                self.main.status(f"BIOS gespeichert: {path}")
            except OSError as e:
                confirm_error(self.get_toplevel(), f"Nicht gespeichert: {e}")
        dlg.destroy()
