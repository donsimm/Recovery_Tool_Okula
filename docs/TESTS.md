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
| **Automatisierung:** Countdown + Esc, Warteschlange (N), 5 Schritte, falsche Disk = nichts gelöscht, Fehler, 24 h | A, V | ganzer Durchlauf über den echten Agent auf Loop-Disks |
| Computername = Gerätename (OS installieren, Anpassen) | A, V | |
| Grüne/rote Fortschrittsbalken | A, V | |
| Demo-Gerät: alle Aufträge, Fehler, Neustart, nur 127.0.0.1, Demo-Image gesperrt | A, V | echter Prozess |
| Inventar-Export: CSV (BOM, Semikolon), PDF je Kunde (A4 quer, mehrseitig), Auswahl, Key maskiert/aus | A, V | |
| Garantie-Abfrage: Dell/HP/Lenovo-Antworten, Farben grün/gelb/rot, Schlüssel 0600 nur beim Root-Helfer | A, V | gemockte Antworten – Hersteller-Server waren gesperrt |

## Offen – am realen System testen

### 1. Fixes von heute
- [ ] **Debian-Direktinstallation** mit der echten Debian-13.7.0-Netinst-ISO (bei Fehler: neue, genauere Meldung schicken)
- [ ] **Doppelter HP-Eintrag** nach dem Update: verschwindet beim Start, sonst Rechtsklick → „Zusammenführen mit …“

### 2. Netzwerk (Reiter „Netzwerk“ im Gerätefenster)
- [ ] Wake-on-LAN: Gerät ausgeschaltet, „Einschalten“ → startet Windows
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
- [ ] Danach: Häkchen aus, Liste „wieder aktiv in 24 h“; Verlauf mit allen Schritten
- [ ] Mit **Netzwerkstart** statt Stick (Gerät freigeschaltet, F12 → Netzwerk)
- [ ] **Zwei Geräte gleichzeitig** bei N = 1 → zweites „wartet (Platz 1)“, startet danach
- [ ] **Andere Disk** im Gerät (oder Zieldisk absichtlich falsch) → Fehler rot, Meldung am Gerät, nichts gelöscht
- [ ] **Backup vorher** an → Backup erscheint im Reiter Backups mit Notiz „Automatisierung – vor dem Zurückspielen“
- [ ] **Backup vorher – ganze Disk** → Disk-Image der alten Disk im Reiter Images, erst danach wird zurückgespielt
- [ ] Hauptschalter: Stopp-Knopf ■ über der Geräteliste (wird rot) → Gerät startet keinen Countdown
- [ ] Vorlage speichern („Schulungs-PC“), bei zweitem Gerät anwenden, Zieldisk dort wählen
- [ ] Nach 24 h: Häkchen wieder an (oder Option aus → bleibt aus)

### 6. Demo-Gerät (Vorführung)
- [ ] Extras → Demo-Gerät: DEMO-PC erscheint grün, Inventar sichtbar
- [ ] Disk-Image vom DEMO-PC (≈ 45 s, grüner Balken), danach Zurückspielen auf den DEMO-PC
- [ ] Demo-Image auf ein echtes Gerät zurückspielen → wird verweigert
- [ ] „Demo: nächster Auftrag mit Fehler“ → roter Balken bei ~40 %
- [ ] Automatisierung auf dem DEMO-PC (Countdown, Schritte 1–5, „wieder aktiv in 24 h“)
- [ ] Tool schliessen → Demo-Prozess ist beendet

### 7. Allgemein
- [ ] I-013: `sudo ./install.sh` (installiert python3-reportlab); Menü → Inventar exportieren → alle Geräte, CSV + PDF → CSV in Excel öffnen: Umlaute richtig, Spalten getrennt; je Kunde ein PDF mit Kopf (Kunde, Datum), Tabelle lesbar, Seitenzahl
- [ ] I-013: Rechtsklick auf einen Kunden-Ordner → nur dessen Geräte (inkl. Unterordner); „Markierte Geräte“ mit 2 Häkchen → nur diese
- [ ] I-013: „Windows-Key nicht exportieren“ an → kein Key in CSV/PDF; aus → nur `XXXXX-…-ABCDE`; letztes Image/Backup stimmt mit Gerätefenster überein (NAS verbunden)
- [ ] I-025: `sudo ./install.sh` erneut (neuer Root-Helfer `okula-warranty`, sudo-Regel); `ls -l /etc/okula-recovery/warranty.cred` nach dem Speichern eines Schlüssels → `-rw------- root root`; Schlüssel stehen **nicht** in `~/.config/okula-recovery/config.json` und nicht in einem Export (`grep` im Export)
- [ ] I-025 Lenovo (ohne Schlüssel): Gerätefenster → Übersicht → „Beim Hersteller abfragen“ → Datum stimmt mit pcsupport.lenovo.com überein; neues Lenovo-Gerät wird nach dem Erfassen einmal automatisch abgefragt
- [ ] I-025 Dell (sobald TechDirect-Schlüssel da): Menü → Einstellungen → Garantie-Abfrage → Client-ID/Secret speichern → „✔ gespeichert“; Abfrage → Datum wie auf dell.com/support
- [ ] I-025 HP (sobald HP-Schlüssel da): wie Dell; Datum wie auf support.hp.com
- [ ] I-025: Farben – Datum > 90 Tage grün, ≤ 90 Tage gelb, abgelaufen rot (von Hand testen: „Von Hand …“ mit Datum in 30 Tagen bzw. gestern); ohne Internet → Meldung „keine Verbindung“, altes Datum bleibt
- [ ] Ä-002: Image einer grösseren Disk (z. B. 512 GB, Windows mit Recovery) auf eine kleinere SSD (256 GB): Dialog zeigt „lässt sich anpassen“ mit Zahlen → Häkchen → neues Image `…_für_256GB` im Reiter Images, Original unverändert → Windows startet (evtl. kurze Laufwerksprüfung), C: hat die neue Grösse, Recovery am Ende vorhanden
- [ ] Ä-002: zu viele Daten für die kleine Disk → klare Meldung mit Zahlen, nichts gelöscht; Automatisierung mit kleinerer Disk (Option an) läuft durch
- [ ] I-024: Agent-Stick neu erstellen, Gerät starten, Inventar neu einlesen → Spalte „Win 11“ zeigt ✔/✖; Gerätefenster → Übersicht: „Windows 11“ mit Grund und „TPM / Start“ stimmen (mit BIOS-Angaben vergleichen: TPM/PTT, Secure Boot); je ein altes (z. B. 7. Gen. Intel) und ein neues Gerät
- [ ] Ä-011: Gerätefenster → Übersicht → „Starttasten“ stimmt für eure Geräte (HP, Dell, Lenovo …); Tabelle im Stick-Dialog sichtbar
- [ ] Ä-014: NAS-Fenster → „NAS-Webseite öffnen“ und Symbol in der NAS-Statuszeile → DSM öffnet sich im Browser (https 5001); auf http 5000 umstellen → richtige Adresse
- [ ] Gerätename mit Umlaut/Unterstrich (z. B. „Büro_PC_01“) bei OS installieren → Hinweis zeigt Name auf dem Gerät
- [ ] Export auf altem/neuem Server: Vorlagen und „höchstens gleichzeitig“ kommen mit
