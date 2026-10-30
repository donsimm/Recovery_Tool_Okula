"""Gemeinsame GTK-Hilfen für Hauptfenster und Dialoge."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

LOGO_COLOR = b"#0b1213"  # Füllfarbe im Original-SVG


def svg_pixbuf(path: Path, height: int, color: str | None = None) -> GdkPixbuf.Pixbuf | None:
    """Rendert ein SVG auf die gewünschte Höhe, optional mit anderer Füllfarbe (dunkles Theme)."""
    try:
        data = path.read_bytes()
        if color:
            data = data.replace(LOGO_COLOR, color.encode())
        loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
        loader.connect("size-prepared", lambda ld, w, h: ld.set_size(max(1, round(w * height / h)), height))
        loader.write(data)
        loader.close()
        return loader.get_pixbuf()
    except (OSError, GLib.Error):
        return None  # ohne SVG-Loader (librsvg2-common) eben ohne Logo


def rgba_hex(c: Gdk.RGBA) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(round(v * 255) for v in (c.red, c.green, c.blue)))


def confirm_error(parent: Gtk.Window, text: str) -> None:
    dlg = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.CLOSE, text="Aktion fehlgeschlagen")
    dlg.format_secondary_text(text)
    dlg.run()
    dlg.destroy()


def run_async(work, done):
    """Führt work() im Hintergrund aus und ruft done(result) im GTK-Thread auf."""
    def target():
        try:
            result = work()
        except Exception as e:  # Fehler sichtbar machen statt Thread still sterben lassen
            result = e
        GLib.idle_add(done, result)
    threading.Thread(target=target, daemon=True).start()


def make_tree(columns: list[tuple[str, int]], store: Gtk.ListStore, expand: int = 1) -> Gtk.TreeView:
    """columns: (Titel, Spaltenindex im Store); Spaltenindex -1 = Status-Icon aus Spalte 0.

    Nur die Spalte `expand` füllt die Breite und kürzt mit „…“, die übrigen bleiben vollständig.
    """
    view = Gtk.TreeView(model=store)
    view.set_headers_clickable(True)
    for title, idx in columns:
        if idx < 0:
            cell = Gtk.CellRendererPixbuf()
            col = Gtk.TreeViewColumn(title, cell, icon_name=0)
        else:
            cell = Gtk.CellRendererText()
            if idx == expand:
                cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, cell, text=idx)
            col.set_resizable(True)
            col.set_expand(idx == expand)
            col.set_sort_column_id(idx)
        view.append_column(col)
    return view


def scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    sw.set_shadow_type(Gtk.ShadowType.IN)
    sw.add(child)
    return sw


def confirm(parent: Gtk.Window, title: str, text: str, ok_label: str = "Löschen") -> bool:
    dlg = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.WARNING,
                            buttons=Gtk.ButtonsType.NONE, text=title)
    dlg.format_secondary_text(text)
    dlg.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
    btn = dlg.add_button(ok_label, Gtk.ResponseType.OK)
    btn.get_style_context().add_class("destructive-action")
    dlg.set_default_response(Gtk.ResponseType.CANCEL)
    ok = dlg.run() == Gtk.ResponseType.OK
    dlg.destroy()
    return ok


def ask_text(parent: Gtk.Window, title: str, label: str, initial: str = "") -> str | None:
    dlg = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
    box.pack_start(Gtk.Label(label=label, xalign=0), False, False, 0)
    entry = Gtk.Entry(text=initial, activates_default=True, width_chars=40)
    box.pack_start(entry, False, False, 0)
    dlg.get_content_area().add(box)
    dlg.show_all()
    entry.grab_focus()
    text = entry.get_text() if dlg.run() == Gtk.ResponseType.OK else None
    dlg.destroy()
    return text


def pane_title(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.get_style_context().add_class("pane-title")
    return lbl


def numbered_section(container: Gtk.Box, number: str, title: str, note: str = "") -> Gtk.Box:
    """Abschnitt wie im Reiter Automatisierung: Nummer im Kreis, fetter Titel, grauer Zusatz, Trennlinie davor;
    gibt die eingerückte Box für den Inhalt zurück."""
    if container.get_children():
        container.pack_start(Gtk.Separator(margin_top=6, margin_bottom=6), False, False, 0)
    head = Gtk.Box(spacing=10)
    num = Gtk.Label(label=number, valign=Gtk.Align.CENTER)
    num.get_style_context().add_class("step-number")
    head.pack_start(num, False, False, 0)
    text = Gtk.Label(xalign=0)
    text.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>" + (
        f"   <span foreground='#757575'>{GLib.markup_escape_text(note)}</span>" if note else ""))
    head.pack_start(text, False, False, 0)
    container.pack_start(head, False, False, 0)
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=36, margin_top=4)
    container.pack_start(inner, False, False, 0)
    return inner
