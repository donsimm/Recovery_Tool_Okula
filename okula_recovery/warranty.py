"""Garantie-Abfrage per Seriennummer (I-025): Dell, HP, Lenovo – sonst „Garantie bis“ von Hand.

- Dell (TechDirect Warranty API v5) und HP (HP Warranty API) brauchen einen Schlüssel. Die Schlüssel liegen
  nur in CRED_FILE (root, 0600) – wie das NAS-Passwort, nie in der Konfiguration, im Repo oder im Export.
  Deshalb fragt der Root-Helfer /usr/local/sbin/okula-warranty (dieses Modul als root) die API ab und gibt nur
  das Ergebnis zurück.
- Lenovo: öffentliche Abfrage der Lenovo-Support-Seite (pcsupport.lenovo.com), ohne Schlüssel, als Benutzer.
  Inoffiziell – ändert Lenovo die Seite, kommt eine Fehlermeldung und die Eingabe von Hand bleibt.
- Abfrage nur auf Knopfdruck oder einmal nach dem Erfassen; kein Dauer-Polling. Das Ergebnis liegt im Gerät
  (Device.warranty) und gilt 30 Tage als aktuell (CACHE_DAYS).

Quellen (Stand 31.10.2026, Endpunkte am realen System zu prüfen – siehe docs/TESTS.md):
- Dell: TechDirect → APIs → Warranty (Zugang auf Antrag, Token 3600 s), Endpunkte laut Dell-Community
  https://www.dell.com/community/en/conversations/automation/dell-warranty-api/69aaadf86d28f8372a2e2dc2
- HP: https://developers.hp.com („HP Warranty API“, Zugang auf Antrag, Schlüssel 90 Tage gültig,
  Kontakt warrantyapi.customers@hp.com)
- Lenovo: https://pcsupport.lenovo.com/warranty-lookup (öffentliche Seite)
Ausgabe des Root-Helfers: eine Zeile „OK <Text/JSON>“ oder „ERROR <Text>“.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

CRED_FILE = Path("/etc/okula-recovery/warranty.cred")
HELPER = "/usr/local/sbin/okula-warranty"
PROJECT_DIR = Path(__file__).resolve().parent.parent

CACHE_DAYS = 30      # Ergebnis gilt so lange als aktuell
WARN_DAYS = 90       # gelb: läuft in höchstens so vielen Tagen ab
TIMEOUT = 20

DELL_TOKEN = "https://apigtwb2c.us.dell.com/auth/oauth/v2/token"
DELL_WARRANTY = "https://apigtwb2c.us.dell.com/PROD/sbil/eapi/v5/asset-entitlements"
HP_TOKEN = "https://warranty.api.hp.com/oauth/v1/token"
HP_QUERY = "https://warranty.api.hp.com/productwarranty/v2/queries"
LENOVO_QUERY = "https://pcsupport.lenovo.com/us/en/api/v4/upsell/redport/getIbaseInfo"
USER_AGENT = "Okula-Recovery-Tool"

KEY_VENDORS = ("dell", "hp")           # brauchen einen Schlüssel (Menü → Einstellungen)
NAMES = {"dell": "Dell", "hp": "HP", "lenovo": "Lenovo", "manual": "von Hand"}
SERIAL_RE = re.compile(r"^[A-Za-z0-9-]{4,30}$")
KEY_RE = re.compile(r"^[\x21-\x7e]{1,200}$")   # druckbar, ohne Leerzeichen/Zeilenumbruch
# Platzhalter statt echter Seriennummer (Eigenbau, Mainboard ohne Eintrag)
DUMMY_SERIALS = {"to be filled by o.e.m.", "default string", "system serial number", "not specified", "none",
                 "0", "00000000", "0123456789", "123456789", "chassis serial number", "invalid"}

Http = Callable[[str, str, bytes | None, dict], tuple[int, bytes]]


class WarrantyError(Exception):
    pass


# ---------- Gerät → Hersteller/Seriennummer ----------

def vendor_of(inv: dict) -> str:
    """dell / hp / lenovo aus dem DMI-Hersteller, sonst ""."""
    v = ((inv or {}).get("dmi") or {}).get("sys_vendor", "").lower()
    if v.startswith("dell"):
        return "dell"
    if v.startswith(("hp", "hewlett")):
        return "hp"
    if v.startswith("lenovo"):
        return "lenovo"
    return ""


def serial_of(inv: dict) -> str:
    sn = ((inv or {}).get("dmi") or {}).get("product_serial", "").strip()
    return "" if sn.lower() in DUMMY_SERIALS or not SERIAL_RE.match(sn) else sn


# ---------- Ergebnis, Anzeige ----------

def parse_date(value) -> date | None:
    """„2027-03-31“, „2027-03-31T23:59:59.999Z“, „31.03.2027“ → date."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
    try:
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", value)
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None
    return None


