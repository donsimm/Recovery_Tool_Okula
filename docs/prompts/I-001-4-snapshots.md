# I-001 Auftrag 4 – Snapshots der VMs

Status: abgenommen 06.11. (Commit 2dadd10) – Ablauf im Tool noch zu testen (TESTS.md Abschnitt 11) · erstellt 06.11.2026 von der Projektleitung · Freigabe: Dominik 06.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, **`docs/VM.md` (verbindlich, inkl. aller Abweichungen aus
Auftrag 1–3)**, `okula_recovery/vm.py`, `okula_recovery/vm_dialogs.py`, in `ui.py` die VM-Funktionen (`vm_*`,
`start_restore`, `start_install`) und die Automatisierung (`automation.py`, `Engine._execute`). Arbeitsbranch
`claude/blissful-goldberg-mo3xda`; vorher `git pull`. Die Sitzung läuft auf dem Server (libvirt 11.3, QEMU 10.0,
`virsh -c qemu:///system` ohne sudo; `sudo` nur mit Passwort). **Das Tool läuft eventuell parallel** – keine zweite
Instanz starten; am Server mit dem echten Code ohne Oberfläche prüfen (wie in Auftrag 3).

## Ziel

Den Zustand einer VM einfrieren und in Sekunden dorthin zurückkehren – z. B. „frisch installiert, vor Sysprep“ oder
„vor der Automatisierung“. Damit lassen sich Master-Bau und Tests beliebig wiederholen, ohne neu zu installieren.

## Entscheide aus dem Brainstorming

- **Snapshots von Hand nur bei ausgeschalteter VM** (nur Disk, kein Arbeitsspeicher) (06.11., Dominik).
- **Automatisch vor riskanten Aktionen** an einer VM – Zurückspielen, OS installieren, Automatisierung: Häkchen
  **„Vorher Snapshot“**, Standard an (06.11., Dominik).
- **Unbegrenzt viele**, Warnung bei wenig Platz (< 50 GB frei auf der Server-SSD) (06.11., Dominik).
- **Automatischer Snapshot bei laufendem Agent** (Projektleitung 06.11.): Für diese Aktionen läuft die VM mit dem
  Agent, Windows/Linux der VM läuft nicht, die Disk ist unbenutzt (Agent hängt höchstens nur lesend ein). Darum ist hier
  ein Disk-Snapshot der laufenden VM zulässig – direkt vor dem Start des Auftrags, nachdem der Agent die Disk
  freigegeben hat. Bei laufendem Windows (kein Agent) nie.

## Anforderungen

1. **Technik klären und festhalten:** Bei UEFI-VMs (pflash-NVRAM) lehnt libvirt interne Snapshots ab → **externe
   Disk-Snapshots** (qcow2-Overlay im Pool-Verzeichnis), Zurückspringen (`snapshot-revert`) und Löschen (Zusammenführen)
   mit libvirt 11.3 für ausgeschaltete VMs. Für alle drei Firmware-Arten gleich lösen (auch BIOS). Prüfen und in
   `docs/VM.md` begründen: was mit dem UEFI-NVRAM (`*_VARS.fd`) und dem TPM-Zustand beim Zurückspringen passiert (bei
   Bedarf beim Snapshot mitkopieren und beim Zurückspringen zurücklegen – Secure Boot/BitLocker hängen daran).
   Overlay-Dateien müssen von AppArmor freigegeben sein (Lehre aus 1b: Disk als Datei).
2. **`vm.py`:** `snapshots(name)`, `snapshot_create(name, title, auto=False)`, `snapshot_revert(name, snap)`,
   `snapshot_delete(name, snap)`, belegter Platz je Snapshot. Fehler als `VmError` mit deutschem Text. Titel frei
   (Vorgabe „Snapshot TT.MM. HH:MM“), automatische mit Titel „vor <Aktion> TT.MM. HH:MM“ und Kennzeichen „automatisch“.
3. **Reiter „Snapshots“** im Gerätefenster einer VM: Liste (Titel, Datum, automatisch ja/nein, Grösse; aktueller
   Stand markiert), Knöpfe **Snapshot erstellen …** (nur aus), **Zurück zu diesem Snapshot …** (nur aus; Rückfrage:
   „Alle Änderungen seit <Titel> gehen verloren“), **Löschen …** (Rückfrage). Platzwarnung unter der Liste.
