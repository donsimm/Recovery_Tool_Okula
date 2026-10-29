"""Fenster „Auf das NAS kopieren“: Dateien/Ordner (z. B. Clonezilla-Images) mit Fortschritt und Abbrechen."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import clonezilla, nasfiles  # noqa: E402
from okula_recovery.usbtools import rate_text  # noqa: E402


def clonezilla_images(folder: Path, names: list[str]) -> list[str]:
    """Kopierte Clonezilla-Images (direkt oder eine Ebene tiefer, z. B. ein ganzer „partimag“-Ordner)."""
    found = []
    for name in names:
        path = folder / name
        if clonezilla.is_clonezilla(path):
            found.append(name)
        elif path.is_dir():
            found += [f"{name}/{sub.name}" for sub in sorted(path.iterdir())
                      if sub.is_dir() and clonezilla.is_clonezilla(sub)]
    return found


class CopyDialog(Gtk.Dialog):
    """Kopiert im Hintergrund; on_done(namen | None) danach im GTK-Thread (Listen aktualisieren)."""

    def __init__(self, parent: Gtk.Window, root: str, rel: str, plan: nasfiles.CopyPlan,
                 on_done: Callable[[list[str] | None], None]):
        super().__init__(title="Auf das NAS kopieren", transient_for=parent, modal=False)
        self.set_default_size(560, -1)
        self.root, self.rel, self.plan, self.on_done = root, rel, plan, on_done
        self.cancel = threading.Event()
        self.running = True
        self.btn = self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.connect("response", self._on_response)
        self.connect("delete-event", self._on_delete)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=14)
        names = ", ".join(s.name for s in plan.sources[:3]) + (" …" if len(plan.sources) > 3 else "")
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"<b>{GLib.markup_escape_text(names)}</b>\n"
                        f"{plan.files} Dateien, {plan.bytes / 1000**3:.1f} GB → NAS: /{GLib.markup_escape_text(rel)}")
        box.pack_start(head, False, False, 0)
        self.bar = Gtk.ProgressBar(show_text=True)
        self.bar.set_text("Starte …")
        box.pack_start(self.bar, False, False, 0)
        self.file = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.START)
        self.file.get_style_context().add_class("status-idle")
        box.pack_start(self.file, False, False, 0)
        if plan.skipped:
            skipped = Gtk.Label(xalign=0, wrap=True)
            skipped.set_text(f"{len(plan.skipped)} Links/Sonderdateien werden übersprungen")
            skipped.get_style_context().add_class("status-idle")
            box.pack_start(skipped, False, False, 0)
        self.get_content_area().add(box)
        self.show_all()
        self.started = time.monotonic()
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            result = nasfiles.copy_in(self.root, self.rel, self.plan,
                                      lambda d, t, f: GLib.idle_add(self._progress, d, t, f), self.cancel)
        except Exception as e:  # Fehler anzeigen statt still zu sterben
            result = e
        GLib.idle_add(self._finished, result)

    def _progress(self, done: int, total: int, current: str) -> bool:
        frac = done / total if total else 1.0
        self.bar.set_fraction(frac)
        self.bar.set_text(f"{frac * 100:.0f} %  ·  {rate_text(done, total, self.started)}")
        if current:
            self.file.set_text(current)
        return False

    def _finished(self, result) -> bool:
        self.running = False
        self.btn.set_label("Schliessen")
        self.btn.set_sensitive(True)
        if isinstance(result, Exception):
            self.on_done(None)
            if self.cancel.is_set():  # vom Benutzer abgebrochen: Fenster zu, Meldung in der Statuszeile
                parent = self.get_transient_for()
                if hasattr(parent, "status"):
                    parent.status("Kopieren abgebrochen – auf dem NAS bleibt nichts Halbes zurück")
                self.destroy()
                return False
            self.bar.set_text("Fehlgeschlagen")
            self.file.set_text(str(result))
            return False
        self.bar.set_fraction(1.0)
        found = clonezilla_images(nasfiles.resolve(self.root, self.rel), result)
        self.bar.set_text(f"Fertig – {len(result)} {'Eintrag' if len(result) == 1 else 'Einträge'} kopiert")
        self.file.set_text(f"Clonezilla-Image erkannt: {', '.join(found)} – steht jetzt im Reiter „Images“"
                           if found else "")
        self.on_done(result)
        return False

    def _on_response(self, _dlg, response: int) -> None:
        if self.running:
            self._abort()
        else:
            self.destroy()

    def _on_delete(self, *_a) -> bool:
        """✕ während des Kopierens = Abbrechen (Fenster schliesst sich, sobald aufgeräumt ist)."""
        if self.running:
            self._abort()
            return True
        return False

    def _abort(self) -> None:
        self.cancel.set()
        self.btn.set_sensitive(False)
        self.bar.set_text("Breche ab … (räume auf)")
