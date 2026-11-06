# I-001 Auftrag 2 – VMs im Tool (Ordner, Neue VM, Starten, Bildschirm)

Status: Entwurf · erstellt 06.11.2026 von der Projektleitung · Freigabe: offen

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, **`docs/VM.md` (verbindlich)**, `docs/prompts/I-001-1-*.md`
und `I-001-1b-*.md` (was schon da ist), `okula_recovery/vm.py`, in `docs/TECHNIK.md` die Abschnitte „Geräte“,
„Netzwerkstart (PXE)“ und „Fernsteuerung: Wake-on-LAN und ‚Netzwerkstart zuerst‘“. Arbeitsbranch
`claude/blissful-goldberg-mo3xda`; vorher `git pull`. Die Sitzung läuft auf dem Server; libvirt, Brücke `br0` und
(nach Auftrag 1b) SPICE sind installiert, `virsh -c qemu:///system` geht ohne sudo. `sudo` nur mit Passwort.

## Ziel

Die VMs erscheinen in der Geräteliste im festen Ordner **„Virtuelle Maschinen“** – auch ausgeschaltet und bevor der
Agent je lief – und lassen sich im Tool anlegen, starten (normal, mit Agent, von ISO), herunterfahren, anschauen
(Bildschirm im eigenen Fenster) und löschen. Läuft der Agent in der VM, ist sie ein Gerät wie jedes andere
(Gerätefenster, Disk-Image, Zurückspielen, Backup, Automatisierung).

## Entscheide aus dem Brainstorming

- VMs im LAN sichtbar (Brücke `br0`), Bildschirm im eigenen Fenster (virt-viewer), Windows „nicht aktiviert“ (06.11., Dominik).
- Drei Profile VM-Win11 / VM-Legacy / VM-Klein (`vm.PROFILES`); Agent über den bestehenden Netzwerkstart.
- <offen – siehe Fragen an Dominik unten, vor Freigabe ausfüllen>

## Anforderungen

1. **Geräteeintrag für jede VM** (`devices.DeviceStore`), angelegt beim Erstellen der VM, im Ordner
   „Virtuelle Maschinen“:
   - Name = VM-Name, Identität über die **SMBIOS-UUID der VM** (`uuid:…`), damit der Agent beim ersten Start den
     Eintrag wiedererkennt (`devices.identity`/`match`) und kein zweites Gerät entsteht.
   - **Vor-Inventar** aus dem Profil (dmi: Hersteller/Modell/Seriennummer/UUID, cpu, memory, disks mit Grösse/
     Anschluss/Modell/Seriennummer, network: eine **Kabel**-Karte mit der VM-MAC, platform: uefi/secure_boot/tpm), als
     vorläufig markiert; der erste echte Agent-Bericht ersetzt es.
   - Markierung „ist VM“ im Gerät (z. B. Feld `vm: {"name": …}`), damit das Tool weiss, dass libvirt statt
     Wake-on-LAN zuständig ist. **Falle:** VM-MACs `52:54:00:…` gelten in `devices.real_mac()` als lokal vergeben –
     `netboot_macs()` nimmt sie nur aus dem Inventar. Darum muss das Vor-Inventar die Kabel-Karte enthalten, sonst
     bekommt die VM beim ersten Netzwerkstart keine Antwort. Test dafür.
   - VMs sind **automatisch für den Netzwerkstart freigeschaltet** (`netboot = True`), Freigabeliste sofort neu
     schreiben (`pxe allow` wie bei echten Geräten).
2. **Startreihenfolge wie bei echten Geräten mit „Netzwerkstart zuerst“** (Entscheid Projektleitung, siehe Begründung):
   VMs werden mit fester Reihenfolge Netzwerk → Disk definiert und `netfirst = True` gesetzt. Ob der Agent oder die
   Disk startet, entscheidet wie bei echten Geräten die Startart des Netzwerkstarts (`boot_mode`: „local“ ohne
   Auftrag, „once“ = einmal Agent). *Begründung:* Die Einmal-Startreihenfolge aus Auftrag 1 gilt bis zum
   Ausschalten – nach „Neu starten“ (z. B. Automatisierung nach dem Zurückspielen) käme sonst wieder der Agent statt
   Windows. `vm.py` entsprechend anpassen (Startart `pxe` entfällt bzw. wird „Agent beim nächsten Start“ +
   normal starten). Ist der Netzwerkstart im Tool aus: VM startet trotzdem (nach kurzem PXE-Versuch von der
   Disk) – Hinweis beim Start „Mit Agent“, dass der Netzwerkstart eingeschaltet sein muss (`netboot_ready()`).
   Am Server prüfen, dass „local“ in OVMF (UEFI) und SeaBIOS (BIOS) wirklich von der Disk weiterstartet.
3. **Ordner „Virtuelle Maschinen“** in der Geräteliste: fest, nicht umbenennbar/löschbar, VMs nicht
   herausziehbar und echte Geräte nicht hinein. Erscheint nur, wenn es mindestens eine VM gibt oder libvirt
   installiert ist. Zeile einer VM: LED wie bei Geräten (grün = Agent verbunden), zusätzlich Zustand der VM
   („aus“, „läuft“, „läuft – Agent verbunden“); Zustand alle 5 s über `virsh list` (ein Aufruf für alle).
4. **Neue VM …** (<Menüort laut Entscheid>): Dialog mit Profil-Auswahl (die drei Profile mit Kurzbeschreibung aus
   `docs/VM.md`), Name (Vorschlag = Profilname, eindeutig), Anzeige der Hardware, Prüfung freier Platz
   (`/var/lib/libvirt/images`) und RAM. „Erstellen“ legt VM + Geräteeintrag an.
