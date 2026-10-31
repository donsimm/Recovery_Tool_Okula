"""Hilfe (F1): Suche (H24) und Aktualität (H25) – läuft ohne Display und ohne GTK."""

import ast
import re
import unicodedata
import unittest
from pathlib import Path

from okula_recovery import helpsearch

ROOT = Path(__file__).resolve().parent.parent
HELP_FILE = ROOT / "okula_recovery" / "help_window.py"


def load_chapters() -> list[tuple[str, str]]:
    """CHAPTERS aus help_window.py – per ast, damit kein GTK nötig ist."""
    for node in ast.walk(ast.parse(HELP_FILE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "CHAPTERS":
            return ast.literal_eval(node.value)
    raise AssertionError("CHAPTERS nicht gefunden")


CHAPTERS = load_chapters()
TITLES = [t for t, _ in CHAPTERS]


class SearchTest(unittest.TestCase):
    def test_find_filters_by_title_and_text(self):
        self.assertEqual(helpsearch.find("", CHAPTERS), TITLES)                   # leer = alle
        found = helpsearch.find("garantie", CHAPTERS)
        self.assertIn("Inventar, Garantie, Windows 11", found)
        self.assertIn("Probleme lösen", found)
        self.assertNotIn("USB klonen", found)
        self.assertEqual(helpsearch.find("GARANTIE", CHAPTERS), found)           # Gross/Klein egal
        self.assertEqual(helpsearch.find("xyzqq", CHAPTERS), [])
        # mehrere Wörter: alle müssen vorkommen
        self.assertLess(len(helpsearch.find("zieldisk klein", CHAPTERS)), len(helpsearch.find("zieldisk", CHAPTERS)))
        # Reihenfolge wie in der Anleitung
        self.assertEqual(found, [t for t in TITLES if t in found])

    def test_umlauts_any_unicode_form(self):
        nfd = unicodedata.normalize("NFD", "Gerät")
        self.assertEqual(helpsearch.find(nfd, CHAPTERS), helpsearch.find("gerät", CHAPTERS))
        self.assertTrue(helpsearch.find("gerät", CHAPTERS))

    def test_markup_not_searched(self):
        self.assertFalse(helpsearch.matches(("X", "<span foreground=\"#2e7d32\">grün</span>"), "foreground"))
        self.assertTrue(helpsearch.matches(("X", "A &amp; B"), "&"))

    def test_highlight_keeps_markup_valid(self):
        out = helpsearch.highlight("<b>Gerät</b> und gerät &amp; Co", "gerät &")
        self.assertEqual(out.count(helpsearch.HIGHLIGHT), 3)
        self.assertIn("<b>" + helpsearch.HIGHLIGHT + "Gerät</span></b>", out)
        self.assertIn(helpsearch.HIGHLIGHT + "&amp;</span>", out)
        self.assertEqual(helpsearch.highlight("<i>x</i>", ""), "<i>x</i>")
        self.assertEqual(helpsearch.highlight('<span foreground="#c62828">rot</span>', "span"),
                         '<span foreground="#c62828">rot</span>')                 # Tags bleiben unberührt
        for title, text in CHAPTERS:
            for q in ("a", "Gerät", "Ctrl", "<b>", "&", "Kapitel Image"):
                check_markup(self, helpsearch.highlight(text, q), f"{title} / {q}")

    def test_ctrl_f_documented(self):
        text = dict(CHAPTERS)["Tastenkürzel"]
        self.assertIn("Ctrl+F", text)
        self.assertIn("Ctrl+F", dict(CHAPTERS)["Überblick"])


def check_markup(case: unittest.TestCase, markup: str, where: str) -> None:
    """Pango-Markup gültig? Mit Pango, wenn vorhanden – sonst als XML mit den Pango-Tags."""
    try:
        import gi
        gi.require_version("Pango", "1.0")
        from gi.repository import GLib, Pango
    except (ImportError, ValueError):
        Pango = None
    if Pango is not None:
        try:
            Pango.parse_markup(markup, -1, "\0")
        except GLib.Error as e:
            case.fail(f"{where}: {e}")
        return
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(f"<markup>{markup}</markup>")
    except ET.ParseError as e:
        case.fail(f"{where}: {e}")
    allowed = {"markup", "b", "i", "u", "s", "tt", "big", "small", "sub", "sup", "span"}
    bad = {el.tag for el in root.iter()} - allowed
    case.assertFalse(bad, f"{where}: unbekannte Tags {bad}")



# ---------- H25: Hilfe bleibt aktuell ----------

UI_FILE = ROOT / "okula_recovery" / "ui.py"
PACKAGE = ROOT / "okula_recovery"


def load_menu_labels() -> dict[str, list]:
    for node in ast.walk(ast.parse(UI_FILE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "MENU_LABELS":
            demo = next(n.value.value for n in ast.walk(ast.parse(UI_FILE.read_text(encoding="utf-8")))
                        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "DEMO_LABEL")
            src = ast.unparse(node.value).replace("DEMO_LABEL", repr(demo))
            return ast.literal_eval(src)
    raise AssertionError("MENU_LABELS nicht gefunden")


def clean_label(label: str) -> str:
    """„Inven_tar exportieren (CSV/PDF) …“ → „Inventar exportieren (CSV/PDF)“."""
    return label.replace("_", "").removesuffix(" …").strip()


# Anrede: „du“-Formen immer, „Sie/Ihr/Ihnen“ gross geschrieben (auch am Satzanfang umformulieren)
DU = re.compile(r"\b(du|dein|deine|deinen|deinem|deiner|deines|dich|dir|euch|euer|eure)\b", re.IGNORECASE)
SIE = re.compile(r"\b(Sie|Ihr|Ihre|Ihren|Ihrem|Ihrer|Ihres|Ihnen)\b")
# Ich-Form am Anfang eines Satzteils, z. B. „Prüfe …“, „– kopiere alles 1:1“
FIRST_PERSON = re.compile(
    r"(?:^|[:–·(] |\n)(prüfe|lade|schreibe|kopiere|erstelle|formatiere|lösche|entpacke|hänge|teste|berechne|suche|"
    r"warte|starte|lese|übertrage|vergleiche|setze|baue|packe|bereite|hole|sende|teile|spiele|installiere|richte|"
    r"fahre|verkleinere|sichere|passe|übernehme|splitte|lege|aktiviere|überspringe|ersetze|verschiebe|überschreibe|"
    r"erzeuge|frage|öffne|trenne|verbinde)\b", re.IGNORECASE)


def ui_strings() -> list[tuple[str, int, str]]:
    """Alle Zeichenketten im Programm (ohne Docstrings) – Oberfläche, Meldungen, Agent-Bildschirm."""
    found = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            # nur Text mit Leerzeichen (Sätze) – keine Schlüssel wie "dir" im Protokoll
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings \
                    and " " in node.value.strip():
                found.append((path.name, node.lineno, node.value))
    return found


class HelpUpToDateTest(unittest.TestCase):
    def test_a_markup_valid(self):
        for title, text in CHAPTERS:
            check_markup(self, text, title)

    def test_b_every_menu_entry_in_help(self):
        menus = load_menu_labels()
        self.assertEqual(list(menus), ["_Menü", "_Tools", "E_xtras", "_Hilfe"])
        help_text = " ".join(helpsearch.plain(t) for _, t in CHAPTERS)
        missing = [f"{clean_label(m)} → {clean_label(label)}"
                   for m in ("_Menü", "_Tools", "E_xtras") for label in menus[m]
                   if label and clean_label(label) not in help_text]
        self.assertEqual(missing, [], "Menüeinträge fehlen in der Hilfe (help_window.py)")

    def test_c_cross_references(self):
        for title, text in CHAPTERS:
            for ref in re.findall(r"Kapitel\s+<i>(.*?)</i>", text):
                self.assertIn(ref, TITLES, f"{title}: Kapitel „{ref}“ gibt es nicht")
        self.assertEqual(TITLES[-2:], ["Tastenkürzel", "Demo-Gerät"])

    def test_d_no_direct_address(self):
        problems = []
        for title, text in CHAPTERS:
            plain = helpsearch.plain(text)
            for rx in (DU, SIE):
                problems += [f"Hilfe „{title}“: {m.group(0)}" for m in rx.finditer(plain)]
        for name, line, text in ui_strings():
            for rx in (DU, SIE):
                problems += [f"{name}:{line}: {m.group(0)} in „{text[:60]}“" for m in rx.finditer(text)]
        self.assertEqual(problems, [])

    def test_e_progress_not_first_person(self):
        """Fortschritt und Log als Vorgang („Stick wird geprüft …“), nicht in Ich-Form („Prüfe Stick …“)."""
        problems = [f"{name}:{line}: „{m.group(0).strip()}“ in „{text[:70]}“"
                    for name, line, text in ui_strings() for m in FIRST_PERSON.finditer(text)]
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