def result(vendor: str, until: date | None, start: date | None = None, service: str = "") -> dict:
    return {"until": until.isoformat() if until else "", "start": start.isoformat() if start else "",
            "source": vendor, "service": service, "checked": datetime.now().isoformat(timespec="seconds"),
            "error": ""}


def manual(until_text: str) -> dict:
    """„Garantie bis“ von Hand (TT.MM.JJJJ oder JJJJ-MM-TT); leer = löschen."""
    if not until_text.strip():
        return {}
    d = parse_date(until_text)
    if d is None:
        raise WarrantyError("Datum als TT.MM.JJJJ eingeben, z. B. 31.03.2027")
    return result("manual", d)


def status(w: dict | None, today: date | None = None) -> tuple[str, str]:
    """(Stufe, Text) – Stufe: ok, warn (≤ 90 Tage), expired, unknown."""
    today = today or date.today()
    until = parse_date((w or {}).get("until"))
    if until is None:
        return "unknown", "unbekannt"
    days = (until - today).days
    text = until.strftime("%d.%m.%Y")
    if days < 0:
        return "expired", f"{text} – abgelaufen"
    if days <= WARN_DAYS:
        return "warn", f"{text} – läuft in {days} Tag{'en' if days != 1 else ''} ab"
    return "ok", text


def fresh(w: dict | None, now: datetime | None = None) -> bool:
    """Abgefragt und jünger als CACHE_DAYS (manuelle Einträge gelten immer)."""
    if not w or not w.get("until"):
        return False
    if w.get("source") == "manual":
        return True
    try:
        checked = datetime.fromisoformat(w.get("checked", ""))
    except ValueError:
        return False
    return (now or datetime.now()) - checked < timedelta(days=CACHE_DAYS)


def describe(w: dict | None) -> str:
    """Zeile fürs Gerätefenster, z. B. „31.03.2027 (Dell, ProSupport) · abgefragt 31.10.2026“."""
    if not w:
        return "unbekannt"
    _level, text = status(w)
    parts = [p for p in (NAMES.get(w.get("source", ""), w.get("source", "")), w.get("service", "")) if p]
    line = f"{text} ({', '.join(parts)})" if parts and w.get("until") else text
    try:
        checked = datetime.fromisoformat(w["checked"]).strftime("%d.%m.%Y")
        line += f" · {'eingetragen' if w.get('source') == 'manual' else 'abgefragt'} {checked}"
    except (KeyError, ValueError):
        pass
    if w.get("source") != "manual" and w.get("until") and not fresh(w):
        line += f" (älter als {CACHE_DAYS} Tage)"
    if w.get("error"):
        line += f"\nLetzte Abfrage: {w['error']}"
    return line


def merge(old: dict | None, new: dict | None, error: str = "") -> dict:
    """Neues Ergebnis übernehmen; bei Fehler das alte behalten und den Fehler vermerken."""
    if new and not error:
        return new
    keep = dict(old or {})
    keep["error"] = error or "keine Angabe"
    return keep


# ---------- Antworten auswerten ----------

def _latest(entries: list[tuple[date | None, date | None, str]]) -> tuple[date | None, date | None, str]:
    entries = [e for e in entries if e[1] is not None]
    if not entries:
        return None, None, ""
    start, until, service = max(entries, key=lambda e: e[1])
    return start, until, service


