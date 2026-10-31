# Änderungen, Bugs, Ideen und Entscheidungen

Zentrale Übersicht zum Okula Recovery Tool. Details zu jeder Funktion stehen im [README](../README.md),
der genaue Verlauf in `git log`, Prüfungen in [TESTS.md](TESTS.md).

**Ablauf:** Spontane Notizen kommen nach [EINGANG.md](EINGANG.md). Claude sortiert sie hier in die passende
Kategorie ein (mit ID), leert den Eingang und hält die Kurzübersicht aktuell.

**Von:** Dominik = eigene Idee/Meldung · Claude = Vorschlag aus Analyse · früher = aus früheren Sitzungen.

**IDs:** `B-` Bug · `Ä-` Änderung/Verbesserung · `I-` Idee · Status: **offen**, **in Arbeit**, **erledigt**
(→ ins Protokoll verschieben), **zurückgestellt**. Priorität: 🔴 hoch · 🟡 mittel · ⚪ tief.

## Kurzübersicht

| Kategorie | Offen | In Arbeit | Zurückgestellt |
|---|---|---|---|
| 🐞 Bugs | 0 | 0 | 0 |
| 🔧 Änderungen | 11 | 1 | 0 |
| 💡 Ideen | 26 | 3 | 2 |
| 🧪 Tests am realen System | siehe [TESTS.md](TESTS.md) | | |

In Arbeit (Reihenfolge): ~~Ä-014~~ ✔ → ~~Ä-011~~ ✔ → **I-024** Windows-11-Tauglichkeit → **Ä-002** kleinere Disk → **I-025** Garantie → **I-013** Inventar-Export (ein neuer Agent-Stick für I-024 und Ä-002).
Als Nächstes danach: Tests „Fixes von heute“ in [TESTS.md](TESTS.md) (Debian-Direktinstallation, doppelter HP-Eintrag).
Vorschlag Reihenfolge (Analyse 31.10.): **Ä-007, Ä-008** (Sicherheit für Laien, klein) → **Ä-001** (Dienst) → **I-005/I-006** (Aufbewahrung, zweite Kopie) → Ä-005 (CI) → **Ä-006, Ä-009, Ä-010** (Assistent) → I-008 (Meldungen) → Rest nach Bedarf.

## 🐞 Bugs

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| – | | | | keine offenen Bugs | |

