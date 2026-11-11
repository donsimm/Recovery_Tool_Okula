"""Hardware-Test im Agent (I-023): Schnelltest (≈ 5 min) und Gründlich (1–3 h), nur lesend.

Bereiche: Akku, Temperaturen, Disk (SMART-Selbsttest kurz/lang, Werte), Disk-Oberfläche (jeden Sektor lesen),
Arbeitsspeicher (Muster schreiben/prüfen im laufenden System), CPU unter Last (Temperatur, Takt, Drosselung,
Hardware-Fehler), Netzwerk (Verbindung und Durchsatz zum Server).
Ergebnis je Bereich: ok (grün), warn (gelb), fail (rot), skip (grau, nicht prüfbar). Nichts wird geschrieben –
weder auf die Disk noch ins BIOS.
Nur stdlib (+ smartctl, das der Agent schon fürs Inventar hat). Läuft auf dem Stick.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Callable

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
SYMBOL = {OK: "✔", WARN: "⚠", FAIL: "✖", SKIP: "–"}
LEVELS = {
    "quick": ("battery", "temperature", "smart_short", "ram", "cpu", "network"),
    "thorough": ("battery", "temperature", "smart_long", "surface", "ram", "cpu", "network"),
}
TITLES = {"battery": "Akku", "temperature": "Temperaturen", "smart_short": "Disk: SMART-Selbsttest (kurz)",
          "smart_long": "Disk: SMART-Selbsttest (lang)", "surface": "Disk: Oberfläche lesen",
          "ram": "Arbeitsspeicher", "cpu": "CPU unter Last", "network": "Netzwerk"}
CPU_SECONDS = {"quick": 60, "thorough": 15 * 60}
RAM_SHARE = {"quick": 0.15, "thorough": 0.6}          # Anteil des freien Speichers
RAM_MAX = {"quick": 1 << 30, "thorough": 16 << 30}
NET_BYTES = {"quick": 200 * 1000 * 1000, "thorough": 500 * 1000 * 1000}
CHUNK = 8 * 1024 * 1024

Emit = Callable[[dict], None]


class Cancelled(Exception):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _int(text: str) -> int | None:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def result(step: str, status: str, summary: str, details: list[str] | None = None, values: dict | None = None,
           target: str = "") -> dict:
    return {"id": step, "title": TITLES[step] + (f" – {target}" if target else ""), "status": status,
            "summary": summary, "details": details or [], "values": values or {}}


# ---------- Akku ----------

def battery(sys_root: Path = Path("/sys")) -> list[dict]:
    out = []
    for bat in sorted((sys_root / "class" / "power_supply").glob("BAT*")):
        full = _int(_read(bat / "energy_full")) or _int(_read(bat / "charge_full"))
        design = _int(_read(bat / "energy_full_design")) or _int(_read(bat / "charge_full_design"))
        cycles = _int(_read(bat / "cycle_count"))
        model = " ".join(x for x in (_read(bat / "manufacturer"), _read(bat / "model_name")) if x)
        if not full or not design:
            out.append(result("battery", SKIP, "Kapazität nicht lesbar", [model], target=bat.name))
            continue
        health = round(100 * full / design)
        status = FAIL if health < 60 else WARN if health < 80 else OK
        text = f"Gesundheit {health} % der ursprünglichen Kapazität" + (f", {cycles} Ladezyklen" if cycles else "")
        out.append(result("battery", status, text,
                          [model, f"Ladestand: {_read(bat / 'capacity')} %, {_read(bat / 'status')}"],
                          {"health": health, "cycles": cycles}, bat.name))
    return out or [result("battery", SKIP, "kein Akku (Desktop-Gerät)")]


# ---------- Temperaturen ----------

def temperatures(sys_root: Path = Path("/sys")) -> dict[str, float]:
    """Sensorname → °C (hwmon, sonst thermal_zone)."""
    temps = {}
    for hw in sorted((sys_root / "class" / "hwmon").glob("hwmon*")):
        chip = _read(hw / "name") or hw.name
        for inp in sorted(hw.glob("temp*_input")):
            v = _int(_read(inp))
            if v is None or not -40000 < v < 150000:
                continue
            label = _read(inp.with_name(inp.name.replace("_input", "_label"))) or inp.name.split("_")[0]
            temps[f"{chip} {label}"] = v / 1000
    if not temps:
        for z in sorted((sys_root / "class" / "thermal").glob("thermal_zone*")):
            v = _int(_read(z / "temp"))
            if v is not None and -40000 < v < 150000:
                temps[_read(z / "type") or z.name] = v / 1000
    return temps


def temperature_step(sys_root: Path = Path("/sys")) -> dict:
    temps = temperatures(sys_root)
    if not temps:
        return result("temperature", SKIP, "keine Temperatursensoren gefunden")
    hottest = max(temps.items(), key=lambda kv: kv[1])
    status = FAIL if hottest[1] >= 95 else WARN if hottest[1] >= 80 else OK
    return result("temperature", status, f"im Leerlauf höchstens {hottest[1]:.0f} °C ({hottest[0]})",
                  [f"{k}: {v:.0f} °C" for k, v in sorted(temps.items())], {"max": hottest[1]})


# ---------- Disk: SMART ----------

def _smartctl(*args: str) -> dict:
    r = subprocess.run(["smartctl", *args, "-j"], capture_output=True, text=True, timeout=60)
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return {}


def smart_values(data: dict) -> tuple[str, list[str], dict]:
    """Bewertung der SMART-Werte: (Status, Details, Werte)."""
    status, details, values = OK, [], {}
    if (data.get("smart_status") or {}).get("passed") is False:
        status = FAIL
        details.append("SMART-Gesamtzustand: FEHLER – Disk bald ersetzen")
    hours = (data.get("power_on_time") or {}).get("hours")
    if hours is not None:
        values["hours"] = hours
        details.append(f"Betriebsstunden: {hours}")
    for attr in (data.get("ata_smart_attributes") or {}).get("table") or []:
        raw = (attr.get("raw") or {}).get("value") or 0
        name = {5: "Umgeschriebene Sektoren", 197: "Unsichere Sektoren", 198: "Unlesbare Sektoren",
                199: "Übertragungsfehler (Kabel)"}.get(attr.get("id"))
        if name:
            values[name] = raw
            details.append(f"{name}: {raw}")
            if raw and attr.get("id") in (197, 198):
                status = FAIL
            elif raw and status == OK:
                status = WARN
    nvme = data.get("nvme_smart_health_information_log") or {}
    if nvme:
        used, spare = nvme.get("percentage_used"), nvme.get("available_spare")
        thresh, errors = nvme.get("available_spare_threshold"), nvme.get("media_errors")
        details += [f"Abnutzung: {used} %", f"Reserve: {spare} % (Grenze {thresh} %)", f"Medienfehler: {errors}"]
        values.update({"used": used, "spare": spare, "media_errors": errors})
        if nvme.get("critical_warning") or (spare is not None and thresh is not None and spare <= thresh):
            status = FAIL
        elif (used or 0) >= 90 or (errors or 0) > 0:
            status = WARN if status == OK else status
    return status, details, values


def self_test_running(data: dict) -> float | None:
    """Läuft ein Selbsttest? Anteil fertig (0–1), sonst None. ATA: Status 240–255; NVMe: laufende Operation."""
    ata = ((data.get("ata_smart_data") or {}).get("self_test") or {}).get("status") or {}
    if ata and (ata.get("value", 0) >> 4) == 0xF:
        return 1 - (ata.get("remaining_percent") or 0) / 100
    nv = data.get("nvme_self_test_log") or {}
    if (nv.get("current_self_test_operation") or {}).get("value"):
        return (nv.get("current_self_test_completion_percent") or 0) / 100
    return None


def self_test_result(data: dict) -> tuple[bool | None, str]:
    """Ergebnis des letzten Selbsttests: (bestanden?, Text)."""
    ata = ((data.get("ata_smart_self_test_log") or {}).get("standard") or {}).get("table") or []
    if ata:
        st = ata[0].get("status") or {}
        return st.get("passed"), st.get("string", "")
    nv = (data.get("nvme_self_test_log") or {}).get("table") or []
    if nv:
        r = nv[0].get("self_test_result") or {}
        return r.get("value") == 0 if "value" in r else None, r.get("string", "")
    return None, ""


def smart_test(disk: dict, kind: str, emit: Emit, cancel: Callable[[], bool], step: str,
               poll: float = 5.0) -> dict:
    """SMART-Selbsttest starten (kurz/lang), warten, Ergebnis + Werte bewerten."""
    path, name = disk["path"], f"{disk['name']} {disk.get('model', '')}".strip()
    if not shutil.which("smartctl"):
        return result(step, SKIP, "smartctl fehlt auf dem Agent-Stick", target=name)
    start = _smartctl("-t", kind, path)
    failed = ((start.get("smartctl") or {}).get("exit_status", 0) & 0x06) or any(
        m.get("severity") == "error" for m in (start.get("smartctl") or {}).get("messages") or [])
    if failed:
        status, details, values = smart_values(_smartctl("-H", "-A", "-i", path))
        return result(step, status if status != OK else SKIP,
                      "Selbsttest wird von dieser Disk nicht unterstützt – nur Werte geprüft", details, values, name)
    began = time.monotonic()
    limit = 6 * 3600 if kind == "long" else 15 * 60
    data: dict = {}
    while True:
        if cancel():
            _smartctl("-X", path)          # Selbsttest abbrechen
            raise Cancelled()
        time.sleep(poll)
        data = _smartctl("-a", path)
        done = self_test_running(data)
        if done is None:
            break
        if time.monotonic() - began > limit:
            _smartctl("-X", path)
            status, details, values = smart_values(data)
            return result(step, WARN, "Selbsttest nach Zeitlimit abgebrochen", details, values, name)
        emit({"event": "progress", "fraction": max(0.0, min(1.0, done)),
              "detail": f"{name}: Selbsttest läuft ({done * 100:.0f} %)"})
    status, details, values = smart_values(data)
    passed, text = self_test_result(data)
    if passed is False:
        status = FAIL
    summary = ("Selbsttest bestanden" if passed else "Selbsttest FEHLGESCHLAGEN" if passed is False
               else "Selbsttest: kein Ergebnis gemeldet") + (f" ({text})" if text and not passed else "")
    return result(step, status, summary, details, values, name)


# ---------- Disk: Oberfläche ----------

def surface(disk: dict, emit: Emit, cancel: Callable[[], bool]) -> dict:
    """Jeden Sektor lesen (nur lesend). Lesefehler werden gezählt und übersprungen."""
    path, size = disk["path"], int(disk.get("size") or 0)
    name = f"{disk['name']} {disk.get('model', '')}".strip()
    errors, pos, began, last = [], 0, time.monotonic(), 0.0
    fd = os.open(path, os.O_RDONLY)
    try:
        while pos < size:
            if cancel():
                raise Cancelled()
            try:
                os.lseek(fd, pos, os.SEEK_SET)
                n = len(os.read(fd, min(CHUNK, size - pos)))
                if n == 0:
                    break
                try:
                    os.posix_fadvise(fd, pos, n, os.POSIX_FADV_DONTNEED)   # Zwischenspeicher nicht füllen
                except (AttributeError, OSError):
                    pass
                pos += n
            except OSError as e:
                errors.append(f"Lesefehler bei {pos // (1024 * 1024)} MiB: {e.strerror or e}")
                pos += 1024 * 1024
            now = time.monotonic()
            if now - last > 2:
                last = now
                speed = pos / max(now - began, 0.001) / 1e6
                emit({"event": "progress", "fraction": pos / size if size else 1.0,
                      "detail": f"{name}: {pos * 100 // max(size, 1)} % gelesen · {speed:.0f} MB/s"})
    finally:
        os.close(fd)
    seconds = time.monotonic() - began
    speed = pos / max(seconds, 0.001) / 1e6
    status = FAIL if errors else OK
    summary = (f"{len(errors)} Lesefehler" if errors else "alle Sektoren lesbar") + \
        f" · {speed:.0f} MB/s · {seconds / 60:.0f} min"
    return result("surface", status, summary, errors[:50], {"errors": len(errors), "mb_s": round(speed)}, name)


# ---------- Arbeitsspeicher ----------

def mem_available() -> int:
    for line in _read(Path("/proc/meminfo")).splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return 0


def ram(level: str, emit: Emit, cancel: Callable[[], bool], size: int | None = None) -> dict:
    """Muster in einen grossen Block schreiben und prüfen (im laufenden System – nur der freie Teil)."""
    avail = mem_available()
    size = size or min(RAM_MAX[level], int(avail * RAM_SHARE[level]))
    size -= size % (1 << 20)
    if size < (64 << 20):
        return result("ram", SKIP, "zu wenig freier Arbeitsspeicher für einen Test")
    passes = 1 if level == "quick" else 3
    patterns = (0x00, 0xFF, 0x55, 0xAA)
    errors, steps, done = 0, passes * len(patterns), 0
    began = time.monotonic()
    buf = bytearray(size)
    try:
        for _p in range(passes):
            for pat in patterns:
                if cancel():
                    raise Cancelled()
                block = bytes([pat]) * (1 << 20)
                for off in range(0, size, 1 << 20):
                    buf[off:off + (1 << 20)] = block
                for off in range(0, size, 1 << 20):
                    if buf[off:off + (1 << 20)] != block:
                        errors += 1
                done += 1
                emit({"event": "progress", "fraction": done / steps,
                      "detail": f"{size >> 20} MiB · Muster {done}/{steps}"})
    finally:
        del buf
    total = _int(next((l.split()[1] for l in _read(Path("/proc/meminfo")).splitlines()
                       if l.startswith("MemTotal:")), "")) or 0
    summary = (f"{errors} fehlerhafte Bereiche" if errors else "keine Fehler") + \
        f" · {size >> 20} MiB von {total >> 10} MiB geprüft ({time.monotonic() - began:.0f} s)"
    return result("ram", FAIL if errors else OK, summary,
                  ["Teilprüfung im laufenden System – vollständiger Test mit memtest86+ (eigener Start) folgt"],
                  {"tested_mib": size >> 20, "total_mib": total >> 10, "errors": errors})


# ---------- CPU unter Last ----------

BURN = "import time\nend=time.monotonic()+{s}\nx=0\nwhile time.monotonic()<end:\n for i in range(20000): x=(x*1103515245+i)&0xFFFFFFFF\n"


def _freqs(sys_root: Path) -> list[int]:
    return [v for v in (_int(_read(p)) for p in sys_root.glob("devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"))
            if v]


def _throttles(sys_root: Path) -> int:
    return sum(_int(_read(p)) or 0 for p in
               sys_root.glob("devices/system/cpu/cpu[0-9]*/thermal_throttle/*_throttle_count"))


# Hardware-Fehler (Machine Check, B-011). Kernel-Log ohne `journalctl -g` lesen (braucht PCRE2 zur Laufzeit, ein
# Fehler fiel früher als „0 Fehler“ durch) und in Python filtern. Mit Zeitstempel, damit sich gleichlautende
# Meldungen verschiedener Ereignisse unterscheiden.
KERNEL_LOG_SOURCES = (["journalctl", "-k", "-b", "-o", "short-monotonic", "--no-pager"], ["dmesg"])
MCE_WORDS = ("mce", "machine check", "hardware error")
# „mce: [Hardware Error]: CPU 3: Machine Check: 0 Bank 0: d400008000040150“ (auch „Machine Check Exception“)
MCE_EVENT = re.compile(r"CPU\s+(\d+):\s*Machine Check[^:]*:\s*\S+\s+Bank\s+(\d+):\s*([0-9a-f]+)", re.I)
MCE_UNASSIGNED = re.compile(r"machine check events logged", re.I)
MCE_UC_BIT = 1 << 61                      # Status-Bit 61: nicht korrigiert
MCE_KIND = {"corrected": "korrigiert", "uncorrected": "nicht korrigiert", "": "Art unbekannt"}


def _run_lines(cmd: list[str], timeout: int = 60) -> list[str] | None:
    """Ausgabe eines Befehls als Zeilen; None bei Fehler, Zeitlimit oder leerer Ausgabe."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    lines = [l for l in r.stdout.splitlines() if l.strip() and not l.startswith("-- ")]   # „-- No entries --“
    return lines or None


