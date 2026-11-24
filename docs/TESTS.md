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
| Agent-Stick erstellen, Gerät verbinden | A, R | |
| Disk-Image erstellen / zurückspielen (Okula, Clonezilla) | A, R | |
| Boot-Sticks aus ISO (alle OS) | A, R | „funktioniert mit allen OS“ |
| Windows-Direktinstallation | A, R | |
| Datei-Backup erstellen / zurückspielen, Notiz, Löschen | A, R | |
| Serverlast (CPU/RAM/LAN), CPU-Fix (84 % → 0,3 %) | A, R | |
| Netzwerkstart (PXE) – Agent ohne Stick, nur freigeschaltete Geräte | A, R | QEMU: UEFI Secure Boot und BIOS; fremde MAC bekommt keine Antwort |
| VM-Grundlage (I-001 1b): `Virsh.create/start/set_profile/poweroff/delete` für VM-Win11, VM-Legacy, VM-Klein am Server | A | 06.11., Bildschirm in einer Testkopie auf VNC (SPICE-Modul noch nicht installiert); Screenshots: UEFI TianoCore mit „UEFI QEMU NVMe Ctrl …“ bzw. „UEFI Okula SATA SSD 64GB …“, SeaBIOS mit iPXE auf Intel 82540EM und DHCP-Adresse aus dem LAN; danach keine VM, Pool leer |
| VMs im Tool (I-001 2), Prüfung durch den Agenten | A | 06.11., neue Version mit echter Geräteliste, NAS und Netzwerkstart (Dialoge im Skript bestätigt): VM-Klein angelegt (Eintrag im Ordner, MAC sofort in der Freigabeliste) → Einschalten und Agent starten → Agent nach 30 s verbunden, Inventar Okula VM-Klein, kein zweites Gerät → laufende VM auf Disk zuerst umgestellt → Disk-Image aufs NAS → Herunterfahren über den Agent → Einschalten startet von der Disk (Test-Disk mit grub) → Bildschirm öffnet, zweites Öffnen ersetzt das Fenster → Ausschalten → VM löschen: Pool leer, Freigabeliste wie vorher, Test-Image entfernt. Startart „lokal“: SeaBIOS startet von der Disk, OVMF zeigt das Setup-Menü (darum Disk → Netzwerk, siehe [VM.md](VM.md)). Von ISO starten (Debian-Netinst vom NAS) in VM-Win11 und VM-Legacy, ISO nicht umbesessen |
| VM-Grundlage nach `sudo ./install.sh` (I-001 1 + 1b) | R | 06.11.: Brücke `br0` mit gleicher IP 192.168.110.199, Internet ok, `virsh` ohne sudo, Pool `okula` aktiv, Standardnetz aus, SPICE-Paket installiert, PXE-Konfiguration `interface=br0`; mit dem echten Code alle drei Profile erstellt/gestartet/gelöscht; virt-viewer-Fenster VM-Win11: „Start PXE over IPv4“, Secure Boot **Enabled** (Dominik); VM-Legacy iPXE mit Intel 82540EM |
| Digitaler Zwilling (I-001 3), Prüfung durch den Agenten | A | 06.11., ohne Oberfläche mit dem echten Code: `profile_from_inventory` aus den Inventaren von CompactPlayer 2 (OEM SHARKBAY, MBR → BIOS/i440FX, SATA 121 GB KINGSTON, Realtek → e1000) und IOVERSAL-1 (GPT → UEFI/Q35, NVMe 1001 GB, 8 → 6 Kerne, RAM gekürzt) → `Virsh.create` + Start: läuft, SMBIOS OEM/SHARKBAY bzw. ASRock, Seriennummern `VM-…`, UUID `0c1a0000-…`, Disk-Seriennummer `VM…` im QEMU-Gerät, NVMe-Gerät vorhanden; `DeviceStore.match()` findet das Original nicht; danach gelöscht, nur VM-Klein und VM-Win11 übrig. Ablauf mit Image im Tool: offen (Abschnitt 10) |
| Snapshots der VMs (I-001 4), Prüfung durch den Agenten | A | 06.11., ohne Oberfläche mit dem echten Code an Probe-VMs (Profil VM-Legacy und VM-Win11, 1 GB): Inhalt per qcow2-Upload gesetzt und über die heruntergeladene Kette gelesen – Snapshot → ändern → Start mit Overlay-Kette (AppArmor) → automatischer Snapshot bei laufender VM → zurück zu A (alter Inhalt) → zurück zum späteren → RAM ändern geht, Disk vergrössern gesperrt → ältesten und letzten Snapshot löschen (Inhalt bleibt) → VM löschen: keine Datei, keine Hilfs-VM übrig. UEFI-Probe nach dem Zurückspringen: Secure Boot **Enabled** (UEFI-Menü). libvirts eigenes Löschen scheitert an AppArmor (siehe [VM.md](VM.md)) |
| install.sh auf neuem Debian 13 | R | |
| USB klonen / formatieren | A | |
| Einstellungen exportieren / importieren (inkl. Vorlagen) | A | |
| Kopieren aufs NAS (Drag & Drop), Abbrechen schliesst Fenster | A, V | |
| Debian-Direktinstallation: xorriso-Fehler behoben | A | mit nachgebauter Debian-ISO (schreibgeschützte Ordner) |
| Doppelte Geräte zusammenführen (automatisch und von Hand) | A, V | |
| Wake-on-LAN, „Netzwerkstart zuerst“, Agent beim nächsten Start | A | Logik und Pakete; keine echte Hardware |
| **Master-Image:** Markieren, Erkennen (Sysprep), unattend.xml mit Name/Key/Region/Konto | A, V | NTFS-Loop-Disk, echtes Image erstellt und zurückgespielt |
| **Ordner senden:** Software, Test Files, Content-Projekte, Ersetzen, Abbruch behält alten Stand | A, V | NTFS-Loop-Disk |
| **Automatisierung:** Countdown + Esc, Warteschlange (N), 5 Schritte, falsche Disk = nichts gelöscht, Fehler, Wiedereinschalten (jetzt 3 Tage) | A, V | ganzer Durchlauf über den echten Agent auf Loop-Disks |
| Computername = Gerätename (OS installieren, Anpassen) | A, V | |
| Grüne/rote Fortschrittsbalken | A, V | |
| Demo-Gerät: alle Aufträge, Fehler, Neustart, nur 127.0.0.1, Demo-Image gesperrt | A, V | echter Prozess |
| Inventar-Export: CSV (BOM, Semikolon), PDF je Ordner oder alle in einem (A4 quer, mehrseitig), Auswahl, Key maskiert/aus | A, V | |
| Unicode-Namen (NFC/NFD, Steuerzeichen, Umschrift), monotone Laufzeit, Win-11-Option nur von Hand | A, V | |
| Hilfe: Reihenfolge, Suche, Test auf Menüeinträge/Querverweise/Anrede/Ich-Form, Sichtprüfung hell/dunkel | A, V | 24 Kapitel als Screenshot |
| Bandbreite: ein Strom und 3 parallele ±10 % der Grenze, gerecht verteilt, Ändern im Lauf, Zeitfenster (Mitternacht, Wochenende), Export | A | Ende-zu-Ende über den Demo-Agent (24 Mbit/s); Sichtprüfung Einstellungen/Serverlast |
| Spaltenbreiten: vier Listen und sechs Tabellen im Gerätefenster mit der Maus verstellbar, nach Neustart gleich | A, V | xdotool-Ziehen unter Xvfb |
| Debian-Direktinstallation mit echter Debian-13.7.0-Netinst-ISO | R | 05.11.2026 (Dominik) |
| Doppelter HP-Eintrag verschwindet nach dem Update | R | 05.11.2026 (Dominik) |
| B-001: zwei baugleiche CompactPlayer gleichzeitig → zwei Einträge | R | 05.11.2026 (Dominik) |
| B-002: OS installieren mit steckendem Agent-Stick → startet nach 15 s von der Disk | R | 05.11.2026 (Dominik) |
| Wake-on-LAN: Gerät aus → „Einschalten“ → Windows startet | R | 05.11.2026 (Dominik, HP EliteBook 850 G1) |
| Demo-Gerät komplett: DEMO-PC, Disk-Image/Zurückspielen, Sperre für echte Geräte, Fehler-Demo, Automatisierung, Prozess beendet; Ä-027 ohne NAS, NAS unberührt, Demo-Daten zurücksetzen, alte Demo-Images | R | 05.11.2026 (Dominik) |
| Ä-014: NAS-Webseite öffnet DSM (https 5001 bzw. http 5000) | R | 05.11.2026 (Dominik) |
| Netzwerkstart-Protokoll: echte UEFI- (OVMF, shim/grub) und BIOS-Abläufe (iPXE, pxelinux), nicht freigeschaltet | A | Labor mit dnsmasq 2.91 und QEMU |
| BIOS-Reiter: Lesen/Setzen über nachgebautes firmware-attributes-sysfs (mit Passwort), Vergleich, CSV, Demo-Agent | A, V | echte HP-Hardware noch offen |
| Hardware-Test: Akku/Temperatur/SMART ATA+NVMe/Selbsttest-Ablauf/Oberfläche mit Lesefehler/RAM/CPU, Protokoll-PDF, Demo-Agent mit Abbrechen | A, V | echte Geräte noch offen |
| Image prüfen: ✔, ein Byte geändert → ✖ mit Datei, fehlende Datei, Abbrechen, Ordner mit Unterordnern, Clonezilla, Ergebnis nach Neustart | A, V | Loop-Disk und Clonezilla-Testimage |
| Demo ohne NAS: ganzer Vorführablauf (Image, Prüfen ✔/✖, Zurückspielen, Backup, Ordner senden, Automatisierung) ohne NAS; mit NAS bleibt das NAS unverändert; Sperren Demo ↔ echt; Zurücksetzen | A, V | echter Demo-Prozess, Snapshot des NAS-Ordners |
| Gerätefenster passt sich der Übersicht an (1920×1080 ganz sichtbar, 1366×768 begrenzt) | A, V | |
| Garantie-Abfrage: Dell/HP/Lenovo-Antworten, Farben grün/gelb/rot, Schlüssel 0600 nur beim Root-Helfer | A, V | gemockte Antworten – Hersteller-Server waren gesperrt |
| Ä-043 Installer-Erkennung: Typ, Parameter, Name/Version/Hersteller der 37 Installer in `Verteilen\Software` (nur gelesen) | A | 18.11.2026, Umsetzungs-Agent; Oberfläche (GTK) ohne Bildschirm nicht geprüft |

## Offen – am realen System testen

### 1. Fixes von heute
- [ ] **B-009** (Werkzeugsuche in `imaging.py`): Disk-Image erstellen und zurückspielen funktioniert wie bisher –
  mit bestehendem Agent-Stick und, falls neu erstellt, mit neuem Stick (enthält `systools.py`).

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

### 4. Ordner senden
- [ ] NAS: `Verteilen/Software`, `Verteilen/Test Files`, `Verteilen/Content` sind da; Inhalte über Reiter Dateien hineinziehen
- [ ] Rechtsklick → Ordner senden → **Software** → Windows starten: Ordner auf dem Desktop (auch bei einem zweiten Benutzer)
- [ ] **Content …** → zwei Projekte → Desktop: `Content\Projekt …`
- [ ] Erneut senden mit geändertem Inhalt → alter Ordnerinhalt ersetzt, andere Projekte bleiben
- [ ] Windows mit Schnellstart heruntergefahren → klare Meldung „Ruhezustand bzw. Schnellstart“
- [ ] Grosser Ordner (z. B. 5 GB) → Fortschritt, Dauer notieren: ______

