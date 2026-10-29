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
        _row(grid, r, "Direkt installierbar", "ja – Rechtsklick „Auf Gerät installieren …“" if oslib.installable(meta)
             else f"nein – {oslib.install_reason(meta)}. Als Boot-Stick verwenden.")
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


def _gb(n: int) -> str:
    return f"{n / 1000**3:.1f} GB"


EDITION_NAMES = {"Core": "Home", "Professional": "Pro", "Education": "Education", "Enterprise": "Enterprise",
                 "CoreSingleLanguage": "Home Single Language", "ProfessionalWorkstation": "Pro for Workstations"}


class InstallDialog(Gtk.Dialog):
    """Betriebssystem direkt auf ein Gerät installieren (über den Agent, ohne Stick): Windows, Ubuntu, Debian."""

    def __init__(self, parent: Gtk.Window, agent, isos: list[oslib.IsoInfo], device, start_job,
                 preselect: str | None = None):
        """start_job(iso, disk_info, edition_index|None, optionen) – Optionen: WinOptions oder LinuxOptions."""
        from okula_recovery import linuxsetup
        self.linuxsetup = linuxsetup
        super().__init__(title="OS installieren", transient_for=parent, modal=True)
        self.set_default_size(780, 760)
        self.agent, self.start_job, self.device = agent, start_job, device
        self.isos = {str(i.path): i for i in isos}
        self.disks: dict[str, dict] = {}
        self.key, self.key_source = device.windows_key
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn_start = self.add_button("Installieren", Gtk.ResponseType.APPLY)
        self.btn_start.get_style_context().add_class("destructive-action")
        self.btn_start.set_sensitive(False)
        self.connect("response", self._on_response)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        r = 0
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"Zielgerät: <b>{GLib.markup_escape_text(device.name)}</b>  ({agent.ip})  "
                        f"{GLib.markup_escape_text(agent.hardware)}")
        grid.attach(head, 0, r, 2, 1)
        r += 1
        grid.attach(Gtk.Label(label="Betriebssystem", xalign=0), 0, r, 1, 1)
        self.iso_combo = Gtk.ComboBoxText(hexpand=True)
        order = sorted(self.isos.items(), key=lambda kv: (not oslib.installable(kv[1].meta), kv[1].family != "windows",
                                                          kv[1].display.lower()))
        for path, iso in order:
            note = "" if oslib.installable(iso.meta) else "  – nur Boot-Stick"
            self.iso_combo.append(path, f"{iso.display}  ({nas.format_size(iso.size)}){note}")
        self.iso_combo.connect("changed", lambda _c: self._on_iso())
        grid.attach(self.iso_combo, 1, r, 1, 1)
        r += 1
        self.edition_label = Gtk.Label(label="Edition", xalign=0)
        grid.attach(self.edition_label, 0, r, 1, 1)
        self.edition = Gtk.ComboBoxText()
        self.edition.connect("changed", lambda _c: self._update())
        grid.attach(self.edition, 1, r, 1, 1)
        r += 1
        grid.attach(Gtk.Label(label="Zieldisk", xalign=0), 0, r, 1, 1)
        self.disk_combo = Gtk.ComboBoxText()
        self.disk_combo.connect("changed", lambda _c: self._update())
        grid.attach(self.disk_combo, 1, r, 1, 1)
        r += 1
        warn = Gtk.Label(xalign=0)
        warn.set_markup("<b>Wird vollständig gelöscht:</b>")
        warn.get_style_context().add_class("status-fail")
        grid.attach(warn, 0, r, 2, 1)
        r += 1
        self.part_store = Gtk.ListStore(str, str, str, str)
        view = Gtk.TreeView(model=self.part_store)
        for i, t in enumerate(("Partition", "Dateisystem", "Grösse", "Label")):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_expand(i == 3)
            view.append_column(col)
        view.get_selection().set_mode(Gtk.SelectionMode.NONE)
        sw = scrolled(view)
        sw.set_min_content_height(80)
        grid.attach(sw, 0, r, 2, 1)
        r += 1

        # --- Windows ---
        self.win = Gtk.Expander(label="Windows-Anpassung", expanded=True)
        wbox = Gtk.Grid(column_spacing=8, row_spacing=4, margin_start=12, margin_top=4)
        self.w_key = Gtk.CheckButton(active=bool(self.key))
        self.w_key.set_label(f"Produktschlüssel verwenden: {self._masked()}  ({self.key_source})" if self.key
                             else "Kein Produktschlüssel bekannt (im Gerätefenster hinterlegen)")
        self.w_key.set_sensitive(bool(self.key))
        self.w_key.connect("toggled", lambda _c: self._update())
        self.w_account = Gtk.CheckButton(label="Lokales Konto statt Microsoft-Konto", active=True)
        self.w_user = Gtk.Entry(text="Benutzer", width_chars=16)
        self.w_pass = Gtk.Entry(visibility=False, placeholder_text="leer = beim ersten Anmelden setzen", width_chars=26)
        self.w_privacy = Gtk.CheckButton(label="Datenschutz-Fragen überspringen (alles aus)", active=True)
        self.w_bitlocker = Gtk.CheckButton(label="Keine automatische BitLocker-Verschlüsselung", active=True)
        self.w_account.connect("toggled", lambda _c: self._update())
        rows = [(self.w_key, None), (self.w_account, None), ("Benutzername", self.w_user), ("Passwort", self.w_pass),
                (self.w_privacy, None), (self.w_bitlocker, None)]
        for i, (a, b) in enumerate(rows):
            if b is None:
                wbox.attach(a, 0, i, 3, 1)
            else:
                wbox.attach(Gtk.Label(label=a, xalign=0, margin_start=24), 0, i, 1, 1)
                wbox.attach(b, 1, i, 1, 1)
        self.win.add(wbox)
        grid.attach(self.win, 0, r, 2, 1)
        r += 1

        # --- Linux ---
        self.lin = Gtk.Expander(label="Linux-Einstellungen", expanded=True)
        lbox = Gtk.Grid(column_spacing=8, row_spacing=4, margin_start=12, margin_top=4)
        self.l_user = Gtk.Entry(text="benutzer", width_chars=16)
        self.l_pass = Gtk.Entry(visibility=False, width_chars=26, placeholder_text="mind. 4 Zeichen")
        self.l_pass2 = Gtk.Entry(visibility=False, width_chars=26, placeholder_text="wiederholen")
        self.l_desktop = Gtk.CheckButton(label="Desktop (GNOME) installieren", active=True)
        # Debian: Softwareauswahl wie im Debian-Installer
        self.l_env = Gtk.ComboBoxText()
        self.l_env.append("", "Kein Desktop (Server)")
        for key, label in self.linuxsetup.DESKTOPS.items():
            self.l_env.append(key, label)
        self.l_env.set_active_id("gnome")
        self.l_standard = Gtk.CheckButton(label="Standard-Systemwerkzeuge", active=True)
        self.l_ssh = Gtk.CheckButton(label="SSH-Server (Fernzugriff per SSH)")
        self.l_web = Gtk.CheckButton(label="Webserver (Apache)")
        self.l_root = Gtk.Entry(visibility=False, width_chars=26,
                                placeholder_text="leer = kein Root-Konto, Benutzer nutzt sudo")
        self.l_packages = Gtk.Entry(width_chars=40, placeholder_text="z. B. htop curl vim – durch Leerzeichen getrennt")
        self.l_packages.set_tooltip_text("Werden am Schluss aus dem Internet installiert. Unbekannte Namen werden "
                                         "übersprungen, die Installation läuft trotzdem durch.")
        for w in (self.l_user, self.l_pass, self.l_pass2, self.l_root, self.l_packages):
            w.connect("changed", lambda _e: self._update())
        rows = (("Benutzername", self.l_user), ("Passwort", self.l_pass), ("Passwort bestätigen", self.l_pass2),
                ("Desktop", self.l_env), ("Root-Passwort", self.l_root), ("Zusätzliche Pakete", self.l_packages))
        self.l_labels = {}
        for i, (label, w) in enumerate(rows):
            lbl = Gtk.Label(label=label, xalign=0)
            self.l_labels[label] = lbl
            lbox.attach(lbl, 0, i, 1, 1)
            lbox.attach(w, 1, i, 1, 1)
        soft = Gtk.Box(spacing=16)
        for cb in (self.l_standard, self.l_ssh, self.l_web):
            soft.pack_start(cb, False, False, 0)
        lbox.attach(soft, 0, len(rows), 3, 1)
        lbox.attach(self.l_desktop, 0, len(rows) + 1, 3, 1)
        self.lin.add(lbox)
        grid.attach(self.lin, 0, r, 2, 1)
        r += 1

        # --- gemeinsam ---
        self.swiss = Gtk.CheckButton(label="Region Schweiz: Formate de-CH, Tastatur Schweiz (Deutsch), Zeitzone Zürich",
                                     active=True)
        grid.attach(self.swiss, 0, r, 2, 1)
        r += 1
        grid.attach(Gtk.Label(label="Computername", xalign=0), 0, r, 1, 1)
        self.name = Gtk.Entry(text=device.name, width_chars=26)
        grid.attach(self.name, 1, r, 1, 1)
        r += 1
        self.info = Gtk.Label(xalign=0, wrap=True)
        grid.attach(self.info, 0, r, 2, 1)
        r += 1
        self.check = Gtk.Label(xalign=0, wrap=True)
        grid.attach(self.check, 0, r, 2, 1)
        r += 1
        self.confirm_label = Gtk.Label(xalign=0)
        grid.attach(self.confirm_label, 0, r, 1, 1)
        self.confirm = Gtk.Entry(placeholder_text="Disk-Namen eintippen")
        self.confirm.connect("changed", lambda _e: self._update())
        grid.attach(self.confirm, 1, r, 1, 1)
        r += 1
        self.status = Gtk.Label(label="Lese Disks vom Agent …", xalign=0, wrap=True)
        self.status.get_style_context().add_class("status-idle")
        grid.attach(self.status, 0, r, 2, 1)
        self.get_content_area().add(scrolled(grid))
        self.show_all()
        if preselect in self.isos:
            self.iso_combo.set_active_id(preselect)
        elif self.isos:
            self.iso_combo.set_active(0)
        self._load_disks()

    def _masked(self) -> str:
        return f"XXXXX-XXXXX-XXXXX-XXXXX-{self.key[-5:]}"

    def _iso(self) -> oslib.IsoInfo | None:
        return self.isos.get(self.iso_combo.get_active_id() or "")

    def _load_disks(self) -> None:
        from okula_recovery import agentclient  # Kreisimport vermeiden
        agent = self.agent
        key = agentclient.load_or_create_key()

        def work():
            try:
                result = agentclient.get_info(agent.ip, key, agent.control_port)
            except Exception as e:
                result = e
            GLib.idle_add(self._on_disks, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_disks(self, result) -> bool:
        if isinstance(result, Exception):
            self.status.set_text(f"Agent nicht erreichbar: {result}")
            return False
        self.disks = {d["path"]: d for d in result.get("disks", [])}
        for path, d in self.disks.items():
            self.disk_combo.append(path, f"{d['name']} – {d['model'] or 'Disk'} ({_gb(d['size'])})")
        if self.disks:
            self.disk_combo.set_active(0)
            self.status.set_text("")
        else:
            self.status.set_text("Der Agent meldet keine interne Disk.")
        return False

    def _on_iso(self) -> None:
        iso = self._iso()
        self.edition.remove_all()
        why = oslib.install_reason(iso.meta) if iso else ""
        windows = iso is not None and iso.family == "windows" and not why
        if windows:
            eds = iso.meta.get("windows", {}).get("editions", [])
            for e in eds:
                self.edition.append(str(e["index"]), e["name"])
            # Edition wie bisher auf dem Gerät (passt zur Lizenz), sonst Pro
            wanted = self.device.windows_edition or "Professional"
            pick = next((e for e in eds if e.get("edition_id") == wanted), None) or \
                next((e for e in eds if e.get("edition_id") == "Professional"), eds[0] if eds else None)
            if pick:
                self.edition.set_active_id(str(pick["index"]))
        self.edition.set_visible(windows)
        self.edition_label.set_visible(windows)
        self.win.set_visible(windows)
        self.lin.set_visible(not windows and not why)
        self.swiss.set_visible(not why)
        self.name.set_sensitive(not why)
        kind = self.linuxsetup.kind(iso.meta) if iso and not windows else ""
        debian = kind == "debian"
        self.l_desktop.set_visible(kind == "fedora")
        for w in (self.l_env, self.l_labels["Desktop"], self.l_root, self.l_labels["Root-Passwort"],
                  self.l_standard, self.l_web):
            w.set_visible(debian)
        self.l_desktop.set_label("Desktop (GNOME) installieren" if kind == "debian" else
                                 "Desktop (Workstation/GNOME) installieren – Pakete aus dem Internet")
        texts = {
            "windows": "Ablauf: EFI-, Windows- und Setup-Partition anlegen, Setup-Dateien vom NAS übertragen, Neustart. "
                       "Windows installiert sich selbständig (ohne Setup-Assistent, ohne TPM-/Secure-Boot-Prüfung) und "
                       "entfernt am Ende die Setup-Partition.",
            "ubuntu": "Ablauf: EFI-Partition und Setup-Partition mit der ISO anlegen, Neustart. Der Ubuntu-Installer "
                      "läuft automatisch (Autoinstall) in den freien Platz; beim ersten Start wird die Setup-Partition "
                      "entfernt und das System vergrössert.",
            "debian": "Ablauf: EFI-Partition mit dem Debian-Netzwerk-Installer anlegen, Neustart. Die Installation "
                      "läuft automatisch (Preseed) – <b>das Gerät braucht Internet</b> (deb.debian.org).",
            "fedora": "Ablauf: EFI-Partition mit dem Installer der ISO und Setup-Partition mit der ISO anlegen, "
                      "Neustart. Anaconda installiert automatisch (Kickstart) in den freien Platz; beim ersten Start "
                      "wird die Setup-Partition entfernt. Netzwerk-ISO oder Desktop: <b>Gerät braucht Internet</b>.",
        }
        which = "windows" if windows else kind
        if why:
            self.info.set_markup(f"<b>Nicht direkt installierbar:</b> {GLib.markup_escape_text(why)}.\n"
                                 "<small>Dieses Medium als Boot-Stick verwenden (rechts: Rechtsklick auf die ISO → "
                                 "„Boot-Stick erstellen …“). Direkt installierbar sind Windows 10/11 (x64), Ubuntu "
                                 "ab 24.04, Debian sowie Fedora/Rocky/Alma mit Anaconda-Installer.</small>")
        else:
            self.info.set_markup(f"<small>{texts.get(which, '')} <b>Gerät muss im UEFI-Modus laufen. Agent-Stick "
                                 "beim Neustart abziehen.</b></small>")
        self._update()

    def _update(self) -> None:
        iso = self._iso()
        if iso is not None and not oslib.installable(iso.meta):
            self.part_store.clear()
            self.check.set_text("")
            self.btn_start.set_sensitive(False)
            return
        windows = iso is not None and iso.family == "windows"
        for w in (self.w_user, self.w_pass):
            w.set_sensitive(self.w_account.get_active())
        disk = self.disks.get(self.disk_combo.get_active_id() or "")
        self.part_store.clear()
        ok = bool(iso and disk and (self.edition.get_active_id() or not windows))
        problems = []
        if disk:
            for p in disk["partitions"] or [{"name": disk["name"], "fstype": "", "size": disk["size"], "label": ""}]:
                self.part_store.append([p["name"], p.get("fstype") or "leer/unbekannt", nas.format_size(p["size"]),
                                        p.get("label", "")])
            self.confirm_label.set_markup(f"Bestätigung: <b>{GLib.markup_escape_text(disk['name'])}</b> eintippen")
            need = 40 * 1000**3 if windows else 30 * 1000**3 + (iso.size if iso else 0)
            if disk["size"] < need:
                problems.append(f"Disk zu klein: {_gb(disk['size'])} (mind. {_gb(need)})")
                ok = False
            if any(p.get("mounted") for p in disk["partitions"]):
                problems.append("Eine Partition der Zieldisk ist eingehängt.")
                ok = False
        if windows and self.w_key.get_active() and self.device.windows_edition:
            chosen = next((e for e in iso.meta["windows"]["editions"]
                           if str(e["index"]) == self.edition.get_active_id()), None)
            if chosen and chosen.get("edition_id") != self.device.windows_edition:
                old = EDITION_NAMES.get(self.device.windows_edition, self.device.windows_edition)
                problems.append(f"Hinweis: Auf dem Gerät war Windows {old} – der Schlüssel aktiviert vermutlich nur "
                                f"diese Edition, nicht {chosen['name']}.")
        if iso and not windows:
            try:
                self.linuxsetup.username(self.l_user.get_text())
            except self.linuxsetup.LinuxSetupError as e:
                problems.append(str(e))
                ok = False
            if len(self.l_pass.get_text()) < 4:
                problems.append("Passwort: mindestens 4 Zeichen")
                ok = False
            elif self.l_pass.get_text() != self.l_pass2.get_text():
                problems.append("Passwörter stimmen nicht überein")
                ok = False
            if self.l_root.get_visible() and 0 < len(self.l_root.get_text()) < 4:
                problems.append("Root-Passwort: mindestens 4 Zeichen (oder leer lassen)")
                ok = False
            try:
                self.linuxsetup.parse_packages(self.l_packages.get_text())
            except self.linuxsetup.LinuxSetupError as e:
                problems.append(str(e))
                ok = False
        self.check.set_markup("\n".join(GLib.markup_escape_text(p) for p in problems)
                              if problems else (f"Disk passt: {_gb(disk['size'])}" if disk else ""))
        typed = disk is not None and self.confirm.get_text().strip() == disk["name"]
        self.btn_start.set_sensitive(ok and typed)

    def options(self):
        iso = self._iso()
        if iso.family == "windows":
            w = iso.meta.get("windows", {})
            return winunattend.WinOptions(
                bypass_requirements=False,  # Direktinstallation läuft ohne Setup-Assistent
                local_account=self.w_user.get_text().strip() if self.w_account.get_active() else "",
                password=self.w_pass.get_text() if self.w_account.get_active() else "",
                skip_privacy=self.w_privacy.get_active(), no_bitlocker=self.w_bitlocker.get_active(),
                swiss_region=self.swiss.get_active(), ui_language=(w.get("languages") or ["de-DE"])[0],
                computer_name=self.name.get_text().strip(), arch=w.get("arch") or "amd64", skip_network=True,
                product_key=self.key if self.w_key.get_active() else "")
        return self.linuxsetup.LinuxOptions(
            username=self.l_user.get_text().strip(), password=self.l_pass.get_text(),
            hostname=self.name.get_text().strip() or self.device.name, swiss_region=self.swiss.get_active(),
            desktop=self.l_desktop.get_active() if self.l_desktop.get_visible() else bool(self.l_env.get_active_id()),
            desktop_env=self.l_env.get_active_id() or "", standard=self.l_standard.get_active(),
            ssh=self.l_ssh.get_active(), web=self.l_web.get_active(),
            root_password=self.l_root.get_text() if self.l_root.get_visible() else "",
            packages=self.linuxsetup.parse_packages(self.l_packages.get_text()))

    def _on_response(self, _dlg, response: int) -> None:
        if response != Gtk.ResponseType.APPLY:
            self.destroy()
            return
        iso = self._iso()
        disk = self.disks[self.disk_combo.get_active_id()]
        index = int(self.edition.get_active_id()) if iso.family == "windows" else None
        try:
            self.start_job(iso, disk, index, self.options())
        except Exception as e:
            self.status.set_text(f"Nicht gestartet: {e}")
            return
        self.destroy()
