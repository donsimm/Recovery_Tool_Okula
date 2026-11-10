# Prüfliste – was geprüft ist und was am realen System noch offen ist

Stand: 29.10.2026. Abhaken mit `[x]`, Probleme mit Datum und Fehlermeldung darunter notieren.

Legende **Geprüft:** **A** = automatischer Test (Loop-Disks/QEMU, `python3 -m unittest`, 240 Tests) ·
**V** = Oberfläche in der Vorschau geprüft (virtuelle Anzeige, Screenshot) · **R** = von dir am realen System
bestätigt.

## Vorbereitung am neuen Server (einmal, vor allen Tests)

> **Ab Version 0.2.0 (I-024 und Ä-002): Agent-Stick neu erstellen und Netzwerkstart neu „Vorbereiten“** – der neue
> Agent erfasst TPM/Secure Boot.

- [ ] Update: `cd ~/recovery_tool_okula && git pull && sudo ./install.sh`, Tool neu starten
- [ ] Einstellungen vom alten Server importiert (NAS-Passwort und ggf. Garantie-Schlüssel Dell/HP einmal neu eingeben)
- [ ] **Agent-Stick neu erstellen** (neuer Agent mit Anpassen, Ordner senden, Countdown) – alte Sticks können das nicht
- [ ] Netzwerkstart: Tools → Netzwerkstart (PXE) → **Vorbereiten**, dann Einschalten
- [ ] Firewall: `sudo nft list ruleset` – leer = nichts zu tun


## Bereits geprüft

| Funktion | Geprüft | Bemerkung |
|---|---|---|

## Offen – am realen System testen

### 1. Fixes von heute
- (alle geprüft)

### 2. Netzwerk (Reiter „Netzwerk“ im Gerätefenster)
- [ ] Ä-034: `git pull && sudo ./install.sh` (HTTP-Dienst neu); EliteBook F9 → Netzwerk → im Gerätefenster → Netzwerk → „Netzwerkstart-Protokoll“: Anfrage (UEFI/BIOS), Antwort, Bootlader … bzw. roter Grund; ohne Netzwerkkabel → „keine Netzwerkstart-Anfrage“
- [ ] Ä-033: Rechtsklick auf ein ausgeschaltetes Gerät → Netzwerkstart → Einschalten (Gerät startet); „Einschalten und Agent starten“ nur aktiv mit „Netzwerkstart zuerst“, sonst ausgegraut mit Grund im Tooltip; bei verbundenem Gerät beides ausgegraut
- [ ] B-003: EliteBook 850 G1 im BIOS auf **UEFI Native (Without CSM)** stellen, Agent-Stick starten → Übersicht „UEFI“; Netzwerk-Reiter: Zahnrad sichtbar, Netzwerkkarten nur enp0s25 (+ feste MACs), Modem „Mobilfunk – nein“; danach die Punkte unten
- [ ] B-003: Gerät im BIOS-Modus (Legacy/CSM): Text nennt die BIOS-Taste; Schalter „Netzwerkstart zuerst“ ohne Fehlermeldung → „von Hand eingestellt“
- [ ] „Netzwerkstart zuerst“ einschalten → Gerät startet ohne Auftrag nach ~2 s normal von der Festplatte
- [ ] „Beim nächsten Start den Agent laden“ → startet einmal den Agent, danach wieder Windows
- [ ] „Einschalten und Agent starten“ (Wake-on-LAN + Agent) → Gerät erscheint im Tool
- [ ] „Prüfen“ nach einem Windows-Update: Startreihenfolge noch richtig?

### 3. Master-Image (Anleitung: [MASTER-IMAGE.md](MASTER-IMAGE.md))
Geht ohne echte Geräte mit VMs (Plan 06.11.): **Referenz = VM-Win11** neu **von ISO** installieren (Netzwerk der VM vorher trennen: `virsh -c qemu:///system domif-setlink VM-Win11 <vnetX> down`, vor dem Agent wieder `up`), in der Region-Seite Ctrl+Shift+F3 → Audit-Modus; nach Sysprep **nur „Einschalten und Agent starten“**; **Zielgerät = zweite VM** mit Profil VM-Win11 (z. B. `VM-Win11-B`). Die heutige VM-Win11 (Direktinstallation) taugt nicht als Referenz – Ersteinrichtung schon durchlaufen, Konto angelegt.
- [ ] Referenzgerät: Audit-Modus (Ctrl+Shift+F3), Programme, BitLocker aus, `sysprep /generalize /oobe /shutdown`
- [ ] Ohne Windows zu starten mit dem Agent-Stick „Disk-Image erstellen“
- [ ] Rechtsklick → „Als Master-Image markieren“ → ★ Master in der Liste
- [ ] Auf ein **anderes** Gerät zurückspielen, „Danach anpassen“ an → Log: „Windows (Master) – Name/Key gesetzt“
- [ ] Erster Start: keine Fragen (bzw. nur Konto, falls leer), **Computername** = Gerätename (max. 15 Zeichen),
      **Region** de-CH / Tastatur Schweiz / Zeitzone Zürich, **Aktivierung** mit Key bzw. BIOS-Key
