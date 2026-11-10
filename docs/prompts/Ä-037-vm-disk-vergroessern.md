# Ä-037 – VM-Disk beim Zurückspielen vergrössern, Profil VM-Win11 256 GB

Status: umgesetzt (Commit 55ed0dd) · erstellt 10.11.2026 von Okuli (Projektleitung) · Freigabe: Dominik 10.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag Ä-037 in `docs/AENDERUNGEN.md`, `docs/VM.md`,
`docs/KLEINERE-DISK.md` (Ä-002). Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde (lokaler
Branch `agent/AE-037`); nicht pullen, nicht pushen.

## Ziel

Images grösserer Geräte (Lenovo L15 256/512 GB, Samsung 970 EVO 1 TB) sollen sich ohne Umwege auf eine VM spielen
lassen. Ist die Disk der VM zu klein, bietet *Image zurückspielen …* an, die VM-Disk auf die Grösse der Quelldisk zu
vergrössern und danach zurückzuspielen – alles in einem Auftrag. Neue VMs mit dem Profil VM-Win11 bekommen 256 GB.

## Entscheide aus dem Brainstorming

- Vergrössern **und** Anpassen (Ä-002) bleiben beide möglich; bei einer VM ist Vergrössern der Standard (Image 1:1,
  kein Umbau) (Dominik 10.11.).
- Neue Grösse = Grösse der Quelldisk des Images, aufgerundet auf ganze GB (dezimal, wie `DiskSpec.size_gb`).
- Profil **VM-Win11: 256 GB** (Modellname „Okula NVMe SSD 256GB“). Bestehende VMs bleiben, wie sie sind (Dominik 10.11.).
- Die qcow2-Disks sind dünn: Vergrössern belegt erst Platz, wenn geschrieben wird.

## Anforderungen

1. **Dialog *Image zurückspielen …* (`restore_dialog.py`), nur bei VMs** (`device.is_vm`), wenn
   `disk["size"] < need`: zusätzlich zur heutigen Prüfung „Image anpassen“ (`_smaller_disk`) eine Wahl mit zwei
   Optionsfeldern:
   - „VM-Disk auf <N> GB vergrössern und zurückspielen“ (Standard), Tooltip: Ablauf in einem Satz.
   - „Image an die kleinere Disk anpassen“ – nur wählbar, wenn die bestehende Ä-002-Prüfung „lässt sich anpassen“ meldet
     (sonst ausgegraut mit dem Grund aus der Prüfung).
   Bei echten Geräten bleibt alles wie heute.
2. **Vergrössern nicht möglich** → Optionsfeld ausgegraut, Grund im Tooltip und im Prüftext:
   - die VM hat Snapshots: „Die VM hat Snapshots – zuerst im Reiter „Snapshots“ löschen, dann lässt sich die Disk
     vergrössern.“
   - zu wenig Platz im Pool `okula`: frei < belegte Daten des Images (aus den Metadaten bzw. Ä-002-Kopf, sonst
     Grösse der Image-Dateien) + 10 % Reserve (mind. 10 GB) → Meldung mit Zahlen.
   - Sind beide Wege nicht möglich, bleibt *Zurückspielen* gesperrt wie heute.
3. **Auftrag „VM-Disk vergrössern und zurückspielen“** (ein Eintrag im Reiter Aufträge, nach dem Vorbild
   `_twin_restore` in `ui.py`), Schritte mit Fortschritt und Log, abbrechbar:
   1. VM herunterfahren (der Agent ist im Leerlauf): zuerst sauber (`shutdown`), nach 60 s hart ausschalten.
   2. Disk vergrössern über `Virsh.set_profile` (Profil mit neuer `disk.size_gb`, sonst unverändert); Modellname der
      Disk bleibt.
   3. „Einschalten und Agent starten“ (`virsh.start(name, "agent")`), auf den Agent warten (höchstens
      `TWIN_AGENT_TIMEOUT`), danach prüfen, dass die Zieldisk jetzt gross genug ist.
   4. „Vorher Snapshot“ (falls angehakt) **erst jetzt** – nach dem Vergrössern, sonst sperrt der Snapshot das
      Vergrössern.
   5. Zurückspielen wie bisher (Auswahl aus dem Dialog: Quelldisk, Zieldisk-Pfad, Prüfen, Anpassen/Master,
      Herunterfahren), Verlauf wie beim normalen Zurückspielen.
   Fehler in Schritt 1–4 → Auftrag rot mit Grund, nichts zurückgespielt; die vergrösserte Disk bleibt (nur
   vergrössert, Daten unverändert) – im Log erwähnen. Verlauf des Geräts: „VM-Disk von 128 GB auf 512 GB vergrössert“.