## 🔧 Änderungen / Verbesserungen

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| Ä-001 | 🔴 | offen | Claude | **Aufträge als Systemdienst statt im Fenster:** Aufträge, Automatisierung und PXE laufen heute als Threads im GTK-Prozess (`jobs.py`). Wird das Tool geschlossen, stürzt es ab oder meldet man sich ab, brechen laufende Restores ab. Lösung: Dienst `okula-recoveryd` (systemd), die Oberfläche wird zum Client (lokaler Socket). Das ist die Grundlage für I-004 (Webinterface) und I-010 (Zeitplan). | 31.10. (Analyse) |
| Ä-002 | 🟡 | **in Arbeit** | Claude | **Restore auf eine kleinere Disk:** Heute bricht der Restore mit „Zieldisk zu klein“ ab. Wenn die belegten Daten passen: letzte Partition vorher mit `ntfsresize`/`resize2fs` verkleinern bzw. die Partitionstabelle anpassen. Typischer Fall: 512-GB- auf 256-GB-SSD | 31.10. (Analyse) |
| Ä-003 | 🟡 | offen | Claude | **Images und Backups auf dem NAS verschlüsseln:** Sie enthalten Personendaten (revDSG Art. 8, Datensicherheit). Minimum: SMB3-Verschlüsselung (`mount.cifs … seal`). Besser: Verschlüsselung im Datenstrom (z. B. `age` nach `zstd`), Schlüssel root-lesbar und zusätzlich auf Papier | 31.10. (Analyse) |
| Ä-004 | 🟡 | offen | Claude | **Zentrales Protokoll:** `/var/log/okula-recovery/` mit logrotate. Festhalten, wer wann was auf welches Gerät gespielt hat. Dazu Menü → „Diagnosepaket exportieren“ (Logs, Version, Konfiguration ohne Geheimnisse), um Fehler an Claude Code zu melden | 31.10. (Analyse) |
| Ä-005 | 🟡 | offen | Claude | **Entwicklung absichern:** GitHub Actions, die die 240 Tests bei jedem Push ausführen. Versionsnummer pflegen (steht noch auf `0.1.0`) und Releases taggen, damit der Server einen geprüften Stand zieht statt den Branch-Kopf. `ui.py` (2780 Zeilen) aufteilen | 31.10. (Analyse) |
| Ä-006 | 🔴 | offen | Claude | **Assistent „Neues Gerät einrichten“:** Sobald ein unbekanntes Gerät auftaucht, fragt ein Hinweis: „Neues Gerät gefunden: HP EliteBook 840 – jetzt einrichten?“. Danach Schritt für Schritt: Name → Ordner/Kunde → Vorlage oder Master-Image → „Sind noch Daten drauf?“ (Ja = Backup) → Zusammenfassung → Start. Heute muss man selbst wissen: Gerät suchen, Doppelklick, Reiter, 5 Abschnitte, Schalter | 31.10. (Laien-Test) |
| Ä-007 | 🔴 | offen | Claude | **Bestätigung vor dem Löschen:** Wird der Schalter eingeschaltet, während das Gerät verbunden ist, startet die Automatisierung ohne Rückfrage nach 30 s und löscht die Disk (`ui.save_automation` → `consider`). Nötig: rote Zusammenfassung „Disk Samsung 256 GB von HP-PC-07 wird gelöscht, Master ‚Win11 Büro‘, neuer Name …, Backup: nein“ mit Knopf „Löschen und neu aufsetzen“ | 31.10. (Laien-Test) |
| Ä-008 | 🔴 | offen | Claude | **Nach dem Restore Windows starten, auch wenn der Stick noch steckt:** BootNext auf den Windows Boot Manager setzen (`efibootmgr --bootnext`, wie in `wininstall.set_bootnext`). Heute heisst es nur „Agent-Stick abziehen“; wer das verpasst, landet wieder im Agent. Und nach 24 h wird das Gerät erneut neu aufgesetzt, weil „Nach 24 h wieder einschalten“ standardmässig an ist → Standard **aus**, oder nur bei Netzwerkstart | 31.10. (Laien-Test) |
| Ä-009 | 🟡 | offen | Claude | **Vorauswahl:** Ist nur eine interne Disk da, ist sie automatisch die Zieldisk; gibt es nur einen Master, ist er gewählt (heute sind beide Listen leer). Dazu eine Standard-Vorlage (Menü → Einstellungen), die bei jedem neuen Gerät schon eingetragen ist | 31.10. (Laien-Test) |
| Ä-010 | 🟡 | offen | Claude | **Vorabprüfung mit Ampel statt Fehler mitten im Lauf:** Image passt auf die Disk, UEFI/BIOS-Modus passt zum Master, BitLocker auf der Zieldisk (dann ist kein Datei-Backup möglich), Agent-Stick aktuell, Windows-Edition des Masters passt zum Key (Pro/Home). Anzeige: „✔ Bereit“ bzw. „⚠ Achtung: …“ | 31.10. (Laien-Test) |
| Ä-012 | 🟡 | offen | Claude | **Einfache Sprache im Reiter Automatisierung:** „Zieldisk“ → „Festplatte, die gelöscht wird“; Sysprep, Master und Content-Projekte mit einem „?“ pro Abschnitt erklären. Gerätenamen wie „DESKTOP-8F3K2LQ“ markieren und zum Umbenennen auffordern; optional Namensschema pro Vorlage (z. B. `KUNDE-001` fortlaufend) | 31.10. (Laien-Test) |
| Ä-013 | ⚪ | offen | Claude | **Klare Fertig-Meldung:** grosses „✔ Fertig – HP-PC-07 ist neu aufgesetzt (18 min)“ im Tool und am Gerät, dazu eine Liste: was gemacht wurde, Key aktiviert ja/nein, wo das Backup liegt. Als PDF ausdruckbar (Übergabeprotokoll, → I-013) | 31.10. (Laien-Test) |

