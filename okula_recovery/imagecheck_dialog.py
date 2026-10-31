"""Fenster „Images prüfen“ (I-007): prüft ein oder mehrere Images nacheinander im Hintergrund.

Nicht modal – das Tool bleibt bedienbar. Fortschritt mit Prozent und Restzeit, „Abbrechen“, am Ende eine
Zusammenfassung („12 Images geprüft: 11 ✔, 1 ✖“). Die Arbeit macht imagecheck.run.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import imagecheck, jobs  # noqa: E402
from okula_recovery.uikit import scrolled  # noqa: E402

if TYPE_CHECKING:
    from okula_recovery.ui import MainWindow


class CheckWindow(Gtk.Window):
    def __init__(self, main: "MainWindow", paths: list[str], title: str,
                 on_result: Callable[[str, dict], None], on_finished: Callable[[list, bool], None]):
        super().__init__(title="Images prüfen")
        self.set_transient_for(main)
        self.set_default_size(720, 420)
        self.paths, self.on_result_cb, self.on_finished_cb = paths, on_result, on_finished
        self.cancel = threading.Event()
        self.started = time.monotonic()
        self.running = True

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(f"<b>{GLib.markup_escape_text(title)}</b> – {len(paths)} Image"
                        f"{'s' if len(paths) != 1 else ''}. Nur lesen, das Image wird nicht verändert.")
        box.pack_start(head, False, False, 0)
        self.current = Gtk.Label(label="Image wird geprüft …", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        box.pack_start(self.current, False, False, 0)
        self.bar = Gtk.ProgressBar(show_text=True)
        self.bar.set_text("0 %")
        box.pack_start(self.bar, False, False, 0)
        self.log = Gtk.ListStore(str, str, str)       # Symbol (Markup), Image, Hinweis
        view = Gtk.TreeView(model=self.log)
        for i, title_ in enumerate(("Ergebnis", "Image", "Hinweis")):
            cell = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title_, cell, **({"markup": i} if i == 0 else {"text": i}))
            col.set_resizable(True)
            col.set_expand(i == 2)
            view.append_column(col)
        box.pack_start(scrolled(view), True, True, 0)
        self.summary = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(self.summary, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        self.btn_cancel = Gtk.Button(label="Abbrechen")
        self.btn_cancel.connect("clicked", lambda _b: self._cancel())
        buttons.pack_end(self.btn_cancel, False, False, 0)
        self.btn_close = Gtk.Button(label="Schliessen", sensitive=False)
        self.btn_close.connect("clicked", lambda _b: self.destroy())
        buttons.pack_end(self.btn_close, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.add(box)
        self.connect("delete-event", self._on_delete)
        self.show_all()
        threading.Thread(target=self._work, daemon=True, name="image-check").start()

    # ---------- Hintergrund ----------

    def _work(self) -> None:
        results, cancelled = imagecheck.run(
            self.paths,
            lambda i, n, frac, name, file: GLib.idle_add(self._progress, i, n, frac, name, file),
            lambda path, res: GLib.idle_add(self._result, path, res),
            self.cancel)
        GLib.idle_add(self._finished, results, cancelled)

    # ---------- GTK-Thread ----------

    def _progress(self, i: int, n: int, frac: float, name: str, file: str) -> bool:
        self.current.set_text(f"Image {i + 1}/{n}: {name} wird geprüft" + (f" · {file}" if file else "") + " …")
        self.bar.set_fraction(max(0.0, min(1.0, frac)))
        elapsed = time.monotonic() - self.started
        eta = elapsed * (1 - frac) / frac if frac > 0.02 and elapsed > 5 else None
        self.bar.set_text(f"{frac * 100:.0f} %" + (f" · {jobs.eta_text(eta)}" if eta is not None else ""))
        return False

    def _result(self, path: str, res: dict) -> bool:
        status = res.get("status")
        symbol = f'<span foreground="{imagecheck.COLOR.get(status, "#757575")}">' \
                 f'{imagecheck.SYMBOL.get(status, "?")} {imagecheck.LABEL.get(status, "")}</span>'
        note = (res.get("message") or "") if status != imagecheck.OK else f"{res.get('seconds', 0):.0f} s"
        self.log.append([symbol, Path(path).name, note])
        self.on_result_cb(path, res)
        return False

    def _finished(self, results: list, cancelled: bool) -> bool:
        self.running = False
        text = imagecheck.summary(results, cancelled)
        self.summary.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
        self.current.set_text("Prüfung abgebrochen" if cancelled else "Prüfung beendet")
        if not cancelled:
            self.bar.set_fraction(1.0)
            self.bar.set_text("100 %")
        self.btn_cancel.set_sensitive(False)
        self.btn_close.set_sensitive(True)
        self.on_finished_cb(results, cancelled)
        return False

    def _cancel(self) -> None:
        self.cancel.set()
        self.btn_cancel.set_sensitive(False)
        self.current.set_text("Wird abgebrochen …")

    def _on_delete(self, *_a) -> bool:
        if self.running:
            self._cancel()     # Fenster schliessen = abbrechen; geschlossen wird nach dem Abbruch
            GLib.timeout_add(200, self._close_when_done)
            return True
        return False

    def _close_when_done(self) -> bool:
        if self.running:
            return True
        self.destroy()
        return False