4. **Häkchen „Vorher Snapshot“** (nur bei VMs sichtbar, Standard an) in den Dialogen *Image zurückspielen* und
   *OS installieren*, und in der **Automatisierung** einer VM als Einstellung (Standard an). Schlägt der Snapshot fehl:
   Auftrag nicht starten, Meldung. Verlauf der VM: „Snapshot ‚…‘ erstellt / zurückgesetzt / gelöscht“.
5. **Zusammenspiel:**
   - *VM löschen …* entfernt auch alle Snapshots und Overlay-Dateien (Pool danach leer).
   - *Hardware ändern …*: Disk vergrössern bei vorhandenen Snapshots sperren mit Grund („zuerst Snapshots löschen“);
     RAM/CPU/Netzwerkkarte bleiben möglich, falls libvirt das mit Snapshots zulässt (prüfen).
   - Nach dem Zurückspringen gilt das Vor-Inventar/Ä-036 wie zum Zeitpunkt des Snapshots (leere Disk wieder leer).
   - Zwillinge (Auftrag 3) wie jede VM.

## Nicht Teil dieses Auftrags

- Snapshots mit Arbeitsspeicher (laufende VM von Hand). Snapshots echter Geräte. Export von Snapshots aufs NAS.
- Die 4 bekannten roten Tests (`test_imaging` ×3, `test_jobs` ×1).

## Hinweise zum Code

- `vm.Virsh` (alle virsh-Aufrufe), `vm.free_disk()`, `ui.vm_delete`, `ui.vm_hardware`, Restore-/Installationsdialog
  (`restore_dialog.py`, `os_dialogs.py`), Automatisierung (`automation.Settings`, `Engine._execute`).
- Agent betroffen? **Nein** – kein neuer Agent-Stick.
- Reihenfolge: `vm.py` + Tests (nachgebildetes `virsh`), dann am Server mit einer echten Probe-VM prüfen, dann Oberfläche.

## Oberfläche und Texte

- Reiter „Snapshots“, Knöpfe und Häkchen genau wie oben; Schreibstil laut `CLAUDE.md`.
- **Hilfe (F1):** Kapitel „Virtuelle Maschinen“ um Abschnitt „Snapshots“ (wozu, nur ausgeschaltet, automatisch vor
  Aktionen, Zurückspringen löscht spätere Änderungen, Platz); Kapitel Zurückspielen/OS installieren/Automatisierung:
  Häkchen „Vorher Snapshot“ bei VMs.

## Abnahmekriterien

- [ ] Tests: Snapshot erstellen/zurück/löschen (nachgebildetes `virsh`), Sperren (laufend, Disk vergrössern),
      automatischer Snapshot vor Auftrag inkl. Abbruch bei Fehler, VM löschen räumt Overlays weg.
- [ ] Am Server mit echter Probe-VM je Firmware (VM-Win11 UEFI+SB+TPM, VM-Legacy BIOS): Datei auf die Disk schreiben
      (z. B. per Agent oder Test-Disk) → Snapshot → ändern → zurück → alter Stand; Secure Boot nach dem Zurückspringen
      weiter „Enabled“; Snapshot löschen; VM löschen → Pool leer. Keine Test-VMs zurücklassen; **die VMs von Dominik
      (VM-Win11, VM-Klein) nicht anfassen**.
- [ ] Alle Tests: nicht mehr als die 4 bekannten roten; `tests/test_help.py` grün.
- [ ] `docs/VM.md` Auftrag 4 ✔ mit Technik-Entscheid (extern, NVRAM/TPM) und Abweichungen, `docs/TECHNIK.md`,
      `docs/TESTS.md` (Prüfschritte für Dominik, inkl. Master-Ablauf: Snapshot „vor Sysprep“), `docs/AENDERUNGEN.md`:
      Protokoll „I-001 Auftrag 4“; **I-001 als erledigt** ins Protokoll (alle 4 Aufträge), Kurzübersicht.

## Abschluss

1. Commit(s) `I-001 (4/4): Snapshots der VMs`; pushen. Nur eigene Dateien committen (`git add <Pfade>`, nie
   `git add -A`) – die Projektleitung arbeitet im selben Ordner.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Testergebnis, Prüfung am Server, Technik-Entscheid, Abweichungen, Schritte für Dominik
   (`git pull && sudo ./install.sh`, Tool neu starten).