- [ ] Lokales Konto: Anmelden ohne Passwort → Windows verlangt neues Passwort
- [ ] Gegenprobe: normales (nicht generalisiertes) Image mit „Danach anpassen“ → Log „nicht mit Sysprep vorbereitet“, Windows unverändert

### 6. Demo-Gerät (Vorführung)
- (alle geprüft)

### 9. Virtuelle Maschinen im Tool (I-001 Auftrag 2)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick). Netzwerkstart eingeschaltet.
- [ ] Geräteliste: Ordner „Virtuelle Maschinen“ erscheint; Rechtsklick darauf → nur „Neue virtuelle Maschine …“ und
      „Inventar exportieren …“; Ordner lässt sich nicht umbenennen, löschen oder verschieben, ein echtes Gerät lässt
      sich nicht hineinziehen
- [x] Extras → Neue virtuelle Maschine … → VM-Klein → Erstellen → Gerätefenster öffnet, Zustand „VM aus“ – ✔ 06.11. (VM-Klein und VM-Win11)
- [x] Einschalten und Agent starten → nach etwa 30 s grüner Punkt, Status „läuft – Agent verbunden“, Übersicht zeigt
      Okula VM-Klein, keine zweite Zeile in „Neu / nicht einsortiert“ – ✔ 06.11. (VM-Klein, „Neu / nicht einsortiert (0)“)
- [ ] Disk-Image erstellen (leere Disk) bzw. nach einer Installation; danach Herunterfahren-Symbol → VM aus
- [x] Einschalten → startet ohne Agent von der Disk (leere Disk: UEFI-Setup-Menü bzw. „kein Betriebssystem“) – ✔ 06.11.
      (VM-Win11 mit leerer Disk: UEFI-Setup-Menü – verständlicher machen: Ä-036)
- [ ] Bildschirm → eigenes Fenster (✔ 06.11. erstes Öffnen); nochmals klicken → Fenster öffnet neu; Ctrl+Alt gibt Maus und Tastatur frei
- [ ] Hardware ändern … (VM aus): RAM 6 GB, Disk 80 GB → Verlauf zeigt die Änderung; Verkleinern nicht möglich

### 11. Snapshots der VMs (I-001 Auftrag 4)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick). Ohne Oberfläche am Server geprüft
(siehe „Bereits geprüft“). Am besten mit einer Test-VM (z. B. neue VM-Klein), nicht mit der Master-VM.
- [ ] Gerätefenster der VM → Reiter **Snapshots**: bei laufender VM alle Knöpfe ausgegraut, Tooltip „Nur bei
      ausgeschalteter VM …“; VM aus → *Snapshot erstellen …* → Titel „frisch“ → Liste: Titel, Datum, Automatisch
      „nein“, Grösse, „◀ aktueller Stand“; Verlauf „Snapshot ‚frisch‘ erstellt“
- [ ] Einschalten, in der VM etwas ändern (Datei auf den Desktop), herunterfahren → *Zurück zu diesem Snapshot …* →
      Rückfrage „Alle Änderungen seit frisch …“ → Zurücksetzen → Einschalten: Datei weg; Verlauf „… zurückgesetzt“
- [ ] Bei VM-Win11 (UEFI + Secure Boot + TPM): nach dem Zurückspringen startet Windows normal, in Windows
      `msinfo32` → Sicherer Startzustand **Ein**, TPM vorhanden; kein BitLocker-Wiederherstellungsschlüssel verlangt
- [ ] *Image zurückspielen …* an der VM (mit Agent): Häkchen **Vorher Snapshot** sichtbar und an → Zurückspielen →
      im Reiter Snapshots „vor Zurückspielen TT.MM. HH:MM“, Automatisch „ja“; Verlauf „… erstellt (automatisch)“.
      Bei echten Geräten ist das Häkchen nicht da
- [ ] Dasselbe bei *OS installieren …* („vor OS-Installation …“) und in der **Automatisierung** der VM (Häkchen
      *Vorher Snapshot* unter „Nach 3 Tagen wieder einschalten“; „vor Automatisierung …“)
