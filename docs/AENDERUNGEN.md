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
| 💡 Ideen | 27 | 0 | 0 |
| 🧪 Tests am realen System | siehe [TESTS.md](TESTS.md) | | |

Erledigt 31.10. (Reihenfolge): Ä-014 ✔ → Ä-011 ✔ → I-024 ✔ → Ä-002 ✔ → I-025 ✔ → I-013 ✔ – **ein neuer Agent-Stick** (Version 0.2.0, für I-024 und Ä-002) und `sudo ./install.sh` (Garantie-Helfer, python3-reportlab).
In Arbeit: **Ä-025** Hilfe abschliessen (H23 ✔ → H24 ✔ → H25 ✔ → README ✔ → Sichtprüfung).
Als Nächstes: Tests am realen System in [TESTS.md](TESTS.md) – „Fixes von heute“ und Abschnitt 7 (neue Funktionen inkl. Ä-015 bis Ä-021).
Vorschlag Reihenfolge (Analyse 31.10.): **Ä-007, Ä-008** (Sicherheit für Laien, klein) → **Ä-001** (Dienst) → **I-005/I-006** (Aufbewahrung, zweite Kopie) → Ä-005 (CI) → **Ä-006, Ä-009, Ä-010** (Assistent) → I-008 (Meldungen) → Rest nach Bedarf.

## 🐞 Bugs

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| – | | | | keine offenen Bugs | |

