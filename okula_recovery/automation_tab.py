"""Reiter „Automatisierung“ im Gerätefenster, Fenster „Ordner senden“ und „Einstellungen“."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from okula_recovery import automation, config, devices, distribute, linuxsetup, winunattend  # noqa: E402
from okula_recovery.uikit import ask_text, confirm, confirm_error, numbered_section, scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow

HINT = ("Die Automatisierung läuft einmal und schaltet sich nach erfolgreichem Durchlauf selbst aus. Nach 24 Stunden "
        "schaltet sie sich wieder ein (abschaltbar). Sie startet 30 Sekunden, nachdem das Gerät im LAN auftaucht "
        "(Agent-Stick oder Netzwerkstart) – am Gerät bricht Esc ab.")


def _hint(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0, wrap=True)
    lbl.get_style_context().add_class("status-idle")
    return lbl


def computer_name_text(name: str) -> str:
    """Wie der Gerätename auf dem Gerät ankommt (Windows: max. 15 Zeichen, nur A–Z, 0–9, -)."""
    win = winunattend.computer_name(name) or "(ungültig)"
    return f"Windows: {win}" + ("" if win == name else " (gekürzt/angepasst)")


class AutomationTab(Gtk.Box):
    def __init__(self, main: "MainWindow", dev: devices.Device):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=8)
        self.main, self.dev = main, dev
        self._updating = False

        top = Gtk.Box(spacing=10)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.connect("notify::active", lambda *_a: self._changed())
        top.pack_start(self.switch, False, False, 0)
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<b>Automatisierung</b>")
        top.pack_start(lbl, False, False, 0)
        self.state = Gtk.Label(xalign=0, wrap=True)
        top.pack_start(self.state, True, True, 0)
        self.btn_cancel = Gtk.Button(label="Abbrechen")
        self.btn_cancel.get_style_context().add_class("destructive-action")
        self.btn_cancel.connect("clicked", lambda _b: self.main.automation.cancel(self.dev.id))
        top.pack_end(self.btn_cancel, False, False, 0)
        self.pack_start(top, False, False, 0)
        self.pack_start(_hint(HINT), False, False, 0)
        self.rearm = Gtk.CheckButton(label="Nach 24 h wieder einschalten")
        self.rearm.connect("toggled", lambda _c: self._changed())
        self.pack_start(self.rearm, False, False, 0)

        # Vorlagen
        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label="Vorlage", xalign=0), False, False, 0)
        self.template = Gtk.ComboBoxText()
        row.pack_start(self.template, True, True, 0)
        for label, handler in (("Anwenden", self._apply_template), ("Als Vorlage speichern …", self._save_template),
                               ("Löschen", self._delete_template)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, h=handler: h())
            row.pack_start(b, False, False, 0)
        self.pack_start(row, False, False, 0)

        grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)

        def section(number: str, title: str, note: str = "") -> Gtk.Box:
            return numbered_section(grid, number, title, note)

        s1 = section("1", "Backup", "Option")
        self.backup = Gtk.CheckButton(label="Vorher sichern, bevor das Image zurückgespielt wird")
        self.backup.connect("toggled", lambda _c: self._changed())
        s1.pack_start(self.backup, False, False, 0)
        self.backup_files = Gtk.RadioButton(label="Benutzerdaten aller Benutzer auf der Zieldisk (Desktop, Dokumente, "
                                                  "Bilder … wie „Backup erstellen“) – schnell, klein")
        self.backup_image = Gtk.RadioButton(label="Ganze Disk als Disk-Image aufs NAS (wie „Disk-Image erstellen“) – "
                                                  "alles, dauert länger", group=self.backup_files)
        self.backup_choice = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_start=24)
        for b in (self.backup_files, self.backup_image):
            b.connect("toggled", lambda b: b.get_active() and self._changed())
            self.backup_choice.pack_start(b, False, False, 0)
        s1.pack_start(self.backup_choice, False, False, 0)

        s2 = section("2", "Image zurückspielen")
        r = Gtk.Box(spacing=8)
        self.mode_master = Gtk.RadioButton(label="Master-Image")
        self.mode_own = Gtk.RadioButton(label="Eigenes Image", group=self.mode_master)
        for b in (self.mode_master, self.mode_own):
            b.connect("toggled", lambda b: b.get_active() and self._mode_changed())
            r.pack_start(b, False, False, 0)
        s2.pack_start(r, False, False, 0)
        self.image = Gtk.ComboBoxText()
        self.image.connect("changed", lambda _c: self._changed())
        s2.pack_start(self.image, False, False, 0)
        r = Gtk.Box(spacing=8)
        r.pack_start(Gtk.Label(label="Zieldisk", xalign=0), False, False, 0)
        self.disk = Gtk.ComboBoxText(hexpand=True)
        self.disk.connect("changed", lambda _c: self._changed())
        r.pack_start(self.disk, True, True, 0)
        s2.pack_start(r, False, False, 0)
        s2.pack_start(_hint("Die Zieldisk wird über ihre Seriennummer erkannt. Steckt eine andere Disk im Gerät, "
                            "bricht die Automatisierung ab – es wird nichts gelöscht. Das Image wird vor dem "
                            "Schreiben vollständig geprüft."), False, False, 0)

        s3 = section("3", "Anpassen", "läuft immer")
        self.custom_text = Gtk.Label(xalign=0, wrap=True, selectable=True)
        s3.pack_start(self.custom_text, False, False, 0)
        self.swiss = Gtk.CheckButton(label="Region Schweiz: Formate de-CH, Tastatur Schweiz, Zeitzone Zürich")
        self.swiss.connect("toggled", lambda _c: self._changed())
        s3.pack_start(self.swiss, False, False, 0)
        r = Gtk.Box(spacing=8)
        r.pack_start(Gtk.Label(label="Lokales Konto", xalign=0), False, False, 0)
        self.account = Gtk.Entry(placeholder_text="leer = Windows fragt beim ersten Start", width_chars=30)
        self.account.connect("changed", lambda _e: self._changed())
        r.pack_start(self.account, False, False, 0)
        r.pack_start(_hint("Passwort beim ersten Anmelden setzen (wird nirgends gespeichert)"), False, False, 0)
        s3.pack_start(r, False, False, 0)

        s4 = section("4", "Ordner senden", "Option – auf den Desktop für alle Benutzer, ersetzt vorhandene Ordner")
        r = Gtk.Box(spacing=12)
        self.software = Gtk.CheckButton(label=distribute.FIXED[0])
        self.testfiles = Gtk.CheckButton(label=distribute.FIXED[1])
        for b in (self.software, self.testfiles):
            b.connect("toggled", lambda _c: self._changed())
            r.pack_start(b, False, False, 0)
        s4.pack_start(r, False, False, 0)
        s4.pack_start(Gtk.Label(label="Content-Projekte:", xalign=0), False, False, 0)
        self.projects_box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4)
        s4.pack_start(self.projects_box, False, False, 0)
        self.project_checks: dict[str, Gtk.CheckButton] = {}

        s5 = section("5", "Abschluss")
        self.finish = Gtk.ComboBoxText()
        for key, label in (("reboot", "Neustart (startet danach Windows)"), ("poweroff", "Herunterfahren"),
                           ("none", "Nichts – Gerät bleibt im Agent")):
            self.finish.append(key, label)
        self.finish.connect("changed", lambda _c: self._changed())
        s5.pack_start(self.finish, False, False, 0)

        self.problems = Gtk.Label(xalign=0, wrap=True)
        self.problems.get_style_context().add_class("status-fail")
        grid.pack_start(self.problems, False, False, 0)
        self.error = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.error.get_style_context().add_class("status-fail")
        grid.pack_start(self.error, False, False, 0)
        self.pack_start(scrolled(grid), True, True, 0)
        self.reload()

    # ---------- Füllen ----------

    def _images(self, master: bool) -> list:
        return [i for i in self.main.restorable_images() if i.master or not master]

    def _fill_images(self, s: automation.Settings) -> None:
        self.image.remove_all()
        root = self.main._nas_root()
        for img in self._images(s.image_mode == "master"):
            rel = str(img.path.relative_to(root)) if root else str(img.path)
            self.image.append(rel, f"{'★ ' if img.master else ''}{img.name} – {img.kind} – "
                                   f"{img.mtime.strftime('%d.%m.%Y')}")
        if s.image and not self.image.set_active_id(s.image):
            self.image.append(s.image, f"{s.image} (nicht gefunden)")
            self.image.set_active_id(s.image)

    def reload(self) -> None:
        """Alles aus den gespeicherten Einstellungen neu aufbauen."""
        self._updating = True
        try:
            s = automation.settings(self.dev)
            self.switch.set_active(s.enabled)
            self.rearm.set_active(s.rearm)
            self.template.remove_all()
            for name in sorted(automation.load_templates(), key=str.lower):
                self.template.append(name, name)
            if s.template:
                self.template.set_active_id(s.template)
            self.backup.set_active(s.backup)
            (self.backup_image if s.backup_mode == "image" else self.backup_files).set_active(True)
            (self.mode_master if s.image_mode == "master" else self.mode_own).set_active(True)
            self._fill_images(s)
            self.disk.remove_all()
            for d in self.dev.inventory.get("disks") or []:
                self.disk.append(automation.disk_key(d), automation.disk_label(d))
            if s.disk_key and not self.disk.set_active_id(s.disk_key):
                self.disk.append(s.disk_key, f"{s.disk_label or s.disk_key} (zuletzt nicht gemeldet)")
                self.disk.set_active_id(s.disk_key)
            self.swiss.set_active(s.swiss)
            self.account.set_text(s.account)
            self.software.set_active(s.software)
            self.testfiles.set_active(s.testfiles)
            for child in self.projects_box.get_children():
                self.projects_box.remove(child)
            self.project_checks = {}
            root = self.main._nas_root()
            names = distribute.projects(root) if root else []
            for name in sorted(set(names) | set(s.projects), key=str.lower):
                check = Gtk.CheckButton(label=name if name in names else f"{name} (fehlt auf dem NAS)",
                                        active=name in s.projects)
                check.connect("toggled", lambda _c: self._changed())
                self.project_checks[name] = check
                self.projects_box.add(check)
            if not self.project_checks:
                self.projects_box.add(_hint("keine – Projektordner unter NAS: /Verteilen/Content anlegen"))
            self.projects_box.show_all()
            self.finish.set_active_id(s.finish)
        finally:
            self._updating = False
        self.refresh()

    def refresh(self) -> None:
        """Status, Hinweise und Knöpfe (bei jedem Ereignis der Automatisierung)."""
        s = automation.settings(self.dev)
        run = self.main.automation.run(self.dev.id)
        text = self.main.automation.text(self.dev) or ("ein – wartet, bis das Gerät im LAN auftaucht" if s.enabled
                                                       else "aus")
        if run is not None and run.phase == "running" and run.job is not None:
            text = f"läuft – {run.job.label} {run.job.shown_fraction * 100:.0f} %"
        self.state.set_text(text)
        self.btn_cancel.set_visible(run is not None and run.active)
        self.backup_choice.set_sensitive(s.backup)
        paused = self.main.cfg.automation_paused   # roter Stopp-Knopf: Schalter ausgegraut
        self.switch.set_sensitive(not paused)
        self.switch.set_tooltip_text("Automatisierung ist pausiert (roter Stopp-Knopf in der Geräteliste)"
                                     if paused else None)
        if self.switch.get_active() != s.enabled:
            self._updating = True
            self.switch.set_active(s.enabled)
            self._updating = False
        key, origin = self.dev.windows_key
        key_text = f"{devices.mask_key(key)} ({origin})" if key else "keiner – Windows aktiviert sich über die " \
                                                                    "digitale Lizenz"
        self.custom_text.set_text(
            f"Gerätename „{self.dev.name}“ → {computer_name_text(self.dev.name)} · Linux: "
            f"{linuxsetup.hostname(self.dev.name)}\nWindows-Key: {key_text}\n"
            "Nur bei Master-Images (mit Sysprep). Name ändern: Gerät oben umbenennen.")
        missing = automation.problems(s, self.main._nas_root())
        self.problems.set_text(("Noch nötig: " + " · ".join(missing)) if missing else "")
        self.error.set_text(f"Letzter Fehler: {s.last_error}" if s.last_error else "")

    # ---------- Ändern ----------

    def _mode_changed(self) -> None:
        if self._updating:
            return
        s = self._collect()
        self._updating = True
        try:
            self._fill_images(s)
        finally:
            self._updating = False
        self._changed()

    def _collect(self) -> automation.Settings:
        s = automation.settings(self.dev)
        s.enabled = self.switch.get_active()
        s.rearm = self.rearm.get_active()
        s.backup = self.backup.get_active()
        s.backup_mode = "image" if self.backup_image.get_active() else "files"
        s.image_mode = "master" if self.mode_master.get_active() else "own"
        s.image = self.image.get_active_id() or ""
        key = self.disk.get_active_id() or ""
        if key != s.disk_key:
            disk = automation.find_disk(self.dev.inventory.get("disks") or [], key)
            s.disk_key, s.disk_label = key, automation.disk_label(disk) if disk else s.disk_label
        s.swiss = self.swiss.get_active()
        s.account = self.account.get_text().strip()
        s.software, s.testfiles = self.software.get_active(), self.testfiles.get_active()
        s.projects = [n for n, c in self.project_checks.items() if c.get_active()]
        s.finish = self.finish.get_active_id() or "reboot"
        return s

    def _changed(self) -> None:
        if self._updating:
            return
        s = self._collect()
        if s.enabled and not automation.settings(self.dev).enabled:
            s.done_at = ""  # von Hand eingeschaltet: 24-h-Wartezeit vergessen
        self.main.save_automation(self.dev, s)
        self.refresh()

    def _apply_template(self) -> None:
        name = self.template.get_active_id()
        if not name:
            return
        try:
            s = automation.apply_template(self._collect(), name)
        except automation.AutomationError as e:
            confirm_error(self.get_toplevel(), str(e))
            return
        self.main.save_automation(self.dev, s)
        self.reload()

    def _save_template(self) -> None:
        name = ask_text(self.get_toplevel(), "Als Vorlage speichern", "Name der Vorlage (z. B. Schulungs-PC):",
                        self.template.get_active_id() or "")
        if not name:
            return
        try:
            automation.save_template(name, self._collect())
        except automation.AutomationError as e:
            confirm_error(self.get_toplevel(), str(e))
            return
        s = self._collect()
        s.template = name.strip()
        self.main.save_automation(self.dev, s)
        self.reload()

    def _delete_template(self) -> None:
        name = self.template.get_active_id()
        if name and confirm(self.get_toplevel(), f"Vorlage „{name}“ löschen?",
                            "Geräte, die sie verwendet haben, behalten ihre Einstellungen.", ok_label="Löschen"):
            automation.delete_template(name)
            self.reload()


class SendFoldersDialog(Gtk.Dialog):
    """Ordner senden: Software, Test Files und Content-Projekte auf den öffentlichen Desktop des Geräts."""

    def __init__(self, parent: Gtk.Window, nas_root: str, device_name: str, preset: str = ""):
        super().__init__(title="Ordner senden", transient_for=parent, modal=True)
        self.set_default_size(520, -1)
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.btn = self.add_button("Senden", Gtk.ResponseType.OK)
        self.btn.get_style_context().add_class("suggested-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"Auf den Desktop von <b>{GLib.markup_escape_text(device_name)}</b> (für alle Benutzer). "
                        "Vorhandene Ordner gleichen Namens werden ersetzt.")
        box.pack_start(head, False, False, 0)
        self.software = Gtk.CheckButton(label=distribute.FIXED[0], active=preset == "software")
        self.testfiles = Gtk.CheckButton(label=distribute.FIXED[1], active=preset == "testfiles")
        for b in (self.software, self.testfiles):
            b.connect("toggled", lambda _c: self._update())
            box.pack_start(b, False, False, 0)
        box.pack_start(Gtk.Label(label="Content – Projekte wählen:", xalign=0), False, False, 0)
        self.checks = {}
        names = distribute.projects(nas_root)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_start=16)
        for name in names:
            c = Gtk.CheckButton(label=name)
            c.connect("toggled", lambda _c: self._update())
            self.checks[name] = c
            inner.pack_start(c, False, False, 0)
        if not names:
            inner.pack_start(_hint("Keine Projekte – Ordner unter NAS: /Verteilen/Content anlegen "
                                   "(Reiter Dateien)"), False, False, 0)
        sw = scrolled(inner)
        sw.set_min_content_height(min(260, 28 * max(1, len(names))))
        box.pack_start(sw, True, True, 0)
        box.pack_start(_hint("Das Gerät muss mit dem Agent laufen; Windows vollständig heruntergefahren "
                             "(kein Schnellstart/Ruhezustand)."), False, False, 0)
        self.get_content_area().add(box)
        self.show_all()
        self._update()

    def items(self) -> list[str]:
        return distribute.items_for(self.software.get_active(), self.testfiles.get_active(),
                                    [n for n, c in self.checks.items() if c.get_active()])

    def _update(self) -> None:
        self.btn.set_sensitive(bool(self.items()))


class SettingsDialog(Gtk.Dialog):
    """Menü → Einstellungen: Automatisierung (gleichzeitig, Hauptschalter)."""

    def __init__(self, parent: Gtk.Window, cfg: config.Config):
        super().__init__(title="Einstellungen", transient_for=parent, modal=True)
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.add_button("Speichern", Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        frame = Gtk.Frame(label="Automatisierung")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=10)
        row = Gtk.Box(spacing=8)
        row.pack_start(Gtk.Label(label="Höchstens gleichzeitig", xalign=0), False, False, 0)
        self.max = Gtk.SpinButton.new_with_range(1, 10, 1)
        self.max.set_value(cfg.automation_max)
        row.pack_start(self.max, False, False, 0)
        row.pack_start(_hint("weitere Geräte warten in der Warteschlange (schont Netz und NAS)"), False, False, 0)
        inner.pack_start(row, False, False, 0)
        self.paused = Gtk.CheckButton(label="Alle Automatisierungen pausieren (Hauptschalter, z. B. bei Wartung "
                                            "am NAS)", active=cfg.automation_paused)
        inner.pack_start(self.paused, False, False, 0)
        frame.add(inner)
        box.pack_start(frame, False, False, 0)
        self.get_content_area().add(box)
        self.show_all()

    def values(self) -> tuple[int, bool]:
        return int(self.max.get_value()), self.paused.get_active()
