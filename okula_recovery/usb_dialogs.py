"""Tools → „USB klonen …“ und „USB formatieren …“ (USB-Sticks und externe Festplatten).

Die Arbeit macht der Root-Helfer (okula-make-stick usb-clone / usb-format, siehe usbtools.py).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from okula_recovery import stick, usbtools  # noqa: E402
from okula_recovery.stick_dialog import helper_subcommand, run_helper  # noqa: E402
from okula_recovery.uikit import confirm, scrolled  # noqa: E402
from okula_recovery.usbtools import DiskInfo, disk_details, gb  # noqa: E402

class _UsbDialog(Gtk.Dialog):
    """Gemeinsam: Datenträgerliste, Fortschritt, Protokoll, Abbrechen, kein Schliessen während der Arbeit."""

    START_LABEL = "Start"

    def __init__(self, parent: Gtk.Window, title: str):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(760, 640)
        self.busy = False
        self.run_handle = None
        self.disks: list[stick.UsbDisk] = []
        self.details: dict[str, DiskInfo] = {}
        self.btn_close = self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.btn_cancel = self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn_start = self.add_button(self.START_LABEL, Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("destructive-action")
        self.connect("response", self._on_response)
        self.connect("delete-event", lambda *_a: self.busy)
        self.grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        self.row = 0

    def _finish_layout(self, warning: str) -> None:
        warn = Gtk.Label(xalign=0, wrap=True)
        warn.set_markup(warning)
        warn.get_style_context().add_class("status-fail")
        self._attach(warn)
        self.bar = Gtk.ProgressBar(show_text=True)
        self.bar.set_text("Bereit")
        self._attach(self.bar)
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sw = scrolled(self.log)
        sw.set_min_content_height(110)
        sw.set_vexpand(True)
        self._attach(sw)
        self.get_content_area().pack_start(self.grid, True, True, 0)
        self.show_all()
        self.btn_cancel.hide()
        self.refresh_disks()

    def _attach(self, widget: Gtk.Widget, label: str | None = None) -> None:
        if label is None:
            self.grid.attach(widget, 0, self.row, 3, 1)
        else:
            self.grid.attach(Gtk.Label(label=label, xalign=0, yalign=0.5), 0, self.row, 1, 1)
            self.grid.attach(widget, 1, self.row, 2, 1)
        self.row += 1

    def _info_label(self) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0, wrap=True)
        lbl.get_style_context().add_class("status-idle")
        return lbl

    def _refresh_button(self) -> Gtk.Button:
        b = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        b.set_tooltip_text("Datenträger neu suchen (nach dem Einstecken)")
        b.connect("clicked", lambda _b: self.refresh_disks())
        self.btn_refresh = b
        return b

    def _disk_combo(self) -> Gtk.ComboBoxText:
        combo = Gtk.ComboBoxText(hexpand=True)
        combo.connect("changed", lambda _c: self._update())
        return combo

    def _fill(self, combo: Gtk.ComboBoxText, active: int = 0) -> None:
        old = combo.get_active_id()
        combo.remove_all()
        for d in self.disks:
            combo.append(d.path, d.label)
        if old and old in {d.path for d in self.disks}:
            combo.set_active_id(old)
        elif self.disks:
            combo.set_active(min(active, len(self.disks) - 1))

    def refresh_disks(self) -> None:
        self.disks = stick.list_usb_disks()
        self.details = disk_details()
        self._fill_disks()
        if not self.disks:
            self._log("Kein USB-Datenträger gefunden – einstecken und mit ⟳ neu suchen.")
        self._update()

    def _fill_disks(self) -> None:
        raise NotImplementedError

    def _update(self) -> None:
        raise NotImplementedError

    def _log(self, text: str) -> bool:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        return False

    def _line(self, line: str) -> bool:
        kind, _, text = line.partition(" ")
        prefix = {"WARN": "Hinweis: ", "ERROR": "Fehler: ", "DONE": "Fertig: "}.get(kind)
        return self._log(prefix + text if prefix else line)

    def _progress(self, frac: float, msg: str) -> bool:
        self.bar.set_fraction(max(0.0, min(1.0, frac)))
        self.bar.set_text(f"{frac * 100:.0f} %  {msg}")
        return False

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.btn_cancel.set_visible(busy)
        self.btn_cancel.set_sensitive(True)
        self.btn_close.set_sensitive(not busy)
        self._update()

    def run_helper(self, sub: str, args: list[str], intro: str) -> None:
        try:
            cmd = helper_subcommand(sub, args)
        except FileNotFoundError as e:
            self._log(str(e))
            return
        self._set_busy(True)
        self.bar.set_fraction(0.0)
        self._log(intro)
        self.run_handle = run_helper(cmd, "", self._progress, self._line, self._done, keep_stdin=True)

    def _done(self, ok: bool, error: str) -> bool:
        self._set_busy(False)
        if ok:
            self.bar.set_fraction(1.0)
            self.bar.set_text("Fertig – Datenträger kann abgezogen werden")
        else:
            self.bar.set_text("Abgebrochen" if "Abgebrochen" in error else "Fehlgeschlagen")
            if error and not error.startswith("Abgebrochen"):
                self._log(f"Fehler: {error}")
        self.refresh_disks()
        return False

    def _on_response(self, _dlg, response: int) -> None:
        if response == Gtk.ResponseType.APPLY:
            self.start()
        elif response == Gtk.ResponseType.CANCEL:
            if self.busy and self.run_handle and confirm(self, "Wirklich abbrechen?",
                                                         "Der Ziel-Datenträger bleibt unvollständig und muss danach "
                                                         "neu beschrieben werden.", ok_label="Abbrechen"):
                self.btn_cancel.set_sensitive(False)
                self._log("Breche ab …")
                self.run_handle.cancel()
        elif not self.busy:
            self.destroy()

    def start(self) -> None:
        raise NotImplementedError


class CloneDialog(_UsbDialog):
    """USB-Stick oder externe Festplatte 1:1 auf einen anderen Datenträger kopieren."""

    START_LABEL = "Klonen"

    def __init__(self, parent: Gtk.Window):
        super().__init__(parent, "USB-Datenträger klonen")
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup("Kopiert einen USB-Stick oder eine externe Festplatte komplett auf einen anderen – mit "
                        "allen Partitionen, Dateien und (falls vorhanden) der Startfähigkeit.")
        self._attach(head)
        self.src = self._disk_combo()
        box = Gtk.Box(spacing=6)
        box.pack_start(self.src, True, True, 0)
        box.pack_start(self._refresh_button(), False, False, 0)
        self._attach(box, "Quelle (wird gelesen)")
        self.src_info = self._info_label()
        self._attach(self.src_info, "")
        self.dst = self._disk_combo()
        self._attach(self.dst, "Ziel (wird gelöscht)")
        self.dst_info = self._info_label()
        self._attach(self.dst_info, "")

        self.smart = Gtk.RadioButton.new_with_label(None, "Nur belegte Bereiche kopieren – schneller (empfohlen)")
        self.raw = Gtk.RadioButton.new_with_label_from_widget(
            self.smart, "Alles 1:1, Sektor für Sektor – auch verschlüsselte oder unbekannte Formate (langsamer)")
        for r in (self.smart, self.raw):
            r.connect("toggled", lambda _r: self._update())
        mode = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        mode.pack_start(self.smart, False, False, 0)
        mode.pack_start(self.raw, False, False, 0)
        hint = self._info_label()
        hint.set_markup("<small>„Nur belegte Bereiche“ kennt FAT, exFAT, NTFS, ext2/3/4, Btrfs, XFS, HFS+ und F2FS; "
                        "alles andere wird automatisch 1:1 kopiert. Das Ziel darf dann auch kleiner als die Quelle "
                        "sein, solange alle Partitionen Platz haben.</small>")
        mode.pack_start(hint, False, False, 0)
        self._attach(mode, "Art")
        self.verify = Gtk.CheckButton(label="Danach vergleichen (Quelle und Ziel ganz lesen, doppelte Zeit)")
        self._attach(self.verify, "")
        self.check = Gtk.Label(xalign=0, wrap=True)
        self._attach(self.check, "")
        self._finish_layout("<b>Achtung:</b> Alle Daten auf dem <b>Ziel</b> werden gelöscht. "
                            "Die Quelle wird nur gelesen.")

    def _fill_disks(self) -> None:
        self._fill(self.src, 0)
        self._fill(self.dst, 1)

    def _check(self) -> tuple[bool, str]:
        s, d = self.src.get_active_id(), self.dst.get_active_id()
        if not s or not d:
            return False, "Zum Klonen braucht es zwei USB-Datenträger."
        if s == d:
            return False, "Quelle und Ziel müssen verschiedene Datenträger sein."
        src = self.details.get(s)
        src_size = next((x.size for x in self.disks if x.path == s), 0)
        dst_size = next((x.size for x in self.disks if x.path == d), 0)
        smart = self.smart.get_active() and src is not None and src.parts
        need = src.used_end if smart and src else src_size
        if need > dst_size:
            return False, f"Ziel zu klein: {gb(dst_size)}, nötig {gb(need)}."
        text = f"Ziel gross genug: {gb(dst_size)}, nötig {gb(need)}."
        if dst_size > need + 1000**3:
            text += f" Danach bleiben {gb(dst_size - need)} auf dem Ziel frei."
        return True, text

    def _update(self) -> None:
        for combo, label in ((self.src, self.src_info), (self.dst, self.dst_info)):
            info = self.details.get(combo.get_active_id() or "")
            label.set_text(f"Inhalt: {info.summary()}" if info else "")
        self.verify.set_sensitive(self.raw.get_active() and not self.busy)
        if not self.raw.get_active():
            self.verify.set_active(False)
        ok, text = self._check()
        self.check.set_text(text)
        ctx = self.check.get_style_context()
        ctx.remove_class("status-ok" if not ok else "status-fail")
        ctx.add_class("status-ok" if ok else "status-fail")
        self.btn_start.set_sensitive(ok and not self.busy)
        for w in (self.src, self.dst, self.smart, self.raw, self.btn_refresh):
            w.set_sensitive(not self.busy)

    def start(self) -> None:
        ok, _text = self._check()
        if not ok:
            return
        s, d = self.src.get_active_id(), self.dst.get_active_id()
        if not confirm(self, "Ziel wirklich überschreiben?",
                       f"Quelle: {self.src.get_active_text()}\nZiel: {self.dst.get_active_text()}\n\n"
                       "Alle Daten auf dem Ziel gehen verloren.", ok_label="Ziel überschreiben"):
            return
        mode = "raw" if self.raw.get_active() else "smart"
        args = ["--source", s, "--target", d, "--mode", mode] + (["--verify"] if self.verify.get_active() else [])
        self.run_helper("usb-clone", args, f"Klone {s} → {d} ({'1:1' if mode == 'raw' else 'nur belegte Bereiche'}) …")


SCHEMES = {"mbr": "MBR – passt überall (Windows, Mac, TV, ältere PCs), bis 2 TB",
           "gpt": "GPT – für Festplatten über 2 TB und moderne PCs",
           "none": "Ohne Partitionstabelle – ganzer Datenträger ein Dateisystem (selten nötig)"}
PREPS = {"none": "Nichts – nur formatieren (schnell)",
         "quick": "Schnelltest: gefälschte Sticks erkennen (wenige Sekunden)",
         "zero": "Mit Nullen überschreiben – alte Daten sicher weg (langsam)",
         "full": "Vollständiger Test: jeden Block schreiben und lesen (sehr langsam)"}


class FormatDialog(_UsbDialog):
    """USB-Stick oder externe Festplatte mit einem gängigen Dateisystem neu formatieren."""

    START_LABEL = "Formatieren"

    def __init__(self, parent: Gtk.Window):
        super().__init__(parent, "USB-Datenträger formatieren")
        self.disk = self._disk_combo()
        box = Gtk.Box(spacing=6)
        box.pack_start(self.disk, True, True, 0)
        box.pack_start(self._refresh_button(), False, False, 0)
        self._attach(box, "Datenträger")
        self.disk_info = self._info_label()
        self._attach(self.disk_info, "")

        # Dateisysteme: id, Text, wählbar (Programm vorhanden)
        self.fs_store = Gtk.ListStore(str, str, bool)
        for spec in usbtools.FILESYSTEMS.values():
            ok = usbtools.available(spec)
            self.fs_store.append([spec.key, spec.title + ("" if ok else f"  (Paket {spec.package} fehlt)"), ok])
        self.fs = Gtk.ComboBox(model=self.fs_store, id_column=0)
        cell = Gtk.CellRendererText()
        self.fs.pack_start(cell, True)
        self.fs.add_attribute(cell, "text", 1)
        self.fs.add_attribute(cell, "sensitive", 2)
        self.fs.connect("changed", lambda _c: self._on_fs())
        self._attach(self.fs, "Dateisystem")
        self.fs_note = self._info_label()
        self._attach(self.fs_note, "")

        self.scheme = Gtk.ComboBoxText()
        for k, v in SCHEMES.items():
            self.scheme.append(k, v)
        self.scheme.set_active_id("mbr")
        self.scheme.connect("changed", lambda _c: self._update())
        self._attach(self.scheme, "Partitionsschema")
        self.label = Gtk.Entry(placeholder_text="z. B. DATEN – leer lassen geht auch")
        self.label.connect("changed", lambda _e: self._update())
        self._attach(self.label, "Name")
        self.label_hint = self._info_label()
        self._attach(self.label_hint, "")
        self.prep = Gtk.ComboBoxText()
        for k, v in PREPS.items():
            self.prep.append(k, v)
        self.prep.set_active_id("none")
        self._attach(self.prep, "Vorher")
        self.check = Gtk.Label(xalign=0, wrap=True)
        self._attach(self.check, "")
        self.fs.set_active_id("fat32")
        self._auto_fs = True  # Vorschlag nach Grösse, bis jemand selbst wählt
        self._finish_layout("<b>Achtung:</b> Alle Daten auf dem gewählten Datenträger werden gelöscht.")

    def _fill_disks(self) -> None:
        self._fill(self.disk, 0)

    def _size(self) -> int:
        return next((d.size for d in self.disks if d.path == self.disk.get_active_id()), 0)

    def _suggest(self) -> None:
        """Vorschlag nach Grösse: bis 32 GB FAT32 (läuft überall), darüber exFAT; über 2 TB GPT."""
        size = self._size()
        if self._auto_fs and size:
            want = "fat32" if size <= 32 * 1000**3 else "exfat"
            if any(r[0] == want and r[2] for r in self.fs_store):
                self.fs.set_active_id(want)
        if size > usbtools.MBR_LIMIT and self.scheme.get_active_id() == "mbr":
            self.scheme.set_active_id("gpt")

    def _on_fs(self) -> None:
        self._auto_fs = False
        spec = usbtools.FILESYSTEMS.get(self.fs.get_active_id() or "")
        if spec:
            self.fs_note.set_text(spec.note)
            self.label.set_max_length(spec.label_max or 1)
        self._update()

    def _check(self) -> tuple[bool, str]:
        spec = usbtools.FILESYSTEMS.get(self.fs.get_active_id() or "")
        size = self._size()
        if not self.disk.get_active_id():
            return False, "Kein USB-Datenträger gewählt."
        if spec is None or not usbtools.available(spec):
            return False, "Dateisystem wählen."
        if spec.key != "none" and self.scheme.get_active_id() == "mbr" and size > usbtools.MBR_LIMIT:
            return False, "MBR reicht nur bis 2 TB – GPT wählen."
        if spec.max_size and size > spec.max_size + 64 * 1024**2:
            return False, f"{spec.title} geht nur bis {spec.max_size / 1024**3:.0f} GB – anderes Dateisystem wählen."
        if spec.min_size and size < spec.min_size:
            return False, f"{spec.title} braucht mindestens {spec.min_size / 1024**2:.0f} MB."
        return True, f"Wird {spec.title} auf {gb(size)}." if spec.key != "none" else "Datenträger wird geleert."

    def _update(self) -> None:
        if not self.busy and self.disk.get_active_id() != getattr(self, "_last_disk", None):
            self._last_disk = self.disk.get_active_id()
            auto = self._auto_fs
            self._suggest()
            self._auto_fs = auto
        info = self.details.get(self.disk.get_active_id() or "")
        self.disk_info.set_text(f"Inhalt jetzt: {info.summary()}" if info else "")
        spec = usbtools.FILESYSTEMS.get(self.fs.get_active_id() or "")
        none = spec is not None and spec.key == "none"
        self.label.set_sensitive(not none and not self.busy)
        self.scheme.set_sensitive(not none and not self.busy)
        text = self.label.get_text()
        clean = usbtools.clean_label(spec, text) if spec else text
        self.label_hint.set_text(f"Wird zu „{clean}“ (Regel von {spec.title})" if spec and text and clean != text
                                 else "")
        ok, msg = self._check()
        self.check.set_text(msg)
        ctx = self.check.get_style_context()
        ctx.remove_class("status-ok" if not ok else "status-fail")
        ctx.add_class("status-ok" if ok else "status-fail")
        self.btn_start.set_sensitive(ok and not self.busy)
        for w in (self.disk, self.fs, self.prep, self.btn_refresh):
            w.set_sensitive(not self.busy)

    def start(self) -> None:
        ok, _msg = self._check()
        if not ok:
            return
        spec = usbtools.FILESYSTEMS[self.fs.get_active_id()]
        dev = self.disk.get_active_id()
        if not confirm(self, "Datenträger wirklich formatieren?",
                       f"{self.disk.get_active_text()}\n→ {spec.title}\n\nAlle Daten darauf gehen verloren.",
                       ok_label="Formatieren"):
            return
        args = ["--device", dev, "--fs", spec.key, "--scheme", self.scheme.get_active_id(),
                "--label", self.label.get_text().strip(), "--prep", self.prep.get_active_id()]
        self.run_helper("usb-format", args, f"Formatiere {dev} als {spec.title} …")