## 🔧 Änderungen / Verbesserungen

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| Ä-001 | 🔴 | offen | Claude | **Aufträge als Systemdienst statt im Fenster:** Aufträge, Automatisierung und PXE laufen heute als Threads im GTK-Prozess (`jobs.py`). Wird das Tool geschlossen, stürzt es ab oder meldet man sich ab, brechen laufende Restores ab. Lösung: Dienst `okula-recoveryd` (systemd), die Oberfläche wird zum Client (lokaler Socket). Das ist die Grundlage für I-004 (Webinterface) und I-010 (Zeitplan). | 31.10. (Analyse) |
| Ä-003 | 🟡 | offen | Claude | **Images und Backups auf dem NAS verschlüsseln:** Sie enthalten Personendaten (revDSG Art. 8, Datensicherheit). Minimum: SMB3-Verschlüsselung (`mount.cifs … seal`). Besser: Verschlüsselung im Datenstrom (z. B. `age` nach `zstd`), Schlüssel root-lesbar und zusätzlich auf Papier | 31.10. (Analyse) |
| Ä-004 | 🟡 | offen | Claude | **Zentrales Protokoll:** `/var/log/okula-recovery/` mit logrotate. Festhalten, wer wann was auf welches Gerät gespielt hat. Dazu Menü → „Diagnosepaket exportieren“ (Logs, Version, Konfiguration ohne Geheimnisse), um Fehler an Claude Code zu melden | 31.10. (Analyse) |
| Ä-005 | 🟡 | offen | Claude | **Entwicklung absichern:** GitHub Actions, die die 240 Tests bei jedem Push ausführen. Versionsnummer pflegen (steht noch auf `0.1.0`) und Releases taggen, damit der Server einen geprüften Stand zieht statt den Branch-Kopf. `ui.py` (2780 Zeilen) aufteilen | 31.10. (Analyse) |
| Ä-006 | 🔴 | offen | Claude | **Assistent „Neues Gerät einrichten“:** Sobald ein unbekanntes Gerät auftaucht, fragt ein Hinweis: „Neues Gerät gefunden: HP EliteBook 840 – jetzt einrichten?“. Danach Schritt für Schritt: Name → Ordner/Kunde → Vorlage oder Master-Image → „Sind noch Daten drauf?“ (Ja = Backup) → Zusammenfassung → Start. Heute muss man selbst wissen: Gerät suchen, Doppelklick, Reiter, 5 Abschnitte, Schalter | 31.10. (Laien-Test) |
| Ä-007 | 🔴 | offen | Claude | **Bestätigung vor dem Löschen:** Wird der Schalter eingeschaltet, während das Gerät verbunden ist, startet die Automatisierung ohne Rückfrage nach 30 s und löscht die Disk (`ui.save_automation` → `consider`). Nötig: rote Zusammenfassung „Disk Samsung 256 GB von HP-PC-07 wird gelöscht, Master ‚Win11 Büro‘, neuer Name …, Backup: nein“ mit Knopf „Löschen und neu aufsetzen“ | 31.10. (Laien-Test) |
| Ä-008 | 🔴 | offen | Claude | **Nach dem Restore Windows starten, auch wenn der Stick noch steckt:** BootNext auf den Windows Boot Manager setzen (`efibootmgr --bootnext`, wie in `wininstall.set_bootnext`). Heute heisst es nur „Agent-Stick abziehen“; wer das verpasst, landet wieder im Agent. Und nach 3 Tagen (bis 31.10.: 24 h) wird das Gerät erneut neu aufgesetzt, weil „Nach 3 Tagen wieder einschalten“ standardmässig an ist → Standard **aus**, oder nur bei Netzwerkstart | 31.10. (Laien-Test) |
| Ä-009 | 🟡 | offen | Claude | **Vorauswahl:** Ist nur eine interne Disk da, ist sie automatisch die Zieldisk; gibt es nur einen Master, ist er gewählt (heute sind beide Listen leer). Dazu eine Standard-Vorlage (Menü → Einstellungen), die bei jedem neuen Gerät schon eingetragen ist | 31.10. (Laien-Test) |
| Ä-010 | 🟡 | offen | Claude | **Vorabprüfung mit Ampel statt Fehler mitten im Lauf:** Image passt auf die Disk, UEFI/BIOS-Modus passt zum Master, BitLocker auf der Zieldisk (dann ist kein Datei-Backup möglich), Agent-Stick aktuell, Windows-Edition des Masters passt zum Key (Pro/Home). Anzeige: „✔ Bereit“ bzw. „⚠ Achtung: …“ | 31.10. (Laien-Test) |
| Ä-012 | 🟡 | offen | Claude | **Einfache Sprache im Reiter Automatisierung:** „Zieldisk“ → „Festplatte, die gelöscht wird“; Sysprep, Master und Content-Projekte mit einem „?“ pro Abschnitt erklären. Gerätenamen wie „DESKTOP-8F3K2LQ“ markieren und zum Umbenennen auffordern; optional Namensschema pro Vorlage (z. B. `KUNDE-001` fortlaufend) | 31.10. (Laien-Test) |
| Ä-013 | ⚪ | offen | Claude | **Klare Fertig-Meldung:** grosses „✔ Fertig – HP-PC-07 ist neu aufgesetzt (18 min)“ im Tool und am Gerät, dazu eine Liste: was gemacht wurde, Key aktiviert ja/nein, wo das Backup liegt. Als PDF ausdruckbar (Übergabeprotokoll, → I-013) | 31.10. (Laien-Test) |
| Ä-025 | 🟡 | **in Arbeit** | Dominik | **Hilfe abschliessen (H23–H25) und README im Handbuch-Stil:** Kapitelreihenfolge nach Arbeitsablauf (Demo ans Ende), Querverweise exakt; Suchfeld in der Hilfe (Ctrl+F, Treffer hervorgehoben); Test `tests/test_help.py` (Markup, Menüeinträge, Querverweise, keine Anrede; `MENU_LABELS` in ui.py); README ohne Anrede und an die Hilfe angeglichen; Sichtprüfung aller Kapitel und der Fortschrittstexte. Plan: [HILFE-PRUEFUNG.md](HILFE-PRUEFUNG.md) | 31.10. |

## 💡 Ideen

