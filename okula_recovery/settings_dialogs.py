"""Menü → „Einstellungen exportieren / importieren …“ und Dateiauswahl für den NAS-Export.

Die eigentliche Arbeit macht transfer.py; hier nur Auswahl, Rückfragen und Ergebnis.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from okula_recovery import agentclient, transfer  # noqa: E402
from okula_recovery.uikit import confirm_error  # noqa: E402

EXPORT_PATTERNS = (("Okula-Export (*.okula.zip, *.zip)", ("*.okula.zip", "*.zip")),)
NAS_PATTERNS = (("NAS-Einstellungen (*.json) oder Gesamt-Export (*.zip)", ("*.json", "*.zip")),)


def choose_file(parent: Gtk.Window, title: str, save: bool, name: str = "",
                patterns: tuple = ()) -> str | None:
    action = Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN
    dlg = Gtk.FileChooserDialog(title=title, transient_for=parent, action=action)
    dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Speichern" if save else "Öffnen", Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)
    dlg.set_current_folder(str(Path.home()))
    if save:
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_current_name(name)
    for label, globs in patterns:
        flt = Gtk.FileFilter()
        flt.set_name(label)
        for g in globs:
            flt.add_pattern(g)
        dlg.add_filter(flt)
    path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
    dlg.destroy()
    return path


def _info(text: str) -> Gtk.Label:
    lbl = Gtk.Label(xalign=0, wrap=True)
    lbl.set_markup(text)
    return lbl


class ExportDialog(Gtk.Dialog):
    """Alles für einen neuen Rechner in eine Datei: Einstellungen, Agent-Schlüssel, Geräte."""

    def __init__(self, parent: Gtk.Window):
        super().__init__(title="Einstellungen exportieren", transient_for=parent, modal=True)
        self.set_default_size(620, -1)
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        btn = self.add_button("Exportieren …", Gtk.ResponseType.OK)
        btn.get_style_context().add_class("suggested-action")
        counts = transfer.summary_counts()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        box.pack_start(_info("Speichert alles, was das Tool auf diesem Rechner weiss, in <b>eine Datei</b>. "
                             "Auf dem neuen Rechner: Tool installieren, dann <i>Menü → Einstellungen "
                             "importieren …</i>"), False, False, 0)
        self.cb_config = Gtk.CheckButton(label="NAS-Verbindung und Einstellungen", active=True)
        self.cb_devices = Gtk.CheckButton(
            label=f"Geräte: {counts['devices']} mit Ordnern, Verlauf, Notizen und Windows-Schlüsseln", active=True)
        self.cb_key = Gtk.CheckButton(label="Agent-Schlüssel – bestehende Agent- und Restore-Sticks funktionieren "
                                            "auch mit dem neuen Rechner (empfohlen)", active=True)
        for cb in (self.cb_config, self.cb_devices, self.cb_key):
            box.pack_start(cb, False, False, 0)
        note = _info("<small>Nicht in der Datei: Images, Backups und ISOs (bleiben auf dem NAS) und das "
                     "<b>NAS-Passwort</b> – aus Sicherheitsgründen. Nach dem Import einmal im NAS-Fenster "
                     "eingeben und „Einhängen“ klicken.</small>")
        note.get_style_context().add_class("status-idle")
        box.pack_start(note, False, False, 0)
        warn = _info("<b>Wie ein Passwort aufbewahren:</b> Die Datei enthält den Agent-Schlüssel und "
                     "Windows-Produktschlüssel.")
        warn.get_style_context().add_class("status-fail")
        box.pack_start(warn, False, False, 0)
        self.get_content_area().add(box)
        self.show_all()

    def run_export(self) -> None:
        while self.run() == Gtk.ResponseType.OK:
            if not (self.cb_config.get_active() or self.cb_devices.get_active() or self.cb_key.get_active()):
                confirm_error(self, "Bitte mindestens einen Teil auswählen.")
                continue
            path = choose_file(self, "Export speichern", True, transfer.default_name("all"), EXPORT_PATTERNS)
            if not path:
                continue
            try:
                manifest = transfer.export_all(path, include_key=self.cb_key.get_active(),
                                               include_devices=self.cb_devices.get_active(),
                                               include_config=self.cb_config.get_active())
            except OSError as e:
                confirm_error(self, f"Export fehlgeschlagen: {e}")
                continue
            parts = []
            if "config" in manifest["contents"]:
                parts.append("Einstellungen")
            if "devices" in manifest["contents"]:
                parts.append(f"{manifest.get('devices', 0)} Geräte")
            if "agent_key" in manifest["contents"]:
                parts.append("Agent-Schlüssel")
            _message(self, "Export gespeichert", f"{path}\n\nEnthält: {', '.join(parts)}.\n\n"
                     "Datei auf den neuen Rechner kopieren (z. B. per USB-Stick) und dort unter "
                     "Menü → Einstellungen importieren … öffnen.")
            break
        self.destroy()


class ImportDialog(Gtk.Dialog):
    """Zeigt, was in der Datei ist, und was übernommen werden soll."""

    def __init__(self, parent: Gtk.Window, export: transfer.ExportFile, path: str):
        super().__init__(title="Einstellungen importieren", transient_for=parent, modal=True)
        self.set_default_size(640, -1)
        self.export = export
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        btn = self.add_button("Importieren", Gtk.ResponseType.OK)
        btn.get_style_context().add_class("suggested-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        box.pack_start(_info(f"<b>{GLib.markup_escape_text(Path(path).name)}</b>\n"
                             + GLib.markup_escape_text("\n".join(export.describe()))), False, False, 0)
        self.cb_config = Gtk.CheckButton(label="NAS-Verbindung und Einstellungen übernehmen",
                                         active=bool(export.config), sensitive=bool(export.config))
        self.cb_devices = Gtk.CheckButton(label="Geräte übernehmen (gleiches Gerät: das zuletzt gesehene gewinnt)",
                                          active=bool(export.device_files or export.folders),
                                          sensitive=bool(export.device_files or export.folders))
        self.cb_key = Gtk.CheckButton(label="Agent-Schlüssel übernehmen", active=export.key is not None,
                                      sensitive=export.key is not None)
        for cb in (self.cb_config, self.cb_devices, self.cb_key):
            box.pack_start(cb, False, False, 0)
        current = None
        try:
            current = bytes.fromhex(agentclient.key_path().read_text().strip())
        except (OSError, ValueError):
            pass
        if export.key is not None and current is not None and current != export.key:
            warn = _info("<small><b>Agent-Schlüssel:</b> Dieser Rechner hat bereits einen eigenen Schlüssel (legt das "
                         "Tool beim ersten Start an). Mit dem Import funktionieren die Sticks vom alten Rechner. "
                         "Falls auf <i>diesem</i> Rechner schon Sticks erstellt wurden, diese danach neu erstellen."
                         "</small>")
            box.pack_start(warn, False, False, 0)
        note = _info("<small>Vorhandene Daten werden vorher gesichert (Ordner <i>import-sicherung</i> bei den "
                     "Einstellungen). Danach startet das Tool neu. Das NAS-Passwort danach einmal im NAS-Fenster "
                     "eingeben und „Einhängen“ klicken.</small>")
        note.get_style_context().add_class("status-idle")
        box.pack_start(note, False, False, 0)
        self.get_content_area().add(box)
        self.show_all()

    def run_import(self) -> transfer.ImportResult | None:
        result = None
        if self.run() == Gtk.ResponseType.OK:
            try:
                result = transfer.import_all(self.export, use_config=self.cb_config.get_active(),
                                             use_key=self.cb_key.get_active(), use_devices=self.cb_devices.get_active())
            except (OSError, ValueError, transfer.TransferError) as e:
                confirm_error(self, f"Import fehlgeschlagen: {e}")
        self.destroy()
        return result


def _message(parent: Gtk.Window, title: str, text: str) -> None:
    dlg = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK, text=title)
    dlg.format_secondary_text(text)
    dlg.run()
    dlg.destroy()


def import_settings(parent: Gtk.Window, busy: bool) -> bool:
    """Datei wählen, prüfen, übernehmen. True = übernommen, das Tool soll neu starten."""
    if busy:
        confirm_error(parent, "Es laufen noch Aufträge – Import erst danach.")
        return False
    path = choose_file(parent, "Export öffnen", False, patterns=EXPORT_PATTERNS)
    if not path:
        return False
    try:
        export = transfer.read_export(path)
    except transfer.TransferError as e:
        confirm_error(parent, str(e))
        return False
    result = ImportDialog(parent, export, path).run_import()
    if result is None:
        return False
    _message(parent, "Import abgeschlossen", "\n".join(result.lines() or ["Nichts geändert"])
             + "\n\nDas Tool startet jetzt neu, damit alles geladen wird.")
    return True
