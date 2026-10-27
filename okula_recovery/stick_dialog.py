"""Dialog „Agent-USB-Stick erstellen“: Stick wählen, ISO bereitstellen, Stick vorbereiten."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from okula_recovery import agentclient, isofetch, network, stick  # noqa: E402

HELPER = "/usr/local/sbin/okula-make-stick"


def helper_command(device: str, iso: str, server: str) -> list[str]:
    args = ["--device", device, "--iso", iso, "--key-stdin"]
    if server:
        args += ["--server", server]
    if os.geteuid() == 0:
        return [sys.executable, "-m", "okula_recovery.stick", *args]
    if not Path(HELPER).exists():
        raise FileNotFoundError(f"{HELPER} fehlt – bitte install.sh ausführen")
    return ["sudo", "-n", HELPER, *args]


class StickDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window):
        super().__init__(title="Agent-USB-Stick erstellen", transient_for=parent, modal=True)
        self.set_default_size(620, 460)
        self.busy = False
        self.btn_close = self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.btn_start = self.add_button("Stick vorbereiten", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("destructive-action")
        self.connect("response", self.on_response)
        self.connect("delete-event", lambda *_a: self.busy)  # während des Schreibens nicht schliessen

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)

        grid.attach(Gtk.Label(label="USB-Stick", xalign=0), 0, 0, 1, 1)
        self.disk_combo = Gtk.ComboBoxText(hexpand=True)
        self.disk_combo.connect("changed", lambda _c: self._update_sensitivity())
        grid.attach(self.disk_combo, 1, 0, 1, 1)
        self.btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.btn_refresh.set_tooltip_text("USB-Sticks neu suchen")
        self.btn_refresh.connect("clicked", lambda _b: self.refresh_disks())
        grid.attach(self.btn_refresh, 2, 0, 1, 1)

        grid.attach(Gtk.Label(label="Debian-Live-ISO", xalign=0), 0, 1, 1, 1)
        self.iso_chooser = Gtk.FileChooserButton(title="Debian-Live-ISO wählen", action=Gtk.FileChooserAction.OPEN)
        iso_filter = Gtk.FileFilter()
        iso_filter.set_name("ISO-Images")
        iso_filter.add_pattern("*.iso")
        self.iso_chooser.add_filter(iso_filter)
        self.iso_chooser.connect("file-set", lambda _c: self._update_sensitivity())
        cached = isofetch.cached_isos()
        if cached:
            self.iso_chooser.set_filename(str(cached[0]))
        grid.attach(self.iso_chooser, 1, 1, 1, 1)
        self.btn_download = Gtk.Button(label="Herunterladen")
        self.btn_download.set_tooltip_text(f"Aktuelles debian-live-…-amd64-{isofetch.FLAVOUR}.iso von {isofetch.BASE_URL}")
        self.btn_download.connect("clicked", self.on_download)
        grid.attach(self.btn_download, 2, 1, 1, 1)

        grid.attach(Gtk.Label(label="Server-IP", xalign=0), 0, 2, 1, 1)
        ifaces = network.local_interfaces()
        self.server_ip = Gtk.Entry(text=str(ifaces[0].ip) if ifaces else "",
                                   placeholder_text="leer = nur Broadcast")
        self.server_ip.set_tooltip_text("Der Agent meldet sich per Broadcast und zusätzlich direkt an diese IP")
        grid.attach(self.server_ip, 1, 2, 2, 1)

        warn = Gtk.Label(xalign=0, wrap=True)
        warn.set_markup("<b>Achtung:</b> Alle Daten auf dem gewählten Stick werden gelöscht.")
        warn.get_style_context().add_class("status-fail")
        grid.attach(warn, 0, 3, 3, 1)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_text("Bereit")
        grid.attach(self.progress, 0, 4, 3, 1)

        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.log)
        grid.attach(sw, 0, 5, 3, 1)

        self.get_content_area().add(grid)
        self.refresh_disks()
        self.show_all()

    # ---------- Zustand ----------

    def selected_disk(self) -> str | None:
        return self.disk_combo.get_active_id()

    def _update_sensitivity(self) -> None:
        ready = not self.busy and self.selected_disk() is not None and bool(self.iso_chooser.get_filename())
        self.btn_start.set_sensitive(ready)
        for w in (self.btn_download, self.btn_close, self.btn_refresh, self.disk_combo, self.iso_chooser,
                  self.server_ip):
            w.set_sensitive(not self.busy)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self._update_sensitivity()

    def append_log(self, text: str) -> None:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)

    def refresh_disks(self) -> None:
        self.disk_combo.remove_all()
        disks = stick.list_usb_disks()
        for d in disks:
            self.disk_combo.append(d.path, d.label)
        if disks:
            self.disk_combo.set_active(0)
        else:
            self.append_log("Kein USB-Stick gefunden – Stick einstecken und neu suchen.")
        self._update_sensitivity()

    # ---------- ISO herunterladen ----------

    def on_download(self, _btn) -> None:
        self._set_busy(True)
        self.append_log(f"Lade Debian-Live-ISO von {isofetch.BASE_URL}")

        def progress(frac: float, msg: str) -> None:
            GLib.idle_add(self._on_progress, frac, msg)

        def work():
            try:
                path = isofetch.fetch(progress)
                GLib.idle_add(self._on_downloaded, path, None)
            except Exception as e:  # Netzwerk, Prüfsumme, Speicherplatz
                GLib.idle_add(self._on_downloaded, None, e)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, frac: float, msg: str) -> bool:
        self.progress.set_fraction(max(0.0, min(1.0, frac)))
        self.progress.set_text(msg)
        return False

    def _on_downloaded(self, path: Path | None, error: Exception | None) -> bool:
        self._set_busy(False)
        if error:
            self.append_log(f"Download fehlgeschlagen: {error}")
            self.progress.set_text("Download fehlgeschlagen")
        else:
            self.iso_chooser.set_filename(str(path))
            self.append_log(f"ISO bereit: {path}")
        self._update_sensitivity()
        return False

    # ---------- Stick schreiben ----------

    def on_response(self, _dlg, response: int) -> None:
        if response == Gtk.ResponseType.APPLY:
            self.start_write()
        elif not self.busy:
            self.destroy()

    def start_write(self) -> None:
        device, iso = self.selected_disk(), self.iso_chooser.get_filename()
        if not device or not iso:
            return
        label = self.disk_combo.get_active_text()
        confirm = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
                                    buttons=Gtk.ButtonsType.OK_CANCEL, text="Stick wirklich löschen?")
        confirm.format_secondary_text(f"{label}\n\nAlle Daten auf diesem Stick gehen verloren.")
        answer = confirm.run()
        confirm.destroy()
        if answer != Gtk.ResponseType.OK:
            return
        try:
            cmd = helper_command(device, iso, self.server_ip.get_text().strip())
        except FileNotFoundError as e:
            self.append_log(str(e))
            return

        key_hex = agentclient.load_or_create_key().hex()
        self._set_busy(True)
        self.append_log(f"Erstelle Agent-Stick auf {device} …")
        cwd = str(Path(stick.__file__).resolve().parent.parent)

        def work():
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, cwd=cwd)
                proc.stdin.write(key_hex + "\n")
                proc.stdin.close()
            except OSError as e:
                GLib.idle_add(self._on_written, False, str(e))
                return
            ok, last_error = False, ""
            for line in proc.stdout:
                kind, _, text = line.rstrip("\n").partition(" ")
                if kind == "PROGRESS":
                    frac, _, msg = text.partition(" ")
                    try:
                        GLib.idle_add(self._on_progress, float(frac), msg)
                    except ValueError:
                        pass
                    continue
                if kind == "DONE":
                    ok = True
                elif kind == "ERROR":
                    last_error = text
                GLib.idle_add(self.append_log, line.rstrip("\n"))
            rc = proc.wait()
            if rc != 0 and not last_error:
                last_error = f"Hilfsprogramm beendet mit Code {rc} (sudo-Regel vorhanden? install.sh)"
            GLib.idle_add(self._on_written, ok and rc == 0, last_error)

        threading.Thread(target=work, daemon=True).start()

    def _on_written(self, ok: bool, error: str) -> bool:
        self._set_busy(False)
        if ok:
            self.progress.set_fraction(1.0)
            self.progress.set_text("Stick bereit")
        else:
            self.progress.set_text("Fehlgeschlagen")
            if error:
                self.append_log(f"Fehler: {error}")
        self.refresh_disks()
        return False
