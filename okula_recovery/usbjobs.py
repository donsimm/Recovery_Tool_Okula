"""USB-Vorgänge im Tool: Root-Helfer starten, Ausgabe auswerten, zuverlässig abbrechen (B-029).

Gilt für USB klonen, USB formatieren, Agent-USB-Stick (bzw. Restore-Stick) und Boot-Stick aus ISO.

Abbrechen: „CANCEL“ auf stdin und stdin schliessen. Reagiert der Helfer nicht innerhalb von CANCEL_TIMEOUT Sekunden
(z. B. hängt er in I/O auf einen verschwundenen Stick), bekommt die Prozessgruppe von sudo SIGTERM (sudo leitet es
an den Helfer weiter), nach KILL_TIMEOUT SIGKILL. Der Helfer selbst beendet sich bei geschlossenem stdin ebenfalls
(usbguard.watch). Danach ist der Vorgang im Tool immer beendet – auch wenn der Prozess im Kernel noch hängt.

Gerät verschwunden: Das Tool prüft alle PROBE_EVERY Sekunden, ob die Datenträger noch da sind (usbguard.current).

Ohne GTK – die Oberfläche übergibt Rückrufe (und GLib.idle_add als post).
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from typing import Callable

from okula_recovery import usbguard
from okula_recovery.usbguard import Ident

CANCEL_TIMEOUT = 15.0     # s nach „CANCEL“, bis das Tool den Helfer beendet
KILL_TIMEOUT = 5.0        # s nach SIGTERM bis SIGKILL bzw. bis das Tool nicht mehr wartet
EXIT_TIMEOUT = 15.0       # s nach DONE/ERROR, bis das Tool nicht mehr auf das Prozessende wartet
PROBE_EVERY = 3.0         # s zwischen zwei Prüfungen „Datenträger noch da?“
FORCED = ("Abgebrochen – das Hilfsprogramm hat nicht reagiert und wurde beendet. Der Ziel-Datenträger ist "
          "unvollständig und muss neu beschrieben werden.")


def _reap(proc) -> None:
    try:
        proc.wait()
    except (OSError, ValueError):
        pass


class HelperProcess:
    """Ein Lauf des Root-Helfers. run() blockiert bis zum Ende und gibt (ok, Fehlertext) zurück – auch wenn der
    Helfer nicht mehr reagiert."""

    def __init__(self, cmd: list[str], stdin_text: str = "", cwd: str | None = None, idents=(),
                 popen=subprocess.Popen, probe=None, cancel_timeout: float | None = None,
                 kill_timeout: float | None = None, exit_timeout: float | None = None,
                 probe_every: float | None = None, tick: float = 0.25, clock: Callable[[], float] = time.monotonic):
        """Zeiten None = Vorgaben dieses Moduls (zum Zeitpunkt des Aufrufs)."""
        self.cmd, self.stdin_text, self.cwd = cmd, stdin_text, cwd
        self.idents: tuple[Ident, ...] = tuple(idents)
        self.popen, self.probe = popen, probe or usbguard.current
        self.cancel_timeout = CANCEL_TIMEOUT if cancel_timeout is None else cancel_timeout
        self.kill_timeout = KILL_TIMEOUT if kill_timeout is None else kill_timeout
        self.exit_timeout = EXIT_TIMEOUT if exit_timeout is None else exit_timeout
        self.probe_every = PROBE_EVERY if probe_every is None else probe_every
        self.tick, self.clock = tick, clock
        self.proc = None
        self.done_text = ""        # Text der DONE-Zeile
        self.forced = False        # Helfer musste beendet werden bzw. das Tool hat nicht mehr gewartet
        self._abandoned = False    # nach dem Ende: späte Zeilen nicht mehr weitergeben

    # ---------- Prozess ----------

    def _send_cancel(self) -> None:
        stdin = getattr(self.proc, "stdin", None)
        if stdin is None:
            return
        try:
            stdin.write("CANCEL\n")
            stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            stdin.close()          # EOF: auch der Helfer bricht ab (usbguard.watch)
        except (OSError, ValueError):
            pass

    def _signal(self, sig: int) -> None:
        """An die Prozessgruppe von sudo (eigene Sitzung); sudo leitet SIGTERM an den Helfer weiter. Prozesse von
        root in der Gruppe darf der Benutzer nicht treffen – das ist so gewollt."""
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, sig)
            return
        except (OSError, AttributeError, TypeError):
            pass
        try:
            proc.send_signal(sig)
        except (OSError, AttributeError):
            pass

    # ---------- Lauf ----------

    def run(self, cancel: threading.Event, on_progress: Callable[[float, str], None],
            on_line: Callable[[str], None]) -> tuple[bool, str]:
        try:
            proc = self.popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, cwd=self.cwd, start_new_session=True)
        except OSError as e:
            return False, str(e)
        self.proc = proc
        try:
            proc.stdin.write(self.stdin_text)
            proc.stdin.flush()     # stdin bleibt offen: „CANCEL“ kommt später
        except (OSError, ValueError, AttributeError):
            pass

        state = {"done": False, "error": "", "final": False}
        eof = threading.Event()

        def read() -> None:
            try:
                for raw in proc.stdout:
                    if self._abandoned:
                        return
                    line = raw.rstrip("\n")
                    kind, _, text = line.partition(" ")
                    if kind == "PROGRESS":
                        frac, _, msg = text.partition(" ")
                        try:
                            on_progress(float(frac), msg)
                        except ValueError:
                            pass
                        continue
                    if kind == "DONE":
                        state["done"], state["final"], self.done_text = True, True, text
                    elif kind == "ERROR":
                        state["error"], state["final"] = text, True
                    on_line(line)
            except (OSError, ValueError):
                pass
            finally:
                eof.set()

        threading.Thread(target=read, daemon=True).start()
        cancel_at = term_at = final_at = None
        gone = ""
        misses: dict[str, int] = {}
        next_probe = self.clock() + self.probe_every
        while not eof.wait(self.tick):
            now = self.clock()
            if cancel.is_set() and cancel_at is None:
                self._send_cancel()
                cancel_at = now
            if self.idents and cancel_at is None and now >= next_probe:
                next_probe = now + self.probe_every
                for ident in self.idents:
                    cur = self.probe(ident.path)
                    if cur is None or cur.size == 0:
                        misses[ident.path] = misses.get(ident.path, 0) + 1
                        if misses[ident.path] >= usbguard.GONE_MISSES:
                            gone = usbguard.gone_message(ident)
                            on_line(f"WARN {ident.text()} ist nicht mehr da – Vorgang wird abgebrochen")
                            self._send_cancel()
                            cancel_at = now
                            break
                    else:
                        misses[ident.path] = 0
            if state["final"] and final_at is None:
                final_at = now
            if cancel_at is not None and term_at is None and now - cancel_at >= self.cancel_timeout:
                on_line("WARN Hilfsprogramm reagiert nicht – wird beendet")
                self._signal(signal.SIGTERM)
                term_at = now
            if term_at is not None and now - term_at >= self.kill_timeout:
                self._signal(signal.SIGKILL)
                self.forced = True
                break
            if final_at is not None and cancel_at is None and now - final_at >= self.exit_timeout:
                self.forced = True     # DONE/ERROR gemeldet, Prozess endet nicht: nicht ewig warten
                break

        rc = None
        if not self.forced:
            try:
                rc = proc.wait(timeout=self.kill_timeout)
            except subprocess.TimeoutExpired:
                self.forced = True
        else:
            rc = proc.poll()
        if rc is None and hasattr(proc, "pid"):   # beendeten sudo-Prozess später abholen (kein Zombie)
            threading.Thread(target=lambda: _reap(proc), daemon=True).start()
        self._abandoned = True
        # stdout nur schliessen, wenn der Leser fertig ist (sonst blockiert close beim hängenden Prozess)
        for stream in (proc.stdin,) + ((proc.stdout,) if eof.is_set() else ()):
            try:
                if stream is not None and not stream.closed:
                    stream.close()
            except (OSError, ValueError, AttributeError):
                pass

        error = gone or state["error"]
        if not error and cancel_at is not None and not state["done"]:
            error = FORCED if self.forced else usbguard.CANCELLED
        ok = state["done"] and not error and (rc == 0 or (rc is None and self.forced))
        if not ok and not error:
            error = f"Hilfsprogramm beendet mit Code {rc} (sudo-Regel vorhanden? install.sh)" if rc else \
                "Hilfsprogramm ohne Ergebnis beendet"
        return ok, error