### 5. Automatisierung (Plan: [AUTOMATISIERUNG.md](AUTOMATISIERUNG.md))
- [ ] Reiter „Automatisierung“: Master-Image, Zieldisk, Ordner, Abschluss „Neustart“ einstellen, Schalter ein
- [ ] Gerät mit Agent-Stick starten → Liste „startet in 30 s“, am Gerät Countdown sichtbar
- [ ] **Esc am Gerät** → abgebrochen, Gerät bleibt im Agent; erst nach Neustart wieder Countdown
- [ ] Durchlauf ohne Eingriff: Schritt 1–5 in der Liste, Neustart, Windows richtet sich mit Name/Key ein, Ordner auf dem Desktop
- [ ] Danach: Häkchen aus, Liste „wieder aktiv in 3 Tagen“; Verlauf mit allen Schritten
- [ ] Mit **Netzwerkstart** statt Stick (Gerät freigeschaltet, F12 → Netzwerk)
- [ ] **Zwei Geräte gleichzeitig** bei N = 1 → zweites „wartet (Platz 1)“, startet danach
- [ ] **Andere Disk** im Gerät (oder Zieldisk absichtlich falsch) → Fehler rot, Meldung am Gerät, nichts gelöscht
- [ ] **Backup vorher** an → Backup erscheint im Reiter Backups mit Notiz „Automatisierung – vor dem Zurückspielen“
- [ ] **Backup vorher – ganze Disk** → Disk-Image der alten Disk im Reiter Images, erst danach wird zurückgespielt
- [ ] Hauptschalter: Stopp-Knopf ■ über der Geräteliste (wird rot) → Gerät startet keinen Countdown
- [ ] Vorlage speichern („Schulungs-PC“), bei zweitem Gerät anwenden, Zieldisk dort wählen
- [ ] Nach 3 Tagen: Häkchen wieder an (oder Option aus → bleibt aus)
- [ ] **Rückfrage (Ä-007), Gerät verbunden:** Häkchen *Auto* setzen → rote Zusammenfassung (Disk, Image, Gerätename,
      Backup, Abschluss, „in 3 Tagen wieder aktiv“) mit Knopf „Löschen und neu aufsetzen“; *Abbrechen* → Häkchen
      bleibt aus, kein Countdown, kein Verlaufseintrag; bestätigen → Countdown 30 s – teilweise ✔ 10.11. (Okuli, Probe-VM über den Schalter im Reiter: Zusammenfassung vollständig, „Löschen und neu aufsetzen“, Abbrechen vorgewählt → aus, kein Verlaufseintrag. Häkchen *Auto* in der Liste ✔ Dominik 10.11. an Probe-VM, nicht verbunden: Rückfrage mit „Einschalten“, Abbrechen → leer, kein Verlaufseintrag. Offen: „bestätigen → Countdown“)
- [x] **Rückfrage, Gerät nicht verbunden:** Knopf „Einschalten“ und Satz „Beim nächsten Verbinden wird die Disk gelöscht.“ – ✔ 10.11. (Okuli: Einschalten → Verlauf „Automatisierung eingeschaltet“, Ausschalten ohne Rückfrage)
- [x] **Rückfrage im Reiter:** Schalter *Automatisierung* ein → gleiche Rückfrage; *Abbrechen* → Schalter wieder aus;
      Ausschalten und andere Änderungen bei eingeschalteter Automatisierung ohne Rückfrage – ✔ 10.11. (Okuli; „andere Änderungen“ nicht einzeln geprüft)
- [x] **Unvollständig** (z. B. ohne Zieldisk): Häkchen bzw. Schalter → Meldung, was fehlt, keine Rückfrage, bleibt aus – ✔ 10.11. (Okuli, Schalter: „Kein Image gewählt · Keine Zieldisk gewählt“)
- [ ] Rückfrage bei einer VM mit Zeile „Snapshot vorher“ und beim DEMO-PC – VM ✔ 10.11. (Okuli: „Snapshot vorher: ja“), DEMO-PC offen

### 6. Demo-Gerät (Vorführung)
- (alle geprüft)

### 7. Allgemein
- [ ] I-023: Agent-Stick neu erstellen; Schnelltest auf beiden EliteBooks → Akku-Gesundheit plausibel (mit BIOS/HP-Diagnose vergleichen), SMART-Selbsttest „bestanden“, CPU-Temperatur unter Last, Netzwerk ≈ 900 Mbit/s bei 1 Gbit/s; Abbrechen während des Selbsttests; PDF-Protokoll öffnen
- [ ] I-023: Gründlich auf einem Gerät mit HDD bzw. älterer SSD → Dauer notieren: ______; Oberflächentest-Geschwindigkeit plausibel; währenddessen „Image zurückspielen“ auf dieselbe Disk → abgelehnt
- [ ] I-032/B-005: **Agent-Stick neu erstellen** (Stand mit B-005); beide HP EliteBook 850 G1 mit dem Agent starten (das nicht startende ggf. wieder im Hybrid-/Legacy-Modus) → Reiter BIOS: Schnittstelle „HP (hp-bioscfg)“ mit Einstellungen oder „nur Grundangaben“ (notieren!); beim zweiten „Vergleichen mit“ das erste → Unterschiede (z. B. PXE Internal IPV4 NIC boot)
- [ ] I-032: eine harmlose Einstellung ändern (z. B. „Fast Boot“ oder „Asset Tracking Number“) → nach dem Neustart im BIOS-Setup sichtbar, Verlauf-Eintrag; mit gesetztem BIOS-Passwort: ohne Passwort Meldung, mit falschem „abgelehnt“; CSV in Excel öffnen
- [ ] Ä-035: nach `sudo ./install.sh` und Neustart des Tools: Alt+Tab und Dock zeigen „Okula Recovery Tool“ mit Okula-Logo; Startmenü-Eintrag nur einmal vorhanden; Autostart funktioniert weiterhin
- [ ] Ä-032: in Geräte, Images, Dateien, Backups und im Gerätefenster (Aufträge, Disks, Images, Backups, Netzwerk, Verlauf) je eine Spalte schmaler/breiter ziehen (auch „Status“ und „Auto“) → Tool neu starten → Breiten bleiben; nicht verstellte Spalten passen sich dem Inhalt an
- [ ] I-030: Menü → Einstellungen … → Bandbreite **100 Mbit/s** → Disk-Image eines echten Geräts: Durchsatz in der Serverlast (LAN) und im Switch ≈ 100 Mbit/s (± 10 %), „begrenzt: 100 Mbit/s“ in der LAN-Kurve, Log-Zeile zu Beginn; während des Auftrags auf 300 Mbit/s ändern → Durchsatz steigt sofort, Restzeit rechnet neu
- [ ] I-030: zwei Aufträge gleichzeitig (z. B. Disk-Image + Zurückspielen) → zusammen ≈ Grenze, je etwa die Hälfte; Zeitfenster so setzen, dass es gerade endet → danach unbegrenzt; Reiter Dateien (Kopieren aufs NAS) bleibt schnell
- [ ] Ä-028: Symbole Neu starten / Herunterfahren unter der Geräteliste und im Gerätefenster – Tooltip, Rückfrage, nur aktiv bei verbundenem Gerät; Menü Tools ohne „Gerät herunterfahren“; Symbole auch im dunklen Design sichtbar
- [ ] I-007: Rechtsklick auf ein **grosses Image** (z. B. 200 GB) → „Image prüfen …“ – **Dauer notieren** (Lesen vom NAS), Fortschritt/Restzeit plausibel, Tool bleibt bedienbar; Abbrechen beendet sofort, nichts gespeichert
- [ ] I-007: Ordner prüfen (mehrere Images, ein Clonezilla-Image) → Zusammenfassung; Spalte „Geprüft“ ✔/✖ bleibt nach Neustart des Tools; während der Prüfung lässt sich das Image nicht löschen; Verlauf des Geräts zeigt die Prüfung
- [ ] Ä-025: F1 → Kapitelliste in der Reihenfolge des Ablaufs, „Demo-Gerät“ zuletzt; Suchfeld (Ctrl+F): „garantie“ zeigt nur passende Kapitel, Treffer gelb, Esc leert; Hilfe im dunklen Design: Farbfelder grün/gelb/rot lesbar
- [ ] Ä-025: Menüleiste unverändert (alle Einträge, Demo-Häkchen unter Extras), Hilfe → Tastenkürzel zeigt Ctrl+F
- [ ] **Hilfe (F1):** alle Kapitel öffnen – Text vollständig, keine Formatierungsfehler, Menü- und Knopfnamen stimmen (Ä-024)
- [ ] Fortschrittstexte in neuer Form („Stick wird geprüft …“) bei Agent-Stick erstellen und USB formatieren
- [ ] Ä-021: OS installieren → Windows-11-ISO auf einem nicht tauglichen Gerät (z. B. 4.–7. Gen. Intel) → Grund und Microsoft-Hinweise sichtbar, „Installieren“ erst mit Häkchen „Trotzdem installieren“; danach Gerätefenster → Übersicht → Windows 11 zeigt „⚠ Am … trotzdem installiert“, Verlauf-Eintrag, Inventar-Export Spalte Win-11 mit Vermerk; auf tauglichem Gerät erscheint nichts davon
- [ ] Ä-021: Boot-Stick aus Windows-11-ISO → „Auch für nicht unterstützte Hardware“ ist aus; Einschalten fragt nach; Stick auf altem Gerät: ohne Häkchen meldet Setup „Dieser PC erfüllt die Anforderungen nicht“, mit Häkchen läuft es durch
- [ ] Ä-018: Automatisierung durchlaufen lassen → Liste „wieder aktiv in 3 Tagen“, Verlauf „wird in 3 Tagen wieder eingeschaltet“
- [ ] Ä-020: Ordner „Zürich“ auf dem NAS vom Mac aus anlegen, im Tool denselben Namen anlegen → „existiert bereits“; Gerät „Büro-PC“ → OS installieren zeigt „Buero-PC“
- [ ] I-013: `sudo ./install.sh` (installiert python3-reportlab); Menü → Inventar exportieren → alle Geräte, CSV + PDF → CSV in Excel öffnen: Umlaute richtig, Spalten getrennt; PDF mit Kopf (Ordnername, Datum), Tabelle lesbar, Seitenzahl
- [ ] I-013: Rechtsklick auf einen Ordner → nur dessen Geräte (inkl. Unterordner); „Markierte Geräte“ mit 2 Häkchen → nur diese
- [ ] Ä-016: PDF „je Ordner eine Datei“ → pro Ordner (auch Unterordner) ein PDF mit dem Ordnernamen als Titel; „alle Geräte in einer Datei“ → ein PDF mit allen gewählten Geräten
- [ ] Ä-015: Gerät öffnen (Doppelklick) → Übersicht komplett sichtbar bis „Garantie bis“, ohne Scrollen (Full-HD-Bildschirm)
- [ ] Ä-017: Geräteliste ohne Spalte „Win 11“; Gerätefenster → Übersicht zeigt „Windows 11“ weiterhin
- [ ] I-013: „Windows-Key nicht exportieren“ an → kein Key in CSV/PDF; aus → nur `XXXXX-…-ABCDE`; letztes Image/Backup stimmt mit Gerätefenster überein (NAS verbunden)
- [ ] I-025: `sudo ./install.sh` erneut (neuer Root-Helfer `okula-warranty`, sudo-Regel); `ls -l /etc/okula-recovery/warranty.cred` nach dem Speichern eines Schlüssels → `-rw------- root root`; Schlüssel stehen **nicht** in `~/.config/okula-recovery/config.json` und nicht in einem Export (`grep` im Export)
- [ ] I-025 Lenovo (ohne Schlüssel): Gerätefenster → Übersicht → „Beim Hersteller abfragen“ → Datum stimmt mit pcsupport.lenovo.com überein; neues Lenovo-Gerät wird nach dem Erfassen einmal automatisch abgefragt
- [ ] I-025 Dell (sobald TechDirect-Schlüssel da): Menü → Einstellungen → Garantie-Abfrage → Client-ID/Secret speichern → „✔ gespeichert“; Abfrage → Datum wie auf dell.com/support
- [ ] I-025 HP (sobald HP-Schlüssel da): wie Dell; Datum wie auf support.hp.com
- [ ] I-025: Farben – Datum > 90 Tage grün, ≤ 90 Tage gelb, abgelaufen rot (von Hand testen: „Von Hand …“ mit Datum in 30 Tagen bzw. gestern); ohne Internet → Meldung „keine Verbindung“, altes Datum bleibt
- [ ] Ä-002: Image einer grösseren Disk (z. B. 512 GB, Windows mit Recovery) auf eine kleinere SSD (256 GB): Dialog zeigt „lässt sich anpassen“ mit Zahlen → Häkchen → neues Image `…_für_256GB` im Reiter Images, Original unverändert → Windows startet (evtl. kurze Laufwerksprüfung), C: hat die neue Grösse, Recovery am Ende vorhanden
- [ ] Ä-002: zu viele Daten für die kleine Disk → klare Meldung mit Zahlen, nichts gelöscht; Automatisierung mit kleinerer Disk (Option an) läuft durch
- [ ] I-024: Agent-Stick neu erstellen, Gerät starten, Inventar neu einlesen → Gerätefenster → Übersicht: „Windows 11“ mit Grund und „TPM / Start“ stimmen (mit BIOS-Angaben vergleichen: TPM/PTT, Secure Boot); je ein altes (z. B. 7. Gen. Intel) und ein neues Gerät
- [ ] Ä-011: Gerätefenster → Übersicht → „Starttasten“ stimmt für eure Geräte (HP, Dell, Lenovo …); Tabelle im Stick-Dialog sichtbar
- [ ] Gerätename mit Umlaut/Unterstrich (z. B. „Büro_PC_01“) bei OS installieren → Hinweis zeigt Name auf dem Gerät
- [ ] Export auf altem/neuem Server: Vorlagen und „höchstens gleichzeitig“ kommen mit

