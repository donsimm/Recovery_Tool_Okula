"""Oberfläche „Software installieren“ (I-020): Auswahlliste mit Häkchen (OS installieren, Image zurückspielen,
Automatisierung) und Pflege des Katalogs (Reiter Dateien → „Software …“). Logik in software.py."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa: E402

from okula_recovery import nas, software  # noqa: E402
from okula_recovery.uikit import confirm_error, run_async, scrolled  # noqa: E402

TITLE = "Software installieren"
FOLDER_HINT = "Programme aus NAS: /Verteilen/Software – neue Dateien erscheinen von selbst (Pflege: Reiter Dateien → " \
              "„Software …“)."
NOT_FOUND = "fehlt im Ordner"


class SoftwareChooser(Gtk.Box):
    """Liste „Software installieren“ mit Häkchen, Suchfeld und Spalten Programm, Version, Grösse, Status.

    Nur Einträge mit Status „bereit“ oder „nur kopieren“ lassen sich ankreuzen; die Gesamtgrösse steht darunter."""

    # Häkchen, Programm, Version, Grösse (Text), Status, Name, wählbar, Grösse (Byte), Tooltip, sichtbar
    C_ON, C_PROG, C_VER, C_SIZE, C_STATUS, C_NAME, C_OK, C_BYTES, C_TIP, C_SHOW = range(10)

    def __init__(self, on_change: Callable[[], None] | None = None, height: int = 140):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.on_change = on_change or (lambda: None)
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
        """Katalog im Hintergrund lesen (legt fehlende Beschreibungen an) und Auswahl setzen."""
        self.nas_root = nas_root
        keep = list(selected) if selected is not None else self.selected()
        self.loaded = False          # bis der Ordner gelesen ist, gilt die gespeicherte Auswahl
        self.store.clear()
        if not nas_root:
            self.total.set_text("NAS nicht verbunden – keine Software wählbar")
            return
        self.total.set_text("Ordner Software wird gelesen …")
        run_async(lambda: software.scan(nas_root), lambda result: self._loaded(result, keep))

    def _loaded(self, result, keep: list[str]) -> None:
        if isinstance(result, Exception):
            self.total.set_text(f"Ordner Software nicht lesbar: {result}")
            return
        self.entries = result
        self.loaded = True
        chosen, missing, _renamed = software.resolve(self.entries, keep)
        names = {e.name for e in chosen}
        self.store.clear()
        for e in self.entries:
            tip = f"{e.name} · {e.kind_label}" + (f" · Parameter: {e.args}" if e.args and e.mode == software.INSTALL
                                                  else "") + (f"\n{e.note}" if e.note else "")
            self.store.append([e.name in names and e.selectable, e.program, e.version, nas.format_size(e.size),
                               e.status, e.name, e.selectable, e.size, tip, True])
        for name in missing:         # gespeicherte Auswahl, die es nicht mehr gibt – nur abwählbar
            self.store.append([True, name, "", "", NOT_FOUND, name, True, 0,
                               "Liegt nicht mehr im Ordner Software – wird übersprungen", True])
        if not self.entries and not missing:
            self.total.set_text("Keine Programme im Ordner Software")
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
                            "ersten Windows-Start still installiert (Protokoll C:\\Windows\\Temp\\okula-software.log)")


class SoftwareCatalogDialog(Gtk.Dialog):
    """Reiter Dateien → „Software …“: Programme mit Typ und Status, Parameter bearbeiten."""

    # Name, Programm, Version, Typ, Grösse, Status, Hinweis
    def __init__(self, parent: Gtk.Window, nas_root: str):
        super().__init__(title="Software – Programme für „Software installieren“", transient_for=parent, modal=False)
        self.nas_root = nas_root
        self.set_default_size(900, 480)
        self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda *_a: self.destroy())
        box = self.get_content_area()
        box.set_spacing(6)
        box.set_border_width(8)
        intro = Gtk.Label(xalign=0, wrap=True)
        intro.set_markup("Installer (<tt>.exe</tt>, <tt>.msi</tt>) und Programm-Ordner in NAS: /Verteilen/Software. "
                         "Erkannte Installer sind sofort <b>bereit</b>; bei „Parameter fehlt“ die Parameter für die "
                         "stille Installation hinterlegen. Eine neue Version übernimmt die Parameter der alten.")
        box.pack_start(intro, False, False, 0)
        self.store = Gtk.ListStore(str, str, str, str, str, str, str)
        self.view = Gtk.TreeView(model=self.store)
        for i, title in enumerate(("Programm", "Version", "Typ", "Grösse", "Status", "Hinweis"), start=1):
            column = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            column.set_resizable(True)
            column.set_expand(i in (1, 6))
            self.view.append_column(column)
        self.view.connect("row-activated", lambda *_a: self.on_edit())
        box.pack_start(scrolled(self.view), True, True, 0)
        bar = Gtk.Box(spacing=6)
        edit = Gtk.Button(label="Bearbeiten …")
        edit.connect("clicked", lambda _b: self.on_edit())
        bar.pack_start(edit, False, False, 0)
        refresh = Gtk.Button(label="Aktualisieren")
        refresh.connect("clicked", lambda _b: self.reload())
        bar.pack_start(refresh, False, False, 0)
        self.status = Gtk.Label(xalign=0, wrap=True)
        bar.pack_start(self.status, True, True, 0)
        box.pack_start(bar, False, False, 0)
        self.entries: list[software.Entry] = []
        self.show_all()
        self.reload()

    def reload(self) -> None:
        self.status.set_text("Ordner Software wird gelesen …")
        run_async(lambda: software.scan(self.nas_root), self._loaded)

    def _loaded(self, result) -> None:
        if isinstance(result, Exception):
            self.status.set_text(f"Nicht lesbar: {result}")
            return
        self.entries = result
        self.store.clear()
        for e in result:
            self.store.append([e.name, e.program, e.version, e.kind_label, nas.format_size(e.size), e.status, e.note])
        counts = {s: sum(1 for e in result if e.status == s) for s in (software.READY, software.MISSING)}
        self.status.set_text(f"{len(result)} Einträge · {counts[software.READY]} bereit · "
                             f"{counts[software.MISSING]} mit fehlenden Parametern" if result else
                             "Keine Programme im Ordner Software – Installer im Reiter Dateien hochladen.")

    def on_edit(self) -> None:
        model, it = self.view.get_selection().get_selected()
        if it is None:
            return
        entry = software.find(self.entries, model[it][0])
        if entry is None:
            return
        dlg = SoftwareEditDialog(self, entry)
        while dlg.run() == Gtk.ResponseType.OK:
            try:
                software.update(self.nas_root, entry.name, **dlg.values())
            except (software.SoftwareError, OSError) as e:
                confirm_error(dlg, str(e), "Nicht gespeichert")
                continue
            break
        dlg.destroy()
        self.reload()


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
        detected = software.KINDS.get(str(entry.meta.get("detected") or ""), software.KINDS[""])[0]
        suggestion = software.KINDS.get(entry.kind, software.KINDS[""])[1]
        self.detected = Gtk.Label(label=f"{detected}" + (f" – Vorschlag: {suggestion}" if suggestion else ""),
                                  xalign=0, wrap=True)
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
               "mode": self.mode.get_active_id() or software.INSTALL}
        if out["mode"] == software.INSTALL:
            out.update(args=self.args.get_text(), exit_codes=self.codes.get_text())
            if self.entry.is_dir:
                out["installer"] = self.installer.get_active_id() or ""
        return out


def describe_selection(entries: list[software.Entry]) -> str:
    """Für Rückfragen und Log: „VLC media player 3.0.24, … (120 MB)“."""
    return f"{software.summary(entries)} ({nas.format_size(software.total_size(entries))})"
