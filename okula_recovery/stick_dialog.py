"""Dialog „Agent-USB-Stick erstellen“: Stick wählen, ISO bereitstellen, Stick vorbereiten."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from okula_recovery import agentclient, isofetch, network, stick  # noqa: E402
from okula_recovery.uikit import confirm, confirm_error, info  # noqa: E402

HELPER = "/usr/local/sbin/okula-make-stick"
UNPLUG_HINT = "Stick erst abziehen, wenn „Stick fertig“ erscheint."


def stick_result_texts(ok: bool, error: str, done_title: str) -> tuple[str, str]:
    """(Titel, Text) des Popups am Ende des Stick-Baus."""
    if ok:
        return done_title, "Der Stick kann jetzt abgezogen werden."
    reason = error or "unbekannter Fehler"
    return "Stick nicht fertig", f"{reason}\n\nStick nicht verwenden – neu erstellen."


def show_stick_result(parent: Gtk.Window, ok: bool, error: str, done_title: str) -> None:
    """Popup „… fertig“ (OK) bzw. roter Fehlerdialog „Stick nicht fertig“ (Schliessen)."""
    title, text = stick_result_texts(ok, error, done_title)
    if ok:
        info(parent, title, text)
    else:
        confirm_error(parent, text, title=title, red=True)


def ident_args(disks) -> list[str]:
    """B-029: „--ident <JSON>“ je Datenträger (Seriennummer, Modell, Grösse) für den Root-Helfer."""
    args: list[str] = []
    for d in disks:
        if d is not None:
            args += ["--ident", d.ident().arg()]
    return args


def helper_command(device: str, iso: str, server: str, image: str | None = None,
                   source_disk: str | None = None, disk=None) -> list[str]:
    args = ["--device", device, "--iso", iso, "--key-stdin", *ident_args([disk])]
    if server:
        args += ["--server", server]
    if image:
        args += ["--image", image]
        if source_disk:
            args += ["--source-disk", source_disk]
    if os.geteuid() == 0:
        return [sys.executable, "-m", "okula_recovery.stick", *args]
    if not Path(HELPER).exists():
        raise FileNotFoundError(f"{HELPER} fehlt – bitte install.sh ausführen")
    return ["sudo", "-n", HELPER, *args]


def helper_subcommand(sub: str, args: list[str]) -> list[str]:
    """Weitere Aufgaben des gleichen Root-Helfers (gleiche sudo-Regel): iso-stick, usb-clone, usb-format."""
    if os.geteuid() == 0:
        return [sys.executable, "-m", "okula_recovery.stick", sub, *args]
    if not Path(HELPER).exists():
        raise FileNotFoundError(f"{HELPER} fehlt – bitte install.sh ausführen")
    return ["sudo", "-n", HELPER, sub, *args]


def iso_stick_command(args: list[str]) -> list[str]:
    """Boot-Stick aus ISO: gleicher Root-Helfer, Unterbefehl „iso-stick“."""
    return helper_subcommand("iso-stick", args)


class HelperRun:
    """Laufender Root-Helfer. cancel() schickt „CANCEL“ über stdin – beenden darf der Benutzer ihn nicht."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None

    def cancel(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None or proc.stdin is None or proc.stdin.closed:
            return
        try:
            proc.stdin.write("CANCEL\n")
            proc.stdin.flush()
        except (OSError, ValueError):
            pass


def run_helper(cmd: list[str], stdin_text: str, on_progress, on_line, on_done,
               keep_stdin: bool = False) -> HelperRun:
    """Root-Helfer im Hintergrund starten und seine Ausgabe auswerten (PROGRESS/WARN/DONE/ERROR).

    Die Rückrufe laufen im GTK-Hauptthread: on_progress(anteil, text), on_line(zeile), on_done(ok, fehler).
    keep_stdin: stdin offen lassen, damit HelperRun.cancel() abbrechen kann.
    """
    cwd = str(Path(stick.__file__).resolve().parent.parent)
    handle = HelperRun()

    def work():
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, cwd=cwd)
            handle.proc = proc
            proc.stdin.write(stdin_text)
            if keep_stdin:
                proc.stdin.flush()
            else:
                proc.stdin.close()
        except OSError as e:
            GLib.idle_add(on_done, False, str(e))
            return
        ok, last_error = False, ""
        for line in proc.stdout:
            kind, _, text = line.rstrip("\n").partition(" ")
            if kind == "PROGRESS":
                frac, _, msg = text.partition(" ")
                try:
                    GLib.idle_add(on_progress, float(frac), msg)
                except ValueError:
                    pass
                continue
            if kind == "DONE":
                ok = True
            elif kind == "ERROR":
                last_error = text
            GLib.idle_add(on_line, line.rstrip("\n"))
        rc = proc.wait()
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        if rc != 0 and not last_error:
            last_error = f"Hilfsprogramm beendet mit Code {rc} (sudo-Regel vorhanden? install.sh)"
        GLib.idle_add(on_done, ok and rc == 0, last_error)

    threading.Thread(target=work, daemon=True).start()
    return handle


