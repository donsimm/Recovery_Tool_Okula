"""Reiter „Hardware-Test“ im Gerätefenster (I-023): Schnelltest / Gründlich starten, Ergebnisse ansehen,
PDF-Prüfprotokoll speichern."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import devices, hwreport  # noqa: E402
from okula_recovery.uikit import confirm_error, numbered_section, remember_columns, scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow


def _esc(text: str) -> str:
    return GLib.markup_escape_text(text or "")


def chip(status: str) -> str:
    return (f'<span foreground="{hwreport.COLOR.get(status, "#757575")}"><b>{hwreport.SYMBOL.get(status, "?")} '
            f'{_esc(hwreport.LABEL.get(status, ""))}</b></span>')


class HwTab(Gtk.Box):
    def __init__(self, main: "MainWindow", dev: devices.Device):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        self.main, self.dev = main, dev

        start = numbered_section(self, "", "Test starten", "nur lesend – Daten und Einstellungen bleiben unverändert")
        row = Gtk.Box(spacing=8)
        self.btn_quick = Gtk.Button(label=f"Schnelltest ({hwreport.DURATION['quick']})")
        self.btn_quick.set_tooltip_text("Akku, Temperaturen, SMART-Selbsttest kurz, Arbeitsspeicher (Teil), "
                                        "1 min CPU-Last, Netzwerk-Durchsatz zum Server")
        self.btn_quick.connect("clicked", lambda _b: self.start("quick"))
        self.btn_full = Gtk.Button(label=f"Gründlich ({hwreport.DURATION['thorough']})")
        self.btn_full.set_tooltip_text("Wie Schnelltest, dazu SMART-Selbsttest lang, jeden Sektor der Disk lesen, "
                                       "15 min CPU-Last, grösserer Arbeitsspeicher-Test")
        self.btn_full.connect("clicked", lambda _b: self.start("thorough"))
        row.pack_start(self.btn_quick, False, False, 0)
        row.pack_start(self.btn_full, False, False, 0)
        self.state = Gtk.Label(xalign=0, wrap=True)
        self.state.get_style_context().add_class("status-idle")
        row.pack_start(self.state, True, True, 0)
        start.pack_start(row, False, False, 0)
        self.disk_box = Gtk.Box(spacing=12)
        start.pack_start(self.disk_box, False, False, 0)
        self.disk_checks: dict[str, Gtk.CheckButton] = {}

        res = numbered_section(self, "", "Ergebnis", "Doppelklick bzw. Pfeil: Einzelheiten")
        bar = Gtk.Box(spacing=8)
        bar.pack_start(Gtk.Label(label="Test vom"), False, False, 0)
        self.which = Gtk.ComboBoxText()
        self.which.connect("changed", lambda _c: self.fill())
        bar.pack_start(self.which, False, False, 0)
        self.verdict = Gtk.Label(xalign=0, wrap=True)
        bar.pack_start(self.verdict, True, True, 0)
        self.btn_pdf = Gtk.Button(label="Protokoll als PDF …")
        self.btn_pdf.connect("clicked", lambda _b: self.save_pdf())
        bar.pack_end(self.btn_pdf, False, False, 0)
        res.pack_start(bar, False, False, 0)
        self.store = Gtk.TreeStore(str, str, str, str)       # Bereich, Ergebnis (Markup), Befund, Tooltip
        self.view = Gtk.TreeView(model=self.store)
        for i, title in enumerate(("Bereich", "Ergebnis", "Befund")):
            cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END if i != 1 else Pango.EllipsizeMode.NONE)
            self.view.append_column(Gtk.TreeViewColumn(title, cell, **({"markup": i} if i == 1 else {"text": i})))
        remember_columns(self.view, "geraet_hwtest", {"Bereich": 300, "Ergebnis": 130, "Befund": 620})
        self.view.set_tooltip_column(3)
        self.view.connect("row-activated", lambda v, path, _c: v.row_expanded(path) and v.collapse_row(path)
                          or v.expand_row(path, False))
        res.pack_start(scrolled(self.view), True, True, 0)
        self.child_set_property(res, "expand", True)
        self.child_set_property(res, "fill", True)
        self.refresh()

    # ---------- Anzeige ----------

    def connected(self):
        agent = self.main.online_agent(self.dev)
        return agent if agent is not None and agent.control_port else None

    def running(self) -> bool:
        return any(j.kind == "hwtest" for j in self.main.jobs.running() if j.device_id == self.dev.id)

    def refresh(self) -> None:
        # Disks: alle internen, vorgewählt
        known = {p for p, c in self.disk_checks.items() if not c.get_active()}
        for c in self.disk_box.get_children():
            self.disk_box.remove(c)
        self.disk_checks = {}
        disks = [d for d in (self.dev.inventory.get("disks") or []) if d.get("transport") != "usb"]
        if disks:
            self.disk_box.pack_start(Gtk.Label(label="Disks:"), False, False, 0)
        for d in disks:
            label = f"{d.get('name')} {d.get('model') or ''} ({(d.get('size') or 0) / 1e9:.0f} GB)".strip()
            c = Gtk.CheckButton(label=label, active=d.get("path") not in known)
            self.disk_box.pack_start(c, False, False, 0)
            self.disk_checks[d.get("path") or f"/dev/{d.get('name')}"] = c
        self.disk_box.show_all()
        ok = self.connected() is not None and not self.running()
        for b in (self.btn_quick, self.btn_full):
            b.set_sensitive(ok)
        self.state.set_text("Test läuft – Fortschritt im Reiter Aufträge" if self.running() else
                            "" if self.connected() is not None else "Gerät mit dem Agent verbinden, um zu testen")
        current = self.which.get_active()
        self.which.remove_all()
        for r in self.dev.hwtests or []:
            self.which.append_text(hwreport.headline(r))
        self.which.set_active(current if 0 <= current < len(self.dev.hwtests or []) else 0)
        self.fill()

    def _report(self) -> dict | None:
        i = self.which.get_active()
        tests = self.dev.hwtests or []
        return tests[i] if 0 <= i < len(tests) else None

    def fill(self) -> None:
        self.store.clear()
        report = self._report()
        self.btn_pdf.set_sensitive(report is not None)
        if report is None:
            self.verdict.set_text("Noch kein Test")
            return
        status = hwreport.overall(report)
        self.verdict.set_markup(f'<span foreground="{hwreport.COLOR[status]}"><b>{_esc(hwreport.verdict(report))}'
                                "</b></span>")
        for r in report.get("results") or []:
            tip = "\n".join([r.get("summary", "")] + list(r.get("details") or []))
            it = self.store.append(None, [r.get("title", ""), chip(r.get("status")), r.get("summary", ""), tip])
            for d in r.get("details") or []:
                self.store.append(it, ["", "", d, d])
        for i, r in enumerate(report.get("results") or []):   # Auffälliges gleich aufklappen
            if r.get("status") in (hwreport.FAIL, hwreport.WARN):
                self.view.expand_row(Gtk.TreePath(i), False)

    # ---------- Aktionen ----------

    def start(self, level: str) -> None:
        disks = [p for p, c in self.disk_checks.items() if c.get_active()]
        if level == "thorough":
            dlg = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True, message_type=Gtk.MessageType.QUESTION,
                                    buttons=Gtk.ButtonsType.OK_CANCEL, text="Gründlichen Hardware-Test starten?")
            dlg.format_secondary_text("Dauert je nach Disk 1–3 Stunden (HDD länger). Das Gerät bleibt so lange im Agent; "
                                      "andere Aufträge auf den gewählten Disks warten. Abbrechen geht jederzeit im "
                                      "Reiter Aufträge.")
            answer = dlg.run()
            dlg.destroy()
            if answer != Gtk.ResponseType.OK:
                return
        self.main.start_hwtest(self.dev, level, disks)
        self.refresh()

    def save_pdf(self) -> None:
        report = self._report()
        if report is None:
            return
        dlg = Gtk.FileChooserDialog(title="Prüfprotokoll als PDF speichern", transient_for=self.get_toplevel(),
                                    action=Gtk.FileChooserAction.SAVE)
        dlg.add_buttons("Abbrechen", Gtk.ResponseType.CANCEL, "Speichern", Gtk.ResponseType.OK)
        dlg.set_do_overwrite_confirmation(True)
        day = (report.get("finished") or report.get("started") or "")[:10]
        dlg.set_current_name(f"Hardwaretest_{self.dev.name}_{day}.pdf")
        if dlg.run() == Gtk.ResponseType.OK:
            path = Path(dlg.get_filename())
            try:
                hwreport.write_pdf(path, self.dev, report)
                self.main.status(f"Prüfprotokoll gespeichert: {path}")
            except ImportError:
                confirm_error(self.get_toplevel(), "PDF braucht python3-reportlab – sudo ./install.sh ausführen")
            except OSError as e:
                confirm_error(self.get_toplevel(), f"Nicht gespeichert: {e}")
        dlg.destroy()