## 💡 Ideen

| ID | Prio | Status | Von | Beschreibung |
|---|---|---|---|---|
| I-001 | ⚪ | offen | Dominik | **Virtuelle Maschine (VM) im Tool:** ISOs/Images in einer VM auf dem Server installieren, testen, ändern und wieder Images erstellen. Details und offene Fragen: [VM.md](VM.md) |
| I-002 | ⚪ | zurückgestellt | früher | Nobara/Zorin direkt installieren – nur möglich, falls deren Installer eine unbeaufsichtigte Installation erhält |
| I-003 | ⚪ | zurückgestellt | früher | Nicht generalisierte 1:1-Images anpassen (Name per Registry, Key per Skript) |
| I-004 | 🟡 | offen | Dominik | **Webinterface für den Fernzugriff:** Geräteübersicht und Gerätereiter im Browser (HTTPS, Anmeldung, über VPN); pro Gerät „Im Webinterface sichtbar“ (Reiter Netzwerk). Offen: nur anschauen oder auch Aktionen, Benutzer/Rechte, LAN oder VPN. Details: [WEBINTERFACE.md](WEBINTERFACE.md) |
| I-005 | 🔴 | offen | Claude | **Aufbewahrungsregeln:** Pro Gerät die letzten N Images bzw. Backups behalten, ältere automatisch löschen; Master-Images sind geschützt. Vor jedem Auftrag den Platz prüfen (belegte Blöcke + Reserve), sonst gar nicht erst starten |
| I-006 | 🔴 | offen | Claude | **Zweite Kopie (3-2-1-Regel):** Das NAS ist heute die einzige Kopie. Images und Backups zusätzlich auf eine USB-Disk, ein zweites NAS oder extern spiegeln (rsync bzw. Synology Hyper Backup). Dazu die Tool-Konfiguration (Geräte, Vorlagen, Einstellungen) täglich automatisch aufs NAS exportieren |
| I-007 | 🟡 | offen | Claude | **Images regelmässig prüfen:** Die SHA256-Werte stehen schon in `okula-image.json`. Ein Nachtlauf prüft alle Images auf Bitfehler und zeigt den Status in der Liste (✔/✖, zuletzt geprüft). Optional ein Test-Restore in eine VM (→ I-001) |
| I-008 | 🟡 | offen | Claude | **Benachrichtigungen:** E-Mail (SMTP) oder Push (ntfy/Teams) bei Fehlern, beim Ende einer Automatisierung, bei knappem NAS-Speicher, bei SMART-Warnungen und bei fehlgeschlagener Image-Prüfung |
| I-009 | 🟡 | offen | Claude | **Disk sicher löschen (Ausmusterung, Leasing-Rückgabe):** NVMe Sanitize/Format, ATA Secure Erase oder `blkdiscard`, sonst Überschreiben. Danach ein Löschprotokoll als PDF mit Seriennummer, Methode, Datum und Prüfung (Nachweis nach revDSG) |
| I-010 | 🟡 | offen | Claude | **Zeitgesteuerte Backups:** z. B. freitags 18:00: Wake-on-LAN → einmal Netzwerkstart in den Agent → Datei-Backup → herunterfahren. Die Bausteine (WOL, Agent beim nächsten Start, Backup) gibt es schon; braucht Ä-001 |
| I-011 | ⚪ | offen | Claude | **Multicast-Restore:** ein Image gleichzeitig auf viele Geräte (Schulungsraum), mit `udp-sender`/`udp-receiver` (udpcast) wie bei Clonezilla. Heute läuft jeder Restore einzeln über dieselbe 1-Gbit-Leitung |
| I-012 | 🟡 | offen | Claude | **BitLocker entsperren:** Den Wiederherstellungsschlüssel pro Gerät hinterlegen (nur root-lesbar) und im Agent mit `dislocker` öffnen. Dann sichert partclone nur die belegten Blöcke statt einer `dd`-Rohkopie (Images viel kleiner), und auch ein Datei-Backup wird möglich |
| I-013 | 🟡 | **in Arbeit** | Claude | **Inventar-Export:** alle oder ausgewählte Geräte als CSV/PDF: Modell, Seriennummer, CPU/RAM, Disks mit SMART-Befund, OS, Windows-Key maskiert, letztes Image bzw. Backup. Für Inventarliste und Übergabe an Kunden |
| I-014 | ⚪ | offen | Claude | **Treiber für Master-Images:** Treiberordner pro Modell auf dem NAS; nach dem Restore nach `Windows\Drivers\Okula` kopieren und in `unattend.xml` per `DriverPaths` (offlineServicing) einbinden. Damit passt ein Master auf verschiedene Hardware |
| I-015 | ⚪ | offen | Claude | **Firmware/BIOS über den Agent:** `fwupd`/LVFS, wo der Hersteller es unterstützt (Dell, Lenovo, teilweise HP). Die BIOS-Version steht schon im Inventar; Hinweis anzeigen, wenn sie veraltet ist |
| I-016 | 🔴 | offen | Claude | **Schutz vor Ransomware und Fehllöschung:** Das Tool-Konto hat heute volles Schreib- und Löschrecht auf dem NAS; wer den Server übernimmt, kann alle Backups löschen. Lösung: unveränderliche NAS-Snapshots (Synology Snapshot Replication mit Immutable), auf die das Tool-Konto keinen Zugriff hat, und ein Papierkorb im Tool (heute: „keinen Papierkorb – gelöschte Daten sind weg“). Das NCSC/BACS empfiehlt Offline- oder WORM-Medien und mindestens zwei Generationen |
| I-017 | 🟡 | offen | Claude | **Defekte Disk retten:** partclone bricht bei Lesefehlern ab. Ein Rettungsmodus mit `ddrescue` (Fehlerkarte, mehrere Durchgänge) bzw. `partclone -R` sichert, was noch lesbar ist. Dazu TestDisk und PhotoRec im Agent, um gelöschte Partitionen und Dateien wiederherzustellen (wie Rescuezilla und FOG) |
| I-018 | 🟡 | offen | Claude | **Einzelne Dateien aus einem Disk-Image holen:** Disk-Image auf dem Server einhängen (partclone → Loop, ntfs-3g read-only), darin suchen und einzelne Dateien oder Ordner aufs NAS oder ans Gerät senden. Heute gibt es Einzeldateien nur aus Datei-Backups (Rescuezilla: Image Explorer, Macrium: Durchsuchen) |
| I-019 | 🟡 | offen | Claude | **Disk direkt klonen:** alte HDD → neue SSD im selben Gerät (beide angeschlossen) oder Gerät → Gerät, ohne Umweg über das NAS. Mit Anpassen der Partitionsgrösse (vgl. Ä-002) |
| I-020 | 🟡 | offen | Claude | **Software nach dem Aufsetzen installieren:** pro Vorlage eine winget-Liste (z. B. 7-Zip, Adobe Reader, Teams), installiert per `FirstLogonCommands`/`SetupComplete.cmd` – der Mechanismus ist schon da (`winunattend.py`). So bleibt der Master klein, und die Software ist immer aktuell (FOG: Snapins, SmartDeploy: Application Packs) |
| I-021 | 🟡 | offen | Claude | **Firmen-Anmeldung:** Domänenbeitritt (`UnattendedJoin` in unattend.xml) bzw. Entra ID. Dazu den Autopilot-Hardware-Hash erfassen (beim ersten Start per `Get-WindowsAutopilotInfo`) und als CSV aufs NAS legen, für den Import in Intune |
| I-022 | 🟡 | offen | Claude | **Geräte vorab erfassen (CSV-Import):** Liste mit Seriennummer oder MAC, Name, Ordner/Kunde und Vorlage, z. B. vom Lieferschein. Startet das Gerät zum ersten Mal mit dem Agent, ist alles schon zugeordnet und die Automatisierung läuft (Acronis Snap Deploy: Einstellungen pro MAC). Passt zu Ä-006 |
| I-023 | 🟡 | offen | Claude | **Hardware-Diagnose am Gerät:** SMART-Selbsttest (kurz/lang), Oberflächentest der Disk, RAM-Test (memtest86+ im PXE- bzw. Stick-Menü). Ergebnis im Verlauf und im Inventar. Heute wird SMART nur gelesen |
| I-024 | 🟡 | **in Arbeit** | Claude | **Windows-11-Tauglichkeit im Inventar:** TPM 2.0, Secure Boot, CPU-Generation, RAM, UEFI. Als Spalte bzw. Filter „Win 11 ✔/✖“ (Windows 10 erhält seit Oktober 2025 keine regulären Updates mehr). Heute wird TPM nur bei der Installation umgangen, aber nicht erfasst |
| I-025 | ⚪ | **in Arbeit** | Claude | **Garantie-Abfrage:** Garantieende per Seriennummer bei Dell, Lenovo und HP (Hersteller-APIs) abfragen, im Inventar anzeigen und vor dem Ablauf warnen (Lansweeper, PDQ) |
| I-026 | ⚪ | offen | Claude | **Hardware-Änderungen erkennen:** RAM, Disk oder Seriennummer anders als beim letzten Mal → Hinweis im Verlauf (Diebstahl, Tausch, Defekt) |
| I-027 | ⚪ | offen | Claude | **Neu aufsetzen direkt am Gerät:** Auf dem Agent-Bildschirm ein Menü „Mit Master neu aufsetzen“, geschützt mit PIN, damit Techniker vor Ort das Tool nicht brauchen (Acronis: user-initiated deployment) |
| I-028 | ⚪ | offen | Claude | **Windows reparieren:** UEFI-Booteinträge und BCD neu schreiben, `ntfsfix`, Passwort eines lokalen Kontos zurücksetzen (wird protokolliert). Typische Recovery-Fälle ohne Neuinstallation |
| I-029 | ⚪ | offen | Claude | **Intel vPro/AMT:** Gerät ein- und ausschalten, ins BIOS starten und den Bildschirm sehen, auch ohne Agent und bei abgestürztem OS (MeshCentral) |
| I-030 | ⚪ | offen | Claude | **Bandbreite begrenzen** je Auftrag oder Zeitfenster, damit das Kundennetz tagsüber nicht ausgelastet ist |
| I-031 | ⚪ | offen | Claude | **Geräte-Etikett mit QR-Code:** Name, Seriennummer und Kunde drucken (z. B. Brother-Etikettendrucker); scannen öffnet das Gerät im Tool bzw. im Webinterface |

