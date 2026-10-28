"""Fenster „NAS-Verbindung“ (Menü → NAS-Verbindung …): Einrichtung, Test, Ein-/Aushängen."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from okula_recovery import config, nas  # noqa: E402
from okula_recovery.uikit import make_tree, run_async, scrolled  # noqa: E402


class NasDialog(Gtk.Dialog):
    """on_changed(cfg) wird nach Speichern/Einhängen/Aushängen/Test aufgerufen (Hauptfenster aktualisieren)."""

    def __init__(self, parent: Gtk.Window, cfg: config.Config, on_changed: Callable[[config.NasConfig], None]):
        super().__init__(title="NAS-Verbindung", transient_for=parent, modal=False, destroy_with_parent=True)
        self.set_default_size(640, 560)
        self.cfg = cfg
        self.on_changed = on_changed
        self.add_button("Schliessen", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda *_a: self.destroy())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        self.protocol = Gtk.ComboBoxText()
        self.protocol.append("smb", "SMB / CIFS")
        self.protocol.append("nfs", "NFS")
        self.protocol.set_active_id(cfg.nas.protocol)
        self.protocol.connect("changed", lambda _c: self._update_form())
        self.host = Gtk.Entry(text=cfg.nas.host, placeholder_text="z. B. nas.local oder 192.168.1.10", hexpand=True)

        # Freigabe: frei eingeben oder aus „Freigaben suchen“ wählen
        share_box = Gtk.Box(spacing=6)
        self.share_combo = Gtk.ComboBoxText.new_with_entry()
        self.share_combo.set_hexpand(True)
        self.share = self.share_combo.get_child()
        self.share.set_text(cfg.nas.share)
        share_box.pack_start(self.share_combo, True, True, 0)
        self.btn_shares = Gtk.Button(label="Freigaben suchen")
        self.btn_shares.set_tooltip_text("Freigaben des NAS mit Benutzer/Passwort auflisten (SMB)")
        self.btn_shares.connect("clicked", self.on_find_shares)
        share_box.pack_start(self.btn_shares, False, False, 0)

        self.user = Gtk.Entry(text=cfg.nas.username, placeholder_text="NAS-Benutzer")
        self.password = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD)
        self.mount_point = Gtk.Entry(text=cfg.nas.mount_point)
        self.rows = {}
        for row, (label, widget) in enumerate([("Protokoll", self.protocol), ("Host", self.host),
                                               ("Freigabe", share_box), ("Benutzer", self.user),
                                               ("Passwort", self.password), ("Einhängepunkt", self.mount_point)]):
            lbl = Gtk.Label(label=label, xalign=0)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            self.rows[label] = (lbl, widget)
        box.pack_start(grid, False, False, 0)

        buttons = Gtk.Box(spacing=6)
        self.btn_test = Gtk.Button(label="Verbindung testen")
        self.btn_test.connect("clicked", self.on_test)
        btn_mount = Gtk.Button(label="Einhängen")
        btn_mount.connect("clicked", self.on_mount)
        btn_umount = Gtk.Button(label="Aushängen")
        btn_umount.connect("clicked", self.on_umount)
        btn_save = Gtk.Button(label="Speichern")
        btn_save.connect("clicked", self.on_save)
        for b in (self.btn_test, btn_mount, btn_umount, btn_save):
            buttons.pack_start(b, False, False, 0)
        self.spinner = Gtk.Spinner()
        buttons.pack_start(self.spinner, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.status = Gtk.Label(label="Nicht geprüft", xalign=0, wrap=True, selectable=True)
        self.status.get_style_context().add_class("status-idle")
        box.pack_start(self.status, False, False, 0)

        # Ergebnis der Einzelprüfungen
        self.check_store = Gtk.ListStore(str, str, str)  # icon, Prüfung, Detail
        checks = make_tree([("", -1), ("Prüfung", 1), ("Detail", 2)], self.check_store, expand=2)
        checks.set_headers_visible(False)
        checks.get_selection().set_mode(Gtk.SelectionMode.NONE)
        box.pack_start(Gtk.Label(label="Prüfdetails", xalign=0), False, False, 0)
        box.pack_start(scrolled(checks), True, True, 0)

        self.get_content_area().add(box)
        self.show_all()
        self._update_form()  # nach show_all, sonst wären die SMB-Felder bei NFS sichtbar
        self.on_test(None)

    # ---------- Formular ----------

    def form(self) -> config.NasConfig:
        smb = self._is_smb()
        share = self.share.get_text().strip()
        return config.NasConfig(protocol=self.protocol.get_active_id() or "smb",
                                host=self.host.get_text().strip(),
                                share=share.strip("/") if smb else share,
                                mount_point=self.mount_point.get_text().strip() or "/mnt/okula-nas",
                                username=self.user.get_text().strip())

    def _is_smb(self) -> bool:
        return (self.protocol.get_active_id() or "smb") == "smb"

    def _update_form(self) -> None:
        """Benutzer/Passwort und Freigabensuche gibt es nur für SMB."""
        smb = self._is_smb()
        for key in ("Benutzer", "Passwort"):
            for w in self.rows[key]:
                w.set_visible(smb)
        self.btn_shares.set_visible(smb)
        self.share.set_placeholder_text("z. B. recovery" if smb else "z. B. /volume1/recovery")
        self.password.set_placeholder_text("gespeichert – nur zum Ändern eingeben"
                                           if smb and nas.has_credentials() else "")

    def _set_status(self, text: str, state: str) -> None:
        ctx = self.status.get_style_context()
        for c in ("status-ok", "status-fail", "status-idle"):
            ctx.remove_class(c)
        ctx.add_class(f"status-{state}")
        self.status.set_text(text)

    def _store(self) -> config.NasConfig:
        self.cfg.nas = self.form()
        config.save(self.cfg)
        return self.cfg.nas

    # ---------- Aktionen ----------

    def on_save(self, _btn) -> None:
        self.on_changed(self._store())
        self._set_status("Einstellungen gespeichert", "idle")

    def on_test(self, _btn) -> None:
        cfg = self.form()
        self.btn_test.set_sensitive(False)
        self.spinner.start()
        self._set_status("Prüfe Verbindung …", "idle")
        run_async(lambda: nas.test_connection(cfg), self._on_tested)

    def _on_tested(self, result) -> None:
        self.btn_test.set_sensitive(True)
        self.spinner.stop()
        self.check_store.clear()
        if isinstance(result, Exception):
            self._set_status(f"✗ Fehler: {result}", "fail")
            return
        for c in result:
            self.check_store.append(["emblem-ok-symbolic" if c.ok else "dialog-error-symbolic", c.name, c.detail])
        if all(c.ok for c in result):
            self._set_status("● NAS verbunden", "ok")
        else:
            failed = next(c for c in result if not c.ok)
            self._set_status(f"● Keine Verbindung – {failed.name}: {failed.detail}", "fail")

    def on_mount(self, _btn) -> None:
        cfg = self.form()
        if not cfg.host or not cfg.share:
            self._set_status("● Host und Freigabe eingeben", "fail")
            return
        password = self.password.get_text() if self._is_smb() else ""
        self._store()
        self.spinner.start()
        self._set_status("Hänge NAS ein …", "idle")
        run_async(lambda: nas.mount(cfg, password), self._on_mounted)

    def _on_mounted(self, result) -> None:
        self.spinner.stop()
        ok, msg = (False, str(result)) if isinstance(result, Exception) else result
        if ok:
            self.password.set_text("")
            self._update_form()
            self.on_changed(self.cfg.nas)
            self.on_test(None)
        else:
            self._set_status(f"● Einhängen fehlgeschlagen: {msg}", "fail")

    def on_umount(self, _btn) -> None:
        cfg = self.form()
        self.spinner.start()
        run_async(lambda: nas.umount(cfg), self._on_umounted)

    def _on_umounted(self, result) -> None:
        self.spinner.stop()
        self.on_changed(self.cfg.nas)
        self.on_test(None)

    def on_find_shares(self, _btn) -> None:
        cfg = self.form()
        password = self.password.get_text()
        if not cfg.host or not cfg.username or not password:
            self._set_status("● Für die Suche Host, Benutzer und Passwort eingeben", "fail")
            return
        self.btn_shares.set_sensitive(False)
        self.spinner.start()
        run_async(lambda: nas.list_smb_shares(cfg.host, cfg.username, password), self._on_shares)

    def _on_shares(self, result) -> None:
        self.btn_shares.set_sensitive(True)
        self.spinner.stop()
        if isinstance(result, Exception):
            self._set_status(f"● Freigaben nicht lesbar: {result}", "fail")
            return
        current = self.share.get_text()
        self.share_combo.remove_all()
        for name in result:
            self.share_combo.append_text(name)
        if current not in result:
            self.share_combo.set_active(0)
            self.share_combo.popup()
        self._set_status(f"{len(result)} Freigaben gefunden: {', '.join(result)}", "idle")