### 8. Virtuelle Maschinen – Grundlage (I-001 Aufträge 1 und 1b)
Installation, Brücke, libvirt und Probe-VMs am 06.11. geprüft (siehe „Bereits geprüft“). Noch offen:
- [ ] NAS im Tool erreichbar und Geräte erscheinen (Beacons/Ping-Scan) – jetzt über `br0`
- [ ] Server neu starten → `br0` kommt wieder mit derselben IP (`ip -br a`), Tool und NAS laufen
- [ ] Netzwerkstart eingeschaltet (Konfiguration zeigt schon `interface=br0`) → ein echtes Gerät (z. B. EliteBook 1)
      per Netzwerkstart → Agent startet wie vorher

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
- [x] **Windows 11 in VM-Win11 per „OS installieren …“** (Direktinstallation über den Agent) – ✔ 06.11.: Installation
      ohne Key durchgelaufen, nach dem Neustart startet Windows von der Disk (nicht wieder der Agent), keine Meldung zu
      Secure Boot/TPM
- [ ] **Windows 11 in VM-Win11 von ISO:** Neue VM VM-Win11 → zuerst Bildschirm → Von ISO starten … → Windows-11-ISO → im Fenster
      schnell eine Taste („Press any key to boot from CD“) → Windows installieren (ohne Key, „nicht aktiviert“);
      Secure Boot und TPM erfüllt die VM (keine Meldung „PC erfüllt die Anforderungen nicht“)
- [x] Danach in Windows: Gerätefenster → Netzwerk → „Beim nächsten Start den Agent laden“ → Windows neu starten →
      Agent startet; nach dem Verbinden Agent-Symbol „Neu starten“ → Windows startet wieder (nicht der Agent) – ✔ 06.11. (VM-Win11)
- [ ] Automatisierung an der VM: Image zurückspielen mit Neustart danach → Windows startet von der Disk
- [x] VM löschen … (aus) → rote Rückfrage → VM und Eintrag weg; `virsh -c qemu:///system vol-list okula` leer – ✔ 10.11. (Okuli: Probe-VM: Rückfrage, VM, Dateien und Eintrag weg)
- [ ] Ä-036: neue VM ohne System → Einschalten → Rückfrage „Die Disk von … ist leer …“ mit *Einschalten und Agent
      starten*, *Von ISO starten …*, *Trotzdem einschalten*; nach einer Installation bzw. einem Zurückspielen keine
      Rückfrage mehr

### 10. Digitaler Zwilling (I-001 Auftrag 3)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick). Netzwerkstart eingeschaltet, NAS
verbunden. Am Server ohne Oberfläche geprüft: Zwillinge aus CompactPlayer 2 und IOVERSAL-1 angelegt, gestartet,
SMBIOS mit `VM-…`, kein Treffer auf das Original, gelöscht (06.11., Agent).
- [ ] Gerätefenster **CompactPlayer 1** (hat ein Image auf dem NAS: „CompactPlayer TEST – 2026-10-27_1217_sda“) →
      oben rechts *VM mit dieser Hardware erstellen …* → Vorschau: Hersteller/Modell OEM SHARKBAY ✔, Firmware
      BIOS bzw. UEFI je nach Partitionstabelle, Netzwerkkarte ~ Intel, Windows-Schlüssel ✖; Häkchen *Letztes Image des
      Geräts einspielen* an, neuestes Image gewählt → Erstellen
- [ ] Gerätefenster der VM öffnet, Reiter Aufträge: Agent starten (1/3) → Agent nach etwa 30 s verbunden → Image
      prüfen / Zurückspielen → VM fährt herunter; Verlauf der VM „Zwilling von CompactPlayer 1 (Image …)“, beim
      Original „Zwilling VM-CompactPlayer-1 erstellt“
- [ ] Danach *Einschalten* (keine Rückfrage „Disk leer“) und *Bildschirm* → Windows des Images startet
- [ ] Inventar der VM (nach dem nächsten Agent-Start): Hersteller/Modell wie das Original, Seriennummer `VM-…`, UUID
      `0c1a…`; Übersicht zeigt „Zwilling von CompactPlayer 1“ (Klick öffnet das Gerät); **Original unverändert, keine
      Zusammenführung**, keine neue Zeile unter „Neu / nicht einsortiert“
- [ ] Gerät ohne Image (z. B. CompactPlayer 2): Häkchen aus und ausgegraut, „Kein Image dieses Geräts auf dem NAS“
- [ ] Rechtsklick auf ein Gerät → *VM mit dieser Hardware erstellen …*; bei VMs und beim DEMO-PC nicht vorhanden
- [ ] Danach Zwilling löschen (*VM löschen …*); Images auf dem NAS bleiben

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
- (Abbruch, wenn der automatische Snapshot fehlschlägt: „Nicht gestartet: Snapshot vorher fehlgeschlagen …“, kein
  Auftrag – mit Tests geprüft, am Server kaum herbeizuführen; tritt es auf, Meldung notieren)
- [ ] Nach dem Zurückspielen zurück zum automatischen Snapshot → wieder der Stand davor
- [ ] Leere VM: Snapshot „leer“ → OS installieren → zurück zu „leer“ → *Einschalten* fragt wieder „Die Disk von … ist
      leer“ (Ä-036)
- [ ] *Löschen …* eines Snapshots: Rückfrage, Balken im Reiter, VM so lange gesperrt; danach aktueller Stand
      unverändert (VM startet wie vorher), Verlauf „… gelöscht“; Zeit für den ältesten Snapshot einer Windows-VM notieren
- [ ] *Hardware ändern …* mit Snapshots: Disk ausgegraut mit Grund „zuerst Snapshots löschen“; RAM ändern geht
- [ ] Platzwarnung unter der Liste erscheint unter 50 GB frei (nur zur Kenntnis, schwer herbeizuführen)
- [x] *VM löschen …* einer VM mit Snapshots → `virsh -c qemu:///system vol-list okula` ohne Dateien dieser VM – ✔ 10.11. (Okuli: Probe-VM mit 1 Snapshot: keine Dateien übrig)
- [ ] **Master-Ablauf** ([MASTER-IMAGE.md](MASTER-IMAGE.md)): Windows in der VM einrichten → herunterfahren →
      Snapshot **„vor Sysprep“** → Sysprep → Einschalten und Agent starten → Disk-Image → zurück zu „vor Sysprep“ →
      Windows startet wieder im eingerichteten Zustand (nicht in der Ersteinrichtung)

### 12. Projektübersicht (I-034)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick).
- [x] Extras → Projektübersicht … → Firefox öffnet „Projektübersicht – Okula Recovery Tool“; zweiter Aufruf öffnet
      dieselbe Adresse (gleicher Port) – ✔ 10.11. (Okuli: Menü per Bedienungshilfe, Firefox geöffnet, zweiter Aufruf gleicher Port 39995)
- [x] Alle offenen Tests (Vorbereitung, Abschnitte 2–12) sind da; ✔ ok / ✖ Fehler und Kommentar → „gespeichert“;
      nach „Neu laden“ und nach Neustart des Tools noch da; `ls -l ~/.local/share/okula-recovery/` → Datei `-rw-------` – ✔ 10.11. (Okuli: über die Schnittstelle: 14 Gruppen inkl. 13, ok+Kommentar gespeichert, nach Neuladen da, Datei 0600; Neustart des Tools nicht geprüft)
- [x] Bugs, Änderungen, Ideen mit ID, Prio, Text; Kommentar, Prio-Wunsch und Status-Wunsch speichern → „Prio 🟡 → Wunsch 🔴“ – ✔ 10.11. (Okuli: Prio- und Status-Wunsch gespeichert (Schnittstelle))
- [ ] Offene Punkte (Übergabe) und Prompts mit Status sichtbar und kommentierbar
- [x] Neue Notiz anlegen, ändern, löschen – ✔ 10.11. (Okuli: anlegen, ändern, löschen (Schnittstelle))
- [ ] Übersicht oben mit Zählern; Suche und alle Filter wirken; Filter bleiben nach Neuladen der Seite
- [ ] In einer Kopie von TESTS.md einen Testtext ändern (Projektordner in den Einstellungen auf die Kopie) →
      alte Rückmeldung unter „Rückmeldungen ohne Eintrag“
- [x] In der JSON-Datei bei einem Eintrag `"uebernommen": "2026-11-10"` setzen → „Neu laden“: grau, „übernommen 10.11.“;
      erneute Änderung → wieder neu – ✔ 10.11. (Okuli: übernommen sichtbar, erneute Änderung → wieder neu)
- [x] Adresse ohne Token (`http://127.0.0.1:<port>/`) → 403; von einem anderen Rechner `http://<server-ip>:<port>/…` → keine Verbindung – ✔ 10.11. (Okuli: 403 ohne Token, Server nur auf 127.0.0.1)
- [ ] Menü → Einstellungen … → Projektordner (Repo) auf einen nicht vorhandenen Ordner → Seite zeigt Hinweis statt Fehler; danach wieder leeren
- [ ] Dunkelmodus (B-008): Art der Notiz und Filter Priorität lesbar, auch aufgeklappt; Suchfeld, Textfelder,
      Platzhaltertext und Knöpfe dunkel mit heller Schrift; Hellmodus wie vorher

### 13. VM-Disk beim Zurückspielen vergrössern (Ä-037)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick). Zum Testen eine Probe-VM mit
128 GB (*Neue virtuelle Maschine …*, VM-Win11, Disk auf 128 GB stellen) und ein Image einer 256- oder 512-GB-Disk.
- [x] VM mit Agent, *Image zurückspielen …* mit dem grossen Image → unter dem Prüftext zwei Optionsfelder, „VM-Disk
      auf <N> GB vergrössern und zurückspielen“ vorgewählt (N = Quelldisk aufgerundet), Tooltip mit dem Ablauf;
      „Image an die kleinere Disk anpassen“ wählbar, wenn die Daten passen (sonst grau mit Grund) – ✔ 10.11. (Okuli: Probe-VM VM-Klein 64 GB + CompactPlayer 120 GB: beide Wege, Vergrössern auf 121 GB vorgewählt, Tooltip)
- [x] Vergrössern starten → ein Auftrag „VM-Disk vergrössern und zurückspielen …“ mit den Schritten „VM wird
      heruntergefahren (1/4)“, „Disk wird vergrössert (2/4)“, „Agent wird gestartet (3/4)“, „Zurückspielen (4/4)“;
      danach `virsh -c qemu:///system vol-info --pool okula <VM>.qcow2` → Kapazität N GB, Image zurückgespielt,
      Windows startet; Verlauf „VM-Disk von 128 GB auf N GB vergrössert“ – ✔ 10.11. (Okuli: Auftrag mit 4 Schritten in ~4 min, Disk 121 000 000 000 Byte, Verlauf „von 64 GB auf 121 GB“. Windows-Start nicht prüfbar: Image ist BIOS/MBR, VM-Klein UEFI)
- [x] „Vorher Snapshot“ angehakt → Snapshot im Reiter *Snapshots* entsteht **nach** dem Vergrössern (Log „Snapshot
      vorher wird erstellt (nach dem Vergrössern)“), Auftrag läuft durch – ✔ 10.11. (Okuli: Snapshot „vor Zurückspielen“ nach dem Vergrössern, Auftrag durch)
- [x] VM mit Snapshots → Vergrössern grau, Prüftext und Tooltip „Die VM hat Snapshots – zuerst im Reiter
      „Snapshots“ löschen …“; Anpassen weiter wählbar, wenn die Daten passen – ✔ 10.11. (Okuli: L15 512 GB: Vergrössern grau mit Grund, Anpassen vorgewählt)
- [ ] Zu wenig Platz im Pool (z. B. Image grösser als frei – sonst nur am Prüftext prüfbar) → Vergrössern grau mit
      Zahlen „frei … GB, nötig … GB“
