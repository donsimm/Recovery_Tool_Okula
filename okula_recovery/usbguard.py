"""B-029: Schutz der USB-Vorgänge (USB klonen, USB formatieren, Agent-USB-Stick, Boot-Stick).

Identität statt Gerätename: Beim Start hält das Tool je Datenträger Seriennummer, Modell und Grösse fest und gibt
sie dem Root-Helfer mit (--ident). Der Helfer prüft vor dem ersten Schreiben und bei jedem neuen Öffnen, dass
/dev/sdX noch derselbe Datenträger ist – nach einem Wackelkontakt bekommen Sticks oft andere Namen. Passt es nicht,
bricht er ab, bevor etwas geschrieben wird.

Gerät verschwunden: Ein Wächter-Thread prüft alle 2 s, ob die Datenträger noch da sind (Grösse > 0). Fehlt einer
zweimal hintereinander, bricht der Helfer ab („Datenträger getrennt – abgebrochen (…)“).

Abbrechen: Zeile „CANCEL“ auf stdin oder stdin geschlossen (Tool beendet) → SIGTERM an sich selbst (Cancelled).
Hängt der Helfer danach (z. B. in I/O auf ein verschwundenes Gerät), beendet der Wächter nach GRACE Sekunden die
eigenen Unterprozesse (nur Nachfahren des Helfers) und den Helfer selbst.

Ohne GTK; current()/check() laufen auch ohne root (Tool).
"""

from __future__ import annotations

import errno
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from okula_recovery.stick import StickError

GRACE = 10.0            # s nach Abbruch, bis der Helfer sich selbst hart beendet
WATCH_EVERY = 2.0       # s zwischen zwei Prüfungen, ob die Datenträger noch da sind
GONE_MISSES = 2         # so oft hintereinander fehlend = getrennt (kurze udev-Lücken nicht werten)
UNPLUG_ERRNOS = (errno.EIO, errno.ENODEV, errno.ENXIO, errno.ENOENT)
INCOMPLETE = "Ziel ist unvollständig und muss neu beschrieben werden"
CANCELLED = "Abgebrochen – der Ziel-Datenträger ist unvollständig und muss neu beschrieben werden"


class Cancelled(Exception):
    """Abbruch (CANCEL, stdin zu, SIGTERM oder Datenträger getrennt) – Grund in reason()."""


class DiskGone(StickError):
    pass


class WrongDisk(StickError):
    pass


@dataclass(frozen=True)
class Ident:
    """Datenträger, wie er beim Start gewählt wurde."""
    path: str
    serial: str = ""
    model: str = ""
    size: int = 0

    def text(self) -> str:
        """„SanDisk Cruzer Blade, SN 4C530001“ – für Meldungen."""
        parts = [self.model or self.path]
        if self.serial:
            parts.append(f"SN {self.serial}")
        return ", ".join(parts)

    def arg(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def parse(cls, text: str) -> "Ident":
        try:
            d = json.loads(text)
            return cls(str(d["path"]), str(d.get("serial") or ""), str(d.get("model") or ""), int(d.get("size") or 0))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError(f"--ident ungültig: {text}") from None


def short_serial(serial: str) -> str:
    """Kurzform für die Auswahlliste: die letzten 8 Zeichen („…4C530001“)."""
    serial = serial.strip()
    return serial if len(serial) <= 10 else "…" + serial[-8:]


def gone_message(ident: Ident, target: bool = True) -> str:
    return f"Datenträger getrennt – abgebrochen ({ident.text()})" + (f" – {INCOMPLETE}" if target else "")


def _sys_size(path: str) -> int | None:
    """Grösse aus /sys (Byte); None = Gerät gibt es nicht."""
    try:
        name = Path(os.path.realpath(path)).name
        return int(Path(f"/sys/class/block/{name}/size").read_text().strip()) * 512
    except (OSError, ValueError):
        return None


def current(path: str) -> Ident | None:
    """Was jetzt unter path steckt; None = nicht (mehr) vorhanden. Seriennummer/Modell aus lsblk (udev)."""
    if not Path(path).exists():
        return None
    size = _sys_size(path)
    if size is None:
        return None
    serial = model = ""
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-d", "-o", "PATH,SERIAL,MODEL,VENDOR,SIZE", path],
                             capture_output=True, text=True, timeout=10).stdout
        dev = (json.loads(out).get("blockdevices") or [{}])[0]
        serial = (dev.get("serial") or "").strip()
        model = " ".join(p for p in ((dev.get("vendor") or "").strip(), (dev.get("model") or "").strip()) if p)
    except (OSError, ValueError, subprocess.TimeoutExpired, IndexError, AttributeError):
        pass
    return Ident(path, serial, model, size)


