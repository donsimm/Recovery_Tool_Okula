# Ä-051 – Ordner senden: Software wie Content (Einträge einzeln wählen)

Status: abgenommen (Okuli 26.11., Commit ee9066e) · erstellt 26.11.2026 von der Projektleitung · Entscheide Dominik 26.11. (Umfang wie mit Dominik besprochen)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag Ä-051 in `docs/AENDERUNGEN.md`,
`docs/ORDNER-SENDEN.md`, Hilfe-Kapitel „Ordner senden“ in `okula_recovery/help_window.py`.
Lokaler Branch `agent/AE-051`; nicht pullen, nicht pushen. 1–2 Commits.

## Ausgangslage

`okula_recovery/distribute.py`: `Verteilen/Software` und `Verteilen/Test Files` sind fix (`FIXED`) und werden immer
ganz gesendet; `Verteilen/Content/<Projekt>` ist Auswahl (`projects`, `items_for`, `plan`), Ziel
`C:\Users\Public\Desktop\Content\<Projekt>`, erneut senden ersetzt nur die gewählten Projekte. Auswahl-UI in
`automation_tab.py` (Automatisierung und Dialog „Ordner senden“), Auftrag in `jobs.py` (~890), Gerät in `deploy.py`.
Auf dem NAS liegen in `Verteilen/Software` heute ~20 Unterordner (z. B. „Browser“, „OBS & plugin“, „Nvidia“) und
einzelne Dateien direkt im Hauptordner (z. B. `Reader_de_install.exe`).

## Anforderungen (Entscheide Dominik 26.11.)

1. **Software wird zur Auswahl** wie Content: Jeder Unterordner **und jede einzelne Datei** direkt in
   `Verteilen/Software` ist ein eigener, anhakbarer Eintrag (versteckte Dateien und Links nicht, alphabetisch,
   Ordner zuerst). Ziel auf dem Gerät: `Desktop\Software\<Eintrag>` (Datei → `Desktop\Software\<Datei>`).
2. **Erneut senden** ersetzt nur die gewählten Einträge; andere Inhalte unter `Desktop\Software` bleiben (gleiches
   sicheres Ersetzen wie bei Content: Zwischenordner/-datei, dann tauschen).
3. **Bedienung:** Rechtsklick → *Ordner senden* → **„Software …“** öffnet die Liste mit Häkchen (wie „Content …“);
   im Gerätefenster und im Dialog *Ordner senden* gleich. Knopf/Häkchen „Alle“ für schnelles Anhaken.
4. **Automatisierung / OS installieren / gespeicherte Auswahl:** Software-Auswahl wird wie die Content-Projekte
   gespeichert. **Rückwärtskompatibel:** alte Einstellung „Software“ = an ohne Liste ⇒ weiterhin **alles** senden
   (in der Oberfläche als „alle“ angezeigt); fehlen gespeicherte Einträge auf dem NAS, Hinweis im Log, Rest läuft.
5. **Test Files bleibt unverändert** (ganzer Ordner).
6. Verlauf/Log/Beschreibung (`describe`) nennen die gewählten Software-Einträge (gekürzt bei vielen).
7. Demo-Speicher (`demostore.py`) mit 2–3 Beispiel-Einträgen unter Software (Ordner und Datei).

## Hilfe und Doku

- Hilfe (F1) „Ordner senden“ und Automatisierung anpassen (Software … mit Auswahl; Test Files ganz). Handbuch-Stil
  ohne Anrede, Namen exakt wie in der Oberfläche.
- `docs/ORDNER-SENDEN.md` (Struktur, Tabelle Ziel) nachführen.
- Nur den eigenen Eintrag Ä-051 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum heute) –
  **Kurzübersicht und „Als Nächstes“ nicht anfassen**. `docs/TESTS.md` Abschnitt „Ä-051“.

## Grenzen und Prüfung

- Software-Bibliothek / *Software installieren* nicht anfassen (anderer Mechanismus). Kein neuer Agent-Stick,
  wenn das Gerät nur Einzeldateien/-ordner bekommt (falls der Agent geändert werden muss: sagen).
- Tests (unittest, Muster für distribute/automation): Liste der Einträge (Ordner + Dateien, versteckte/Links aus),
  `items_for`/`plan` mit Software-Auswahl, alte Einstellung = alles, Ersetzen nur gewählter Einträge, fehlende Einträge.
  Ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .`
- Rückmeldung: was geändert, Commits, Testergebnis, Offenes, ob neuer Agent-Stick nötig.
