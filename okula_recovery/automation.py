"""Automatisierung: erfasste Geräte mit eingeschalteter Automatisierung werden neu aufgesetzt, sobald sie im LAN
auftauchen (Agent-Stick oder Netzwerkstart).

Ablauf pro Gerät: 30 s Countdown (im Tool und am Gerät, Esc bricht ab) → Warteschlange (höchstens N gleichzeitig)
→ 1 Backup (Option) → 2 Image zurückspielen (Master oder eigenes) → 3 Anpassen (Name, Key; immer)
→ 4 Ordner senden (Option) → 5 Abschluss (Neustart / Herunterfahren / nichts).

Läuft einmal: nach Erfolg schaltet sich die Automatisierung aus und – falls „Nach 24 h wieder einschalten“ an ist
(Standard) – 24 h später wieder ein. Bei einem Fehler wird abgebrochen; das Gerät bleibt im normalen
Agent-Betrieb, der Fehler steht überall (Übersicht, Gerätefenster, Verlauf, Bildschirm des Geräts).
Ein neuer Versuch erst, wenn das Gerät neu angeschlossen wird. Kein GTK hier.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Callable

from okula_recovery import agentclient, config, distribute, jobs, nas

COUNTDOWN = 30
REARM_HOURS = 24
STEPS = ("Backup", "Image zurückspielen", "Anpassen", "Ordner senden", "Abschluss")
FINISH = {"reboot": "Neustart", "poweroff": "Herunterfahren", "none": "nichts"}
# Gesamtfortschritt: Anteil der Schritte (Zurückspielen dauert am längsten)
WEIGHTS = (0.15, 0.65, 0.03, 0.14, 0.03)


class AutomationError(Exception):
    pass


@dataclass
class Settings:
    enabled: bool = False
    rearm: bool = True               # nach erfolgreichem Durchlauf 24 h später wieder einschalten
    backup: bool = False             # 1: vorher sichern
    backup_mode: str = "files"       #    files (Benutzerdaten) | image (ganze Disk als Disk-Image)
    image_mode: str = "master"       # 2: master | own
    image: str = ""                  #    Image-Pfad relativ zum NAS
    adapt_smaller: bool = True       #    Zieldisk kleiner: Image dafür anpassen (Ä-002)
    source_disk: str = ""            #    Clonezilla: welche Disk aus dem Image (leer = erste)
    disk_key: str = ""               #    Zieldisk (Seriennummer, sonst Modell|Grösse)
    disk_label: str = ""             #    Anzeige, z. B. „Samsung SSD 256 GB (S6ABC123)“
    swiss: bool = True               # 3: Region Schweiz
    account: str = ""                #    lokales Konto (Passwort beim ersten Anmelden), leer = Windows fragt
    software: bool = False           # 4: Ordner senden
    testfiles: bool = False
    projects: list[str] = field(default_factory=list)
    finish: str = "reboot"           # 5: reboot | poweroff | none
    template: str = ""               # zuletzt angewendete Vorlage (nur Anzeige)
    done_at: str = ""                # letzter erfolgreicher Durchlauf (ISO)
    last_error: str = ""

    @classmethod
    def from_dict(cls, data: dict | None) -> "Settings":
        names = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in (data or {}).items() if k in names})
        s.projects = [str(p) for p in s.projects or [] if p]
        if s.image_mode not in ("master", "own"):
            s.image_mode = "master"
        if s.finish not in FINISH:
            s.finish = "reboot"
        if s.backup_mode not in ("files", "image"):
            s.backup_mode = "files"
        return s

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def items(self) -> list[str]:
        return distribute.items_for(self.software, self.testfiles, self.projects)


# Was eine Vorlage enthält (ohne gerätebezogene Werte wie Zieldisk und Zustand)
TEMPLATE_FIELDS = ("rearm", "backup", "backup_mode", "image_mode", "image", "adapt_smaller", "source_disk", "swiss", "account", "software",
                   "testfiles", "projects", "finish")


def settings(dev) -> Settings:
    return Settings.from_dict(getattr(dev, "automation", None))


def disk_key(disk: dict) -> str:
    serial = (disk.get("serial") or "").strip()
    return serial or f"{(disk.get('model') or '').strip()}|{int(disk.get('size') or 0)}"


def disk_label(disk: dict) -> str:
    size = int(disk.get("size") or 0) / 1000**3
    serial = (disk.get("serial") or "").strip()
    return f"{disk.get('model') or disk.get('name') or 'Disk'} {size:.0f} GB" + (f" ({serial})" if serial else "")


def find_disk(disks: list[dict], key: str) -> dict | None:
    return next((d for d in disks if key and disk_key(d) == key), None)


def image_path(nas_root: str | Path, rel: str) -> Path:
    p = PurePosixPath(rel)
    if not rel or p.is_absolute() or ".." in p.parts:
        raise AutomationError(f"Ungültiger Image-Pfad: {rel or '(keiner)'}")
    return Path(nas_root).joinpath(*p.parts)


def problems(s: Settings, nas_root: str | Path | None) -> list[str]:
    """Was fehlt, damit die Automatisierung laufen kann (leer = bereit)."""
    out = []
    if not s.image:
        out.append("Kein Image gewählt")
    elif nas_root:
        try:
            path = image_path(nas_root, s.image)
            if not path.exists():
                out.append(f"Image nicht gefunden: {s.image}")
            elif s.image_mode == "master" and not nas.is_master(path):
                out.append(f"Image ist nicht (mehr) als Master markiert: {s.image}")
        except AutomationError as e:
            out.append(str(e))
    if not nas_root:
        out.append("NAS nicht verbunden")
    if not s.disk_key:
        out.append("Keine Zieldisk gewählt")
    return out


def rearm_at(s: Settings) -> datetime | None:
    if s.enabled or not s.rearm or not s.done_at:
        return None
    try:
        return datetime.fromisoformat(s.done_at) + timedelta(hours=REARM_HOURS)
    except ValueError:
        return None


def rearm_text(s: Settings, now: datetime | None = None) -> str:
    """„wieder aktiv in 5 h“ – leer, wenn nichts ansteht."""
    at = rearm_at(s)
    if at is None:
        return ""
    left = (at - (now or datetime.now())).total_seconds()
    if left <= 0:
        return "wird wieder eingeschaltet"
    if left < 3600:
        return f"wieder aktiv in {max(1, math.ceil(left / 60))} min"
    return f"wieder aktiv in {math.ceil(left / 3600)} h"


# ---------- Vorlagen ----------

def templates_path() -> Path:
    return config.config_path().parent / "automatisierung-vorlagen.json"


def load_templates() -> dict[str, dict]:
    try:
        data = json.loads(templates_path().read_text())
    except (OSError, ValueError):
        return {}
    return {str(k): {f: v[f] for f in TEMPLATE_FIELDS if f in v} for k, v in data.items() if isinstance(v, dict)}


def _save_templates(data: dict[str, dict]) -> None:
    path = templates_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


def save_template(name: str, s: Settings) -> None:
    name = name.strip()
    if not name:
        raise AutomationError("Vorlage braucht einen Namen")
    data = load_templates()
    data[name] = {f: getattr(s, f) for f in TEMPLATE_FIELDS}
    _save_templates(data)


def delete_template(name: str) -> None:
    data = load_templates()
    data.pop(name, None)
    _save_templates(data)


def apply_template(s: Settings, name: str) -> Settings:
    tpl = load_templates().get(name)
    if tpl is None:
        raise AutomationError(f"Vorlage „{name}“ gibt es nicht")
    merged = Settings.from_dict({**s.to_dict(), **tpl, "template": name})
    return merged


# ---------- Ablauf ----------

@dataclass
class Run:
    phase: str                     # countdown | waiting | running | done | error | cancelled
    left: int = COUNTDOWN
    position: int = 0
    text: str = ""
    job: jobs.Job | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    @property
    def active(self) -> bool:
        return self.phase in ("countdown", "waiting", "running")


def run_text(run: Run | None, s: Settings, paused: bool, ready: bool, now: datetime | None = None) -> str:
    """Kurzer Status für die Übersicht (leer = nichts zu zeigen)."""
    if run is not None:
        if run.phase == "countdown":
            return f"Automatisierung startet in {run.left} s"
        if run.phase == "waiting":
            return f"Automatisierung wartet (Platz {run.position} in der Warteschlange)"
        if run.phase == "running":
            return ""   # Fortschritt kommt vom Auftrag („Schritt 2/5: Image zurückspielen 45 %“)
        if run.phase == "done":
            return "Automatisierung fertig"
        if run.phase == "error":
            return "Automatisierung: Fehler – Gerät neu anschliessen"
        if run.phase == "cancelled":
            return run.text or "Automatisierung abgebrochen"
    if s.enabled and paused:
        return "Automatisierung pausiert"
    if s.enabled and not ready:
        return "Automatisierung: Einstellungen unvollständig"
    if s.enabled:
        return "Automatisierung ein" + (" – letzter Versuch fehlgeschlagen" if s.last_error else "")
    return rearm_text(s, now)


class Engine:
    """Steuert alle Automatisierungen. on_change(device_id) wird aus Threads aufgerufen (UI: idle_add)."""

    def __init__(self, store, job_manager: jobs.JobManager, key: bytes, nas_root: Callable[[], str | None],
                 cfg: Callable[[], config.Config], on_change: Callable[[str], None] = lambda dev_id: None):
        self.store, self.jobs, self.key = store, job_manager, key
        self.nas_root, self.cfg, self.on_change = nas_root, cfg, on_change
        self.runs: dict[str, Run] = {}
        self.queue: list[str] = []
        self.running = 0
        self.cond = threading.Condition()
        self.countdown_seconds = COUNTDOWN

    # --- Abfragen ---

    def run(self, dev_id: str) -> Run | None:
        return self.runs.get(dev_id)

    def text(self, dev, now: datetime | None = None) -> str:
        s = settings(dev)
        return run_text(self.runs.get(dev.id), s, self.cfg().automation_paused,
                        not problems(s, self.nas_root()), now)

    # --- Ereignisse ---

    def consider(self, dev, agent) -> bool:
        """Gerät ist (wieder) im LAN: Automatisierung starten, falls an und bereit. True = gestartet."""
        s = settings(dev)
        if not s.enabled or self.cfg().automation_paused or not getattr(agent, "control_port", 0):
            return False
        if dev.id in self.runs or self.jobs.summary(dev.id) or problems(s, self.nas_root()):
            return False  # läuft schon, ist erledigt/abgebrochen (bis neu angeschlossen) oder unvollständig
        run = Run("countdown", left=self.countdown_seconds)
        self.runs[dev.id] = run
        self.on_change(dev.id)
        threading.Thread(target=self._run, args=(dev, agent, run), daemon=True,
                         name=f"auto-{dev.id}").start()
        return True

    def offline(self, dev_id: str) -> None:
        """Gerät getrennt: abgeschlossene/abgebrochene Läufe vergessen – beim nächsten Anschliessen neu."""
        run = self.runs.get(dev_id)
        if run is not None and not run.active:
            del self.runs[dev_id]
            self.on_change(dev_id)

    def cancel(self, dev_id: str) -> None:
        run = self.runs.get(dev_id)
        if run is None or not run.active:
            return
        run.cancel.set()
        if run.job is not None:
            run.job.cancel.set()
        with self.cond:
            self.cond.notify_all()

    def tick(self, now: datetime | None = None) -> list:
        """Regelmässig aufrufen: nach 24 h wieder einschalten. Gibt die wieder eingeschalteten Geräte zurück."""
        now = now or datetime.now()
        back = []
        for dev in list(self.store.devices.values()):
            s = settings(dev)
            at = rearm_at(s)
            if at is not None and at <= now:
                s.enabled = True
                self._save(dev, s)
                self.store.add_history(dev, "automatisierung", "Automatisierung nach 24 h wieder eingeschaltet")
                self.runs.pop(dev.id, None)
                back.append(dev)
                self.on_change(dev.id)
        return back

    # --- Ablauf im Thread ---

    def _save(self, dev, s: Settings) -> None:
        dev.automation = s.to_dict()
        self.store.save(dev)

    def _run(self, dev, agent, run: Run) -> None:
        def tick(left: int) -> None:
            if left != run.left:
                run.left = left
                self.on_change(dev.id)

        try:
            result = agentclient.countdown(agent.ip, self.key, self.countdown_seconds,
                                           f"Automatisierung für {dev.name}", run.cancel, tick, agent.control_port)
        except Exception as e:  # Countdown darf nie den Ablauf ohne Meldung beenden
            result = "tool"
            run.text = f"Automatisierung abgebrochen: {e}"
        if result != "start":
            run.phase = "cancelled"
            run.text = run.text or ("Automatisierung am Gerät mit Esc abgebrochen" if result == "esc"
                                    else "Automatisierung im Tool abgebrochen")
            self.store.add_history(dev, "automatisierung", run.text, ok=None)
            self.on_change(dev.id)
            return
        if not self._wait_slot(dev, run):
            run.phase, run.text = "cancelled", "Automatisierung im Tool abgebrochen (Warteschlange)"
            self.store.add_history(dev, "automatisierung", run.text, ok=None)
            self.on_change(dev.id)
            return
        try:
            self._execute(dev, agent, run)
        finally:
            with self.cond:
                self.running -= 1
                self.cond.notify_all()
            self._update_positions()

    def _update_positions(self) -> None:
        with self.cond:
            for i, dev_id in enumerate(self.queue, 1):
                run = self.runs.get(dev_id)
                if run is not None and run.position != i:
                    run.position = i
                    self.on_change(dev_id)

    def _wait_slot(self, dev, run: Run) -> bool:
        with self.cond:
            self.queue.append(dev.id)
            run.phase = "waiting"
        self._update_positions()
        self.on_change(dev.id)
        with self.cond:
            while True:
                if run.cancel.is_set():
                    self.queue.remove(dev.id)
                    break
                limit = max(1, int(self.cfg().automation_max or 1))
                if self.queue[0] == dev.id and self.running < limit:
                    self.queue.pop(0)
                    self.running += 1
                    run.phase = "running"
                    break
                self.cond.wait(timeout=1.0)
        self._update_positions()
        self.on_change(dev.id)
        return run.phase == "running"

    def _execute(self, dev, agent, run: Run) -> None:
        s = settings(dev)
        error: dict = {}
        finished = threading.Event()
        work = automation_work(agent.ip, self.key, agent.control_port, dev, s, self.nas_root(), error)

        def wrapped(job, jm):
            try:
                return work(job, jm)
            finally:
                finished.set()

        try:
            run.job = self.jobs.start(dev.id, "auto", "automatisierung", f"Automatisierung ({dev.name})", wrapped)
        except agentclient.AgentError as e:
            error["message"] = str(e)
            finished.set()
        self.on_change(dev.id)
        finished.wait()
        while run.job is not None and run.job.running:
            time.sleep(0.05)  # JobManager trägt den Endzustand gleich danach ein
        if run.job is not None and run.job.state == jobs.DONE:
            s = settings(dev)
            s.enabled, s.done_at, s.last_error = False, datetime.now().isoformat(timespec="seconds"), ""
            self._save(dev, s)
            run.phase = "done"
            self.store.add_history(dev, "automatisierung", "Automatisierung erfolgreich" +
                                   (" – wird in 24 h wieder eingeschaltet" if s.rearm else ""), ok=True)
        else:
            message = error.get("message") or (run.job.log[-1].split(" ", 1)[-1] if run.job and run.job.log
                                               else "unbekannter Fehler")
            if run.cancel.is_set():
                message = "im Tool abgebrochen"
            s = settings(dev)
            s.last_error = f"{error.get('step', '')}: {message}".strip(": ")
            self._save(dev, s)
            run.phase, run.text = "error", s.last_error
            self.store.add_history(dev, "automatisierung", f"Automatisierung fehlgeschlagen – {s.last_error}",
                                   ok=False)
            shown = agentclient.banner(agent.ip, self.key, [f"Automatisierung fehlgeschlagen: {s.last_error}",
                                                            "Das Gerät bleibt im normalen Agent-Betrieb.",
                                                            "Für einen neuen Versuch: Gerät neu starten bzw. neu "
                                                            "anschliessen."], True, agent.control_port)
            if not shown:
                run.text += " (Meldung am Gerät nicht möglich)"
        self.on_change(dev.id)


def automation_work(ip: str, key: bytes, port: int, dev, s: Settings, nas_root: str | None, error: dict):
    """Die fünf Schritte als Auftrag (läuft im Auftrags-Thread). error bekommt Schritt und Meldung."""
    from okula_recovery import backups, linuxsetup, winunattend

    def work(job: jobs.Job, jm: jobs.JobManager) -> str:
        done_weight = 0.0

        def step(i: int, fraction: float, detail: str = "") -> None:
            jm.progress(job, done_weight + WEIGHTS[i] * fraction, detail, f"Schritt {i + 1}/5: {STEPS[i]}",
                        fraction)

        current = {"i": 0}

        def begin(i: int, text: str) -> None:
            nonlocal done_weight
            done_weight = sum(WEIGHTS[:i])
            current["i"] = i
            jm.log(job, f"Schritt {i + 1}/5 – {STEPS[i]}: {text}")
            step(i, 0.0)

        try:
            if not nas_root:
                raise AutomationError("NAS nicht verbunden")
            image = image_path(nas_root, s.image)
            if not image.exists():
                raise AutomationError(f"Image nicht gefunden: {s.image}")
            info = agentclient.get_info(ip, key, port)
            disk = find_disk(info.get("disks") or [], s.disk_key)
            if disk is None:
                raise AutomationError(f"Zieldisk {s.disk_label or s.disk_key} nicht im Gerät gefunden – "
                                      "nichts gelöscht")
            target = disk["path"]
            jm.log(job, f"Zieldisk {disk_label(disk)} = {target}")

            # 1 Backup
            if s.backup and s.backup_mode == "image":
                begin(0, "ganze Disk sichern (Disk-Image aufs NAS)")
                sizes = {p["name"]: int(p.get("size") or 0) for p in disk.get("partitions") or []
                         if p.get("fstype") != "swap"}
                total = sum(sizes.values()) or 1
                state = {"part": "", "done": set()}

                def image_progress(ev: dict) -> None:
                    if ev.get("phase") == "file":
                        if state["part"] and state["part"] != ev.get("part"):
                            state["done"].add(state["part"])
                        state["part"] = ev.get("part", "")
                    elif ev.get("phase") == "data":
                        part, pct = ev.get("part") or state["part"], ev.get("pct")
                        done = sum(sizes.get(p, 0) for p in state["done"])
                        if part in sizes and pct is not None:
                            done += sizes[part] * pct / 100
                        step(0, done / total, f"{part or 'Partitionstabelle'} · {ev.get('speed', 0) / 1e6:.0f} MB/s")

                source = {"device_id": dev.id, "device_name": dev.name, "note": "Automatisierung – vor dem Zurückspielen"}
                path = agentclient.create_image(ip, key, target, nas_root, dev.name, image_progress, job.cancel, port,
                                                source)
                jm.log(job, f"  Disk-Image: {path}")
            elif s.backup:
                begin(0, "Benutzerdaten sichern")
                sources, users = [], []
                for p in backups.get_profiles(ip, key, port):
                    if p.get("disk") != target:
                        continue
                    for u in p.get("users") or []:
                        sources += backups.profile_sources(p["part"], u["path"], p.get("kind", ""),
                                                           list(backups.DEFAULT_CATEGORIES))
                        users.append(u["name"])
                if sources:
                    description = backups.describe_selection("profiles", users, "files")
                    path = backups.run_backup(
                        ip, key, port, target, sources, nas_root, {"id": dev.id, "name": dev.name}, "profiles",
                        "files", description,
                        lambda ev: step(0, ev.get("fraction", 0)) if ev.get("phase") == "data" else None,
                        job.cancel, note="Automatisierung – vor dem Zurückspielen")
                    jm.log(job, f"  Backup: {path}")
                else:
                    jm.log(job, "  Keine Benutzerprofile auf der Zieldisk – nichts zu sichern")
            else:
                jm.log(job, "Schritt 1/5 – Backup: aus")

            # 2 Image zurückspielen (prüft zuerst die Prüfsummen, erst dann wird gelöscht)
            begin(1, f"{s.image} → {target}")
            src = agentclient.image_source(image, s.source_disk or None)
            need = int((src.get("source") or {}).get("size") or 0)
            source_disk = s.source_disk or None
            if need and int(disk.get("size") or 0) and need > int(disk["size"]):
                if not s.adapt_smaller:
                    raise AutomationError(f"Image ({need / 1000**3:.0f} GB) passt nicht auf die Zieldisk "
                                          f"({int(disk['size']) / 1000**3:.0f} GB) – nichts gelöscht")
                from okula_recovery import shrink
                try:
                    shrink_plan = shrink.plan(image, int(disk["size"]), source_disk)
                except shrink.ShrinkError as e:
                    raise AutomationError(f"Image passt nicht auf die Zieldisk und lässt sich nicht anpassen: {e} "
                                          "– nichts gelöscht") from None
                jm.log(job, "  Zieldisk ist kleiner – Image wird angepasst (neues Image, Original bleibt):")
                for line in shrink_plan.lines():
                    jm.log(job, "    · " + line)
                image = shrink.create(shrink_plan, nas_root,
                                      lambda ev: step(1, 0.15 * ev.get("fraction", 0), "Image anpassen"),
                                      job.cancel)
                source_disk = None
                jm.log(job, f"  Angepasstes Image: {image.name}")

            def restore_progress(ev: dict) -> None:
                if ev.get("phase") == "verify":
                    step(1, 0.3 * ev.get("fraction", 0), "Image prüfen")
                elif ev.get("phase") == "data":
                    step(1, 0.3 + 0.7 * ev.get("fraction", 0), f"{ev.get('part')} · "
                         f"{ev.get('speed', 0) / 1e6:.0f} MB/s")

            agentclient.restore_image(ip, key, image, target, restore_progress, job.cancel, port, True,
                                      source_disk)

            # 3 Anpassen (immer)
            begin(2, f"Name „{dev.name}“" + (", Windows-Key" if dev.windows_key[0] else ""))
            xml = winunattend.master_unattend(dev.name, dev.windows_key[0], s.swiss, s.account)
            for r in agentclient.customize(ip, key, target, xml, linuxsetup.hostname(dev.name), port):
                what = {"unattend": f"Windows (Master): Name {winunattend.computer_name(dev.name)}"
                                    + (", Key gesetzt" if dev.windows_key[0] else "") + " – richtet sich beim "
                                    "ersten Start ein",
                        "hostname": f"Linux: Hostname {linuxsetup.hostname(dev.name)}",
                        "not_generalized": "Windows ist nicht mit Sysprep vorbereitet – Name und Key NICHT gesetzt "
                                           "(Master-Image mit Sysprep erstellen)",
                        "none": "nichts zu tun", "error": r.get("detail", "Fehler")}.get(r["action"], r["action"])
                jm.log(job, f"  {r['part']}: {what}")

            # 4 Ordner senden
            if s.items:
                begin(3, distribute.describe(s.items))
                plan = distribute.plan(nas_root, s.items)
                if plan.missing:
                    jm.log(job, f"  Fehlt auf dem NAS (übersprungen): {', '.join(plan.missing)}")
                agentclient.deliver(ip, key, target, plan.items, plan.entries, plan.bytes,
                                    lambda ev: step(3, ev.get("fraction", 0)) if ev.get("phase") == "data" else None,
                                    job.cancel, port)
                jm.log(job, f"  {plan.files} Dateien auf den Desktop gelegt")
            else:
                jm.log(job, "Schritt 4/5 – Ordner senden: aus")

            # 5 Abschluss
            begin(4, FINISH[s.finish])
            agentclient.banner(ip, key, [f"Automatisierung fertig ({dev.name})",
                                         {"reboot": "Neustart in 10 s – Agent-Stick abziehen",
                                          "poweroff": "Gerät wird in 10 s ausgeschaltet",
                                          "none": "Gerät bleibt eingeschaltet"}[s.finish]], False, port)
            if s.finish != "none":
                agentclient.power(ip, key, s.finish, port, delay=10)
            step(4, 1.0)
            return "Automatisierung fertig"
        except Exception as e:
            error["step"] = f"Schritt {current['i'] + 1}/5 {STEPS[current['i']]}" if job.phase else "Vorbereitung"
            error["message"] = str(e)
            raise

    return work