Umgesetzte Ideen: Windows-Master-Image mit Sysprep ([MASTER-IMAGE.md](MASTER-IMAGE.md)), Ordner an Geräte senden
([ORDNER-SENDEN.md](ORDNER-SENDEN.md)), Automatisierung ([AUTOMATISIERUNG.md](AUTOMATISIERUNG.md)),
Gerätename = Name im Tool.

## 📌 Entscheidungen

- **Netzwerkstart nur für freigeschaltete Geräte:** Nur Geräte, die schon mit dem Agent-Stick liefen und
  freigeschaltet sind, bekommen eine PXE-Antwort. Andere Rechner im Netz bleiben unberührt, IP-Adressen vergibt
  weiterhin der bestehende DHCP-Server.
- **NAS-Passwort nie im Repo oder Export:** liegt nur root-lesbar in `/etc/okula-recovery/nas.cred`.
  Exporte mit Agent-Schlüssel haben Rechte 0600.
- **Nur Boot-Stick (keine Direktinstallation):** Nobara (Calamares), Zorin OS (ohne Autoinstall), Windows 32-Bit.
  Bewusst so belassen.
- **Auf Zielgeräten wird nichts installiert:** Agent läuft im RAM (Stick oder Netzwerkstart).
- **Automatisches Zusammenführen nur bei sicherer Identität** (gleiche Board-UUID/Seriennummer); eine gleiche MAC
  allein reicht nie (geteilter USB-Netzwerkadapter).
