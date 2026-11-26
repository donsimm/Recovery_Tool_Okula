# B-030 – Umbenennen nach dem Laden scheitert auf dem NAS („Keine Berechtigung“)

Status: freigegeben · erstellt 26.11.2026 von der Projektleitung · Freigabe: Dominik 26.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag B-030 in `docs/AENDERUNGEN.md`.
Lokaler Branch `agent/B-030`; nicht pullen, nicht pushen. 1 Commit.

## Befund (realer Fall 26.11.2026, 11:44)

*Software-Bibliothek → Ordner laden …* mit dem Office-Ordner (3,9 GB, sehr viele Dateien): Kopie komplett, Erkennung
ok (Name `office-16.0.20625.20142`), dann Fehler
`[Errno 13] Keine Berechtigung: '/mnt/okula-nas/Software-Bibliothek/.00343525d387.partial' ->
'/mnt/okula-nas/Software-Bibliothek/office-16.0.20625.20142'` – `software.load` (~Zeile 1331 `partial.rename`),
danach `.partial` korrekt gelöscht. NAS: CIFS `vers=3.1.1,cache=strict` (Synology). Das Tool hielt keine Datei offen
(von Okuli geprüft). Wahrscheinlich: SMB verweigert das Umbenennen eines Ordners, solange darin eine Datei offen ist –
der Linux-CIFS-Client schliesst frisch geschriebene Dateien verzögert (deferred close), ggf. hält das NAS
(Indexierung/Virenscan) neue Dateien kurz offen. Kleine Einträge waren bisher nie betroffen.

## Anforderungen

1. Gemeinsame Funktion (z. B. `nas.rename_retry(src, dst, attempts=10, pause=2.0)`): `rename`; bei
   `PermissionError`/`EACCES`/`EBUSY` warten und erneut versuchen (insgesamt ~20 s), **nie** wenn `dst` schon
   existiert (dann sofort Fehler wie bisher). Andere Fehler sofort weiterreichen. Optional vor dem ersten Versuch
   `os.sync()` bzw. kurzer Wartevorgang nur, wenn es nachweislich hilft – nicht raten.
2. Verwenden überall, wo nach grossem Schreiben ein `.partial`/Arbeitsordner auf dem NAS umbenannt wird:
   `software.py` (Laden), `agentclient.py` (Image fertig, ~405), `backups.py` (~317), `nasfiles.py` (~286),
   `oslib.py` (~578), `shrink.py` (~468). Verhalten sonst unverändert (Aufräumen bei Fehler bleibt).
3. Scheitert es endgültig: verständliche Meldung, z. B. „Kopie fertig, aber das NAS lässt den Ordner nicht
   umbenennen (Datei noch geöffnet?) – nochmals laden; bleibt es, NAS-Indexierung/Virenscan für diesen Ordner prüfen“.
   Fortschritt/Log zeigt „Ordner wird fertiggestellt …“, solange versucht wird.
4. Tests: gemocktes `rename` (erst 3× `PermissionError`, dann ok → ok; immer `PermissionError` → Meldung nach
   Versuchen; Ziel existiert → sofort Fehler; anderer Fehler → sofort). Kein echtes Warten in Tests (Pause
   injizierbar).

## Doku und Grenzen

- Nur den eigenen Eintrag B-030 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum heute) –
  **Kurzübersicht und „Als Nächstes“ nicht anfassen**. `docs/TESTS.md` kurzer Abschnitt „B-030“ (Office-Ordner
  erneut laden). Hilfe nur, falls dort Fehler beim Laden beschrieben sind.
- **Nicht** ändern: `usb_dialogs.py`, `stick_dialog.py`, `usbtools.py`, `stick.py`, `os_dialogs.py`, `ui.py`,
  `help_window.py` ausser wenn zwingend (parallel arbeitet Ä-052/B-029 dort). Kein neuer Agent-Stick.
- Tests ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .`
- Rückmeldung: was geändert, Commit, Testergebnis, Offenes.
