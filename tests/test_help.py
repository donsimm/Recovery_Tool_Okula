"""Hilfe (F1): Suche (H24) und Aktualität (H25) – läuft ohne Display und ohne GTK."""

import ast
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


if __name__ == "__main__":
    unittest.main()