JOB_WINDOWS: dict[int, Gtk.Window] = {}   # Auftrags-ID → Fenster des USB-Vorgangs (Auftragsliste: „Anzeigen“)


class UsbJobMixin:
    """Ä-052/B-029: gemeinsam für USB klonen, USB formatieren, Agent-USB-Stick und Boot-Stick.

    Fenster nicht modal (Hauptfenster bleibt bedienbar, minimierbar). Der Vorgang läuft als Auftrag im JobManager
    des Hauptfensters (usbjobs.start) und steht in der Auftragsliste „USB-Vorgänge“. Fenster schliessen während des
    Vorgangs blendet es nur aus – der Vorgang läuft weiter, die Auftragsliste zeigt ihn wieder an. Belegte
    Datenträger sind in den Listen ausgegraut („wird gerade verwendet“)."""

    usb_job = None

    def _init_usb(self) -> None:
        from okula_recovery import usbjobs
        self.usb_job = None
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL)        # minimieren möglich (kein Dialog-Fenstertyp)
        self._usb_listener = self._on_usb_change
        usbjobs.subscribe(self._usb_listener)
        self.connect("destroy", lambda *_a: usbjobs.unsubscribe(self._usb_listener))
        self.connect("delete-event", self._on_usb_delete)

    # ---------- Zustand ----------

    @property
    def usb_running(self) -> bool:
        return self.usb_job is not None and self.usb_job.running

    def usb_manager(self):
        from okula_recovery import usbjobs
        return usbjobs.manager(self.get_transient_for())

    def disk_in_use(self, disk):
        """Laufender Auftrag eines anderen Fensters, der diesen Datenträger verwendet (None = frei)."""
        from okula_recovery import usbjobs
        return usbjobs.in_use(disk, exclude=self.usb_job) if disk is not None else None

    def disk_text(self, disk, extra: str = "") -> str:
        from okula_recovery import usbjobs
        return disk.label + extra + (f"  – {usbjobs.IN_USE}" if self.disk_in_use(disk) else "")

    def mark_in_use(self, combo: Gtk.ComboBox, lookup) -> None:
        """Belegte Datenträger in der Liste ausgrauen; lookup(Pfad) → UsbDisk."""
        cells = combo.get_cells()
        if not cells:
            return
        column = combo.get_id_column()

        def data(_layout, cell, model, it, _data=None):
            cell.set_property("sensitive", self.disk_in_use(lookup(model[it][column])) is None)

        combo.set_cell_data_func(cells[0], data, None)

    def in_use_problem(self, disks) -> str:
        """„/dev/sdb wird gerade verwendet (USB klonen …)“ oder leer."""
        for d in disks:
            job = self.disk_in_use(d)
            if job is not None:
                return f"{d.path} wird gerade verwendet ({job.title})."
        return ""

    # ---------- Ablauf ----------

    def start_usb_job(self, title: str, cmd: list[str], stdin_text: str, disks, on_progress, on_line,
                      on_done) -> bool:
        from okula_recovery import usbjobs
        cwd = str(Path(stick.__file__).resolve().parent.parent)
        idents = [d.ident() for d in disks if d is not None]
        try:
            self.usb_job = usbjobs.start(self.usb_manager(), title, cmd, stdin_text, idents, on_progress, on_line,
                                         on_done, post=GLib.idle_add, cwd=cwd)
        except usbjobs.Busy as e:
            confirm_error(self, str(e), title="Datenträger wird gerade verwendet")
            return False
        JOB_WINDOWS[self.usb_job.id] = self
        return True

    def cancel_usb_job(self, text: str) -> None:
        """Abbrechen mit Rückfrage – gleich wie in der Auftragsliste."""
        from okula_recovery import usbjobs
        if self.usb_running and confirm(self, "Wirklich abbrechen?", text, ok_label="Abbrechen"):
            usbjobs.cancel(self.usb_manager(), self.usb_job)
            self.usb_cancel_requested()

    def usb_cancel_requested(self) -> None:
        """Abbruch angefordert (Fenster oder Auftragsliste): Knopf sperren, im Protokoll vermerken."""
        if getattr(self, "btn_cancel", None) is not None:
            self.btn_cancel.set_sensitive(False)
        log = getattr(self, "_log", None) or getattr(self, "append_log", None)
        if log is not None:
            log("Wird abgebrochen …")

    def usb_finished(self) -> bool:
        """Am Ende des Vorgangs aufrufen. True = das Fenster war ausgeblendet (Ergebnis steht in der
        Auftragsliste; das Fenster wird danach geschlossen)."""
        if self.usb_job is not None:
            JOB_WINDOWS.pop(self.usb_job.id, None)
        return not self.get_visible()

    def result_parent(self) -> Gtk.Window:
        """Fenster für das Ergebnis-Popup: dieses, oder das Hauptfenster, wenn es ausgeblendet ist."""
        return self if self.get_visible() else (self.get_transient_for() or self)

    def _on_usb_delete(self, *_a) -> bool:
        if self.usb_running:
            self.hide()       # Vorgang läuft weiter – Auftragsliste „USB-Vorgänge“ → Anzeigen
            return True
        return bool(getattr(self, "busy", False))

    def close_or_hide(self) -> None:
        if self.usb_running:
            self.hide()
        elif not getattr(self, "busy", False):
            self.destroy()

    def _on_usb_change(self) -> None:
        """Ein USB-Vorgang hat begonnen oder geendet: belegte Datenträger neu anzeigen."""
        if not self.usb_running and not getattr(self, "busy", False):
            self.refresh_disks()