def parse_dell(data) -> tuple[date | None, date | None, str]:
    """asset-entitlements v5: [{"serviceTag", "invalid", "entitlements": [{"startDate", "endDate",
    "serviceLevelDescription"}]}] → (Beginn, Ende, Dienst) des am längsten laufenden Eintrags."""
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise WarrantyError("Dell: leere Antwort")
    asset = data[0] if isinstance(data[0], dict) else {}
    if asset.get("invalid"):
        raise WarrantyError("Dell: Service-Tag unbekannt")
    entries = [(parse_date(e.get("startDate")), parse_date(e.get("endDate")), e.get("serviceLevelDescription") or "")
               for e in asset.get("entitlements") or [] if isinstance(e, dict)]
    start, until, service = _latest(entries)
    if until is None:
        raise WarrantyError("Dell: keine Garantie-Einträge zu diesem Service-Tag")
    return start, until, service


def _walk(obj, found: list) -> None:
    """Alle Objekte mit einem Feld „…EndDate“ sammeln (HP-/Lenovo-Antworten sind tief verschachtelt)."""
    if isinstance(obj, dict):
        ends = [k for k in obj if k.lower().endswith("enddate") and isinstance(obj[k], str)]
        if ends:
            k = ends[0]
            start_key = next((s for s in obj if s.lower().endswith("startdate")), "")
            desc = next((obj[s] for s in ("offerDescription", "serviceLevelDescription", "name", "description",
                                          "warrantyName") if isinstance(obj.get(s), str) and obj.get(s)), "")
            found.append((parse_date(obj.get(start_key)), parse_date(obj[k]), desc))
        for v in obj.values():
            _walk(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, found)


def parse_hp(data) -> tuple[date | None, date | None, str]:
    """HP Warranty API v2: [{"product": {...}, "offers": [{"serviceObligationLineItemStartDate",
    "serviceObligationLineItemEndDate", "offerDescription"}]}] – Felder mit …EndDate werden gesucht."""
    found: list = []
    _walk(data, found)
    start, until, service = _latest(found)
    if until is None:
        raise WarrantyError("HP: keine Garantie-Einträge zu dieser Seriennummer")
    return start, until, service


def parse_lenovo(data) -> tuple[date | None, date | None, str]:
    """pcsupport getIbaseInfo: {"code": 0, "data": {"baseWarranties": [{"startDate", "endDate", "name"}],
    "upmaWarranties": [...]}} → längste Garantie (Basis oder Erweiterung)."""
    if not isinstance(data, dict):
        raise WarrantyError("Lenovo: unerwartete Antwort")
    body = data.get("data") if isinstance(data.get("data"), dict) else {}
    found: list = []
    for key in ("baseWarranties", "upmaWarranties", "contractWarranties"):
        _walk(body.get(key) or [], found)
    start, until, service = _latest(found)
    if until is None:
        msg = data.get("msg") or data.get("message") or ""
        raise WarrantyError("Lenovo: keine Garantie zu dieser Seriennummer gefunden"
                            + (f" ({msg})" if isinstance(msg, str) and msg else ""))
    return start, until, service


# ---------- HTTP ----------

