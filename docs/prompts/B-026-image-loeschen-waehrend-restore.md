# B-026 – Image lässt sich löschen/verschieben, während es zurückgespielt wird

Status: offen · erstellt 25.11.2026 von der Projektleitung (Code-Review) · Freigabe: Dominik 25.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag B-026 in `docs/AENDERUNGEN.md`,
`docs/REVIEW-2026-11-25.md` (R-ui Befund 1). Lokaler Branch `agent/B-026`; nicht pullen, nicht pushen. 1–2 Commits.

## Befund (am Code bestätigt)

- `jobs.Job` hat `source`; gesetzt wird es nur bei Datei-Backups (`ui.py` ~4068, ~4081), geprüft nur in
  `delete_backup` (`ui.py` ~1851).
- Zurückspielen (`start_restore` ~3794/3845), Direktinstallation mit ISO (`start_install` ~3928), Zwilling (~2799)
  und Automatisierung (`automation.py` ~462, Image aus `s.image`) lesen eine Datei/einen Ordner auf dem NAS, setzen
  aber kein `source`.
- `on_delete_image` (~1406), `drop` (~1067, `archive.move_image`/`move_folder`), Verschieben nach „Nicht
  einsortiert“ (~1016), Ordner löschen (`archive.delete_folder`, `oslib.delete_folder`) und
  `delete_old_demo_images` (~839) prüfen keine laufenden Aufträge → Restore bricht mitten im Schreiben ab,
  Kundendisk halb beschrieben.

## Anforderungen

1. Jeder Auftrag, der ein Image/ISO/Software vom NAS liest, trägt den gelesenen Pfad in `Job.source` ein
   (Restore, Zwilling, Installation, Automatisierung; Automatisierung: Job wird in `automation.py` angelegt – dort nur
   die Zeile ergänzen, die `source` setzt, sonst nichts in `automation.py` ändern, dort arbeitet parallel B-025).
2. Eine gemeinsame Prüfung (z. B. `jobs.JobManager.busy_paths()` / `in_use(path)`), die auch Ordner abdeckt:
   Löschen oder Verschieben eines Ordners ist gesperrt, wenn ein laufender Auftrag einen Pfad darin liest.
3. Löschen, Verschieben (Drag-and-Drop, „Nicht einsortiert“), Ordner löschen/verschieben und Demo-Aufräumen prüfen
   damit; bei Treffer Meldung „… wird gerade von ‚<Auftrag>‘ verwendet – erst nach Ende löschen/verschieben“, nichts tun.
   `delete_backup` auf dieselbe Prüfung umstellen.
4. Tests: Prüfung mit laufendem/fertigem Job, Datei und übergeordneter Ordner, Demo-Aufräumen überspringt belegte Images.
5. Doku: Eintrag B-026 in `docs/AENDERUNGEN.md` auf erledigt und ins Protokoll (25.11.), `docs/TESTS.md` kurzer
   Abschnitt „B-026“ (Demo-Gerät: Zurückspielen starten, Image bzw. Ordner löschen/verschieben → Meldung, Restore
   läuft durch).

## Grenzen

- Kein Umbau von `ui.py` (Ä-049 ist später), nur die nötigen Stellen.
- Nicht in `filebackup.py`, `backups.py` ändern; in `automation.py` nur Punkt 1.
- Tests ausführen: `python3 -m unittest discover -s tests -t .` – alle grün vor dem Commit.
