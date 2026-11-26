# Ä-052 + B-029 – USB-Vorgänge im Hintergrund, Abbrechen zuverlässig

Status: freigegeben · erstellt 26.11.2026 von der Projektleitung · Umfang wie mit Dominik besprochen (26.11.) · Start nach Ä-051

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge Ä-052 und B-029 in `docs/AENDERUNGEN.md`,
Hilfe-Kapitel zu *USB klonen*, *USB formatieren*, *Agent-USB-Stick erstellen*, *Boot-Stick* in
`okula_recovery/help_window.py`. Lokaler Branch `agent/AE-052`; nicht pullen, nicht pushen.
**Zwei Commits:** Teil A (B-029 Abbrechen/Gerät weg), Teil B (Ä-052 nicht modal, Auftragsliste).

## Befund B-029 (realer Fall 26.11.2026, Server)

09:29:25 *USB klonen* `sdb → sdc` (nur belegte Bereiche) gestartet. 09:29:37–47 meldet der Kernel für **beide** Sticks
„detected capacity change … to 0“ und „USB disconnect“ (Ursache am Server unklar: Hub/Wackelkontakt oder abgezogen),
danach melden sie sich neu an, später mit **anderen Namen** (`sda`/`sdb`/`sdc`). Dominik drückte *Abbrechen* – das
Tool „hing“ (Dialog blieb in „Wird abgebrochen …“). Ablauf heute: `usb_dialogs.py` → `stick_dialog.run_helper`
(Root-Helfer per sudo, `usbtools.py`), `HelperRun.cancel()` schreibt nur „CANCEL“ auf stdin; hängt der Helfer in
I/O auf ein verschwundenes Gerät, kommt das nie an und `_done` wird nicht aufgerufen.

## Teil A – B-029 (`usbtools.py`, `stick_dialog.py`, `usb_dialogs.py`, ggf. `stick.py`/`isostick.py`)

1. **Abbrechen erzwingen:** Reagiert der Helfer nach „CANCEL“ nicht innerhalb von ~15 s, das Tool beendet ihn
   (sudo-Kind: Prozessgruppe/`SIGTERM`, danach `SIGKILL` – der Benutzer darf den root-Helfer nicht direkt killen;
   saubere Lösung finden, z. B. Helfer startet Kinder in eigener Prozessgruppe und beendet sie bei stdin-EOF/
   „CANCEL“ selbst, Tool schliesst stdin; nötigenfalls `sudo -n HELPER kill <pid>`-Unterbefehl mit Prüfung, dass nur
   eigene Kinder getroffen werden). Danach immer `_done` mit „Abgebrochen“ – der Dialog darf nie hängen bleiben.
2. **Gerät verschwunden:** Helfer und Tool erkennen, wenn Quelle oder Ziel während des Vorgangs wegfällt (Gerät
   existiert nicht mehr / Grösse 0 / I/O-Fehler) → Abbruch mit Meldung „Datenträger getrennt – abgebrochen
   (<Modell, Seriennummer>)“, Ziel als unvollständig kennzeichnen.
3. **Identität statt Name:** Quelle und Ziel werden beim Start mit **Seriennummer (und Modell/Grösse)** festgehalten;
   der Helfer prüft vor dem ersten Schreiben und bei jedem neuen Öffnen, dass `/dev/sdX` noch dieselbe Seriennummer
   hat (`/dev/disk/by-id` bzw. `lsblk -o SERIAL`). Passt es nicht → Abbruch, nie auf ein anderes Gerät schreiben.
   Die Liste im Dialog zeigt Seriennummer bzw. Kurzform, damit gleiche Modelle unterscheidbar sind.
4. Gilt für alle vier Vorgänge (USB klonen, USB formatieren, Agent-USB-Stick, Boot-Stick aus ISO).
5. Tests: gemockte Prozesse (Helfer reagiert nicht auf CANCEL → nach Frist beendet, `_done` aufgerufen), Gerät
   verschwindet, Seriennummer passt nicht → kein Schreiben.

## Teil B – Ä-052 (`usb_dialogs.py`, `stick_dialog.py`, `os_dialogs.py` BootStick, `ui.py` Verdrahtung)

1. Die vier Fenster sind **nicht modal** (`modal=False`, weiter `transient_for`), lassen sich minimieren/verschieben;
   das Hauptfenster bleibt bedienbar.
2. Jeder laufende Vorgang erscheint zusätzlich in der **Auftragsliste** des Hauptfensters (Titel z. B. „USB klonen
   SanDisk … → SanDisk …“, Fortschritt in %, Ergebnis/Fehler, Abbrechen aus der Liste ruft dasselbe Abbrechen);
   bestehendes Muster der Auftragsliste (`jobs.JobManager`) nutzen, ohne Geräte-Verlauf.
3. **Schutz:** Ein Datenträger, der gerade beschrieben/gelesen wird, ist in allen USB-/Stick-Dialogen gesperrt
   (ausgegraut mit „wird gerade verwendet“). Fenster eines laufenden Vorgangs schliessen → Frage „Abbrechen?“ statt
   still schliessen (oder: Fenster schliesst, Vorgang läuft in der Auftragsliste weiter – einfachste sichere Lösung
   wählen und in der Rückmeldung nennen). **Tool beenden** während eines laufenden USB-Vorgangs → Rückfrage.
4. Mehrere Vorgänge gleichzeitig auf **verschiedenen** Datenträgern sind erlaubt.

## Hilfe und Doku

- Hilfe (F1) der vier Funktionen: läuft im Hintergrund, Auftragsliste, Abbrechen, „Datenträger getrennt“.
  Handbuch-Stil ohne Anrede, Namen exakt wie in der Oberfläche.
- Nur die eigenen Einträge Ä-052 und B-029 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum
  heute) – **Kurzübersicht und „Als Nächstes“ nicht anfassen**. `docs/TESTS.md` Abschnitt „Ä-052 / B-029“ (Klonen
  starten, im Hauptfenster weiterarbeiten; Abbrechen; Stick während Klon abziehen → Meldung, Tool bedienbar; zwei
  gleiche Sticks umstecken → kein Schreiben aufs falsche Gerät).

## Grenzen und Prüfung

- Keine Änderung an Agent/Agent-Stick-Inhalt; neuer Root-Helfer-Unterbefehl nur, wenn unvermeidbar (dann
  `install.sh`/sudoers prüfen und in der Rückmeldung nennen). `ui.py` nur Verdrahtung.
- Tests ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .` – alle
  grün vor jedem Commit.
- Rückmeldung: was geändert (Teil A/B), Commits, Testergebnis, Offenes, ob `sudo ./install.sh` nötig.