def http(method: str, url: str, body: bytes | None, headers: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(2_000_000)
    except urllib.error.HTTPError as e:
        return e.code, e.read(20_000)
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise WarrantyError(f"keine Verbindung ({reason}) – Internet prüfen oder „Garantie bis“ von Hand "
                            "eintragen") from None


def _json(code: int, raw: bytes, what: str):
    if code in (401, 403):
        raise WarrantyError(f"{what}: Zugang abgelehnt ({code}) – Schlüssel in Menü → Einstellungen prüfen")
    if code == 404:
        raise WarrantyError(f"{what}: Seriennummer nicht gefunden")
    if code == 429:
        raise WarrantyError(f"{what}: zu viele Abfragen – später erneut versuchen")
    if not 200 <= code < 300:
        raise WarrantyError(f"{what}: Fehler {code}")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise WarrantyError(f"{what}: Antwort ist kein JSON") from None


def query_dell(serial: str, client_id: str, secret: str, send: Http = http) -> dict:
    form = urllib.parse.urlencode({"client_id": client_id, "client_secret": secret,
                                   "grant_type": "client_credentials"}).encode()
    token = _json(*send("POST", DELL_TOKEN, form, {"Content-Type": "application/x-www-form-urlencoded"}),
                  "Dell-Anmeldung")
    if not isinstance(token, dict) or not token.get("access_token"):
        raise WarrantyError("Dell-Anmeldung: kein Token erhalten")
    url = f"{DELL_WARRANTY}?{urllib.parse.urlencode({'servicetags': serial})}"
    data = _json(*send("GET", url, None, {"Authorization": f"Bearer {token['access_token']}"}), "Dell")
    start, until, service = parse_dell(data)
    return result("dell", until, start, service)


def query_hp(serial: str, key: str, secret: str, product: str = "", send: Http = http) -> dict:
    basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
    token = _json(*send("POST", HP_TOKEN, b"grant_type=client_credentials",
                        {"Authorization": f"Basic {basic}",
                         "Content-Type": "application/x-www-form-urlencoded"}), "HP-Anmeldung")
    if not isinstance(token, dict) or not token.get("access_token"):
        raise WarrantyError("HP-Anmeldung: kein Token erhalten")
    item = {"sn": serial}
    if product:
        item["pn"] = product
    data = _json(*send("POST", HP_QUERY, json.dumps([item]).encode(),
                       {"Authorization": f"Bearer {token['access_token']}",
                        "Content-Type": "application/json"}), "HP")
    start, until, service = parse_hp(data)
    return result("hp", until, start, service)


def query_lenovo(serial: str, send: Http = http) -> dict:
    body = json.dumps({"serialNumber": serial, "country": "us", "language": "en"}).encode()
    data = _json(*send("POST", LENOVO_QUERY, body, {"Content-Type": "application/json"}), "Lenovo")
    start, until, service = parse_lenovo(data)
    return result("lenovo", until, start, service)


def hp_product(inv: dict) -> str:
    """HP-Produktnummer aus der DMI-SKU (z. B. „5ZH12EA#UUZ“), hilft der HP-API bei der Zuordnung."""
    sku = ((inv or {}).get("dmi") or {}).get("product_sku", "").strip()
    return sku if re.match(r"^[A-Za-z0-9#-]{4,30}$", sku) else ""


# ---------- Schlüssel (nur root) ----------

def read_keys(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or CRED_FILE).read_text())
    except (OSError, ValueError):
        return {}
    return {v: data[v] for v in KEY_VENDORS if isinstance(data.get(v), dict) and data[v].get("id")
            and data[v].get("secret")}


def write_keys(keys: dict, path: Path | None = None) -> None:
    path = path or CRED_FILE
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(keys, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def set_key(vendor: str, key_id: str, secret: str, path: Path | None = None) -> str:
    if vendor not in KEY_VENDORS:
        raise WarrantyError(f"Unbekannter Hersteller: {vendor}")
    keys = read_keys(path)
    if not key_id and not secret:
        keys.pop(vendor, None)
        write_keys(keys, path)
        return f"{NAMES[vendor]}-Schlüssel gelöscht"
    if not (KEY_RE.match(key_id) and KEY_RE.match(secret)):
        raise WarrantyError("Schlüssel ungültig (ohne Leerzeichen, beide Felder ausfüllen)")
    keys[vendor] = {"id": key_id, "secret": secret}
    write_keys(keys, path)
    return f"{NAMES[vendor]}-Schlüssel gespeichert"


def root_query(vendor: str, serial: str, product: str = "", path: Path | None = None, send: Http = http) -> dict:
    if not SERIAL_RE.match(serial):
        raise WarrantyError("Seriennummer ungültig")
    keys = read_keys(path).get(vendor)
    if vendor not in KEY_VENDORS:
        raise WarrantyError(f"Unbekannter Hersteller: {vendor}")
    if not keys:
        raise WarrantyError(f"kein {NAMES[vendor]}-Schlüssel – in Menü → Einstellungen eintragen oder "
                            "„Garantie bis“ von Hand eintragen")
    if vendor == "dell":
        return query_dell(serial, keys["id"], keys["secret"], send)
    return query_hp(serial, keys["id"], keys["secret"], product, send)


# ---------- Aufruf aus dem Tool (Benutzer) ----------

def _helper(args: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return [sys.executable, "-m", "okula_recovery.warranty", *args]
    if not Path(HELPER).exists():
        raise FileNotFoundError(f"{HELPER} fehlt – bitte install.sh erneut ausführen")
    return ["sudo", "-n", HELPER, *args]


def call_helper(args: list[str], stdin: str | None = None) -> tuple[bool, str]:
    try:
        r = subprocess.run(_helper(args), input=stdin, capture_output=True, text=True, timeout=90, cwd=PROJECT_DIR)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("OK ", "ERROR "))]
    if lines:
        kind, _, msg = lines[-1].partition(" ")
        return kind == "OK" and r.returncode == 0, msg
    return False, (r.stderr or r.stdout).strip() or f"Hilfsprogramm: Exit-Code {r.returncode}"