def kernel_log() -> list[str] | None:
    """Kernel-Meldungen seit dem Start: journalctl, sonst dmesg; None, wenn keine Quelle Daten liefert."""
    for cmd in KERNEL_LOG_SOURCES:
        lines = _run_lines(cmd)
        if lines:
            return lines
    return None


def mce_filter(lines: list[str]) -> list[str]:
    return [l for l in lines if any(w in l.lower() for w in MCE_WORDS)]


def _mce_lines() -> list[str] | None:
    """MCE-Zeilen des Kernel-Logs seit dem Start; None = nicht prüfbar (für Tests austauschbar)."""
    lines = kernel_log()
    return None if lines is None else mce_filter(lines)


def mce_events(lines: list[str]) -> list[dict]:
    """Kernel-Zeilen → Ereignisse {cpu, bank, kind, line}. Ein Ereignis = Zeile „CPU n: Machine Check … Bank b:
    <Status>“ (PROCESSOR-, TSC-, ADDR-Zeilen gehören dazu und zählen nicht); „Machine check events logged“ =
    Ereignis ohne Zuordnung."""
    out = []
    for line in lines:
        m = MCE_EVENT.search(line)
        if m:
            kind = "uncorrected" if int(m.group(3), 16) & MCE_UC_BIT else "corrected"
            out.append({"cpu": int(m.group(1)), "bank": int(m.group(2)), "kind": kind, "line": line})
        elif MCE_UNASSIGNED.search(line):
            out.append({"cpu": None, "bank": None, "kind": "", "line": line})
    return out


