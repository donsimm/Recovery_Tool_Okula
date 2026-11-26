# Ä-053 – Ordner senden: „Alle“ bei Software ersetzt den ganzen Ordner

Status: freigegeben · erstellt 26.11.2026 von der Projektleitung · Entscheid Dominik 26.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag Ä-053 in `docs/AENDERUNGEN.md`, Protokoll-Eintrag
**Ä-051** (Software wie Content), `docs/ORDNER-SENDEN.md`. Lokaler Branch `agent/AE-053`; nicht pullen, nicht pushen.
1 Commit.

## Ziel (Entscheid Dominik 26.11.)

Seit Ä-051 ersetzt *Ordner senden → Software …* jeden gewählten Eintrag einzeln – auch bei **„Alle“**; was auf dem
NAS gelöscht wurde, bleibt auf dem Gerät liegen. Neu:

1. **„Alle“** (Häkchen „Alle“, gespeicherte Auswahl „alle“/leer, alte Einstellungen „Software an“) ⇒ der ganze
   Ordner `Desktop\Software` wird **ersetzt** wie vor Ä-051 (alter Inhalt weg, neuer Stand vom NAS; sicheres Ersetzen:
   erst alles übertragen, dann tauschen).
2. **Einzelne Einträge** gewählt ⇒ wie Ä-051: nur diese ersetzen, Rest bleibt.
3. Sind zufällig alle Einträge einzeln angehakt, aber nicht „Alle“: gilt als „Alle“ (gleiches Ergebnis) – in der
   Oberfläche so beschriften, dass klar ist: „Alle – Ordner Software auf dem Gerät wird ganz ersetzt“.
4. Log/Verlauf: „Software: alle (Ordner ersetzt)“ bzw. Liste der Einträge.

## Hilfe, Doku, Grenzen

- Hilfe (F1) „Ordner senden“ und Automatisierung: Unterschied „Alle“ (ganz ersetzt) und einzelne Einträge. Handbuch-
  Stil ohne Anrede.
- `docs/ORDNER-SENDEN.md` nachführen. Nur den eigenen Eintrag Ä-053 in `docs/AENDERUNGEN.md` auf erledigt setzen und
  ins Protokoll (Datum heute) – **Kurzübersicht und „Als Nächstes“ nicht anfassen**. `docs/TESTS.md` in Abschnitt
  „Ä-051“ einen Punkt für „Alle“ ergänzen.
- Nur `distribute.py`, `jobs.py`, `automation_tab.py`/`automation.py` (falls nötig), `deploy.py` (falls nötig),
  Hilfe, Tests. **Nicht**: `usb_dialogs.py`, `stick_dialog.py`, `usbtools.py`, `stick.py`, `os_dialogs.py`, `ui.py`
  (parallel Ä-052/B-029), `nas.py`, `nasfiles.py`, `software.py`, `agentclient.py`, `backups.py`, `oslib.py`,
  `shrink.py` (parallel B-030). Möglichst ohne Agent-Änderung (sonst sagen, ob neuer Stick nötig).
- Tests: „Alle“ ⇒ ein Eintrag `Software` (ganz ersetzt), einzelne ⇒ nur diese, alte Einstellung ⇒ ganz.
  Ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .`
- Rückmeldung: was geändert, Commit, Testergebnis, Offenes.
