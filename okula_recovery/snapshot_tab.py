"""Reiter „Snapshots“ im Gerätefenster einer VM (I-001 Auftrag 4): Liste, erstellen, zurück, löschen."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from okula_recovery import devices, nas, vm  # noqa: E402
from okula_recovery.uikit import remember_columns, run_async, scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow

HINT = ("Ein Snapshot friert den Stand der Disk ein, z. B. „frisch installiert“ oder „vor Sysprep“ – zurück geht es in "
        "Sekunden. Von Hand nur bei ausgeschalteter VM (nur die Disk, ohne Arbeitsspeicher). Vor Zurückspielen, OS "
        "installieren und Automatisierung entsteht mit dem Häkchen „Vorher Snapshot“ automatisch einer.")
CURRENT = "◀ aktueller Stand"


class SnapshotTab(Gtk.Box):
    def __init__(self, main: "MainWindow", dev: devices.Device):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        self.main, self.dev = main, dev
        self.snaps: dict[str, vm.Snapshot] = {}
        self._loading = False
        hint = Gtk.Label(label=HINT, xalign=0, wrap=True, max_width_chars=110)
        hint.get_style_context().add_class("status-idle")
        self.pack_start(hint, False, False, 0)
        # Titel, Datum, Automatisch, Grösse, Stand, ID (versteckt)
        self.store = Gtk.ListStore(str, str, str, str, str, str)
        self.view = Gtk.TreeView(model=self.store)
        for i, title in enumerate(("Titel", "Datum", "Automatisch", "Grösse", "Stand")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            col.set_expand(i == 0)
            self.view.append_column(col)
        remember_columns(self.view, "geraet_snapshots", {"Titel": 280})
        self.view.get_selection().connect("changed", lambda _s: self.refresh_buttons())
        self.view.connect("row-activated", lambda *_a: self._revert())
        self.pack_start(scrolled(self.view), True, True, 0)
        self.current = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.pack_start(self.current, False, False, 0)
        self.warning = Gtk.Label(xalign=0, wrap=True, no_show_all=True)
        self.warning.get_style_context().add_class("status-fail")
        self.pack_start(self.warning, False, False, 0)
        self.bar = Gtk.ProgressBar(show_text=True, no_show_all=True)
        self.pack_start(self.bar, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        self.btn_create = Gtk.Button(label="Snapshot erstellen …")
        self.btn_create.connect("clicked", lambda _b: self.main.vm_snapshot_create(self.dev))
        self.btn_revert = Gtk.Button(label="Zurück zu diesem Snapshot …")
        self.btn_revert.connect("clicked", lambda _b: self._revert())
        self.btn_delete = Gtk.Button(label="Löschen …")
        self.btn_delete.connect("clicked", lambda _b: self._delete())
        for b in (self.btn_create, self.btn_revert):
            buttons.pack_start(b, False, False, 0)
        buttons.pack_end(self.btn_delete, False, False, 0)
        self.pack_start(buttons, False, False, 0)

    def selected(self) -> vm.Snapshot | None:
        model, it = self.view.get_selection().get_selected()
        return self.snaps.get(model[it][5]) if it is not None else None

    def _revert(self) -> None:
        snap = self.selected()
        if snap is not None:
            self.main.vm_snapshot_revert(self.dev, snap)

    def _delete(self) -> None:
        snap = self.selected()
        if snap is not None:
            self.main.vm_snapshot_delete(self.dev, snap)

    def load(self) -> None:
        """Snapshots, Grössen und freien Platz im Hintergrund lesen."""
        if self._loading or not vm.available():
            return
        self._loading = True
        name = self.dev.vm.get("name", "")

        def work():
            if name not in self.main.virsh.names():
                return [], 0, vm.free_disk()
            return self.main.virsh.snapshots(name), self.main.virsh.snapshot_changes(name), vm.free_disk()

        run_async(work, self._loaded)

    def _loaded(self, result) -> None:
        self._loading = False
        selected = self.selected()
        self.store.clear()
        self.snaps.clear()
        if isinstance(result, Exception):
            self.current.set_text(f"Snapshots nicht lesbar: {result}")
            self.refresh_buttons()
            return
        snaps, changes, free = result
        base = None
        for s in reversed(snaps):                     # neueste zuerst
            key = str(s.id)
            self.snaps[key] = s
            it = self.store.append([s.title, s.when, "ja" if s.auto else "nein", nas.format_size(s.size),
                                    CURRENT if s.current else "", key])
            if selected is not None and selected.id == s.id:
                self.view.get_selection().select_iter(it)
            if s.current:
                base = s
        if not snaps:
            self.current.set_text("Noch kein Snapshot.")
        elif base is not None:
            self.current.set_text(f"Aktueller Stand: ‚{base.title}‘ plus {nas.format_size(changes)} Änderungen "
                                  f"seither · {len(snaps)} Snapshot{'s' if len(snaps) != 1 else ''} belegen "
                                  f"{nas.format_size(sum(s.size for s in snaps))}")
        else:
            self.current.set_text(f"Aktueller Stand: {nas.format_size(changes)} · {len(snaps)} Snapshots")
        low = vm.low_space_text(free)
        self.warning.set_text(low)
        self.warning.set_visible(bool(low))
        self.refresh_buttons()

    def progress(self, fraction: float, text: str) -> None:
        self.bar.set_visible(True)
        self.bar.set_fraction(max(0.0, min(1.0, fraction)))
        self.bar.set_text(f"{text} … {fraction * 100:.0f} %")

    def refresh_buttons(self) -> None:
        """Knöpfe nach Zustand der VM: alles nur bei ausgeschalteter VM, sonst mit Grund im Tooltip."""
        why = self.main.vm_why(self.dev, "snapshot")
        busy = self.dev.vm.get("name") in self.main.vm_snap_busy
        if not busy:
            self.bar.set_visible(False)
        snap = self.selected()
        self.btn_create.set_sensitive(not why)
        self.btn_create.set_tooltip_text(why or "Stand der Disk jetzt einfrieren (VM ausgeschaltet, dauert Sekunden)")
        for b, tip in ((self.btn_revert, "Disk auf den Stand des gewählten Snapshots zurücksetzen – spätere "
                                         "Änderungen gehen verloren"),
                       (self.btn_delete, "Gewählten Snapshot löschen – der aktuelle Stand bleibt")):
            reason = why or ("" if snap is not None else "Zuerst einen Snapshot in der Liste wählen")
            b.set_sensitive(not reason)
            b.set_tooltip_text(reason or tip)