def show_job_window(job_id: int) -> bool:
    """Auftragsliste → Anzeigen: Fenster des Vorgangs wieder zeigen. False = Fenster gibt es nicht mehr."""
    win = JOB_WINDOWS.get(job_id)
    if win is None:
        return False
    win.present()
    return True


def job_cancel_requested(job_id: int) -> None:
    win = JOB_WINDOWS.get(job_id)
    if win is not None:
        win.usb_cancel_requested()


def result_status(ok: bool, error: str) -> str:
    """Text im Fortschrittsbalken am Ende: Fertig / Abgebrochen / Datenträger getrennt / Fehlgeschlagen."""
    if ok:
        return "Fertig"
    if error.startswith("Datenträger getrennt"):
        return "Datenträger getrennt – abgebrochen"
    if error.startswith("Abgebrochen"):
        return "Abgebrochen"
    return "Fehlgeschlagen"



def boot_keys_table() -> Gtk.Widget:
    """Tabelle „Boot-Menü-Taste je Hersteller“ (zum Starten vom Stick)."""
    from okula_recovery import bootkeys
    store = Gtk.ListStore(str, str, str, str)
    for k in bootkeys.TABLE.values():
        store.append([k.vendor, k.boot, k.bios, k.hint])
    view = Gtk.TreeView(model=store)
    for i, title in enumerate(("Hersteller", "Boot-Menü", "BIOS", "Hinweis")):
        cell = Gtk.CellRendererText(wrap_mode=Pango.WrapMode.WORD_CHAR, wrap_width=(150, 150, 120, 250)[i])
        col = Gtk.TreeViewColumn(title, cell, text=i)
        col.set_resizable(True)
        view.append_column(col)
    view.get_selection().set_mode(Gtk.SelectionMode.NONE)
    sw = Gtk.ScrolledWindow(hexpand=True)
    sw.set_shadow_type(Gtk.ShadowType.IN)
    sw.set_min_content_height(170)
    sw.add(view)
    expander = Gtk.Expander(label="Boot-Menü-Taste je Hersteller – Gerät einschalten und Taste antippen, "
                                  "dann den USB-Stick wählen", expanded=True)
    expander.add(sw)
    return expander

