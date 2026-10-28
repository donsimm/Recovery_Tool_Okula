"""Leiste mit der Auslastung des Servers: CPU, RAM und LAN mit Verlauf der letzten Minute."""

from __future__ import annotations

from collections import deque

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from okula_recovery import sysload  # noqa: E402

INTERVAL = 1     # Sekunden zwischen Messungen
HISTORY = 60     # Punkte im Verlauf
HIGH = 0.9       # ab hier Wert rot

# Stil: .load-name, .load-value, .load-high in ui.CSS


class Sparkline(Gtk.DrawingArea):
    """Verlauf 0–1 als gefüllte Kurve; neuester Wert rechts."""

    def __init__(self, rgb: tuple[float, float, float]):
        super().__init__()
        self.rgb = rgb
        self.values: deque[float] = deque([0.0] * HISTORY, maxlen=HISTORY)
        self.set_size_request(60, 20)
        self.connect("draw", self._draw)

    def push(self, value: float) -> None:
        self.values.append(max(0.0, min(1.0, value)))
        self.queue_draw()

    def _draw(self, _w, cr) -> bool:
        w, h = self.get_allocated_width(), self.get_allocated_height()
        r, g, b = self.rgb
        cr.set_source_rgba(r, g, b, 0.08)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        step = w / (HISTORY - 1)
        pts = [(i * step, h - 1 - v * (h - 2)) for i, v in enumerate(self.values)]
        cr.move_to(0, h)
        for x, y in pts:
            cr.line_to(x, y)
        cr.line_to(w, h)
        cr.close_path()
        cr.set_source_rgba(r, g, b, 0.30)
        cr.fill()
        cr.move_to(*pts[0])
        for x, y in pts[1:]:
            cr.line_to(x, y)
        cr.set_source_rgba(r, g, b, 1.0)
        cr.set_line_width(1.5)
        cr.stroke()
        return False


class Meter(Gtk.Box):
    def __init__(self, name: str, rgb: tuple[float, float, float]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        head = Gtk.Box(spacing=6)
        label = Gtk.Label(label=name, xalign=0)
        label.get_style_context().add_class("load-name")
        head.pack_start(label, False, False, 0)
        self.value = Gtk.Label(label="–", xalign=1, ellipsize=Pango.EllipsizeMode.START)
        self.value.get_style_context().add_class("load-value")
        head.pack_end(self.value, True, True, 0)
        self.pack_start(head, False, False, 0)
        self.spark = Sparkline(rgb)
        self.pack_start(self.spark, True, True, 0)

    def update(self, fraction: float, text: str, tip: str) -> None:
        self.spark.push(fraction)
        self.value.set_text(text)
        ctx = self.value.get_style_context()
        (ctx.add_class if fraction >= HIGH else ctx.remove_class)("load-high")
        self.set_tooltip_text(tip)


class LoadBar(Gtk.Box):
    """CPU · RAM · LAN nebeneinander; misst selbst jede Sekunde, solange die Leiste sichtbar ist."""

    def __init__(self, sampler: sysload.Sampler | None = None):
        super().__init__(spacing=16, homogeneous=True)
        self.sampler = sampler or sysload.Sampler()
        self.cpu = Meter("CPU", (0.21, 0.52, 0.89))
        self.ram = Meter("RAM", (0.57, 0.25, 0.67))
        self.lan = Meter("LAN", (0.18, 0.62, 0.40))
        for m in (self.cpu, self.ram, self.lan):
            self.pack_start(m, True, True, 0)
        self._peak = 1e6  # Skala der LAN-Kurve ohne bekannte Geschwindigkeit (Bytes/s)
        self.tick()
        self._timer = GLib.timeout_add_seconds(INTERVAL, self.tick)
        self.connect("destroy", lambda _w: GLib.source_remove(self._timer))

    def tick(self) -> bool:
        if not self.get_mapped() and self.cpu.value.get_text() != "–":
            return True  # verdeckt: nicht messen, aber weiterlaufen
        load = self.sampler.sample()
        self.show_load(load)
        return True

    def show_load(self, load: sysload.Load) -> None:
        self.cpu.update(load.cpu, f"{load.cpu * 100:.0f} %",
                        f"CPU: {load.cpu * 100:.0f} % über {load.cores} Kerne\nLast (1/5/15 min): {load.loadavg}")
        self.ram.update(load.mem, f"{sysload.gib(load.mem_used)} / {sysload.gib(load.mem_total)} GiB",
                        f"RAM belegt: {sysload.gib(load.mem_used)} von {sysload.gib(load.mem_total)} GiB "
                        f"({load.mem * 100:.0f} %, ohne Cache)\nSwap belegt: {sysload.gib(load.swap_used)} GiB")
        if load.link:
            fraction = load.lan
        else:
            self._peak = max(self._peak * 0.98, load.rx, load.tx, 1e6)
            fraction = max(load.rx, load.tx) / self._peak
        speed = f"{load.link / 1000:g} Gbit/s" if load.link >= 1000 else (f"{load.link} Mbit/s" if load.link else "unbekannt")
        self.lan.update(fraction, sysload.rates(load.rx, load.tx),
                        f"Netzwerk {load.iface or '–'} · Verbindung {speed}\n"
                        f"Empfangen: {sysload.mbit(load.rx)}\nGesendet: {sysload.mbit(load.tx)}"
                        + (f"\nAuslastung: {load.lan * 100:.0f} %" if load.link else ""))
