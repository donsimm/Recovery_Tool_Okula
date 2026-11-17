# B-015 – Direktinstallation: Gerät startet nach der Installation wieder die Setup-Partition

Status: umgesetzt (Commit fecfc81) · erstellt 17.11.2026 von der Projektleitung · Freigabe: Dominik 17.11. (Nachtrag zu B-014)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, die Einträge **B-015** und (erledigt) **B-014** in
`docs/AENDERUNGEN.md`, in `docs/TECHNIK.md` den Abschnitt zur Windows-Direktinstallation. Gearbeitet wird in der
eigenen Kopie, in der der Agent gestartet wurde (lokaler Branch `agent/B-015`); nicht pullen, nicht pushen.
Kleiner Auftrag: nur `install.cmd` (bzw. was zwingend dazugehört), keine Umbauten.

## Ziel

Nach `dism` und `bcdboot` startet das Gerät **in das neue Windows** – nicht erneut in die Setup-Partition – auch auf
Firmware, die für die Setup-Partition selbst einen Starteintrag anlegt und ihn an die erste Stelle setzt.

## Befund (CompactPlayer 1, AMI-Firmware 2014, UEFI, 17.11.)

- Nach erfolgreichem `dism`/`bcdboot` und `wpeutil reboot` startete das Gerät wieder die Setup-Partition;
  `install.cmd` lief ein zweites Mal und brach ab (Markierung durch `format` gelöscht → „Windows-Partition :“).
- `bcdedit /enum firmware` in WinPE: `{fwbootmgr}` `displayorder` = **`UEFI OS` (device partition=D: = Setup-Partition,
  path `\EFI\BOOT\BOOTX64.EFI`)**, dann `{bootmgr}` (Windows Boot Manager), `UEFI: USB` (Agent-Stick), weitere
  `UEFI OS`/`Windows Boot Manager`-Reste. Den Eintrag „UEFI OS“ legt die Firmware selbst an (Wechseldatenträger-Pfad
  auf einer FAT-Partition) – nicht der Agent (`set_bootnext` legt „Okula Windows-Installation“ nur für BootNext an).
- Umgehung (funktioniert): `bcdedit /set {fwbootmgr} displayorder {bootmgr} /addfirst`, dann `wpeutil reboot`.
- Danach löscht der erste Windows-Start (SetupComplete bzw. auditUser, I-038) die Setup-Partition – dann ist der
  Eintrag gegenstandslos. Bis dahin darf die Firmware aber nicht die Setup-Partition wählen.

## Anforderungen

1. `install.cmd`: nach erfolgreichem `bcdboot` den Windows Boot Manager an die erste Stelle der Firmware-
   Startreihenfolge setzen (`bcdedit /set {fwbootmgr} displayorder {bootmgr} /addfirst`), Ergebnis ins `install.log`
   (inkl. `bcdedit /enum firmware` vor und nach). Schlägt `bcdedit` fehl → nur protokollieren, kein Abbruch
   (`bcdboot` hat die Reihenfolge normalerweise schon gesetzt).
2. Prüfen (Microsoft Learn, `bcdboot`-Doku), ob `bcdboot … /f UEFI` mit einer Option die Reihenfolge zuverlässiger
   setzt; wenn ja, zusätzlich nutzen und in `TECHNIK.md` begründen.
3. Optional, falls ohne Risiko: Firmware-Einträge, die auf die Setup-Partition zeigen, aus `{fwbootmgr}` entfernen
   (`bcdedit /set {fwbootmgr} displayorder <id> /remove`) – nur wenn eindeutig per `device partition=<Setup-Laufwerk>`
   erkennbar; sonst weglassen und begründen.
4. Nur ASCII und CRLF in der .cmd (bestehende Tests beachten); Tests für den neuen Text (Befehl nach `bcdboot`,
   Protokoll, kein `goto fehler` bei bcdedit-Fehler).

## Nicht Teil dieses Auftrags

- Agent-Seite (`wininstall.py`, `set_bootnext`), B-013, alles aus B-014 ausser direkter Abhängigkeit.

## Hinweise zum Code

- `okula_recovery/winsetup.py`: `install_cmd()`.
- Agent betroffen (neuer Agent-Stick nötig)? **nein** (`install.cmd` erzeugt das Tool).

## Oberfläche und Texte

- Keine. Hilfe (F1) zur Direktinstallation nur anpassen, falls dort die Startreihenfolge beschrieben ist.

## Abnahmekriterien

- [ ] `install.cmd` setzt nach `bcdboot` den Windows Boot Manager an die erste Stelle, protokolliert vorher/nachher
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests wie oben
- [ ] `docs/AENDERUNGEN.md`: B-015 ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Abschnitt 20 um „startet nach der Installation direkt Windows (CompactPlayer)“ ergänzen
- [ ] `docs/TECHNIK.md`: Absatz zur Startreihenfolge

## Abschluss

1. Ein Commit `B-015: Windows Boot Manager nach der Installation zuerst`, **nur lokal** auf `agent/B-015` – **nicht
   pushen**. **Nur eigene Dateien committen** (`git add <Pfade>`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Commit, Testergebnis, neuer Agent-Stick nein, Schritte für den Server, offene Punkte.
