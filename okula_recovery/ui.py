"""GTK-3-Oberfläche: Menüleiste, links Maschinen im LAN, rechts NAS-Status mit Images und Dateien."""

from __future__ import annotations

import ipaddress
import os
import time
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from okula_recovery import (__version__, agentclient, archive, clonezilla, config, discovery, nas,  # noqa: E402
                            nasfiles, network)
from okula_recovery.image_dialog import ImageDialog  # noqa: E402
from okula_recovery.nas_dialog import NasDialog  # noqa: E402
from okula_recovery.restore_dialog import RestoreDialog  # noqa: E402
from okula_recovery.stick_dialog import StickDialog  # noqa: E402
from okula_recovery.uikit import (ask_text, confirm, confirm_error, make_tree, pane_title, rgba_hex,  # noqa: E402
                                  run_async, scrolled, svg_pixbuf)

ASSETS = Path(__file__).resolve().parent / "assets"
NAS_POLL = 30  # Sekunden zwischen den NAS-Statusabfragen

# Agent gilt als offline, wenn so lange kein Beacon kam, und verschwindet nach AGENT_REMOVE_AFTER
AGENT_TIMEOUT = 15
AGENT_REMOVE_AFTER = 60

ICON_ONLINE = "network-transmit-receive-symbolic"
ICON_OFFLINE = "network-offline-symbolic"
ICON_AGENT = "media-removable-symbolic"

