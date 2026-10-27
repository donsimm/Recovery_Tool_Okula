"""GTK-3-Oberfläche: links NAS und Images, rechts Maschinen im LAN."""

from __future__ import annotations

import ipaddress
import threading
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from okula_recovery import __version__, config, discovery, nas, network  # noqa: E402

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


def pane_title(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.get_style_context().add_class("pane-title")
    return lbl


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Okula Recovery Tool")
        self.set_default_size(1280, 760)
        self.cfg = config.load()

        header = Gtk.HeaderBar(title="Okula Recovery Tool", subtitle=f"Version {__version__}",
                               show_close_button=True)
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

        self._load_manual_machines()
        self._start_listener()
        GLib.idle_add(self.on_test_nas, None)

    # ---------- linke Seite: NAS ----------

    def _build_nas_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        box.pack_start(pane_title("NAS – Images & Backups"), False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        self.nas_protocol = Gtk.ComboBoxText()
        self.nas_protocol.append("smb", "SMB / CIFS")
        self.nas_protocol.append("nfs", "NFS")
        self.nas_protocol.set_active_id(self.cfg.nas.protocol)
        self.nas_host = Gtk.Entry(text=self.cfg.nas.host, placeholder_text="z. B. nas.local oder 192.168.1.10",
                                  hexpand=True)
        self.nas_share = Gtk.Entry(text=self.cfg.nas.share, placeholder_text="z. B. recovery")
        self.nas_mount = Gtk.Entry(text=self.cfg.nas.mount_point)
        for row, (label, widget) in enumerate([("Protokoll", self.nas_protocol), ("Host", self.nas_host),
                                               ("Freigabe", self.nas_share), ("Einhängepunkt", self.nas_mount)]):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
        box.pack_start(grid, False, False, 0)

        buttons = Gtk.Box(spacing=6)
        self.btn_test = Gtk.Button(label="Verbindung testen")
        self.btn_test.connect("clicked", self.on_test_nas)
        btn_mount = Gtk.Button(label="Einhängen")
        btn_mount.connect("clicked", self.on_mount_nas)
        btn_save = Gtk.Button(label="Speichern")
        btn_save.connect("clicked", self.on_save_nas)
        for b in (self.btn_test, btn_mount, btn_save):
            buttons.pack_start(b, False, False, 0)
        self.nas_spinner = Gtk.Spinner()
        buttons.pack_start(self.nas_spinner, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.nas_status = Gtk.Label(label="Nicht geprüft", xalign=0)
        self.nas_status.get_style_context().add_class("status-idle")
        box.pack_start(self.nas_status, False, False, 0)

        # Ergebnis der Einzelprüfungen
        self.check_store = Gtk.ListStore(str, str, str)  # icon, Prüfung, Detail
        checks = make_tree([("", -1), ("Prüfung", 1), ("Detail", 2)], self.check_store, expand=2)
        checks.set_headers_visible(False)
        checks.get_selection().set_mode(Gtk.SelectionMode.NONE)
        sw = scrolled(checks)
        sw.set_vexpand(False)
        sw.set_min_content_height(150)
        box.pack_start(sw, False, False, 0)

        img_head = Gtk.Box(spacing=6)
        img_head.pack_start(pane_title("Gespeicherte Images"), True, True, 0)
        self.img_count = Gtk.Label(label="")
        img_head.pack_start(self.img_count, False, False, 0)
        btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_refresh.set_tooltip_text("Image-Liste neu laden")
        btn_refresh.connect("clicked", lambda _b: self.refresh_images())
        img_head.pack_start(btn_refresh, False, False, 0)
        box.pack_start(img_head, False, False, 4)

        # Name, Typ, Grösse (Text), Datum (Text), Grösse (Byte, für Sortierung), Pfad
        self.image_store = Gtk.ListStore(str, str, str, str, str, GObject.TYPE_INT64, str)
        self.image_view = make_tree([("Name", 1), ("Typ", 2), ("Grösse", 3), ("Datum", 4)], self.image_store)
        self.image_view.get_column(2).set_sort_column_id(5)
        box.pack_start(scrolled(self.image_view), True, True, 0)
        return box

    def _nas_cfg_from_form(self) -> config.NasConfig:
        return config.NasConfig(protocol=self.nas_protocol.get_active_id() or "smb",
                                host=self.nas_host.get_text().strip(),
                                share=self.nas_share.get_text().strip(),
                                mount_point=self.nas_mount.get_text().strip() or "/mnt/okula-nas")

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
            self.refresh_images()
        else:
            failed = next(c for c in result if not c.ok)
            self._set_nas_status(f"● Keine Verbindung – {failed.name}", "fail")
            self.image_store.clear()
            self.img_count.set_text("")

    def on_mount_nas(self, _btn) -> None:
        cfg = self._nas_cfg_from_form()
        self.nas_spinner.start()
        run_async(lambda: nas.mount(cfg), self._on_mounted)

    def _on_mounted(self, result) -> None:
        self.nas_spinner.stop()
        ok, msg = (False, str(result)) if isinstance(result, Exception) else result
        self.status(f"Einhängen: {msg}")
        if ok:
            self.on_test_nas(None)

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
        self.machine_buttons = []
        for label in ("Backup erstellen", "Disk-Image erstellen", "Image zurückspielen"):
            b = Gtk.Button(label=label, sensitive=False)
            b.set_tooltip_text("Noch nicht implementiert")
            actions.pack_start(b, False, False, 0)
            self.machine_buttons.append(b)
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
        disks = ", ".join(f"{d.name} {nas.format_size(d.size)}" for d in info.disks) or "–"
        known = any(row[2] == info.ip and row[4] == "USB-Agent" and row[0] == ICON_AGENT
                    for row in self.machine_store)
        self._add_machine_row(network.Machine(ip=info.ip, name=info.hostname, mac=info.mac, online=True,
                                              source="USB-Agent", hardware=info.hardware, disks=disks))
        if not known:
            self.status(f"USB-Agent gemeldet: {info.hostname or info.ip} ({info.ip})")
        return False

    def _expire_agents(self) -> bool:
        limit = time.time() - AGENT_TIMEOUT
        for row in self.machine_store:
            if row[4] == "USB-Agent" and row[0] == ICON_AGENT and row[8] < limit:
                row[0] = ICON_OFFLINE
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
        if has:
            self.status(f"Ausgewählt: {model[it][1]} ({model[it][2]})")

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