- [ ] Beide Wege nicht möglich → *Zurückspielen* bleibt gesperrt, Prüftext „Zurückspielen nicht möglich.“
- [ ] Windows in der VM reagiert nicht auf das Herunterfahren (Agent ohne ACPI) → nach 60 s hart ausgeschaltet,
      Log „VM hat nicht reagiert – hart ausgeschaltet“
- [ ] Abbrechen während „Agent wird gestartet (3/4)“ → Auftrag abgebrochen, nichts zurückgespielt, Disk bleibt
      vergrössert (Log), Verlauf „… abgebrochen“
- [ ] Echtes Gerät mit kleinerer Zieldisk → Dialog wie bisher (Häkchen „Für diese Disk anpassen“, keine Optionsfelder)
- [x] B-007: 1-TB-Image `2026-10-29_1133_nvme0n1` auf VM mit 64 GB → Anpassen: nicht möglich (belegt ~397 GB) – ✔ 10.11. (Okuli: Probe-VM VM-Klein 64 GB, Prüftext „Anpassen: nicht möglich – … auf nvme0n1p4 sind 397.7 GB belegt, mit Reserve 437.4 GB nötig …“; Vergrössern auf 1001 GB möglich, nicht gestartet; Probe-VM gelöscht)
- [x] Neue VM mit Profil VM-Win11 → 256 GB, Modell „Okula NVMe SSD 256GB“; bestehende VMs unverändert – ✔ 10.11. (Okuli: Dialog zeigt NVMe-SSD 256 GB)

### 14. Stick fertig und Prüfung am Schluss (Ä-038)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick nötig).
- [x] *Menü → Agent-USB-Stick erstellen …* → während des Baus steht unter dem Balken fett „Stick erst abziehen, wenn
      „Stick fertig“ erscheint.“; im Log „Stick wird geprüft“ kurz vor dem Ende; danach Fenster „Agent-Stick fertig“,
      Text „Der Stick kann jetzt abgezogen werden.“, Knopf „OK“; Balken „Stick bereit“, Hinweis verschwunden;
      Stick startet am Gerät – teilweise ✔ 10.11. (Okuli: Hinweis fett während des Baus, Popup „Agent-Stick fertig“ mit OK, Balken 100 %, Hinweis danach weg; am Server nachgeprüft: okula-agent.squashfs 3,4 MB, gültiger Kopf. Log-Zeile „Stick wird geprüft“ und Start am Gerät ✔ Dominik 10.11.)
- [ ] Stick während des Baus abziehen (z. B. bei „Live-System wird kopiert“) → rotes Fenster „Stick nicht fertig“
      mit „Stick wurde während des Schreibens abgezogen – Stick neu erstellen.“ und „Stick nicht verwenden – neu
      erstellen.“, Knopf „Schliessen“; Balken „Fehlgeschlagen“, Log bleibt
- [ ] *Restore-Stick aus Image …* → am Ende „Restore-Stick fertig“; Stick spielt das Image am Gerät zurück
- [ ] *Boot-Stick aus ISO …* → am Ende „Boot-Stick fertig“ (bzw. rot „Stick nicht fertig“ bei Fehler)
- [ ] Andere Fehlermeldungen „Aktion fehlgeschlagen“ (z. B. Wake-on-LAN bei einem Gerät ohne bekannte
      Kabel-Netzwerkkarte) → Knopf heisst jetzt „Schliessen“

### 15. Hardware-Test: Prozessor-Fehler seit dem Start (B-011)
Nach `git pull && sudo ./install.sh` das Tool neu starten und **neuen Agent-Stick** erstellen.
- [x] SRV-002 mit neuem Stick starten, Reiter *Hardware-Test* → *Schnelltest* → „CPU unter Last“ mit Hinweis auf
      Hardware-Fehler (CPU 3, Bank 0, Anzahl), Details „Hardware-Fehler CPU 3, Bank 0 (korrigiert): … Mal seit dem
      Start“ mit Beispielzeilen; Protokoll-PDF zeigt dasselbe. **Gelb**, wenn während der Minute Last keine neuen
      Meldungen kamen; meldet CPU 3 wie auf dem Foto jede Sekunde einen Fehler, kommen während der Last neue dazu →
      **rot** („… während der Last gemeldet …“) – ✔ 11.11. (Dominik; Netzwerkstart, Schnelltest 10:51: gelb, CPU 3 Bank 0
      korrigiert 37 Mal + 2 ohne Zuordnung seit dem Start, keine neuen während der Last)
- [ ] Gerät ohne MCE (z. B. EliteBook) → „CPU unter Last“ weiterhin grün, Detail „Hardware-Fehler: keine seit dem Start“
- [ ] Erscheint stattdessen „Hardware-Fehler nicht prüfbar (Kernel-Protokoll nicht lesbar)“: am Gerät
      `journalctl -k -b | tail` und `dmesg | tail` prüfen und an Okuli melden

### 16. Windows-Kontoname (B-012)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick).
- [ ] CompactPlayer (bzw. VM-Zwilling „VM-CompactPlayer-1“): *OS installieren …* mit Windows-ISO, *Benutzername*
      vorbelegt mit „Okula“ → Installation läuft ohne Eingriff bis zum Anmeldebildschirm, Konto „Okula“ meldet sich
      einmal automatisch an und verlangt ein neues Passwort (keine Neustart-Schleife)
- [ ] Im selben Dialog *Benutzername* „Benutzer“ (auch „ benutzer “) → unter der Disk erscheint die Meldung
      „Der Name ‚Benutzer‘ ist in Windows … vergeben …“, *Installieren* bleibt gesperrt; „Okula“ → wieder frei
- [ ] *Boot-Stick aus ISO …* (Windows), *Benutzername* „Administrator“ → *Stick erstellen* zeigt Fenster
      „Benutzername nicht möglich“, der Stick wird nicht gelöscht

### 17. Windows für Master-Image im Audit-Modus (I-038)
Nach `git pull && sudo ./install.sh` das Tool neu starten (kein neuer Agent-Stick). Am VM-Zwilling
(z. B. „VM-CompactPlayer-1“), danach am echten Gerät.
- [ ] *OS installieren …* mit Windows-ISO: Häkchen *Für Master-Image (Audit-Modus)* → Windows-Schlüssel, Lokales
      Konto, Benutzername, Passwort und Computername ausgegraut; Region, Datenschutz, BitLocker bleiben wählbar;
      unter der Disk steht „Startet im Audit-Modus für ein Master-Image …“. Bei einer Linux-ISO kein Häkchen
- [ ] Installation läuft ohne Eingriff und startet im **Audit-Modus** (Administrator angemeldet, Sysprep-Fenster
      erscheint); kein Konto „Okula“ angelegt
- [ ] Setup-Partition „OKULASETUP“ weg, C: über die ganze Disk (Datenträgerverwaltung);
      `C:\Windows\Temp\okula-aufraeumen.log` vorhanden
- [ ] Nach ca. 3 Minuten: `C:\Windows\Panther\unattend.xml` **fehlt** (`dir C:\Windows\Panther`)
- [ ] Tastatur Schweiz, Formate de-CH, Zeitzone Zürich gesetzt
- [ ] Neustart im Audit-Modus → startet wieder im Audit-Modus (kein OOBE)
- [ ] Log des Auftrags nennt die nächsten Schritte (Sysprep … /generalize /oobe /shutdown, Disk-Image, Master);
      Verlauf „Windows-Installation … für Master-Image (Audit-Modus) → …: vorbereitet …“
- [ ] VM: Snapshot „vor Sysprep“ → Sysprep → mit Agent *Disk-Image erstellen …* → als Master markieren
- [ ] Image mit *Danach anpassen* zurückspielen → startet **nicht** im Audit-Modus, sondern in die normale
      Einrichtung mit Gerätename und Windows-Schlüssel (und ggf. Konto)
- [ ] Ohne Häkchen: Direktinstallation wie bisher (Konto, Computername, Schlüssel)

### 18. Direktinstallation mit OEM-Schlüssel: Setup-Partition (B-013)
An einem Gerät mit Windows-Schlüssel im BIOS (OEM, z. B. HP/Lenovo-Notebook), Windows Pro/Home – nicht Enterprise.
- [ ] *OS installieren …* mit Schlüssel aus dem BIOS → nach der Einrichtung in der Datenträgerverwaltung prüfen: Setup-Partition „OKULASETUP“ **weg** und C: über die ganze Disk? (bleibt sie stehen: B-013 bestätigt)
- [ ] `C:\Windows\Temp\okula-aufraeumen.log` vorhanden?

### 19. Windows anpassen (I-039)
Nach `git pull && sudo ./install.sh` das Tool neu starten und **Agent-Stick bzw. Netzwerkstart neu erstellen** (neuer
Agent-Befehl). Je eine VM mit Windows 10 Pro 22H2 und Windows 11 Pro (installiert, mit lokalem Konto, z. B. „Okula“),
Windows ganz heruntergefahren, dann mit dem Agent starten.
- [ ] Rechtsklick auf das Gerät → *Windows anpassen …* (auch *Tools* und Knopf im Gerätefenster): Dialog mit allen
      Gruppen; Vorlage *Player* setzt alles ausser *Kamera* und *Druckwarteschlange*, „Vorlage: Player“;
      ein Häkchen ändern → „Vorlage: Player (geändert)“; *Senden* gesperrt, bis Benutzername und Passwort da sind
- [ ] Vorlage *Player* senden → Auftrag „Windows anpassen“ fertig, Log nennt die Auswahl (ohne Passwort), Verlauf
      „Windows anpassen (Vorlage Player: …): Startskript abgelegt …“
- [ ] Neustart in Windows → `C:\Windows\Temp\okula-windows-anpassen.log`: je Einstellung „ok“ (Fehler mit Grund),
      „Ende: … ok, … mit Fehler“; **kein Passwort** im Protokoll
- [ ] Store-Apps weg (Xbox, Bing-Wetter/News, Solitaire, Store …; Kamera noch da), auch für ein neu angelegtes Konto;
      `Get-AppxProvisionedPackage -Online` ohne die entfernten Apps
- [ ] Automatische Anmeldung als „Okula“ (spätestens beim zweiten Start); Energieplan Höchstleistung, Bildschirm/
      Standby „Nie“, kein Ruhezustand/Schnellstart, kein Sperrbildschirm; Dateiendungen und versteckte Dateien sichtbar,
      Explorer öffnet „Dieser PC“, Symbole auf dem Desktop; Dienste WSearch/SysMain/RemoteRegistry „Deaktiviert“
- [ ] Danach weg: `C:\Windows\System32\GroupPolicy\Machine\Scripts\Startup\okula-windows-anpassen.*`, Eintrag in
      `scripts.ini`, `*.okula-nachher`; `gpt.ini` gelöscht (vorher keine) bzw. wie vorher mit höherer Version;
      unter `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\Scripts\Startup` kein Okula-Eintrag
- [ ] Zweiter Neustart: **kein erneuter Lauf** (keine neuen Zeilen im Protokoll)
- [ ] Vorhandene lokale Gruppenrichtlinie (z. B. mit `gpedit.msc` eine Einstellung und ein eigenes Startskript
      setzen) → *Windows anpassen* senden → nach dem Lauf beides noch da und wirksam (`gpresult /r`)
- [ ] Vorlage *Laptop* an der zweiten VM: Updates unverändert, Kamera und Store bleiben, keine automatische Anmeldung
- [ ] Windows im Schnellstart (normal „Herunterfahren“) → Meldung „Windows ist im Ruhezustand bzw. Schnellstart …“,
      nichts abgelegt
- [ ] Gerät ohne Windows (z. B. Linux) → Meldung „kein Windows erkannt“, nichts gesendet
- [ ] Automatische Anmeldung mit einem Konto, das es nicht gibt → Protokoll „FEHLER Automatische Anmeldung: Konto … nicht
      vorhanden – nichts gesetzt“, die übrigen Einstellungen „ok“
- [ ] Dauer der App-Entfernung am echten Gerät (Startskripte haben eine Wartezeit von 10 min, danach bricht Windows sie
      ab – Protokoll muss „Ende“ zeigen)
- [ ] Alter Agent (Stick vor I-039) → Meldung „Agent zu alt …“
- [ ] DEMO-PC: *Windows anpassen …* → Auftrag nach wenigen Sekunden „fertig“

