"""USB-Vorgänge im Tool: Root-Helfer starten, Ausgabe auswerten, zuverlässig abbrechen (B-029).

Gilt für USB klonen, USB formatieren, Agent-USB-Stick (bzw. Restore-Stick) und Boot-Stick aus ISO.

Abbrechen: „CANCEL“ auf stdin und stdin schliessen. Reagiert der Helfer nicht innerhalb von CANCEL_TIMEOUT Sekunden
(z. B. hängt er in I/O auf einen verschwundenen Stick), bekommt die Prozessgruppe von sudo SIGTERM (sudo leitet es
an den Helfer weiter), nach KILL_TIMEOUT SIGKILL. Der Helfer selbst beendet sich bei geschlossenem stdin ebenfalls
(usbguard.watch). Danach ist der Vorgang im Tool immer beendet – auch wenn der Prozess im Kernel noch hängt.

Gerät verschwunden: Das Tool prüft alle PROBE_EVERY Sekunden, ob die Datenträger noch da sind (usbguard.current).

Ä-052: Jeder Vorgang läuft als Auftrag im JobManager des Hauptfensters (Gerät USB_DEVICE, Art KIND, ohne
Geräte-Verlauf) und erscheint in der Auftragsliste „USB-Vorgänge“. Datenträger eines laufenden Vorgangs sind belegt
(in_use) – erkannt an Pfad oder Seriennummer, damit ein umgesteckter Stick belegt bleibt.

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


# ---------- Ä-052: Auftragsliste, belegte Datenträger ----------

USB_DEVICE = "usb"        # Geräte-ID der USB-Vorgänge im JobManager (kein Gerät, kein Verlauf)
KIND = "usb"
IN_USE = "wird gerade verwendet"

_lock = threading.Lock()
_claims: list[tuple["jobs.Job", tuple[Ident, ...]]] = []
_listeners: list[Callable[[], None]] = []
_fallback = None


class Busy(Exception):
    """Ein Datenträger ist schon in einem laufenden USB-Vorgang."""


class UsbFailed(Exception):
    """Ergebnis eines USB-Vorgangs, der nicht fertig wurde (Text wie im Dialog)."""


def manager(owner=None):
    """JobManager des Hauptfensters (owner.jobs) – ohne Hauptfenster ein eigener."""
    from okula_recovery import jobs
    global _fallback
    jm = getattr(owner, "jobs", None)
    if isinstance(jm, jobs.JobManager):
        return jm
    if _fallback is None:
        _fallback = jobs.JobManager()
    return _fallback


def claims() -> list[tuple["jobs.Job", Ident]]:
    """(laufender Auftrag, Datenträger) aller laufenden USB-Vorgänge."""
    with _lock:
        _claims[:] = [(j, ids) for j, ids in _claims if j.running]
        return [(j, i) for j, ids in _claims for i in ids]


def in_use(disk, exclude=None):
    """Laufender USB-Vorgang, der den Datenträger (UsbDisk oder Ident) liest/beschreibt – gleicher Pfad oder gleiche
    Seriennummer. None = frei."""
    path, serial = disk.path, getattr(disk, "serial", "")
    for job, ident in claims():
        if job is exclude:
            continue
        if ident.path == path or (serial and ident.serial == serial):
            return job
    return None


def subscribe(fn: Callable[[], None]) -> None:
    with _lock:
        _listeners.append(fn)


def unsubscribe(fn: Callable[[], None]) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def notify() -> bool:
    """Offene USB-/Stick-Dialoge: belegte Datenträger neu anzeigen (im GTK-Hauptthread aufrufen)."""
    with _lock:
        fns = list(_listeners)
    for fn in fns:
        try:
            fn()
        except Exception:  # ein geschlossenes Fenster darf die anderen nicht stören
            pass
    return False


def log_text(line: str) -> str | None:
    """Zeile des Helfers fürs Auftragslog; DONE/ERROR schreibt der JobManager selbst (Fertig/Fehler)."""
    kind, _, text = line.partition(" ")
    if kind in ("DONE", "ERROR"):
        return None
    if kind == "WARN":
        return "Hinweis: " + text
    if kind == "INFO":
        return text
    return line


def start(jm, title: str, cmd: list[str], stdin_text: str, idents, on_progress, on_line, on_done,
          post: Callable = lambda fn, *a: fn(*a), cwd: str | None = None, runner=HelperProcess):
    """USB-Vorgang als Auftrag starten. Rückrufe des Dialogs kommen über post (GLib.idle_add), on_done genau einmal.
    Busy, wenn ein Datenträger schon verwendet wird."""
    idents = tuple(i for i in idents if i is not None)
    for ident in idents:
        other = in_use(ident)
        if other is not None:
            raise Busy(f"{ident.path} ({ident.text()}) {IN_USE}: {other.title}")

    def work(job, jm_) -> str:
        def progress(frac: float, msg: str) -> None:
            jm_.progress(job, frac, msg)
            post(on_progress, frac, msg)

        def line(text: str) -> None:
            shown = log_text(text)
            if shown:
                jm_.log(job, shown)
            post(on_line, text)

        proc = runner(cmd, stdin_text, cwd=cwd, idents=idents)
        try:
            ok, error = proc.run(job.cancel, progress, line)
        except Exception as e:  # nie ohne Ende
            ok, error = False, str(e)
        post(on_done, ok, error)
        post(notify)
        if not ok:
            raise UsbFailed(error or "fehlgeschlagen")
        return proc.done_text

    key = ",".join(i.path for i in idents) or title
    try:
        job = jm.start(USB_DEVICE, KIND, key, title, work)
    except Exception as e:  # AgentError „Auf … läuft bereits ein Auftrag“
        raise Busy(str(e)) from None
    with _lock:
        _claims.append((job, idents))
    notify()
    return job


def cancel(jm, job) -> None:
    """Abbrechen – aus dem Fenster und aus der Auftragsliste gleich."""
    if job is not None and job.running and not job.cancel.is_set():
        job.cancel.set()
        jm.log(job, "Abbruch angefordert …")


def running(jm) -> list:
    return [j for j in jm.running() if j.kind == KIND]
