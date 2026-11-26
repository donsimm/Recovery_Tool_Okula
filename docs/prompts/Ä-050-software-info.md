# Ä-050 – Software-Bibliothek: Info-Feld (Spalte und Reiter)

Status: Entwurf · erstellt 26.11.2026 von der Projektleitung · Wunsch Dominik 26.11. · Freigabe: –

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag Ä-050 in `docs/AENDERUNGEN.md`,
Hilfe-Kapitel „Software installieren“ / „Die Software-Bibliothek“ in `okula_recovery/help_window.py`.
Lokaler Branch `agent/Ä-050`; nicht pullen, nicht pushen. 1 Commit.

## Ziel

Zu jedem Eintrag der Software-Bibliothek (*Extras → Software-Bibliothek …*) lässt sich ein freier Text **Info**
erfassen (z. B. „Lizenz im Tresor“, „nur für Lenovo-Modelle“, „vor Office installieren“). Geräte sind Okulas eigene
Mietgeräte in vielen Ausführungen – die Info dient den Technikern.

## Anforderungen

1. **Speichern:** neues Feld `info` (Text, mehrzeilig, max. ~2000 Zeichen) in den Metadaten des Eintrags
   (`software.py`, gleicher Mechanismus wie `program`/`version`/`publisher`, `update(…, info=…)`). Liegt auf dem NAS
   beim Eintrag → gilt für alle Tool-Rechner. **Nicht** mit dem bestehenden automatischen Feld `note`/`Entry.note`
   vermischen (das bleibt Erkennungs-Hinweis).
2. **Neue Version eines Programms** (Übernahme der Angaben vom Vorgänger, `_adopt`/`ADOPT_FIELDS`): `info` wird mit
   übernommen.
3. **Liste:** Spalte **„Info“ als 2. Spalte** direkt nach „Programm“; zeigt die erste Zeile (gekürzt, Ellipse),
   Tooltip der Zeile enthält den ganzen Text. Direkt in der Liste per Doppelklick bearbeitbar (einzeilig; enthält der
   Text schon mehrere Zeilen, öffnet Doppelklick stattdessen „Bearbeiten …“ auf dem Reiter Info oder ersetzt nur die
   erste Zeile – einfachste saubere Lösung wählen und in der Rückmeldung nennen). Suchfeld findet auch Text in Info.
4. **Bearbeiten-Dialog** (`SoftwareEditDialog`): zwei Reiter – **„Angaben“** (bisheriger Inhalt unverändert) und
   **„Info“** (mehrzeiliges Textfeld mit Rollbalken). Speichern wie die übrigen Felder.
5. Die Auswahl-Liste in *Software installieren …* (Gerät) zeigt die Info als Tooltip der Zeile, keine neue Spalte.
6. Demo-Speicher (Demo-Gerät) funktioniert gleich; ein Beispiel-Eintrag darf eine Info haben.

## Hilfe und Doku

- Hilfe (F1) „Die Software-Bibliothek“: Spaltenliste um „Info“ ergänzen, Reiter „Angaben“/„Info“ im Bearbeiten-Dialog
  beschreiben. Handbuch-Stil ohne Anrede; Namen exakt wie in der Oberfläche.
- Nur den eigenen Eintrag Ä-050 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum heute) –
  **Kurzübersicht und „Als Nächstes“ nicht anfassen** (macht Okuli). `docs/TESTS.md` kurzer Abschnitt „Ä-050“.

## Grenzen und Prüfung

- Nur `software.py`, `software_ui.py`, ggf. `demo_*`, Hilfe, Tests. Kein neuer Agent-Stick.
- Tests (unittest, Muster in `tests/test_software*.py`): Feld speichern/lesen, Übernahme bei neuer Version, Suche,
  Begrenzung der Länge. Ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`):
  `python3 -m unittest discover -s tests -t .` – alle grün vor dem Commit.
- Rückmeldung: was geändert, Commit, Testergebnis, Offenes.
