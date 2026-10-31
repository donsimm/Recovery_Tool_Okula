"""Menü → „Inventar exportieren …“ und Rechtsklick auf einen Geräte-Ordner (I-013)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from okula_recovery import inventory_export as ie  # noqa: E402
from okula_recovery.uikit import confirm_error, open_url, run_async, scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow


def _hint(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=80)
    lbl.get_style_context().add_class("status-idle")
    return lbl


def default_dir() -> str:
    docs = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
    return docs if docs and Path(docs).is_dir() else str(Path.home())


class InventoryExportDialog(Gtk.Dialog):
    """Umfang (alle / Ordner / markierte Geräte), Format (CSV, PDF je Ordner oder alle in einem), Windows-Schlüssel, Ziel."""

    def __init__(self, main: "MainWindow", folder: str | None = None, marked: set[str] | None = None):
        super().__init__(title="Inventar exportieren", transient_for=main, modal=True)
        self.main = main
        self.set_default_size(620, 560)
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.ok = self.add_button("Exportieren", Gtk.ResponseType.OK)
        self.ok.get_style_context().add_class("suggested-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        devs = list(main.store.devices.values())

        box.pack_start(self._title("Welche Geräte?"), False, False, 0)
        self.r_all = Gtk.RadioButton.new_with_label(None, f"Alle Geräte ({len(devs)})")
        box.pack_start(self.r_all, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.r_folder = Gtk.RadioButton.new_with_label_from_widget(self.r_all, "Ordner (mit Unterordnern):")
        row.pack_start(self.r_folder, False, False, 0)
        self.folder = Gtk.ComboBoxText()
        self.folder.append(ie.UNSORTED, ie.UNSORTED)
        for f in main.store.folders:
            self.folder.append(f, f.replace("/", " › "))
        self.folder.set_active_id(folder if folder in main.store.folders else
                                  (main.store.folders[0] if main.store.folders else ie.UNSORTED))
        row.pack_start(self.folder, True, True, 0)
        box.pack_start(row, False, False, 0)
        self.r_marked = Gtk.RadioButton.new_with_label_from_widget(self.r_all, "Markierte Geräte:")
        box.pack_start(self.r_marked, False, False, 0)

        # Liste zum Markieren: Häkchen, Name, Ordner, ID
        self.list = Gtk.ListStore(bool, str, str, str)
        for d in sorted(devs, key=lambda d: (d.folder.lower(), d.name.lower())):
            self.list.append([d.id in (marked or set()), d.name, d.folder or "Neu / nicht einsortiert", d.id])
        view = Gtk.TreeView(model=self.list, headers_visible=True)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_toggle)
        view.append_column(Gtk.TreeViewColumn("", toggle, active=0))
        for i, title in ((1, "Gerät"), (2, "Ordner")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_expand(i == 1)
            view.append_column(col)
        self.marked_view = scrolled(view)
        self.marked_view.set_size_request(-1, 150)
        box.pack_start(self.marked_view, True, True, 0)

        box.pack_start(self._title("Format"), False, False, 0)
        fmt = Gtk.Box(spacing=16)
        self.csv = Gtk.CheckButton(label="CSV (Excel, alle gewählten Geräte in einer Datei)", active=True)
        self.pdf = Gtk.CheckButton(label="PDF:", active=ie.pdf_available())
        self.pdf_folders = Gtk.RadioButton.new_with_label(None, "je Ordner eine Datei")
        self.pdf_single = Gtk.RadioButton.new_with_label_from_widget(self.pdf_folders, "alle Geräte in einer Datei")
        if not ie.pdf_available():
            for w in (self.pdf, self.pdf_folders, self.pdf_single):
                w.set_sensitive(False)
            self.pdf.set_active(False)
            self.pdf.set_tooltip_text("PDF-Bibliothek fehlt – install.sh ausführen (python3-reportlab)")
        fmt.pack_start(self.csv, False, False, 0)
        box.pack_start(fmt, False, False, 0)
        pdf_row = Gtk.Box(spacing=12)
        for w in (self.pdf, self.pdf_folders, self.pdf_single):
            pdf_row.pack_start(w, False, False, 0)
        box.pack_start(pdf_row, False, False, 0)
        self.no_key = Gtk.CheckButton(label="Windows-Schlüssel nicht exportieren", active=True)
        self.no_key.set_tooltip_text("Ausgeschaltet: nur maskiert (XXXXX-XXXXX-XXXXX-XXXXX-ABCDE), nie vollständig")
        box.pack_start(self.no_key, False, False, 0)

        box.pack_start(self._title("Speichern in"), False, False, 0)
        self.target = Gtk.FileChooserButton(title="Zielordner wählen", action=Gtk.FileChooserAction.SELECT_FOLDER)
        self.target.set_current_folder(default_dir())
        box.pack_start(self.target, False, False, 0)
        box.pack_start(_hint("Spalten: Name, Ordner, Hersteller, Modell, Seriennummer, CPU, RAM, Disks (Modell, "
                             "Grösse, SMART), OS, Win-11-tauglich, Garantie bis, zuletzt verbunden, letztes Image, "
                             "letztes Backup. Letztes Image/Backup nur mit verbundenem NAS."), False, False, 0)

        for w in (self.r_all, self.r_folder, self.r_marked):
            w.connect("toggled", lambda _w: self._update())
        for w in (self.csv, self.pdf):
            w.connect("toggled", lambda _w: self._update())
        self.folder.connect("changed", lambda _c: self._update())
        if folder is not None:
            self.r_folder.set_active(True)
        elif marked:
            self.r_marked.set_active(True)
        self.get_content_area().add(box)
        self.show_all()
        self._update()

    @staticmethod
    def _title(text: str) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
        return lbl

    def _on_toggle(self, _cell, path) -> None:
        self.list[path][0] = not self.list[path][0]
        self.r_marked.set_active(True)
        self._update()

    def scope(self) -> tuple[str, str, set[str]]:
        if self.r_folder.get_active():
            fid = self.folder.get_active_id() or ie.UNSORTED
            return "folder", "" if fid == ie.UNSORTED else fid, set()
        if self.r_marked.get_active():
            return "marked", "", {r[3] for r in self.list if r[0]}
        return "all", "", set()

    def chosen(self) -> list:
        kind, folder, ids = self.scope()
        return ie.select(self.main.store.devices.values(), kind, folder, ids)

    def label(self) -> str:
        """Titel für CSV und Einzel-PDF: Ordnername wie in der Liste, „Auswahl“ oder „Alle Geräte“."""
        kind, folder, _ids = self.scope()
        if kind == "folder":
            return ie.folder_title(folder)
        return "Auswahl" if kind == "marked" else "Alle Geräte"

    def _update(self) -> None:
        for w in (self.pdf_folders, self.pdf_single):
            w.set_sensitive(self.pdf.get_active())
        n = len(self.chosen())
        self.ok.set_sensitive(n > 0 and (self.csv.get_active() or self.pdf.get_active()))
        self.ok.set_label(f"Exportieren ({n} Gerät{'e' if n != 1 else ''})")

    def run_export(self) -> None:
        if self.run() != Gtk.ResponseType.OK:
            self.destroy()
            return
        devs, label = self.chosen(), self.label()
        target = Path(self.target.get_filename() or default_dir())
        fmt_csv, fmt_pdf, with_key = self.csv.get_active(), self.pdf.get_active(), not self.no_key.get_active()
        single = self.pdf_single.get_active()
        self.destroy()
        main = self.main
        root = main._nas_root()
        saved = list(main._backups.values())
        main.status(f"Inventar wird exportiert ({len(devs)} Geräte) …")

        def work():
            try:
                images = ie.latest_images(root, devs)
            except OSError:
                images = {}
            rows = ie.build(devs, images, ie.latest_backups(saved, devs), with_key)
            return ie.export(target, devs, rows, label, fmt_csv, fmt_pdf, with_key, pdf_single=single)

        def done(result) -> None:
            if isinstance(result, Exception):
                confirm_error(main, f"Inventar nicht exportiert: {result}")
                return
            main.status(f"Inventar exportiert: {len(result)} Datei{'en' if len(result) != 1 else ''} in {target}")
            show_result(main, target, result)
        run_async(work, done)


def show_result(parent: Gtk.Window, target: Path, files: list[Path]) -> None:
    dlg = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.NONE, text="Inventar exportiert")
    dlg.format_secondary_text("\n".join(f.name for f in files) + f"\n\nOrdner: {target}")
    dlg.add_button("Ordner öffnen", 1)
    dlg.add_button("OK", Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)
    if dlg.run() == 1:
        open_url(parent, target.as_uri())
    dlg.destroy()
