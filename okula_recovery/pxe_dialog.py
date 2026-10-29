"""Tools → „Netzwerkstart (PXE) …“: vorbereiten, ein-/ausschalten, Geräte freischalten."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from okula_recovery import devices, isofetch, network, pxe  # noqa: E402
from okula_recovery.stick_dialog import helper_subcommand, run_helper  # noqa: E402
from okula_recovery.uikit import scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow


class PxeDialog(Gtk.Dialog):
    def __init__(self, main: "MainWindow"):
        super().__init__(title="Netzwerkstart (PXE)", transient_for=main, modal=False)
        self.set_default_size(800, 720)
        self.main = main
        self.busy = False
        self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda *_a: None if self.busy else self.destroy())
        self.connect("delete-event", lambda *_a: self.busy)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        intro = Gtk.Label(xalign=0, wrap=True)
        intro.set_markup(
            "Freigeschaltete Geräte starten den Agent <b>ohne Stick</b>: am Gerät F12 (Boot-Menü) → Netzwerk / PXE. "
            "Nur Geräte, die schon einmal mit dem Agent-Stick liefen <b>und</b> unten freigeschaltet sind, bekommen "
            "eine Antwort. Andere Rechner im Netz merken nichts; IP-Adressen vergibt weiterhin euer DHCP-Server.")
        box.pack_start(intro, False, False, 0)
        self.status = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(self.status, False, False, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        grid.attach(Gtk.Label(label="Server-IP", xalign=0), 0, 0, 1, 1)
        self.server = Gtk.ComboBoxText(hexpand=True)
        for iface in network.local_interfaces():
            self.server.append(str(iface.ip), f"{iface.ip}  ({iface.network})")
        state = pxe.read_state()
        if not self.server.set_active_id(state.get("server") or ""):
            self.server.set_active(0)
        self.server.connect("changed", lambda _c: self.update())
        grid.attach(self.server, 1, 0, 2, 1)
        grid.attach(Gtk.Label(label="Debian-Live-ISO", xalign=0), 0, 1, 1, 1)
        self.iso = Gtk.ComboBoxText(hexpand=True)
        self._fill_isos()
        grid.attach(self.iso, 1, 1, 1, 1)
        self.btn_download = Gtk.Button(label="Herunterladen")
        self.btn_download.set_tooltip_text(f"Aktuelles debian-live-…-amd64-{isofetch.FLAVOUR}.iso (wie beim Agent-Stick)")
        self.btn_download.connect("clicked", lambda _b: self.download())
        grid.attach(self.btn_download, 2, 1, 1, 1)
        box.pack_start(grid, False, False, 0)

        actions = Gtk.Box(spacing=6)
        self.btn_prepare = Gtk.Button(label="Vorbereiten")
        self.btn_prepare.set_tooltip_text("Live-System, Agent-Teil (mit Schlüssel) und Bootlader bereitlegen – einmal "
                                          "und nach einem Tool-Update oder wenn sich die Server-IP ändert")
        self.btn_prepare.connect("clicked", lambda _b: self.prepare())
        self.btn_on = Gtk.Button(label="Einschalten")
        self.btn_on.get_style_context().add_class("suggested-action")
        self.btn_on.connect("clicked", lambda _b: self.switch(True))
        self.btn_off = Gtk.Button(label="Ausschalten")
        self.btn_off.connect("clicked", lambda _b: self.switch(False))
        for b in (self.btn_prepare, self.btn_on, self.btn_off):
            actions.pack_start(b, False, False, 0)
        box.pack_start(actions, False, False, 0)

        box.pack_start(Gtk.Label(label="Geräte (Haken = Netzwerkstart erlaubt)", xalign=0), False, False, 0)
        # erlaubt, Name, Ordner, MAC-Adressen, Geräte-ID, wählbar
        self.store = Gtk.ListStore(bool, str, str, str, str, bool)
        view = Gtk.TreeView(model=self.store)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_toggled)
        col = Gtk.TreeViewColumn("", toggle, active=0, activatable=5)
        view.append_column(col)
        for title, idx in (("Gerät", 1), ("Ordner", 2), ("Kabel-Netzwerkkarten (MAC)", 3)):
            c = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
            c.set_resizable(True)
            c.set_expand(idx == 3)
            view.append_column(c)
        sw = scrolled(view)
        sw.set_vexpand(True)
        box.pack_start(sw, True, True, 0)

        hint = Gtk.Label(xalign=0, wrap=True)
        hint.set_markup("<small>Am Gerät: Netzwerkkabel, im BIOS Netzwerkstart (PXE) aktiv; Secure Boot darf an "
                        "bleiben. Bei VLANs/Routern dazwischen braucht der Switch eine DHCP-Weiterleitung (IP-Helper) "
                        "zum Server.</small>")
        hint.get_style_context().add_class("status-idle")
        box.pack_start(hint, False, False, 0)
        self.bar = Gtk.ProgressBar(show_text=True)
        self.bar.set_text("Bereit")
        box.pack_start(self.bar, False, False, 0)
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        lsw = scrolled(self.log)
        lsw.set_min_content_height(90)
        box.pack_start(lsw, False, False, 0)
        self.get_content_area().pack_start(box, True, True, 0)
        self.show_all()
        self.fill_devices()
        self.update()

    # ---------- Anzeige ----------

    def _fill_isos(self) -> None:
        current = self.iso.get_active_id()
        self.iso.remove_all()
        for p in isofetch.cached_isos():
            self.iso.append(str(p), p.name)
        if not (current and self.iso.set_active_id(current)):
            self.iso.set_active(0)

    def fill_devices(self) -> None:
        self.store.clear()
        for dev in sorted(self.main.store.devices.values(), key=lambda d: (d.folder.lower(), d.name.lower())):
            macs = devices.netboot_macs([devices.Device(id="x", netboot=True, macs=dev.macs, inventory=dev.inventory)])
            self.store.append([dev.netboot, dev.name, dev.folder or "Neu / nicht einsortiert",
                               ", ".join(macs) or "keine bekannt", dev.id, bool(macs)])

    def _on_toggled(self, _cell, path) -> None:
        row = self.store[path]
        dev = self.main.store.devices.get(row[4])
        if dev is not None:
            self.main.set_netboot(dev, not row[0], self)
            row[0] = dev.netboot

    def update(self) -> None:
        state = pxe.read_state()
        active = pxe.is_active()
        server = self.server.get_active_id()
        if not state:
            text, cls = "● Noch nicht vorbereitet – Debian-Live-ISO wählen und „Vorbereiten“", "status-idle"
        elif state.get("server") != server:
            text, cls = (f"● Vorbereitet für {state.get('server')} – für {server} neu vorbereiten", "status-fail")
        else:
            prepared = state.get("prepared", "").replace("T", " ")[:16]
            n = sum(1 for d in self.main.store.devices.values() if d.netboot)
            text = (f"● Netzwerkstart {'EIN' if active else 'aus'} · vorbereitet {prepared} aus {state.get('iso')} · "
                    f"{n} Gerät{'e' if n != 1 else ''} freigeschaltet")
            cls = "status-ok" if active else "status-idle"
        self.status.set_text(text)
        ctx = self.status.get_style_context()
        for c in ("status-ok", "status-fail", "status-idle"):
            ctx.remove_class(c)
        ctx.add_class(cls)
        ready = bool(state) and state.get("server") == server
        self.btn_prepare.set_sensitive(not self.busy and bool(self.iso.get_active_id()) and bool(server))
        self.btn_on.set_sensitive(not self.busy and ready and not active)
        self.btn_off.set_sensitive(not self.busy and active)
        self.btn_download.set_sensitive(not self.busy)
        if active != getattr(self, "_was_active", None) or bool(state) != getattr(self, "_was_prepared", None):
            self._was_active, self._was_prepared = active, bool(state)
            self.main.netboot_changed()   # Schalter in offenen Gerätefenstern nachführen

    def _log(self, text: str) -> bool:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        return False

    def _progress(self, frac: float, msg: str) -> bool:
        self.bar.set_fraction(max(0.0, min(1.0, frac)))
        self.bar.set_text(msg)
        return False

    def _line(self, line: str) -> bool:
        kind, _, text = line.partition(" ")
        if kind in ("INFO", "WARN", "DONE", "ERROR"):
            return self._log({"WARN": "Hinweis: ", "ERROR": "Fehler: "}.get(kind, "") + text)
        return self._log(line)

    # ---------- Aktionen ----------

    def _run(self, args: list[str], stdin: str, intro: str, then=None) -> None:
        try:
            cmd = helper_subcommand("pxe", args)
        except FileNotFoundError as e:
            self._log(str(e))
            return
        self.busy = True
        self.update()
        self._log(intro)

        def done(ok: bool, error: str) -> bool:
            self.busy = False
            if not ok and error:
                self._log(f"Fehler: {error}")
                self.bar.set_text("Fehlgeschlagen")
            if ok and then:
                then()
            self.update()
            return False

        run_helper(cmd, stdin, self._progress, self._line, done)

    def prepare(self) -> None:
        iso, server = self.iso.get_active_id(), self.server.get_active_id()
        self._run(["prepare", "--iso", iso, "--server", server], self.main.key.hex() + "\n",
                  f"Bereite Netzwerkstart vor ({Path(iso).name}, Server {server}) – dauert einige Minuten …")

    def switch(self, on: bool) -> None:
        if not on:
            self._run(["stop"], "", "Schalte Netzwerkstart aus …")
            return
        server = self.server.get_active_id()
        modes = devices.netboot_modes(self.main.store.devices.values())
        self._run(["allow"], "".join(f"{m} {mode}\n" for m, mode in modes.items()),
                  f"Schalte {len(modes)} MAC-Adressen frei …",
                  then=lambda: self._run(["start", "--server", server], "", "Starte Netzwerkstart …"))

    def download(self) -> None:
        self.busy = True
        self.update()
        self._log(f"Lade Debian-Live-ISO von {isofetch.BASE_URL}")

        def work():
            try:
                path = isofetch.fetch(lambda f, m: GLib.idle_add(self._progress, f, m))
                GLib.idle_add(self._downloaded, path, None)
            except Exception as e:  # Netzwerk, Prüfsumme, Speicherplatz
                GLib.idle_add(self._downloaded, None, e)

        threading.Thread(target=work, daemon=True).start()

    def _downloaded(self, path, error) -> bool:
        self.busy = False
        self._log(f"Download fehlgeschlagen: {error}" if error else f"ISO bereit: {path}")
        self._fill_isos()
        if path:
            self.iso.set_active_id(str(path))
        self.update()
        return False