5. **Aktionen** (Rechtsklick auf die VM und Knöpfe im Gerätefenster; bei VMs ersetzen sie Wake-on-LAN):
   - **Einschalten**, **Einschalten und Agent starten**, **Von ISO starten …** (ISO aus der ISO-Bibliothek auf dem
     NAS wie bei „Boot-Stick aus ISO“; Achtung NAS = CIFS: libvirt darf die Datei nicht umbesitzen – falls nötig
     `<seclabel model='dac' relabel='no'/>` an der CD; am Server mit einer echten ISO prüfen)
   - **Bildschirm** → `virt-viewer -c qemu:///system --wait --reconnect <name>` als eigenes Fenster (mehrfaches
     Öffnen bringt das bestehende Fenster nach vorne)
   - **Herunterfahren** (ACPI), **Ausschalten** (hart, mit Rückfrage), **Neu starten** – bei verbundenem Agent wie
     bisher über den Agent
   - **VM löschen …** mit roter Rückfrage („VM, Disk und Geräteeintrag werden gelöscht; Images und Backups auf dem
     NAS bleiben“), nur ausgeschaltet
   - <„Hardware ändern …“ laut Entscheid>
   - Alle Stellen, die heute Wake-on-LAN senden (Rechtsklick, Reiter Netzwerk, Automatisierung o. ä. – im Code
     suchen), bei VMs durch das Einschalten über libvirt ersetzen. Reiter „Netzwerk“: bei VMs Wake-on-LAN und
     „Netzwerkstart zuerst“ ausblenden bzw. als „bei VMs immer aktiv“ zeigen.
6. **Fehler** aus `vm.VmError` als verständliche Meldung im Tool, nie Traceback.
7. **Demo-Gerät** unverändert; VMs nie im Demo-Bereich.

## Nicht Teil dieses Auftrags

- Hardware von einem Gerät übernehmen, letztes Image einspielen (Auftrag 3). Snapshots (Auftrag 4).
- Die 4 bekannten roten Tests (`test_imaging` ×3, `test_jobs` ×1).

## Hinweise zum Code

- Geräte: `okula_recovery/devices.py` (`Device`, `DeviceStore`, `identity`, `match`, `register`, `netboot_macs`,
  `boot_mode`), Liste/Menü/Fernsteuerung: `okula_recovery/ui.py` (`MENU_LABELS`, `wake_options`, `wake_device`,
  `request_agent`, `netboot_changed`, `power`), Gerätefenster: `okula_recovery/device_window.py` (Kopf mit
  `power_buttons`, Reiter Netzwerk), ISO-Bibliothek: `okula_recovery/oslib.py`, PXE-Freigabe: `pxe.allow`.
- Agent betroffen? **Nein** – kein neuer Agent-Stick.
- Reihenfolge laut Entscheid: Tool-Logik zuerst (testbar ohne GTK), dann Oberfläche.

## Oberfläche und Texte

- Menüeintrag(e) in `MENU_LABELS` (sonst schlägt `tests/test_help.py` fehl), Knopf-/Menütexte genau wie in der
  Hilfe. Schreibstil laut `CLAUDE.md`.
- **Hilfe (F1):** neues Kapitel „Virtuelle Maschinen“ (wozu, drei Profile, anlegen, starten, Bildschirm, löschen,
  Grenzen: kein echter Hersteller-BIOS, Windows nicht aktiviert, Image auf andere Hardware nur mit Sysprep); Kapitel
  „Wichtige Begriffe“ um „Virtuelle Maschine (VM)“ ergänzen; Querverweis aus „Master-Image“.

## Abnahmekriterien

- [ ] Tests ohne libvirt (nachgebildetes `virsh`): Geräteeintrag mit Vor-Inventar, Wiedererkennung über UUID beim
      ersten Agent-Bericht (kein zweites Gerät), VM-MAC in `netboot_macs`, Freigabe automatisch, Startart, Ordner fest.
- [ ] Am Server geprüft (ohne sudo): VM-Klein im Tool anlegen → Einschalten und Agent starten → Agent verbindet,
      Gerät im Ordner, Inventar zeigt Okula/VM-Klein → Disk-Image erstellen → Herunterfahren → Einschalten
      (startet ohne Agent von der Disk bzw. meldet leere Disk) → Bildschirm öffnet → löschen; Pool leer.
- [ ] Alle Tests: nicht mehr als die 4 bekannten roten; `tests/test_help.py` grün.
- [ ] `docs/TECHNIK.md` Abschnitt „Virtuelle Maschinen“, `docs/VM.md` Auftrag 2 ✔ mit Abweichungen,
      `docs/TESTS.md` Prüfschritte für Dominik (inkl. Windows-11-Installation von ISO in VM-Win11),
      `docs/AENDERUNGEN.md` Protokoll „I-001 Auftrag 2“.

## Abschluss

1. Commit(s) `I-001 (2/4): VMs im Tool – Ordner, Neue VM, Starten, Bildschirm`; pushen.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Testergebnis, Prüfung am Server, Abweichungen, Schritte für Dominik
   (`git pull && sudo ./install.sh`, Tool neu starten).

---

## Fragen an Dominik (vor Freigabe klären, dann diesen Abschnitt entfernen)

1. Wo „Neue VM …“: Menü **Extras → „Neue virtuelle Maschine …“** + Rechtsklick auf den Ordner (Vorschlag) oder Menü Tools?
2. „Hardware ändern …“ (RAM, CPU, Disk vergrössern, Netzwerkkarte) schon in Auftrag 2 oder später?
3. Ordner „Virtuelle Maschinen“ fest (Vorschlag) oder dürfen VMs in eigene Unterordner sortiert werden?