| ID | Prio | Status | Von | Beschreibung |
|---|---|---|---|---|
| I-001 | ⚪ | offen | Dominik | **Virtuelle Maschine (VM) im Tool:** ISOs/Images in einer VM auf dem Server installieren, testen, ändern und wieder Images erstellen. Details und offene Fragen: [VM.md](VM.md) |
| I-003 | ⚪ | offen | früher | **Nicht generalisierte 1:1-Images anpassen:** Gerätename per Registry (Offline-Hive `SYSTEM`: ComputerName/Hostname), Windows-Key per Skript beim ersten Start (`slmgr /ipk`). Achtung: gleiche SID und Gerätekennung auf mehreren Geräten → nur für Einzelplätze ohne Domäne geeignet. Wieder aufgenommen 31.10.2026 |
| I-004 | 🟡 | offen | Dominik | **Webinterface für den Fernzugriff:** Geräteübersicht und Gerätereiter im Browser (HTTPS, Anmeldung, über VPN); pro Gerät „Im Webinterface sichtbar“ (Reiter Netzwerk). Offen: nur anschauen oder auch Aktionen, Benutzer/Rechte, LAN oder VPN. Details: [WEBINTERFACE.md](WEBINTERFACE.md) |
| I-005 | 🔴 | offen | Claude | **Aufbewahrungsregeln:** Pro Gerät die letzten N Images bzw. Backups behalten, ältere automatisch löschen; Master-Images sind geschützt. Vor jedem Auftrag den Platz prüfen (belegte Blöcke + Reserve), sonst gar nicht erst starten |
| I-006 | 🔴 | offen | Claude | **Zweite Kopie (3-2-1-Regel):** Das NAS ist heute die einzige Kopie. Images und Backups zusätzlich auf eine USB-Disk, ein zweites NAS oder extern spiegeln (rsync bzw. Synology Hyper Backup). Dazu die Tool-Konfiguration (Geräte, Vorlagen, Einstellungen) täglich automatisch aufs NAS exportieren |
| I-007 | 🟡 | offen | Claude | **Images regelmässig prüfen:** Die SHA256-Werte stehen schon in `okula-image.json`. Ein Nachtlauf prüft alle Images auf Bitfehler und zeigt den Status in der Liste (✔/✖, zuletzt geprüft). Optional ein Test-Restore in eine VM (→ I-001) |
| I-008 | 🟡 | offen | Claude | **Benachrichtigungen:** E-Mail (SMTP) oder Push (ntfy/Teams) bei Fehlern, beim Ende einer Automatisierung, bei knappem NAS-Speicher, bei SMART-Warnungen und bei fehlgeschlagener Image-Prüfung |
| I-009 | 🟡 | offen | Claude | **Disk sicher löschen (Ausmusterung, Leasing-Rückgabe):** NVMe Sanitize/Format, ATA Secure Erase oder `blkdiscard`, sonst Überschreiben. Danach ein Löschprotokoll als PDF mit Seriennummer, Methode, Datum und Prüfung (Nachweis nach revDSG) |
| I-010 | 🟡 | offen | Claude | **Zeitgesteuerte Backups:** z. B. freitags 18:00: Wake-on-LAN → einmal Netzwerkstart in den Agent → Datei-Backup → herunterfahren. Die Bausteine (WOL, Agent beim nächsten Start, Backup) gibt es schon; braucht Ä-001 |
| I-011 | ⚪ | offen | Claude | **Multicast-Restore:** ein Image gleichzeitig auf viele Geräte (Schulungsraum), mit `udp-sender`/`udp-receiver` (udpcast) wie bei Clonezilla. Heute läuft jeder Restore einzeln über dieselbe 1-Gbit-Leitung |
| I-012 | 🟡 | offen | Claude | **BitLocker entsperren:** Den Wiederherstellungsschlüssel pro Gerät hinterlegen (nur root-lesbar) und im Agent mit `dislocker` öffnen. Dann sichert partclone nur die belegten Blöcke statt einer `dd`-Rohkopie (Images viel kleiner), und auch ein Datei-Backup wird möglich |
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
  Bewusst so belassen; Idee I-002 (Nobara/Zorin direkt installieren) am 31.10.2026 gestrichen.
