"""Dialoge für Betriebssysteme: ISOs hochladen, Details und Prüfsummen, Boot-Stick erstellen."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import isostick, nas, oslib, stick, winunattend  # noqa: E402
from okula_recovery.stick_dialog import iso_stick_command, run_helper  # noqa: E402
from okula_recovery.uikit import confirm, scrolled  # noqa: E402

MODE_LABELS = {
    "windows": "Windows-Installation (FAT32, UEFI mit Secure Boot und BIOS)",
    "dd": "Abbild 1:1 schreiben (DD) – empfohlen für Linux-ISOs",
    "files": "Dateien kopieren (FAT32, nur UEFI)",
}
CHECK_LABELS = {"quick": "Schnelltest: gefälschte Kapazität erkennen (wenige Sekunden)",
                "full": "Vollständig: alle Blöcke schreiben und lesen (badblocks, dauert lange)",
                "none": "Nicht prüfen"}


def choose_isos(parent: Gtk.Window) -> list[str]:
    dlg = Gtk.FileChooserDialog(title="ISO-Dateien hinzufügen", transient_for=parent,
                                action=Gtk.FileChooserAction.OPEN)
    dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Hinzufügen", Gtk.ResponseType.OK)
    dlg.set_select_multiple(True)
    flt = Gtk.FileFilter()
    flt.set_name("ISO- und Disk-Abbilder (*.iso, *.img, *.img.xz …)")
    for s in oslib.SUFFIXES:
        flt.add_pattern("*" + s)
        flt.add_pattern("*" + s.upper())
    dlg.add_filter(flt)
    files = dlg.get_filenames() if dlg.run() == Gtk.ResponseType.OK else []
    dlg.destroy()
    return files


def _row(grid: Gtk.Grid, row: int, key: str, value: str) -> Gtk.Label:
    k = Gtk.Label(label=key, xalign=0, yalign=0)
    k.get_style_context().add_class("status-idle")
    v = Gtk.Label(label=value or "–", xalign=0, selectable=True, wrap=True)
    grid.attach(k, 0, row, 1, 1)
    grid.attach(v, 1, row, 1, 1)
    return v


class UploadDialog(Gtk.Window):
    """ISO-Dateien aufs NAS kopieren – läuft weiter, auch wenn das Fenster im Hintergrund ist."""

    def __init__(self, parent: Gtk.Window, root: str, files: list[str], dest_rel: str | None,
                 on_done: Callable[[], None]):
        super().__init__(title="ISO hochladen", transient_for=parent)
        self.set_default_size(620, 300)
        self.root, self.files, self.dest_rel, self.on_done = root, files, dest_rel, on_done
        self.cancel = threading.Event()
        self.running = True
        self.connect("delete-event", self._on_close)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        where = f"NAS: /{oslib.OS_DIR}/{dest_rel}" if dest_rel else "automatisch nach Windows / Linux / Sonstige"
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"<b>{len(files)} Datei{'en' if len(files) != 1 else ''}</b> → {GLib.markup_escape_text(where)}")
        box.pack_start(head, False, False, 0)
        self.bar = Gtk.ProgressBar(show_text=True)
        box.pack_start(self.bar, False, False, 0)
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        box.pack_start(scrolled(self.log), True, True, 0)
        buttons = Gtk.Box(spacing=6)
        self.btn = Gtk.Button(label="Abbrechen")
        self.btn.connect("clicked", self._on_button)
        buttons.pack_end(self.btn, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.add(box)
        self.show_all()
        threading.Thread(target=self._work, daemon=True).start()

    def _log(self, text: str) -> bool:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), time.strftime("%H:%M:%S ") + text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        return False

    def _progress(self, i: int, name: str, done: int, total: int, started: float) -> bool:
        frac = done / total if total else 1.0
        speed = done / max(time.monotonic() - started, 0.001)
        rest = (total - done) / speed if speed > 0 and done else 0
        self.bar.set_fraction(frac)
        self.bar.set_text(f"{i}/{len(self.files)}  {name}  {frac * 100:.0f} %  ·  {speed / 1e6:.0f} MB/s"
                          + (f"  ·  noch {rest / 60:.0f} min" if rest > 60 else ""))
        return False

    def _work(self) -> None:
        ok = 0
        for i, f in enumerate(self.files, 1):
            if self.cancel.is_set():
                break
            name = os.path.basename(f)
            GLib.idle_add(self._log, f"Kopiere {name} …")
            started, last = time.monotonic(), [0.0]

            def progress(done, total, i=i, name=name, started=started):
                if time.monotonic() - last[0] >= 0.3 or done == total:
                    last[0] = time.monotonic()
                    GLib.idle_add(self._progress, i, name, done, total, started)

            try:
                target = oslib.add_iso(self.root, f, self.dest_rel, progress, self.cancel)
                meta = oslib.load_meta(target) or {}
                GLib.idle_add(self._log, f"✓ {target.name}: {meta.get('title', '')} → "
                                         f"{target.parent.relative_to(Path(self.root))}")
                GLib.idle_add(self._log, f"  SHA-256 {meta.get('sha256', '')}")
                ok += 1
            except Exception as e:  # Datei, NAS, Platz – pro Datei melden und weitermachen
                GLib.idle_add(self._log, f"✗ {name}: {e}")
        GLib.idle_add(self._finished, ok)

    def _finished(self, ok: int) -> bool:
        self.running = False
        self.bar.set_fraction(1.0 if ok == len(self.files) else self.bar.get_fraction())
        self.bar.set_text(f"{ok} von {len(self.files)} hochgeladen")
        self.btn.set_label("Schliessen")
        self.on_done()
        return False

    def _on_button(self, _btn) -> None:
        if self.running:
            self.cancel.set()
            self._log("Abbruch angefordert …")
        else:
            self.destroy()

    def _on_close(self, *_a) -> bool:
        if self.running:
            self.cancel.set()
        return False


class IsoDetailsDialog(Gtk.Dialog):
    """Was steckt in der ISO? Editionen, Bootfähigkeit, Prüfsummen (mit Vergleich)."""

    def __init__(self, parent: Gtk.Window, iso: oslib.IsoInfo):
        super().__init__(title=f"ISO – {iso.name}", transient_for=parent, modal=False)
        self.set_default_size(720, 520)
        self.iso = iso
        self.cancel = threading.Event()
        self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda *_a: (self.cancel.set(), self.destroy()))
        meta = iso.meta
        grid = Gtk.Grid(column_spacing=16, row_spacing=4, margin=12)
        r = 0
        for key, value in (("Medium", iso.title), ("Datei", str(iso.path)), ("Grösse", nas.format_size(iso.size)),
                           ("Art", oslib.describe(meta)),
                           ("Startet über", ", ".join(p for p, on in (("UEFI", meta.get("uefi")),
                                                                     ("BIOS", meta.get("bios")),
                                                                     ("Hybrid (DD)", meta.get("hybrid"))) if on)),
                           ("Volume-ID", meta.get("volume_id", ""))):
            _row(grid, r, key, value)
            r += 1
        w = meta.get("windows")
        if w:
            eds = "\n".join(f"{e['index']}: {e['name']}  ({e['edition_id']}, Build {e['build']}, {e['arch']})"
                            for e in w.get("editions", []))
            _row(grid, r, "Editionen", eds)
            _row(grid, r + 1, "Abbild", f"sources/{w.get('wim', '')}  ({nas.format_size(w.get('wim_size', 0))})"
                 + ("  – wird auf dem Stick gesplittet (> 4 GB)" if w.get("wim_size", 0) > isostick.FAT32_MAX else ""))
            r += 2
        lx = meta.get("linux")
        if lx:
            _row(grid, r, "Distribution", lx.get("info", ""))
            r += 1
        _row(grid, r, "Direkt installierbar", "ja (folgt: „Auf Gerät installieren“)" if oslib.installable(meta)
             else "nein – nur als Boot-Stick")
        r += 1
        sep = Gtk.Separator(margin_top=8, margin_bottom=8)
        grid.attach(sep, 0, r, 2, 1)
        r += 1
        self.sums: dict[str, Gtk.Label] = {}
        for algo, label in (("md5", "MD5"), ("sha1", "SHA-1"), ("sha256", "SHA-256"), ("sha512", "SHA-512")):
            v = _row(grid, r, label, meta.get("sha256", "") if algo == "sha256" else "")
            v.get_style_context().add_class("monospace")
            v.set_line_wrap_mode(Pango.WrapMode.CHAR)
            self.sums[algo] = v
            r += 1
        grid.attach(Gtk.Label(label="Vergleichen", xalign=0), 0, r, 1, 1)
        self.compare = Gtk.Entry(placeholder_text="Prüfsumme von der Herstellerseite einfügen", hexpand=True)
        self.compare.connect("changed", lambda _e: self._compare())
        grid.attach(self.compare, 1, r, 1, 1)
        r += 1
        self.result = Gtk.Label(xalign=0)
        grid.attach(self.result, 1, r, 1, 1)
        r += 1
        self.btn_sums = Gtk.Button(label="Alle Prüfsummen berechnen", halign=Gtk.Align.START)
        self.btn_sums.connect("clicked", self._calc)
        grid.attach(self.btn_sums, 1, r, 1, 1)
        r += 1
        self.bar = Gtk.ProgressBar(show_text=True, hexpand=True)
        self.bar.set_text("MD5, SHA-1 und SHA-512 werden auf Wunsch berechnet (liest die ganze ISO)")
        grid.attach(self.bar, 0, r, 2, 1)
        self.get_content_area().add(scrolled(grid))
        self.show_all()

    def _calc(self, _btn) -> None:
        self.btn_sums.set_sensitive(False)
        path, cancel = self.iso.path, self.cancel
        last = [0.0]

        def progress(done, total):
            if time.monotonic() - last[0] >= 0.3:
                last[0] = time.monotonic()
                GLib.idle_add(self._progress, done, total)

        def work():
            try:
                result = oslib.checksums(path, progress, cancel)
            except Exception as e:
                result = e
            GLib.idle_add(self._done, result)

        threading.Thread(target=work, daemon=True).start()

    def _progress(self, done: int, total: int) -> bool:
        self.bar.set_fraction(done / total if total else 1)
        self.bar.set_text(f"Lese ISO {done * 100 // max(total, 1)} %")
        return False

    def _done(self, result) -> bool:
        self.btn_sums.set_sensitive(True)
        if isinstance(result, Exception):
            self.bar.set_text(f"Fehler: {result}")
            return False
        for algo, value in result.items():
            self.sums[algo].set_text(value)
        self.bar.set_fraction(1.0)
        self.bar.set_text("Prüfsummen berechnet")
        self._compare()
        return False

    def _compare(self) -> None:
        want = self.compare.get_text().strip().lower()
        ctx = self.result.get_style_context()
        for c in ("status-ok", "status-fail"):
            ctx.remove_class(c)
        if not want:
            self.result.set_text("")
            return
        known = {a: l.get_text().lower() for a, l in self.sums.items() if l.get_text() not in ("", "–")}
        match = [a for a, v in known.items() if v == want]
        if match:
            self.result.set_text(f"✓ stimmt überein ({match[0].upper()})")
            ctx.add_class("status-ok")
        elif any(len(v) == len(want) for v in known.values()):
            self.result.set_text("✗ stimmt NICHT überein – ISO nicht verwenden")
            ctx.add_class("status-fail")
        else:
            self.result.set_text("Noch nicht berechnet – „Alle Prüfsummen berechnen“")


class BootStickDialog(Gtk.Dialog):
    """Boot-Stick aus ISO – die Möglichkeiten von Rufus, mit Vorgaben für die Schweiz."""

    def __init__(self, parent: Gtk.Window, iso: oslib.IsoInfo):
        super().__init__(title="Boot-Stick erstellen", transient_for=parent, modal=True)
        self.set_default_size(720, 680)
        self.iso = iso
        self.meta = iso.meta
        self.busy = False
        self.modes = oslib.stick_modes(self.meta)
        self.disk_sizes: dict[str, int] = {}
        self.btn_close = self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.btn_start = self.add_button("Stick erstellen", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("destructive-action")
        self.connect("response", self._on_response)
        self.connect("delete-event", lambda *_a: self.busy)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        r = 0
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"<b>{GLib.markup_escape_text(iso.title)}</b>  ({nas.format_size(iso.size)})\n"
                        f"<small>{GLib.markup_escape_text(iso.name)} · {GLib.markup_escape_text(oslib.describe(self.meta))}"
                        "</small>")
        grid.attach(head, 0, r, 3, 1)
        r += 1
        grid.attach(Gtk.Label(label="USB-Stick", xalign=0), 0, r, 1, 1)
        self.disk_combo = Gtk.ComboBoxText(hexpand=True)
        self.disk_combo.connect("changed", lambda _c: self._update())
        grid.attach(self.disk_combo, 1, r, 1, 1)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("USB-Sticks neu suchen")
        refresh.connect("clicked", lambda _b: self.refresh_disks())
        grid.attach(refresh, 2, r, 1, 1)
        self.btn_refresh = refresh
        r += 1
        grid.attach(Gtk.Label(label="Schreibart", xalign=0), 0, r, 1, 1)
        self.mode_combo = Gtk.ComboBoxText()
        for m in self.modes:
            self.mode_combo.append(m, MODE_LABELS[m])
        self.mode_combo.connect("changed", lambda _c: self._update())
        grid.attach(self.mode_combo, 1, r, 2, 1)
        r += 1
        grid.attach(Gtk.Label(label="Partitionsschema", xalign=0), 0, r, 1, 1)
        self.scheme_combo = Gtk.ComboBoxText()
        self.scheme_combo.append("mbr", "MBR – startet per UEFI und BIOS (empfohlen)")
        self.scheme_combo.append("gpt", "GPT – nur UEFI")
        self.scheme_combo.set_active_id("mbr")
        grid.attach(self.scheme_combo, 1, r, 2, 1)
        r += 1
        grid.attach(Gtk.Label(label="Datenträgername", xalign=0), 0, r, 1, 1)
        self.label = Gtk.Entry(text=isostick.fat_label(self.meta), max_length=11)
        grid.attach(self.label, 1, r, 2, 1)
        r += 1
        grid.attach(Gtk.Label(label="Stick prüfen", xalign=0), 0, r, 1, 1)
        self.check_combo = Gtk.ComboBoxText()
        for k, v in CHECK_LABELS.items():
            self.check_combo.append(k, v)
        self.check_combo.set_active_id("quick")
        grid.attach(self.check_combo, 1, r, 2, 1)
        r += 1
        self.verify = Gtk.CheckButton(label="Nach dem Schreiben zurücklesen und vergleichen", active=True)
        grid.attach(self.verify, 1, r, 2, 1)
        r += 1

        # Windows-Anpassung (autounattend.xml)
        self.win = Gtk.Expander(label="Windows-Anpassung", expanded=True)
        wbox = Gtk.Grid(column_spacing=8, row_spacing=4, margin_start=12, margin_top=4)
        self.w_bypass = Gtk.CheckButton(label="Anforderungen umgehen: TPM 2.0, Secure Boot, 4 GB RAM, CPU", active=True)
        self.w_account = Gtk.CheckButton(label="Lokales Konto statt Microsoft-Konto", active=True)
        self.w_user = Gtk.Entry(text="Benutzer", width_chars=16)
        self.w_pass = Gtk.Entry(visibility=False, placeholder_text="leer = beim ersten Anmelden setzen", width_chars=26)
        self.w_privacy = Gtk.CheckButton(label="Datenschutz-Fragen überspringen (alles aus)", active=True)
        self.w_bitlocker = Gtk.CheckButton(label="Keine automatische BitLocker-Verschlüsselung", active=True)
        self.w_swiss = Gtk.CheckButton(label="Region Schweiz: Formate de-CH, Tastatur Schweiz (Deutsch), Zeitzone Zürich",
                                       active=True)
        self.w_name = Gtk.Entry(placeholder_text="leer = Windows wählt (max. 15 Zeichen)", width_chars=26)
        wr = 0
        for w in (self.w_bypass, self.w_account):
            wbox.attach(w, 0, wr, 3, 1)
            wr += 1
        wbox.attach(Gtk.Label(label="Benutzername", xalign=0, margin_start=24), 0, wr, 1, 1)
        wbox.attach(self.w_user, 1, wr, 1, 1)
        wr += 1
        wbox.attach(Gtk.Label(label="Passwort", xalign=0, margin_start=24), 0, wr, 1, 1)
        wbox.attach(self.w_pass, 1, wr, 1, 1)
        wr += 1
        for w in (self.w_privacy, self.w_bitlocker, self.w_swiss):
            wbox.attach(w, 0, wr, 3, 1)
            wr += 1
        wbox.attach(Gtk.Label(label="Computername", xalign=0), 0, wr, 1, 1)
        wbox.attach(self.w_name, 1, wr, 1, 1)
        self.w_account.connect("toggled", lambda _c: self._update())
        self.win.add(wbox)
        grid.attach(self.win, 0, r, 3, 1)
        r += 1

        warn = Gtk.Label(xalign=0, wrap=True)
        warn.set_markup("<b>Achtung:</b> Alle Daten auf dem gewählten Stick werden gelöscht.")
        warn.get_style_context().add_class("status-fail")
        grid.attach(warn, 0, r, 3, 1)
        r += 1
        self.bar = Gtk.ProgressBar(show_text=True)
        self.bar.set_text("Bereit")
        grid.attach(self.bar, 0, r, 3, 1)
        r += 1
        self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sw = scrolled(self.log)
        sw.set_min_content_height(120)
        grid.attach(sw, 0, r, 3, 1)
        self.get_content_area().add(scrolled(grid))
        self.show_all()
        if self.modes:
            self.mode_combo.set_active(0)
        else:
            self._log("Dieses Medium lässt sich nicht bootfähig schreiben (kein Hybrid-Bootsektor, keine UEFI-Dateien).")
        self.refresh_disks()

    # ---------- Zustand ----------

    def _log(self, text: str) -> bool:
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), text + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        return False

    def need(self) -> int:
        return self.iso.size + (64 * 1024 * 1024 if self.mode_combo.get_active_id() != "dd" else 0)

    def refresh_disks(self) -> None:
        self.disk_combo.remove_all()
        disks = stick.list_usb_disks()
        self.disk_sizes = {d.path: d.size for d in disks}
        for d in disks:
            self.disk_combo.append(d.path, d.label + ("  – zu klein" if d.size < self.need() else ""))
        if disks:
            self.disk_combo.set_active(0)
        else:
            self._log("Kein USB-Stick gefunden – Stick einstecken und neu suchen.")
        self._update()

    def _update(self) -> None:
        mode = self.mode_combo.get_active_id()
        windows = mode == "windows"
        self.win.set_visible(windows)
        self.scheme_combo.set_sensitive(mode != "dd" and not self.busy)
        self.label.set_sensitive(mode != "dd" and not self.busy)
        self.verify.set_visible(mode == "dd")
        self.verify.set_sensitive(not self.busy)
        for w in (self.w_user, self.w_pass):
            w.set_sensitive(self.w_account.get_active())
        disk = self.disk_combo.get_active_id()
        ok = (not self.busy and mode is not None and disk is not None
              and self.disk_sizes.get(disk, 0) >= self.need())
        self.btn_start.set_sensitive(ok)
        for w in (self.btn_close, self.disk_combo, self.mode_combo, self.check_combo, self.btn_refresh):
            w.set_sensitive(not self.busy)

    def options(self) -> winunattend.WinOptions:
        langs = (self.meta.get("windows") or {}).get("languages") or ["de-DE"]
        return winunattend.WinOptions(
            bypass_requirements=self.w_bypass.get_active(),
            local_account=self.w_user.get_text().strip() if self.w_account.get_active() else "",
            password=self.w_pass.get_text() if self.w_account.get_active() else "",
            skip_privacy=self.w_privacy.get_active(), no_bitlocker=self.w_bitlocker.get_active(),
            swiss_region=self.w_swiss.get_active(), ui_language=langs[0],
            computer_name=self.w_name.get_text().strip(),
            arch=(self.meta.get("windows") or {}).get("arch") or "amd64")

    # ---------- Schreiben ----------

    def _on_response(self, _dlg, response: int) -> None:
        if response == Gtk.ResponseType.APPLY:
            self.start()
        elif not self.busy:
            self.destroy()

    def start(self) -> None:
        device, mode = self.disk_combo.get_active_id(), self.mode_combo.get_active_id()
        if not device or not mode:
            return
        if not confirm(self, "Stick wirklich löschen?",
                       f"{self.disk_combo.get_active_text()}\n\nAlle Daten auf diesem Stick gehen verloren.",
                       ok_label="Stick löschen"):
            return
        args = ["--device", device, "--iso", str(self.iso.path), "--mode", mode,
                "--scheme", self.scheme_combo.get_active_id(), "--check", self.check_combo.get_active_id()]
        if mode != "dd" and self.label.get_text().strip():
            args += ["--label", self.label.get_text().strip()]
        if not self.verify.get_active():
            args.append("--no-verify")
        stdin = ""
        if mode == "windows":
            opts = self.options()
            stdin = winunattend.build(opts)
            args.append("--unattend-stdin")
        try:
            cmd = iso_stick_command(args)
        except FileNotFoundError as e:
            self._log(str(e))
            return
        self.busy = True
        self._update()
        self._log(f"Erstelle Boot-Stick auf {device} ({MODE_LABELS[mode]}) …")
        if mode == "windows":
            for line in winunattend.summary(opts):
                self._log(f"  · {line}")
        run_helper(cmd, stdin, self._progress, self._log, self._done)

    def _progress(self, frac: float, msg: str) -> bool:
        self.bar.set_fraction(max(0.0, min(1.0, frac)))
        self.bar.set_text(f"{frac * 100:.0f} %  {msg}")
        return False

    def _done(self, ok: bool, error: str) -> bool:
        self.busy = False
        if ok:
            self.bar.set_fraction(1.0)
            self.bar.set_text("Stick bereit – kann abgezogen werden")
        else:
            self.bar.set_text("Fehlgeschlagen")
            if error:
                self._log(f"Fehler: {error}")
        self.refresh_disks()
        return False