### 20. Direktinstallation auf Disk mit altem Windows (B-014, Ä-039, B-015)
Nach `git pull && sudo ./install.sh` das Tool neu starten und **Agent-Stick bzw. Netzwerkstart neu erstellen**
(Agent geändert). Am CompactPlayer 1 (bzw. VM mit installiertem, hart ausgeschaltetem Windows).
- [ ] *OS installieren …* auf eine Disk, auf der schon ein Windows aus einer früheren Direktinstallation liegt →
      Log des Auftrags zeigt „Alte Daten auf den neuen Partitionen werden gelöscht …“ und „Windows-Partition wird
      geprüft …“; `install.cmd` findet die Windows-Partition, Installation läuft ohne Eingriff durch
- [ ] Zweiter Versuch direkt hintereinander (ohne Windows zu starten) → ebenfalls ohne Fehler
- [ ] `okula\install.log` (vor dem Aufräumen bzw. bei einem Fehler): Zeile „Windows-Partition C: - Markierung …“
- [ ] Fehlerfall-Diagnose sichtbar (absichtlich auslösen, z. B. am VM-Zwilling: nach „vorbereitet“ vor dem Neustart
      ausschalten, auf der Windows-Partition Bezeichnung auf „Windows“ ändern und Markierung löschen, dann von der
      Setup-Partition starten): Editor zeigt
      oben den Kasten „Nach dem Schliessen dieses Fensters schaltet sich das Geraet aus …“, darunter Laufwerksliste
      (`list volume`) und je Laufwerk Markierung ja/nein und Inhalt; das Laufwerk mit „Windows“ wird **nicht**
      formatiert
- [ ] Im selben Zustand Shift+F10 → öffnet sich eine Eingabeaufforderung? Sonst Weg über *Datei → Öffnen*,
      Dateityp „Alle Dateien“, `X:\Windows\System32\cmd.exe` mit Rechtsklick → Öffnen (Ergebnis melden, Hilfe ggf.
      anpassen); nach dem Schliessen des Editors schaltet sich das Gerät aus
- [ ] Nur Bezeichnung „OKULAWIN“ ohne Markierung (Markierungsdatei löschen) → Installation läuft trotzdem durch,
      `install.log`: „Markierung … fehlt, Laufwerke mit Bezeichnung OKULAWIN: 1“
- [ ] Meldung bei nicht übernommenem Schreiben: nicht künstlich auslösbar; falls sie am CompactPlayer erscheint
      („Schreiben auf die Disk wird nicht übernommen – Disk prüfen (Windows-Partition …)“), Auftrag bricht ab,
      Gerät startet **nicht** neu, kein Starteintrag „Okula Windows-Installation“ als BootNext → Meldung samt Klammertext
      notieren (Hinweis auf die SSD, B-014 in [TECHNIK.md](TECHNIK.md))
- [ ] Startet nach der Installation direkt Windows (CompactPlayer, B-015): nach `dism`/`bcdboot` startet das Gerät
      **nicht** erneut die Setup-Partition (kein zweiter Lauf von `install.cmd`), sondern das neue Windows. Falls
      möglich `okula\install.log` vor dem Aufräumen ansehen: „Windows Boot Manager an erste Stelle - Rueckgabe 0“ und
      `bcdedit /enum firmware` nachher mit `{bootmgr}` zuoberst in `displayorder` (dafür kein neuer Agent-Stick nötig)

### 21. Grafikkarte im Inventar (I-037)
Nach `git pull && sudo ./install.sh` das Tool neu starten und **Agent-Stick bzw. Netzwerkstart neu erstellen**
(Agent geändert, neu mit `pciutils`). Grösse des Agent-Teils vorher/nachher notieren (erwartet: weniger als 1 MB mehr).
- [x] ✔ 17.11. (Dominik: Grafikkarte wird gelesen) CompactPlayer (Master, NVIDIA GT 740): vom neuen Stick starten, *Inventar neu einlesen* → Übersicht zeigt
      „Grafikkarte 1“ (Intel-Onboard, falls im BIOS aktiv) und „Grafikkarte 2“ „NVIDIA GeForce GT 740 (GK107)
      (0000:01:00.0)“ bzw. bei nur einer Karte „Grafikkarte“; HDMI-Audio der Karte erscheint **nicht**; Tooltip
      zeigt PCI-Adresse, IDs `10de:0fc8`, Hersteller der Karte und Treiber (z. B. nouveau)
- [ ] Laptop mit Intel-Grafik: *Inventar neu einlesen* → eine Zeile „Grafikkarte“, z. B. „Intel … Graphics (…)“
- [ ] VM (Agent in der VM): *Inventar neu einlesen* → Grafik der VM (z. B. „Red Hat …“ bzw. „QEMU …“), kein Fehler
- [ ] Gerät mit altem Inventar (noch nicht neu eingelesen) → Übersicht ohne Zeile „Grafikkarte“, sonst unverändert
- [ ] *VM mit dieser Hardware erstellen …* vom CompactPlayer → Vorschau zeigt Zeile „Grafikkarte“ mit ✖ „Standard-Grafik
      der VM (nicht nachgebildet)“, die VM-Hardware ist wie bisher
- [ ] DEMO-PC → Übersicht „Grafikkarte“ „Intel Iris Xe Graphics (TigerLake-LP GT2)  (0000:00:02.0)“
- [ ] Video-Server mit mehreren GPUs (falls verfügbar): jede Karte einzeln, gleiche Modelle mit verschiedenen
      PCI-Adressen, Reihenfolge nach Adresse

### 22. Einstellungen aus dem Audit-Modus (Ä-040)
Nach `git pull && sudo ./install.sh` das Tool neu starten und **Agent-Stick bzw. Netzwerkstart neu erstellen**
(Agent geändert: neues Modul `winprofile.py`). Am besten an einer VM mit Windows 10 (Snapshot „vor Sysprep“).
- [ ] VM im Audit-Modus (I-038): Desktop-Symbole anordnen, **VLC** und **Explorer** an die Taskleiste heften (Edge
      lösen, Reihenfolge merken), Explorer-Ansicht ändern (z. B. Details, Dateiendungen ein), Hintergrund ändern;
      kein weiteres Konto anlegen → Sysprep `/generalize /oobe /shutdown` → *Disk-Image erstellen …* → als Master markieren
- [ ] *Image zurückspielen*: unter *Danach anpassen* steht **„Einstellungen des Administrators übernehmen (Master)“**,
      angehakt, Tooltip erklärt es; mit *Danach anpassen* aus ist das Häkchen ausgegraut
- [ ] Log des Auftrags: „Anpassen: Gerätename und Windows-Schlüssel, Einstellungen des Administrators (Master-Image)“
      und „Einstellungen des Administrators werden übernommen – Taskleiste: VLC media player, Explorer“ (Reihenfolge
      wie am Administrator)
- [ ] Erster Start, Konto anlegen bzw. lokales Konto aus dem Dialog → Benutzer hat Symbol-Anordnung, Explorer-Ansicht,
      Hintergrund und die Taskleiste (VLC, Explorer in dieser Reihenfolge, Edge nicht mehr)
- [ ] Zweiten neuen Benutzer anlegen und anmelden → gleiche Einstellungen und Taskleiste
- [ ] Am Gerät: `C:\Users\Default\AppData\Local\Microsoft\Windows\Shell\LayoutModification.xml` enthält die Pins;
      `C:\Windows\Panther\setupact.log` bzw. `UnattendGC\setupact.log`: CopyProfile ohne Fehler; ob Windows meldet
      „Eine App-Standardeinstellung wurde zurückgesetzt“ (Hinweis Microsoft, nicht umgesetzt) – notieren
- [ ] Gegenprobe Häkchen aus: neuer Benutzer hat Standard-Taskleiste und Standard-Desktop, keine
      `LayoutModification.xml` im Standardprofil
- [ ] Gegenprobe normales Image (ohne Sysprep): Log „nicht mit Sysprep vorbereitet“, Windows unverändert
- [ ] Gegenprobe alter Agent-Stick: Log „… Taskleiste nicht übernommen: Agent zu alt“, Name/Key trotzdem gesetzt
- [ ] Automatisierung: Schritt *Anpassen* zeigt das Häkchen (Standard an), Wert bleibt nach Tool-Neustart und in
      Vorlagen; Durchlauf → gleiche Logzeilen wie oben
- [ ] Programm ohne Eintrag im Startmenü (z. B. portable `.exe` angeheftet) → liegt nach dem Zurückspielen als
      Verknüpfung unter Startmenü → *Okula* und ist auf der Taskleiste
- [ ] **Windows 11** (VM): gleicher Ablauf – Windows startet normal, nichts kaputt; ob die Taskleiste übernommen
      wird, notieren (offen, [TECHNIK.md](TECHNIK.md) „Einstellungen des Administrators übernehmen“)
- [ ] DEMO-PC: *Image zurückspielen* mit Häkchen → Log nennt „Taskleiste: Explorer, Microsoft Edge, VLC media player“

### 23. Software installieren (I-020)
Nach `git pull && sudo ./install.sh` das Tool neu starten und **Agent-Stick bzw. Netzwerkstart neu erstellen**
(Agent geändert: neuer Befehl `software`). **Seit Ä-041** kommen die Programme aus der Software-Bibliothek
(*Extras → Software-Bibliothek …*, Prüfungen zum Laden und Bearbeiten in Abschnitt 25) – nicht mehr aus
`Verteilen\Software`. In die Bibliothek laden: z. B. `vlc-3.0.24-win64.exe` (NSIS), den Adobe Reader
(`AcroRdrDC….exe` bzw. `.msi`), ein Programm unbekannten Typs und einen Ordner mit mehreren Dateien.
- [ ] Programm mit „Parameter fehlt“: in *OS installieren …* nicht ankreuzbar (ausgegraut); in der Software-Bibliothek
      Parameter eintragen → danach „bereit“ und wählbar; *Nur von Hand* → nicht wählbar
- [ ] **Direktinstallation (VM, Windows 10 oder 11)**: *OS installieren …* mit **VLC + Adobe Reader** → Log nennt die
      Programme; `okula\install.log` auf der Setup-Partition: „Software kopiert“, „Startskript Software eingerichtet“;
      nach dem ersten Start sind beide installiert, **ohne Klick**; `C:\Windows\Temp\okula-software.log` mit Start/ok
      je Programm und „Ende: 2 ok, 0 mit Fehler“; `C:\ProgramData\Okula` gelöscht; Aufgabenplanung ohne
      „Okula Software installieren“; `C:\Windows\System32\GroupPolicy` ohne `okula-software.*`
- [ ] Notieren, **wann** installiert wurde: vor der ersten Anmeldung (SetupComplete bzw. Startskript) oder erst danach;
      bei Rückgabewert 3010 genau **ein** Neustart nach dem letzten Programm
- [ ] Direktinstallation mit **OEM-Schlüssel** (Gerät mit Schlüssel im BIOS): Installation trotzdem (Startskript der
      Gruppenrichtlinie, B-013) – ggf. erst beim nächsten Start
- [ ] **Master im Audit-Modus**: *OS installieren …* mit *Für Master-Image (Audit-Modus)* und VLC → Programme sind im
      Audit-Modus installiert, `C:\Windows\Panther\unattend.xml` ist weg, Setup-Partition entfernt; danach Sysprep →
      Image → zurückspielen: VLC ist im Master
- [ ] **Zurückspielen mit *Danach anpassen*** (generalisiertes Master-Image): Liste *Software installieren* unter
      *Danach anpassen*, VLC ankreuzen → Log „Software … abgelegt“, Verlauf „Software: VLC … (wird beim ersten Start
      installiert)“; nach der Ersteinrichtung ist VLC installiert (notieren: schon vor der ersten Anmeldung oder erst
      beim nächsten Start); zusammen mit Ä-040 (Einstellungen des Administrators) und I-039 (Windows anpassen vor dem
      ersten Start senden) → beide Protokolle vollständig, lokale Gruppenrichtlinie danach wie vorher
- [ ] **Lange Installation** (z. B. grosses Paket > 10 min oder Testprogramm, das 12 min wartet): wird nicht abgebrochen,
      Protokoll „Installation läuft als geplante Aufgabe weiter“, danach „ok“
- [ ] Programm mit falschen Parametern (wartet auf Eingabe) → nach 60 min „FEHLER … abgebrochen“, die übrigen laufen
- [ ] **Automatisierung**: Schritt *Anpassen* mit Software → Auswahl bleibt nach Tool-Neustart und in Vorlagen;
      Durchlauf → Log nennt die Programme, Verlauf mit „Software: …“
