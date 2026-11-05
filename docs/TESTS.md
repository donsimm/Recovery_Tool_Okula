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
- [ ] I-032: **Agent-Stick neu erstellen**; beide HP EliteBook 850 G1 mit dem Agent starten (das nicht startende ggf. wieder im Hybrid-/Legacy-Modus) → Reiter BIOS: Schnittstelle „HP (hp-bioscfg)“ mit Einstellungen oder „nur Grundangaben“ (notieren!); beim zweiten „Vergleichen mit“ das erste → Unterschiede (z. B. PXE Internal IPV4 NIC boot)
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
