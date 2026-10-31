"""Suche in der Hilfe (F1) – ohne GTK, damit sie sich testen lässt.

Kapitel passen, wenn jedes Wort der Suche im Titel oder im Text (ohne Markup) vorkommt; Gross/Klein egal, Umlaute
in jeder Unicode-Form (NFC). Treffer werden im Pango-Markup gelb hinterlegt, ohne Tags zu verändern.
"""

from __future__ import annotations

import html
import re
import unicodedata

HIGHLIGHT = '<span background="#fff3b0" foreground="#000000">'   # Treffer (gelb wie die Garantie-Warnung)


def _norm(text: str) -> str:
    """Für den Vergleich: NFC (Umlaute als ein Zeichen), Gross/Klein egal."""
    return unicodedata.normalize("NFC", text).lower()


def plain(markup: str) -> str:
    """Text ohne Pango-Markup und ohne Entities."""
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def search_words(query: str) -> list[str]:
    return [w for w in _norm(query).split() if w]


def matches(chapter: tuple[str, str], query: str) -> bool:
    """Kapitel passt, wenn jedes Wort der Suche im Titel oder Text vorkommt (leere Suche = alle)."""
    title, text = chapter
    haystack = _norm(title + "\n" + plain(text))
    return all(w in haystack for w in search_words(query))


def find(query: str, chapters: list[tuple[str, str]]) -> list[str]:
    """Titel der passenden Kapitel in der Reihenfolge der Anleitung."""
    return [c[0] for c in chapters if matches(c, query)]


def highlight(markup: str, query: str) -> str:
    """Treffer im Text gelb hinterlegen – nur im Text, nie in Tags (Markup bleibt gültig)."""
    words = search_words(query)
    if not words:
        return markup
    pattern = re.compile("|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)), re.IGNORECASE)
    out = []
    for part in re.split(r"(<[^>]+>)", markup):
        if part.startswith("<"):
            out.append(part)
            continue
        text = unicodedata.normalize("NFC", html.unescape(part))
        pieces, last = [], 0
        for m in pattern.finditer(text):
            pieces.append(html.escape(text[last:m.start()], quote=False))
            pieces.append(HIGHLIGHT + html.escape(m.group(0), quote=False) + "</span>")
            last = m.end()
        pieces.append(html.escape(text[last:], quote=False))
        out.append("".join(pieces) if last else part)
    return "".join(out)