class StickDialog(UsbJobMixin, Gtk.Dialog):
    """Agent-Stick (image=None) oder Restore-Stick mit genau einem Image."""

    def __init__(self, parent: Gtk.Window, image: str | None = None, source_disks: list[str] | None = None):
        title = "Restore-Stick erstellen" if image else "Agent-USB-Stick erstellen"
        super().__init__(title=title, transient_for=parent, modal=False)   # Ä-052: Tool bleibt bedienbar
        self.set_default_size(780, 640)
        self.busy = False
        self.image = image
        self.image_size = stick.tree_size(Path(image)) if image else 0
        self.disk_sizes: dict[str, int] = {}
        self.disks: dict[str, stick.UsbDisk] = {}
        self.btn_close = self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.btn_cancel = self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn_start = self.add_button("Stick vorbereiten", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("destructive-action")
        self.connect("response", self.on_response)
        self._init_usb()   # Schliessen während des Schreibens: Fenster aus, Vorgang läuft weiter

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)

        grid.attach(Gtk.Label(label="USB-Stick", xalign=0), 0, 0, 1, 1)
        self.disk_combo = Gtk.ComboBoxText(hexpand=True)
        self.disk_combo.connect("changed", lambda _c: self._update_sensitivity())
        self.mark_in_use(self.disk_combo, self.disks_get)
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

        self.server_ip = Gtk.Entry(text="")
        self.source_disk = Gtk.ComboBoxText()
        if image:
            grid.attach(Gtk.Label(label="Image", xalign=0), 0, 2, 1, 1)
            info = Gtk.Label(xalign=0, wrap=True, selectable=True)
            info.set_markup(f"<b>{GLib.markup_escape_text(Path(image).name)}</b>  "
                            f"({self.image_size / 1000**3:.1f} GB) – der Stick spielt es nach Rückfrage "
                            "am Bildschirm auf eine Disk zurück, ohne Netzwerk")
            grid.attach(info, 1, 2, 2, 1)
            if source_disks and len(source_disks) > 1:
                grid.attach(Gtk.Label(label="Disk im Image", xalign=0), 0, 6, 1, 1)
                for d in source_disks:
                    self.source_disk.append(d, d)
                self.source_disk.set_active(0)
                grid.attach(self.source_disk, 1, 6, 2, 1)
        else:
            grid.attach(Gtk.Label(label="Server-IP", xalign=0), 0, 2, 1, 1)
            ifaces = network.local_interfaces()
            self.server_ip.set_text(str(ifaces[0].ip) if ifaces else "")
            self.server_ip.set_placeholder_text("leer = nur Broadcast")
            self.server_ip.set_tooltip_text("Der Agent meldet sich per Broadcast und zusätzlich direkt an diese IP")
            grid.attach(self.server_ip, 1, 2, 2, 1)

        warn = Gtk.Label(xalign=0, wrap=True)
        warn.set_markup("<b>Achtung:</b> Alle Daten auf dem gewählten Stick werden gelöscht."
                        + (f" Der Stick braucht mindestens <b>{self.required_size() / 1000**3:.0f} GB</b>."
                           if image else ""))
        warn.get_style_context().add_class("status-fail")
        grid.attach(warn, 0, 3, 3, 1)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_text("Bereit")
        # Hinweis unter dem Balken, nur während der Stick geschrieben wird
        self.unplug_hint = Gtk.Label(xalign=0, wrap=True, no_show_all=True)
        self.unplug_hint.set_markup(f"<b>{GLib.markup_escape_text(UNPLUG_HINT)}</b>")
        self.unplug_hint.get_style_context().add_class("status-fail")
        bar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bar_box.pack_start(self.progress, False, False, 0)
        bar_box.pack_start(self.unplug_hint, False, False, 0)
        grid.attach(bar_box, 0, 4, 3, 1)

        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.log)
        grid.attach(sw, 0, 5, 3, 1)

        grid.attach(boot_keys_table(), 0, 7, 3, 1)
        self.get_content_area().add(grid)
        self.refresh_disks()
        self.show_all()
        self.btn_cancel.hide()

    # ---------- Zustand ----------

    def selected_disk(self) -> str | None:
        return self.disk_combo.get_active_id()

    def disks_get(self, path: str | None) -> stick.UsbDisk | None:
        return self.disks.get(path or "")

    def _update_sensitivity(self) -> None:
        disk = self.selected_disk()
        need = self.required_size() if self.image else stick.MIN_SIZE
        big_enough = disk is not None and self.disk_sizes.get(disk, 0) >= need
        free = self.disk_in_use(self.disks_get(disk)) is None
        ready = not self.busy and big_enough and free and bool(self.iso_chooser.get_filename())
        self.btn_start.set_sensitive(ready)
        for w in (self.btn_download, self.btn_refresh, self.disk_combo, self.iso_chooser, self.server_ip):
            w.set_sensitive(not self.busy)
        self.btn_close.set_sensitive(not self.busy or self.usb_running)   # während des Schreibens: ausblenden
        self.btn_cancel.set_visible(self.usb_running)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self._update_sensitivity()

    def append_log(self, text: str) -> None:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)

    def required_size(self) -> int:
        """Mindestgrösse des Sticks für den Restore-Stick (ISO-Grösse geschätzt, falls noch keins gewählt)."""
        iso = self.iso_chooser.get_filename() if hasattr(self, "iso_chooser") else None
        iso_size = Path(iso).stat().st_size if iso and Path(iso).is_file() else 1_600_000_000
        return stick.restore_need(iso_size, self.image_size)[1]

    def refresh_disks(self) -> None:
        old = self.disk_combo.get_active_id()
        self.disk_combo.remove_all()
        disks = stick.list_usb_disks()
        need = self.required_size() if self.image else stick.MIN_SIZE
        self.disk_sizes = {d.path: d.size for d in disks}
        self.disks = {d.path: d for d in disks}
        for d in disks:
            self.disk_combo.append(d.path, self.disk_text(d, "  – zu klein" if d.size < need else ""))
        if old in self.disks:
            self.disk_combo.set_active_id(old)
        elif disks:
            free = [i for i, d in enumerate(disks) if self.disk_in_use(d) is None]
            self.disk_combo.set_active(free[0] if free else 0)
        else:
            self.append_log("Kein USB-Stick gefunden – Stick einstecken und neu suchen.")
        self._update_sensitivity()

    # ---------- ISO herunterladen ----------

    def on_download(self, _btn) -> None:
        self._set_busy(True)
        self.append_log(f"Debian-Live-ISO wird geladen von {isofetch.BASE_URL}")

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
        elif response == Gtk.ResponseType.CANCEL:
            self.cancel_usb_job("Der Stick bleibt unvollständig und muss danach neu erstellt werden.")
        else:
            self.close_or_hide()

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
            cmd = helper_command(device, iso, self.server_ip.get_text().strip(), self.image,
                                 self.source_disk.get_active_id(), self.disks.get(device))
        except FileNotFoundError as e:
            self.append_log(str(e))
            return

        key_hex = agentclient.load_or_create_key().hex()
        disk = self.disks.get(device)
        what = "Restore-Stick" if self.image else "Agent-Stick"
        if not self.start_usb_job(f"{what} → {disk.name if disk else device} ({device})", cmd, key_hex + "\n",
                                  [disk], self._on_progress, self.append_log, self._on_written):
            return
        self._set_busy(True)
        self.btn_cancel.set_sensitive(True)
        self.unplug_hint.show()
        self.append_log(f"{what} wird auf {device} erstellt …")

    def _on_written(self, ok: bool, error: str) -> bool:
        hidden = self.usb_finished()
        parent = self.result_parent()
        self._set_busy(False)
        self.unplug_hint.hide()
        if ok:
            self.progress.set_fraction(1.0)
            self.progress.set_text("Stick bereit")
        else:
            self.progress.set_text(result_status(ok, error))
            if error:
                self.append_log(f"Fehler: {error}")
        if not hidden:
            self.refresh_disks()
        show_stick_result(parent, ok, error, "Restore-Stick fertig" if self.image else "Agent-Stick fertig")
        if hidden:
            self.destroy()       # Ergebnis steht in der Auftragsliste
        return False