4. **Profil VM-Win11** in `vm.py`: 256 GB, Modell „Okula NVMe SSD 256GB“; `PROFILE_NOTES`, `docs/VM.md`, Hilfe und
   Tests (`tests/test_vm.py` erwartet heute 128) nachführen. Andere Profile unverändert.
5. **Hilfe (F1):** Kapitel zu VMs bzw. Zurückspielen: neuer Absatz „Disk der VM zu klein“ (beide Wege, Snapshots
   verhindern das Vergrössern, Platz auf dem Server); VM-Win11 mit 256 GB.

## Nicht Teil dieses Auftrags

- Kein Vergrössern im laufenden Betrieb (`blockresize`), keine Änderung am Agent (kein neuer Agent-Stick).
- Kein Verkleinern von VM-Disks, keine Änderung an bestehenden VMs ausser im neuen Auftrag.
- Keine Änderung an `shrink.py` ausser, falls nötig, einer kleinen Hilfsfunktion für „belegte Daten“.

## Hinweise zum Code

- Dialog: `RestoreDialog._update` / `_smaller_disk` (Zeilen ~235–310), Rückgabe an `start(...)` in
  `ui.start_restore` (~Zeile 3573) um einen Parameter, z. B. `grow_gb: int | None`, erweitern.
- Ablauf-Vorbild: `MainWindow._twin_restore` (Agent starten, warten, `online_agent`, Abbruch, Log).
- VM: `Virsh.set_profile` (nur ausgeschaltet, nur vergrössern, Snapshots sperren), `Virsh.shutdown`, Pool-Infos
  (`_vol_info`, `pool-info`), `snapshots_from_xml`.
- Tests: Dialog-Logik ohne GTK testbar machen, wo möglich (Entscheidungsfunktion „welche Wege gehen, warum nicht“
  als reine Funktion), Ablauf mit gefälschtem `Virsh`/Agent wie in `tests/test_vm_twin.py`.
- Agent betroffen (neuer Agent-Stick nötig)? **nein**.

## Oberfläche und Texte

- Optionsfelder: „VM-Disk auf <N> GB vergrössern und zurückspielen“, „Image an die kleinere Disk anpassen“.
- Auftrag: „VM-Disk vergrössern und zurückspielen <Image> → <Disk>“, Schritte „VM wird heruntergefahren (1/4)“,
  „Disk wird vergrössert (2/4)“, „Agent wird gestartet (3/4)“, „Zurückspielen (4/4)“.
- Schreibstil laut `CLAUDE.md` (Handbuch-Stil ohne Anrede, Vorgänge statt Ich-Form).

## Abnahmekriterien

- [ ] VM mit 128 GB, Image einer 512-GB-Disk: Dialog zeigt beide Wege, Vergrössern vorgewählt; nach Start ein Auftrag
      mit 4 Schritten; danach VM-Disk 512 GB, Image zurückgespielt
- [ ] VM mit Snapshots: Vergrössern ausgegraut mit Grund; Anpassen weiter möglich, wenn die Daten passen
- [ ] Zu wenig Platz im Pool: Vergrössern ausgegraut mit Zahlen
- [ ] „Vorher Snapshot“ angehakt: Snapshot entsteht nach dem Vergrössern, Auftrag läuft durch
- [ ] Echte Geräte: Dialog unverändert
- [ ] Neue VM mit Profil VM-Win11: 256 GB
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .` (bekannt rot: 4 Tests in `test_imaging`/`test_jobs`;
      als Benutzer `okuli-agent` ohne Anzeige werden GTK-Tests evtl. übersprungen – melden, Okuli prüft mit Anzeige);
      neue Tests für die Entscheidungslogik und den Ablauf
- [ ] Hilfe (F1) angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Ä-037 aus der Tabelle ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Prüfschritte unter „Offen“ (neuer Abschnitt 13)
- [ ] `docs/TECHNIK.md` und `docs/VM.md` ergänzt
- [ ] Demo-Gerät: nicht nötig

## Abschluss

1. Ein Commit (oder wenige, sinnvoll getrennt) mit der ID im Titel, z. B. `Ä-037: VM-Disk beim Zurückspielen
   vergrössern`, **nur lokal** auf dem Branch `agent/AE-037` – **nicht pushen**, das macht Okuli nach der Abnahme.
   **Nur eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit danach ist ok).
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis, ob ein neuer Agent-Stick nötig ist, Schritte für
   den Server, offene Punkte oder Abweichungen vom Prompt.
