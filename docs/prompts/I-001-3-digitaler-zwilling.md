# I-001 Auftrag 3 – Digitaler Zwilling (VM mit der Hardware eines Geräts) + Ä-036

Status: freigegeben · erstellt 06.11.2026 von der Projektleitung · Freigabe: Dominik 06.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, **`docs/VM.md` (verbindlich, v. a. „Hardware von einem
Gerät übernehmen“ und die Abweichungen aus Auftrag 1/1b/2)**, Ä-036 in `docs/AENDERUNGEN.md`,
`docs/prompts/I-001-2-vms-im-tool.md`, `okula_recovery/vm.py`, `okula_recovery/vm_dialogs.py`, in `ui.py` die
Funktionen `vm_new`, `_vm_created`, `vm_start`, `start_restore`, in `devices.py` `register_vm`, `identity`, `match`.
Arbeitsbranch `claude/blissful-goldberg-mo3xda`; vorher `git pull`. Die Sitzung läuft auf dem Server (libvirt,
`br0`, SPICE installiert; `virsh -c qemu:///system` ohne sudo; `sudo` nur mit Passwort).

## Ziel

Aus einem echten Gerät der Geräteliste entsteht mit einem Klick eine VM mit derselben Hardware-Beschreibung –
Hersteller, Modell, BIOS, CPU-Name, RAM, Disk (Grösse/Anschluss/Modell), Firmware (UEFI/BIOS, Secure Boot, TPM) – und
auf Wunsch mit dem letzten Image des Geräts darauf („digitaler Zwilling“). Damit lassen sich Images auf „derselben“
Hardware testen, ohne das echte Gerät anzufassen. Dazu Ä-036: „Einschalten“ einer VM mit leerer Disk fragt nach,
statt im UEFI-Setup-Menü zu landen.

## Entscheide aus dem Brainstorming

- Übernahme laut Tabelle „Hardware von einem Gerät übernehmen“ in `docs/VM.md` (06.11., Dominik).
- **Identität abgewandelt mit Kennzeichen** (06.11., Dominik): Seriennummern `VM-` + Original, UUID mit geänderten
  Stellen, **immer eigene MAC**. Sonst führt das Tool VM und Gerät zusammen.
- **Letztes Image einspielen:** Häkchen, Standard an (06.11., Dominik).
- **OEM-Key nie übernehmen**, Windows bleibt „nicht aktiviert“ (06.11., Dominik).
- **Netzwerkkarte immer Intel** (Projektleitung 06.11.): Q35 → `e1000e`, i440FX → `e1000`, auch wenn das Gerät eine
  Realtek-Karte hat (`rtl8139` hat keinen Windows-Treiber, siehe Auftrag 1b). Die echte Karte steht in der Vorschau.
- Ä-036 gehört in diesen Auftrag (06.11., Dominik).

## Anforderungen

