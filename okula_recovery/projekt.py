"""Projektübersicht (I-034): Doku des Repos einlesen und Rückmeldungen speichern – ohne GTK, gut testbar.

Datenquelle sind die Markdown-Dateien in ``<Projektordner>/docs`` (TESTS.md, AENDERUNGEN.md, UEBERGABE.md,
prompts/*.md). Sie werden nur gelesen. Rückmeldungen (Häkchen, Kommentare, Wünsche, neue Notizen) liegen in
``~/.local/share/okula-recovery/projekt-rueckmeldungen.json`` ausserhalb von Git; die Projektleitung überträgt sie
in die Doku und setzt dabei ``uebernommen``.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import pwd
import re
import secrets
import subprocess
import threading
from datetime import datetime
from pathlib import Path

REPO_NAME = "recovery_tool_okula"
FEEDBACK_NAME = "projekt-rueckmeldungen.json"

ARTEN = ("test", "bug", "aenderung", "idee", "uebergabe", "prompt")
NOTIZ_ARTEN = ("bug", "aenderung", "idee", "frage")
HAKEN = ("ok", "fehler")
PRIOS = ("🔴", "🟡", "⚪")
STATUS_WUENSCHE = ("als Nächstes", "zurückstellen", "streichen", "erledigt")
MAX_TEXT = 20000


# ---------- Benutzer und Pfade ----------

def user_home() -> Path:
    """Home des aufrufenden Benutzers – läuft das Tool unter sudo, das von SUDO_USER."""
    user = os.environ.get("SUDO_USER")
    if os.geteuid() == 0 and user:
        try:
            return Path(pwd.getpwnam(user).pw_dir)
        except KeyError:
            pass
    return Path.home()


def default_project_dir() -> Path:
    return user_home() / REPO_NAME


def project_dir(configured: str = "") -> Path:
    """Projektordner aus der Konfiguration, leer = Standard ``~/recovery_tool_okula``."""
    return Path(os.path.expanduser(configured.strip())) if configured.strip() else default_project_dir()


def feedback_path() -> Path:
    return user_home() / ".local" / "share" / "okula-recovery" / FEEDBACK_NAME


# ---------- Inline-Markdown ----------

_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?![\s*])(.+?)(?<![\s*])\*(?![*\w])")


def inline_html(text: str) -> str:
    """Inline-Markdown (fett, kursiv, `code`, Links) als HTML – alles escaped, kein Roh-HTML aus der Datei."""
    codes: list[str] = []

    def keep_code(m: re.Match) -> str:
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    out = html.escape(_CODE.sub(keep_code, text.replace("\x00", "")), quote=True)

    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if re.match(r"https?://", html.unescape(url)):
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
        return f'<span class="ref" title="{url}">{label}</span>'

    out = _LINK.sub(link, out)
    out = _BOLD.sub(r"<b>\1</b>", out)
    out = _ITALIC.sub(r"<i>\1</i>", out)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], out)


def plain(text: str) -> str:
    """Text ohne Markdown-Zeichen, Leerraum zusammengefasst (Kopie in der Rückmeldung, Suche, Schlüssel)."""
    text = _LINK.sub(r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<![\w*])\*(?!\s)|(?<!\s)\*(?![\w*])", "", text)
    return " ".join(text.split())


def block_html(lines: list[str]) -> str:
    """Mehrere Zeilen (Fortsetzungen, Unterpunkte) – Unterpunkte mit „•“, Teile mit <br>."""
    parts: list[str] = []
    bullets: list[bool] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^[-*]\s+(.*)$", s)
        if m and parts:
            parts.append(m.group(1))
            bullets.append(True)
        elif parts and line.startswith((" ", "\t")):
            parts[-1] += " " + s          # Fortsetzung (auch über Zeilen hinweg **fett**)
        else:
            parts.append(s)
            bullets.append(False)
    return "<br>".join(("• " if b else "") + inline_html(p) for p, b in zip(parts, bullets))


def text_key(prefix: str, section: str, text: str) -> str:
    """Stabiler Schlüssel: Abschnitt + SHA-1 der ersten 200 Zeichen (ohne Markdown, Leerraum, Gross/Klein)."""
    norm = plain(text).lower()[:200]
    digest = hashlib.sha1(f"{section}\n{norm}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{section}:{digest}"


# ---------- Markdown-Abschnitte ----------

def _sections(lines: list[str], level: int) -> list[tuple[str, list[str]]]:
    """Überschriften einer Ebene (``##``/``###``) mit den Zeilen bis zur nächsten gleicher oder höherer Ebene."""
    out: list[tuple[str, list[str]]] = []
    mark = "#" * level + " "
    higher = re.compile(r"^#{1,%d} " % (level - 1)) if level > 1 else None
    for line in lines:
        if line.startswith(mark):
            out.append((line[len(mark):].strip(), []))
        elif higher is not None and higher.match(line):
            out.append(("", []))   # höhere Ebene beendet den Abschnitt
        elif out:
            out[-1][1].append(line)
    return [(t, b) for t, b in out if t]


def _find(sections: list[tuple[str, list[str]]], start: str) -> list[str] | None:
    for title, body in sections:
        if title.startswith(start) or start in title:
            return body
    return None


def _items(body: list[str], pattern: str) -> tuple[list[str], list[tuple[re.Match, list[str]]]]:
    """Listeneinträge (Muster für die erste Zeile) mit eingerückten Folgezeilen; übrige Zeilen als Text."""
    text: list[str] = []
    items: list[tuple[re.Match, list[str]]] = []
    rx = re.compile(pattern)
    current: list[str] | None = None
    for line in body:
        m = rx.match(line)
        if m:
            current = [m.group("text")]
            items.append((m, current))
        elif current is not None and line.startswith((" ", "\t")) and line.strip():
            current.append(line)
        elif not line.strip():
            current = None
        else:
            current = None
            text.append(line)
    return text, items


def _section_id(title: str) -> str:
    m = re.match(r"^(\d+)\.", title)
    return m.group(1) if m else re.sub(r"\W+", "-", plain(title).lower()).strip("-")[:40]


def _test_group(title: str, body: list[str], sid: str, bezug: str) -> dict:
    text, items = _items(body, r"^- \[(?P<mark>[ xX])\]\s+(?P<text>.*)$")
    notes, rest = [], []
    for line in text:
        s = line.strip()
        if s.startswith(">"):
            s = s.lstrip(">").strip()
        if s.startswith("- "):
            notes.append([s[2:]])
        elif re.match(r"^\s", line) and notes:
            notes[-1].append(line)
        elif s:
            rest.append(s)
    paragraph = [inline_html(" ".join(rest))] if rest else []
    paragraph += [block_html(n) for n in notes if plain(" ".join(n)) not in ("(alle geprüft)",)]
    out = []
    for m, lines in items:
        full = "\n".join(lines)
        out.append({
            # Vermerk „– ✔ 06.11. …“ der Projektleitung ändert den Schlüssel nicht
            "key": text_key("test", sid, re.split(r"\s[–-]\s✔", full)[0]), "art": "test", "bezug": bezug,
            "html": block_html(lines), "text": plain(full), "erledigt": m.group("mark").lower() == "x",
        })
    return {"id": sid, "titel": title, "titel_html": inline_html(title), "text_html": paragraph, "items": out}


def parse_tests(md: str) -> list[dict]:
    """TESTS.md: „Vorbereitung am neuen Server“ und die Abschnitte unter „Offen – am realen System testen“."""
    lines = md.splitlines()
    top = _sections(lines, 2)
    groups = []
    prep = _find(top, "Vorbereitung")
    if prep is not None:
        title = next(t for t, b in top if b is prep)
        groups.append(_test_group(title, prep, "vorbereitung", "Vorbereitung"))
    offen = _find(top, "Offen")
    if offen is not None:
        for title, body in _sections(offen, 3):
            sid = _section_id(title)
            bezug = f"Abschnitt {sid}" if sid.isdigit() else plain(title)
            group = _test_group(title, body, sid, bezug)
            groups.append(group)
    return groups


# ---------- AENDERUNGEN.md ----------

def split_row(line: str) -> list[str]:
    """Tabellenzeile in Zellen – ``|`` in `code` oder als ``\\|`` trennt nicht."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, code, i = [], [], False, 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if c == "`":
            code = not code
        if c == "|" and not code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    cells.append("".join(cur).strip())
    return cells


def _table(body: list[str]) -> tuple[list[str], list[list[str]]]:
    rows = [line for line in body if line.strip().startswith("|")]
    if len(rows) < 2:
        return [], []
    head = split_row(rows[0])
    data = [split_row(r) for r in rows[1:] if not re.match(r"^\|?[\s:|-]+\|?$", r.strip())]
    return head, data


TABLES = (("bug", "🐞", "Bugs"), ("aenderung", "🔧", "Änderungen"), ("idee", "💡", "Ideen"))


def parse_changes(md: str) -> dict:
    """AENDERUNGEN.md: Tabellen Bugs/Änderungen/Ideen, Kurzübersicht, Entscheidungen."""
    top = _sections(md.splitlines(), 2)
    out: dict = {"tabellen": {}, "kurz": {"zaehler": [], "als_naechstes": "", "vorschlag": ""}, "entscheidungen": []}
    for art, emoji, name in TABLES:
        body = next((b for t, b in top if t.startswith(emoji)), None)
        if body is None:
            continue
        head, rows = _table(body)
        items = []
        for cells in rows:
            cols = list(head)
            for extra in range(len(cells) - len(cols)):
                cols.append("Gemeldet" if "Gemeldet" not in cols else f"Spalte {len(cols) + 1}")
            row = dict(zip(cols, cells))
            ident = plain(row.get("ID", ""))
            if not re.match(r"^[A-ZÄ]-\d+", ident):
                continue
            desc = row.get("Beschreibung", "")
            items.append({
                "key": ident, "art": art, "bezug": ident, "id": ident,
                "prio": plain(row.get("Prio", "")), "status": plain(row.get("Status", "")),
                "html": inline_html(desc), "text": plain(desc),
                "spalten": [[c, inline_html(v)] for c, v in zip(cols, cells)],
            })
        out["tabellen"][art] = {"titel": name, "spalten": head, "items": items}
    kurz = _find(top, "Kurzübersicht")
    if kurz is not None:
        head, rows = _table(kurz)
        out["kurz"]["spalten"] = head
        out["kurz"]["zaehler"] = [[inline_html(c) for c in r] for r in rows]
        for line in kurz:
            s = line.strip()
            if s.startswith("Als Nächstes"):
                out["kurz"]["als_naechstes"] = inline_html(s.split(":", 1)[1].strip() if ":" in s else s)
            elif s.startswith("Vorschlag Reihenfolge"):
                out["kurz"]["vorschlag"] = inline_html(s)
    ents = _find(top, "📌")
    if ents is not None:
        _text, items = _items(ents, r"^- (?P<text>.*)$")
        out["entscheidungen"] = [block_html(lines) for _m, lines in items]
    return out


# ---------- UEBERGABE.md und Prompts ----------

def parse_handover(md: str) -> dict:
    lines = md.splitlines()
    title = plain(lines[0].lstrip("#")) if lines and lines[0].startswith("#") else "Übergabe"
    body = _find(_sections(lines, 2), "Offen und als Nächstes") or []
    _text, items = _items(body, r"^(?P<nr>\d+)\.\s+(?P<text>.*)$")
    out = []
    for m, lines_ in items:
        full = "\n".join(lines_)
        out.append({"key": text_key("uebergabe", "offen", full), "art": "uebergabe",
                    "bezug": f"Übergabe Punkt {m.group('nr')}", "nr": m.group("nr"),
                    "html": block_html(lines_), "text": plain(full)})
    return {"titel": title, "items": out}


def parse_prompt(name: str, md: str) -> dict:
    lines = md.splitlines()
    title = plain(lines[0].lstrip("#")) if lines else name
    status = next((plain(line[len("Status:"):]) for line in lines[:15] if line.startswith("Status:")), "")
    short = status.split(" · ")[0].strip()
    return {"key": f"prompt:{name}", "art": "prompt", "bezug": name, "datei": name,
            "titel": title, "status": status, "status_kurz": short, "html": inline_html(title),
            "text": f"{title} – {status}"}


def git_state(folder: Path) -> str:
    try:
        r = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(folder), "log", "-1",
                            "--format=%h %cd", "--date=format:%d.%m.%Y %H:%M"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def collect(folder: Path) -> dict:
    """Alles für die Seite – bei jedem Laden neu. Fehler einzelner Dateien landen in ``fehler``, nie als Absturz."""
    data: dict = {"projektordner": str(folder), "gelesen": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                  "git": "", "hinweis": "", "fehler": [], "tests": [], "tabellen": {},
                  "kurz": {"zaehler": [], "als_naechstes": "", "vorschlag": ""}, "entscheidungen": [],
                  "uebergabe": {"titel": "", "items": []}, "prompts": []}
    docs = folder / "docs"
    if not folder.is_dir():
        data["hinweis"] = (f"Projektordner {folder} nicht gefunden. Repo klonen oder unter Menü → Einstellungen … "
                           "den Projektordner (Repo) anpassen.")
        return data
    if not docs.is_dir():
        data["hinweis"] = (f"Im Projektordner {folder} fehlt der Ordner docs. Unter Menü → Einstellungen … "
                           "den Projektordner (Repo) prüfen.")
        return data
    data["git"] = git_state(folder)

    def read(name: str, parser, key: str) -> None:
        try:
            md = (docs / name).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            data["fehler"].append(f"{name} nicht lesbar: {e.strerror or e}")
            return
        try:
            result = parser(md)
        except Exception as e:  # unbekannte Struktur: Seite trotzdem zeigen
            data["fehler"].append(f"{name} nicht lesbar: {e}")
            return
        if key == "aenderungen":
            data.update(result)
        else:
            data[key] = result

    read("TESTS.md", parse_tests, "tests")
    read("AENDERUNGEN.md", parse_changes, "aenderungen")
    read("UEBERGABE.md", parse_handover, "uebergabe")
    for path in sorted((docs / "prompts").glob("*.md")) if (docs / "prompts").is_dir() else []:
        if path.name == "VORLAGE.md":
            continue
        try:
            data["prompts"].append(parse_prompt(path.name, path.read_text(encoding="utf-8", errors="replace")))
        except Exception as e:
            data["fehler"].append(f"prompts/{path.name} nicht lesbar: {e}")
    return data


def all_keys(data: dict) -> set[str]:
    keys = {i["key"] for g in data.get("tests", []) for i in g["items"]}
    keys |= {i["key"] for t in data.get("tabellen", {}).values() for i in t["items"]}
    keys |= {i["key"] for i in data.get("uebergabe", {}).get("items", [])}
    keys |= {p["key"] for p in data.get("prompts", [])}
    return keys


# ---------- Rückmeldungen (JSON-Datei) ----------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _empty() -> dict:
    return {"version": 1, "eintraege": {}, "notizen": []}


class FeedbackError(ValueError):
    pass


class FeedbackStore:
    """Rückmeldungen in einer JSON-Datei; bei jedem Zugriff neu gelesen (die Projektleitung setzt ``uebernommen``)."""

    def __init__(self, path: Path | None = None):
        self.path = path or feedback_path()
        self.hinweis = ""
        self._lock = threading.Lock()

    def load(self) -> dict:
        with self._lock:
            return self._load()

    def _load(self) -> dict:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _empty()
        except OSError as e:
            raise FeedbackError(f"Rückmeldungen nicht lesbar: {e.strerror or e}") from e
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or not isinstance(data.get("eintraege", {}), dict) \
                    or not isinstance(data.get("notizen", []), list):
                raise ValueError("unerwarteter Aufbau")
        except ValueError as e:
            broken = self.path.with_name(f"{self.path.stem}.defekt-{datetime.now():%Y%m%d-%H%M%S}.json")
            try:
                os.replace(self.path, broken)
            except OSError:
                pass
            self.hinweis = (f"Die Datei mit den Rückmeldungen war defekt ({e}) und wurde als {broken.name} "
                            "beiseitegelegt. Neue Rückmeldungen kommen in eine neue Datei.")
            return _empty()
        data.setdefault("version", 1)
        data.setdefault("eintraege", {})
        data.setdefault("notizen", [])
        return data

    def _save(self, data: dict) -> None:
        folder = self.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".{self.path.name}.{secrets.token_hex(4)}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            self._chown(folder, tmp)
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    @staticmethod
    def _chown(folder: Path, file: Path) -> None:
        """Unter sudo: Datei und Ordner gehören SUDO_USER (sonst kann die Projektleitung nicht schreiben)."""
        user = os.environ.get("SUDO_USER")
        if os.geteuid() != 0 or not user:
            return
        try:
            pw = pwd.getpwnam(user)
        except KeyError:
            return
        for p in (folder, file):
            try:
                os.chown(p, pw.pw_uid, pw.pw_gid)
            except OSError:
                pass

    def save_entry(self, key: str, art: str, bezug: str, text: str, changes: dict) -> dict | None:
        """Felder einer Rückmeldung ändern; alle Felder leer = Rückmeldung entfernen. Gibt den Eintrag zurück."""
        if not key or len(key) > 200:
            raise FeedbackError("Schlüssel fehlt")
        if art not in ARTEN:
            raise FeedbackError(f"Unbekannte Art: {art}")
        clean: dict = {}
        for field, value in changes.items():
            if value in ("", None):
                value = None
            if field == "haken" and value not in (None, *HAKEN):
                raise FeedbackError("Häkchen nur „ok“ oder „fehler“")
            elif field == "prio_wunsch" and value not in (None, *PRIOS):
                raise FeedbackError("Priorität nur 🔴, 🟡 oder ⚪")
            elif field == "status_wunsch" and value not in (None, *STATUS_WUENSCHE):
                raise FeedbackError("Unbekannter Status-Wunsch")
            elif field == "kommentar":
                if value is not None and not isinstance(value, str):
                    raise FeedbackError("Kommentar muss Text sein")
                value = value[:MAX_TEXT] if value and value.strip() else None
            elif field not in ("haken", "prio_wunsch", "status_wunsch", "kommentar"):
                continue
            clean[field] = value
        with self._lock:
            data = self._load()
            entry = data["eintraege"].get(key) or {"art": art, "bezug": bezug, "text": "", "haken": None,
                                                    "kommentar": None, "prio_wunsch": None, "status_wunsch": None,
                                                    "geaendert": None, "uebernommen": None}
            if not any(entry.get(f) != v for f, v in clean.items()):
                return data["eintraege"].get(key)
            entry.update(clean)
            entry.update({"art": art, "bezug": str(bezug)[:200], "text": str(text)[:MAX_TEXT],
                          "geaendert": _now(), "uebernommen": None})
            if not any(entry.get(f) for f in ("haken", "kommentar", "prio_wunsch", "status_wunsch")):
                data["eintraege"].pop(key, None)
                entry = None
            else:
                data["eintraege"][key] = entry
            self._save(data)
            return entry

    def add_note(self, art: str, text: str) -> dict:
        if art not in NOTIZ_ARTEN:
            raise FeedbackError(f"Unbekannte Art: {art}")
        if not text.strip():
            raise FeedbackError("Text fehlt")
        now = _now()
        note = {"id": f"n-{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(2)}", "art": art,
                "text": text.strip()[:MAX_TEXT], "erstellt": now, "geaendert": now, "uebernommen": None}
        with self._lock:
            data = self._load()
            data["notizen"].append(note)
            self._save(data)
        return note

    def _note(self, data: dict, note_id: str) -> dict:
        note = next((n for n in data["notizen"] if n.get("id") == note_id), None)
        if note is None:
            raise FeedbackError("Notiz nicht gefunden")
        if note.get("uebernommen"):
            raise FeedbackError("Notiz ist schon übernommen und lässt sich nicht mehr ändern")
        return note

    def update_note(self, note_id: str, art: str, text: str) -> dict:
        if art not in NOTIZ_ARTEN:
            raise FeedbackError(f"Unbekannte Art: {art}")
        if not text.strip():
            raise FeedbackError("Text fehlt")
        with self._lock:
            data = self._load()
            note = self._note(data, note_id)
            note.update({"art": art, "text": text.strip()[:MAX_TEXT], "geaendert": _now()})
            self._save(data)
            return note

    def delete_note(self, note_id: str) -> None:
        with self._lock:
            data = self._load()
            note = self._note(data, note_id)
            data["notizen"].remove(note)
            self._save(data)


def page_data(folder: Path, store: FeedbackStore) -> dict:
    """Doku + Rückmeldungen: verwaiste Rückmeldungen (Eintrag in der Doku geändert) gesondert aufgeführt."""
    data = collect(folder)
    store.hinweis = ""
    try:
        fb = store.load()
    except FeedbackError as e:
        fb = _empty()
        store.hinweis = str(e)
    data["rueckmeldungen"] = fb["eintraege"]
    data["notizen"] = fb["notizen"]
    data["datei"] = str(store.path)
    data["datei_hinweis"] = store.hinweis
    if data["hinweis"]:
        data["ohne_eintrag"] = []          # ohne Doku lässt sich nichts zuordnen
    else:
        keys = all_keys(data)
        data["ohne_eintrag"] = sorted(k for k in fb["eintraege"] if k not in keys)
    return data
