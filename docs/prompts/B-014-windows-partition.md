# B-014 – Direktinstallation: Windows-Partition nicht gefunden (mit Ä-039)

Status: freigegeben · erstellt 17.11.2026 von der Projektleitung · Freigabe: Dominik 17.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, die Einträge **B-014** und **Ä-039** in
`docs/AENDERUNGEN.md`, in `docs/TECHNIK.md` den Abschnitt zur Windows-Direktinstallation, `docs/TESTS.md` Abschnitte
16, 17 und 20. Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde (lokaler Branch `agent/B-014`);
nicht pullen, nicht pushen.

## Ziel

*OS installieren …* mit einer Windows-ISO läuft auch dann ohne Eingriff durch, wenn auf der Zieldisk schon ein Windows
(aus einer früheren Direktinstallation) liegt – auch mehrmals hintereinander. Geht trotzdem etwas schief, zeigt das
Gerät verständlich, was los ist, und das Protokoll enthält genug, um die Ursache zu finden. Ä-039 wird dabei miterledigt.

## Befund (CompactPlayer 1, Kingston SH103S3 120 GB, SATA, UEFI)

- 12.11. 1. Versuch: lief durch (Disk war vorher MBR mit anderer Aufteilung). Windows hing danach in der
  OOBE-Schleife (B-012) und wurde hart ausgeschaltet.