- **Auf Zielgeräten wird nichts installiert:** Agent läuft im RAM (Stick oder Netzwerkstart).
- **Automatisches Zusammenführen nur bei sicherer Identität** (gleiche Board-UUID/Seriennummer); eine gleiche MAC
  allein reicht nie (geteilter USB-Netzwerkadapter).
- **Gerätename im Tool = Computername** bei Neuinstallation, Anpassen und Automatisierung; ändern = Gerät umbenennen.
- **Windows anpassen nur bei Master-Images (Sysprep)**; ein nicht generalisiertes Windows wird nicht verändert. (Wird mit I-003 neu geprüft.)
- **Passwörter werden nicht gespeichert:** lokales Konto ohne Passwort, Windows verlangt es beim ersten Anmelden.
- **Kleinere Disk (Ä-002):** Anpassen auf dem Server als neues Image (Original bleibt); Zwischenspeicher zuerst
  Server-SSD, sonst NAS (Entscheid Dominik 31.10.). Nicht bei BitLocker/Rohkopie, Btrfs/XFS, LVM, logischen Partitionen.
- **Garantie (I-025):** Felder für Dell/HP vorbereitet (Entscheid Dominik 31.10.), Abfrage aktiv, sobald ein Schlüssel
  eingetragen ist; Lenovo öffentlich (inoffiziell, kann sich ändern), sonst „Garantie bis“ von Hand. Schlüssel nur beim
  Root-Helfer, der auch abfragt – das Tool sieht sie nie. Kein Dauer-Polling: Knopfdruck + einmal nach dem Erfassen.
- **Inventar-Export (I-013, angepasst Ä-016):** keine „Kunden“ – PDF je Ordner (Name wie in der Geräteliste, jeder
  Unterordner eigene Datei) oder auf Wunsch alle Geräte in einem PDF; CSV immer eine Datei. Windows-Key nie vollständig.
- **Win 11 nicht in der Geräteliste (Ä-017):** nur im Gerätefenster (Übersicht) und im Inventar-Export.
- **Windows 11 auf nicht unterstützter Hardware (Ä-021):** technisch möglich, Microsoft rät ab (kein Support,
  keine Update-Garantie, keine Herstellergarantie bei Schäden). Daher nur von Hand mit Warnung und Vermerk, nicht
  in der Automatisierung. Empfehlung: Gerät ersetzen, Windows 10 mit ESU oder Linux.
- **Keine Kunden (Entscheid Dominik 31.10.):** alle Geräte gehören Okula – Texte und Beispiele ohne „Kunde“
  (Ordner z. B. nach Standort/Abteilung).
- **Automatisierung wieder einschalten nach 3 Tagen** (Entscheid Dominik 31.10., vorher 24 h).
- **Umsetzungsreihenfolge:** zuerst Agent (Fundament, ein neuer Stick reicht), dann Tool-Logik, zuletzt Oberfläche.

## ✅ Erledigt – Änderungsprotokoll

Neueste zuoberst.