- **Gerätename im Tool = Computername** bei Neuinstallation, Anpassen und Automatisierung; ändern = Gerät umbenennen.
- **Windows anpassen nur bei Master-Images (Sysprep)**; ein nicht generalisiertes Windows wird nicht verändert.
- **Passwörter werden nicht gespeichert:** lokales Konto ohne Passwort, Windows verlangt es beim ersten Anmelden.
- **Umsetzungsreihenfolge:** zuerst Agent (Fundament, ein neuer Stick reicht), dann Tool-Logik, zuletzt Oberfläche.

## ✅ Erledigt – Änderungsprotokoll

Neueste zuoberst.

### 31.10.2026
- **Ä-011 Boot-Menü-Taste je Hersteller:** Modul `bootkeys.py` (HP, Dell, Lenovo ThinkPad/IdeaPad, Asus Notebook/
  Desktop, Acer, MSI, Gigabyte, Fujitsu, Medion, Toshiba/Dynabook, Surface, Apple Intel; Quellen im Code). Tabelle im
  Stick-Dialog, in Hilfe und README; im Gerätefenster „Starttasten“ aus DMI (sys_vendor, Modell, Gehäuse, bei
  Eigenbau Mainboard-Hersteller); Netzwerkstart-Hinweis nennt die Taste des Geräts.