Probe = Callable[[str], "Ident | None"]


def _probe(probe: Probe | None) -> Probe:
    return probe or current        # erst beim Aufruf auflösen (Tests ersetzen current)


def check(want: Ident, probe: Probe | None = None, target: bool = True,
          settle: Callable[[], None] | None = None) -> None:
    """Ist unter want.path noch derselbe Datenträger? DiskGone (weg/Grösse 0) bzw. WrongDisk (anderer)."""
    probe = _probe(probe)
    now = probe(want.path)
    if now is None or now.size == 0:
        raise DiskGone(gone_message(want, target))
    if want.serial and not now.serial and settle is not None:
        settle()                                   # udev noch nicht fertig: einmal warten
        now = probe(want.path) or now
    if want.serial:
        same = now.serial == want.serial
    else:
        same = not want.size or now.size == want.size
    if not same:
        found = now.text() if now.serial or now.model else f"{now.size / 1000**3:.1f} GB"
        raise WrongDisk(f"{want.path} ist nicht mehr derselbe Datenträger (erwartet {want.text()}, gefunden "
                        f"{found}) – abgebrochen, nichts geschrieben. Datenträger neu suchen und neu starten.")


def _settle() -> None:
    subprocess.run(["udevadm", "settle", "--timeout=5"], capture_output=True)


# ---------- im Root-Helfer ----------

_lock = threading.Lock()
_guarded: list[tuple[Ident, bool]] = []      # (Datenträger, wird beschrieben)
_reason: list[str] = []                      # erster Abbruchgrund


def guard(idents: list[Ident], targets: set[str] | None = None) -> None:
    """Diese Datenträger überwachen; targets = Pfade, die beschrieben werden (Meldung „Ziel unvollständig“)."""
    with _lock:
        _guarded[:] = [(i, targets is None or i.path in targets) for i in idents]


def guarded() -> list[Ident]:
    with _lock:
        return [i for i, _t in _guarded]


def idents_for(paths: list[str], given: list[str] | None, probe: Probe | None = None) -> list[Ident]:
    """--ident vom Tool; fehlt es (Aufruf von Hand), gilt der Datenträger beim Start des Helfers."""
    probe = _probe(probe)
    known = {i.path: i for i in (Ident.parse(t) for t in given or [])}
    result = []
    for p in paths:
        if p in known:
            result.append(known[p])
        else:
            now = probe(p)
            if now is not None:
                result.append(now)
    return result


def _belongs(path: str, disk: str) -> bool:
    """/dev/sdb1, /dev/nvme0n1p2 gehören zu /dev/sdb bzw. /dev/nvme0n1."""
    if path == disk:
        return True
    rest = path[len(disk):] if path.startswith(disk) else None
    return rest is not None and re.fullmatch(r"p?\d+", rest) is not None


def check_path(path: str, probe: Probe | None = None) -> None:
    for ident, target in list(_guarded):
        if _belongs(path, ident.path):
            check(ident, probe, target, _settle)


def check_all(probe: Probe | None = None) -> None:
    for ident, target in list(_guarded):
        check(ident, probe, target, _settle)


def check_args(cmd: list[str], probe: Probe | None = None) -> None:
    """Vor jedem Programmaufruf auf einen überwachten Datenträger (sfdisk, mkfs, partclone, mount …)."""
    if not _guarded:
        return
    for arg in cmd:
        if isinstance(arg, str) and arg.startswith("/dev/"):
            check_path(arg, probe)


def open_dev(path: str, flags: int) -> int:
    """os.open mit Identitätsprüfung; E/A-Fehler beim Öffnen eines getrennten Datenträgers → DiskGone."""
    check_path(path)
    try:
        return os.open(path, flags)
    except OSError as e:
        raise explain(e) from None


