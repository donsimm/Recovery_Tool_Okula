"""GTK-3-Oberfläche: links NAS und Images, rechts Maschinen im LAN."""

from __future__ import annotations

import ipaddress
import os
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango  # noqa: E402

from okula_recovery import __version__, config, discovery, nas, nasfiles, network  # noqa: E402
from okula_recovery.image_dialog import ImageDialog  # noqa: E402
from okula_recovery.restore_dialog import RestoreDialog  # noqa: E402
from okula_recovery.stick_dialog import StickDialog  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO_COLOR = b"#0b1213"  # Füllfarbe im Original-SVG

# Agent gilt als offline, wenn so lange kein Beacon kam
AGENT_TIMEOUT = 15

ICON_ONLINE = "network-transmit-receive-symbolic"
ICON_OFFLINE = "network-offline-symbolic"
ICON_AGENT = "media-removable-symbolic"

CSS = b"""
.pane-title { font-weight: bold; font-size: 115%; }
.status-ok { color: #2e7d32; font-weight: bold; }
.status-fail { color: #c62828; font-weight: bold; }
.status-idle { color: #757575; }
"""


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
        self._auto_mount_tried = False

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
        paned.pack1(self._build_nas_pane(), resize=True, shrink=False)
        paned.pack2(self._build_machine_pane(), resize=True, shrink=False)
        paned.set_position(620)

        self.statusbar = Gtk.Statusbar()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(paned, True, True, 0)
        root.pack_start(self.statusbar, False, False, 0)
        self.add(root)

        self._update_nas_form()
        self._load_manual_machines()
        self._start_listener()
        GLib.idle_add(self.on_test_nas, None)

    def _update_logo(self, header: Gtk.HeaderBar) -> None:
        """Logo in der Textfarbe der Titelleiste, damit es auch im dunklen Theme lesbar ist."""
        color = rgba_hex(header.get_style_context().get_color(Gtk.StateFlags.NORMAL))
        if color != getattr(self, "_logo_color", None):
            self._logo_color = color
            self.logo.set_from_pixbuf(svg_pixbuf(ASSETS / "okula-logo.svg", 22, color))

    # ---------- linke Seite: NAS ----------

    def _build_nas_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        box.pack_start(pane_title("NAS – Images & Backups"), False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        self.nas_protocol = Gtk.ComboBoxText()
        self.nas_protocol.append("smb", "SMB / CIFS")
        self.nas_protocol.append("nfs", "NFS")
        self.nas_protocol.set_active_id(self.cfg.nas.protocol)
        self.nas_protocol.connect("changed", lambda _c: self._update_nas_form())
        self.nas_host = Gtk.Entry(text=self.cfg.nas.host, placeholder_text="z. B. nas.local oder 192.168.1.10",
                                  hexpand=True)

        # Freigabe: frei eingeben oder aus „Freigaben suchen“ wählen
        share_box = Gtk.Box(spacing=6)
        self.nas_share_combo = Gtk.ComboBoxText.new_with_entry()
        self.nas_share_combo.set_hexpand(True)
        self.nas_share = self.nas_share_combo.get_child()
        self.nas_share.set_text(self.cfg.nas.share)
        share_box.pack_start(self.nas_share_combo, True, True, 0)
        self.btn_shares = Gtk.Button(label="Freigaben suchen")
        self.btn_shares.set_tooltip_text("Freigaben des NAS mit Benutzer/Passwort auflisten (SMB)")
        self.btn_shares.connect("clicked", self.on_find_shares)
        share_box.pack_start(self.btn_shares, False, False, 0)

        self.nas_user = Gtk.Entry(text=self.cfg.nas.username, placeholder_text="NAS-Benutzer")
        self.nas_password = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD)
        self.nas_mount = Gtk.Entry(text=self.cfg.nas.mount_point)
        self.nas_rows = {}
        for row, (label, widget) in enumerate([("Protokoll", self.nas_protocol), ("Host", self.nas_host),
                                               ("Freigabe", share_box), ("Benutzer", self.nas_user),
                                               ("Passwort", self.nas_password), ("Einhängepunkt", self.nas_mount)]):
            lbl = Gtk.Label(label=label, xalign=0)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            self.nas_rows[label] = (lbl, widget)
        box.pack_start(grid, False, False, 0)

        buttons = Gtk.Box(spacing=6)
        self.btn_test = Gtk.Button(label="Verbindung testen")
        self.btn_test.connect("clicked", self.on_test_nas)
        btn_mount = Gtk.Button(label="Einhängen")
        btn_mount.connect("clicked", self.on_mount_nas)
        btn_umount = Gtk.Button(label="Aushängen")
        btn_umount.connect("clicked", self.on_umount_nas)
        btn_save = Gtk.Button(label="Speichern")
        btn_save.connect("clicked", self.on_save_nas)
        for b in (self.btn_test, btn_mount, btn_umount, btn_save):
            buttons.pack_start(b, False, False, 0)
        self.nas_spinner = Gtk.Spinner()
        buttons.pack_start(self.nas_spinner, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.nas_status = Gtk.Label(label="Nicht geprüft", xalign=0, wrap=True, selectable=True)
        self.nas_status.get_style_context().add_class("status-idle")
        box.pack_start(self.nas_status, False, False, 0)

        # Ergebnis der Einzelprüfungen
        self.check_store = Gtk.ListStore(str, str, str)  # icon, Prüfung, Detail
        checks = make_tree([("", -1), ("Prüfung", 1), ("Detail", 2)], self.check_store, expand=2)
        checks.set_headers_visible(False)
        checks.get_selection().set_mode(Gtk.SelectionMode.NONE)
        sw = scrolled(checks)
        sw.set_vexpand(False)
        sw.set_min_content_height(140)
        # Bei Erfolg zugeklappt, damit die Dateiliste Platz hat; bei Fehlern offen
        self.check_expander = Gtk.Expander(label="Prüfdetails", expanded=True)
        self.check_expander.add(sw)
        box.pack_start(self.check_expander, False, False, 0)

        # Reiter: Images (Übersicht) und Dateien (Dateiverwaltung des NAS)
        self.nas_tabs = Gtk.Notebook()
        self.nas_tabs.append_page(self._build_images_tab(), Gtk.Label(label="Images"))
        self.nas_tabs.append_page(self._build_files_tab(), Gtk.Label(label="Dateien"))
        self.nas_tabs.connect("switch-page", lambda _n, _p, num: num == 1 and self.refresh_files())
        box.pack_start(self.nas_tabs, True, True, 4)
        return box

    def _build_images_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        head = Gtk.Box(spacing=6)
        self.img_count = Gtk.Label(label="", xalign=0)
        head.pack_start(self.img_count, True, True, 0)
        self.btn_img_delete = Gtk.Button(label="Löschen", sensitive=False)
        self.btn_img_delete.set_tooltip_text("Gewähltes Image vom NAS löschen")
        self.btn_img_delete.connect("clicked", self.on_delete_image)
        head.pack_start(self.btn_img_delete, False, False, 0)
        btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_refresh.set_tooltip_text("Image-Liste neu laden")
        btn_refresh.connect("clicked", lambda _b: self.refresh_images())
        head.pack_start(btn_refresh, False, False, 0)
        box.pack_start(head, False, False, 0)

        # Name, Typ, Grösse (Text), Datum (Text), Grösse (Byte, für Sortierung), Pfad
        self.image_store = Gtk.ListStore(str, str, str, str, str, GObject.TYPE_INT64, str)
        self.image_view = make_tree([("Name", 1), ("Typ", 2), ("Grösse", 3), ("Datum", 4)], self.image_store)
        self.image_view.get_column(2).set_sort_column_id(5)
        self.image_view.get_selection().connect(
            "changed", lambda sel: self.btn_img_delete.set_sensitive(sel.get_selected()[1] is not None))
        box.pack_start(scrolled(self.image_view), True, True, 0)
        return box

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
        mp = self._nas_cfg_from_form().mount_point
        return mp if os.path.ismount(mp) else None

    def _selected_files(self) -> list[str]:
        model, paths = self.file_view.get_selection().get_selected_rows()
        return [model[p][1] for p in paths]

    def _update_file_buttons(self) -> None:
        n = len(self._selected_files()) if hasattr(self, "file_view") else 0
        root_ok = self._nas_root() is not None if hasattr(self, "nas_mount") else False
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
        try:
            rel_path = os.path.relpath(model[it][6], root)
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

    def _nas_cfg_from_form(self) -> config.NasConfig:
        return config.NasConfig(protocol=self.nas_protocol.get_active_id() or "smb",
                                host=self.nas_host.get_text().strip(),
                                share=self.nas_share.get_text().strip().strip("/") if self._is_smb()
                                else self.nas_share.get_text().strip(),
                                mount_point=self.nas_mount.get_text().strip() or "/mnt/okula-nas",
                                username=self.nas_user.get_text().strip())

    def _is_smb(self) -> bool:
        return (self.nas_protocol.get_active_id() or "smb") == "smb"

    def _update_nas_form(self) -> None:
        """Benutzer/Passwort und Freigabensuche gibt es nur für SMB."""
        smb = self._is_smb()
        for key in ("Benutzer", "Passwort"):
            for w in self.nas_rows.get(key, ()):
                w.set_visible(smb)
        if hasattr(self, "btn_shares"):
            self.btn_shares.set_visible(smb)
        self.nas_share.set_placeholder_text("z. B. recovery" if smb else "z. B. /volume1/recovery")
        if smb and nas.has_credentials():
            self.nas_password.set_placeholder_text("gespeichert – nur zum Ändern eingeben")

    def _set_nas_status(self, text: str, state: str) -> None:
        ctx = self.nas_status.get_style_context()
        for c in ("status-ok", "status-fail", "status-idle"):
            ctx.remove_class(c)
        ctx.add_class(f"status-{state}")
        self.nas_status.set_text(text)

    def on_save_nas(self, _btn) -> None:
        self.cfg.nas = self._nas_cfg_from_form()
        config.save(self.cfg)
        self.status("Einstellungen gespeichert")

    def on_test_nas(self, _btn) -> bool:
        cfg = self._nas_cfg_from_form()
        self.btn_test.set_sensitive(False)
        self.nas_spinner.start()
        self._set_nas_status("Prüfe Verbindung …", "idle")
        run_async(lambda: nas.test_connection(cfg), self._on_nas_tested)
        return False

    def _on_nas_tested(self, result) -> None:
        self.btn_test.set_sensitive(True)
        self.nas_spinner.stop()
        self.check_store.clear()
        if isinstance(result, Exception):
            self._set_nas_status(f"✗ Fehler: {result}", "fail")
            return
        for c in result:
            self.check_store.append(["emblem-ok-symbolic" if c.ok else "dialog-error-symbolic", c.name, c.detail])
        if all(c.ok for c in result):
            self._set_nas_status("● NAS verbunden", "ok")
            self.check_expander.set_expanded(False)
            self.refresh_images()
            self.refresh_files()
        else:
            failed = next(c for c in result if not c.ok)
            self._set_nas_status(f"● Keine Verbindung – {failed.name}: {failed.detail}", "fail")
            self.check_expander.set_expanded(True)
            self.image_store.clear()
            self.img_count.set_text("")
            self.refresh_files()
            if failed.name == "Eingehängt" and not self._auto_mount_tried and \
                    (not self._is_smb() or nas.has_credentials()):
                self._auto_mount_tried = True
                self.on_mount_nas(None)

    def on_mount_nas(self, _btn) -> bool:
        cfg = self._nas_cfg_from_form()
        if not cfg.host or not cfg.share:
            self._set_nas_status("● Host und Freigabe eingeben", "fail")
            return False
        password = self.nas_password.get_text() if self._is_smb() else ""
        self.cfg.nas = cfg
        config.save(self.cfg)
        self.nas_spinner.start()
        self._set_nas_status("Hänge NAS ein …", "idle")
        run_async(lambda: nas.mount(cfg, password), self._on_mounted)
        return False

    def _on_mounted(self, result) -> None:
        self.nas_spinner.stop()
        ok, msg = (False, str(result)) if isinstance(result, Exception) else result
        self.status(f"Einhängen: {msg}")
        if ok:
            self.nas_password.set_text("")
            self._update_nas_form()
            self.on_test_nas(None)
        else:
            self._set_nas_status(f"● Einhängen fehlgeschlagen: {msg}", "fail")

    def on_umount_nas(self, _btn) -> None:
        cfg = self._nas_cfg_from_form()
        self.nas_spinner.start()
        run_async(lambda: nas.umount(cfg), self._on_umounted)

    def _on_umounted(self, result) -> None:
        self.nas_spinner.stop()
        ok, msg = (False, str(result)) if isinstance(result, Exception) else result
        self.status(f"Aushängen: {msg}")
        self.on_test_nas(None)

    def on_find_shares(self, _btn) -> None:
        cfg = self._nas_cfg_from_form()
        password = self.nas_password.get_text()
        if not cfg.host or not cfg.username or not password:
            self._set_nas_status("● Für die Suche Host, Benutzer und Passwort eingeben", "fail")
            return
        self.btn_shares.set_sensitive(False)
        self.nas_spinner.start()
        run_async(lambda: nas.list_smb_shares(cfg.host, cfg.username, password), self._on_shares)

    def _on_shares(self, result) -> None:
        self.btn_shares.set_sensitive(True)
        self.nas_spinner.stop()
        if isinstance(result, Exception):
            self._set_nas_status(f"● Freigaben nicht lesbar: {result}", "fail")
            return
        current = self.nas_share.get_text()
        self.nas_share_combo.remove_all()
        for name in result:
            self.nas_share_combo.append_text(name)
        if current not in result:
            self.nas_share_combo.set_active(0)
            self.nas_share_combo.popup()
        self.status(f"{len(result)} Freigaben gefunden: {', '.join(result)}")

    def refresh_images(self) -> None:
        mp = self._nas_cfg_from_form().mount_point
        run_async(lambda: nas.list_images(mp), self._on_images)

    def _on_images(self, result) -> None:
        self.image_store.clear()
        if isinstance(result, Exception):
            self.status(f"Images konnten nicht gelesen werden: {result}")
            return
        for img in result:
            self.image_store.append(["", img.name, img.kind, nas.format_size(img.size),
                                     img.mtime.strftime("%d.%m.%Y %H:%M"), img.size, str(img.path)])
        self.img_count.set_text(f"{len(result)} Images")

    # ---------- rechte Seite: Maschinen ----------

    def _build_machine_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        box.pack_start(pane_title("Maschinen im LAN"), False, False, 0)

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

        # icon, Name, IP, MAC, Quelle, IP als Zahl (Sortierung), Hardware, Disks, zuletzt gesehen
        self.machine_store = Gtk.ListStore(str, str, str, str, str, GObject.TYPE_INT64, str, str, float)
        self.machine_view = make_tree([("", -1), ("Name", 1), ("IP-Adresse", 2), ("Quelle", 4),
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
                                   int(ipaddress.IPv4Address(m.ip)), m.hardware, m.disks, now])

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
        self._update_image_button()
        if not known:
            note = " – Link-Local, im Netz gibt es kein DHCP" if info.ip.startswith("169.254.") else ""
            self.status(f"USB-Agent gemeldet: {info.hostname or info.ip} ({info.ip}){note}")
        return False

    def _expire_agents(self) -> bool:
        limit = time.time() - AGENT_TIMEOUT
        for row in self.machine_store:
            if row[4] == "USB-Agent" and row[0] == ICON_AGENT and row[8] < limit:
                row[0] = ICON_OFFLINE
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
        for m in result:
            self._add_machine_row(m)
        self.status(f"Scan fertig: {len(result)} Maschinen online")

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
        if agent is not None and not agent.control_port:
            self.btn_image.set_tooltip_text("Agent-Stick ist veraltet – mit aktuellem Tool neu erstellen")

    def on_create_image(self, _btn) -> None:
        agent = self._selected_agent()
        if agent is None:
            return
        if agent.busy:
            self.status("Agent ist mit einem anderen Auftrag beschäftigt")
            return
        ImageDialog(self, agent, self._nas_cfg_from_form().mount_point, on_done=self.refresh_images)

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
        RestoreDialog(self, agent, root, preselect=model[it][6] if it is not None else None)

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
        win._update_nas_form()  # show_all würde die SMB-Felder bei NFS wieder einblenden
        win.present()


def main() -> int:
    return App().run(None)