- [ ] Ordner als *Nur kopieren* (z. B. „System Tools“) → liegt danach auf dem Desktop unter `Software\system-tools`
      (Name des Eintrags in der Bibliothek)
- [ ] Alter Agent-Stick: Zurückspielen mit Software → „Zurückgespielt, aber Software nicht übertragen: Agent zu alt …“
- [ ] DEMO-PC: Liste zeigt drei Beispiel-Installer (zwei bereit, einer „Parameter fehlt“), Zurückspielen mit
      Software → Auftrag „fertig“

### 24. Start ohne GRUB-Meldung (B-016)
Nach `git pull && sudo ./install.sh` das Tool neu starten und **Agent-Stick neu erstellen** (GRUB-Konfiguration geändert).
- [ ] **Start ohne GRUB-Meldung**: CompactPlayer 1 vom neuen Agent-Stick starten → keine Meldung
      „error: file `/boot/grub/font.pf2' not found“, grafisches Menü mit Okula-Logo wie bisher, Agent startet normal
- [ ] Zweites Gerät (UEFI, z. B. Laptop oder VM) vom selben Stick → ebenfalls ohne Meldung, Menü mit Logo

### 25. Software-Bibliothek (Ä-041)
Nach `git pull && sudo ./install.sh` das Tool neu starten (**kein** neuer Agent-Stick nötig).
- [ ] **Aufräumen:** Nach dem Start (NAS verbunden) Statuszeile „Verteilen/Software aufgeräumt: 21 alte
      Software-Beschreibung(en) …“; in `Verteilen\Software` sind die versteckten `.<Name>.okula.json` weg, alle übrigen
      Dateien und Ordner (OBS & plugin, Browser, ZIP, portable Tools …) unverändert; *Ordner senden → Software* wie bisher
- [ ] *Extras → Software-Bibliothek …* öffnet das Fenster; auf dem NAS gibt es den Ordner `Software-Bibliothek` neben
      `Verteilen`; Liste leer („Noch keine Programme …“)
- [ ] **Ins Tool laden …** mit `vlc-3.0.24-win64.exe` von einem USB-Datenträger → Balken, danach Zeile
      „VLC media player · 3.0.24 · NSIS · /S · 0, 3010 · bereit“; auf dem NAS `Software-Bibliothek/vlc-3.0.24/`
- [ ] Datei aus `Verteilen\Software` laden (Dateiwahl auf dem NAS) → Kopie in der Bibliothek, `Verteilen\Software`
      unverändert
- [ ] **Doppel:** dieselbe Datei nochmals laden (auch umbenannt) → Statuszeile „… ist schon in der Bibliothek …“,
      kein zweiter Eintrag
- [ ] **Ordner laden …** mit `YSUSB_V213_Win` (setup.exe und Treiberdateien) → ein Eintrag, Installer `setup.exe`;
      Ordner mit mehreren Installern (z. B. „Browser“ mit Chrome und Firefox) → Rückfrage *Installer wählen*
- [ ] Dateien/Ordner aus dem Dateimanager ins Fenster ziehen → werden nacheinander geladen
- [ ] **Abbrechen** während eine grosse Datei kopiert wird → Statuszeile „… abgebrochen – in der Bibliothek bleibt
      nichts Halbes zurück“; auf dem NAS kein Rest (`.…partial`) und kein Eintrag
- [ ] In der Liste Programm, Version, Parameter und Rückgabewerte direkt ändern (Zelle anklicken, Enter) → bleibt nach
      *Aktualisieren* bzw. neuem Öffnen; „Parameter fehlt“ wird nach Eintrag der Parameter „bereit“; ungültige
      Rückgabewerte → Meldung „Nicht gespeichert“
- [ ] *Bearbeiten …*: Art *Nur kopieren* für einen Werkzeug-Ordner, Installer im Ordner wechseln
- [ ] **Neue Version:** `vlc-3.0.23-win64.exe` laden, Parameter ändern, dann `vlc-3.0.24-win64.exe` laden → neue Zeile
      übernimmt die Parameter (Hinweis beim Mauszeiger „Parameter von „vlc-3.0.23“ übernommen“), alte Zeile bleibt
- [ ] **Löschen** (Knopf oder Entf) mit Rückfrage → Eintrag und Ordner auf dem NAS weg; Automatisierung mit der
      gelöschten alten Version nimmt die neue; ein ganz gelöschtes Programm steht in der Auswahl als „fehlt in der
      Bibliothek“ und im Log des Auftrags „… fehlt in der Software-Bibliothek – übersprungen“
- [ ] Auswahl *Software installieren* (OS installieren, *Danach anpassen*, Automatisierung) zeigt nur die Bibliothek;
      Reiter *Dateien* hat keinen Knopf *Software …* mehr
- [ ] Gespeicherte Auswahl aus der Zeit vor Ä-041 (Automatisierung/Vorlage mit z. B. `vlc-3.0.24-win64.exe`) →
      nach dem Laden von VLC in die Bibliothek wird sie zu `vlc-3.0.24` aufgelöst
- [ ] Ein Auftrag mit Software (z. B. Zurückspielen mit *Danach anpassen*) → am Gerät
      `C:\ProgramData\Okula\Software\vlc-3.0.24\…`, Installation wie in Abschnitt 23
- [ ] **Demo:** Demo-Gerät an, *Extras → Software-Bibliothek …* → Text oben nennt „Ablage: Demo (lokal, nicht auf dem NAS)“, drei
      Beispiel-Einträge; laden/löschen dort ändert das NAS nicht

**Installer-Typen erkennen (Ä-043)** – nach `git pull && sudo ./install.sh` das Tool neu starten (**kein** neuer
Agent-Stick nötig).
- [ ] **Araneo, schon geladen:** Eintrag `AraneoInstaller` markieren → *Neu erkennen* (ohne Rückfrage, wenn nicht von Hand
      geändert) → Zeile „Araneo · 1.10.2 · Luminex Network Intelligence · Qt Installer Framework · `install --root
      "C:\Program Files\Araneo" --accept-licenses --accept-messages --default-answer --confirm-command` · 0 · bereit“
- [ ] **Araneo an der VM:** Windows-VM zurückspielen mit *Danach anpassen* und Software „Araneo“ → nach dem ersten Start
      `C:\Program Files\Araneo` vorhanden, Araneo im Startmenü; `C:\Windows\Temp\okula-software.log`: „ok Araneo 1.10.2:
      Rückgabewert 0“, kein Fenster blieb offen
- [ ] **Weiterer neuer Typ an der VM:** z. B. `Event Master Toolset Rev 10.2.0.4128 Installer.exe` (InstallBuilder,
      `--mode unattended --unattendedmodeui none`) oder `Kards-1.3.1-windows-x64.exe` (electron-builder, `/S /allusers` –
      danach für einen normalen Benutzer im Startmenü sichtbar) → im Protokoll „ok …“
- [ ] **Neu erkennen mit Änderung von Hand:** Parameter eines Eintrags ändern, dann *Neu erkennen* → Rückfrage
      „… neu erkennen?“; *Abbrechen* lässt die Parameter, *Überschreiben* setzt die erkannten
- [ ] Rechtsklick auf eine Zeile → Menü *Bearbeiten …*, *Neu erkennen*, *Löschen*
- [ ] **Hersteller:** Spalte *Hersteller* gefüllt (z. B. MSI `RODECaster App (2.0.111).msi` → „RØDE Microphones“), in der
      Zelle änderbar
- [ ] **Parameter fehlt mit Hinweis:** `epson665751eu.exe` laden → Typ „InstallShield (InstallScript)“, unter der Liste
      „Was tun: InstallScript braucht eine Antwortdatei …“; `Firefox Installer.exe` → „7-Zip-SFX (selbstentpackend)“
      mit Hinweis; unbekannter Installer (z. B. `OKULA-Monitor-Setup.exe`) → „unbekannt“ mit Hinweis Herstellerdoku/VM
- [ ] **MSIX/MSU:** eine `.msix` bzw. `.msixbundle` (z. B. aus dem Microsoft Store für Unternehmen) und ein `.msu`
      (Windows-Update aus dem Microsoft-Update-Katalog) laden → „bereit“; an der VM installiert (App für einen neuen
      Benutzer vorhanden bzw. Update unter *Installierte Updates*), Protokoll „ok …“ (MSU schon installiert →
      Rückgabewert 2359302 gilt als ok)

### 26. Win11 clean (Ä-042)
Nach `git pull && sudo ./install.sh` das Tool neu starten (**kein** neuer Agent-Stick nötig). VM mit **Windows 11 Pro**
(am besten 24H2 mit aktuellen Updates, Netzwerk an), ein lokales Konto angemeldet gewesen.
- [ ] Vor dem Senden in Windows (PowerShell als Administrator) `Get-AppxPackage -AllUsers | Select Name | Sort Name`
      festhalten; Startmenü fotografieren (Platzhalter WhatsApp, LinkedIn, Clipchamp …)
- [ ] *Windows anpassen …* → Vorlage **„Clean“** → Häkchen wie in der Hilfe (Kamera und Microsoft Store aus, Startmenü
      und Nachlauf an), *Senden* ohne Benutzername/Passwort möglich; Mauszeiger auf „Wiederinstallation … sperren“ →
      Hinweis Enterprise/Education
- [ ] Neustart, anmelden → **Startmenü** zeigt nur Edge, Explorer, Einstellungen und die vorhandenen Rechner, Editor,
      Fotos, Paint, Snipping Tool, Terminal – keine Werbe-Kacheln (WhatsApp, LinkedIn, Adobe Express, Clipchamp …)
- [ ] `C:\Windows\Temp\okula-windows-anpassen.log`: „ok Startmenü: Werbe-Kacheln entfernen (Windows 11) (Richtlinie
      ConfigureStartPins gesetzt (Policy CSP) …)“ – steht dort „Gruppenrichtlinie … gesetzt“ oder FEHLER, Text notieren;
      „Wiederinstallation …“ nennt die Edition („wirkt bei Professional nicht“); Ende „N ok, M mit Fehler“
- [ ] **Bing Search:** Zeile „Store-Apps entfernen: Bing (Wetter, News, Bing Search …)“ – steht dort
      `Microsoft.BingSearch … entfernt`, „nicht vorhanden“ oder ein FEHLER? (klärt, ob die App später nachgeladen wurde
      oder die Entfernung scheiterte)
- [ ] Aufgabenplanung: Aufgabe „Okula Windows anpassen Nachlauf“ vorhanden, `C:\ProgramData\Okula\okula-windows-anpassen-nachlauf.ps1` vorhanden
- [ ] **Nach 1 h** (angemeldet bleiben): Protokoll „Windows anpassen – Nachlauf nach der Anmeldung: Start … Nachlauf
      Ende“; Aufgabe und Datei weg; `Get-AppxPackage -AllUsers` ohne WhatsApp, LinkedIn, Outlook (neu), Teams,
      Clipchamp, Dev Home, Bing Search, Widgets …; Rechner, Editor, Paint, Fotos, Snipping Tool, Terminal, Edge, Store,
      Kamera unverändert
- [ ] **Neustart** und erneut anmelden → Startmenü unverändert sauber, keine neuen Werbe-Apps; selbst eine App anheften,
      abmelden, anmelden → bleibt angeheftet (nur ab 24H2 mit KB5062660; sonst setzt Windows die Liste neu – notieren)
- [ ] **Neuer Benutzer** anlegen und anmelden → gleiches Startmenü, keine Werbe-Apps
- [ ] Windows 10 VM, Vorlage „Clean“ → Protokoll „Startmenü …: Windows 10 – ohne Wirkung“, sonst wie Abschnitt 19

**Windows-Programme (Ergänzung 18.11.)**
- [ ] Dialog: Gruppe *Windows-Programme* zwischen *Apps* und *Updates*, alle Häkchen aus; Vorlagen „Player“, „Laptop“,
      „Clean“ setzen dort **kein** Häkchen; Mauszeiger auf *Medien-Erweiterungen* → Warnung, auf *Internet Explorer 11*
      → Hinweis IE-Modus
- [ ] Nach „Clean“ (oben): Rechner, Editor, Paint, Fotos, Snipping Tool, Terminal, Medienwiedergabe und die
      Medien-Erweiterungen (`Get-AppxPackage -AllUsers *Extension*`) sind noch da
- [ ] Win11-VM nur *Rechner*, *Paint*, *Medienwiedergabe*, *WordPad*, *Schrittaufzeichnung*, *Windows Media Player
      (klassisch)*, *Math-Eingabe* anhaken → senden → Neustart: Protokoll „ok Windows-Programm entfernen: Rechner
      (Microsoft.WindowsCalculator entfernt)“, Paint („… entfernt“, Windows-Funktion MSPaint „nicht vorhanden“),
      WordPad „Windows-Funktion nicht vorhanden“ (24H2) bzw. „entfernt“; `Get-WindowsCapability -Online | ? State -eq
      Installed` ohne StepsRecorder, WindowsMediaPlayer, MathRecognizer; Edge, Einstellungen, Suche und
      Windows-Sicherheit funktionieren; nach einem weiteren Neustart nichts zurück
- [ ] Win10-VM *Editor*, *Paint*, *Internet Explorer 11* → klassischer Editor bzw. Paint entfernt (Windows-Funktion),
      IE11 weg (`Get-WindowsCapability -Online -Name Browser.InternetExplorer*` → NotPresent)

**Korrektur B-017 (19.11.) – VM-Win11-test, Windows 11 Pro 24H2 (Build 26100.x)**
Nach `git pull && sudo ./install.sh` das Tool neu starten (**kein** neuer Agent-Stick). Die VM kann die schon einmal
angepasste sein (der falsche Wert von Ä-042 wird ersetzt).
- [ ] Vorlage **„Clean“** (Widgets und Startmenü an) → senden → Neustart, anmelden → **Startmenü** zeigt nur die festen
      Kacheln (Edge, Explorer, Einstellungen und die vorhandenen Rechner, Editor, Fotos, Paint, Snipping Tool, Terminal) –
      kein WhatsApp, Adobe Express, LinkedIn
- [ ] Registrierung `HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer`: `ConfigureStartPins` = 1 (REG_DWORD),
      `ConfigureStartPinsJSON` = `C:\ProgramData\Okula\StartPins.json` (REG_EXPAND_SZ); Datei vorhanden, lesbares JSON,
      bleibt auch nach dem Nachlauf (nach 1 h) erhalten
- [ ] Protokoll „ok Startmenü: Werbe-Kacheln entfernen (Windows 11) (Gruppenrichtlinie ConfigureStartPins gesetzt
      (Datei C:\ProgramData\Okula\StartPins.json) …)“
- [ ] **Keine Wetteranzeige** („11°C …“) und kein Widgets-Knopf in der Taskleiste; `HKLM\SOFTWARE\Policies\Microsoft\Dsh`
      `AllowNewsAndInterests` = 0; Protokoll „ok Store-Apps entfernen: Widgets (Richtlinie „Widgets zulassen“ aus; …)“
- [ ] Protokoll **ohne falsche FEHLER**: keine Zeile „(vorinstalliert): Das System kann die angegebene Datei … nicht
      finden“; jede App-Zeile nennt die entfernten Pakete („… entfernt“) bzw. „nicht vorhanden“; gibt es doch einen
      FEHLER, steht davor „…, … entfernt; Fehler: …“ – Text notieren
- [ ] Erste Zeile „Startskript und Gruppenrichtlinie aufräumen“ ist **ok** (ggf. mit Hinweis „leerer Ordner
      Machine\Scripts\Startup bleibt …“), kein FEHLER „wird gerade verwendet“; `C:\Windows\System32\GroupPolicy\Machine\Scripts\scripts.ini`
      weg bzw. ohne `okula-windows-anpassen`
- [ ] Selbst eine App anheften, abmelden, anmelden → bleibt angeheftet (`applyOnce`)
- [ ] Zum Vergleich (Rückmeldung an Okuli): Ist der Bereich **„Empfohlen“** („Erste Schritte“ u. a.) noch da?

**Korrektur B-018 (24.11.) – VM-Win11-clean, Windows 11 Pro 25H2, bestehendes Konto (z. B. „Okula-test“)**
Nach `git pull && sudo ./install.sh` das Tool neu starten (**kein** neuer Agent-Stick). Das Konto hat vorher ein
eigenes Startmenü (mehrfach angemeldet), die Registry hat ggf. noch Reste früherer Läufe.
- [ ] Vorher (Gastagent oder Regedit): unter `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\Scripts\Startup`
      und `…\Group Policy\State\Machine\Scripts\Startup` Einträge mit `Script = okula-software.cmd` notieren
- [ ] *Startmenü: Werbe-Kacheln entfernen (Windows 11)* senden → Neustart → mit dem **bestehenden** Konto anmelden →
      Startmenü zeigt die festen Kacheln (Edge, Explorer, Einstellungen, Rechner, Editor, Fotos, Paint, Snipping Tool,
      Terminal)
- [ ] Im Profil `C:\Users\<Konto>\AppData\Local\Packages\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\LocalState`
      liegt `start2.bin.okula-<Datum-Zeit>` (Sicherung) und eine neue `start2.bin`
- [ ] Protokoll „ok Startmenü: Werbe-Kacheln entfernen (Windows 11) (… gilt für neue Konten und – einmalig
      zurückgesetzt – für bestehende: Startmenü von N Profil(en) zurückgesetzt …)“ – N = Anzahl Konten mit Startmenü;
      kein FEHLER
- [ ] Protokoll „ok Startskript und Gruppenrichtlinie aufräumen“ **ohne** InvalidCastException, mit Hinweis
      „… Eintrag/Einträge von Okula-Startskripten in der Registrierung entfernt“; danach unter beiden Schlüsseln oben
      **keine** Einträge mit `okula-*` mehr (auch nicht `okula-software.cmd` von früher); übrige Einträge (falls
      vorhanden) lückenlos 0, 1, …
- [ ] Selbst eine App anheften, abmelden, nach dem Nachlauf (1 h) bzw. Neustart wieder anmelden → bleibt angeheftet
      (Nachlauf setzt nichts zurück)
- [ ] Danach *Software installieren …* (z. B. Gasttools) → Neustart → Protokoll `okula-software.log` Zeile „ok
      Startskript und Gruppenrichtlinie aufgeräumt“, Registry wieder ohne `okula-*`-Einträge

**Korrektur B-019 (24.11.) – VM-Win11-clean ab Snapshot „frisch“, Windows 11 Pro 25H2, Konto ohne Passwort**
*Abgelöst durch B-020 (Gesamttest 24.11.: SyncForegroundPolicy wirkt nicht, Windows meldet trotzdem vor dem Skript
an) – nicht mehr prüfen, stattdessen „Korrektur B-020“ unten.*
Nach `git pull && sudo ./install.sh` das Tool neu starten und **den Agent-Stick bzw. Netzwerkstart neu erstellen**
(Agent-Code geändert). Wie am 24.11.: *Windows anpassen* (alle Optionen bzw. Vorlage wie im Gesamttest) und
*Software installieren* (virtio-Gasttools) zusammen senden, dann **nur einmal** neu starten.
- [ ] Vorher (Regedit oder Gastagent): `HKLM\SOFTWARE\Policies\Microsoft\Windows NT\CurrentVersion\Winlogon` –
      `SyncForegroundPolicy` vorhanden? Wert notieren: ______ (Snapshot „frisch“: vermutlich nicht vorhanden)
- [ ] Log beider Aufträge im Tool: „Die Anmeldung wartet beim nächsten Start, bis das Startskript fertig ist …“, kein
      „Hinweis: Die Anmeldung wartet nicht …“; im Agent-Bildschirm/-Log „SyncForegroundPolicy gesetzt“
- [ ] Beim Start „Bitte warten“, bis die Skripte fertig sind; erst dann erscheint die Anmeldung. Dauer notieren: ______
- [ ] Ereignisanzeige (System, Quelle GroupPolicy bzw. Sicherheit): Ereignis **5016** (Scripts-Erweiterung) bzw. Ende
      der Okula-Protokolle **vor** der interaktiven Anmeldung **4624** (Typ 2); `okula-windows-anpassen.log` und
      `okula-software.log` beginnen vor der Anmeldung
- [ ] Ohne weiteren Neustart: Startmenü zeigt die festen Kacheln (kein WhatsApp, Adobe Express, LinkedIn …), **kein
      Wetter** in der Taskleiste, **kein Sperrbildschirm**
- [ ] Protokoll Startmenü-Zeile ohne „beim Lauf angemeldet“; geplante Aufgabe „Okula Windows anpassen Nachlauf“ mit
      Auslöser *Bei Anmeldung* (30 min Verzögerung) – Protokollzeile „30 min nach der ersten Anmeldung“ (ohne „einmalig
      um …“, weil niemand angemeldet war)
- [ ] Nach 30 min: Nachlauf gelaufen (Protokoll „Nachlauf … Ende“), Aufgabe verschwunden
- [ ] Danach `SyncForegroundPolicy` wie vorher (nicht vorhanden bzw. alter Wert); Protokoll „Startskript und
      Gruppenrichtlinie aufräumen (… SyncForegroundPolicy entfernt wie vorher …)“; `C:\Windows\System32\GroupPolicy`
      ohne `SyncForegroundPolicy.okula-nachher`; nächster Neustart ohne „Bitte warten“
- [ ] Gegenprobe Fehlerfall: VM hart ausschalten (nicht herunterfahren), mit Agent starten, *Windows anpassen* senden →
      Log „Hinweis: Die Anmeldung wartet nicht auf das Startskript (… nicht sauber geschlossen …)“, Windows startet
      normal; oder Meldung „Ruhezustand bzw. Schnellstart“ (dann ist dieser Teil nicht prüfbar)
- [ ] Optional angemeldet (nur wenn die Anmeldung doch vorher erscheint): Protokoll nennt „<Konto> beim Lauf angemeldet
      – Startmenü dort nicht zurückgesetzt …“ und beim Nachlauf „einmalig um HH:MM“; nach Abmelden und Nachlauf
      „Startmenü von 1 Profil(en) einmalig zurückgesetzt“

**Korrektur B-020 (24.11.) – VM-Win11-clean ab Snapshot „frisch“, Windows 11 Pro 25H2, Konto ohne Passwort**
Nach `git pull && sudo ./install.sh` das Tool neu starten und **den Agent-Stick bzw. Netzwerkstart neu erstellen**
(Agent-Code geändert). Wie im Gesamttest: *Windows anpassen* (Vorlage „Clean“ bzw. alle Optionen mit Startmenü und
Widgets) und *Software installieren* (virtio-Gasttools) zusammen senden, dann **nur einmal** neu starten und sich
anmelden, sobald die Anmeldung erscheint (auch wenn das Skript noch läuft).
- [ ] Log des Auftrags *Windows anpassen*: „Vor dem Windows-Start gesetzt: Startmenü-Richtlinie (feste Kacheln),
      Startmenü von N Profil(en) zurückgesetzt …“ und „Vor dem Windows-Start gesetzt: Richtlinie „Widgets zulassen“
      aus …“, kein „Hinweis: …“; Agent-Log „… vor dem Windows-Start: Startmenü-Richtlinie gesetzt, …“
- [ ] Vor dem Neustart (optional, z. B. mit dem Agent bzw. danach im Profil): `start2.bin.okula-<Datum-Zeit>` in jedem
      Profil mit Startmenü, `C:\ProgramData\Okula\StartPins.json` und `start-offline.ok` vorhanden
- [ ] **Erste Anmeldung**, auch wenn sie vor dem Ende des Skripts kommt (Uhrzeit Anmeldung ____ / Start der
      Okula-Protokolle ____): Startmenü zeigt **nur die festen Kacheln** (kein WhatsApp, Adobe Express, LinkedIn …),
      **kein Wetter** in der Taskleiste – ohne weiteren Neustart
- [ ] Registrierung: `HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer` `ConfigureStartPins` = 1,
      `ConfigureStartPinsJSON` gesetzt; `HKLM\SOFTWARE\Policies\Microsoft\Dsh` `AllowNewsAndInterests` = 0;
      **kein** `SyncForegroundPolicy` unter `…\Policies\Microsoft\Windows NT\CurrentVersion\Winlogon` (Snapshot
      „frisch“) bzw. Wert wie vorher
- [ ] `okula-windows-anpassen.log`: Startmenü-Zeile „ok … Startmenü schon beim Senden vor dem Windows-Start
      zurückgesetzt (Agent: …)“, **ohne** „beim Lauf angemeldet“; `start-offline.ok` danach weg, `StartPins.json` bleibt;
      Nachlauf-Aufgabe ohne `-StartSids`
- [ ] **Beide Protokolle ohne FEHLER** (`okula-windows-anpassen.log` und `okula-software.log`): Zeile „Startskript und
      Gruppenrichtlinie aufräumen/aufgeräumt“ ok – bei einem der beiden ggf. mit Hinweis „Gruppenrichtlinie war schon
      zurückgelegt (anderes Okula-Startskript)“; kein „… `Startup\0\0` nicht vorhanden“, kein „SyncForegroundPolicy nicht
      zurückgesetzt“
- [ ] Danach: `C:\Windows\System32\GroupPolicy` ohne `*.okula-nachher`, `scripts.ini` weg bzw. wie vorher, Registry
      unter `Group Policy\Scripts\Startup` und `State\Machine\Scripts\Startup` ohne `okula-*`-Einträge
- [ ] Nach 30 min: Nachlauf gelaufen (Protokoll „Nachlauf … Ende“), Aufgabe verschwunden; Startmenü bleibt
- [ ] Gegenprobe Fehlerfall: VM hart ausschalten (nicht herunterfahren), mit Agent starten, *Windows anpassen* senden →
      Log „Hinweis: Einstellungen vor dem Windows-Start nicht gesetzt (… nicht sauber geschlossen …)“ (Text seit
      B-021), Windows
      startet normal, das Startskript setzt es (Protokoll wie B-018/B-019); oder Meldung „Ruhezustand bzw.
      Schnellstart“ (dann ist dieser Teil nicht prüfbar)
- [ ] Optional VM mit Windows 11 vor 24H2 (Build < 26100): Log „Startmenü: Windows-Build … vor 24H2 – setzt nur das
      Startskript“, Widgets trotzdem offline

**Korrektur B-021 (24.11.) – VM-Win11-clean ab Snapshot „frisch“, Windows 11 Pro (Build 26200)**
Nach `git pull && sudo ./install.sh` das Tool neu starten und **den Agent-Stick bzw. Netzwerkstart neu erstellen**
(Agent-Code geändert: Offline-Werte, Uhr). *Windows anpassen* mit Vorlage „Clean“ **plus** *Sperrbildschirm aus*
senden (Clean enthält *Wiederinstallation von Werbe-Apps sperren* und das Startmenü), dann **nur einmal** neu starten.
- [ ] Log des Auftrags: „Vor dem Windows-Start gesetzt: Richtlinie „Sperrbildschirm nicht anzeigen“ – kein
      Sperrbildschirm ab dem ersten Start“ und „… „Microsoft-Benutzererfahrungen deaktivieren“ – wirkt bei Windows
      Professional nicht (nur Enterprise/Education). Werbe-Platzhalter …“; Agent-Log „… Sperrbildschirm-Richtlinie
      gesetzt, Richtlinie Microsoft-Benutzererfahrungen gesetzt“
- [ ] **Erster Start: kein Sperrbildschirm** – Windows zeigt gleich die Anmeldung (bzw. meldet automatisch an)
- [ ] Registrierung: `HKLM\SOFTWARE\Policies\Microsoft\Windows\Personalization` `NoLockScreen` = 1,
      `…\Windows\CloudContent` `DisableWindowsConsumerFeatures` = 1
- [ ] **Startmenü:** stehen WhatsApp, Adobe Express, LinkedIn wieder dabei, ist das bei Pro erwartet (laut Microsoft
      nur bei Enterprise/Education abschaltbar) – dann Protokoll-Zeile Startmenü mit „Hinweis: Windows Professional –
      Microsoft kann zusätzlich Werbe-Platzhalter anheften …“ und Zeile *Wiederinstallation …* mit „… bleiben evtl.,
      von Hand lösen“. Die drei Kacheln mit Rechtsklick → „Von Start lösen“ entfernen, abmelden, anmelden, nach dem
      Nachlauf (30 min) und nach einem Neustart: **bleiben weg** ____ (wenn nicht: als Bug melden)
- [ ] Optional mit Windows 11 Enterprise oder Education (Probe-VM): Startmenü **ohne** WhatsApp, Adobe Express,
      LinkedIn bei der ersten Anmeldung; Log „… – keine Werbe-Apps und Werbe-Platzhalter ab der ersten Anmeldung“
- [ ] **Zeitstempel in Ortszeit:** Uhrzeit beim Senden ____; Name `start2.bin.okula-<JJJJMMTT-hhmmss>` im Profil und
      `stamp=` in `start-offline.ok` (vor dem Start mit dem Agent bzw. danach im Profil) zeigen dieselbe Ortszeit
      (nicht 1 h vor); Agent-Journal „Uhr nach dem Server gestellt (ging 3600 s vor; Hardware-Uhr unverändert)“
- [ ] Danach in Windows: Uhrzeit stimmt weiterhin (Hardware-Uhr nicht verändert), ohne Internet-Zeitabgleich prüfen
      (z. B. Netzwerk der VM kurz trennen)

### 27. Test-VMs mit Gastagent (I-041)
Nach `git pull && sudo ./install.sh` das Tool neu starten (**kein** neuer Agent-Stick). Eine Test-VM mit Windows 11
(z. B. VM-Win11-test), am besten vorher Snapshot „vor Gastagent“. Gasttools aus Fedora virtio-win, stabile Version
(`virtio-win.iso`: `virtio-win-guest-tools.exe` bzw. `virtio-win-gt-x64.msi` + `guest-agent/qemu-ga-x86_64.msi`).
- [ ] *Extras → Neue virtuelle Maschine …*: Häkchen *Gastagent (nur Test-VMs)* ist **aus**, Mauszeiger darauf → Tooltip
      mit dem Grund (Standard-Hardware, Image auf echten Geräten)
- [ ] **Option einschalten:** VM ausgeschaltet → *Hardware ändern …* → Häkchen *Gastagent (nur Test-VMs)* → Hinweis
      „Gastagent nur für Test-VMs …“ → *Übernehmen*; Verlauf „Hardware geändert: Gastagent aus → an“;
      `virsh -c qemu:///system dumpxml <VM>` zeigt `<controller type='virtio-serial' …>` und `<channel type='unix'>` mit
      `<target type='virtio' name='org.qemu.guest_agent.0' …/>` (Pfad von libvirt), sonst unverändert (Disk-Datei,
      Snapshots, MAC, UUID)