CSS = b"""
.pane-title { font-weight: bold; font-size: 115%; }
.status-ok { color: #2e7d32; font-weight: bold; }
.status-fail { color: #c62828; font-weight: bold; }
.status-idle { color: #757575; }
.nas-bar { padding: 4px 8px; border-radius: 4px; background-color: alpha(currentColor, 0.06); }
"""


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Okula Recovery Tool")
        self.set_default_size(1280, 760)
        self.maximize()  # Arbeitsplatz-Tool: ganzer Bildschirm, F11 = Vollbild ohne Titelleiste
        self._fullscreen = False
        self.connect("key-press-event", self._on_key)
        self.connect("window-state-event", self._on_window_state)
        self.cfg = config.load()
        self.agents: dict[str, discovery.AgentInfo] = {}  # IP → letzte Meldung
        self.nas_state = ""          # letzter NAS-Zustand, um Wechsel zu erkennen
        self._nas_checking = False
        self.nas_dialog: NasDialog | None = None

        header = Gtk.HeaderBar(title="Recovery Tool", subtitle=f"Version {__version__}",
                               show_close_button=True)
        self.logo = Gtk.Image(margin_start=6, margin_end=6)
        header.pack_start(self.logo)
        header.connect("style-updated", self._update_logo)
        icon = svg_pixbuf(ASSETS / "okula-emblem.svg", 128)
        if icon:
            self.set_icon(icon)
            Gtk.Window.set_default_icon(icon)
        btn_stick = Gtk.Button(label="Agent-USB-Stick erstellen …")
        btn_stick.set_tooltip_text("USB-Stick wählen und mit Live-System und Agent vorbereiten")
        btn_stick.connect("clicked", lambda _b: StickDialog(self))
        header.pack_end(btn_stick)
        self.set_titlebar(header)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True)
        paned.pack1(self._build_machine_pane(), resize=True, shrink=False)
        paned.pack2(self._build_storage_pane(), resize=True, shrink=False)
        paned.set_position(760)

        self.statusbar = Gtk.Statusbar()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(self._build_menubar(), False, False, 0)
        root.pack_start(paned, True, True, 0)
        root.pack_start(self.statusbar, False, False, 0)
        self.add(root)

        self._load_manual_machines()
        self._start_listener()
        self._update_image_button()
        GLib.idle_add(self.refresh_nas_status, True)   # beim Start mit gespeicherten Zugangsdaten einhängen
        GLib.timeout_add_seconds(NAS_POLL, self.refresh_nas_status)

    # ---------- Menüleiste ----------

    def _build_menubar(self) -> Gtk.MenuBar:
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        self.menu_items: dict[str, Gtk.MenuItem] = {}

        def menu(title: str, entries) -> Gtk.MenuItem:
            top = Gtk.MenuItem.new_with_mnemonic(title)
            sub = Gtk.Menu()
            for entry in entries:
                if entry is None:
                    sub.append(Gtk.SeparatorMenuItem())
                    continue
                label, handler, shortcut = entry
                item = Gtk.MenuItem.new_with_mnemonic(label)
                item.connect("activate", lambda _i, h=handler: h())
                if shortcut:
                    key, mods = Gtk.accelerator_parse(shortcut)
                    item.add_accelerator("activate", accel, key, mods, Gtk.AccelFlags.VISIBLE)
                self.menu_items[label.replace("_", "")] = item
                sub.append(item)
            top.set_submenu(sub)
            return top

        bar = Gtk.MenuBar()
        bar.append(menu("_Menü", [
            ("_NAS-Verbindung …", self.open_nas_dialog, "<Control>n"),
            ("_Agent-USB-Stick erstellen …", lambda: StickDialog(self), None),
            None,
            ("_Beenden", self.close, "<Control>q"),
        ]))
        bar.append(menu("_Tools", [
            ("Netzwerk _scannen", lambda: self.on_scan(None), "F5"),
            ("Maschine _hinzufügen …", lambda: self.on_add_machine(None), None),
            None,
            ("_Disk-Image erstellen …", lambda: self.on_create_image(None), None),
            ("Image _zurückspielen …", lambda: self.on_restore_image(None), None),
            ("Maschine _herunterfahren", lambda: self.on_power_off(None), None),
            None,
            ("_Restore-Stick aus Image …", lambda: self.on_restore_stick(None), None),
            ("Images _aktualisieren", self.refresh_images, None),
        ]))
        bar.append(menu("_Hilfe", [
            ("_Tastenkürzel", self.show_shortcuts, "F1"),
            ("Ü_ber Okula Recovery Tool", self.show_about, None),
        ]))
        return bar

    def show_about(self) -> None:
        dlg = Gtk.AboutDialog(transient_for=self, modal=True, program_name="Okula Recovery Tool",
                              version=__version__, website="https://www.okula.ch", website_label="okula.ch",
                              comments="Disk-Images und Wiederherstellung von Maschinen im LAN – "
                                       "mit Agent-Stick, Restore-Stick und NAS.")
        logo = svg_pixbuf(ASSETS / "okula-logo.svg", 64)
        if logo:
            dlg.set_logo(logo)
        dlg.run()
        dlg.destroy()

    def show_shortcuts(self) -> None:
        text = ("Ctrl+N\tNAS-Verbindung\n"
                "F5\tNetzwerk scannen\n"
                "F11\tVollbild ein/aus\n"
                "Ctrl+Q\tBeenden\n\n"
                "Im Reiter „Dateien“:\n"
                "Doppelklick\tOrdner öffnen\n"
                "Backspace\tEine Ebene zurück\n"
                "F2\tUmbenennen\n"
                "Entf\tLöschen")
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                buttons=Gtk.ButtonsType.CLOSE, text="Tastenkürzel")
        dlg.format_secondary_text(text)
        dlg.run()
        dlg.destroy()

    def _update_logo(self, header: Gtk.HeaderBar) -> None:
        """Logo in der Textfarbe der Titelleiste, damit es auch im dunklen Theme lesbar ist."""
        color = rgba_hex(header.get_style_context().get_color(Gtk.StateFlags.NORMAL))
        if color != getattr(self, "_logo_color", None):
            self._logo_color = color
            self.logo.set_from_pixbuf(svg_pixbuf(ASSETS / "okula-logo.svg", 22, color))

    # ---------- rechte Seite: NAS-Status, Images, Dateien ----------

    def _build_storage_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        box.pack_start(pane_title("NAS – Images & Dateien"), False, False, 0)

        # Nur Status und freier Speicher; die Einrichtung steht unter Menü → NAS-Verbindung …
        bar = Gtk.Box(spacing=16)
        bar.get_style_context().add_class("nas-bar")
        self.nas_status = Gtk.Label(label="● NAS wird geprüft …", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.nas_status.get_style_context().add_class("status-idle")
        bar.pack_start(self.nas_status, True, True, 0)
        self.nas_space = Gtk.Label(label="", xalign=0)
        bar.pack_start(self.nas_space, False, False, 0)
        btn_settings = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON)
        btn_settings.set_relief(Gtk.ReliefStyle.NONE)
        btn_settings.set_tooltip_text("NAS-Verbindung einrichten (Menü → NAS-Verbindung …)")
        btn_settings.connect("clicked", lambda _b: self.open_nas_dialog())
        bar.pack_end(btn_settings, False, False, 0)
        box.pack_start(bar, False, False, 0)

        # Reiter: Images (Übersicht) und Dateien (Dateiverwaltung des NAS)
        self.nas_tabs = Gtk.Notebook()
        self.nas_tabs.append_page(self._build_images_tab(), Gtk.Label(label="Images"))
        self.nas_tabs.append_page(self._build_files_tab(), Gtk.Label(label="Dateien"))
        self.nas_tabs.connect("switch-page", lambda _n, _p, num: num == 1 and self.refresh_files())
        box.pack_start(self.nas_tabs, True, True, 0)
        return box

    # Spalten des Image-Baums
    C_ICON, C_NAME, C_TYPE, C_SIZE, C_DATE, C_BYTES, C_PATH, C_KIND, C_REL, C_AREA = range(10)
    DND_TARGET = "okula/archive-row"

    def _build_images_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        head = Gtk.Box(spacing=6)
        self.img_count = Gtk.Label(label="", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        head.pack_start(self.img_count, True, True, 0)
        self.img_buttons = {}
        for key, icon, tip, handler in (
                ("folder", "folder-new-symbolic", "Neuer Ordner (im gewählten Ordner, max. 3 Ebenen)",
                 self.on_new_archive_folder),
                ("rename", "document-edit-symbolic", "Ordner umbenennen", self.on_rename_archive_folder),
                ("delete", "user-trash-symbolic", "Löschen (Image bzw. leerer Ordner)", self.on_delete_image)):
            b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            b.set_tooltip_text(tip)
            b.connect("clicked", handler)
            head.pack_start(b, False, False, 0)
            self.img_buttons[key] = b
        self.btn_img_stick = Gtk.Button(label="Restore-Stick …", sensitive=False)
        self.btn_img_stick.set_tooltip_text("Bootfähigen USB-Stick mit diesem Image erstellen – spielt es nach "
                                            "Rückfrage ohne Netzwerk zurück")
        self.btn_img_stick.connect("clicked", self.on_restore_stick)
        head.pack_start(self.btn_img_stick, False, False, 0)
        btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_refresh.set_tooltip_text("Image-Liste neu laden")
        btn_refresh.connect("clicked", lambda _b: self.refresh_images())
        head.pack_start(btn_refresh, False, False, 0)
        box.pack_start(head, False, False, 0)

        # icon, Name, Typ, Grösse, Datum, Bytes, Pfad (Image), Art (unsorted/folder/image), Ordner-rel, Bereich
        self.image_store = Gtk.TreeStore(str, str, str, str, str, GObject.TYPE_INT64, str, str, str, str)
        view = Gtk.TreeView(model=self.image_store)
        col = Gtk.TreeViewColumn("Name")
        icon = Gtk.CellRendererPixbuf()
        col.pack_start(icon, False)
        col.add_attribute(icon, "icon-name", self.C_ICON)
        text = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col.pack_start(text, True)
        col.add_attribute(text, "text", self.C_NAME)
        col.set_expand(True)
        col.set_resizable(True)
        view.append_column(col)
        for title, idx in (("Typ", self.C_TYPE), ("Grösse", self.C_SIZE), ("Datum", self.C_DATE)):
            c = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            c.set_resizable(True)
            view.append_column(c)
        view.set_enable_tree_lines(True)
        view.get_selection().connect("changed", self._on_image_selected)
        view.connect("row-activated", self._on_image_activated)
        view.connect("button-press-event", self._on_image_button)
        # Ziehen mit der Maus: Images und Ordner in Ordner bzw. nach „Nicht einsortiert“
        target = [Gtk.TargetEntry.new(self.DND_TARGET, Gtk.TargetFlags.SAME_WIDGET, 0)]
        view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.MOVE)
        view.enable_model_drag_dest(target, Gdk.DragAction.MOVE)
        view.connect("drag-data-get", self._on_drag_get)
        view.connect("drag-data-received", self._on_drag_received)
        self.image_view = view
        self._images_loaded = False
        self._expand_after_refresh: str | None = None
        box.pack_start(scrolled(view), True, True, 0)
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_markup("<small>Images per Maus in Ordner ziehen · Rechtsklick für weitere Aktionen</small>")
        hint.get_style_context().add_class("status-idle")
        box.pack_start(hint, False, False, 0)
        self._on_image_selected(view.get_selection())
        return box

    # ---------- Image-Archiv (Baum) ----------

    def _selected_image_row(self):
        model, it = self.image_view.get_selection().get_selected()
        return model, it

    def _target_folder(self) -> str:
        """Ordner für „Neuer Ordner“: gewählter Ordner, Ordner des gewählten Images, sonst oberste Ebene."""
        model, it = self._selected_image_row()
        if it is None:
            return ""
        kind, area, rel = model[it][self.C_KIND], model[it][self.C_AREA], model[it][self.C_REL]
        if kind == "folder" or (kind == "image" and area == "archive"):
            return rel
        return ""

    def _on_image_selected(self, sel: Gtk.TreeSelection) -> None:
        model, it = sel.get_selected()
        kind = model[it][self.C_KIND] if it is not None else ""
        root_ok = self._nas_root() is not None
        self.img_buttons["folder"].set_sensitive(root_ok)
        self.img_buttons["rename"].set_sensitive(root_ok and kind == "folder")
        self.img_buttons["delete"].set_sensitive(root_ok and kind in ("folder", "image"))
        self.btn_img_stick.set_sensitive(kind == "image" and model[it][self.C_TYPE] in ("Disk-Image", "Clonezilla"))

    def _on_image_activated(self, view, path, _col) -> None:
        if view.row_expanded(path):
            view.collapse_row(path)
        else:
            view.expand_row(path, False)

    def _on_image_button(self, view, event) -> bool:
        if event.button != 3:
            return False
        hit = view.get_path_at_pos(int(event.x), int(event.y))
        if hit:
            view.get_selection().select_path(hit[0])
        model, it = self._selected_image_row()
        kind = model[it][self.C_KIND] if it is not None else ""
        menu = Gtk.Menu()

        def add(label, handler, sensitive=True):
            item = Gtk.MenuItem(label=label, sensitive=sensitive)
            item.connect("activate", lambda _i: handler(None))
            menu.append(item)

        add("Neuer Ordner …", self.on_new_archive_folder)
        if kind == "folder":
            add("Umbenennen …", self.on_rename_archive_folder)
            add("Löschen (nur leer)", self.on_delete_image)
        if kind == "image":
            if model[it][self.C_AREA] == "archive":
                add("Nach „Nicht einsortiert“", self.on_unsort_image)
            add("Restore-Stick …", self.on_restore_stick,
                model[it][self.C_TYPE] in ("Disk-Image", "Clonezilla"))
            add("Löschen …", self.on_delete_image)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def on_restore_stick(self, _btn) -> None:
        model, it = self._selected_image_row()
        if it is None or model[it][self.C_KIND] != "image" or \
                model[it][self.C_TYPE] not in ("Disk-Image", "Clonezilla"):
            self.status("Zuerst rechts im Reiter „Images“ ein Disk- oder Clonezilla-Image wählen")
            return
        path = model[it][self.C_PATH]
        disks = clonezilla.disks(Path(path)) if model[it][self.C_TYPE] == "Clonezilla" else None
        StickDialog(self, image=path, source_disks=disks)

    def _archive_op(self, op, done_msg: str) -> None:
        def finished(result) -> None:
            if isinstance(result, Exception):
                self.status(f"Fehler: {result}")
                confirm_error(self, str(result))
            else:
                self.status(done_msg)
            self.refresh_images()
            self.refresh_files()
        run_async(op, finished)

    def on_new_archive_folder(self, _btn) -> None:
        root = self._nas_root()
        if root is None:
            return
        parent = self._target_folder()
        if parent and len(parent.split("/")) >= archive.MAX_DEPTH:
            confirm_error(self, f"„{parent}“ liegt schon auf Ebene {archive.MAX_DEPTH} – "
                                "dort sind keine weiteren Unterordner möglich.")
            return
        where = f" in „{parent}“" if parent else " (oberste Ebene)"
        name = ask_text(self, "Neuer Ordner", f"Name des neuen Ordners{where}:")
        if name:
            self._expand_after_refresh = parent
            self._archive_op(lambda: archive.make_folder(root, parent, name), f"Ordner „{name.strip()}“ angelegt")

    def on_rename_archive_folder(self, _btn) -> None:
        root = self._nas_root()
        model, it = self._selected_image_row()
        if root is None or it is None or model[it][self.C_KIND] != "folder":
            return
        rel = model[it][self.C_REL]
        old = rel.rsplit("/", 1)[-1]
        new = ask_text(self, "Ordner umbenennen", f"Neuer Name für „{old}“:", old)
        if new and new.strip() != old:
            self._archive_op(lambda: archive.rename_folder(root, rel, new), f"Umbenannt in „{new.strip()}“")

    def on_unsort_image(self, _btn) -> None:
        root = self._nas_root()
        model, it = self._selected_image_row()
        if root and it is not None and model[it][self.C_KIND] == "image":
            path = model[it][self.C_PATH]
            self._archive_op(lambda: archive.move_image(root, path, None), "Nach „Nicht einsortiert“ verschoben")

    def _on_drag_get(self, view, _context, selection, _info, _time) -> None:
        model, it = view.get_selection().get_selected()
        if it is not None:
            selection.set(selection.get_target(), 8, model.get_string_from_iter(it).encode())

    def _on_drag_received(self, view, context, x, y, selection, _info, time) -> None:
        # Der Store soll die Zeilen nicht selbst umhängen – das NAS ist die Wahrheit
        view.stop_emission_by_name("drag-data-received")
        Gtk.drag_finish(context, True, False, time)
        root = self._nas_root()
        data = selection.get_data()
        if root is None or not data:
            return
        model = self.image_store
        try:
            src = model.get_iter_from_string(data.decode())
        except (ValueError, TypeError):
            return
        hit = view.get_dest_row_at_pos(x, y)
        if hit is None:
            dest_area, dest_rel = "archive", ""  # leere Fläche: oberste Ebene (nur für Ordner)
        else:
            row = model[hit[0]]
            dest_area = row[self.C_AREA]
            dest_rel = row[self.C_REL] if row[self.C_KIND] in ("folder", "image") else ""
        self.drop(model[src][self.C_KIND], model[src][self.C_AREA], model[src][self.C_REL],
                  model[src][self.C_PATH], model[src][self.C_NAME], dest_area, dest_rel)

    def drop(self, kind: str, area: str, rel: str, path: str, name: str, dest_area: str, dest_rel: str) -> None:
        """Ziel einer Maus-Verschiebung auswerten (auch für Tests ohne echte Maus)."""
        root = self._nas_root()
        if root is None:
            return
        if kind == "image":
            if dest_area == "unsorted":
                if area != "unsorted":
                    self._archive_op(lambda: archive.move_image(root, path, None),
                                     "Nach „Nicht einsortiert“ verschoben")
            elif dest_rel:
                if not (area == "archive" and rel == dest_rel):
                    self._expand_after_refresh = dest_rel
                    self._archive_op(lambda: archive.move_image(root, path, dest_rel),
                                     f"Verschoben nach „{dest_rel}“")
            else:
                self.status("Images bitte in einen Ordner ziehen")
        elif kind == "folder":
            current_parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            if dest_area == "unsorted":
                self.status("Ordner können nicht nach „Nicht einsortiert“ verschoben werden")
            elif dest_rel != current_parent and dest_rel != rel:
                self._expand_after_refresh = dest_rel
                folder = rel.rsplit("/", 1)[-1]
                self._archive_op(lambda: archive.move_folder(root, rel, dest_rel), f"Ordner „{folder}“ verschoben")

    def _expanded_keys(self) -> set[str]:
        keys = set()

        def walk(it):
            while it is not None:
                if self.image_view.row_expanded(self.image_store.get_path(it)):
                    keys.add(self.image_store[it][self.C_KIND] + ":" + self.image_store[it][self.C_REL])
                walk(self.image_store.iter_children(it))
                it = self.image_store.iter_next(it)
        walk(self.image_store.get_iter_first())
        return keys

    def _restore_expanded(self, keys: set[str]) -> None:
        def walk(it):
            while it is not None:
                row = self.image_store[it]
                if row[self.C_KIND] + ":" + row[self.C_REL] in keys:
                    self.image_view.expand_row(self.image_store.get_path(it), False)
                walk(self.image_store.iter_children(it))
                it = self.image_store.iter_next(it)
        walk(self.image_store.get_iter_first())

    def _build_files_tab(self) -> Gtk.Widget:
        self.files_rel = ""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        bar = Gtk.Box(spacing=6)
        self.btn_up = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.BUTTON)
        self.btn_up.set_tooltip_text("Übergeordneter Ordner")
        self.btn_up.connect("clicked", lambda _b: self.open_folder(nasfiles.parent(self.files_rel)))
        bar.pack_start(self.btn_up, False, False, 0)
        self.files_path = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.START, selectable=True)
        bar.pack_start(self.files_path, True, True, 0)
        buttons = (("folder-new-symbolic", "Neuer Ordner", self.on_new_folder),
                   ("document-edit-symbolic", "Umbenennen", self.on_rename),
                   ("user-trash-symbolic", "Löschen", self.on_delete_files),
                   ("view-refresh-symbolic", "Aktualisieren", lambda _b: self.refresh_files()))
        self.file_buttons = {}
        for icon, tip, handler in buttons:
            b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            b.set_tooltip_text(tip)
            b.connect("clicked", handler)
            bar.pack_start(b, False, False, 0)
            self.file_buttons[tip] = b
        box.pack_start(bar, False, False, 0)

        # icon, Name, Grösse (Text), Geändert, Ordner?, Grösse (Byte)
        self.file_store = Gtk.ListStore(str, str, str, str, bool, GObject.TYPE_INT64)
        self.file_view = make_tree([("", -1), ("Name", 1), ("Grösse", 2), ("Geändert", 3)], self.file_store)
        self.file_view.get_column(2).set_sort_column_id(5)
        self.file_view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.file_view.get_selection().connect("changed", lambda _s: self._update_file_buttons())
        self.file_view.connect("row-activated", self._on_file_activated)
        self.file_view.connect("key-press-event", self._on_file_key)
        box.pack_start(scrolled(self.file_view), True, True, 0)
        self._update_file_buttons()
        return box

    # ---------- Fenster ----------

    def _on_window_state(self, _w, event) -> None:
        self._fullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)

    def _on_key(self, _w, event) -> bool:
        if event.keyval == Gdk.KEY_F11:
            self.unfullscreen() if self._fullscreen else self.fullscreen()
            return True
        return False

    # ---------- Dateiverwaltung NAS ----------

    def _nas_root(self) -> str | None:
        mp = self.cfg.nas.mount_point
        return mp if os.path.ismount(mp) else None

    def _selected_files(self) -> list[str]:
        model, paths = self.file_view.get_selection().get_selected_rows()
        return [model[p][1] for p in paths]

    def _update_file_buttons(self) -> None:
        n = len(self._selected_files()) if hasattr(self, "file_view") else 0
        root_ok = self._nas_root() is not None
        self.file_buttons["Neuer Ordner"].set_sensitive(root_ok)
        self.file_buttons["Umbenennen"].set_sensitive(root_ok and n == 1)
        self.file_buttons["Löschen"].set_sensitive(root_ok and n > 0)
        self.btn_up.set_sensitive(bool(self.files_rel))

    def refresh_files(self) -> None:
        self.open_folder(self.files_rel)

    def open_folder(self, rel: str) -> None:
        root = self._nas_root()
        self.file_store.clear()
        if root is None:
            self.files_path.set_text("NAS nicht eingehängt")
            self._update_file_buttons()
            return
        run_async(lambda: nasfiles.list_dir(root, rel), lambda r: self._on_folder(root, rel, r))

    def _on_folder(self, root: str, rel: str, result) -> None:
        if isinstance(result, Exception):
            self.status(f"Ordner nicht lesbar: {result}")
            if rel:
                self.open_folder(nasfiles.parent(rel))
            return
        self.files_rel = rel
        self.files_path.set_text(f"NAS: /{rel}")
        self.files_path.set_tooltip_text(f"{root}/{rel}" if rel else root)
        self.file_store.clear()
        for e in result:
            icon = "folder-symbolic" if e.is_dir else "emblem-symbolic-link-symbolic" if e.is_link \
                else "text-x-generic-symbolic"
            self.file_store.append([icon, e.name, "" if e.is_dir else nas.format_size(e.size),
                                    e.mtime.strftime("%d.%m.%Y %H:%M"), e.is_dir, e.size])
        self._update_file_buttons()

    def _on_file_activated(self, view, path, _col) -> None:
        row = view.get_model()[path]
        if row[4]:
            self.open_folder(nasfiles.join(self.files_rel, row[1]))

    def _on_file_key(self, _view, event) -> bool:
        if event.keyval == Gdk.KEY_Delete:
            self.on_delete_files(None)
            return True
        if event.keyval == Gdk.KEY_F2:
            self.on_rename(None)
            return True
        if event.keyval == Gdk.KEY_BackSpace and self.files_rel:
            self.open_folder(nasfiles.parent(self.files_rel))
            return True
        return False

    def _file_op(self, op, done_msg: str) -> None:
        def finished(result) -> None:
            if isinstance(result, Exception):
                self.status(f"Fehler: {result}")
                confirm_error(self, str(result))
            else:
                self.status(done_msg)
            self.refresh_files()
            self.refresh_images()
            self.refresh_nas_status()
        run_async(op, finished)

    def on_new_folder(self, _btn) -> None:
        root = self._nas_root()
        name = root and ask_text(self, "Neuer Ordner", "Name des neuen Ordners:")
        if name:
            rel = self.files_rel
            self._file_op(lambda: nasfiles.make_dir(root, rel, name), f"Ordner „{name.strip()}“ angelegt")

    def on_rename(self, _btn) -> None:
        root, names = self._nas_root(), self._selected_files()
        if not root or len(names) != 1:
            return
        new = ask_text(self, "Umbenennen", f"Neuer Name für „{names[0]}“:", names[0])
        if new and new != names[0]:
            rel = self.files_rel
            self._file_op(lambda: nasfiles.rename(root, rel, names[0], new), f"Umbenannt in „{new.strip()}“")

    def on_delete_files(self, _btn) -> None:
        root, names = self._nas_root(), self._selected_files()
        if root and names:
            self._confirm_delete(root, self.files_rel, names)

    def on_delete_image(self, _btn) -> None:
        root = self._nas_root()
        model, it = self.image_view.get_selection().get_selected()
        if not root or it is None:
            return
        if model[it][self.C_KIND] == "folder":
            rel = model[it][self.C_REL]
            self._archive_op(lambda: archive.delete_folder(root, rel), f"Ordner „{rel}“ gelöscht")
            return
        if model[it][self.C_KIND] != "image":
            return
        try:
            rel_path = os.path.relpath(model[it][self.C_PATH], root)
        except ValueError:
            return
        if rel_path.startswith(".."):
            return
        self._confirm_delete(root, nasfiles.parent(rel_path), [os.path.basename(rel_path)])

    def _confirm_delete(self, root: str, rel: str, names: list[str]) -> None:
        """Erst Umfang zählen (kann bei Images dauern), dann nachfragen, dann löschen."""
        self.status("Ermittle Umfang …")

        def ask(result) -> None:
            if isinstance(result, Exception):
                self.status(f"Fehler: {result}")
                return
            files, size = result
            what = f"„{names[0]}“" if len(names) == 1 else f"{len(names)} Einträge"
            if not confirm(self, f"{what} endgültig löschen?",
                           f"{files} Datei(en), {nas.format_size(size)} in NAS: /{rel}\n\n"
                           "Das NAS hat keinen Papierkorb für das Tool – gelöschte Daten sind weg."):
                self.status("Löschen abgebrochen")
                return
            self.status(f"Lösche {what} …")
            self._file_op(lambda: nasfiles.delete(root, rel, names), f"{what} gelöscht")

        run_async(lambda: nasfiles.measure(root, rel, names), ask)

    # ---------- NAS-Status ----------

    def open_nas_dialog(self) -> None:
        if self.nas_dialog is not None:
            self.nas_dialog.present()
            return
        self.nas_dialog = NasDialog(self, self.cfg, self._on_nas_changed)
        self.nas_dialog.connect("destroy", lambda _d: setattr(self, "nas_dialog", None))

    def _on_nas_changed(self, _cfg: config.NasConfig) -> None:
        self.refresh_nas_status()

    def refresh_nas_status(self, auto_mount: bool = False) -> bool:
        """Kurzstatus abfragen (Timer: True = weiterlaufen). Läuft schon eine Abfrage, nicht doppelt."""
        if not self._nas_checking:
            self._nas_checking = True
            cfg = self.cfg.nas
            run_async(lambda: nas.quick_status(cfg, auto_mount), self._on_nas_status)
        return True

    def _on_nas_status(self, st) -> None:
        self._nas_checking = False
        if isinstance(st, Exception):
            st = nas.Status("fail", str(st))
        cfg = self.cfg.nas
        where = f"{cfg.host}/{cfg.share.strip('/')}" if cfg.host else ""
        if st.state == "ok":
            text, state = f"● NAS verbunden  ({where})", "ok"
        elif st.state == "unconfigured":
            text, state = "● NAS nicht eingerichtet – Menü → NAS-Verbindung …", "fail"
        else:
            text, state = f"● NAS nicht verbunden – {st.reason}", "fail"
        self._set_style(self.nas_status, state)
        self.nas_status.set_text(text)
        self.nas_status.set_tooltip_text(f"{text}\n{where} → {cfg.mount_point}" if where else text)
        if st.state == "ok":
            low = st.low_space
            self.nas_space.set_text(f"Frei: {nas.format_gb(st.free)} von {nas.format_gb(st.total)}"
                                    + (" – wenig Platz" if low else ""))
            self.nas_space.set_tooltip_text("Unter 100 GB frei – Images vor dem nächsten Sichern aufräumen"
                                            if low else "Genügend freier Speicher (mehr als 100 GB)")
            self._set_style(self.nas_space, "fail" if low else "ok")
        else:
            self.nas_space.set_text("Frei: –")
            self.nas_space.set_tooltip_text(None)
            self._set_style(self.nas_space, "idle")
        if st.state != self.nas_state:
            self.nas_state = st.state
            # Wechsel verbunden ↔ getrennt: Listen neu laden bzw. leeren
            self.refresh_images()
            self.refresh_files()
            self._update_file_buttons()

    @staticmethod
    def _set_style(label: Gtk.Label, state: str) -> None:
        ctx = label.get_style_context()
        for c in ("status-ok", "status-fail", "status-idle"):
            ctx.remove_class(c)
        ctx.add_class(f"status-{state}")

    def refresh_images(self) -> None:
        mp = self._nas_root()
        if mp is None:
            self.image_store.clear()
            self.img_count.set_text("NAS nicht verbunden")
            self._on_image_selected(self.image_view.get_selection())
            return
        run_async(lambda: archive.scan(mp), self._on_images)

    def _image_row(self, img: nas.ImageInfo, rel: str, area: str) -> list:
        return ["drive-harddisk-symbolic", img.name, img.kind, nas.format_size(img.size),
                img.mtime.strftime("%d.%m.%Y %H:%M"), img.size, str(img.path), "image", rel, area]

    def _on_images(self, tree) -> None:
        if isinstance(tree, Exception):
            self.status(f"Images konnten nicht gelesen werden: {tree}")
            return
        keys = self._expanded_keys() if self._images_loaded else {"unsorted:"}
        if self._expand_after_refresh is not None:
            parts = self._expand_after_refresh.split("/") if self._expand_after_refresh else []
            keys |= {"folder:" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)}
            self._expand_after_refresh = None
        store = self.image_store
        store.clear()
        unsorted = store.append(None, ["folder-download-symbolic", f"Nicht einsortiert ({len(tree.unsorted)})", "",
                                       nas.format_size(sum(i.size for i in tree.unsorted)), "", 0, "", "unsorted",
                                       "", "unsorted"])
        for img in tree.unsorted:  # neueste zuerst
            store.append(unsorted, self._image_row(img, "", "unsorted"))

        def add(parent, folder: archive.Folder) -> None:
            total = folder.size()  # inklusive Unterordner
            it = store.append(parent, ["folder-symbolic", f"{folder.name} ({folder.count()})", "Ordner",
                                       nas.format_size(total) if total else "", "", total, "", "folder",
                                       folder.rel, "archive"])
            for sub in folder.folders:
                add(it, sub)
            for img in folder.images:
                store.append(it, self._image_row(img, folder.rel, "archive"))

        for folder in tree.folders:
            add(None, folder)
        self._restore_expanded(keys)
        self._images_loaded = True
        self.img_count.set_text(f"{len(tree.all_images())} Images · {len(tree.unsorted)} nicht einsortiert")
        self._on_image_selected(self.image_view.get_selection())


    # ---------- linke Seite: Maschinen ----------

    def _build_machine_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        box.pack_start(pane_title("Geräte"), False, False, 0)

        bar = Gtk.Box(spacing=6)
        bar.pack_start(Gtk.Label(label="Netz"), False, False, 0)
        default = self.cfg.scan_network or str(network.default_scan_network() or "")
        self.scan_net = Gtk.Entry(text=default, placeholder_text="z. B. 192.168.1.0/24", width_chars=18)
        bar.pack_start(self.scan_net, False, False, 0)
        self.btn_scan = Gtk.Button(label="Netzwerk scannen")
        self.btn_scan.connect("clicked", self.on_scan)
        bar.pack_start(self.btn_scan, False, False, 0)
        btn_add = Gtk.Button(label="Hinzufügen …")
        btn_add.connect("clicked", self.on_add_machine)
        bar.pack_start(btn_add, False, False, 0)
        box.pack_start(bar, False, False, 0)

        self.scan_progress = Gtk.ProgressBar(show_text=True, no_show_all=True)
        box.pack_start(self.scan_progress, False, False, 0)

        # icon, Name, IP, MAC, Quelle, IP als Zahl (Sortierung), Hardware, Disks, zuletzt gesehen, Status
        self.machine_store = Gtk.ListStore(str, str, str, str, str, GObject.TYPE_INT64, str, str, float, str)
        self.machine_view = make_tree([("", -1), ("Name", 1), ("IP-Adresse", 2), ("Status", 9), ("Quelle", 4),
                                       ("Hardware", 6), ("Disks", 7), ("MAC", 3)], self.machine_store)
        self.machine_view.get_column(2).set_sort_column_id(5)
        self.machine_view.get_column(1).set_min_width(190)
        self.machine_store.set_sort_column_id(5, Gtk.SortType.ASCENDING)
        self.machine_view.get_selection().connect("changed", self._on_machine_selected)
        box.pack_start(scrolled(self.machine_view), True, True, 0)

        # Aktionen für die gewählte Maschine (Funktion folgt in späteren Schritten)
        actions = Gtk.Box(spacing=6)
        self.btn_backup = Gtk.Button(label="Backup erstellen", sensitive=False)
        self.btn_backup.set_tooltip_text("Datei-Backup – folgt")
        self.btn_image = Gtk.Button(label="Disk-Image erstellen", sensitive=False)
        self.btn_image.set_tooltip_text("Ganze Disk der gewählten Maschine aufs NAS sichern (Maschine mit Agent-Stick)")
        self.btn_image.connect("clicked", self.on_create_image)
        self.btn_restore = Gtk.Button(label="Image zurückspielen", sensitive=False)
        self.btn_restore.set_tooltip_text("Disk-Image vom NAS auf eine Disk der gewählten Maschine schreiben")
        self.btn_restore.connect("clicked", self.on_restore_image)
        for b in (self.btn_backup, self.btn_image, self.btn_restore):
            actions.pack_start(b, False, False, 0)
        self.btn_power = Gtk.Button(label="Herunterfahren", sensitive=False)
        self.btn_power.set_tooltip_text("Gewählte Maschine mit Agent-Stick herunterfahren")
        self.btn_power.connect("clicked", self.on_power_off)
        actions.pack_start(self.btn_power, False, False, 0)
        self.btn_remove = Gtk.Button(label="Entfernen", sensitive=False)
        self.btn_remove.connect("clicked", self.on_remove_machine)
        actions.pack_end(self.btn_remove, False, False, 0)
        box.pack_start(actions, False, False, 0)
        return box

    def _add_machine_row(self, m: network.Machine) -> None:
        """Fügt eine Maschine hinzu oder ergänzt die bestehende Zeile mit derselben IP."""
        now = time.time() if m.source == "USB-Agent" else 0.0
        for row in self.machine_store:
            if row[2] == m.ip:
                if m.source == "USB-Agent":
                    row[0], row[4], row[8] = ICON_AGENT, m.source, now
                elif m.online and row[4] != "USB-Agent":
                    row[0] = ICON_ONLINE
                if m.name:
                    row[1] = m.name
                for idx, value in ((3, m.mac), (6, m.hardware), (7, m.disks)):
                    if value:
                        row[idx] = value
                return
        icon = ICON_AGENT if m.source == "USB-Agent" else ICON_ONLINE if m.online else ICON_OFFLINE
        self.machine_store.append([icon, m.name or "–", m.ip, m.mac or "–", m.source,
                                   int(ipaddress.IPv4Address(m.ip)), m.hardware, m.disks, now, ""])

    # ---------- USB-Agent ----------

    def _start_listener(self) -> None:
        self.listener = discovery.Listener(lambda info: GLib.idle_add(self._on_agent, info))
        try:
            self.listener.start()
        except OSError as e:
            self.status(f"USB-Agent-Erkennung nicht aktiv (UDP {discovery.PORT}): {e}")
            return
        GLib.timeout_add_seconds(5, self._expire_agents)

    def _on_agent(self, info: discovery.AgentInfo) -> bool:
        self.agents[info.ip] = info
        disks = ", ".join(f"{d.name} {nas.format_size(d.size)}" for d in info.disks) or "–"
        known = any(row[2] == info.ip and row[4] == "USB-Agent" and row[0] == ICON_AGENT
                    for row in self.machine_store)
        self._add_machine_row(network.Machine(ip=info.ip, name=info.hostname, mac=info.mac, online=True,
                                              source="USB-Agent", hardware=info.hardware, disks=disks))
        for row in self.machine_store:
            if row[2] == info.ip:
                row[9] = info.status
        self._update_image_button()
        if not known:
            note = " – Link-Local, im Netz gibt es kein DHCP" if info.ip.startswith("169.254.") else ""
            self.status(f"USB-Agent gemeldet: {info.hostname or info.ip} ({info.ip}){note}")
        return False

    def _expire_agents(self) -> bool:
        """Agents ohne Meldung: nach 15 s offline, nach 60 s aus der Liste (manuelle bleiben)."""
        now = time.time()
        manual = {e.get("ip") for e in self.cfg.machines}
        gone = []
        for row in self.machine_store:
            if row[4] != "USB-Agent":
                continue
            if row[8] < now - AGENT_REMOVE_AFTER:
                gone.append(row.iter)
            elif row[0] == ICON_AGENT and row[8] < now - AGENT_TIMEOUT:
                row[0] = ICON_OFFLINE
                row[9] = "offline"
        for it in gone:
            ip, name = self.machine_store[it][2], self.machine_store[it][1]
            self.agents.pop(ip, None)
            if ip in manual:
                # war manuell erfasst: wieder als manueller Eintrag zeigen
                entry = next(e for e in self.cfg.machines if e.get("ip") == ip)
                self.machine_store[it][0] = ICON_OFFLINE
                self.machine_store[it][1] = entry.get("name") or "–"
                self.machine_store[it][4] = "manuell"
                self.machine_store[it][6] = self.machine_store[it][7] = self.machine_store[it][9] = ""
            else:
                self.machine_store.remove(it)
            self.status(f"{name} ({ip}) entfernt – seit {AGENT_REMOVE_AFTER} s keine Meldung")
        self._update_image_button()
        return True

    def _load_manual_machines(self) -> None:
        for entry in self.cfg.machines:
            try:
                self._add_machine_row(network.Machine(ip=entry["ip"], name=entry.get("name", ""), source="manuell"))
            except (KeyError, ValueError):
                continue

    def on_scan(self, _btn) -> None:
        try:
            net = ipaddress.IPv4Network(self.scan_net.get_text().strip(), strict=False)
        except ValueError:
            self.status("Ungültiges Netz, Format z. B. 192.168.1.0/24")
            return
        if net.num_addresses > 1024:
            self.status("Netz zu gross (max. /22)")
            return
        self.btn_scan.set_sensitive(False)
        self.scan_progress.set_fraction(0)
        self.scan_progress.show()
        self.status(f"Scanne {net} …")

        def progress(done, total):
            GLib.idle_add(self._on_scan_progress, done, total)

        run_async(lambda: network.scan(net, progress), self._on_scanned)

    def _on_scan_progress(self, done: int, total: int) -> None:
        self.scan_progress.set_fraction(done / total if total else 1)
        self.scan_progress.set_text(f"{done} / {total}")

    def _on_scanned(self, result) -> None:
        self.btn_scan.set_sensitive(True)
        self.scan_progress.hide()
        if isinstance(result, Exception):
            self.status(f"Scan fehlgeschlagen: {result}")
            return
        found = {m.ip for m in result}
        stale = [row.iter for row in self.machine_store if row[4] == "Scan" and row[2] not in found]
        for it in stale:
            self.machine_store.remove(it)
        for m in result:
            self._add_machine_row(m)
        removed = f", {len(stale)} nicht mehr erreichbare entfernt" if stale else ""
        self.status(f"Scan fertig: {len(result)} Maschinen online{removed}")

    def on_add_machine(self, _btn) -> None:
        dlg = Gtk.Dialog(title="Maschine hinzufügen", transient_for=self, modal=True)
        dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Hinzufügen", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=8, row_spacing=6, margin=12)
        name = Gtk.Entry(activates_default=True)
        ip = Gtk.Entry(activates_default=True, placeholder_text="192.168.1.50")
        grid.attach(Gtk.Label(label="Name", xalign=0), 0, 0, 1, 1)
        grid.attach(name, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="IP-Adresse", xalign=0), 0, 1, 1, 1)
        grid.attach(ip, 1, 1, 1, 1)
        dlg.get_content_area().add(grid)
        dlg.show_all()
        while dlg.run() == Gtk.ResponseType.OK:
            try:
                addr = str(ipaddress.IPv4Address(ip.get_text().strip()))
            except ValueError:
                self.status("Ungültige IP-Adresse")
                continue
            m = network.Machine(ip=addr, name=name.get_text().strip(), source="manuell")
            self.cfg.machines = [e for e in self.cfg.machines if e.get("ip") != addr]
            self.cfg.machines.append({"name": m.name, "ip": addr})
            config.save(self.cfg)
            self._add_machine_row(m)
            run_async(lambda: network.ping(addr), lambda ok: self._add_machine_row(
                network.Machine(ip=addr, online=bool(ok) and not isinstance(ok, Exception))))
            break
        dlg.destroy()

    def _on_machine_selected(self, selection: Gtk.TreeSelection) -> None:
        model, it = selection.get_selected()
        has = it is not None
        self.btn_remove.set_sensitive(has)
        self._update_image_button()
        if has:
            self.status(f"Ausgewählt: {model[it][1]} ({model[it][2]})")

    def _selected_agent(self) -> discovery.AgentInfo | None:
        model, it = self.machine_view.get_selection().get_selected()
        if it is None or model[it][4] != "USB-Agent" or model[it][0] != ICON_AGENT:
            return None
        return self.agents.get(model[it][2])

    def _update_image_button(self) -> None:
        agent = self._selected_agent()
        ok = agent is not None and agent.control_port > 0
        self.btn_image.set_sensitive(ok)
        self.btn_restore.set_sensitive(ok)
        self.btn_power.set_sensitive(ok)
        for label in ("Disk-Image erstellen …", "Image zurückspielen …", "Maschine herunterfahren"):
            if label in getattr(self, "menu_items", {}):
                self.menu_items[label].set_sensitive(ok)
        if agent is not None and not agent.control_port:
            self.btn_image.set_tooltip_text("Agent-Stick ist veraltet – mit aktuellem Tool neu erstellen")

    def on_create_image(self, _btn) -> None:
        agent = self._selected_agent()
        if agent is None:
            return
        if agent.busy:
            self.status("Agent ist mit einem anderen Auftrag beschäftigt")
            return
        root = self._nas_root()
        if root is None:
            self.status("NAS ist nicht verbunden – Menü → NAS-Verbindung …")
            return
        ImageDialog(self, agent, root, on_done=self._after_job)

    def _after_job(self) -> None:
        self.refresh_images()
        self.refresh_nas_status()  # freier Speicher hat sich geändert

    def on_power_off(self, _btn) -> None:
        agent = self._selected_agent()
        if agent is None:
            return
        if not confirm(self, f"{agent.hostname or agent.ip} herunterfahren?",
                       f"{agent.hardware} ({agent.ip})\n\nDanach kann der Stick abgezogen werden.",
                       ok_label="Herunterfahren"):
            return
        key = agentclient.load_or_create_key()

        def done(result) -> None:
            if isinstance(result, Exception):
                self.status(f"Herunterfahren fehlgeschlagen: {result}")
                confirm_error(self, str(result))
            else:
                self.status(f"{agent.hostname or agent.ip} wird heruntergefahren")

        run_async(lambda: agentclient.power(agent.ip, key, "poweroff", agent.control_port), done)

    def on_restore_image(self, _btn) -> None:
        agent = self._selected_agent()
        if agent is None:
            return
        if agent.busy:
            self.status("Agent ist mit einem anderen Auftrag beschäftigt")
            return
        root = self._nas_root()
        if root is None:
            self.status("NAS ist nicht eingehängt")
            return
        model, it = self.image_view.get_selection().get_selected()
        pre = model[it][self.C_PATH] if it is not None and model[it][self.C_KIND] == "image" else None
        RestoreDialog(self, agent, root, preselect=pre)

    def on_remove_machine(self, _btn) -> None:
        model, it = self.machine_view.get_selection().get_selected()
        if it is None:
            return
        ip = model[it][2]
        self.cfg.machines = [e for e in self.cfg.machines if e.get("ip") != ip]
        config.save(self.cfg)
        model.remove(it)

    def status(self, text: str) -> None:
        self.statusbar.pop(0)
        self.statusbar.push(0, text)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="ch.okula.RecoveryTool")

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = self.get_active_window() or MainWindow(self)
        win.show_all()
        win.present()


def main() -> int:
    return App().run(None)