- **Ä-014 NAS-Webseite öffnen:** Knopf im Fenster NAS-Verbindung (neben „Verbindung testen“) und Symbol in der
  NAS-Statuszeile; Adresse aus dem gespeicherten Host, Protokoll/Port einstellbar (https 5001, http 5000), Export/Import
  inklusive. Öffnet den Browser als normaler Benutzer; ohne Host ausgegraut.

### 30.10.2026
- **Demo-Gerät (Vorführung):** Extras → Demo-Gerät startet einen simulierten Agent auf dem Server („DEMO-PC“).
  Alle Aufträge lassen sich vorführen (≈ 45 s), Fehler auf Knopfdruck; nur 127.0.0.1, keine echte Disk,
  Demo-Images nur auf den DEMO-PC zurückspielbar.
- **Fortschrittsbalken:** grün während des Auftrags, rot wenn er fehlgeschlagen ist (bis der nächste startet).
- Hilfe: alle Kapitel auf den neuen Stand (Master-Image, Ordner senden, Automatisierung, Demo-Gerät).
- **Automatisierung, Schritt 1 Backup:** wahlweise Benutzerdaten oder **ganze Disk als Disk-Image** aufs NAS.
- **Hauptschalter Automatisierung:** Stopp-Knopf ■ über der Geräteliste (statt Menü Tools), im Normalbetrieb wie
  die anderen Symbole, **rot nur solange pausiert**; dann sind die Häkchen „Auto“ und der Schalter im Reiter ausgegraut.
- **Rechtsklick Gerät:** „Automatisierung …“ entfernt, Herunterfahren/Neu starten in eigenem Block.
- **Gerätefenster:** Reiter „Automatisierung“ mit nummerierten Schritten (Kreis, Titel, Trennlinien), Reiter
  „Netzwerk“ im gleichen Stil ohne Nummern.

### 29.10.2026 (Abend) – Master-Image, Ordner senden, Automatisierung
- **Automatisierung:** Häkchen „Auto“ in der Geräteliste und Reiter „Automatisierung“ im Gerätefenster. Erfasste
  Geräte werden 30 s nach dem Auftauchen im LAN neu aufgesetzt (Countdown im Tool und am Gerät, Esc bricht ab):
  Backup (Option) → Master- oder eigenes Image → Anpassen (Name, Key) → Ordner senden (Option) → Neustart/
  Herunterfahren/nichts. Zieldisk über Seriennummer, höchstens N gleichzeitig (Menü → Einstellungen), Hauptschalter
  (Tools → Automatisierungen pausieren), Vorlagen, nach 24 h wieder ein (abschaltbar), Fehler überall sichtbar.