- [ ] Geräteliste: Zustand „aus · Gastagent“; Gerätefenster: Zeile *Virtuelle Maschine* mit „Gastagent: VM nicht
      eingeschaltet“, Übersicht „… · Gastagent (nur Test-VMs)“
- [ ] **Start mit Overlay-Kette** (VM mit Snapshots): *Einschalten* bzw. *Einschalten und Agent starten* geht wie bisher
      (kein AppArmor-Fehler); bei Windows: Gerätefenster „Gastagent: keine Antwort“ (Gasttools fehlen noch)
- [ ] **Gasttools installieren:** `virtio-win-guest-tools.exe` in *Extras → Software-Bibliothek …* laden → Typ
      „virtio-win-Gasttools (Burn)“, Parameter `/install /quiet /norestart`, Rückgabewerte 0, 1638, 1641, 3010, Status
      „bereit“ (alternativ die beiden MSI → „MSI (Windows Installer)“, `/qn /norestart`); an der VM über *OS installieren …*
      bzw. *Image zurückspielen …* → *Danach anpassen* wählen (oder von Hand in der VM) → `C:\Windows\Temp\okula-software.log`
      „ok …“; Dienst „QEMU Guest Agent“ läuft (`Get-Service QEMU-GA`)
- [ ] **guest-ping antwortet:** am Server `virsh -c qemu:///system qemu-agent-command <VM> '{"execute":"guest-ping"}'` →
      `{"return":{}}`; Gerätefenster „Gastagent: antwortet“ (spätestens nach 30 s)
