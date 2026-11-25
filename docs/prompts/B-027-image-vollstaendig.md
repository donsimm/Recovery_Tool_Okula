# B-027 – Image gilt als fertig, obwohl eine Datei offen ist oder fehlt

Status: abgenommen (Okuli 25.11., Commit 8a0b686) · erstellt 25.11.2026 von der Projektleitung (Code-Review) · Freigabe: Dominik 25.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag B-027 in `docs/AENDERUNGEN.md`,
`docs/REVIEW-2026-11-25.md` Abschnitt „R-client“ Befunde **1, 7, 8, 9**. Lokaler Branch `agent/B-027`;
nicht pullen, nicht pushen. 1–2 Commits.

## Befunde (Zeilen laut Review, vor dem Ändern am Code nachprüfen)

1. **`agentclient.py` ~310–318 (Hoch, von Okuli bestätigt):** Bei `end` wird das Image abgeschlossen und umbenannt,
   ohne zu prüfen, ob eine Datei noch offen ist (`current is not None`), ob `begin` kam und ob alle Dateien aus
   `meta["plan"]` eingetroffen sind. Kein `fsync` vor dem Umbenennen.
2. **~244–248 (Tief):** Existiert der Zielordner, wird nur `%S` angehängt – kann erneut kollidieren; `work.mkdir`
   ohne `exist_ok` wirft rohen `FileExistsError` bei einem `.partial`-Rest.
3. **~61–64 (Tief):** Schlüsseldatei wird mit `O_TRUNC` nicht atomar geschrieben; leere/kaputte Datei → beim
   nächsten Start still ein neuer Schlüssel, alle Agent-Sticks lehnen ab.
4. **~762–776 (Tief):** Bricht die Verbindung nach Esc am Gerät ab, zählt das Tool selbst weiter und gibt „start“
   zurück → Disk wird trotz Esc gelöscht.

## Anforderungen

1. Bei `end` mit offener Datei, ohne `begin` oder mit fehlenden Dateien aus dem Plan: `AgentError` mit klarer
   Meldung („Image unvollständig: … fehlt“), `.partial` wird wie bei anderen Fehlern aufgeräumt, nichts wird als
   fertig gemeldet. Vor dem Umbenennen Dateien flushen und `fsync`en, danach den Elternordner `fsync`en.
2. Freien Ordnernamen in einer Schleife suchen (`-2`, `-3` …); ein `.partial`-Rest gleichen Namens wird nicht
   überschrieben, sondern ebenfalls übersprungen (nicht löschen – könnte zu einem laufenden Auftrag gehören).
3. Schlüsseldatei: in `.tmp` mit 0600 schreiben, `os.replace`. Ist die Datei vorhanden, aber leer/ungültig: **nicht**
   überschreiben, sondern verständlichen Fehler melden (Pfad nennen).
4. Countdown: Verbindungsverlust, nachdem der Agent den Countdown angenommen hat → „abgebrochen“ melden, nicht
   „start“. Selbst zählen nur, wenn der Agent den Befehl nicht kennt (alter Agent).
5. Tests (unittest, Muster in `tests/` für agentclient nachbilden): `end` mit offener Datei, ohne `begin`, mit
   fehlender Plan-Datei → Fehler und kein fertiger Ordner; vollständiges Image → fertig wie bisher; Ordner-Kollision
   und `.partial`-Rest; kaputte Schlüsseldatei → Fehler, Datei unverändert; Countdown-Verbindungsverlust → abgebrochen.
6. Doku: nur den eigenen Eintrag B-027 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum heute)
   verschieben – **Kurzübersicht und „Als Nächstes“ nicht anfassen** (macht Okuli). `docs/TESTS.md` kurzer Abschnitt
   „B-027“ (Image erstellen am Demo-Gerät, Ordnername, Esc im Countdown). Hilfe (F1) nur, wenn sichtbares Verhalten
   dort beschrieben ist.

## Grenzen

- Nur `okula_recovery/agentclient.py` und Tests dazu. **Nicht** `automation.py`, `jobs.py`, `winsetup.py`,
  `software.py`, `wintweaks.py` – dort arbeitet parallel B-028.
- Am Agent (`agent.py`) nichts ändern; kein neuer Agent-Stick nötig. Falls der Agent für Punkt 4 eine Änderung
  bräuchte: nur in der Rückmeldung beschreiben.
- Tests ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .` –
  alle grün vor dem Commit.
- Rückmeldung: was geändert, Commits, Testergebnis, Offenes.