def explain(exc: BaseException, probe: Probe | None = None) -> BaseException:
    """Fehler beim Lesen/Schreiben: DiskGone, wenn ein überwachter Datenträger weg ist, sonst exc selbst."""
    probe = _probe(probe)
    if isinstance(exc, (DiskGone, WrongDisk)):
        return exc
    io = (isinstance(exc, OSError) and exc.errno in UNPLUG_ERRNOS) or \
        any(t in str(exc) for t in ("Input/output error", "Eingabe-/Ausgabefehler", "No such device",
                                    "Kein passendes Gerät", "No medium found"))
    for ident, target in list(_guarded):
        now = probe(ident.path)
        if now is None or now.size == 0 or (io and ident.serial and now.serial and now.serial != ident.serial):
            return DiskGone(gone_message(ident, target))
    return exc


def reason() -> str:
    return _reason[0] if _reason else CANCELLED


def reset() -> None:
    """Zustand zurücksetzen (Tests)."""
    with _lock:
        _guarded.clear()
        _reason.clear()


def _descendants(pid: int) -> list[int]:
    """Alle Nachfahren von pid (aus /proc) – beim harten Beenden nur eigene Kinder treffen."""
    children: dict[int, list[int]] = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            text = Path(f"/proc/{d}/stat").read_text()
            ppid = int(text.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(int(d))
    out, todo = [], [pid]
    while todo:
        for c in children.get(todo.pop(), []):
            out.append(c)
            todo.append(c)
    return out


def request_stop(why: str, emit: Callable[[str, str], None] | None = None, grace: float = GRACE,
                 kill: Callable[[int, int], None] = os.kill, exit_: Callable[[int], None] = os._exit) -> None:
    """Abbruch auslösen: SIGTERM an sich selbst (→ Cancelled im Hauptthread). Reagiert der Helfer nicht innerhalb
    von grace Sekunden (I/O hängt), eigene Unterprozesse und sich selbst hart beenden."""
    with _lock:
        if _reason:
            return
        _reason.append(why)
    kill(os.getpid(), signal.SIGTERM)

    def hard() -> None:
        for pid in reversed(_descendants(os.getpid())):
            try:
                kill(pid, signal.SIGKILL)
            except OSError:
                pass
        if emit is not None:
            try:
                emit("ERROR", why + " (Hilfsprogramm hart beendet)")
            except (OSError, ValueError):
                pass
        exit_(1)

    timer = threading.Timer(grace, hard)
    timer.daemon = True
    timer.start()


def watch(emit: Callable[[str, str], None] | None = None, stdin=None, every: float = WATCH_EVERY,
          probe: Probe | None = None) -> None:
    """Wächter starten: stdin („CANCEL“/EOF) und Datenträger (getrennt?). Erst nach dem Lesen von Schlüssel bzw.
    autounattend.xml aufrufen – der Wächter liest stdin bis zum Ende."""
    stdin = sys.stdin if stdin is None else stdin
    probe = _probe(probe)

    def read() -> None:
        for line in stdin:
            if line.strip() == "CANCEL":
                request_stop(CANCELLED, emit)
                return
        if _is_pipe(stdin):      # Tool hat stdin geschlossen oder ist beendet worden
            request_stop(CANCELLED, emit)

    def monitor() -> None:
        misses: dict[str, int] = {}
        while not _reason:
            time.sleep(every)
            with _lock:
                items = list(_guarded)
            for ident, target in items:
                now = probe(ident.path)
                if now is None or now.size == 0:
                    misses[ident.path] = misses.get(ident.path, 0) + 1
                    if misses[ident.path] >= GONE_MISSES:
                        request_stop(gone_message(ident, target), emit)
                        return
                else:
                    misses[ident.path] = 0

    threading.Thread(target=read, daemon=True).start()
    threading.Thread(target=monitor, daemon=True).start()


def _is_pipe(stream) -> bool:
    try:
        return stat.S_ISFIFO(os.fstat(stream.fileno()).st_mode)
    except (OSError, ValueError, AttributeError):
        return False


def install_sigterm() -> None:
    """SIGTERM (vom Wächter, vom Tool über sudo) → Cancelled im Hauptthread, damit Einhängepunkte aufgeräumt
    werden."""
    def on_term(*_a):
        raise Cancelled(reason())
    signal.signal(signal.SIGTERM, on_term)
