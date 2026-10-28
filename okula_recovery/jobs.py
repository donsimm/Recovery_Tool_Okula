"""Aufträge im Hintergrund: Disk-Images und Zurückspielen, mehrere parallel.

Pro Gerät und Disk höchstens ein Auftrag. Jeder Auftrag hat Fortschritt, Log und Abbrechen;
das Ergebnis landet im Verlauf des Geräts. Kein GTK hier – die Oberfläche hängt sich über
on_change ein (wird aus dem Auftrags-Thread aufgerufen).
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from okula_recovery import agentclient, nas

RUNNING, DONE, FAILED, CANCELLED = "läuft", "fertig", "fehlgeschlagen", "abgebrochen"


@dataclass
class Job:
    id: int
    device_id: str
    kind: str              # "image" | "restore"
    disk: str
    title: str
    state: str = RUNNING
    fraction: float = 0.0
    detail: str = ""
    log: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    ended: float | None = None
    result: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)
    phase: str = ""                # Schritt bei mehrstufigen Aufträgen, z. B. „Image prüfen (1/2)“
    phase_fraction: float = 0.0    # Fortschritt innerhalb des Schritts
    phase_started: float = 0.0

    @property
    def running(self) -> bool:
        return self.state == RUNNING

    @property
    def label(self) -> str:
        return self.phase or {"image": "Disk-Image", "install": "Windows-Installation",
                              "linux": "Linux-Installation"}.get(self.kind, "Zurückspielen")

    @property
    def shown_fraction(self) -> float:
        """Was der Balken zeigt: bei Schritten der Fortschritt des aktuellen Schritts (wie am Agent)."""
        return self.phase_fraction if self.phase else self.fraction

    @property
    def remaining(self) -> float | None:
        """Geschätzte Restzeit (des aktuellen Schritts) in Sekunden, None = noch unklar."""
        fraction = self.shown_fraction
        if not self.running or fraction < 0.02:
            return None
        elapsed = time.time() - (self.phase_started if self.phase else self.started)
        if elapsed < 10:
            return None
        return elapsed * (1 - fraction) / fraction


def eta_text(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return "noch < 1 min"
    if seconds < 3600:
        return f"noch {seconds / 60:.0f} min"
    return f"noch {int(seconds // 3600)} h {int(seconds % 3600 // 60):02d} min"


class JobManager:
    def __init__(self, on_change: Callable[[Job], None] = lambda job: None):
        self.on_change = on_change
        self.jobs: list[Job] = []
        self.lock = threading.Lock()
        self._ids = itertools.count(1)

    def for_device(self, device_id: str) -> list[Job]:
        with self.lock:
            return [j for j in self.jobs if j.device_id == device_id]

    def running(self) -> list[Job]:
        with self.lock:
            return [j for j in self.jobs if j.running]

    def summary(self, device_id: str) -> str:
        """Kurzstatus für die Geräteliste, z. B. „Disk-Image 45 % · noch 6 min“."""
        return self.status(device_id)[0]

    def status(self, device_id: str) -> tuple[str, float | None]:
        """(Text, Fortschritt 0..1) der laufenden Aufträge eines Geräts."""
        what, fraction, eta = self.parts(device_id)
        if fraction is None:
            return "", None
        return " · ".join(p for p in (f"{what} {fraction * 100:.0f} %", eta) if p), fraction

    def parts(self, device_id: str) -> tuple[str, float | None, str]:
        """(was läuft, Fortschritt, Restzeit); mehrere Aufträge: Mittelwert und längste Restzeit."""
        active = [j for j in self.running() if j.device_id == device_id]
        if not active:
            return "", None, ""
        rests = [j.remaining for j in active]
        if len(active) == 1:
            return active[0].label, active[0].shown_fraction, eta_text(rests[0])
        return (f"{len(active)} Aufträge", sum(j.fraction for j in active) / len(active),
                eta_text(None if None in rests else max(rests)))

    def start(self, device_id: str, kind: str, disk: str, title: str,
              work: Callable[["Job", "JobManager"], str]) -> Job:
        with self.lock:
            if any(j.running and j.device_id == device_id and j.disk == disk for j in self.jobs):
                raise agentclient.AgentError(f"Auf {disk} läuft bereits ein Auftrag")
            job = Job(next(self._ids), device_id, kind, disk, title)
            self.jobs.append(job)
        self.log(job, f"{title} gestartet")

        def run() -> None:
            try:
                job.result = work(job, self) or ""
                job.state, job.fraction = DONE, 1.0
                self.log(job, f"Fertig{': ' + job.result if job.result else ''}")
            except Exception as e:  # jeder Fehler gehört ins Log des Auftrags
                job.state = CANCELLED if job.cancel.is_set() else FAILED
                self.log(job, f"{'Abgebrochen' if job.cancel.is_set() else 'Fehler'}: {e}")
            finally:
                job.ended = time.time()
                self.on_change(job)

        threading.Thread(target=run, daemon=True, name=f"job-{job.id}").start()
        return job

    def log(self, job: Job, line: str) -> None:
        job.log.append(time.strftime("%H:%M:%S ") + line)
        self.on_change(job)

    def progress(self, job: Job, fraction: float, detail: str, phase: str = "",
                 phase_fraction: float = 0.0) -> None:
        """fraction = Gesamtfortschritt; phase/phase_fraction = aktueller Schritt (Anzeige und Restzeit)."""
        if phase != job.phase:
            job.phase, job.phase_started = phase, time.time()
        job.fraction, job.detail = max(0.0, min(1.0, fraction)), detail
        job.phase_fraction = max(0.0, min(1.0, phase_fraction))
        self.on_change(job)


# ---------- Arbeitsfunktionen (laufen im Auftrags-Thread) ----------

def image_work(ip: str, key: bytes, port: int, disk: dict, nas_root: str, machine: str, source: dict,
               after: Callable[[Job, str | None, Exception | None], None]):
    """Disk-Image erstellen; after(job, pfad, fehler) trägt das Ergebnis ein (Verlauf, Herunterfahren)."""
    sizes = {p["name"]: p["size"] for p in disk["partitions"] if p.get("fstype") != "swap"}
    total = sum(sizes.values()) or 1

    def work(job: Job, jm: JobManager) -> str:
        done_parts: set[str] = set()
        state = {"part": ""}

        def progress(ev: dict) -> None:
            phase = ev.get("phase")
            if phase == "file":
                if state["part"] and state["part"] != ev.get("part"):
                    done_parts.add(state["part"])
                state["part"] = ev.get("part", "")
                jm.log(job, f"Übertrage {ev.get('file')}")
            elif phase == "data":
                part, pct = ev.get("part") or state["part"], ev.get("pct")
                done = sum(sizes.get(p, 0) for p in done_parts)
                if part in sizes and pct is not None:
                    done += sizes[part] * pct / 100
                jm.progress(job, done / total, f"{part or 'Partitionstabelle'} · "
                            f"{nas.format_size(ev.get('total_bytes', 0))} · {ev.get('speed', 0) / 1e6:.0f} MB/s")

        try:
            path = agentclient.create_image(ip, key, disk["path"], nas_root, machine, progress, job.cancel,
                                            port, source)
        except Exception as e:
            after(job, None, e)
            raise
        after(job, str(path), None)
        return str(path)

    return work


def restore_work(ip: str, key: bytes, port: int, image: str, target: str, source_disk: str | None, verify: bool,
                 after: Callable[[Job, str | None, Exception | None], None]):
    def work(job: Job, jm: JobManager) -> str:
        def progress(ev: dict) -> None:
            phase = ev.get("phase")
            if phase == "note":
                jm.log(job, ev.get("message", ""))
            elif phase == "verify":
                f = ev.get("fraction", 0)
                if ev.get("file") and ev["file"] != state["file"]:
                    state["file"] = ev["file"]
                    jm.log(job, f"Prüfe {ev['file']}")
                jm.progress(job, f * 0.3, ev.get("file", ""), "Image prüfen (1/2)", f)
            elif phase == "table":
                jm.log(job, ("Image geprüft. Schritt 2/2: " if verify else "") + "schreibe Partitionstabelle und Bootcode")
                jm.progress(job, 0.3 if verify else 0.0, "Partitionstabelle", "Zurückspielen (2/2)" if verify else "", 0)
            elif phase == "file":
                jm.log(job, f"Schreibe {ev.get('part')} ({ev.get('file')})")
            elif phase == "data":
                # Gesamt: Prüfung = erste 30 %, Schreiben = Rest; angezeigt wird der Schritt
                base = 0.3 if verify else 0.0
                f = ev.get("fraction", 0)
                jm.progress(job, base + (1 - base) * f, f"{ev.get('part')} · {ev.get('speed', 0) / 1e6:.0f} MB/s",
                            "Zurückspielen (2/2)" if verify else "", f)

        state = {"file": ""}
        if verify:
            jm.log(job, "Schritt 1/2: Image auf dem NAS prüfen (Prüfsummen) – danach wird zurückgespielt")

        try:
            agentclient.restore_image(ip, key, image, target, progress, job.cancel, port, verify, source_disk)
        except Exception as e:
            after(job, None, e)
            raise
        after(job, image, None)
        return f"{target} zurückgespielt"

    return work


def install_work(ip: str, key: bytes, port: int, iso: str, index: int, opts, disk: str,
                 after: Callable[[Job, str | None, Exception | None], None]):
    """Windows-Direktinstallation: Übertragen (1/2), Teilen der install.wim (2/2, falls nötig)."""
    from okula_recovery import winsetup, winunattend

    def work(job: Job, jm: JobManager) -> str:
        state = {"files": 0}
        try:
            jm.log(job, "Lese das Windows-Medium auf dem NAS")
            plan = winsetup.plan(iso, index, opts)
        except Exception as e:
            after(job, None, e)
            raise
        for line in winsetup.describe(plan) + winunattend.summary(opts):
            jm.log(job, "  · " + line)
        phase_send = "Übertragen (1/2)" if plan.split else "Übertragen"

        def progress(ev: dict) -> None:
            phase = ev.get("phase")
            if phase == "prepare":
                jm.log(job, f"Agent partitioniert {disk}: EFI · MSR · Windows · Setup-Partition")
            elif phase == "file":
                state["files"] += 1
                if state["files"] == 1:
                    jm.log(job, "Übertrage die Setup-Dateien aus der ISO")
                if ev.get("file", "").lower().startswith("sources/install."):
                    jm.log(job, f"Übertrage {ev['file']}")
            elif phase == "data":
                f = ev.get("fraction", 0)
                jm.progress(job, f * (0.8 if plan.split else 1.0),
                            f"{state['files']}/{len(plan.files)} Dateien · {ev.get('speed', 0) / 1e6:.0f} MB/s",
                            phase_send, f)
            elif phase == "split":
                f = ev.get("fraction", 0)
                if job.phase != "Teilen (2/2)":
                    jm.log(job, "Agent teilt install.wim in install.swm-Teile (FAT32: max. 4 GB je Datei)")
                jm.progress(job, 0.8 + 0.2 * f, "install.swm", "Teilen (2/2)", f)
            elif phase == "done":
                jm.log(job, "Setup-Partition bereit – das Gerät startet in 15 s neu und installiert Windows "
                            "selbständig (Agent-Stick JETZT abziehen)")

        try:
            boot = agentclient.install_windows(ip, key, iso, plan, disk, progress, job.cancel, port)
        except Exception as e:
            after(job, None, e)
            raise
        after(job, boot, None)
        return f"Windows-Installation auf {disk} gestartet (Boot{boot})"

    return work


def linux_install_work(ip: str, key: bytes, port: int, iso: str, meta: dict, disk: str, disk_size: int, opts,
                       after: Callable[[Job, str | None, Exception | None], None]):
    """Linux-Direktinstallation: Bootdateien (und bei Ubuntu die ISO) übertragen, dann Neustart."""
    from okula_recovery import linuxsetup

    def work(job: Job, jm: JobManager) -> str:
        try:
            jm.log(job, "Bereite die Bootdateien vor (aus der ISO" +
                   (", Debian-Netzwerk-Installer von deb.debian.org)" if linuxsetup.kind(meta) == "debian" else ")"))
            plan = linuxsetup.plan(iso, meta, disk, disk_size, opts)
        except Exception as e:
            after(job, None, e)
            raise
        try:
            for line in plan.lines:
                jm.log(job, "  · " + line)
            state = {"files": 0}

            def progress(ev: dict) -> None:
                phase = ev.get("phase")
                if phase == "prepare":
                    jm.log(job, f"Agent partitioniert {disk}: EFI vorne, Platz für das System"
                           + (", Setup-Partitionen am Ende" if len(plan.parts) > 1 else ""))
                elif phase == "file":
                    state["files"] += 1
                    if ev.get("file", "").endswith(".iso"):
                        jm.log(job, f"Übertrage {ev['file']}")
                elif phase == "data":
                    jm.progress(job, ev.get("fraction", 0),
                                f"{state['files']}/{len(plan.files)} Dateien · {ev.get('speed', 0) / 1e6:.0f} MB/s")
                elif phase == "done":
                    jm.log(job, "Vorbereitet – das Gerät startet in 15 s neu und installiert selbständig "
                                "(Agent-Stick JETZT abziehen)")

            boot = agentclient.bootprep(ip, key, plan, disk, progress, job.cancel, port)
        except Exception as e:
            after(job, None, e)
            raise
        finally:
            plan.cleanup()
        after(job, boot, None)
        return f"Linux-Installation auf {disk} gestartet (Boot{boot})"

    return work