- **Master-Image:** Images als Master markieren (★); beim Zurückspielen „Danach anpassen“: Windows nach Sysprep
  bekommt `Windows\Panther\unattend.xml` (Gerätename, Windows-Key, Region Schweiz, lokales Konto), Linux den Hostnamen.
- **Ordner senden:** `Verteilen/Software`, `Verteilen/Test Files` und gewählte `Content`-Projekte auf den
  öffentlichen Desktop; erneut senden ersetzt, Abbruch behält den alten Stand.
- **Computername = Gerätename** bei „OS installieren“ (fest, Anzeige wie er auf dem Gerät ankommt).
- Export/Import enthält Vorlagen der Automatisierung und „höchstens gleichzeitig“.
- Neuer Agent (Modul `deploy.py`): **Agent-Stick neu erstellen bzw. Netzwerkstart neu „Vorbereiten“.**

### 29.10.2026
- **Doppelt erfasste Geräte zusammenführen:** gleiche Board-UUID/Seriennummer mit anderer ID wird beim Import und
  beim Start automatisch vereint; von Hand per Rechtsklick → „Zusammenführen mit …“. Auslöser: Gerät wurde auf
  dem neuen Server vor dem Import mit dem Stick gestartet und stand danach doppelt in der Liste.
- **Fix Debian-Direktinstallation:** Debian-ISOs haben schreibgeschützte Ordner, xorriso brach beim Entpacken
  der Bootdateien ab (`-abort_on 'FAILURE'`). Jetzt `-osirrox on:auto_chmod_on`; Fehlermeldung nennt die Ursache.
- **Fernsteuerung (Reiter „Netzwerk“ im Gerätefenster):** Wake-on-LAN, „Netzwerkstart zuerst“ (UEFI-Startreihenfolge
  per efibootmgr), Agent beim nächsten Start einmal laden.
- **Netzwerkstart (PXE):** Agent ohne Stick, nur für registrierte und freigeschaltete Geräte (Proxy-DHCP,
  MAC-Freigabeliste); unter Tools, Schalter mit Zahnrad im Gerätefenster.
- **Reiter Dateien:** Dateien/Ordner (z. B. Clonezilla-Images) per Drag & Drop oder „Hochladen“ aufs NAS;
  Abbrechen schliesst das Fenster.
- **Linux-Direktinstallation:** Softwareauswahl wie im Debian-Installer (Desktop, Standard-Werkzeuge, SSH,
  Webserver), Root-Passwort, zusätzliche Pakete.
- **Einstellungen exportieren/importieren** (Umzug auf einen neuen Rechner), NAS-Export im NAS-Fenster.
- **Fix CPU-Last ~85 %:** NAS-Prüfung lief nach dem Start pausenlos (`GLib.idle_add` mit `True`).
- Oberfläche: Menü „Extras“ (USB klonen/formatieren), Hinweise unter den Listen gekürzt, LED-Legende entfernt.
- install.sh: Zusatzpakete zum Formatieren sichtbar installieren.

### 28.10.2026
- USB klonen und USB formatieren (alle gängigen Dateisysteme); Hilfe in einfacher Sprache (F1).
- Serverlast oben rechts: CPU, RAM, LAN mit Verlauf.
- Backups: eigener Reiter, Notiz hinzufügen/ändern, Backups löschen.
- Datei-Backup: Benutzerdaten, Partitionen oder eigene Ordner sichern und zurückspielen.
- OS installieren: Windows 10/11, Ubuntu, Debian, Fedora/Anaconda direkt auf ein Gerät; Produktschlüssel pro Gerät.
- ISO-Bibliothek auf dem NAS und Boot-Sticks (wie Rufus).
- Geräte-Erfassung: Inventar, Wiedererkennung, Ordner, Gerätefenster, parallele Aufträge mit Fortschritt.
- Images in eigene Ordner einsortieren, eigene Icons je Herkunft.

### 27.10.2026
- Grundgerüst: GTK-Oberfläche, NAS einhängen, Agent-USB-Stick, Disk-Image erstellen und zurückspielen,
  Clonezilla-Images, Restore-Stick, Agent-Fortschritt am Bildschirm, install.sh.
