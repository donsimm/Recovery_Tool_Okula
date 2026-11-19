"""Oberfläche „Software installieren“ (I-020) und Software-Bibliothek (Ä-041): Auswahlliste mit Häkchen
(OS installieren, Image zurückspielen, Automatisierung) und das Fenster Extras → „Software-Bibliothek …“
(laden, Angaben bearbeiten, löschen). Logik in software.py."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from okula_recovery import nas, software  # noqa: E402
from okula_recovery.uikit import confirm, confirm_error, run_async, scrolled  # noqa: E402
from okula_recovery.usbtools import rate_text  # noqa: E402

TITLE = "Software installieren"
LIBRARY_TITLE = "Software-Bibliothek"
FOLDER_HINT = "Programme aus der Software-Bibliothek – laden und Parameter pflegen: Extras → „Software-Bibliothek …“."
NOT_FOUND = "fehlt in der Bibliothek"
URI_TARGET = "text/uri-list"


class SoftwareChooser(Gtk.Box):
    """Liste „Software installieren“ mit Häkchen, Suchfeld und Spalten Programm, Version, Grösse, Status.

    Nur Einträge mit Status „bereit“ oder „nur kopieren“ lassen sich ankreuzen; die Gesamtgrösse steht darunter."""

    # Häkchen, Programm, Version, Grösse (Text), Status, Name, wählbar, Grösse (Byte), Tooltip, sichtbar
    C_ON, C_PROG, C_VER, C_SIZE, C_STATUS, C_NAME, C_OK, C_BYTES, C_TIP, C_SHOW = range(10)

    def __init__(self, on_change: Callable[[], None] | None = None, height: int = 140, when: str = "ersten"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.on_change = on_change or (lambda: None)
        self.when = when             # „ersten“ (Aufsetzen) bzw. „nächsten“ Windows-Start (Ä-044)
        self.entries: list[software.Entry] = []
        self.nas_root: str | None = None
        self.loaded = False
        head = Gtk.Box(spacing=8)
        title = Gtk.Label(xalign=0)
        title.set_markup(f"<b>{TITLE}</b>")
        head.pack_start(title, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Suchen …", width_chars=18)
        self.search.connect("search-changed", lambda _e: self.filter.refilter())
        head.pack_end(self.search, False, False, 0)
        self.pack_start(head, False, False, 0)
        self.store = Gtk.ListStore(bool, str, str, str, str, str, bool, GObject.TYPE_INT64, str, bool)
        self.filter = self.store.filter_new()
        self.filter.set_visible_func(self._visible)
        self.view = Gtk.TreeView(model=self.filter, tooltip_column=self.C_TIP)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_toggle)
        col = Gtk.TreeViewColumn("", toggle, active=self.C_ON, activatable=self.C_OK)
        self.view.append_column(col)
        for title_text, index, expand in (("Programm", self.C_PROG, True), ("Version", self.C_VER, False),
                                          ("Grösse", self.C_SIZE, False), ("Status", self.C_STATUS, False)):
            cell = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title_text, cell, text=index, sensitive=self.C_OK)
            column.set_expand(expand)
            column.set_resizable(True)
            self.view.append_column(column)
        sw = scrolled(self.view)
        sw.set_min_content_height(height)
        self.pack_start(sw, True, True, 0)
        self.total = Gtk.Label(xalign=0, wrap=True)
        self.pack_start(self.total, False, False, 0)
        self.hint = Gtk.Label(label=FOLDER_HINT, xalign=0, wrap=True)
        self.hint.get_style_context().add_class("status-idle")
        self.pack_start(self.hint, False, False, 0)
        self._update_total()

    def _visible(self, model, it, _data) -> bool:
        text = self.search.get_text().strip().lower()
        if not text:
            return True
        row = model[it]
        return text in f"{row[self.C_PROG]} {row[self.C_VER]} {row[self.C_NAME]} {row[self.C_STATUS]}".lower()

    def load(self, nas_root: str | None, selected: list[str] | None = None) -> None:
        """Bibliothek im Hintergrund lesen und Auswahl setzen."""
        self.nas_root = nas_root
        keep = list(selected) if selected is not None else self.selected()
        self.loaded = False          # bis die Bibliothek gelesen ist, gilt die gespeicherte Auswahl
        self.store.clear()
        if not nas_root:
            self.total.set_text("NAS nicht verbunden – keine Software wählbar")
            return
        self.total.set_text("Software-Bibliothek wird gelesen …")
        run_async(lambda: software.scan(nas_root), lambda result: self._loaded(result, keep))

    def _loaded(self, result, keep: list[str]) -> None:
        if isinstance(result, Exception):
            self.total.set_text(f"Software-Bibliothek nicht lesbar: {result}")
            return
        self.entries = result
        self.loaded = True
        chosen, missing, _renamed = software.resolve(self.entries, keep)
        names = {e.name for e in chosen}
        self.store.clear()
        for e in self.entries:
            tip = f"{e.name} · {e.kind_label}" + (f" · {e.publisher}" if e.publisher else "") \
                + (f" · Parameter: {e.args}" if e.args and e.mode == software.INSTALL else "") \
                + (f"\n{e.note}" if e.note else "")
            self.store.append([e.name in names and e.selectable, e.program, e.version, nas.format_size(e.size),
                               e.status, e.name, e.selectable, e.size, tip, True])
        for name in missing:         # gespeicherte Auswahl, die es nicht mehr gibt – nur abwählbar
            self.store.append([True, name, "", "", NOT_FOUND, name, True, 0,
                               "Liegt nicht mehr in der Software-Bibliothek – wird übersprungen", True])
        if not self.entries and not missing:
            self.total.set_text("Keine Programme in der Software-Bibliothek – Extras → Software-Bibliothek …")
        self._update_total()
        self.on_change()

    def _on_toggle(self, _cell, path) -> None:
        it = self.filter.convert_iter_to_child_iter(self.filter.get_iter(path))
        row = self.store[it]
        if row[self.C_STATUS] == NOT_FOUND:
            self.store.remove(it)
        elif row[self.C_OK]:
            row[self.C_ON] = not row[self.C_ON]
        self._update_total()
        self.on_change()

    def selected(self) -> list[str]:
        return [row[self.C_NAME] for row in self.store if row[self.C_ON]]

    def selected_entries(self) -> list[software.Entry]:
        names = set(self.selected())
        return [e for e in self.entries if e.name in names]

    def _update_total(self) -> None:
        chosen = [row for row in self.store if row[self.C_ON]]
        if not self.store.get_iter_first() and self.total.get_text():
            return
        if not chosen:
            self.total.set_text("Keine Software gewählt")
            return
        size = sum(row[self.C_BYTES] for row in chosen)
        self.total.set_text(f"Gewählt: {len(chosen)} Programm(e), zusammen {nas.format_size(size)} – werden beim "
                            f"{self.when} Windows-Start still installiert (Protokoll "
                            "C:\\Windows\\Temp\\okula-software.log)")


class SoftwareInstallDialog(Gtk.Dialog):
    """Software installieren an einem Gerät mit Windows (Ä-044): Auswahl aus der Bibliothek (nur „bereit“ und „nur
    kopieren“ wählbar), Senden legt Installer und Startskript ab – Windows installiert beim nächsten Start."""

    def __init__(self, parent: Gtk.Window | None, device_name: str, nas_root: str):
        super().__init__(title="Software installieren", transient_for=parent, modal=True)
        self.set_default_size(640, 520)
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn = self.add_button("Senden", Gtk.ResponseType.OK)
        self.btn.get_style_context().add_class("suggested-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"Programme für <b>{GLib.markup_escape_text(device_name)}</b> – Windows installiert sie beim "
                        "nächsten Start still und ohne Klicks (als SYSTEM, nacheinander in der Reihenfolge der "
                        "Liste).")
        box.pack_start(head, False, False, 0)
        self.chooser = SoftwareChooser(on_change=self._update, height=280, when="nächsten")
        box.pack_start(self.chooser, True, True, 0)
        for text in ("Ausgegraut: „Parameter fehlt“ bzw. „nur von Hand“ – Grund in der Liste (Maus über der Zeile), "
                     "Parameter in Extras → „Software-Bibliothek …“ hinterlegen.",
                     "Das Gerät muss mit dem Agent laufen; Windows vollständig heruntergefahren (kein Schnellstart/"
                     "Ruhezustand). Danach Gerät neu starten (Agent-Stick abziehen). Erneut senden ersetzt eine noch "
                     "nicht installierte Auswahl; ein ausstehendes „Windows anpassen“ bleibt."):
            hint = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=80)
            hint.get_style_context().add_class("status-idle")
            box.pack_start(hint, False, False, 0)
        self.get_content_area().add(box)
        self.show_all()
        self.chooser.load(nas_root, [])
        self._update()

    def _update(self) -> None:
        self.btn.set_sensitive(self.chooser.loaded and bool(self.selected()))

    def selected(self) -> list[str]:
        """Gewählte Einträge der Bibliothek (Name), Reihenfolge wie in der Liste."""
        return [e.name for e in self.chooser.selected_entries()]

    def summary(self) -> str:
        return software.summary(self.chooser.selected_entries())


class SoftwareLibraryWindow(Gtk.Window):
    """Extras → „Software-Bibliothek …“ (Ä-041): oben laden (Datei, Ordner, Ziehen und Ablegen), darunter die Liste
    mit den Angaben – Programm, Version, Hersteller, Parameter und Rückgabewerte direkt in der Zeile bearbeitbar, Art
    und Installer über „Bearbeiten …“, „Neu erkennen“ (Ä-043) über Knopf und Kontextmenü; unter der Liste die
    Angaben des markierten Eintrags (Typ, Hersteller, Hinweis bei „Parameter fehlt“)."""

    # Name, Programm, Version, Typ, Parameter, Rückgabewerte, Status, Grösse (Text), Grösse (Byte), Tooltip,
    # Parameter bearbeitbar, Hersteller
    C_NAME, C_PROG, C_VER, C_TYPE, C_ARGS, C_CODES, C_STATUS, C_SIZE, C_BYTES, C_TIP, C_EDIT, C_PUB = range(12)

    def __init__(self, parent: Gtk.Window, root: str, where: str = "NAS"):
        super().__init__(title=LIBRARY_TITLE, transient_for=parent)
        self.parent_window = parent
        self.root = root
        self.set_default_size(1100, 560)
        self.entries: list[software.Entry] = []
        self.queue: list[str] = []
        self.cancel = threading.Event()
        self.running = False           # Laden läuft (für „Beenden“ im Hauptfenster)
        self.closing = False
        self.select_after = ""
        self.message = ""              # Meldung, die nach dem nächsten Neulesen vor der Zählung stehen bleibt
        self.connect("delete-event", self._on_delete)
        self.connect("destroy", lambda _w: setattr(self, "closing", True))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
        intro = Gtk.Label(xalign=0, wrap=True)
        intro.set_markup(
            f"Programme für <i>Software installieren</i> – Ablage: {GLib.markup_escape_text(where)}: "
            f"/{software.LIBRARY_DIR}. Installer (<tt>.exe</tt>, <tt>.msi</tt>, <tt>.msp</tt>, <tt>.msu</tt>, "
            "<tt>.msix</tt>, <tt>.appx</tt> und Bündel) mit <b>Ins Tool laden …</b>, Installer mit Dateien daneben mit "
            "<b>Ordner laden …</b> – oder aus dem Dateimanager hierher ziehen. Erkannte Installer sind sofort "
            "<b>bereit</b>; bei „Parameter fehlt“ steht unter der Liste, was zu tun ist. Eine neue Version übernimmt "
            "die Parameter der vorigen.")
        box.pack_start(intro, False, False, 0)

        bar = Gtk.Box(spacing=6)
        self.btn_file = Gtk.Button(label="Ins Tool laden …")
        self.btn_file.set_tooltip_text("Installer-Datei (.exe, .msi, .msp, .msu, .msix, .appx …) von hier, einem "
                                       "USB-Datenträger oder dem NAS in die Software-Bibliothek kopieren")
        self.btn_file.connect("clicked", lambda _b: self.on_choose(False))
        bar.pack_start(self.btn_file, False, False, 0)
        self.btn_folder = Gtk.Button(label="Ordner laden …")
        self.btn_folder.set_tooltip_text("Ganzen Ordner kopieren – für Installer, die ihre Dateien daneben brauchen "
                                         "(z. B. YSUSB_V213_Win mit setup.exe)")
        self.btn_folder.connect("clicked", lambda _b: self.on_choose(True))
        bar.pack_start(self.btn_folder, False, False, 0)
        drop = Gtk.Label(xalign=0)
        drop.set_markup("<small>oder Dateien und Ordner hierher ziehen</small>")
        drop.get_style_context().add_class("status-idle")
        bar.pack_start(drop, False, False, 6)
        self.search = Gtk.SearchEntry(placeholder_text="Suchen …", width_chars=22)
        self.search.connect("search-changed", lambda _e: self.filter.refilter())
        bar.pack_end(self.search, False, False, 0)
        box.pack_start(bar, False, False, 0)

        # Laden: Fortschritt mit Abbrechen (nur sichtbar, solange geladen wird)
        self.load_box = Gtk.Box(spacing=6, no_show_all=True)
        self.bar = Gtk.ProgressBar(show_text=True, hexpand=True)
        self.load_box.pack_start(self.bar, True, True, 0)
        self.btn_cancel = Gtk.Button(label="Abbrechen")
        self.btn_cancel.connect("clicked", lambda _b: self._abort())
        self.load_box.pack_start(self.btn_cancel, False, False, 0)
        self.bar.show()
        self.btn_cancel.show()
        box.pack_start(self.load_box, False, False, 0)
        self.load_file = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.START, no_show_all=True)
        self.load_file.get_style_context().add_class("status-idle")
        box.pack_start(self.load_file, False, False, 0)

        self.store = Gtk.ListStore(str, str, str, str, str, str, str, str, GObject.TYPE_INT64, str, bool, str)
        self.filter = self.store.filter_new()
        self.filter.set_visible_func(self._visible)
        self.sorted = Gtk.TreeModelSort(model=self.filter)
        self.view = Gtk.TreeView(model=self.sorted, tooltip_column=self.C_TIP)
        columns = (("Programm", self.C_PROG, True, "program"), ("Version", self.C_VER, False, "version"),
                   ("Hersteller", self.C_PUB, False, "publisher"),
                   ("Typ", self.C_TYPE, False, None), ("Parameter", self.C_ARGS, True, "args"),
                   ("Rückgabewerte", self.C_CODES, False, "exit_codes"), ("Status", self.C_STATUS, False, None),
                   ("Grösse", self.C_SIZE, False, None))
        for title, index, expand, field_name in columns:
            cell = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, cell, text=index)
            if field_name:
                cell.connect("edited", self._on_edited, field_name)
                if field_name in ("args", "exit_codes"):
                    column.add_attribute(cell, "editable", self.C_EDIT)
                else:
                    cell.set_property("editable", True)
            if expand:
                cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            column.set_expand(expand)
            column.set_resizable(True)
            column.set_sort_column_id(self.C_BYTES if index == self.C_SIZE else index)
            self.view.append_column(column)
        self.view.get_selection().connect("changed", lambda _s: self._update_buttons())
        self.view.connect("key-press-event", self._on_key)
        self.view.connect("button-press-event", self._on_button)
        box.pack_start(scrolled(self.view), True, True, 0)
        # Angaben zum markierten Eintrag: Typ, Hersteller, Installer und was bei „Parameter fehlt“ zu tun ist
        self.detail = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.pack_start(self.detail, False, False, 0)
        tip = Gtk.Label(xalign=0, wrap=True)
        tip.set_markup("<small>Programm, Version, Hersteller, Parameter und Rückgabewerte: Zeile markieren und in die "
                       "Zelle klicken. Art (still installieren, nur kopieren, nur von Hand) und Installer im Ordner: "
                       "<b>Bearbeiten …</b> · Erkennung erneut anwenden: <b>Neu erkennen</b> (auch Rechtsklick)</small>")
        tip.get_style_context().add_class("status-idle")
        box.pack_start(tip, False, False, 0)

        bottom = Gtk.Box(spacing=6)
        self.btn_edit = Gtk.Button(label="Bearbeiten …")
        self.btn_edit.connect("clicked", lambda _b: self.on_edit())
        bottom.pack_start(self.btn_edit, False, False, 0)
        self.btn_redetect = Gtk.Button(label="Neu erkennen")
        self.btn_redetect.set_tooltip_text("Installer-Typ, Parameter, Name, Version und Hersteller erneut aus der Datei "
                                           "lesen – z. B. für Einträge, die vor einer neueren Erkennung geladen wurden")
        self.btn_redetect.connect("clicked", lambda _b: self.on_redetect())
        bottom.pack_start(self.btn_redetect, False, False, 0)
        self.btn_delete = Gtk.Button(label="Löschen")
        self.btn_delete.connect("clicked", lambda _b: self.on_delete())
        bottom.pack_start(self.btn_delete, False, False, 0)
        refresh = Gtk.Button(label="Aktualisieren")
        refresh.connect("clicked", lambda _b: self.reload())
        bottom.pack_start(refresh, False, False, 0)
        self.status = Gtk.Label(xalign=0, wrap=True)
        bottom.pack_start(self.status, True, True, 6)
        close = Gtk.Button(label="Schliessen")
        close.connect("clicked", lambda _b: self.close())
        bottom.pack_end(close, False, False, 0)
        box.pack_start(bottom, False, False, 0)
        self.add(box)

        # Ziehen und Ablegen aus dem Dateimanager (ganzes Fenster)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new(URI_TARGET, Gtk.TargetFlags.OTHER_APP, 0)],
                           Gdk.DragAction.COPY)
        self.connect("drag-data-received", self._on_drop)
        self.show_all()
        self._update_buttons()
        self.reload()

    # ---------- Liste ----------

    def _visible(self, model, it, _data) -> bool:
        text = self.search.get_text().strip().lower()
        if not text:
            return True
        row = model[it]
        return text in " ".join(str(row[i]) for i in (self.C_NAME, self.C_PROG, self.C_VER, self.C_PUB, self.C_TYPE,
                                                      self.C_ARGS, self.C_STATUS)).lower()

    def reload(self, select: str = "", message: str = "") -> None:
        """Liste neu lesen; message (z. B. „„VLC“ geladen: bereit“) bleibt danach vor der Zählung stehen."""
        self.select_after = select or self.select_after
        self.message = message or self.message
        self.status.set_text(" · ".join(t for t in (self.message, "Software-Bibliothek wird gelesen …") if t))
        run_async(lambda: software.scan(self.root), self._loaded)

    def _loaded(self, result) -> None:
        if self.closing:
            return
        if isinstance(result, Exception):
            self.status.set_text(f"Nicht lesbar: {result}")
            return
        self.entries = result
        keep = self.select_after or self._selected_name()
        self.select_after = ""
        self.store.clear()
        for e in result:
            tip = [e.name + (f" · Installer: {e.installer}" if e.installer else "")]
            if e.note:
                tip.append(e.note)
            if e.loaded_from:
                tip.append(f"Geladen aus {e.loaded_from}")
            install = e.mode == software.INSTALL
            self.store.append([e.name, e.program, e.version, e.kind_label, e.args if install else "–",
                               ", ".join(str(c) for c in e.exit_codes) if install else "–", e.status,
                               nas.format_size(e.size), e.size, "\n".join(tip), install, e.publisher])
        counts = {s: sum(1 for e in result if e.status == s) for s in (software.READY, software.MISSING)}
        summary = (f"{len(result)} Einträge · {counts[software.READY]} bereit · "
                   f"{counts[software.MISSING]} mit fehlenden Parametern" if result else
                   "Noch keine Programme – „Ins Tool laden …“ oder „Ordner laden …“.")
        message, self.message = self.message, ""
        self.status.set_text(" · ".join(t for t in (message, summary) if t))
        if keep:
            self._select(keep)
        self._update_buttons()

    def _select(self, name: str) -> None:
        for row in self.sorted:
            if row[self.C_NAME] == name:
                self.view.get_selection().select_iter(row.iter)
                self.view.scroll_to_cell(row.path, None, False, 0, 0)
                return

    def _selected_name(self) -> str:
        model, it = self.view.get_selection().get_selected()
        return model[it][self.C_NAME] if it is not None else ""

    def _selected_entry(self) -> software.Entry | None:
        return software.find(self.entries, self._selected_name())

    def _update_buttons(self) -> None:
        entry = self._selected_entry()
        has = entry is not None
        self.btn_edit.set_sensitive(has)
        self.btn_redetect.set_sensitive(has and not self.running)
        self.btn_delete.set_sensitive(has and not self.running)
        self.detail.set_markup(detail_markup(entry) if has else "")

    def _on_key(self, _view, event) -> bool:
        if event.keyval == Gdk.KEY_Delete:
            self.on_delete()
            return True
        return False

    def _on_button(self, view, event) -> bool:
        """Rechtsklick auf eine Zeile: Kontextmenü Bearbeiten, Neu erkennen, Löschen."""
        if event.type != Gdk.EventType.BUTTON_PRESS or event.button != 3:
            return False
        hit = view.get_path_at_pos(int(event.x), int(event.y))
        if hit is None:
            return False
        view.get_selection().select_path(hit[0])
        menu = Gtk.Menu()
        for label, action, enabled in (("Bearbeiten …", self.on_edit, True),
                                       ("Neu erkennen", self.on_redetect, not self.running),
                                       ("Löschen", self.on_delete, not self.running)):
            item = Gtk.MenuItem(label=label)
            item.set_sensitive(enabled)
            item.connect("activate", lambda _i, a=action: a())
            menu.append(item)
        menu.show_all()
        menu.attach_to_widget(view, None)
        menu.popup_at_pointer(event)
        self.menu = menu                    # Verweis halten, solange das Menü offen ist
        return True

    def _on_edited(self, _cell, path: str, text: str, field_name: str) -> None:
        name = self.sorted[path][self.C_NAME]
        entry = software.find(self.entries, name)
        if entry is None:
            return
        current = {"program": entry.program, "version": entry.version, "publisher": entry.publisher,
                   "args": entry.args, "exit_codes": ", ".join(str(c) for c in entry.exit_codes)}[field_name]
        if text.strip() == current:
            return
        self._save(name, {field_name: text})

    def _save(self, name: str, values: dict) -> None:
        def done(result) -> None:
            if isinstance(result, Exception):
                confirm_error(self, str(result), "Nicht gespeichert")
            self.reload(select=name)
        run_async(lambda: software.update(self.root, name, **values), done)

    def on_edit(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        dlg = SoftwareEditDialog(self, entry)
        while dlg.run() == Gtk.ResponseType.OK:
            try:
                software.update(self.root, entry.name, **dlg.values())
            except (software.SoftwareError, OSError) as e:
                confirm_error(dlg, str(e), "Nicht gespeichert")
                continue
            break
        dlg.destroy()
        self.reload(select=entry.name)

    def on_redetect(self) -> None:
        """„Neu erkennen“ (Ä-043): von Hand geänderte Angaben erst nach Rückfrage überschreiben."""
        entry = self._selected_entry()
        if entry is None or self.running:
            return
        overwrite = bool(entry.meta.get("edited"))
        if overwrite and not confirm(
                self, f"„{entry.label}“ neu erkennen?",
                "Die Angaben dieses Eintrags wurden von Hand geändert (z. B. Parameter, Rückgabewerte, Name oder "
                "Art). Neu erkennen ersetzt sie durch das Ergebnis der Erkennung – von Hand eingetragene Parameter "
                "gehen dabei verloren.", ok_label="Überschreiben"):
            return

        def done(result) -> None:
            if isinstance(result, Exception):
                confirm_error(self, str(result), "Nicht neu erkannt")
                self.reload(select=entry.name)
                return
            self.reload(select=result.name,
                        message=f"„{result.label}“ neu erkannt: {result.kind_label}, {result.status}")
        self.status.set_text("Wird neu erkannt …")
        run_async(lambda: software.redetect(self.root, entry.name, overwrite_edited=overwrite), done)

    def on_delete(self) -> None:
        entry = self._selected_entry()
        if entry is None or self.running:
            return
        if not confirm(self, f"„{entry.label}“ aus der Software-Bibliothek löschen?",
                       f"Der Eintrag „{entry.name}“ mit allen Dateien ({nas.format_size(entry.size)}) wird aus der "
                       "Bibliothek gelöscht. Gespeicherte Auswahlen (Automatisierung, Vorlagen) nehmen danach eine andere "
                       "Version desselben Programms oder melden es als fehlend."):
            return

        def done(result) -> None:
            if isinstance(result, Exception):
                confirm_error(self, str(result), "Nicht gelöscht")
                self.reload()
            else:
                self.reload(message=f"„{entry.label}“ gelöscht")
        self.status.set_text("Wird gelöscht …")
        run_async(lambda: software.delete(self.root, entry.name), done)

    # ---------- Laden ----------

    def on_choose(self, folder: bool) -> None:
        dlg = Gtk.FileChooserDialog(title="Ordner laden" if folder else "Ins Tool laden", transient_for=self,
                                    action=Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Laden", Gtk.ResponseType.OK)
        dlg.set_select_multiple(True)
        if not folder:
            flt = Gtk.FileFilter()
            flt.set_name("Installer (" + ", ".join(software.INSTALLER_EXT) + ")")
            for ext in software.INSTALLER_EXT:
                # Gross/Klein egal: *.[mM][sS][iI]
                flt.add_pattern("*." + "".join(f"[{c.lower()}{c.upper()}]" for c in ext[1:]))
            dlg.add_filter(flt)
        dlg.set_current_folder(str(Path.home()))
        paths = dlg.get_filenames() if dlg.run() == Gtk.ResponseType.OK else []
        dlg.destroy()
        self.enqueue(paths)

    def _on_drop(self, _w, _ctx, _x, _y, selection, _info, _time) -> None:
        # Gtk.DestDefaults.ALL beendet das Ziehen selbst (kein drag_finish hier)
        paths = [GLib.filename_from_uri(u)[0] for u in selection.get_uris() if u.startswith("file://")]
        self.enqueue(paths)

    def enqueue(self, paths: list[str]) -> None:
        if not paths:
            return
        self.queue += list(paths)
        if not self.running:
            self._next()

    def _set_running(self, on: bool) -> None:
        self.running = on
        main_copies = getattr(self.parent_window, "copies", None)
        if isinstance(main_copies, set):
            (main_copies.add if on else main_copies.discard)(self)
        for w in (self.load_box, self.load_file):
            w.set_visible(on)
        self.btn_cancel.set_sensitive(on)
        self._update_buttons()

    def _next(self) -> None:
        if self.closing or not self.queue:
            self._set_running(False)
            if self.closing:
                self.destroy()
            return
        path = self.queue.pop(0)
        self.cancel = threading.Event()
        self._set_running(True)
        self.bar.set_fraction(0)
        self.bar.set_text(f"{Path(path).name} wird geprüft …")
        self.load_file.set_text(path)
        run_async(lambda: software.inspect(path, self.root), self._inspected)

    def _inspected(self, src) -> None:
        if isinstance(src, Exception):
            confirm_error(self, str(src), "Nicht geladen")
            self._next()
            return
        if self.closing:
            self._next()
            return
        installer = None
        if src.is_dir and not src.installer and len(src.candidates) > 1:
            installer = self._ask_installer(src)
            if installer is None:          # Abbrechen
                self.status.set_text(f"„{src.path.name}“ nicht geladen")
                self._next()
                return
        self.bar.set_text(f"{src.path.name} wird in die Software-Bibliothek kopiert …")
        self.started = time.monotonic()

        def work():
            return software.load(self.root, src, lambda d, t, f: GLib.idle_add(self._progress, d, t, f),
                                 self.cancel, installer)

        run_async(work, lambda result: self._loaded_one(src, result))

    def _ask_installer(self, src: software.Source) -> str | None:
        """Ordner mit mehreren Installern: welcher ist es? „“ = später wählen (bzw. „nur kopieren“)."""
        dlg = Gtk.Dialog(title="Installer wählen", transient_for=self, modal=True)
        dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Laden", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        label = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
        label.set_text(f"Im Ordner „{src.path.name}“ liegen mehrere Installer. Welche Datei installiert das Programm? "
                       "Bei einer Sammlung von Werkzeugen „(keiner – später festlegen)“ wählen und danach unter "
                       "„Bearbeiten …“ die Art „Nur kopieren“ setzen.")
        box.pack_start(label, False, False, 0)
        combo = Gtk.ComboBoxText()
        combo.append("", "(keiner – später festlegen)")
        for c in src.candidates:
            combo.append(c, c)
        combo.set_active_id(src.candidates[0])
        box.pack_start(combo, False, False, 0)
        dlg.get_content_area().add(box)
        dlg.show_all()
        answer = combo.get_active_id() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        return answer if answer is None else (answer or "")

    def _progress(self, done: int, total: int, current: str) -> bool:
        frac = done / total if total else 1.0
        self.bar.set_fraction(frac)
        self.bar.set_text(f"{frac * 100:.0f} %  ·  {rate_text(done, total, self.started)}")
        if current:
            self.load_file.set_text(current)
        return False

    def _loaded_one(self, src: software.Source, result) -> None:
        if isinstance(result, Exception):
            if self.cancel.is_set():
                self.status.set_text(f"Laden von „{src.path.name}“ abgebrochen – in der Bibliothek bleibt nichts "
                                     "Halbes zurück")
                self.queue.clear()
            else:
                confirm_error(self, str(result), f"„{src.path.name}“ nicht geladen")
            self._next()
            return
        e = result.entry
        if result.duplicate:
            text = (f"„{src.path.name}“ ist schon in der Bibliothek (als „{e.label}“, {e.name}) – "
                    "nicht doppelt abgelegt")
        else:
            extra = f" – Parameter von „{e.adopted_from}“ übernommen" if e.adopted_from else ""
            text = f"„{e.label}“ geladen: {e.status}{extra}"
        self.status.set_text(text)
        if not self.closing:
            self.reload(select=e.name, message=text)   # Meldung bleibt nach dem Neulesen vor der Zählung
        self._next()

    def _abort(self) -> None:
        self.cancel.set()
        self.queue.clear()
        self.btn_cancel.set_sensitive(False)
        self.bar.set_text("Wird abgebrochen … (aufräumen)")

    def _on_delete(self, *_a) -> bool:
        """✕ während des Ladens = Abbrechen (Fenster schliesst sich, sobald aufgeräumt ist)."""
        if self.running:
            self.closing = True
            self._abort()
            return True
        return False


class SoftwareEditDialog(Gtk.Dialog):
    """Ein Programm: Name, Version, Art, Installer (Ordner), Parameter, Rückgabewerte."""

    def __init__(self, parent: Gtk.Window, entry: software.Entry):
        super().__init__(title=f"Software – {entry.name}", transient_for=parent, modal=True)
        self.entry = entry
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.add_button("Speichern", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=8, row_spacing=6, margin=12)
        r = 0

        def row(label: str, widget: Gtk.Widget) -> None:
            nonlocal r
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            grid.attach(widget, 1, r, 1, 1)
            r += 1

        self.program = Gtk.Entry(text=entry.program, width_chars=40)
        row("Programm", self.program)
        self.version = Gtk.Entry(text=entry.version)
        row("Version", self.version)
        self.publisher = Gtk.Entry(text=entry.publisher, width_chars=40)
        row("Hersteller", self.publisher)
        self.mode = Gtk.ComboBoxText()
        self.mode.append(software.INSTALL, "Still installieren")
        if entry.is_dir:
            self.mode.append(software.COPY, "Nur kopieren (Ordner auf den Desktop, Software\\…)")
        self.mode.append(software.MANUAL, "Nur von Hand (lässt sich nicht still installieren)")
        self.mode.set_active_id(entry.mode)
        self.mode.connect("changed", lambda _c: self._update())
        row("Art", self.mode)
        self.installer = Gtk.ComboBoxText()
        if entry.is_dir:
            self.installer.append("", "(keiner gewählt)")
            for c in entry.candidates:
                self.installer.append(c, c)
            self.installer.set_active_id(entry.installer if entry.installer in entry.candidates else "")
            row("Installer", self.installer)
        suggestion = entry.detected_args
        self.detected = Gtk.Label(label=entry.detected_label + (f" – Vorschlag: {suggestion}" if suggestion else ""),
                                  xalign=0, wrap=True, max_width_chars=70, selectable=True)
        row("Erkannt", self.detected)
        self.args = Gtk.Entry(text=entry.args, width_chars=50, placeholder_text="z. B. /S oder /quiet /norestart")
        self.args.set_tooltip_text("Parameter für die stille Installation (ohne Dateinamen). Bei MSI ergänzt das Tool "
                                   "„msiexec /i <Datei>“. {ordner} steht für den Ordner des Installers, z. B. "
                                   "/f1\"{ordner}\\setup.iss\".")
        row("Parameter", self.args)
        self.codes = Gtk.Entry(text=", ".join(str(c) for c in entry.exit_codes))
        self.codes.set_tooltip_text("Rückgabewerte, die als erfolgreich gelten (3010 = Neustart nötig – das Gerät "
                                    "startet nach dem letzten Programm einmal neu)")
        row("Erfolgreich bei Rückgabewert", self.codes)
        if entry.loaded_from:
            row("Geladen aus", Gtk.Label(label=entry.loaded_from, xalign=0, wrap=True, max_width_chars=60,
                                         selectable=True))
        note = Gtk.Label(label=entry.note, xalign=0, wrap=True, max_width_chars=70)
        note.get_style_context().add_class("status-idle")
        grid.attach(note, 0, r, 2, 1)
        self.get_content_area().add(grid)
        self.show_all()
        self._update()

    def _update(self) -> None:
        install = self.mode.get_active_id() == software.INSTALL
        for w in (self.args, self.codes, self.installer):
            w.set_sensitive(install)

    def values(self) -> dict:
        out = {"program": self.program.get_text(), "version": self.version.get_text(),
               "publisher": self.publisher.get_text(), "mode": self.mode.get_active_id() or software.INSTALL}
        if out["mode"] == software.INSTALL:
            out.update(args=self.args.get_text(), exit_codes=self.codes.get_text())
            if self.entry.is_dir:
                out["installer"] = self.installer.get_active_id() or ""
        return out


def detail_markup(entry: software.Entry) -> str:
    """Zeile unter der Liste: „Typ: Qt Installer Framework · Hersteller: … · Installer: …“, darunter bei
    „Parameter fehlt“ der Hinweis, was zu tun ist (Ä-043)."""
    esc = GLib.markup_escape_text
    parts = [f"<b>Typ:</b> {esc(entry.kind_label)}"]
    if entry.publisher:
        parts.append(f"<b>Hersteller:</b> {esc(entry.publisher)}")
    if entry.installer:
        parts.append(f"<b>Installer:</b> {esc(entry.installer)}")
    parts.append(f"<b>Status:</b> {esc(entry.status)}")
    text = " · ".join(parts)
    if entry.hint:
        text += f"\n<b>Was tun:</b> {esc(entry.hint)}"
    elif entry.note:
        text += f"\n{esc(entry.note)}"
    return text


def describe_selection(entries: list[software.Entry]) -> str:
    """Für Rückfragen und Log: „VLC media player 3.0.24, … (120 MB)“."""
    return f"{software.summary(entries)} ({nas.format_size(software.total_size(entries))})"