### 31.10.2026
- **Ä-024 Hilfe (F1) überarbeitet – Prüfung H1–H22** ([HILFE-PRUEFUNG.md](HILFE-PRUEFUNG.md)): Fehler korrigiert (Knopf „Verbindung testen“, Firewall-Ports inkl. Netzwerkstart, Optionen bei Image/Restore/Datei-Backup, Menünamen), neue Kapitel „Typischer Ablauf“, „Geräte verwalten“, „Master-Image“, „Inventar, Garantie, Win 11“, „Images verwalten“, „Probleme lösen“ ergänzt, Begriffe erklärt und vereinheitlicht. **Handbuch-Stil ohne Anrede** in Hilfe und Oberfläche; rund 80 Fortschritts- und Log-Texte von Ich-Form auf Vorgang („Stick wird geprüft …“). Regel in CLAUDE.md. Nur Texte, kein neuer Agent-Stick nötig.
- **Ä-023 Win-11-Prozessorliste abgeglichen** (Microsoft Learn, Listen Original/24H2/25H2 für Intel, AMD, Qualcomm):
  tauglich = Serie steht in einer der Listen (24H2/25H2 gelten laut Microsoft für neue OEM-Geräte und lassen ältere
  Serien weg, z. B. Ryzen 2000). Neu ✔: Celeron 3000-Serie, Pentium Gold 4415U/4417U/4425Y, Core X 7000X, Xeon Scalable
  1. Gen. (z. B. Silver 4110), Xeon W-2100/3100, Core Series 1/2, Ryzen 100/200/Z, AMD 3015e/3020e. Neu ✖: i7-7820HQ
  (in keiner Liste mehr), Atom x6000. EPYC 2. Gen. (7xx2) bleibt „?“ (nicht eindeutig gelistet).
- **Ä-022 Texte ohne „Kunde“:** „auf Wunsch des Kunden“ aus Häkchen, Warnung, Hilfe und README entfernt;
  Beispiele für Ordner jetzt Standort/Abteilung (alle Geräte gehören Okula).
- **Ä-018 Automatisierung: 3 Tage statt 24 h:** nach erfolgreichem Durchlauf schaltet sie sich nach 3 Tagen wieder
  ein (`automation.REARM_HOURS = 72`), Anzeige „wieder aktiv in 2 Tagen 5 h“; Texte, Hilfe, README angepasst.
- **Ä-019 Laufzeit monoton gemessen:** Laufzeit/Restzeit der Aufträge (`jobs.Job.t0`, `duration`) und das
  Agent-Timeout (`discovery.AgentInfo.last_seen`) mit `time.monotonic()` – eine Uhr-Korrektur (NTP) verfälscht die
  Restzeit nicht mehr und trennt nicht mehr alle Agents auf einmal. Uhrzeit für Anzeige bleibt `time.time()`.
- **Ä-020 Unicode-Prüfung:** neues Modul `textnorm.py`. Computernamen mit sauberer Umschrift auch in NFD-Form
  (vorher „Bu-ro“, „Stra-e“, „ster“ – jetzt „Buero“, „Strasse“, „Oester“). Neue Ordner-/Dateinamen auf NAS und
  im Tool: NFC, unsichtbare Steuerzeichen (z. B. Rechts-nach-links U+202E, Null-Breite) abgelehnt, „existiert
  bereits“ auch bei anderer Unicode-Form oder Gross-/Kleinschreibung (SMB). Bestehende Namen bleiben unverändert
  erreichbar. Gerätenamen vom Gerät: NFC, Steuerzeichen entfernt. Export-Dateinamen nach NFC gekürzt.
- **Ä-021 Windows 11 auf nicht unterstützter Hardware – nur von Hand:** Die Setup-Umgehung (LabConfig) war beim
  Boot-Stick **standardmässig an** – jetzt aus, Einschalten nur nach Bestätigung der Microsoft-Hinweise.
  Direktinstallation (prüft selbst nichts): Windows 11 auf „nicht tauglichem“ Gerät nur mit Häkchen „Trotzdem
  installieren“; danach Vermerk am Gerät (Übersicht, Verlauf, Inventar-Export). Nie in der Automatisierung.
- **Ä-015 Gerätefenster zeigt die ganze Übersicht:** Fenster öffnet so hoch, dass alle Zeilen der Übersicht ohne
  Scrollen sichtbar sind (höchstens Bildschirmhöhe; auf kleinen Bildschirmen weiter mit Scrollbalken).
- **Ä-016 Inventar-Export je Ordner:** statt „je Kunde“ eine PDF-Datei je Ordner (Ordnername wie in der Liste,
  Unterordner eigene Datei, voller Ort im Kopf); neue Option „alle Geräte in einer Datei“.