def new_lines(before: list[str], after: list[str]) -> list[str]:
    """Zeilen, die nach `before` dazugekommen sind (gleichlautende Zeilen werden mitgezählt)."""
    left = Counter(before)
    out = []
    for l in after:
        if left[l]:
            left[l] -= 1
        else:
            out.append(l)
    return out


def _short_line(line: str, width: int = 110) -> str:
    low = line.lower()
    i = low.find("mce:")
    if i < 0:
        i = max(low.find("[hardware error]"), 0)
    text = line[i:].strip()
    return text if len(text) <= width else text[:width - 1] + "…"


def mce_groups(lines: list[str], new: list[str] = ()) -> list[dict]:
    """Ereignisse nach CPU, Bank und Art zusammenfassen: [{cpu, bank, kind, count, during, examples}].
    `new` = Zeilen, die während der Last dazukamen (Teil von `lines`)."""
    fresh = Counter(new)
    groups: dict[tuple, dict] = {}
    for ev in mce_events(lines):
        g = groups.setdefault((ev["cpu"], ev["bank"], ev["kind"]), {
            "cpu": ev["cpu"], "bank": ev["bank"], "kind": ev["kind"], "count": 0, "during": 0, "examples": []})
        g["count"] += 1
        if fresh[ev["line"]]:
            fresh[ev["line"]] -= 1
            g["during"] += 1
        ex = _short_line(ev["line"])
        if len(g["examples"]) < 3 and ex not in g["examples"]:
            g["examples"].append(ex)
    return sorted(groups.values(), key=lambda g: (g["cpu"] is None, g["cpu"] or 0, g["bank"] or 0, g["kind"]))


