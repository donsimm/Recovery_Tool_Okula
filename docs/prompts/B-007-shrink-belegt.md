# B-007 – Anpassen an kleinere Disk: belegte Blöcke richtig lesen

Status: abgenommen (Commit abf61f8) · Abnahme Okuli 10.11.: Tests, echter Kopf p4 ergibt 397,7 GB belegt

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, den Eintrag B-007 in `docs/AENDERUNGEN.md`, `docs/KLEINERE-DISK.md`,
`okula_recovery/shrink.py`, `tests/test_shrink.py`. Gearbeitet wird in der eigenen Kopie (lokaler Branch
`agent/B-007`); nicht pullen, nicht pushen. Shell-Befehle einzeln ausführen.

## Ziel

Die Prüfung „Image an die kleinere Disk anpassen“ (Ä-002, auch im Dialog von Ä-037) muss die belegten Daten einer
Partition richtig bestimmen. Heute meldet sie bei grossen partclone-Images „belegt 0.0 GB … möglich“, obwohl hunderte
GB belegt sind.

## Befund (Okuli, 10.11.)

Kopf von `nvme0n1p4.ntfs.pcl.zst` (1-TB-Image, Format `0002`), `struct.unpack_from("<QQQQI", data, 52)`:
`(999559266304, 244033023, 0, 97088142, 4096)` → `device_size, totalblock, usedblocks=0, used_bitmap=97088142, block_size`.
Auch die kleine Partition p1 desselben Images: `(523239424, 127743, 0, 97926, 4096)`. partclone schreibt hier
`usedblocks = 0`; die tatsächliche Zahl belegter Blöcke steht im nächsten Feld. `parse_pcl_header` liest nur
`usedblocks` → `used = 0`.

## Anforderungen

1. `parse_pcl_header` (Format 0002): Ist `usedblocks == 0` und das nächste Feld > 0 und ≤ `totalblock`, dieses als
   belegte Blöcke verwenden. Ist beides 0 oder unplausibel (> totalblock), **nicht** 0 annehmen, sondern
   `ShrinkError("Belegter Platz im Image nicht lesbar – Anpassen nicht möglich")` – lieber ablehnen als falsch erlauben.
   Format 0001 unverändert.
2. Prüfen, ob `used_bytes` (Ä-037, Platzprüfung) und alle anderen Aufrufer denselben Weg nutzen – dann sind sie mit
   behoben; sonst angleichen.
3. Tests in `tests/test_shrink.py`: Kopf mit `usedblocks=0, used_bitmap=97088142` → `used == 97088142 * 4096`;
   beide 0 → `ShrinkError`; unplausibel → `ShrinkError`; bestehender Fall (usedblocks gesetzt) unverändert. Die
   Köpfe als Bytes im Test nachbauen (kein NAS-Zugriff).
4. `docs/AENDERUNGEN.md`: B-007 ins „✅ Erledigt“-Protokoll, Kurzübersicht (Bugs) aktualisieren. `docs/TESTS.md`:
   Prüfschritt unter „Offen“ (Abschnitt 13 ergänzen): „1-TB-Image `2026-10-29_1133_nvme0n1` auf VM mit 64 GB →
   Anpassen: nicht möglich (belegt ~397 GB)“. `docs/TECHNIK.md`: Satz zum Feld `used_bitmap` bei Ä-002.
5. Hilfe (F1) nur anpassen, falls dort etwas Falsches steht (vermutlich nicht nötig).

## Nicht Teil dieses Auftrags

- Keine Änderung am Ablauf von Ä-002/Ä-037 ausser der Kopf-Auswertung, keine Änderung am Agent (kein neuer Stick).

## Abnahmekriterien

- [ ] Neue Tests grün, `python3 -m unittest discover -s tests -t .` (bekannt rot: 4 Tests in `test_imaging`/`test_jobs`;
      als `okuli-agent` evtl. zusätzlich `RealPartcloneTest` wegen `/var/log/partclone.log` – melden)
- [ ] Doku wie oben

## Abschluss

1. Ein Commit `B-007: belegte Blöcke im partclone-Kopf richtig lesen`, **nur lokal** auf `agent/B-007`, nur eigene
   Dateien (`git add <Pfade>`). Danach in dieser Datei `Status: umgesetzt (Commit <hash>)` (eigener Commit ok).
2. Rückmeldung: Änderungen, Commits, Testergebnis, Abweichungen.