def configured() -> tuple[set[str], str]:
    """(Hersteller mit Schlüssel, Fehlertext) – liest nur, welche Schlüssel da sind, nie die Schlüssel selbst."""
    ok, msg = call_helper(["keys"])
    if not ok:
        return set(), msg
    return {v for v in msg.split(",") if v in KEY_VENDORS}, ""


def save_key(vendor: str, key_id: str, secret: str) -> tuple[bool, str]:
    return call_helper(["set-key", "--vendor", vendor, "--stdin"], stdin=f"{key_id}\n{secret}\n")


def supported(inv: dict) -> bool:
    return bool(vendor_of(inv) and serial_of(inv))


def lookup(inv: dict, run_helper=call_helper, send: Http = http) -> dict:
    """Garantie für ein Gerät abfragen. WarrantyError mit verständlichem Text, wenn es nicht geht."""
    vendor, serial = vendor_of(inv), serial_of(inv)
    if not vendor:
        hersteller = ((inv or {}).get("dmi") or {}).get("sys_vendor") or "unbekannt"
        raise WarrantyError(f"Abfrage nur für Dell, HP und Lenovo (Hersteller: {hersteller}) – "
                            "„Garantie bis“ von Hand eintragen")
    if not serial:
        raise WarrantyError("keine gültige Seriennummer im Inventar")
    if vendor == "lenovo":
        return query_lenovo(serial, send)
    args = ["query", "--vendor", vendor, "--serial", serial]
    product = hp_product(inv) if vendor == "hp" else ""
    if product:
        args += ["--product", product]
    ok, msg = run_helper(args)
    if not ok:
        raise WarrantyError(msg)
    try:
        data = json.loads(msg)
    except ValueError:
        raise WarrantyError("Antwort des Root-Helfers unlesbar") from None
    if not isinstance(data, dict) or not data.get("until"):
        raise WarrantyError("keine Garantie-Angabe erhalten")
    return data


# ---------- Root-Helfer ----------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Garantie-Abfrage (Dell/HP) für das Okula Recovery Tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keys")
    s = sub.add_parser("set-key")
    s.add_argument("--vendor", choices=KEY_VENDORS, required=True)
    s.add_argument("--stdin", action="store_true", help="Zeile 1: ID/Key, Zeile 2: Secret (beide leer = löschen)")
    q = sub.add_parser("query")
    q.add_argument("--vendor", choices=KEY_VENDORS, required=True)
    q.add_argument("--serial", required=True)
    q.add_argument("--product", default="")
    args = ap.parse_args(argv)

    if os.geteuid() != 0:
        print("ERROR Muss als root laufen", flush=True)
        return 1
    try:
        if args.cmd == "keys":
            msg = ",".join(sorted(read_keys())) or "-"
        elif args.cmd == "set-key":
            lines = sys.stdin.read().split("\n") if args.stdin else []
            key_id, secret = (lines + ["", ""])[:2]
            msg = set_key(args.vendor, key_id.strip(), secret.strip())
        else:
            product = args.product if re.match(r"^[A-Za-z0-9#-]{0,30}$", args.product) else ""
            msg = json.dumps(root_query(args.vendor, args.serial, product), ensure_ascii=False)
    except (WarrantyError, OSError) as e:
        print(f"ERROR {e}", flush=True)
        return 1
    print(f"OK {msg}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