def _mce_where(g: dict) -> str:
    return f"CPU {g['cpu']}, Bank {g['bank']}" if g["cpu"] is not None else "ohne Zuordnung"


def mce_short(groups: list[dict], key: str = "count") -> str:
    """„CPU 3, Bank 0: 12 Mal“ – höchstens 3 Gruppen."""
    parts = [f"{_mce_where(g)}: {g[key]} Mal" for g in groups if g[key]]
    return "; ".join(parts[:3]) + (f"; {len(parts) - 3} weitere" if len(parts) > 3 else "")


def mce_details(groups: list[dict]) -> list[str]:
    out = []
    for g in groups:
        kind = f" ({MCE_KIND[g['kind']]})" if g["kind"] else ""
        out.append(f"Hardware-Fehler {_mce_where(g)}{kind}: {g['count']} Mal seit dem Start"
                   + (f", davon {g['during']} während der Last" if g["during"] else ""))
        out += [f"  Beispiel: {ex}" for ex in g["examples"]]
    return out


def cpu(level: str, emit: Emit, cancel: Callable[[], bool], sys_root: Path = Path("/sys"),
        seconds: int | None = None) -> dict:
    seconds = seconds or CPU_SECONDS[level]
    cores = os.cpu_count() or 1
    max_freq = max((_int(_read(p)) or 0 for p in
                    sys_root.glob("devices/system/cpu/cpu[0-9]*/cpufreq/cpuinfo_max_freq")), default=0)
    thr0, mce0 = _throttles(sys_root), _mce_lines()
    began = time.monotonic()
    stop_at = began + seconds
    procs = [subprocess.Popen([sys.executable, "-c", BURN.format(s=seconds)], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) for _ in range(cores)]
    peak, freqs, sensed = 0.0, [], False
    try:
        while time.monotonic() < stop_at:
            if cancel():
                raise Cancelled()
            time.sleep(min(5, max(0.1, stop_at - time.monotonic())))
            temps = temperatures(sys_root)
            sensed = sensed or bool(temps)
            peak = max([peak] + list(temps.values()))
            f = _freqs(sys_root)
            if f:
                freqs.append(sum(f) / len(f))
            emit({"event": "progress", "fraction": (time.monotonic() - began) / seconds,
                  "detail": f"{cores} Kerne unter Last" + (f" · {peak:.0f} °C" if sensed else "")
                            + (f" · {freqs[-1] / 1e6:.1f} GHz" if freqs else "")})
    finally:
        for p in procs:
            p.kill()
        for p in procs:
            p.wait(5)
    thr = _throttles(sys_root) - thr0
    mce1 = _mce_lines()
    lines = mce1 if mce1 is not None else mce0
    groups = mce_groups(lines or [], new_lines(mce0, mce1) if mce0 is not None and mce1 is not None else [])
    mce_new, mce_boot = sum(g["during"] for g in groups), sum(g["count"] for g in groups)
    uncorrected = any(g["kind"] == "uncorrected" for g in groups)
    avg = sum(freqs[len(freqs) // 2:]) / max(1, len(freqs[len(freqs) // 2:])) if freqs else 0
    details = [f"{cores} Kerne, {max(1, round(seconds / 60))} min Volllast",
               f"höchste Temperatur: {peak:.0f} °C" if sensed else "keine Temperatursensoren gefunden"]
    if avg and max_freq:
        details.append(f"Takt in der zweiten Hälfte: {avg / 1e6:.2f} GHz (höchstens {max_freq / 1e6:.2f} GHz)")
    if thr:
        details.append(f"Drosselung wegen Hitze: {thr} Mal")
    if lines is None:
        details.append("Hardware-Fehler nicht prüfbar (Kernel-Protokoll nicht lesbar)")
    elif not groups:
        details.append("Hardware-Fehler: keine seit dem Start")
    details += mce_details(groups)
    status = FAIL if peak >= 100 else WARN if peak >= 95 or thr > 0 or (
        max_freq and avg and avg < 0.5 * max_freq) else OK
    hint = " – BIOS-Update bzw. Prozessor prüfen"
    if mce_new:
        status = FAIL
        summary = f"Hardware-Fehler des Prozessors während der Last gemeldet ({mce_short(groups, 'during')})" + hint
    elif uncorrected:
        status = FAIL
        summary = f"Nicht korrigierte Hardware-Fehler seit dem Start gemeldet ({mce_short(groups)})" + hint
    elif mce_boot:
        status = WARN if status == OK else status
        summary = f"Hardware-Fehler seit dem Start gemeldet ({mce_short(groups)})" + hint
    else:
        summary = ((f"höchstens {peak:.0f} °C" if sensed else "Temperatur nicht messbar") +
                   (", drosselt wegen Hitze (Lüfter/Wärmeleitpaste prüfen)" if thr else ", stabil"))
    return result("cpu", status, summary, details, {
        "peak": peak, "throttle": thr, "mce": mce_new, "mce_boot": mce_boot,
        "mce_groups": [{k: g[k] for k in ("cpu", "bank", "count", "kind", "during")} for g in groups]})


# ---------- Netzwerk ----------

def network_info(sys_root: Path = Path("/sys")) -> list[str]:
    out = []
    for nic in sorted((sys_root / "class" / "net").iterdir()) if (sys_root / "class" / "net").is_dir() else []:
        if nic.name == "lo" or not (nic / "device").exists() or (nic / "wireless").exists():
            continue
        speed, carrier = _int(_read(nic / "speed")), _read(nic / "carrier") == "1"
        out.append(f"{nic.name}: " + (f"verbunden, {speed} Mbit/s {_read(nic / 'duplex')}" if carrier and speed
                                      and speed > 0 else "kein Kabel" if not carrier else "verbunden"))
    return out


def network(level: str, emit: Emit, send_data: Callable[[bytes], None], wait_ack: Callable[[], None],
            sys_root: Path = Path("/sys")) -> dict:
    """Durchsatz zum Server: Daten an das Tool senden, das bestätigt den Empfang."""
    links = network_info(sys_root)
    total = NET_BYTES[level]
    emit({"event": "net_begin", "bytes": total})
    block = bytes(1024 * 1024)
    began = time.monotonic()
    sent = 0
    while sent < total:
        n = min(len(block), total - sent)
        send_data(block[:n])
        sent += n
    wait_ack()
    seconds = max(time.monotonic() - began, 0.001)
    mbit = sent * 8 / seconds / 1e6
    speed = max((_int(s.split(", ")[1].split()[0]) or 0 for s in links if ", " in s and "Mbit" in s), default=0)
    status = WARN if speed and mbit < 0.5 * speed else OK
    if speed and speed < 1000:
        status = WARN
        links.append("Verbindung unter 1 Gbit/s – Kabel, Switch-Port oder Netzwerkkarte prüfen")
    return result("network", status, f"{mbit:.0f} Mbit/s zum Server" + (f" (Verbindung {speed} Mbit/s)" if speed else ""),
                  links, {"mbit": round(mbit), "link": speed})


# ---------- Ablauf ----------

def run(req: dict, disks: list[dict], emit: Emit, cancel: Callable[[], bool], send_data, wait_ack) -> dict:
    """Alle Schritte der Stufe; emit({...}) meldet Fortschritt und Ergebnisse an das Tool."""
    level = req.get("level") if req.get("level") in LEVELS else "quick"
    began = time.strftime("%Y-%m-%dT%H:%M:%S")
    results = []
    steps = list(LEVELS[level])
    for i, step in enumerate(steps):
        targets = disks if step in ("smart_short", "smart_long", "surface") else [None]
        for target in targets:
            title = TITLES[step] + (f" – {target['name']}" if target else "")
            emit({"event": "step_start", "id": step, "title": title, "index": i, "count": len(steps)})
            if cancel():
                raise Cancelled()
            try:
                if step == "battery":
                    res = battery()
                elif step == "temperature":
                    res = [temperature_step()]
                elif step in ("smart_short", "smart_long"):
                    res = [smart_test(target, "short" if step == "smart_short" else "long", emit, cancel, step)]
                elif step == "surface":
                    res = [surface(target, emit, cancel)]
                elif step == "ram":
                    res = [ram(level, emit, cancel)]
                elif step == "cpu":
                    res = [cpu(level, emit, cancel)]
                else:
                    res = [network(level, emit, send_data, wait_ack)]
            except Cancelled:
                raise
            except Exception as e:      # ein Bereich darf die anderen nicht verhindern
                res = [result(step, SKIP, f"nicht prüfbar: {type(e).__name__}: {e}")]
            for r in res:
                results.append(r)
                emit({"event": "step", "result": r})
        if step in ("smart_short", "smart_long", "surface") and not disks:
            r = result(step, SKIP, "keine interne Disk gefunden")
            results.append(r)
            emit({"event": "step", "result": r})
    return {"level": level, "started": began, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}
