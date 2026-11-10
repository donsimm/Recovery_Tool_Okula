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
- [x] Neue VM mit Profil VM-Win11 → 256 GB, Modell „Okula NVMe SSD 256GB“; bestehende VMs unverändert – ✔ 10.11. (Okuli: Dialog zeigt NVMe-SSD 256 GB)