- 12.11. 2. Versuch und 17.11. (Installation `421a8299`): `install.log` = „Setup-Partition D:, Windows-Partition :“,
  FEHLER. In Windows PE (Fotos 17.11.):
  - `list disk`: nur Datenträger 0 (111 GB, GPT) – der Agent-Stick ist in WinPE nicht sichtbar.
  - `list volume`: C: „Windows“ NTFS 105 GB · D: „OKULASETUP“ FAT32 · SYSTEM FAT32 (versteckt).
  - `D:\okula\*` vom 17.11. 09:34 (neu, Kennung 421a8299) – die Setup-Partition ist also aktuell.
  - `C:\`: **alter Inhalt** – Bezeichnung „Windows“ (vergibt nur `install.cmd`: `format /v:Windows`), Ordner
    PerfLogs/Program Files/Users (Daten aus dem Win10-Image), `Windows` 17.11. 09:37, **kein** `okula-421a8299.target`,
    103 GB frei.
  - Erwartet war C: = „OKULAWIN“ (`wininstall._mkntfs`, `mkntfs -Q -F -L OKULAWIN`) mit der Markierungsdatei.
- Inventar vor dem Versuch (09:30): gleiche GPT-Aufteilung wie beim Vorversuch (sda1 ESP, sda2 MSR, sda3 113 055 367 168
  Bytes NTFS „Windows“, sda4 OKULASETUP) → `layout()` erzeugt dieselben Startsektoren, die neue Windows-Partition
  liegt genau über der alten.
- Win10-ISO → `split` aktiv: sda3 dient zuerst als ext4-Zwischenablage (`_mkstage`, mkfs.ext4 verwirft dabei
  standardmässig die Blöcke per Discard/TRIM), danach `mkntfs -Q`, Markierung über ntfs-3g, `sync`, dann sauberer
  Neustart (`systemctl reboot`).
- Umgehung am Gerät (funktioniert): in WinPE `format C: /fs:ntfs /q /y`, `echo Okula > C:\okula-421a8299.target`,
  `D:\okula\install.cmd D`.
- In VMs (qcow2) trat der Fehler bisher nicht auf – dort war die Disk vorher leer bzw. anders aufgeteilt.

## Anforderungen

1. **Ursache eingrenzen** und in `TECHNIK.md` festhalten (was belegt ist, was vermutet). Zu prüfen u. a.: Wie kann
   Windows PE nach `mkntfs -Q` + ntfs-3g-Schreiben den alten NTFS-Stand sehen (alter Backup-Bootsektor am
   Partitionsende, alte `$MFT`/`$LogFile`-Reste, Windows-Journal-Wiederholung, Schreibvorgänge erreichen die SSD
   nicht – z. B. nach Discard auf einer SandForce-SSD)? Quellen nennen (ntfs-3g/mkntfs-Doku, Microsoft Learn).
2. **Vor dem Formatieren alte Strukturen sicher entfernen** – für die Windows-Partition (und sinnvollerweise alle
   neu angelegten Partitionen): Signaturen löschen (`wipefs -a <partition>`) und Anfang **und** Ende der Partition
   mit Nullen überschreiben (mind. die ersten 16 MiB und das letzte 1 MiB, inkl. NTFS-Backup-Bootsektor), mit
   `O_DIRECT`/`conv=fsync` bzw. `sync`. Kein Discard als einziges Mittel (Lesen nach TRIM ist nicht garantiert null).
3. **Prüfung auf dem Agent nach dem Schreiben:** nach `mkntfs` + Markierung: `sync`, Seitencache verwerfen
   (`/proc/sys/vm/drop_caches` bzw. `blockdev --flushbufs`), dann direkt von der Disk prüfen, dass Bezeichnung
   „OKULAWIN“ und `okula-<id>.target` vorhanden sind (z. B. erneut einhängen nur lesend). Schlägt das fehl → Auftrag
   bricht mit klarer Meldung im Tool ab („Schreiben auf die Disk wird nicht übernommen – Disk prüfen“) statt erst im
   WinPE zu scheitern; kein Neustart.
4. **`install.cmd` robuster:** Findet es die Markierung nicht, sucht es die Windows-Partition zusätzlich über die
   Volume-Bezeichnung „OKULAWIN“ (z. B. `vol`/`label`-Ausgabe) – nur wenn **genau eine** passt. Ein Laufwerk mit
   altem Windows o. ä. wird **nie** auf Verdacht formatiert.
5. **Ä-039 – Fehlerfall verständlich:** Im Fehlerfall schreibt `install.cmd` ins `install.log`: Laufwerksliste
   (`echo list volume | diskpart` bzw. Skriptdatei), je Laufwerk C–Z ob vorhanden, Bezeichnung und ob eine
   `okula-*.target` darauf liegt. Im Editor oben deutlich: „Nach dem Schliessen dieses Fensters schaltet sich das
   Gerät aus. Für eine Eingabeaufforderung vorher Shift+F10 drücken.“ (Wortlaut im Handbuch-Stil, nur ASCII in der
   .cmd – Umlaute als ae/oe/ue). Prüfen, ob Shift+F10 in diesem Zustand wirklich eine Eingabeaufforderung öffnet; sonst
   den Weg über *Datei → Öffnen* → `X:\Windows\System32\cmd.exe` nennen.
6. Tests: Löschen von Anfang/Ende (auf Probe-Datei/Loop-Gerät, wo ohne root nicht möglich → überspringen wie
   bestehende Tests), Prüfung nach dem Schreiben (Fehlerfall gemeldet, kein Neustart), `install.cmd`-Text (Suche über
   Bezeichnung nur bei genau einem Treffer, Diagnose im Fehlerfall, nur ASCII, CRLF).

## Nicht Teil dieses Auftrags

- B-013 (OEM-Schlüssel/SetupComplete), Audit-Modus-Logik (I-038), Kontoname (B-012).
- Änderungen an der Partitionsaufteilung (`layout()`) ausser falls zwingend für die Lösung – dann begründen.
- Disk-Test/SMART-Auswertung der SSD.

## Hinweise zum Code

- `okula_recovery/wininstall.py`: `install()`, `_mkntfs`, `_mkstage`, `_mkfat`, `_mount`, `layout()`.
- `okula_recovery/winsetup.py`: `install_cmd()` (Vorlage, `LETTERS`, `target_marker`).
- Agent betroffen (neuer Agent-Stick nötig)? **ja** (`wininstall.py` läuft auf dem Agent); `install.cmd` wird vom Tool
  erzeugt.
- Reihenfolge: zuerst Agent (Löschen, Prüfung), dann `install.cmd`, zuletzt Hilfe/Doku.

## Oberfläche und Texte

- Keine neuen Menüs. Meldungen im Handbuch-Stil, Fortschritt als Vorgang („Alte Daten auf der Windows-Partition
  werden gelöscht …“, „Windows-Partition wird geprüft …“).
- Hilfe (F1), Kapitel zur Direktinstallation: Abschnitt „Fehler am Gerät“ (Editor mit `install.log`, nicht schliessen,
  Shift+F10, was im Protokoll steht).

## Abnahmekriterien

- [ ] Agent löscht Anfang und Ende der neuen Partitionen vor dem Formatieren und prüft die Windows-Partition nach dem
      Schreiben direkt von der Disk; Fehlerfall → klare Meldung im Tool, kein Neustart
- [ ] `install.cmd`: Markierung → sonst genau ein „OKULAWIN“ → sonst Fehler mit Diagnose im `install.log` und Hinweis
      zum Ausschalten/Shift+F10
- [ ] Ursache in `TECHNIK.md` (belegt/vermutet, Quellen)
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests wie oben
- [ ] Hilfe (F1) in `okula_recovery/help_window.py` angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: B-014 und Ä-039 ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Abschnitt 20 ergänzen (Fehlerfall-Diagnose sichtbar; Meldung bei nicht übernommenem Schreiben)
- [ ] Demo-Gerät: nicht nötig

## Abschluss

1. Ein Commit (oder wenige, sinnvoll getrennt) mit der ID im Titel, z. B. `B-014: Windows-Partition sicher löschen und
   prüfen`, **nur lokal** auf dem Branch `agent/B-014` – **nicht pushen**, das macht Okuli nach der Abnahme. **Nur
   eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit danach ist ok).
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis, ob ein neuer Agent-Stick nötig ist, Schritte für
   den Server (`git pull && sudo ./install.sh`), Befund zur Ursache, offene Punkte oder Abweichungen vom Prompt.