- **Ä-017 Spalte „Win 11“ aus der Geräteliste entfernt:** Tauglichkeit bleibt im Gerätefenster und im Export.
- **I-013 Inventar-Export:** `inventory_export.py` + Dialog (`inventory_dialog.py`): Menü → „Inventar exportieren
  (CSV/PDF) …“ und Rechtsklick auf Ordner/Gerät. Umfang alle / Ordner (mit Unterordnern) / markierte Geräte. CSV UTF-8
  mit BOM, Semikolon; PDF je Kunde (oberste Ordnerebene), A4 quer, Kopf Kunde + Datum, Seitenzahl (reportlab,
  `python3-reportlab` in install.sh). Spalten wie gewünscht inkl. Disks mit SMART, Win-11-tauglich, Garantie bis,
  letztes Image/Backup (vom NAS). Windows-Key standardmässig nicht, sonst nur maskiert. Tests `tests/test_inventory_export.py`.
- **I-025 Garantie-Abfrage:** `warranty.py` – Dell (TechDirect Warranty API v5) und HP (HP Warranty API) über den
  neuen Root-Helfer `/usr/local/sbin/okula-warranty` (Schlüssel nur in `/etc/okula-recovery/warranty.cred`, root,
  0600; Eingabe unter Menü → Einstellungen → Garantie-Abfrage, nie in Konfiguration/Export, nie angezeigt), Lenovo über
  die öffentliche Support-Seite. Gerätefenster → Übersicht „Garantie bis“: grün / gelb (≤ 90 Tage) / rot (abgelaufen),
  „Beim Hersteller abfragen“ und „Von Hand …“. Abfrage nur auf Knopfdruck und einmal nach dem Erfassen; Ergebnis am
  Gerät (30 Tage aktuell), bei Fehler bleibt das alte Datum. Tests mit gemockten Antworten (`tests/test_warranty.py`).
  Hinweis: Die Hersteller-Server waren in der Entwicklungsumgebung gesperrt – Endpunkte am realen System prüfen
  (TESTS.md). `install.sh` erneut ausführen (neuer Root-Helfer, sudo-Regel).
- **Ä-002 Restore auf eine kleinere Disk:** `shrink.py` leitet auf dem Server ein neues Image ab (grösste Partition
  NTFS/ext2/3/4 in Sparse-Datei → `ntfsresize`+`ntfsfix -d` bzw. `e2fsck`+`resize2fs` → neu sichern; Partitionen
  dahinter ans neue Ende; neue sfdisk-Tabelle). Prüfung sofort aus dem partclone-Kopf (belegt + Reserve 10 %, min.
  1 GB), Meldung mit Zahlen. Zwischenspeicher Server-SSD, sonst NAS. Dialog „Für diese Disk anpassen“, Automatisierung
  Option „Image dafür anpassen“. Agent: fehlendes Dateisystem bei lsblk per `blkid` ermitteln (sonst Rohkopie).
  Plan: [KLEINERE-DISK.md](KLEINERE-DISK.md).
- **I-024 Windows-11-Tauglichkeit:** Agent erfasst TPM-Version, UEFI/BIOS und Secure Boot (`inventory.platform`);
  Bewertung auf dem Server (`win11.py`: TPM 2.0, UEFI, RAM ≥ 4 GB, Disk ≥ 64 GB, Prozessor nach
  `data/win11_cpus.txt` mit Quelle Microsoft). Spalte „Win 11“ ✔/✖/? in der Geräteliste, Grund im Gerätefenster.
  Version 0.2.0 – **Agent-Stick neu erstellen**. Hinweis: learn.microsoft.com war in der Entwicklungsumgebung gesperrt,
  die Prozessorliste ist nach Microsofts Generationen-Regeln aufgebaut; unbekannte Modelle zeigen „?“.
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
