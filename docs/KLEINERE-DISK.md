# Restore auf eine kleinere Disk (Ä-002) – Plan

Stand: **umgesetzt** 31.10.2026 (`okula_recovery/shrink.py`, Tests `tests/test_shrink.py`). Prüfungen am realen
System: [TESTS.md](TESTS.md).

## Problem

Ein Disk-Image einer 512-GB-SSD lässt sich heute nicht auf eine 256-GB-SSD zurückspielen („Zieldisk zu klein“),
auch wenn auf C: nur 80 GB belegt sind. partclone schreibt ein Dateisystem immer in voller Grösse zurück.

## Gewählter Weg: auf dem Server ein angepasstes Image ableiten

1. **Prüfen (sofort, ohne Daten zu bewegen):** Aus dem Kopf des partclone-Images (Offset 52: Gerätegrösse,
   Blöcke, belegte Blöcke, Blockgrösse) liest das Tool, wie viel auf der grössten Partition belegt ist. Neue
   Aufteilung: Partitionen davor bleiben, Partitionen danach (z. B. Recovery) rücken ans neue Disk-Ende (gleiche
   Grösse, 1-MiB-ausgerichtet), die grosse Partition (C:) bekommt den Rest. Passt **belegt + Reserve
   (10 %, mindestens 1 GB)** nicht hinein → klare Meldung mit Zahlen.
2. **Anpassen (Auftrag auf dem Server):**
   - grosse Partition aus dem Image in eine **Sparse-Datei** zurückspielen (`partclone.<fs> -r -O`), braucht nur so
     viel Platz wie belegt ist;
   - Dateisystem verkleinern: NTFS `ntfsresize --force --force --size …` + `ntfsfix -d` (sonst gilt das Laufwerk
     als „zu prüfen“ und lässt sich danach nicht anpassen), ext2/3/4 `e2fsck -f -y` + `resize2fs`;
   - Datei auf die neue Grösse kürzen und neu sichern (`partclone.<fs> -c | zstd`);
   - übrige Partitionen unverändert übernehmen (Okula: Datei kopieren, Clonezilla: in zstd umpacken);
   - neue Partitionstabelle (`sfdisk`-Dump mit neuen Starts/Grössen, GPT `last-lba` passend zur neuen Grösse,
     UUIDs/Namen/Typen bleiben), Kopfbereich (Bootcode, Bootloader-Lücke) vom Original.
3. Ergebnis: **neues Okula-Image** neben dem Original, z. B. `…_für_256GB` (Metadaten: abgeleitet von, verkleinerte
   Partition, alte/neue Grösse). Das **Original bleibt unverändert**. Gibt es schon ein angepasstes Image für dieselbe
   Grösse, wird es wiederverwendet.
4. Zurückspielen wie gewohnt (Agent unverändert – die Tabelle passt jetzt auf die Disk).

**Zwischenspeicher** (Entscheid Dominik): zuerst Server-SSD (`/var/tmp/okula-recovery`), reicht der Platz nicht,
auf dem NAS (`.okula-tmp`); reicht beides nicht → Meldung mit Zahlen. Alles läuft als normaler Benutzer (getestet:
partclone in eine Datei, ntfsresize/resize2fs auf Dateien brauchen kein root).

## Grenzen (klare Meldung statt Versuch)

- **BitLocker / Rohkopie (`dd`)** auf der grossen Partition: nicht verkleinerbar (Inhalt unbekannt).
- Andere Dateisysteme (Btrfs, XFS – XFS kann gar nicht schrumpfen), LVM: nicht unterstützt.
- **MBR mit erweiterter/logischen Partitionen:** nicht unterstützt (nur primäre Partitionen).
- Demo-Images: nicht.

## Alternativen (verworfen)

- **Auf dem Agent beim Zurückspielen verkleinern:** Die Zieldisk ist zu klein für das volle Dateisystem –
  partclone braucht die Originalgrösse, also müsste der Agent erst irgendwo die volle Partition ablegen. Geht nicht.
- **Vor dem Image auf dem Quellgerät verkleinern:** verändert das Original-Gerät; das Image gibt es oft schon.
- **Dateibasiert kopieren (rsync/ntfs-3g):** Windows-Rechte, Hardlinks, Reparse-Points, Alternate Data Streams und
  der Bootsektor gehen verloren – nicht zuverlässig für ein startfähiges Windows.

## Oberfläche

- **Image zurückspielen:** statt „Zieldisk zu klein“ → Prüfergebnis (belegt, neue Grösse von C:) und Häkchen
  **„Für diese Disk anpassen (neues Image, Original bleibt)“**; dann startet zuerst das Anpassen, danach das
  Zurückspielen. Passt es nicht: Grund mit Zahlen.
- **Automatisierung:** Option in Schritt 2 „Ist die Zieldisk kleiner: Image automatisch anpassen“ (Standard ein).
- **Danach:** Windows prüft das Laufwerk beim ersten Start evtl. kurz (normal nach dem Verkleinern).

## Tests

Loop-Disks: GPT mit EFI/MSR/C: (NTFS)/Recovery (NTFS) und MBR mit ext4 + Swap; Image erstellen → für kleinere Disk
anpassen → über den Agent zurückspielen → Partitionstabelle prüfen (`sfdisk --verify`), NTFS lesen (`ntfsls`,
`ntfsfix -n`), ext4 `e2fsck -f -n`, Dateien vergleichen. Dazu: zu viel belegt → Meldung mit Zahlen; dd/BitLocker →
Meldung.