1. **`vm.profile_from_inventory(inv, server) -> (VmProfile, notes)`** (rein, ohne GTK/virsh, gut testbar):
   - **Systemdisk** = Disk mit installiertem System (`inventory.systems[].disk`), sonst die erste Disk.
   - **Firmware:** Partitionstabelle der Systemdisk `gpt` → UEFI, `dos` → BIOS (Legacy); ohne Tabelle (leere Disk)
     → `platform.uefi`. UEFI + `platform.secure_boot` wahr → `uefi-sb`. TPM, wenn `platform.tpm` nicht leer.
     Chipsatz: BIOS → `i440fx`, UEFI → `q35`.
   - **Disk:** Grösse genau (aufrunden auf ganze GB), Anschluss `nvme` → `nvme`, sonst `sata`; Modellname (≤ 40
     Zeichen, nur bei SATA wirksam – siehe VM.md); Drehzahl nur, wenn das Inventar sie kennt.
   - **CPU:** Name aus `cpu.model`, Kerne/Threads wie im Gerät, aber höchstens **Server-Kerne − 2** gesamt
     (mindestens 1) → Hinweis, wenn gekürzt.
   - **RAM:** wie im Gerät (auf MB), höchstens **freier RAM des Servers − 4 GB** → Hinweis, wenn gekürzt.
   - **SMBIOS:** `dmi`-Werte genau (Hersteller, Modell, Version, SKU, Familie, Board, BIOS-Hersteller/-Version/-Datum,
     Gehäusetyp). Fehlende Werte leer lassen, keine „Okula“-Vorgaben einmischen.
   - **Identität abwandeln:** `product_serial`, `board_serial`, `chassis_serial` → `VM-` + Original (auf zulässige Länge
     kürzen); `product_uuid` → erste 8 Hex-Stellen durch `0c1a0000` ersetzen (Rest gleich, gültige UUID); Platzhalter
     ab Werk (`devices.placeholder_uuid`/`placeholder_serial`) → wie bei neuen VMs neu erzeugen. **Disk-Seriennummer**
     ebenfalls abwandeln (`VM` + Original, ≤ 20 Zeichen) – das Tool erkennt Geräte auch daran wieder. MAC: neu.
   - **Name:** `VM-<Gerätename>`, auf erlaubte Zeichen (`vm.NAME_RE`) und 48 Zeichen gebracht, eindeutig.
   - `notes`: jede Abweichung als kurzer Satz (z. B. „RAM 16 GB → 12 GB (Server)“, „Netzwerkkarte Realtek r8169 →
     Intel e1000e“, „Gehäusetyp nur im Profil“, „OEM-Key nicht übernommen“).
   - **Test:** Der erzeugte Geräteeintrag darf in `devices.match()` nie auf das Originalgerät passen (UUID, Seriennummer,
     MAC, Disk-Seriennummer) – mit dem echten Inventar-Beispiel aus `docs/VM.md` (SHARKBAY) und einem UEFI/NVMe-Gerät.
2. **„VM mit dieser Hardware erstellen …“** im Gerätefenster (Kopf oder Reiter Übersicht) und im Rechtsklick auf ein
   Gerät. Nicht für VMs und nicht für den DEMO-PC; ohne Inventar ausgegraut mit Grund im Tooltip.
3. **Vorschau-Dialog** (`vm_dialogs.py`): Tabelle *Gerät → VM* mit Zeichen ✔ (genau), ~ (angepasst), ✖ (nicht
   übernommen) laut Tabelle in `docs/VM.md`, die Hinweise aus `notes`, Name (änderbar), Platz/RAM-Prüfung wie bei
   „Neue virtuelle Maschine …“. Häkchen **„Letztes Image des Geräts einspielen“** (Standard an) mit Auswahl des Images
   (Images des Geräts wie im Reiter Images des Gerätefensters, neuestes zuerst; Master-Images mit ★). Gibt es keins:
   Häkchen aus und ausgegraut, Hinweis „Kein Image dieses Geräts auf dem NAS“.
4. **Ablauf beim Erstellen:** VM anlegen (`virsh.create` mit dem Profil) → Geräteeintrag im Ordner „Virtuelle
   Maschinen“ (`register_vm`, Vor-Inventar aus dem Profil, Merkmal `vm.twin_of = <Geräte-ID>`) → Netzwerkstart frei.
   Mit Häkchen zusätzlich: **Einschalten und Agent starten** → auf den Agent warten (höchstens 5 min, Fortschritt im
   Reiter Aufträge) → **Zurückspielen** des gewählten Images auf die VM-Disk wie `start_restore`, aber ohne Dialog,
   ohne „Danach anpassen“ (1:1-Zwilling), Prüfung vor dem Zurückspielen an → danach VM herunterfahren. Fehler in einem
   Schritt: verständliche Meldung, VM bleibt bestehen (nicht automatisch löschen).
5. **Verlauf:** beim Original „Zwilling <VM-Name> erstellt“, bei der VM „Zwilling von <Gerät> (Image …)“. Im
   Gerätefenster der VM in der Übersicht eine Zeile „Zwilling von <Gerät>“ (anklickbar → Gerät öffnen).
