"""GTK-3-Oberfläche: Menüleiste, links erfasste Geräte, rechts NAS-Status mit Images und Dateien."""

from __future__ import annotations

import os
import time
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from okula_recovery import (__version__, agentclient, archive, clonezilla, config, devices, discovery,  # noqa: E402
                            jobs, nas, nasfiles, oslib)
from okula_recovery.device_window import DeviceWindow  # noqa: E402
from okula_recovery.image_dialog import ImageDialog  # noqa: E402
from okula_recovery.nas_dialog import NasDialog  # noqa: E402
from okula_recovery.os_dialogs import (BootStickDialog, InstallDialog, IsoDetailsDialog, UploadDialog,  # noqa: E402
                                       choose_isos)
from okula_recovery.restore_dialog import RestoreDialog  # noqa: E402
from okula_recovery.stick_dialog import StickDialog  # noqa: E402
from okula_recovery.uikit import (ask_text, confirm, confirm_error, make_tree, pane_title, rgba_hex,  # noqa: E402
                                  run_async, scrolled, svg_pixbuf)

ASSETS = Path(__file__).resolve().parent / "assets"
NAS_POLL = 30  # Sekunden zwischen den NAS-Statusabfragen

# Icons im Image-Baum je nach Herkunft (eigene SVGs in assets/icons, siehe App.do_activate)
IMAGE_ICONS = {"Disk-Image": "okula-image", "Clonezilla": "okula-image-clonezilla"}
FILE_IMAGE_ICON = "text-x-generic-symbolic"
OS_ICONS = {"windows": "okula-os-windows", "linux": "okula-os-linux", "other": "okula-os-other"}

# Gerät gilt als getrennt, wenn so lange kein Beacon seines Agents kam
AGENT_TIMEOUT = 15