- [ ] **Befehl ausführen:** `virsh … qemu-agent-command <VM> '{"execute":"guest-exec","arguments":{"path":"powershell.exe",
      "arg":["-NoProfile","-Command","Get-ComputerInfo | Select OsName"],"capture-output":true}}'` → `pid`; danach
      `guest-exec-status` mit dieser `pid` → `out-data` (Base64) mit dem Windows-Namen
- [ ] **Warnung beim Master:** Agent starten → *Disk-Image erstellen …* → Rückfrage „VM mit Gastagent – virtio-Treiber
      und qemu-ga sind im Image. Für Master-Images ohne Gastagent arbeiten.“; *Abbrechen* öffnet nichts, *Trotzdem
      fortfahren* öffnet den Dialog. Dasselbe bei *Als Master-Image markieren* eines Images dieser VM und bei
      *OS installieren …* mit *Für Master-Image (Audit-Modus)* (*Abbrechen* → Dialog bleibt offen, „Nicht gestartet: …“)
- [ ] Snapshot erstellen, zurück, löschen mit Gastagent wie bisher; automatischer Snapshot bei laufendem Agent geht
- [ ] **Option aus → Kanal weg:** VM aus → *Hardware ändern …* → Häkchen weg → `dumpxml` ohne `channel` und ohne
      `virtio-serial`; Liste ohne „Gastagent“; Windows startet weiter (Treiber bleiben bis zur Deinstallation)
- [ ] **Entfernen in Windows:** *Einstellungen → Apps* „Virtio-win-guest-tools“ deinstallieren (bzw. zurück zum Snapshot
      „vor Gastagent“) → Dienst „QEMU Guest Agent“ weg

### 28. Software installieren an einem Gerät mit Windows (Ä-044)
Nach `git pull && sudo ./install.sh` das Tool neu starten (**kein** neuer Agent-Stick). VM-Win11-clean (Windows läuft
schon, Option *Gastagent* an – Abschnitt 27), am besten vorher Snapshot „vor Software“. In der Software-Bibliothek
`virtio-win-guest-tools.exe` mit Status „bereit“ (Abschnitt 27).
- [ ] Windows ganz herunterfahren (Shift + „Herunterfahren“), *Einschalten und Agent starten*
- [ ] Rechtsklick auf die VM: **„Software installieren …“** direkt unter „Windows anpassen …“; ebenso *Tools →
      Software installieren …* und Knopf im Gerätefenster. Ohne Agent ausgegraut bzw. Meldung „… nicht verbunden“
- [ ] Dialog: nur „bereit“/„nur kopieren“ ankreuzbar, „Parameter fehlt“/„nur von Hand“ ausgegraut, Grund im Tooltip;
      *Senden* erst mit Auswahl; unten „werden beim nächsten Windows-Start still installiert“
- [ ] Gasttools wählen → *Senden*: Auftrag „Software installieren (…)“ im Reiter *Aufträge* mit Fortschritt; Log nennt
      Programm, Ablage auf der Windows-Partition, „Wird beim nächsten Windows-Start … installiert“
- [ ] Verlauf: „Software installieren (virtio-win … ) – wird beim nächsten Start installiert“
- [ ] VM neu starten (Agent-Stick bzw. Netzwerkstart weg) → Windows startet, `C:\Windows\Temp\okula-software.log`
      mit „ok …“ und „Ende: 1 ok, 0 mit Fehler“; `C:\Windows\System32\GroupPolicy\Machine\Scripts\scripts.ini` weg bzw.
      ohne `okula-software`
- [ ] Am Server: `virsh -c qemu:///system qemu-agent-command VM-Win11-clean '{"execute":"guest-ping"}'` →
      `{"return":{}}`; Gerätefenster „Gastagent: antwortet“
- [ ] **Zusammen mit Windows anpassen:** wieder Agent starten → erst *Windows anpassen …* (z. B. Vorlage „Clean“)
      senden, dann *Software installieren …* (anderes Programm, z. B. VLC) senden – Log „Ein weiteres
      Okula-Startskript (Windows anpassen) steht noch aus …“. Neustart: beide Protokolle (`okula-windows-anpassen.log`,
      `okula-software.log`) ok, danach `scripts.ini`/`gpt.ini` wie vorher (bzw. weg, wenn es vorher keine gab), keine
      Okula-Einträge mehr in `gpedit.msc` → *Computerkonfiguration → Windows-Einstellungen → Skripts → Starten*
- [ ] Umgekehrte Reihenfolge (erst Software, dann Windows anpassen) einmal wiederholen – Ergebnis gleich
- [ ] Gerät mit BitLocker bzw. ohne Windows: Meldung „kein Windows erkannt (oder … BitLocker) – nichts gesendet“
- [ ] Demo-Gerät: *Software installieren …* mit den Beispielen aus dem Demo-Speicher → Auftrag „fertig“, Verlauf