6. **Ä-036 – leere Disk:** „Einschalten“ einer VM, die noch nie ein System hatte (Disk im Inventar ohne Partitionen und
   im Verlauf keine Installation/kein Zurückspielen), fragt: „Die Disk von <VM> ist leer – ohne System startet die VM
   ins UEFI-Menü bzw. meldet ‚kein Betriebssystem‘.“ mit den Knöpfen *Einschalten und Agent starten*,
   *Von ISO starten …*, *Trotzdem einschalten*. Gilt für alle VMs, nicht nur Zwillinge.

## Nicht Teil dieses Auftrags

- Snapshots (Auftrag 4). Treiber für Zwillinge, Hersteller-BIOS-Einstellungen (nicht nachbildbar).
- Automatisches Löschen oder Aktualisieren eines Zwillings bei neuem Image.
- Die 4 bekannten roten Tests (`test_imaging` ×3, `test_jobs` ×1).

## Hinweise zum Code

- Images eines Geräts: `device_window.load_images()` (Metadaten `source.device_id` bzw. `agent_id`) – wiederverwenden,
  nicht doppelt bauen. Zurückspielen: `jobs.restore_work` wie in `ui.start_restore`.
- Server-Werte: `vm.ram_mb()`, `vm.free_disk()`, Kerne über `os.cpu_count()`.
- Agent betroffen? **Nein** – kein neuer Agent-Stick.
- Reihenfolge: Logik (`profile_from_inventory`, Ä-036-Erkennung) mit Tests zuerst, dann Dialog und Ablauf.

## Oberfläche und Texte

- Knopf/Menü exakt „VM mit dieser Hardware erstellen …“; Schreibstil laut `CLAUDE.md`.
- **Hilfe (F1):** Kapitel „Virtuelle Maschinen“ um Abschnitt „Digitaler Zwilling“ (wozu, was übernommen wird und was
  nicht, abgewandelte Identität, Windows nicht aktiviert) und um den Hinweis zur leeren Disk (Ä-036) ergänzen;
  Kapitel zum Gerätefenster: neuer Knopf.

## Abnahmekriterien

- [ ] Tests: `profile_from_inventory` für BIOS/MBR-Gerät (SHARKBAY-Beispiel), UEFI-Gerät mit NVMe, Secure Boot und TPM,
      Gerät ohne System, Platzhalter-Seriennummern, Kürzung CPU/RAM; Identität passt nie auf das Original; Ä-036-Erkennung.
- [ ] Am Server geprüft (ohne sudo): Zwilling eines echten Geräts **mit** Image (z. B. eines der Geräte im Ordner
      „Coolux Compact Player“, falls ein Image auf dem NAS liegt) → VM startet danach mit „Einschalten“ in das System
      des Images; Inventar der VM zeigt Hersteller/Modell des Originals, Seriennummer `VM-…`; Original unverändert, kein
      Zusammenführen. Danach Zwilling löschen (Images auf dem NAS bleiben, Test-Images des Agents entfernen).
- [ ] Ä-036 am Server: neue VM → Einschalten → Rückfrage erscheint.
- [ ] Alle Tests: nicht mehr als die 4 bekannten roten; `tests/test_help.py` grün.
- [ ] `docs/VM.md` Auftrag 3 ✔ mit Abweichungen, `docs/TECHNIK.md`, `docs/TESTS.md` (Prüfschritte für Dominik),
      `docs/AENDERUNGEN.md`: Protokoll „I-001 Auftrag 3“ und **Ä-036 aus der Tabelle ins Protokoll**, Kurzübersicht.

## Abschluss

1. Commit(s) `I-001 (3/4): Digitaler Zwilling – VM mit der Hardware eines Geräts; Ä-036 leere Disk`; pushen. Nur eigene
   Dateien committen (`git add <Pfade>`, nie `git add -A`) – die Projektleitung arbeitet im selben Ordner.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Testergebnis, Prüfung am Server, Abweichungen, Schritte für Dominik
   (`git pull && sudo ./install.sh`, Tool neu starten).