CSS = b"""
.pane-title { font-weight: bold; font-size: 115%; }
.status-ok { color: #2e7d32; font-weight: bold; }
.status-fail { color: #c62828; font-weight: bold; }
.status-idle { color: #757575; }
.nas-bar { padding: 4px 8px; border-radius: 4px; background-color: alpha(currentColor, 0.06); }
.device-name { font-weight: bold; font-size: 120%; }
"""


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Okula Recovery Tool")
        self.set_default_size(1280, 760)
        self.maximize()  # Arbeitsplatz-Tool: ganzer Bildschirm, F11 = Vollbild ohne Titelleiste
        self._fullscreen = False
        self.connect("key-press-event", self._on_key)
        self.connect("window-state-event", self._on_window_state)
        self.connect("delete-event", self._on_delete)
        self.cfg = config.load()
        self.key = agentclient.load_or_create_key()
        self.store = devices.DeviceStore()          # erfasste Geräte, lokal auf dem Server
        self.jobs = jobs.JobManager(on_change=lambda job: GLib.idle_add(self._on_job_change, job))
        self.agents: dict[str, discovery.AgentInfo] = {}  # Agent-ID → letzter Beacon (nur verbundene)
        self.device_of_agent: dict[str, str] = {}   # Agent-ID → Geräte-ID
        self.online: dict[str, str] = {}            # Geräte-ID → Agent-ID der verbundenen Geräte
        self.inv_seen: dict[str, int] = {}          # Agent-ID → zuletzt geholte Inventar-Version
        self.inv_pending: set[str] = set()
        self.device_windows: dict[str, DeviceWindow] = {}
        self._win_state: dict[str, tuple] = {}
        self._devices_loaded = False
        self._dev_expand_after: str | None = None
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
        paned.pack1(self._build_device_pane(), resize=True, shrink=False)
        paned.pack2(self._build_storage_pane(), resize=True, shrink=False)
        paned.set_position(760)

        self.statusbar = Gtk.Statusbar()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(self._build_menubar(), False, False, 0)
        root.pack_start(paned, True, True, 0)
        root.pack_start(self.statusbar, False, False, 0)
        self.add(root)

        self.refresh_devices()
        self._start_listener()
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
            ("Gerät ö_ffnen …", self.on_open_device, "<Control>o"),
            ("_Disk-Image erstellen …", lambda: self._with_device(self.start_image), None),
            ("Image _zurückspielen …", lambda: self._with_device(self.start_restore), None),
            ("_OS installieren …", lambda: self._with_device(self.start_install), None),
            ("_Inventar neu einlesen", lambda: self._with_device(self.refresh_inventory), None),
            ("Gerät _herunterfahren", lambda: self._with_device(lambda d: self.power(d, "poweroff")), None),
            None,
            ("_Restore-Stick aus Image …", lambda: self.on_restore_stick(None), None),
            ("IS_O hinzufügen …", self.on_add_iso, None),
            ("_Boot-Stick aus ISO …", self.on_boot_stick, None),
            ("Images _aktualisieren", self.refresh_images, "F5"),
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
                "Ctrl+O\tGewähltes Gerät öffnen\n"
                "F5\tImages aktualisieren\n"
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
    # Art: unsorted/folder/image (Images), osroot/osfolder/iso (Betriebssysteme, Bereich „os“)
    C_ICON, C_NAME, C_TYPE, C_SIZE, C_DATE, C_BYTES, C_PATH, C_KIND, C_REL, C_AREA, C_TIP = range(11)
    DND_TARGET = "okula/archive-row"
    URI_TARGET = "text/uri-list"   # ISO-Dateien aus dem Dateimanager

    def _build_images_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        head = Gtk.Box(spacing=6)
        self.img_count = Gtk.Label(label="", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        head.pack_start(self.img_count, True, True, 0)
        self.img_buttons = {}
        for key, icon, tip, handler in (
                ("iso", "media-optical-symbolic", "ISO hinzufügen … (Betriebssysteme)", lambda _b: self.on_add_iso()),
                ("folder", "folder-new-symbolic", "Neuer Ordner (im gewählten Ordner, max. 3 Ebenen)",
                 self.on_new_archive_folder),
                ("rename", "document-edit-symbolic", "Umbenennen (Ordner bzw. ISO)", self.on_rename_archive_folder),
                ("delete", "user-trash-symbolic", "Löschen (Image, ISO bzw. leerer Ordner)", self.on_delete_image)):
            b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            b.set_tooltip_text(tip)
            b.connect("clicked", handler)
            head.pack_start(b, False, False, 0)
            self.img_buttons[key] = b
        btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_refresh.set_tooltip_text("Image-Liste neu laden")
        btn_refresh.connect("clicked", lambda _b: self.refresh_images())
        head.pack_start(btn_refresh, False, False, 0)
        box.pack_start(head, False, False, 0)

        # icon, Name, Typ, Grösse, Datum, Bytes, Pfad (Image/ISO), Art, Ordner-rel, Bereich, Tooltip
        self.image_store = Gtk.TreeStore(str, str, str, str, str, GObject.TYPE_INT64, str, str, str, str, str)
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
        col.set_min_width(220)
        for title, idx in (("Typ", self.C_TYPE), ("Grösse", self.C_SIZE), ("Datum", self.C_DATE)):
            cell = Gtk.CellRendererText()
            if idx == self.C_TYPE:  # „Windows-ISO · 2 Editionen“ darf gekürzt werden, der Name nicht
                cell.set_property("ellipsize", Pango.EllipsizeMode.END)
                cell.set_property("width-chars", 12)
            c = Gtk.TreeViewColumn(title, cell, text=idx)
            c.set_resizable(True)
            view.append_column(c)
        view.set_enable_tree_lines(True)
        view.set_tooltip_column(self.C_TIP)
        view.get_selection().connect("changed", self._on_image_selected)
        view.connect("row-activated", self._on_image_activated)
        view.connect("button-press-event", self._on_image_button)
        # Ziehen mit der Maus: Images und Ordner in Ordner bzw. nach „Nicht einsortiert“, ISOs zwischen
        # OS-Ordnern; ISO-Dateien aus dem Dateimanager werden hochgeladen
        target = [Gtk.TargetEntry.new(self.DND_TARGET, Gtk.TargetFlags.SAME_WIDGET, 0)]
        view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.MOVE)
        view.enable_model_drag_dest(target + [Gtk.TargetEntry.new(self.URI_TARGET, Gtk.TargetFlags.OTHER_APP, 1)],
                                    Gdk.DragAction.MOVE | Gdk.DragAction.COPY)
        view.connect("drag-data-get", self._on_drag_get)
        view.connect("drag-data-received", self._on_drag_received)
        self.image_view = view
        self._images_loaded = False
        self._expand_after_refresh: str | None = None
        self._expand_after_os: str | None = None
        self._isos: dict[str, oslib.IsoInfo] = {}
        box.pack_start(scrolled(view), True, True, 0)

        # Unter dem Baum: Legende der Icons, dann Sticks (Restore-Stick aus Image, Boot-Stick aus ISO)
        legend = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=12, max_children_per_line=6)
        for icon, label in (("okula-image", "Okula-Image"), ("okula-image-clonezilla", "Clonezilla"),
                            (FILE_IMAGE_ICON, "Image-Datei"), ("okula-os-windows", "Windows-ISO"),
                            ("okula-os-linux", "Linux-ISO"), ("okula-os-other", "Sonstige ISO")):
            item = Gtk.Box(spacing=4)
            item.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
            lbl = Gtk.Label(label=label)
            lbl.get_style_context().add_class("status-idle")
            item.pack_start(lbl, False, False, 0)
            legend.add(item)
        box.pack_start(legend, False, False, 0)
        bottom = Gtk.Box(spacing=6)
        self.btn_add_iso = Gtk.Button(label="ISO hinzufügen …")
        self.btn_add_iso.set_tooltip_text("ISO-Dateien aufs NAS hochladen (Betriebssysteme) – auch per Ziehen aus "
                                          "dem Dateimanager")
        self.btn_add_iso.connect("clicked", lambda _b: self.on_add_iso())
        bottom.pack_start(self.btn_add_iso, False, False, 0)
        self.btn_img_stick = Gtk.Button(label="Restore-Stick aus Image …", sensitive=False)
        self.btn_img_stick.set_tooltip_text("Bootfähigen USB-Stick mit dem gewählten Image erstellen – spielt es "
                                            "nach Rückfrage ohne Netzwerk zurück")
        self.btn_img_stick.connect("clicked", self.on_restore_stick)
        bottom.pack_end(self.btn_img_stick, False, False, 0)
        self.btn_boot_stick = Gtk.Button(label="Boot-Stick aus ISO …", sensitive=False)
        self.btn_boot_stick.set_tooltip_text("Installations- bzw. Live-Stick aus der gewählten ISO erstellen")
        self.btn_boot_stick.connect("clicked", lambda _b: self.on_boot_stick())
        bottom.pack_end(self.btn_boot_stick, False, False, 0)
        box.pack_start(bottom, False, False, 0)
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_markup("<small>Images und ISOs per Maus in Ordner ziehen · ISO-Dateien aus dem Dateimanager "
                        "hierher ziehen = hochladen · Doppelklick auf ISO = Details · Rechtsklick für weitere "
                        "Aktionen</small>")
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
        rel = model[it][self.C_REL] if it is not None else ""
        root_ok = self._nas_root() is not None
        own_osfolder = kind == "osfolder" and "/" in rel   # Kategorien bleiben fest
        self.img_buttons["iso"].set_sensitive(root_ok)
        self.btn_add_iso.set_sensitive(root_ok)
        self.img_buttons["folder"].set_sensitive(root_ok and kind != "osroot")
        self.img_buttons["rename"].set_sensitive(root_ok and (kind in ("folder", "iso") or own_osfolder))
        self.img_buttons["delete"].set_sensitive(root_ok and (kind in ("folder", "image", "iso") or own_osfolder))
        self.btn_img_stick.set_sensitive(kind == "image" and model[it][self.C_TYPE] in ("Disk-Image", "Clonezilla"))
        iso = self._selected_iso()
        self.btn_boot_stick.set_sensitive(iso is not None and bool(oslib.stick_modes(iso.meta)))

    def _selected_iso(self) -> oslib.IsoInfo | None:
        model, it = self._selected_image_row()
        if it is None or model[it][self.C_KIND] != "iso":
            return None
        return self._isos.get(model[it][self.C_PATH])

    def _on_image_activated(self, view, path, _col) -> None:
        if self.image_store[path][self.C_KIND] == "iso":
            iso = self._selected_iso()
            if iso:
                IsoDetailsDialog(self, iso)
            return
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

        if model[it][self.C_AREA] == "os" if it is not None else False:
            self._os_menu(menu, model[it][self.C_KIND], model[it][self.C_REL])
            menu.show_all()
            menu.popup_at_pointer(event)
            return True
        add("Neuer Ordner …", self.on_new_archive_folder)
        if kind == "folder":
            add("Umbenennen …", self.on_rename_archive_folder)
            add("Löschen (nur leer)", self.on_delete_image)
        if kind == "image":
            if model[it][self.C_AREA] == "archive":
                add("Nach „Nicht einsortiert“", self.on_unsort_image)
            add("Restore-Stick aus Image …", self.on_restore_stick,
                model[it][self.C_TYPE] in ("Disk-Image", "Clonezilla"))
            add("Löschen …", self.on_delete_image)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _os_menu(self, menu: Gtk.Menu, kind: str, rel: str) -> None:
        def add(label, handler, sensitive=True):
            item = Gtk.MenuItem(label=label, sensitive=sensitive)
            item.connect("activate", lambda _i: handler())
            menu.append(item)

        if kind == "iso":
            iso = self._selected_iso()
            add("Details und Prüfsummen …", lambda: iso and IsoDetailsDialog(self, iso), iso is not None)
            add("Boot-Stick erstellen …", self.on_boot_stick, iso is not None and bool(oslib.stick_modes(iso.meta)))
            add("Auf Gerät installieren …", lambda: self.install_iso_on_device(iso),
                iso is not None and oslib.installable(iso.meta))
            menu.append(Gtk.SeparatorMenuItem())
            add("Umbenennen …", lambda: self.on_rename_archive_folder(None))
            add("Löschen …", lambda: self.on_delete_image(None))
            return
        add("ISO hinzufügen …", lambda: self.on_add_iso(rel if kind == "osfolder" else None))
        if kind == "osfolder":
            add("Neuer Ordner …", lambda: self.on_new_archive_folder(None), len(rel.split("/")) < oslib.MAX_DEPTH)
            if "/" in rel:
                add("Umbenennen …", lambda: self.on_rename_archive_folder(None))
                add("Löschen (nur leer)", lambda: self.on_delete_image(None))

    # ---------- Betriebssysteme (ISOs) ----------

    def on_add_iso(self, dest_rel: str | None = None) -> None:
        root = self._nas_root()
        if root is None:
            confirm_error(self, "NAS ist nicht verbunden – Menü → NAS-Verbindung …")
            return
        if dest_rel is None:
            model, it = self._selected_image_row()
            if it is not None and model[it][self.C_KIND] in ("osfolder", "iso"):
                dest_rel = model[it][self.C_REL]
        files = choose_isos(self)
        if files:
            self.upload_isos(files, dest_rel)

    def upload_isos(self, files: list[str], dest_rel: str | None) -> None:
        root = self._nas_root()
        if root is None:
            return
        self._expand_after_os = dest_rel or ""

        def done() -> None:
            self.refresh_images()
            self.refresh_nas_status()

        UploadDialog(self, root, files, dest_rel, done)

    def on_boot_stick(self) -> None:
        iso = self._selected_iso()
        if iso is None:
            self.status("Zuerst rechts unter „Betriebssysteme“ eine ISO wählen")
            return
        BootStickDialog(self, iso)

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
        model, it = self._selected_image_row()
        if it is not None and model[it][self.C_AREA] == "os":
            parent = model[it][self.C_REL]
            if not parent:
                confirm_error(self, "Eigene Ordner bitte in Windows, Linux oder Sonstige anlegen.")
                return
            if len(parent.split("/")) >= oslib.MAX_DEPTH:
                confirm_error(self, f"„{parent}“ liegt schon auf Ebene {oslib.MAX_DEPTH}.")
                return
            name = ask_text(self, "Neuer Ordner", f"Name des neuen Ordners in „{parent}“:")
            if name:
                self._expand_after_os = parent
                self._archive_op(lambda: oslib.make_folder(root, parent, name), f"Ordner „{name.strip()}“ angelegt")
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
        if root is None or it is None:
            return
        kind, rel = model[it][self.C_KIND], model[it][self.C_REL]
        if kind == "iso":
            path = model[it][self.C_PATH]
            old = os.path.basename(path)
            new = ask_text(self, "ISO umbenennen", f"Neuer Name für „{old}“:", old)
            if new and new.strip() != old:
                self._archive_op(lambda: oslib.rename_iso(root, path, new), f"Umbenannt in „{new.strip()}“")
            return
        if kind == "osfolder" and "/" in rel:
            old = rel.rsplit("/", 1)[-1]
            new = ask_text(self, "Ordner umbenennen", f"Neuer Name für „{old}“:", old)
            if new and new.strip() != old:
                self._expand_after_os = rel.rsplit("/", 1)[0]
                self._archive_op(lambda: oslib.rename_folder(root, rel, new), f"Umbenannt in „{new.strip()}“")
            return
        if kind != "folder":
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
        if root is not None and selection.get_target().name() == self.URI_TARGET:
            self._drop_files(view, x, y, selection.get_uris())
            return
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
            dest_rel = row[self.C_REL] if row[self.C_KIND] in ("folder", "image", "osfolder", "iso") else ""
        self.drop(model[src][self.C_KIND], model[src][self.C_AREA], model[src][self.C_REL],
                  model[src][self.C_PATH], model[src][self.C_NAME], dest_area, dest_rel)

    def _drop_files(self, view, x: int, y: int, uris: list[str]) -> None:
        """Dateien aus dem Dateimanager: ISOs hochladen (in den OS-Ordner unter der Maus, sonst automatisch)."""
        files = [GLib.filename_from_uri(u)[0] for u in uris if u.startswith("file://")]
        isos = [f for f in files if oslib.is_iso_name(os.path.basename(f)) and os.path.isfile(f)]
        if not isos:
            self.status("Nur ISO- und IMG-Dateien können hier hochgeladen werden")
            return
        hit = view.get_dest_row_at_pos(x, y)
        dest_rel = None
        if hit is not None:
            row = self.image_store[hit[0]]
            if row[self.C_KIND] in ("osfolder", "iso"):
                dest_rel = row[self.C_REL]
        self.upload_isos(isos, dest_rel)

    def drop(self, kind: str, area: str, rel: str, path: str, name: str, dest_area: str, dest_rel: str) -> None:
        """Ziel einer Maus-Verschiebung auswerten (auch für Tests ohne echte Maus)."""
        root = self._nas_root()
        if root is None:
            return
        if kind == "iso":
            if dest_area != "os" or not dest_rel:
                self.status("ISOs bitte in einen Ordner unter „Betriebssysteme“ ziehen")
            elif dest_rel != rel:
                self._expand_after_os = dest_rel
                self._archive_op(lambda: oslib.move_iso(root, path, dest_rel), f"Verschoben nach „{dest_rel}“")
            return
        if area == "os" or dest_area == "os":
            self.status("Images und Betriebssysteme sind getrennt – nur innerhalb des Bereichs verschieben")
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
        if model[it][self.C_KIND] == "osfolder" and "/" in model[it][self.C_REL]:
            rel = model[it][self.C_REL]
            self._archive_op(lambda: oslib.delete_folder(root, rel), f"Ordner „{rel}“ gelöscht")
            return
        if model[it][self.C_KIND] == "iso":
            path = model[it][self.C_PATH]
            if confirm(self, f"„{os.path.basename(path)}“ endgültig löschen?",
                       f"{model[it][self.C_NAME]} · {model[it][self.C_SIZE]}\n\n"
                       "Das NAS hat keinen Papierkorb für das Tool – gelöschte Daten sind weg."):
                self._archive_op(lambda: oslib.delete_iso(root, path), f"„{os.path.basename(path)}“ gelöscht")
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
        def work():
            tree = archive.scan(mp)
            try:
                oslib.ensure_layout(mp)  # OS/Windows, OS/Linux, OS/Sonstige anlegen
                systems = oslib.scan(mp)
            except (OSError, oslib.OsLibError, nasfiles.FileError) as e:
                systems = e
            return tree, systems

        run_async(work, self._on_images)

    def _image_row(self, img: nas.ImageInfo, rel: str, area: str) -> list:
        return [IMAGE_ICONS.get(img.kind, FILE_IMAGE_ICON), img.name, img.kind, nas.format_size(img.size),
                img.mtime.strftime("%d.%m.%Y %H:%M"), img.size, str(img.path), "image", rel, area, str(img.path)]

    def _iso_row(self, iso: oslib.IsoInfo) -> list:
        sha = iso.meta.get("sha256", "")
        tip = f"{iso.name}\n{iso.title} · {oslib.describe(iso.meta)}" + (f"\nSHA-256 {sha}" if sha else "")
        return [OS_ICONS.get(iso.family, "okula-os-other"), iso.display, oslib.describe(iso.meta),
                nas.format_size(iso.size), iso.mtime.strftime("%d.%m.%Y %H:%M"), iso.size, str(iso.path), "iso",
                iso.rel, "os", tip]

    def _add_os_tree(self, systems, keys: set[str]) -> int:
        store = self.image_store
        self._isos = {}
        if isinstance(systems, Exception):
            store.append(None, ["dialog-warning-symbolic", "Betriebssysteme: nicht lesbar", "", "", "", 0, "",
                                "osroot", "", "os", str(systems)])
            return 0
        isos = [i for f in systems for i in f.all_isos()]
        self._isos = {str(i.path): i for i in isos}
        total = sum(i.size for i in isos)
        root = store.append(None, ["media-optical-symbolic", f"Betriebssysteme ({len(isos)})", "",
                                   nas.format_size(total) if total else "", "", total, "", "osroot", "", "os",
                                   f"ISO-Dateien in NAS: /{oslib.OS_DIR} – „ISO hinzufügen …“ oder Dateien "
                                   "hierher ziehen"])

        def add(parent, folder: oslib.OsFolder) -> None:
            size = folder.size()
            it = store.append(parent, ["folder-symbolic", f"{folder.name} ({folder.count()})", "Ordner",
                                       nas.format_size(size) if size else "", "", size, "", "osfolder",
                                       folder.rel, "os", f"NAS: /{oslib.OS_DIR}/{folder.rel}"])
            for sub in folder.folders:
                add(it, sub)
            for iso in folder.isos:
                store.append(it, self._iso_row(iso))

        for folder in systems:
            add(root, folder)
        if self._expand_after_os is not None:
            parts = self._expand_after_os.split("/") if self._expand_after_os else []
            keys |= {"osroot:"} | {"osfolder:" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)}
            self._expand_after_os = None
        return len(isos)

    def _on_images(self, result) -> None:
        if isinstance(result, Exception):
            self.status(f"Images konnten nicht gelesen werden: {result}")
            return
        tree, systems = result
        keys = self._expanded_keys() if self._images_loaded else {"unsorted:", "osroot:"}
        if self._expand_after_refresh is not None:
            parts = self._expand_after_refresh.split("/") if self._expand_after_refresh else []
            keys |= {"folder:" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)}
            self._expand_after_refresh = None
        store = self.image_store
        store.clear()
        unsorted = store.append(None, ["folder-download-symbolic", f"Nicht einsortiert ({len(tree.unsorted)})", "",
                                       nas.format_size(sum(i.size for i in tree.unsorted)), "", 0, "", "unsorted",
                                       "", "unsorted", ""])
        for img in tree.unsorted:  # neueste zuerst
            store.append(unsorted, self._image_row(img, "", "unsorted"))

        def add(parent, folder: archive.Folder) -> None:
            total = folder.size()  # inklusive Unterordner
            it = store.append(parent, ["folder-symbolic", f"{folder.name} ({folder.count()})", "Ordner",
                                       nas.format_size(total) if total else "", "", total, "", "folder",
                                       folder.rel, "archive", ""])
            for sub in folder.folders:
                add(it, sub)
            for img in folder.images:
                store.append(it, self._image_row(img, folder.rel, "archive"))

        for folder in tree.folders:
            add(None, folder)
        n_isos = self._add_os_tree(systems, keys)
        self._restore_expanded(keys)
        self._images_loaded = True
        self.img_count.set_text(f"{len(tree.all_images())} Images · {len(tree.unsorted)} nicht einsortiert · "
                                f"{n_isos} ISOs")
        self._on_image_selected(self.image_view.get_selection())

    # ---------- linke Seite: Geräte ----------

    # Spalten des Gerätebaums: LED bzw. Ordner-Icon, Name, Status, Betriebssystem, zuletzt verbunden, IP,
    # Geräte-ID, Art (unsorted/folder/device), Ordner-rel, Fortschritt 0–100, Balken-Text (leer), Balken zeigen
    D_ICON, D_NAME, D_STATUS, D_OS, D_SEEN, D_IP, D_ID, D_KIND, D_REL, D_PROG, D_PCT, D_BAR = range(12)
    NO_PROGRESS = [0, "", False]
    DEV_DND_TARGET = "okula/device-row"

    def _build_device_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        head = Gtk.Box(spacing=6)
        head.pack_start(pane_title("Geräte"), False, False, 0)
        self.dev_count = Gtk.Label(label="", xalign=0, ellipsize=Pango.EllipsizeMode.END, margin_start=8)
        self.dev_count.get_style_context().add_class("status-idle")
        head.pack_start(self.dev_count, True, True, 0)
        self.dev_buttons = {}
        for key, icon, tip, handler in (
                ("folder", "folder-new-symbolic", "Neuer Ordner (im gewählten Ordner, max. 3 Ebenen)",
                 self.on_new_device_folder),
                ("rename", "document-edit-symbolic", "Umbenennen (Ordner oder Gerät)", self.on_rename_device_entry),
                ("delete", "user-trash-symbolic", "Löschen (leerer Ordner bzw. nicht verbundenes Gerät)",
                 self.on_delete_device_entry)):
            b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            b.set_tooltip_text(tip)
            b.connect("clicked", handler)
            head.pack_start(b, False, False, 0)
            self.dev_buttons[key] = b
        box.pack_start(head, False, False, 0)

        self.device_store = Gtk.TreeStore(str, str, str, str, str, str, str, str, str, int, str, bool)
        view = Gtk.TreeView(model=self.device_store)
        col = Gtk.TreeViewColumn("Gerät")
        icon = Gtk.CellRendererPixbuf()
        col.pack_start(icon, False)
        col.add_attribute(icon, "icon-name", self.D_ICON)
        text = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col.pack_start(text, True)
        col.add_attribute(text, "text", self.D_NAME)
        col.set_expand(True)
        col.set_resizable(True)
        col.set_min_width(200)
        view.append_column(col)
        # Status: solange etwas läuft, Fortschrittsbalken mit Prozent, daneben Auftrag und Restzeit
        col = Gtk.TreeViewColumn("Status")
        bar = Gtk.CellRendererProgress()
        bar.set_fixed_size(90, -1)
        col.pack_start(bar, False)
        for attr, idx in (("value", self.D_PROG), ("text", self.D_PCT), ("visible", self.D_BAR)):
            col.add_attribute(bar, attr, idx)
        text = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col.pack_start(text, True)
        col.add_attribute(text, "markup", self.D_STATUS)
        col.set_min_width(340)
        col.set_resizable(True)
        view.append_column(col)
        for title, idx, chars in (("Betriebssystem", self.D_OS, 18),
                                  ("Zuletzt verbunden", self.D_SEEN, 16), ("IP", self.D_IP, 14)):
            cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, width_chars=chars)
            c = Gtk.TreeViewColumn(title, cell, text=idx)
            c.set_resizable(True)
            view.append_column(c)
        view.set_enable_tree_lines(True)
        view.get_selection().connect("changed", lambda _s: self._on_device_selected())
        view.connect("row-activated", self._on_device_activated)
        view.connect("button-press-event", self._on_device_button)
        target = [Gtk.TargetEntry.new(self.DEV_DND_TARGET, Gtk.TargetFlags.SAME_WIDGET, 0)]
        view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.MOVE)
        view.enable_model_drag_dest(target, Gdk.DragAction.MOVE)
        view.connect("drag-data-get", self._on_drag_get)
        view.connect("drag-data-received", self._on_device_drag_received)
        self.device_view = view
        box.pack_start(scrolled(view), True, True, 0)

        actions = Gtk.Box(spacing=6)
        self.btn_open = Gtk.Button(label="Gerät öffnen …", sensitive=False)
        self.btn_open.set_tooltip_text("Alle Infos, Aufträge mit Log, Verlauf und Notizen (auch Doppelklick)")
        self.btn_open.connect("clicked", lambda _b: self.on_open_device())
        self.btn_image = Gtk.Button(label="Disk-Image erstellen …", sensitive=False)
        self.btn_image.set_tooltip_text("Ganze Disk des gewählten Geräts aufs NAS sichern (läuft im Hintergrund)")
        self.btn_image.connect("clicked", lambda _b: self._with_device(self.start_image))
        self.btn_restore = Gtk.Button(label="Image zurückspielen …", sensitive=False)
        self.btn_restore.set_tooltip_text("Disk-Image vom NAS auf eine Disk des gewählten Geräts schreiben")
        self.btn_restore.connect("clicked", lambda _b: self._with_device(self.start_restore))
        for b in (self.btn_open, self.btn_image, self.btn_restore):
            actions.pack_start(b, False, False, 0)
        self.btn_power = Gtk.Button(label="Herunterfahren", sensitive=False)
        self.btn_power.set_tooltip_text("Gewähltes Gerät herunterfahren (Agent-Stick)")
        self.btn_power.connect("clicked", lambda _b: self._with_device(lambda d: self.power(d, "poweroff")))
        actions.pack_end(self.btn_power, False, False, 0)
        box.pack_start(actions, False, False, 0)

        legend = Gtk.Box(spacing=12)
        for icon, label in (("okula-led-on", "verbunden"), ("okula-led-off", "nicht verbunden")):
            item = Gtk.Box(spacing=4)
            item.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
            lbl = Gtk.Label(label=label)
            lbl.get_style_context().add_class("status-idle")
            item.pack_start(lbl, False, False, 0)
            legend.pack_start(item, False, False, 0)
        hint = Gtk.Label(xalign=1, wrap=True)
        hint.set_markup("<small>Doppelklick öffnet das Gerät · per Maus in Ordner ziehen</small>")
        hint.get_style_context().add_class("status-idle")
        legend.pack_end(hint, False, False, 0)
        box.pack_start(legend, False, False, 0)
        return box

    # ---------- Geräte: Anzeige ----------

    def online_agent(self, dev: devices.Device) -> discovery.AgentInfo | None:
        aid = self.online.get(dev.id)
        return self.agents.get(aid) if aid else None

    def device_status(self, dev: devices.Device) -> str:
        what, fraction, eta = self.device_progress(dev)
        pct = f" {fraction * 100:.0f} %" if fraction is not None else ""
        return " · ".join(p for p in (what + pct, eta) if p)

    def device_progress(self, dev: devices.Device) -> tuple[str, float | None, str]:
        """(was läuft, Fortschritt 0..1, Restzeit) – Aufträge des Tools zuerst, dann die Meldung des Agents."""
        what, fraction, eta = self.jobs.parts(dev.id)
        agent = self.online_agent(dev)
        if what or agent is None:
            return what or "nicht verbunden", fraction, eta
        if agent.agent_id in self.inv_pending:
            return "Inventar wird gelesen …", None, ""
        if not agent.control_port:
            return "Agent-Stick veraltet", None, ""
        if agent.job:  # z. B. Image-Prüfung, die das Tool dem Agent meldet
            return agent.job, agent.progress, ""
        return agent.status, None, ""

    def _device_values(self, dev: devices.Device) -> list:
        agent = self.online_agent(dev)
        what, fraction, eta = self.device_progress(dev)
        bar = fraction is not None
        status = GLib.markup_escape_text(" · ".join(p for p in (what, eta) if p))
        if bar:
            status = f"<b>{fraction * 100:.0f} %</b>  {status}"
        return ["okula-led-on" if agent else "okula-led-off", dev.name, status,
                dev.os_name or "–", "jetzt" if agent else devices.short_time(dev.last_seen) or "–",
                agent.ip if agent else dev.last_ip, dev.id, "device", dev.folder,
                int(fraction * 100) if bar else 0, "", bar]

    def refresh_devices(self) -> None:
        """Baum neu aufbauen (neue Geräte, Ordner, Umbenennen) – Auf- und Zuklappen bleibt erhalten."""
        view, store = self.device_view, self.device_store
        keys = self._dev_expanded() if self._devices_loaded else {"unsorted:"}
        if self._dev_expand_after is not None:
            parts = self._dev_expand_after.split("/") if self._dev_expand_after else []
            keys |= {"folder:" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)}
            self._dev_expand_after = None
        model, it = view.get_selection().get_selected()
        selected = (model[it][self.D_KIND], model[it][self.D_ID] or model[it][self.D_REL]) if it else None
        store.clear()
        new = sorted(self.store.in_folder(""), key=lambda d: d.first_seen, reverse=True)  # neueste zuerst
        unsorted = store.append(None, ["folder-download-symbolic", f"Neu / nicht einsortiert ({len(new)})",
                                       "", "", "", "", "", "unsorted", ""] + self.NO_PROGRESS)
        for dev in new:
            store.append(unsorted, self._device_values(dev))

        def count(rel: str) -> int:
            return sum(1 for d in self.store.devices.values() if d.folder == rel or d.folder.startswith(rel + "/"))

        def add(parent, rel: str) -> None:
            it = store.append(parent, ["folder-symbolic", f"{rel.rsplit('/', 1)[-1]} ({count(rel)})", "", "", "",
                                       "", "", "folder", rel] + self.NO_PROGRESS)
            for sub in self.store.folders:
                if sub.rsplit("/", 1)[0] == rel and "/" in sub:
                    add(it, sub)
            for dev in self.store.in_folder(rel):
                store.append(it, self._device_values(dev))

        for rel in self.store.folders:
            if "/" not in rel:
                add(None, rel)

        def walk(it):
            while it is not None:
                row = store[it]
                if row[self.D_KIND] + ":" + row[self.D_REL] in keys and row[self.D_KIND] != "device":
                    view.expand_row(store.get_path(it), False)
                if selected and (row[self.D_KIND], row[self.D_ID] or row[self.D_REL]) == selected:
                    view.expand_to_path(store.get_path(it))
                    view.get_selection().select_iter(it)
                walk(store.iter_children(it))
                it = store.iter_next(it)
        walk(store.get_iter_first())
        self._devices_loaded = True
        self.update_device_rows()

    def update_device_rows(self) -> None:
        """LED, Status und IP der Zeilen nachführen (bei jedem Beacon und Auftrags-Fortschritt)."""
        store = self.device_store

        def walk(it):
            while it is not None:
                row = store[it]
                dev = self.store.devices.get(row[self.D_ID]) if row[self.D_KIND] == "device" else None
                if dev is not None:
                    for i, v in enumerate(self._device_values(dev)):
                        if row[i] != v:
                            row[i] = v
                walk(store.iter_children(it))
                it = store.iter_next(it)
        walk(store.get_iter_first())
        total, online = len(self.store.devices), len(self.online)
        self.dev_count.set_text(f"{total} Gerät{'e' if total != 1 else ''} · {online} verbunden")
        for dev_id, win in list(self.device_windows.items()):
            dev = self.store.devices.get(dev_id)
            if dev is not None:
                state = (dev.id in self.online, self.device_status(dev))
                if self._win_state.get(dev_id) != state:
                    self._win_state[dev_id] = state
                    win.refresh_head()
        self._on_device_selected()

    def _dev_expanded(self) -> set[str]:
        keys = set()

        def walk(it):
            while it is not None:
                row = self.device_store[it]
                if self.device_view.row_expanded(self.device_store.get_path(it)):
                    keys.add(row[self.D_KIND] + ":" + row[self.D_REL])
                walk(self.device_store.iter_children(it))
                it = self.device_store.iter_next(it)
        walk(self.device_store.get_iter_first())
        return keys

    def _selected_device_row(self):
        return self.device_view.get_selection().get_selected()

    def _selected_device(self) -> devices.Device | None:
        model, it = self._selected_device_row()
        if it is None or model[it][self.D_KIND] != "device":
            return None
        return self.store.devices.get(model[it][self.D_ID])

    def _with_device(self, action) -> None:
        dev = self._selected_device()
        if dev is None:
            self.status("Zuerst links ein Gerät wählen")
            return
        action(dev)

    def _on_device_selected(self) -> None:
        model, it = self._selected_device_row()
        kind = model[it][self.D_KIND] if it is not None else ""
        dev = self._selected_device()
        agent = self.online_agent(dev) if dev else None
        ready = agent is not None and agent.control_port > 0
        self.btn_open.set_sensitive(dev is not None)
        for b in (self.btn_image, self.btn_restore, self.btn_power):
            b.set_sensitive(ready)
        self.dev_buttons["rename"].set_sensitive(kind in ("folder", "device"))
        self.dev_buttons["delete"].set_sensitive(kind == "folder" or (dev is not None and agent is None))
        for label in ("Gerät öffnen …", "Disk-Image erstellen …", "Image zurückspielen …", "OS installieren …",
                      "Inventar neu einlesen", "Gerät herunterfahren"):
            if label in getattr(self, "menu_items", {}):
                self.menu_items[label].set_sensitive(dev is not None if label == "Gerät öffnen …" else ready)

    def _on_device_activated(self, view, path, _col) -> None:
        row = self.device_store[path]
        if row[self.D_KIND] == "device":
            self.on_open_device()
        elif view.row_expanded(path):
            view.collapse_row(path)
        else:
            view.expand_row(path, False)

    def _on_device_button(self, view, event) -> bool:
        if event.button != 3:
            return False
        hit = view.get_path_at_pos(int(event.x), int(event.y))
        if hit:
            view.get_selection().select_path(hit[0])
        model, it = self._selected_device_row()
        kind = model[it][self.D_KIND] if it is not None else ""
        dev = self._selected_device()
        agent = self.online_agent(dev) if dev else None
        ready = agent is not None and agent.control_port > 0
        menu = Gtk.Menu()

        def add(label, handler, sensitive=True):
            item = Gtk.MenuItem(label=label, sensitive=sensitive)
            item.connect("activate", lambda _i: handler())
            menu.append(item)

        if dev is not None:
            add("Öffnen …", self.on_open_device)
            add("Disk-Image erstellen …", lambda: self.start_image(dev), ready)
            add("Image zurückspielen …", lambda: self.start_restore(dev), ready)
            add("OS installieren …", lambda: self.start_install(dev), ready)
            add("Inventar neu einlesen", lambda: self.refresh_inventory(dev), ready)
            add("Herunterfahren", lambda: self.power(dev, "poweroff"), ready)
            add("Neu starten", lambda: self.power(dev, "reboot"), ready)
            menu.append(Gtk.SeparatorMenuItem())
            add("Umbenennen …", lambda: self.on_rename_device_entry(None))
            if dev.folder:
                add("Nach „Neu / nicht einsortiert“", lambda: self._device_op(
                    lambda: self.store.move_device(dev, ""), "Nach „Neu / nicht einsortiert“ verschoben"))
            add("Aus der Liste löschen …", lambda: self.on_delete_device_entry(None), agent is None)
            menu.append(Gtk.SeparatorMenuItem())
        add("Neuer Ordner …", lambda: self.on_new_device_folder(None))
        if kind == "folder":
            add("Ordner umbenennen …", lambda: self.on_rename_device_entry(None))
            add("Ordner löschen (nur leer)", lambda: self.on_delete_device_entry(None))
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    # ---------- Geräte: Ordner, Umbenennen, Löschen, Ziehen ----------

    def _device_op(self, op, done_msg: str) -> bool:
        try:
            op()
        except (devices.DeviceError, nasfiles.FileError, OSError) as e:
            self.status(f"Fehler: {e}")
            confirm_error(self, str(e))
            return False
        self.status(done_msg)
        self.refresh_devices()
        return True

    def _device_target_folder(self) -> str:
        model, it = self._selected_device_row()
        if it is None:
            return ""
        return model[it][self.D_REL] if model[it][self.D_KIND] in ("folder", "device") else ""

    def on_new_device_folder(self, _btn) -> None:
        parent = self._device_target_folder()
        if parent and len(parent.split("/")) >= devices.MAX_DEPTH:
            confirm_error(self, f"„{parent}“ liegt schon auf Ebene {devices.MAX_DEPTH} – "
                                "dort sind keine weiteren Unterordner möglich.")
            return
        where = f" in „{parent}“" if parent else " (oberste Ebene)"
        name = ask_text(self, "Neuer Ordner", f"Name des neuen Ordners{where}:")
        if name:
            self._dev_expand_after = parent
            self._device_op(lambda: self.store.make_folder(parent, name), f"Ordner „{name.strip()}“ angelegt")

    def on_rename_device_entry(self, _btn) -> None:
        model, it = self._selected_device_row()
        if it is None:
            return
        dev = self._selected_device()
        if dev is not None:
            new = ask_text(self, "Gerät umbenennen", f"Neuer Name für „{dev.name}“:", dev.name)
            if new and new.strip() != dev.name:
                self._device_op(lambda: self.store.update(dev, name=new), f"Umbenannt in „{new.strip()}“")
                win = self.device_windows.get(dev.id)
                if win:
                    win.name.set_text(dev.name)
                    win.refresh_head()
            return
        if model[it][self.D_KIND] != "folder":
            return
        rel = model[it][self.D_REL]
        old = rel.rsplit("/", 1)[-1]
        new = ask_text(self, "Ordner umbenennen", f"Neuer Name für „{old}“:", old)
        if new and new.strip() != old:
            self._dev_expand_after = rel.rsplit("/", 1)[0] if "/" in rel else ""
            self._device_op(lambda: self.store.rename_folder(rel, new), f"Umbenannt in „{new.strip()}“")

    def on_delete_device_entry(self, _btn) -> None:
        model, it = self._selected_device_row()
        if it is None:
            return
        if model[it][self.D_KIND] == "folder":
            rel = model[it][self.D_REL]
            self._device_op(lambda: self.store.delete_folder(rel), f"Ordner „{rel}“ gelöscht")
            return
        dev = self._selected_device()
        if dev is None:
            return
        if self.online_agent(dev) is not None or self.jobs.summary(dev.id):
            self.status("Verbundene Geräte und Geräte mit laufenden Aufträgen können nicht gelöscht werden")
            return
        if confirm(self, f"„{dev.name}“ aus der Geräteliste löschen?",
                   "Inventar, Verlauf und Notizen dieses Geräts gehen verloren. Images auf dem NAS bleiben.\n"
                   "Beim nächsten Start mit dem Agent-Stick wird das Gerät neu erfasst.", ok_label="Löschen"):
            win = self.device_windows.pop(dev.id, None)
            if win:
                win.destroy()
            self._device_op(lambda: self.store.delete(dev), f"„{dev.name}“ gelöscht")

    def _on_device_drag_received(self, view, context, x, y, selection, _info, time_) -> None:
        view.stop_emission_by_name("drag-data-received")
        Gtk.drag_finish(context, True, False, time_)
        data = selection.get_data()
        if not data:
            return
        model = self.device_store
        try:
            src = model.get_iter_from_string(data.decode())
        except (ValueError, TypeError):
            return
        hit = view.get_dest_row_at_pos(x, y)
        if hit is None:
            dest_kind, dest_rel = "folder", ""  # leere Fläche: oberste Ebene
        else:
            row = model[hit[0]]
            dest_kind, dest_rel = row[self.D_KIND], row[self.D_REL]
            if dest_kind == "device" and not dest_rel:
                dest_kind = "unsorted"
        self.drop_device(model[src][self.D_KIND], model[src][self.D_ID], model[src][self.D_REL], dest_kind, dest_rel)

    def drop_device(self, kind: str, dev_id: str, rel: str, dest_kind: str, dest_rel: str) -> None:
        """Ziel einer Maus-Verschiebung im Gerätebaum (auch für Tests ohne echte Maus)."""
        if kind == "device":
            dev = self.store.devices.get(dev_id)
            target = "" if dest_kind == "unsorted" else dest_rel
            if dev is None or dev.folder == target:
                return
            self._dev_expand_after = target
            self._device_op(lambda: self.store.move_device(dev, target),
                            f"Verschoben nach „{target or 'Neu / nicht einsortiert'}“")
        elif kind == "folder":
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            if dest_kind == "unsorted":
                self.status("Ordner können nicht nach „Neu / nicht einsortiert“ verschoben werden")
            elif dest_rel not in (parent, rel):
                self._dev_expand_after = dest_rel
                self._device_op(lambda: self.store.move_folder(rel, dest_rel),
                                f"Ordner „{rel.rsplit('/', 1)[-1]}“ verschoben")

    # ---------- USB-Agent: Erkennen und Erfassen ----------

    def _start_listener(self) -> None:
        self.listener = discovery.Listener(lambda info: GLib.idle_add(self._on_agent, info))
        try:
            self.listener.start()
        except OSError as e:
            self.status(f"USB-Agent-Erkennung nicht aktiv (UDP {discovery.PORT}): {e}")
            return
        GLib.timeout_add_seconds(5, self._expire_agents)

    def _device_for_agent(self, info: discovery.AgentInfo) -> devices.Device | None:
        dev = self.store.devices.get(self.device_of_agent.get(info.agent_id, ""))
        if dev is None:
            # Ohne Inventar nur über die Agent-ID (Board-UUID) – eine MAC kann von einem geteilten
            # USB-Netzwerkadapter stammen. Alte Sticks liefern kein Inventar: dort auch über die MAC.
            dev = self.store.match(agent_id=info.agent_id, mac="" if info.control_port else info.mac)
            if dev is not None:
                self.device_of_agent[info.agent_id] = dev.id
        return dev

    def _on_agent(self, info: discovery.AgentInfo) -> bool:
        aid = info.agent_id
        self.agents[aid] = info
        dev = self._device_for_agent(info)
        if dev is not None and self.online.get(dev.id) != aid:
            self._set_online(dev, aid)
        if info.control_port and aid not in self.inv_pending and self.inv_seen.get(aid) != info.inventory_version:
            self.fetch_inventory(info)
        elif not info.control_port and dev is None:
            # alter Stick ohne Steuerdienst: mit dem erfassen, was der Beacon meldet
            dev, _new = self.store.register(aid, info.ip, info.mac, beacon_inventory(info), info.hardware or info.ip)
            self.device_of_agent[aid] = dev.id
            self._set_online(dev, aid)
            self.refresh_devices()
        self.update_device_rows()
        return False

    def fetch_inventory(self, info: discovery.AgentInfo, refresh: bool = False) -> None:
        aid, version, key = info.agent_id, info.inventory_version, self.key
        self.inv_pending.add(aid)
        self.update_device_rows()

        def done(result) -> None:
            self.inv_pending.discard(aid)
            self.inv_seen[aid] = version
            current = self.agents.get(aid, info)
            if isinstance(result, Exception):
                self.status(f"Inventar von {current.ip} nicht lesbar: {result}")
                if self._device_for_agent(current) is not None:
                    self.update_device_rows()
                    return
                inv = beacon_inventory(current)
            else:
                inv = result
            dev, new = self.store.register(aid, current.ip, current.mac, inv, current.hardware or current.ip)
            for dev_id, a in list(self.online.items()):
                if a == aid and dev_id != dev.id:  # vorläufige Zuordnung war falsch
                    del self.online[dev_id]
            self.device_of_agent[aid] = dev.id
            if aid in self.agents and self.online.get(dev.id) != aid:
                self._set_online(dev, aid)
            if new:
                self._dev_expand_after = ""
                self.status(f"Neues Gerät erfasst: {dev.name} ({current.ip}) – unter „Neu / nicht einsortiert“")
            elif refresh:
                self.status(f"Inventar von {dev.name} neu eingelesen")
            self.refresh_devices()
            win = self.device_windows.get(dev.id)
            if win:
                win.refresh()

        run_async(lambda: agentclient.get_inventory(info.ip, key, info.control_port, refresh), done)

    def _set_online(self, dev: devices.Device, aid: str) -> None:
        self.online[dev.id] = aid
        info = self.agents[aid]
        self.store.touch(dev, info.ip, True)
        note = " – Link-Local, im Netz gibt es kein DHCP" if info.ip.startswith("169.254.") else ""
        self.status(f"Gerät verbunden: {dev.name} ({info.ip}){note}")
        win = self.device_windows.get(dev.id)
        if win:
            win.refresh()

    def _expire_agents(self) -> bool:
        """Agents ohne Beacon gelten nach AGENT_TIMEOUT als getrennt – das Gerät bleibt in der Liste."""
        limit = time.time() - AGENT_TIMEOUT
        for aid, info in list(self.agents.items()):
            if info.last_seen >= limit:
                continue
            del self.agents[aid]
            self.inv_seen.pop(aid, None)  # beim nächsten Start Inventar neu holen
            for dev_id, a in list(self.online.items()):
                if a != aid:
                    continue
                del self.online[dev_id]
                dev = self.store.devices.get(dev_id)
                if dev is not None:
                    self.store.touch(dev, "", False)
                    self.status(f"{dev.name} getrennt – seit {AGENT_TIMEOUT} s keine Meldung")
                    win = self.device_windows.get(dev_id)
                    if win:
                        win.refresh()
        self.update_device_rows()
        return True

    # ---------- Geräte: Aktionen (auch aus dem Gerätefenster) ----------

    def on_open_device(self) -> None:
        dev = self._selected_device()
        if dev is not None:
            self.open_device(dev)

    def open_device(self, dev: devices.Device) -> DeviceWindow:
        win = self.device_windows.get(dev.id)
        if win is None:
            win = DeviceWindow(self, dev)
            self.device_windows[dev.id] = win
        win.present()
        return win

    def _ready_agent(self, dev: devices.Device, parent: Gtk.Window) -> discovery.AgentInfo | None:
        agent = self.online_agent(dev)
        if agent is None:
            confirm_error(parent, f"„{dev.name}“ ist nicht verbunden – Gerät mit dem Agent-Stick starten.")
        elif not agent.control_port:
            confirm_error(parent, "Der Agent-Stick dieses Geräts ist veraltet – Stick mit dem aktuellen Tool "
                                  "neu erstellen.")
        else:
            return agent
        return None

    def _parent_for(self, dev: devices.Device) -> Gtk.Window:
        return self.device_windows.get(dev.id) or self

    def start_image(self, dev: devices.Device) -> None:
        parent = self._parent_for(dev)
        agent = self._ready_agent(dev, parent)
        if agent is None:
            return
        root = self._nas_root()
        if root is None:
            confirm_error(parent, "NAS ist nicht verbunden – Menü → NAS-Verbindung …")
            return
        ImageDialog(parent, agent, root, name=dev.name,
                    start_job=lambda disk, name, shutdown: self._start_image_job(dev, agent, root, disk, name,
                                                                                  shutdown))

    def _start_image_job(self, dev, agent, root, disk: dict, name: str, shutdown: bool) -> None:
        source = {"hostname": agent.hostname, "mac": agent.mac, "vendor": agent.vendor, "product": agent.product,
                  "agent_id": agent.agent_id, "device_id": dev.id, "device_name": dev.name}

        def after(job, path, error) -> None:
            GLib.idle_add(self._after_job, dev.id, job, f"Disk-Image {disk['name']}", path, error, shutdown)

        work = jobs.image_work(agent.ip, self.key, agent.control_port, disk, root, name, source, after)
        self.jobs.start(dev.id, "image", disk["path"], f"Disk-Image {disk['name']} → {name}", work)
        self.open_device(dev).show_jobs()

    def start_restore(self, dev: devices.Device, preselect: str | None = None) -> None:
        parent = self._parent_for(dev)
        agent = self._ready_agent(dev, parent)
        if agent is None:
            return
        root = self._nas_root()
        if root is None:
            confirm_error(parent, "NAS ist nicht verbunden – Menü → NAS-Verbindung …")
            return
        if preselect is None:
            model, it = self.image_view.get_selection().get_selected()
            if it is not None and model[it][self.C_KIND] == "image":
                preselect = model[it][self.C_PATH]

        def start(image, source_disk, target, verify, shutdown, label) -> None:
            def after(job, path, error) -> None:
                GLib.idle_add(self._after_job, dev.id, job, f"Zurückspielen {label} → {target}", path, error,
                              shutdown)

            work = jobs.restore_work(agent.ip, self.key, agent.control_port, image, target, source_disk, verify,
                                     after)
            self.jobs.start(dev.id, "restore", target, f"Zurückspielen {label} → {target}", work)
            self.open_device(dev).show_jobs()

        RestoreDialog(parent, agent, root, start_job=start, preselect=preselect, device_name=dev.name)

    def start_install(self, dev: devices.Device, preselect: str | None = None) -> None:
        """Betriebssystem direkt aufs Gerät installieren (Medium aus „Betriebssysteme“ auf dem NAS)."""
        parent = self._parent_for(dev)
        agent = self._ready_agent(dev, parent)
        if agent is None:
            return
        if self._nas_root() is None:
            confirm_error(parent, "NAS ist nicht verbunden – Menü → NAS-Verbindung …")
            return
        isos = [i for i in self._isos.values() if oslib.installable(i.meta)]
        if not isos:
            confirm_error(parent, "Keine installierbare ISO unter „Betriebssysteme“ (Windows 10/11, Ubuntu Desktop "
                                  "ab 24.04, Debian) – zuerst rechts „ISO hinzufügen …“.")
            return
        if preselect is None:
            iso = self._selected_iso()
            preselect = str(iso.path) if iso else None

        def start(iso: oslib.IsoInfo, disk: dict, index: int | None, opts) -> None:
            if iso.family == "windows":
                edition = next((e["name"] for e in iso.meta["windows"]["editions"] if e["index"] == index), "")
                what = f"Windows-Installation {edition} → {disk['path']}"
                kind = "install"
            else:
                what = f"Linux-Installation {iso.title} → {disk['path']}"
                kind = "linux"

            def after(job, boot, error) -> None:
                GLib.idle_add(self._after_job, dev.id, job, what, boot, error, False)

            if kind == "install":
                work = jobs.install_work(agent.ip, self.key, agent.control_port, str(iso.path), index, opts,
                                         disk["path"], after)
            else:
                work = jobs.linux_install_work(agent.ip, self.key, agent.control_port, str(iso.path), iso.meta,
                                               disk["path"], int(disk["size"]), opts, after)
            self.jobs.start(dev.id, kind, disk["path"], what, work)
            self.open_device(dev).show_jobs()

        InstallDialog(parent, agent, isos, dev, start, preselect)

    def install_iso_on_device(self, iso: oslib.IsoInfo | None) -> None:
        """Rechtsklick auf eine ISO: auf welches verbundene Gerät?"""
        if iso is None:
            return
        online = [self.store.devices[d] for d in self.online if d in self.store.devices]
        if not online:
            confirm_error(self, "Kein Gerät verbunden – Zielgerät mit dem Agent-Stick starten.")
            return
        dev = online[0]
        if len(online) > 1:
            dlg = Gtk.Dialog(title="Zielgerät wählen", transient_for=self, modal=True)
            dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Weiter", Gtk.ResponseType.OK)
            combo = Gtk.ComboBoxText(margin=12)
            for d in online:
                agent = self.online_agent(d)
                combo.append(d.id, f"{d.name}  ({agent.ip if agent else ''})")
            combo.set_active(0)
            dlg.get_content_area().add(combo)
            dlg.show_all()
            answer = dlg.run()
            chosen = combo.get_active_id()
            dlg.destroy()
            if answer != Gtk.ResponseType.OK:
                return
            dev = self.store.devices[chosen]
        self.start_install(dev, str(iso.path))

    def _after_job(self, dev_id: str, job: jobs.Job, what: str, path: str | None, error: Exception | None,
                   shutdown: bool) -> bool:
        """Ergebnis eines Auftrags: Verlauf, Image-Liste, freier Speicher, evtl. herunterfahren."""
        dev = self.store.devices.get(dev_id)
        if dev is not None:
            if error is None and job.kind in ("install", "linux"):
                self.store.add_history(dev, job.kind, f"{what}: vorbereitet, Gerät startet neu und installiert "
                                                      "selbständig", ok=True)
            elif error is None:
                where = ""
                if job.kind == "image" and path and self._nas_root():
                    where = f" → NAS: /{os.path.relpath(path, self._nas_root())}"
                self.store.add_history(dev, job.kind, f"{what} erfolgreich{where}", ok=True)
            else:
                state = "abgebrochen" if job.cancel.is_set() else f"fehlgeschlagen: {error}"
                self.store.add_history(dev, job.kind, f"{what} {state}", ok=False)
        self.refresh_images()
        self.refresh_nas_status()  # freier Speicher hat sich geändert
        win = self.device_windows.get(dev_id)
        if win:
            win.load_images()
        if error is None and shutdown and dev is not None:
            self._power_after(dev, job)
        return False

    def _power_after(self, dev: devices.Device, job: jobs.Job) -> None:
        """Nach dem Auftrag herunterfahren – aber nicht, solange noch ein anderer Auftrag läuft."""
        others = [j for j in self.jobs.running() if j.device_id == dev.id and j is not job]
        agent = self.online_agent(dev)
        if others or agent is None:
            self.jobs.log(job, "Nicht heruntergefahren – " + ("weitere Aufträge laufen" if others
                                                               else "Gerät nicht mehr verbunden"))
            return
        key = self.key

        def work():
            for _ in range(10):  # der Agent gibt die Disk erst kurz nach dem letzten Block frei
                try:
                    agentclient.power(agent.ip, key, "poweroff", agent.control_port)
                    return "Gerät wird heruntergefahren"
                except agentclient.AgentError as e:
                    if "beschäftigt" not in str(e):
                        raise
                    time.sleep(2)
            raise agentclient.AgentError("Agent ist noch beschäftigt")

        def done(result) -> None:
            ok = not isinstance(result, Exception)
            self.jobs.log(job, result if ok else f"Herunterfahren fehlgeschlagen: {result}")
            self.store.add_history(dev, "power", "Nach dem Auftrag heruntergefahren" if ok
                                   else f"Herunterfahren fehlgeschlagen: {result}", ok=ok)
            win = self.device_windows.get(dev.id)
            if win:
                win.refresh()

        run_async(work, done)

    def refresh_inventory(self, dev: devices.Device) -> None:
        agent = self._ready_agent(dev, self._parent_for(dev))
        if agent is None:
            return
        if self.jobs.summary(dev.id) or agent.busy:
            confirm_error(self._parent_for(dev), "Während ein Auftrag läuft, kann das Inventar nicht neu "
                                                 "eingelesen werden (Partitionen werden dafür eingehängt).")
            return
        if agent.agent_id not in self.inv_pending:
            self.fetch_inventory(agent, refresh=True)

    def power(self, dev: devices.Device, action: str) -> None:
        parent = self._parent_for(dev)
        agent = self._ready_agent(dev, parent)
        if agent is None:
            return
        what = "herunterfahren" if action == "poweroff" else "neu starten"
        if self.jobs.summary(dev.id) or agent.busy:
            confirm_error(parent, f"Auf „{dev.name}“ läuft ein Auftrag – erst danach {what}.")
            return
        if not confirm(parent, f"„{dev.name}“ {what}?",
                       f"{dev.hardware or agent.hardware} ({agent.ip})"
                       + ("\n\nDanach kann der Stick abgezogen werden." if action == "poweroff" else ""),
                       ok_label=what.capitalize()):
            return
        key = self.key

        def done(result) -> None:
            if isinstance(result, Exception):
                self.status(f"{what.capitalize()} fehlgeschlagen: {result}")
                confirm_error(parent, str(result))
                return
            text = "Heruntergefahren" if action == "poweroff" else "Neu gestartet"
            self.store.add_history(dev, "power", f"{text} (vom Tool)", ok=True)
            self.status(f"{dev.name}: {text.lower()}")
            win = self.device_windows.get(dev.id)
            if win:
                win.refresh()

        run_async(lambda: agentclient.power(agent.ip, key, action, agent.control_port), done)

    def _on_job_change(self, job: jobs.Job) -> bool:
        self.update_device_rows()
        win = self.device_windows.get(job.device_id)
        if win:
            win.refresh_jobs(job)
        return False

    def _on_delete(self, *_a) -> bool:
        """Beim Beenden warnen, wenn noch Aufträge laufen (sie würden abbrechen)."""
        running = self.jobs.running()
        if not running:
            return False
        names = "\n".join(f"• {self.store.devices[j.device_id].name if j.device_id in self.store.devices else '?'}"
                          f": {j.title} ({j.fraction * 100:.0f} %)" for j in running)
        what = "1 Auftrag läuft" if len(running) == 1 else f"{len(running)} Aufträge laufen"
        if confirm(self, f"{what} noch – trotzdem beenden?",
                   f"{names}\n\nLaufende Images und Restores werden abgebrochen. Ein abgebrochenes Restore "
                   "hinterlässt eine unbrauchbare Zieldisk.", ok_label="Trotzdem beenden"):
            for j in running:
                j.cancel.set()
            return False
        return True

    def status(self, text: str) -> None:
        self.statusbar.pop(0)
        self.statusbar.push(0, text)


def beacon_inventory(info: discovery.AgentInfo) -> dict:
    """Notbehelf ohne Inventar (alter Stick, Fehler): das, was der Beacon meldet."""
    return {"dmi": {k: v for k, v in (("sys_vendor", info.vendor), ("product_name", info.product)) if v},
            "network": [{"name": "", "mac": info.mac}] if info.mac else [],
            "disks": [{"name": d.name, "size": d.size, "model": d.model, "serial": d.serial} for d in info.disks]}


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="ch.okula.RecoveryTool")

    def do_activate(self):
        Gtk.IconTheme.get_default().append_search_path(str(ASSETS / "icons"))
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = self.get_active_window() or MainWindow(self)
        win.show_all()
        win.present()


def main() -> int:
    return App().run(None)
