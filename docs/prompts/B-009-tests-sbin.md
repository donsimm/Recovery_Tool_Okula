# B-009 – Tests grün auch als normaler Benutzer (sbin-Pfad, Root-Test)

Status: abgenommen (Commit 3ef6bd7) · Abnahme Okuli 10.11.: Diff, Agent-Importe vollständig, 526 Tests grün mit und ohne sbin im PATH · erstellt 10.11.2026 von der Projektleitung · Freigabe: Dominik 10.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, den Eintrag B-009 in `docs/AENDERUNGEN.md`, `okula_recovery/imaging.py`,
`okula_recovery/clonezilla.py` (`SBIN_DIRS`, `find_tool`), `tests/test_imaging.py`, `tests/test_jobs.py`.
Gearbeitet wird in der eigenen Kopie (lokaler Branch `agent/B-009`); nicht pullen, nicht pushen.
Shell-Befehle einzeln ausführen.

## Ziel

`python3 -m unittest discover -s tests -t .` läuft als normaler Benutzer (ohne `/usr/sbin` im PATH, ohne root)
grün durch. Im Betrieb (Agent als root) ändert sich nichts.

## Befund (Okuli, 10.11.)

- Rot ohne `/usr/sbin` im PATH, Fehler „No such file or directory: 'sfdisk'“:
  `test_imaging` ConsoleAndPowerTest.test_image_shows_progress_on_console, EndToEndTest.test_full_image,
  EndToEndTest.test_failure_leaves_no_partial; `test_jobs` ParallelJobsTest.test_two_disks_in_parallel_same_disk_refused.
- RealPartcloneTest.test_ext4_roundtrip braucht Schreibrecht auf `/var/log/partclone.log` (nur root).
- `clonezilla.py` löst das Problem schon mit `SBIN_DIRS` + `find_tool()`.

## Anforderungen

1. Externe Systemwerkzeuge in `imaging.py` (mindestens `sfdisk`, `partclone.*`, und wo gleich betroffen weitere
   sbin-Werkzeuge) werden auch gefunden, wenn `/usr/sbin`/`/sbin` nicht im PATH sind. Bestehendes Muster
   wiederverwenden (`find_tool`/`SBIN_DIRS` – bei Bedarf an einen gemeinsamen Ort verschieben, z. B. ein kleines
   Hilfsmodul, und `clonezilla.py` darauf umstellen). Keine Duplikate.
2. Auch die Verfügbarkeitsprüfung (`imaging.py` um Zeile 119, `shutil.which(...)`) nutzt dieselbe Suche.
3. RealPartcloneTest.test_ext4_roundtrip: sauber überspringen (`skipUnless`/`skipTest` mit verständlichem Grund),
   wenn `/var/log/partclone.log` nicht beschreibbar ist – oder partclone so aufrufen, dass das Log anderswo landet
   (`-L <pfad>`), falls das ohne Verhaltensänderung im Betrieb geht. Lieber skippen als den Betrieb ändern.
4. Keine Änderung am Verhalten im Betrieb; Aufrufe der Tests mit gesetztem PATH müssen weiterhin grün sein.

## Nicht Teil dieses Auftrags

- Andere Module (`stick.py`, `wininstall.py`, `isostick.py` …) nur anfassen, wenn dort Tests aus demselben Grund
  rot sind. Kein grosser Umbau aller `shutil.which`-Aufrufe.
- Keine Oberflächen- oder Hilfeänderung (Hilfe F1 bleibt unverändert, da keine Funktion für Nutzer ändert).

## Hinweise zum Code

- Agent betroffen (neuer Agent-Stick nötig)? Code in `imaging.py` läuft auf dem Agent – Verhalten bleibt aber gleich
  (dort ist root mit sbin im PATH). Im Abschluss klar sagen, ob ein neuer Stick nötig ist (Erwartung: nein, optional).

## Prüfung

- Tests als normaler Benutzer ohne sbin: `env PATH=/usr/local/bin:/usr/bin:/bin python3 -m unittest discover -s tests -t .`
  → alles grün (Skips erlaubt, mit Grund).
- Zusätzlich normal: `python3 -m unittest discover -s tests -t .`

## Abnahmekriterien

- [ ] Beide Testläufe oben grün; der Root-Test meldet einen verständlichen Skip-Grund
- [ ] Neuer Test: Werkzeugsuche findet ein Programm in einem sbin-Ordner, wenn PATH ihn nicht enthält
- [ ] `docs/AENDERUNGEN.md`: B-009 ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: – (kein Test am realen System nötig, ausser Hinweis „Image erstellen/zurückspielen wie bisher“, falls Agent-Code geändert)
- [ ] `docs/TECHNIK.md`: kurzer Satz zur Werkzeugsuche (sbin), wenn es dort einen passenden Abschnitt gibt

## Abschluss

1. Ein Commit `B-009: Tests grün ohne sbin im PATH`, **nur lokal** auf `agent/B-009` – **nicht pushen**.
   **Nur eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit danach ist ok).
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis (beide Läufe), ob ein neuer Agent-Stick nötig ist,
   offene Punkte oder Abweichungen vom Prompt.
