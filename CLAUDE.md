# Hinweise für Claude Code – Okula Recovery Tool

Arbeitsbranch: `claude/blissful-goldberg-mo3xda` (einziger Branch). Sprache in Chat, Doku und Oberfläche: Deutsch (Schweiz, „ss“ statt „ß“).

## Sitzungsstart – immer zuerst

1. **`docs/PROJEKTLEITUNG.md` lesen:** Rollen (Projektleitung oder Umsetzungs-Agent), Ablauf Brainstorming → Prompt,
   Prompts in `docs/prompts/`. Projektleitung: danach `docs/UEBERGABE.md` lesen (falls vorhanden) und dort weitermachen.
2. **Projektleitung ändert keinen Code des Tools** (`okula_recovery/`, `tests/`, `install.sh`, `packaging/`) – auch nicht
   auf Zuruf; Code ändert nur ein Umsetzungs-Agent mit Prompt aus `docs/prompts/`. Im Zweifel nachfragen.
3. Gearbeitet wird nur über GitHub; Dominik installiert von Hand auf dem Server. Statuszeile (`.claude/`) nie entfernen.

## Schreibstil (Oberfläche, Hilfe F1, Meldungen)

- **Handbuch-Stil ohne Anrede:** weder „du“ noch „Sie“. Schritte im Infinitiv („Agent-Stick einstecken.“),
  Beschreibungen sachlich („Links stehen alle Geräte.“, „… lässt sich … verschieben“).
- Fortschritt und Log als Vorgang, nicht in Ich-Form: „Stick wird geprüft …“ statt „Prüfe Stick …“.
- Begriffe wie in der Oberfläche: Disk (Festplatte/SSD im Gerät), Zieldisk, Datenträger (USB/extern),
  Windows-Schlüssel, Agent-Stick.
- **Hilfe mitführen:** Jede neue oder geänderte Funktion → passendes Kapitel in `okula_recovery/help_window.py`
  im selben Commit anpassen (Menü- und Knopfnamen exakt wie in der Oberfläche).
  `tests/test_help.py` prüft das: Markup gültig, jeder Eintrag aus `MENU_LABELS` (ui.py) in der Hilfe,
  Querverweise „Kapitel <i>…</i>“ gültig, keine Anrede in Hilfe und Oberflächentexten.

## Notizen, Bugs, Ideen – Ablauf

1. **Zu Beginn jeder Sitzung** `docs/EINGANG.md` lesen. Stehen dort neue Einträge, diese einsortieren, bevor andere Arbeit beginnt.
2. **Einsortieren** in `docs/AENDERUNGEN.md`:
   - Bug → Tabelle „🐞 Bugs“ (`B-NNN`), Änderung/Verbesserung → „🔧 Änderungen“ (`Ä-NNN`), Idee → „💡 Ideen“ (`I-NNN`).
   - IDs fortlaufend je Kategorie, nie wiederverwenden. Kurz, technisch, mit Datum der Meldung.
   - Priorität (🔴/🟡/⚪) vorschlagen; Unklares als Frage an den Nutzer zurückmelden.
   - Testbedarf am realen System zusätzlich in `docs/TESTS.md` unter „Offen“ eintragen.
   - Danach die Einträge aus `EINGANG.md` entfernen (Kopfteil und Kommentar bleiben).
3. **Kurzübersicht** (Zähler + „Als Nächstes“) in `AENDERUNGEN.md` bei jeder Änderung aktualisieren.
4. **Erledigt:** Eintrag aus der Tabelle entfernen und mit Datum und ID ins „✅ Erledigt – Änderungsprotokoll“ übernehmen; Prüfung in `TESTS.md` ergänzen.
5. Entscheidungen (bewusst so gelöst / bewusst nicht gemacht) unter „📌 Entscheidungen“ festhalten.
6. **Gestrichen:** Zeile aus der Tabelle in `docs/PAPIERKORB.md` verschieben (Datum, Grund). Punkte im Papierkorb
   nicht wieder vorschlagen; neue Vorschläge vorher gegen Papierkorb und Tabellen auf Doppel prüfen.

## Tests

`python3 -m unittest discover -s tests -t .`
