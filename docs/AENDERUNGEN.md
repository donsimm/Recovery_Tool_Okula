# Änderungen, Bugs, Ideen und Entscheidungen

Zentrale Übersicht zum Okula Recovery Tool. Details zu jeder Funktion stehen in [TECHNIK.md](TECHNIK.md),
der genaue Verlauf in `git log`, Prüfungen in [TESTS.md](TESTS.md).

**Ablauf:** Spontane Notizen kommen nach [EINGANG.md](EINGANG.md). Gestrichene Punkte liegen im [PAPIERKORB.md](PAPIERKORB.md). Claude sortiert sie hier in die passende
Kategorie ein (mit ID), leert den Eingang und hält die Kurzübersicht aktuell.

**Von:** Dominik = eigene Idee/Meldung · Claude = Vorschlag aus Analyse · früher = aus früheren Sitzungen.

**IDs:** `B-` Bug · `Ä-` Änderung/Verbesserung · `I-` Idee · Status: **offen**, **in Arbeit**, **erledigt**
(→ ins Protokoll verschieben), **zurückgestellt**. Priorität: 🔴 hoch · 🟡 mittel · ⚪ tief.

## Kurzübersicht

| Kategorie | Offen | In Arbeit | Zurückgestellt |
|---|---|---|---|
| 🐞 Bugs | 4 | 0 | 0 |
| 🔧 Änderungen | 9 | 0 | 0 |
| 💡 Ideen | 23 | 0 | 0 |
| 🧪 Tests am realen System | siehe [TESTS.md](TESTS.md) | | |

**Stand 25.11.2026 – Version 0.2.0 (Tag `v0.2.0`):** letzter VM-Durchgang grün (VM-Win11-clean: Direktinstallation
mit Windows anpassen „Clean“, Startmenü über das Bereitstellungspaket des Tools – auch ohne ADK, kein Sperrbildschirm,
Protokoll ohne Fehler). Code-Review [REVIEW-2026-11-25.md](REVIEW-2026-11-25.md); B-025 bis B-028 daraus erledigt.
Frühere Stände: Protokoll unten und `git log`.

**Als Nächstes** (Reihenfolge Dominik 25.11.):
1. ~~B-027, B-028~~ erledigt 25.11. (am realen System ungeprüft, [TESTS.md](TESTS.md) „B-027“, „B-028“). Klein dazu: Startdialog bei kaputter Schlüsseldatei (`ui.py:135`) und Verlauf „abgebrochen“ von Hand gestarteter Aufträge (`ui.py:4202`) → bei Ä-048.
2. ~~I-012~~ BitLocker entsperren erledigt 25.11. (am realen System ungeprüft, [TESTS.md](TESTS.md) „I-012“; neuer Agent-Stick und Netzwerkstart nötig). Offen dazu: Ausführungsrecht `packaging/okula-bitlocker` im Repo (install.sh setzt 0755), Schlüssel beim Zusammenführen zweier Geräte übernehmen.
3. **I-042** Microsoft 365 Apps einzeln installieren (Office).
4. **I-043** Ordner einfärben (Geräteliste und Archiv).
5. Danach: Kleines aus dem VM-Test (**Ä-047**, **B-023**, **B-024**), Datensicherheit (**I-016**, **I-006**, **Ä-003**),
   **I-017** Rescue, **I-011** Multicast; **Ä-048**/**Ä-049** und zweite Review-Runde.
6. Am realen Gerät: **B-013** (OEM-Schlüssel), **B-004** (EliteBook UEFI), offene Prüfungen [TESTS.md](TESTS.md) „Übersicht“.

**Am Server nach jedem Update:** `git pull && sudo ./install.sh`, Tool neu starten; ob ein neuer Agent-Stick nötig ist,
steht im jeweiligen Protokoll-Eintrag.

## 🐞 Bugs

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| B-023 | ⚪ | offen | Okuli | **Protokoll „Windows anpassen“ uneinheitlich, Startmenü meldet Hinweis trotz Paket.** VM-Test 25.11. (VM-Win11-clean, Direktinstallation, Vorlage Clean geändert, Pro Build 26200): Startmenü zeigt nur die Okula-Kacheln, `StartPins.ppkg` vom Tool installiert – trotzdem steht in der Zeile „Startmenü: Werbe-Kacheln entfernen“ und in „Wiederinstallation von Werbe-Apps sperren“ weiter der lange Pro-Hinweis (WhatsApp, LinkedIn, Adobe Express … von Hand lösen). Erwartet laut B-022: knappes „ok“, wenn das Paket greift. Zudem schreibt die erste Zeile (vor dem ersten Start, `winsetup.py`) „Startmenue“ und „ - “ statt Umlaut und „–“ und verweist auf eine „Zeile Startmenue beim ersten Start“, die es nicht gibt | 25.11. |
| B-024 | ⚪ | offen | Okuli | **OneDrive entfernen meldet ok trotz Fehlercode.** Protokoll 25.11.: „OneDrive entfernen (OneDriveSetup /uninstall: -2147219813, Autostart entfernt: 2 Profile)“ mit Status ok. Rückgabewert prüfen (bekannter harmloser Code oder echter Fehler?) und entsprechend Hinweis statt ok melden | 25.11. |
| B-013 | 🟡 | offen | Okuli | **Windows-Direktinstallation mit OEM-Schlüssel: Setup-Partition bleibt evtl. stehen.** Laut Microsoft Learn („Add a Custom Script to Windows Setup“) läuft `%WINDIR%\Setup\Scripts\SetupComplete.cmd` nicht, wenn Windows mit einem OEM-Schlüssel installiert wird (ausser Enterprise). Die Direktinstallation setzt den Schlüssel (hinterlegt oder aus dem BIOS, MSDM) in specialize als `ProductKey`; ist es ein OEM-Schlüssel, würde das Aufräumen (Setup-Partition „OKULASETUP“ löschen, C: vergrössern) ausbleiben. Hinweis des Agenten bei I-038 (12.11.), am realen System ungeprüft. Prüfen an einem Gerät mit Schlüssel im BIOS; falls bestätigt: Aufräumen zusätzlich anders auslösen (z. B. wie bei I-038 als RunSynchronous bzw. FirstLogonCommand) | 12.11. |
| B-004 | 🔴 | offen | Dominik | **HP EliteBook 850 G1 in „UEFI Native (Without CSM)“: Agent-Stick wird nicht angezeigt, Netzwerkstart (UEFI IPv4) scheitert – im Tool kein Hinweis.** Stick: MBR + FAT32 (Typ 0x0c) mit Debian-shim; PXE: Proxy-DHCP mit `pxe-prompt`/`pxe-service` BC_EFI/X86-64_EFI. Befund 05.11. (BIOS-Fotos): Secure Boot aus, Fast Boot aus, USB device boot an; **„PXE Internal IPV4 NIC boot“ aus** (nur „PXE Internal NIC boot“ = Legacy an) → im UEFI-Modus gibt es keinen Netzwerkstart; F9 zeigt nur „Boot From EFI File“ – auch der Stick fehlt. Nächster Test: IPV4 NIC boot an; Stick über „Boot From EFI File“ → EFI/boot/bootx64.efi starten (liest die Firmware die FAT-Partition?). BIOS-Vergleich 05.11.: einziger lesbarer Unterschied die **BIOS-Version** – EliteBook 2 (geht nicht) L71 **01.49** (2020), EliteBook 1 (geht) L71 **01.11** (2014); Einstellungen über Linux nicht lesbar (B-006) | 05.11. |

## 🔧 Änderungen / Verbesserungen

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| Ä-048 | 🟡 | offen | Okuli (Review) | **Robustheit Agent, Netz und Oberfläche (Sammelpunkt aus dem Review).** Agent: TLS-Handshake ohne Timeout/accept ungeschützt (R-agent 2), Neustart-Timer prüft Disk-Lock nicht erneut (R-agent 3), `wimlib-imagex` läuft nach Verbindungsabbruch weiter (R-agent 1), Kleines R-agent 4–9. Tool: Beacons ungeprüft legen Geräte an, keine Obergrenze (R-client 6); NAS-Zugriffe im GTK-Hauptthread frieren bei hängendem CIFS ein (R-ui 2), `refresh_images` überholt sich (R-ui 4), Kleines R-ui 3, 5–8. Software-Bibliothek: Programme, die ein Auftrag gerade überträgt, lassen sich löschen (Rest aus B-026). Windows: Int32-Rückgabewerte (R-win 5), Kindprozesse bei Timeout (R-win 6). Gleiche Board-UUID → falsches Gerät (R-client 3) zuerst prüfen. [REVIEW-2026-11-25.md](REVIEW-2026-11-25.md) | 25.11. |
| Ä-049 | ⚪ | offen | Okuli (Review) | **`ui.py` (4457 Zeilen) aufteilen** – erster Schritt als Mixins (`ui_const`, `ui_storage`, `ui_devices`, `ui_vm`, `ui_actions`), `win.xxx` bleibt stabil; Vorschlag [REVIEW-2026-11-25.md](REVIEW-2026-11-25.md) R-ui. Teil von Ä-005 (dort Version 0.1.0 überholt: steht auf 0.2.0, Tag v0.2.0 gesetzt 25.11.) | 25.11. |
| Ä-047 | 🟡 | offen | Dominik/Okuli | **„Sperrbildschirm aus“ in die Vorlage Clean aufnehmen.** Clean = Windows ohne Werbung; der Sperrbildschirm zeigt Windows Spotlight (Werbung, Tipps). Heute fehlt `lockscreen_off` in `TEMPLATES["Clean"]` (`wintweaks.py`), beim VM-Test 25.11. darum nicht gewählt. Tests anpassen (Vorlagen-Inhalt, „Clean (geändert)“-Erkennung) | 25.11. |
| Ä-003 | 🟡 | offen | Claude | **Images und Backups auf dem NAS verschlüsseln:** Sie enthalten Personendaten (revDSG Art. 8, Datensicherheit). Minimum: SMB3-Verschlüsselung (`mount.cifs … seal`). Besser: Verschlüsselung im Datenstrom (z. B. `age` nach `zstd`), Schlüssel root-lesbar und zusätzlich auf Papier | 31.10. (Analyse) |
| Ä-004 | 🟡 | offen | Claude | **Zentrales Protokoll:** `/var/log/okula-recovery/` mit logrotate. Festhalten, wer wann was auf welches Gerät gespielt hat. Dazu Menü → „Diagnosepaket exportieren“ (Logs, Version, Konfiguration ohne Geheimnisse), um Fehler an Claude Code zu melden | 31.10. (Analyse) |
| Ä-005 | 🟡 | offen | Claude | **Entwicklung absichern:** GitHub Actions, die alle Tests (über 320) bei jedem Push ausführen. Versionsnummer pflegen und Releases taggen, damit der Server einen geprüften Stand zieht statt den Branch-Kopf (25.11.: Version 0.2.0, erstes Tag `v0.2.0` – Rest offen: CI, Server zieht Tags). `ui.py` aufteilen → Ä-049 | 31.10. (Analyse) |
| Ä-006 | 🔴 | offen | Claude | **Assistent „Neues Gerät einrichten“:** Sobald ein unbekanntes Gerät auftaucht, fragt ein Hinweis: „Neues Gerät gefunden: HP EliteBook 840 – jetzt einrichten?“. Danach Schritt für Schritt: Name → Ordner/Kunde → Vorlage oder Master-Image → „Sind noch Daten drauf?“ (Ja = Backup) → Zusammenfassung → Start. Heute muss man selbst wissen: Gerät suchen, Doppelklick, Reiter, 5 Abschnitte, Schalter | 31.10. (Laien-Test) |
| Ä-010 | 🟡 | offen | Claude | **Vorabprüfung mit Ampel statt Fehler mitten im Lauf:** Image passt auf die Disk, UEFI/BIOS-Modus passt zum Master, BitLocker auf der Zieldisk (dann ist kein Datei-Backup möglich), Agent-Stick aktuell, Windows-Edition des Masters passt zum Key (Pro/Home). Befund 10.11.: BIOS/MBR-Image (CompactPlayer) liess sich ohne Warnung auf eine UEFI-VM spielen und startet dort nicht. Anzeige: „✔ Bereit“ bzw. „⚠ Achtung: …“. Befund 25.11. (HP ZBook Fury G1i): Agent-Stick „Selected boot image did not authenticate“ bei Secure Boot → Hinweis aufnehmen: BIOS F10 → Security → Secure Boot Configuration → „Enable MS UEFI CA key“ = Yes (hat geholfen); auch in Hilfe (F1) | 31.10. (Laien-Test) |
| Ä-012 | 🟡 | offen | Claude | **Einfache Sprache im Reiter Automatisierung:** „Zieldisk“ → „Festplatte, die gelöscht wird“; Sysprep, Master und Content-Projekte mit einem „?“ pro Abschnitt erklären. Gerätenamen wie „DESKTOP-8F3K2LQ“ markieren und zum Umbenennen auffordern; optional Namensschema pro Vorlage (z. B. `KUNDE-001` fortlaufend) | 31.10. (Laien-Test) |

## 💡 Ideen

| ID | Prio | Status | Von | Beschreibung |
|---|---|---|---|---|
| I-003 | ⚪ | offen | früher | **Nicht generalisierte 1:1-Images anpassen:** Gerätename per Registry (Offline-Hive `SYSTEM`: ComputerName/Hostname), Windows-Key per Skript beim ersten Start (`slmgr /ipk`). Achtung: gleiche SID und Gerätekennung auf mehreren Geräten → nur für Einzelplätze ohne Domäne geeignet. Wieder aufgenommen 31.10.2026 |
| I-004 | 🟡 | offen | Dominik | **Webinterface für den Fernzugriff:** Geräteübersicht und Gerätereiter im Browser (HTTPS, Anmeldung, über VPN); pro Gerät „Im Webinterface sichtbar“ (Reiter Netzwerk). Offen: nur anschauen oder auch Aktionen, Benutzer/Rechte, LAN oder VPN. Details: [WEBINTERFACE.md](WEBINTERFACE.md) |
| I-005 | 🔴 | offen | Claude | **Aufbewahrungsregeln:** Pro Gerät die letzten N Images bzw. Backups behalten, ältere automatisch löschen; Master-Images sind geschützt. Vor jedem Auftrag den Platz prüfen (belegte Blöcke + Reserve), sonst gar nicht erst starten |
| I-006 | 🔴 | offen | Claude | **Zweite Kopie (3-2-1-Regel):** Das NAS ist heute die einzige Kopie. Images und Backups zusätzlich auf eine USB-Disk, ein zweites NAS oder extern spiegeln (rsync bzw. Synology Hyper Backup). Dazu die Tool-Konfiguration (Geräte, Vorlagen, Einstellungen) täglich automatisch aufs NAS exportieren |
| I-008 | 🟡 | offen | Claude | **Benachrichtigungen:** E-Mail (SMTP) oder Push (ntfy/Teams) bei Fehlern, beim Ende einer Automatisierung, bei knappem NAS-Speicher, bei SMART-Warnungen und bei fehlgeschlagener Image-Prüfung |
| I-009 | 🟡 | offen | Claude | **Disk sicher löschen (Ausmusterung, Leasing-Rückgabe):** NVMe Sanitize/Format, ATA Secure Erase oder `blkdiscard`, sonst Überschreiben. Danach ein Löschprotokoll als PDF mit Seriennummer, Methode, Datum und Prüfung (Nachweis nach revDSG) |
| I-011 | 🟡 | offen | Claude/Dominik | **Multicast – ein Image gleichzeitig auf viele Geräte (von Hand, Variante B):** eigener Menüpunkt **Extras → Multicast …** mit eigenem Fenster, ähnlich wie Netzwerkstart (PXE): Image wählen (Master zuerst), Geräteliste mit Haken (Status verbunden/nicht verbunden, Zieldisk je Gerät), Knopf zum Einschalten und Agent starten, „Starten“ wartet, bis alle gewählten Geräte bereit sind, dann ein Datenstrom für alle (udpcast `udp-sender`/`udp-receiver`). Fortschritt je Gerät; fällt eines aus, laufen die anderen weiter. Danach je Gerät Anpassen (Name, Windows-Schlüssel) bei Master-Images. Nicht in die Automatisierung eingebaut (Entscheid Dominik 31.10.). Voraussetzungen: gleiches Netz/VLAN, Kabel, Firewall-Ports für udpcast; neuer Agent-Stick nötig. Heute läuft jeder Restore einzeln |
| I-014 | ⚪ | offen | Claude | **Treiber für Master-Images:** Treiberordner pro Modell auf dem NAS; nach dem Restore nach `Windows\Drivers\Okula` kopieren und in `unattend.xml` per `DriverPaths` (offlineServicing) einbinden. Damit passt ein Master auf verschiedene Hardware |
| I-015 | ⚪ | offen | Claude | **Firmware/BIOS über den Agent:** `fwupd`/LVFS, wo der Hersteller es unterstützt (Dell, Lenovo, teilweise HP). Die BIOS-Version steht schon im Inventar; Hinweis anzeigen, wenn sie veraltet ist |
| I-016 | 🔴 | offen | Claude | **Schutz vor Ransomware und Fehllöschung:** Das Tool-Konto hat heute volles Schreib- und Löschrecht auf dem NAS; wer den Server übernimmt, kann alle Backups löschen. Lösung: unveränderliche NAS-Snapshots (Synology Snapshot Replication mit Immutable), auf die das Tool-Konto keinen Zugriff hat, und ein Papierkorb im Tool (heute: „keinen Papierkorb – gelöschte Daten sind weg“). Das NCSC/BACS empfiehlt Offline- oder WORM-Medien und mindestens zwei Generationen |
| I-017 | 🔴 | offen | Claude/Dominik | **Extras → Rescue … (Daten retten und Windows reparieren, zusammengeführt mit I-028):** eigenes Fenster wie Netzwerkstart/Multicast. 1. Gerät wählen (nur mit Agent verbunden), 2. Disk/Partition wählen (mit SMART-Zustand), 3. Werkzeug: **Daten retten** – Defekte Disk sichern (`ddrescue` mit Fehlerkarte, mehrere Durchgänge, Image aufs NAS), Gelöschte Dateien retten (PhotoRec, nicht interaktiv), Partitionen wiederherstellen (TestDisk: Suchen/Anzeigen im Tool, schwierige Fälle interaktiv am Bildschirm des Geräts); **Windows reparieren** – Start reparieren (UEFI-Booteinträge, BCD), NTFS reparieren (`ntfsfix`), lokales Passwort zurücksetzen (`chntpw`, im Verlauf protokolliert). Regeln: auf eine defekte Disk nie schreiben; Ergebnisse nach `Rescue/<Gerät>/<Datum>` auf dem NAS; schreibende Reparaturen nur mit Bestätigung und Empfehlung „vorher Disk-Image“; BitLocker: nur „Defekte Disk sichern“. Fortschritt, Log, Verlauf. Neuer Agent-Stick (gddrescue, testdisk, chntpw). Vorführbar am DEMO-PC (ohne NAS, Demo-Speicher). Heute bricht partclone bei Lesefehlern ab |
| I-018 | 🟡 | offen | Claude | **Einzelne Dateien aus einem Disk-Image holen:** Disk-Image auf dem Server einhängen (partclone → Loop, ntfs-3g read-only), darin suchen und einzelne Dateien oder Ordner aufs NAS oder ans Gerät senden. Heute gibt es Einzeldateien nur aus Datei-Backups (Rescuezilla: Image Explorer, Macrium: Durchsuchen) |
| I-021 | 🟡 | offen | Claude | **Firmen-Anmeldung:** Domänenbeitritt (`UnattendedJoin` in unattend.xml) bzw. Entra ID. Dazu den Autopilot-Hardware-Hash erfassen (beim ersten Start per `Get-WindowsAutopilotInfo`) und als CSV aufs NAS legen, für den Import in Intune |
| I-022 | 🟡 | offen | Claude | **Geräte vorab erfassen (CSV-Import):** Liste mit Seriennummer oder MAC, Name, Ordner/Kunde und Vorlage, z. B. vom Lieferschein. Startet das Gerät zum ersten Mal mit dem Agent, ist alles schon zugeordnet und die Automatisierung läuft (Acronis Snap Deploy: Einstellungen pro MAC). Passt zu Ä-006 |
| I-033 | 🟡 | offen | Dominik/Claude | **Hardware-Test Teil 2:** vollständiger RAM-Test mit memtest86+ als eigener Starteintrag (Agent-Stick und Netzwerkstart; nicht für Secure Boot signiert → dafür Secure Boot kurz aus) mit Ergebnis im Tool; Tests mit Person am Gerät (Tastatur, Lautsprecher, Bildschirm-Testbilder, Kamera); optional Schnelltest als Schritt der Automatisierung | 05.11. |
| I-026 | ⚪ | offen | Claude | **Hardware-Änderungen erkennen:** RAM, Disk oder Seriennummer anders als beim letzten Mal → Hinweis im Verlauf (Diebstahl, Tausch, Defekt) |
| I-027 | ⚪ | offen | Claude | **Neu aufsetzen direkt am Gerät:** Auf dem Agent-Bildschirm ein Menü „Mit Master neu aufsetzen“, geschützt mit PIN, damit Techniker vor Ort das Tool nicht brauchen (Acronis: user-initiated deployment) |
| I-029 | ⚪ | offen | Claude | **Intel vPro/AMT:** Gerät ein- und ausschalten, ins BIOS starten und den Bildschirm sehen, auch ohne Agent und bei abgestürztem OS (MeshCentral) |
| I-035 | ⚪ | offen | Okuli | **Hinweis bei VM-Disk grösser als freier Platz:** Ä-037 bietet „VM-Disk auf 1001 GB vergrössern“ an, obwohl der Server nur 889 GB frei hat (Befund 10.11., Probe-VM). Zum Zurückspielen reicht es (qcow2 wächst nur mit den belegten Daten), füllt sich die VM später, läuft der Server voll. Vorschlag: Hinweis „⚠ Disk grösser als der freie Platz auf dem Server (… GB)“ im Prüftext, ohne zu sperren |
| I-036 | ⚪ | offen | Okuli | **Hardware-Fehler (MCE/WHEA) anzeigen:** Der Agent liest Kernel-Meldungen `mce: [Hardware Error]` (bzw. `rasdaemon`) und meldet sie im Tool (Gerätefenster, Verlauf, Hinweis in der Liste). Anlass B-010 (CPU 3 meldet laufend Fehler). Passt zu I-033 Hardware-Test |
| I-040 | ⚪ | offen | Okuli/Dominik | **Windows-Aktivierung im Blick:** Der Agent liest den OEM-Key aus der Firmware (ACPI-Tabelle MSDM, unter Windows `(Get-CimInstance SoftwareLicensingService).OA3xOriginalProductKey`) und, wenn Windows läuft, den Aktivierungsstatus; das Tool zeigt beides im Gerätefenster bzw. Inventar. Beim Aufsetzen wird der passende allgemeine Setup-Key (RTM-Key) der Edition gesetzt, damit sich ein Gerät mit digitaler Lizenz oder Firmware-Key online von selbst aktiviert. Nur lizenzkonforme Wege (kein KMS-Emulator o. ä.); bei VMs gilt weiter „OEM-Key nie übernehmen“ (I-001). Anlass: Frage Dominik 19.11. zu GVLK/RTM-Keys |
| I-042 | 🟡 | offen | Dominik | **Microsoft 365 Apps einzeln installieren:** Neuer Bibliothekstyp „Office (Click-to-Run)“ mit dem Office Deployment Tool. Laden: `setup.exe /download` einmal komplett auf das NAS (Deutsch, 64 Bit, Produkt `O365BusinessRetail` bzw. `O365ProPlusRetail` – mit Learn klären). Auswahl in *Software installieren …* (und *OS installieren* / *Danach anpassen*): Apps einzeln anhaken (Word, Excel, PowerPoint, Outlook, OneNote, Access, Publisher, OneDrive = `Groove`, Teams); das Tool erzeugt je Auftrag eine `config.xml` mit `ExcludeApp` für alles Nicht-Gewählte, Installation still über das Startskript ohne Internet (`SourcePath` lokal). Nachinstallieren einzelner Apps auf einem Gerät mit Office: gleiche Sprachen → neue `ExcludeApp`-Liste ersetzt die alte (Microsoft Learn, ODT-Konfigurationsoptionen). Aktivierung: Anmeldung des Kunden mit dem Microsoft-Konto, kein Schlüssel im Tool. Offen: Updatekanal, neues vs. klassisches Outlook, Publisher-Ende. Von Dominik 24.11. |
| I-043 | ⚪ | offen | Dominik | **Ordner einfärben:** Ordner in der Geräteliste (Kunden/Gruppen) und im Archiv (Images/ISOs) bekommen per Kontextmenü „Farbe …“ eine von etwa 8 festen Farben (oder keine); Anzeige als Farbpunkt bzw. -balken in der Liste, lesbar im hellen und dunklen Design. Farbe wird mit dem Ordner gespeichert und bleibt beim Verschieben/Umbenennen erhalten. Hilfe-Kapitel mitführen. Cockpit-Idee ID-0003 (11.11.), Umfang „beide“ Dominik 25.11. |

Umgesetzte Ideen: Windows-Master-Image mit Sysprep ([MASTER-IMAGE.md](MASTER-IMAGE.md)), Ordner an Geräte senden
([ORDNER-SENDEN.md](ORDNER-SENDEN.md)), Automatisierung ([AUTOMATISIERUNG.md](AUTOMATISIERUNG.md)),
Gerätename = Name im Tool.

## 📌 Entscheidungen

- **BitLocker entsperren (I-012, Dominik 25.11.2026):** nur **lesend** (`dislocker -r`) und nur für Datei-Backups
  (Benutzerdaten, Ordner/Partitionen, Durchsuchen). Bewusst **nicht**: Disk-Image aus belegten Blöcken (Kundendaten lägen
  unverschlüsselt auf dem NAS – erst mit Ä-003), Schreiben auf BitLocker (Software, Anpassen, Restore). Schlüssel:
  Standard beim Auftrag eingeben, Häkchen „Für dieses Gerät speichern“ → nur root-lesbar unter
  `/etc/okula-recovery/bitlocker/`, nie in Inventar, Export oder Webinterface; Automatisierung sichert nur mit
  gespeichertem Schlüssel. Nur Wiederherstellungsschlüssel, kein Benutzerpasswort. Prompt
  [I-012](prompts/I-012-bitlocker-entsperren.md).
- **Startmenü auf neu installiertem Windows (B-022, Umsetzungs-Agent 25.11.2026):** Gruppenrichtlinie „Configure
  Start Pins“ bleibt (offline und im Skript, wirkt, wo freigeschaltet), aber **kein „ok“ ohne Wirkung**: Status
  „Hinweis“ im Protokoll und Hinweis im Log, solange kein Bereitstellungspaket wirkt. Sicherer Weg laut Learn ist das
  **Bereitstellungspaket** (Policy CSP ohne Geräteverwaltung) – Installation über das Skript
  (`Install-ProvisioningPackage -QuietInstall`), gleich für alle Wege. Das Paket lässt sich nur unter Windows mit
  Windows Configuration Designer erzeugen (Format nicht dokumentiert) – einmal erzeugen und im Repo ablegen, nur
  verwendet, wenn es zur aktuellen Liste passt. Bewusst **nicht**: Paket nach `C:\Recovery\Customizations` (nur bei
  OOBE, gehört zu „Reset this PC“), `LayoutModification.json` (nur Zusatz-Kacheln), Wirkung über `start2.bin` erkennen
  (nicht dokumentiert), Zeit in cmd zerlegen (`%DATE%` sprachabhängig) – stattdessen gleicht das Skript das
  Protokoll an. Belege Microsoft Learn und support.microsoft.com (abgerufen 25.11.2026) in TECHNIK.md.
- **Neustart-Knöpfe (Ä-045, Umsetzungs-Agent 24.11.2026):** Startziel bei echten Geräten über **BootNext** (einmalig,
  BootOrder unverändert) statt die Startreihenfolge umzustellen; „Agent“ = BootCurrent (der Eintrag, von dem der Agent
  lief), Rückfall Netzwerk-Eintrag. Mehrere Windows-Boot-Manager: aktiv vor inaktiv, dann wie in BootOrder (welche Disk,
  prüft das Tool nicht). Geht es nicht, wird nicht still neu gestartet, sondern mit Hinweis nachgefragt. VMs ohne BootNext
  (libvirt-Reihenfolge genügt). Frage nach dem Senden nur bei *Windows anpassen* und *Software installieren*, erst wenn
  der Auftrag fertig ist. Bewusst **nicht** geändert: Abschluss „Neustart“ der Automatisierung (`automation.py`,
  `automation_tab.py` – parallel Ä-046) und der Neustart nach der Direktinstallation (BootNext auf die Setup-Partition).
  Belege: UEFI-Spezifikation 3.1.2 (BootNext/BootCurrent), Microsoft Learn „BCDBoot Command-Line Options“ (Eintrag
  „Windows Boot Manager“ in NVRAM), abgerufen 24.11.2026.

- **Windows anpassen beim Aufsetzen (Ä-046, Umsetzungs-Agent 25.11.2026):** Direktinstallation in zwei Teilen –
  Richtlinien vor der ersten Anmeldung setzt `install.cmd` in der Setup-Umgebung offline (`reg load` des neuen Hives,
  noch kein Profil → kein Umbenennen von `start2.bin`; wirkt auch mit OEM-Schlüssel), das Skript läuft zuletzt aus
  `SetupComplete.cmd` bzw. als Startskript. Reihenfolge **erst Software, dann Anpassen** (Dienste/Store-Apps stören
  keine Installation; SetupComplete wartet höchstens 30 min, Neustart der Software kommt danach). OEM-Schlüssel (B-013):
  übrige Einstellungen über das Startskript beim ersten Start, nur ehrlicher Hinweis. Bewusst **nicht**: automatische
  Anmeldung beim Aufsetzen (Passwort würde gespeichert), Anpassen beim Master im Audit-Modus (landet im Master,
  Sysprep-Risiko), `FirstLogonCommands`/specialize als OEM-Ausweichweg. Belege Microsoft Learn (abgerufen 24.11.2026)
  in TECHNIK.md – die Seite zu SetupComplete widerspricht sich („before the logon screen“ vs. „after the user sees the
  desktop“), am Gerät prüfen.
- **Win11 clean (Ä-042, Umsetzungs-Agent 18.11.2026):** Startmenü über die Richtlinie **ConfigureStartPins** (Policy
  CSP, laut Microsoft Learn Pro ab Windows 11 21H2) per MDM-Bridge statt `LayoutModification.json` im Standardprofil
  (die OEM-Datei ergänzt nur bis zu 4+4 Kacheln, ersetzt die Microsoft-Platzhalter nicht und gilt nur für neue
  Benutzer) und statt `start2.bin` (binär, nicht dokumentiert). Bewusst **nicht**: Bereich „Empfohlen“ ausblenden
  (`HideRecommendedSection` – nimmt auch die zuletzt geöffneten Dateien), Rechner/Editor/Paint/Fotos/Snipping
  Tool/Terminal/Edge über Apps-Häkchen oder Vorlagen entfernen (Ergänzung 18.11., Entscheid Dominik: nur über die Gruppe
  *Windows-Programme*, Standard aus, in keiner Vorlage; Edge, Einstellungen, Suche, Sicherheit nie), Store-Apps
  nachinstallieren. Nachlauf als einmalige geplante Aufgabe 30 min nach der
  ersten Anmeldung (läuft einmal, nicht dauerhaft). Laptop entfernt Kurznotizen, Audiorecorder und Schnellhilfe wie
  die übrigen Apps (Prompt: „wie die übrigen Apps behandeln“). Ä-040 (`LayoutModification.xml` der Taskleiste)
  bleibt unberührt – die Richtlinie betrifft nur die Startmenü-Kacheln.
  **Korrektur B-017 (19.11.):** Ab Windows 11 24H2 die Gruppenrichtlinie mit Pfad zur JSON-Datei
  (`ConfigureStartPinsJSON`, Datei `%ProgramData%\Okula\StartPins.json`), MDM-Bridge nur davor; Widgets zusätzlich per
  Richtlinie `AllowNewsAndInterests` = 0. Bewusst nicht geprüft: ob KB5062660 installiert ist.
- **Rest vor der ersten Anmeldung (B-021, Umsetzungs-Agent 24.11.2026):** Offline zusätzlich nur `NoLockScreen`
  (*Sperrbildschirm aus*) und `DisableWindowsConsumerFeatures` (*Wiederinstallation sperren*) – beide wirken vor bzw. bei
  der ersten Anmeldung und sind reine Maschinen-Richtlinien (Belege Policy CSP, TECHNIK.md). Werbe-Platzhalter bei
  Pro/Home: **kein** Registry-Weg ohne Quelle (weder `ContentDeliveryManager`-Werte noch Standardprofil
  `NTUSER.DAT`), nur ehrlicher Hinweis und „Von Start lösen“ von Hand; `DisableCloudOptimizedContent` bewusst nicht
  gesetzt (nicht Pro, Wirkung aufs Startmenü nicht ausdrücklich belegt). Agent-Uhr nach dem **Server** (Anfrage trägt
  `now`) statt `hwclock --localtime` bzw. `utc=no` (Geräte mit Linux führen die RTC in UTC; RTC wird nie geschrieben).
  Weitere Maschinen-Werte (Cortana, Bing, Telemetrie, Updates, OneDrive, automatische Anmeldung) bewusst nicht offline
  – Begründung in TECHNIK.md. Belege von Microsoft Learn (abgerufen 24.11.2026).
- **Offline statt Wettlauf (B-020, Umsetzungs-Agent 24.11.2026):** Windows wartet bei der Anmeldung nicht auf
  Startskripte (auch nicht mit `SyncForegroundPolicy`). Was vor der ersten Anmeldung wirken muss (Startmenü-Richtlinie,
  JSON, `start2.bin` umbenennen, Widgets-Richtlinie), schreibt der Agent offline; das Startskript setzt die Werte trotzdem
  (doppelt). Umbenannt und markiert wird nur, wenn die Richtlinie offline gesetzt ist. `ConfigureStartPinsJSON` offline
  als `%ProgramData%\Okula\StartPins.json` (REG_EXPAND_SZ, Laufwerk unbekannt), das Startskript schreibt danach den
  absoluten Pfad. Sperre: Mutex mit 120 s Wartezeit, danach ohne Sperre weiter (Hinweis). Bewusst **nicht**:
  Registrierungs-Reste nach dem Aufräumen als FEHLER (bleiben Hinweis wie B-018, ohne Wirkung); Sperre im Notfall-`.cmd`;
  Offline-Teil für *Software installieren* (nichts muss dort vor der Anmeldung wirken); Direktinstallation (Ä-046).
  Belege aus dem Befund, Quellen aus dem Gedächtnis (kein Internet im Auftrag).
- **Startskripte vor der Anmeldung (B-019, Umsetzungs-Agent 24.11.2026; abgelöst durch B-020 – SyncForegroundPolicy
  wird nicht mehr gesetzt, nur noch als Altlast wiederhergestellt):** Richtlinie `SyncForegroundPolicy` nur
  während ein Okula-Startskript aussteht, offline per `hivexsh` (das einzige Hive-Schreiben des Agents) mit Prüfung
  vor dem Zurückschreiben. Klappt das Setzen nicht, wird trotzdem gesendet (Hinweis statt Abbruch – das Skript läuft
  dann wie vorher nach der Anmeldung). Ein unsauber geschlossener Hive (Sequenznummern ungleich) wird bewusst
  **nicht** beschrieben. Leer angelegte Richtlinien-Schlüssel bleiben nach dem Rückbau stehen (ohne Wirkung).
  Bewusst **nicht**: `MaxGPOScriptWait` erhöhen, Direktinstallation (dort kein Hive vor dem Setup). Angemeldete
  Profile: kein Umbenennen von `start2.bin` (die Shell schriebe sie neu), Nachholen nur im Nachlauf und nur
  abgemeldet. Belege aus dem Gedächtnis (kein Internet im Auftrag) – Prüfung am Gerät über Ereignis 5016 vs. 4624.
- **Test-VMs mit Gastagent (I-041, Umsetzungs-Agent 19.11.2026):** einzige Ausnahme vom Grundsatz „keine
  virtio-Geräte“, nur als Option *Gastagent (nur Test-VMs)*, Standard aus; Häkchen auch beim Anlegen einer VM.
  Warnung beim Master als Rückfrage (*Trotzdem fortfahren*), nicht gesperrt. Gasttools mit eigenem Typ
  „virtio-win-Gasttools (Burn)“ (`/install /quiet /norestart`); andere Burn-Pakete bleiben bei `/quiet /norestart`.
  Bewusst **nicht**: Befehle aus dem Tool heraus in der VM, eigener Download der Gasttools, Gastagent bei Zwillingen.
- **Installer-Erkennung (Ä-043, Umsetzungs-Agent 18.11.2026):** Parameter nur vorbelegen, wo sie sicher sind; bei
  Setup Factory, Clickteam, Smart Install Maker, Actual Installer, CreateInstall, Ghost Installer, InstallScript,
  Qt IFW vor 4.0 und SFX-Archiven bewusst „Parameter fehlt“ mit dem vermuteten Parameter im Hinweis (ein falscher
  Parameter liesse den Installer am Gerät 60 min auf eine Eingabe warten). Quellen der Parameter aus dem Gedächtnis,
  nicht abgerufen (kein Internet im Auftrag) – Liste in [TECHNIK.md](TECHNIK.md). MSI ohne `msiinfo`/`msidump` mit
  eigenem Leser. *Neu erkennen* behält Ordnername und Schlüssel (gespeicherte Auswahlen bleiben gültig). MSIX:
  Abhängigkeiten (VCLibs …) nicht automatisch, sondern als eigene Einträge. Bewusst **nicht**: Installer ausführen,
  Antwortdateien aufzeichnen, SFX-Archive entpacken, Name von NSIS-Installern ohne Versionsinfo aus dem Skript raten
  (nur feste Registry-Werte).
- **Startreihenfolge nach der Direktinstallation (B-015, Umsetzungs-Agent 17.11.2026):** `install.cmd` setzt nur
  `{bootmgr}` an die erste Stelle; Firmware-Einträge der Setup-Partition werden bewusst **nicht** aus `{fwbootmgr}`
  entfernt (`bcdedit`-Ausgabe sprachabhängig und mehrzeilig, Agent-Stick mit gleichem Pfad, Eintrag evtl. von der
  Firmware neu angelegt). Keine zusätzliche `bcdboot`-Option. Details [TECHNIK.md](TECHNIK.md).
- **Software automatisch installieren (I-020, Entscheid Dominik 17.11.2026):** aus dem Ordner `Verteilen\Software` mit festen,
  getesteten Versionen statt winget (winget: neueste Version, Internet nötig, Spezialsoftware fehlt, unter Windows 10 ohne Store
  kaum nutzbar); in *OS installieren*, *Image zurückspielen* und Automatisierung. winget höchstens später als Ergänzung.
  Umsetzung (Umsetzungs-Agent 17.11.): Unterordner = ein Programm; Sammelordner werden nicht einzeln aufgeteilt,
  sondern lassen sich als **„nur kopieren“** markieren (Ordner auf den öffentlichen Desktop unter `Software\`).
  Startmechanismus wie I-039 (Startskript der lokalen Gruppenrichtlinie), installiert wird in einer **einmaligen
  geplanten Aufgabe als SYSTEM**, die das Startskript anlegt (10-Minuten-Grenze der Startskripte); bei der
  Direktinstallation zusätzlich Aufruf aus `SetupComplete.cmd` (auch Audit-Modus). Squirrel-Installer gelten als „nur
  von Hand“ (installieren nur für den angemeldeten Benutzer). Bewusst **nicht**: Ergebnis zurücklesen, winget,
  Deinstallieren. Details [TECHNIK.md](TECHNIK.md), „Software installieren“.
  **Abgelöst durch Ä-041 (Entscheid Dominik 18.11.2026):** Quelle ist nicht mehr `Verteilen\Software`, sondern die
  eigene **Software-Bibliothek** des Tools (NAS `Software-Bibliothek/` neben `Verteilen`, Extras → „Software-Bibliothek …“);
  `Verteilen\Software` bleibt Werkzeug-Ordner für *Ordner senden*. Umsetzung (Umsetzungs-Agent 18.11.): je Eintrag ein
  Ordner `<key>-<version>` mit Installer bzw. geladenem Ordner und Beschreibung `.okula.json`; Doppel = gleiche
  SHA-256 des ganzen Inhalts (gleicher Name, anderer Inhalt → `-2`); Aufräumen der I-020-Beschreibungen bei jedem
  Verbinden mit dem NAS (nur Dateien mit `"format": "okula-software"` direkt in `Verteilen\Software`); bei laufendem
  Demo-Gerät zeigt das Fenster die Bibliothek im Demo-Speicher. Bewusst **nicht**: automatisch übernehmen, ZIP entpacken,
  portable Tools erkennen.
- **Master-Einstellungen ohne Skripte (Ä-040, Entscheid Dominik 17.11.2026):** CopyProfile und Taskleiste übernimmt das Tool;
  am Master wird nur im Audit-Modus von Hand eingerichtet. Umsetzung (Umsetzungs-Agent 17.11.): Reihenfolge der Pins aus
  `NTUSER.DAT` mit eigenem, nur lesendem Registry-Leser (kein Hive-Schreiben, kein `LayoutXMLPath`);
  `LayoutModification.xml` ins Standardprofil **und** ins Administrator-Profil (CopyProfile ersetzt das Standardprofil);
  Programme ohne Startmenü-Eintrag als Verknüpfung unter Startmenü → *Okula*. Bewusst **nicht**: Startmenü-Kacheln
  (aus dem Profil nicht zuverlässig ableitbar), Bereinigen der Standard-App-Zuordnungen nach CopyProfile, Windows 11
  besonders behandeln (erst am Gerät prüfen). Details [TECHNIK.md](TECHNIK.md).
- **Windows anpassen (I-039, Entscheid Dominik 17.11.2026):** eigene Funktion wie *Ordner senden* (später als Häkchen
  in *Danach anpassen*, Direktinstallation und Automatisierung); Umsetzung über ein einmaliges Startskript beim nächsten
  Windows-Start; Vorlagen „Player“ und „Laptop“ fest vorgegeben; automatische Anmeldung gehört dazu. Bewusst **nicht**
  aus dem TuningPack: Utilman durch CMD ersetzen, Sicherheitscenter/Defender aus, Microsoft-Server sperren,
  Zeitsynchronisation aus, Admin-Freigaben aus, Gaming-/TCP-Tweaks, Entwicklermodus, Core Parking.
  Startmechanismus (Umsetzungs-Agent 17.11., Prompt liess die Wahl offen): **Startskript der lokalen
  Gruppenrichtlinie** (`System32\GroupPolicy`, nur Dateien, kein Hive-Schreiben); vorhandene Richtlinie wird ergänzt
  und nach dem Lauf wiederhergestellt. Begründung und verworfene Varianten: [TECHNIK.md](TECHNIK.md), „Windows anpassen“.
- **Software installieren an einem Gerät mit Windows (Ä-044, Umsetzungs-Agent 19.11.2026, Prompt liess „Neustart
  anbieten bzw. gleiches Verhalten wie Windows anpassen“ offen):** gleiches Verhalten wie *Windows anpassen* – das
  Tool startet nicht neu, Dialog und Hilfe nennen „Gerät neu starten (Agent-Stick abziehen)“. Kein eigener Agent-Befehl,
  der bestehende `software` (I-020) wird wiederverwendet.

- **Rückfrage beim Einschalten der Automatisierung (Ä-007, Entscheid Dominik 10.11.2026, Variante B):** bei jedem
  Einschalten von Hand (Häkchen *Auto*, Schalter im Reiter), egal ob verbunden. Keine Rückfrage beim Wieder-Einschalten
  nach 3 Tagen und beim Aufheben des Stopps ■; kein Eintippen des Gerätenamens (Variante C verworfen); Countdown
  30 s mit Esc bleibt. Schalter im Reiter lässt sich unvollständig nicht mehr einschalten (Umsetzungs-Agent: sonst
  startete eine später vervollständigte Einstellung ohne Rückfrage).
- **Projektübersicht (I-034) im Tool, nicht auf claude.ai** (Entscheid Dominik 10.11.2026): Daten live aus dem Repo (`~/recovery_tool_okula/docs`), Anzeige in Firefox über einen Webserver nur auf 127.0.0.1, Rückmeldungen in einer Datei ausserhalb von Git; die Projektleitung trägt sie auf Zuruf („neue Daten“) in TESTS.md/AENDERUNGEN.md ein und markiert sie als übernommen.
- **„Nach 3 Tagen wieder einschalten“ bleibt standardmässig an** (Automatisierung; Entscheid Dominik 31.10.2026).
- **Netzwerkstart nur für freigeschaltete Geräte:** Nur Geräte, die schon mit dem Agent-Stick liefen und
  freigeschaltet sind, bekommen eine PXE-Antwort. Andere Rechner im Netz bleiben unberührt, IP-Adressen vergibt
  weiterhin der bestehende DHCP-Server.
- **NAS-Passwort nie im Repo oder Export:** liegt nur root-lesbar in `/etc/okula-recovery/nas.cred`.
  Exporte mit Agent-Schlüssel haben Rechte 0600.
- **Nur Boot-Stick (keine Direktinstallation):** Nobara (Calamares), Zorin OS (ohne Autoinstall), Windows 32-Bit.
  Bewusst so belassen; Idee I-002 (Nobara/Zorin direkt installieren) am 31.10.2026 gestrichen ([PAPIERKORB.md](PAPIERKORB.md)).
- **Auf Zielgeräten wird nichts installiert:** Agent läuft im RAM (Stick oder Netzwerkstart).
- **Automatisches Zusammenführen nur bei sicherer Identität** (gleiche Board-UUID/Seriennummer); eine gleiche MAC
  allein reicht nie (geteilter USB-Netzwerkadapter).
- **Gerätename im Tool = Computername** bei Neuinstallation, Anpassen und Automatisierung; ändern = Gerät umbenennen.
- **Windows anpassen nur bei Master-Images (Sysprep)**; ein nicht generalisiertes Windows wird nicht verändert. (Wird mit I-003 neu geprüft.) Gilt für *Danach anpassen* (Name, Key); die Funktion „Windows anpassen …“ (I-039) ändert bewusst auch ein installiertes Windows.
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
- **Demo nutzt nie das NAS (Entscheid Dominik 31.10., Ä-027):** alle Daten des DEMO-PC liegen im lokalen
  Demo-Speicher (`~/.config/okula-recovery/demo/`), auch wenn das NAS verbunden ist. Demo-Images nie auf echte
  Geräte, echte Images und Backups nie auf den DEMO-PC. Alte Demo-Images auf dem NAS werden nur ausgeblendet
  und zum Löschen angeboten, nicht automatisch gelöscht.
- **Bandbreite nur im Tool begrenzt (I-030):** Der Agent bleibt unverändert (kein neuer Stick); eine Grenze für
  alle Aufträge zusammen statt je Auftrag. NAS-Zugriffe des Servers werden nicht begrenzt.
- **VMs (I-001, Entscheid Dominik 06.11.2026):** im LAN sichtbar (Brücke `br0`, von `install.sh` angelegt – am Server
  installieren), Bildschirm im eigenen Fenster, Windows „nicht aktiviert“, OEM-Key nie übernehmen. Zwillings-VM:
  Seriennummer/UUID abgewandelt mit Kennzeichen, eigene MAC, letztes Image einspielen (Standard an). Details [VM.md](VM.md).
- **VM-Legacy mit Intel e1000 statt Realtek rtl8139** (I-001 Auftrag 1b, 06.11.2026): rtl8139 hat in Windows 10/11
  keinen mitgelieferten Treiber; rtl8139 bleibt nur für Linux wählbar.
- **Umsetzungsreihenfolge:** zuerst Agent (Fundament, ein neuer Stick reicht), dann Tool-Logik, zuletzt Oberfläche.
- **VM-Startreihenfolge Disk → Netzwerk mit Umstellung zur Laufzeit** (I-001 Auftrag 2, 06.11.2026, Umsetzungs-Agent
  nach Prüfung am Server; ersetzt den Prompt-Entscheid „fest Netzwerk → Disk“): OVMF startet nach grub-`exit`
  (Startart „lokal“) nicht von der Disk. Das Tool stellt die laufende VM nach dem Verbinden des Agents auf Disk
  zuerst um. Details [VM.md](VM.md).
- **Digitaler Zwilling: Netzwerkkarte immer Intel** (Projektleitung, 06.11.2026, I-001 Auftrag 3): Q35 → e1000e,
  i440FX → e1000, auch wenn das Gerät eine Realtek-Karte hat; die echte Karte steht in der Vorschau. Zweiter Zwilling
  desselben Geräts bekommt UUID `0c1a0001-…` usw. (Umsetzungs-Agent).

- **VM-Snapshots als externe Overlays, vom Tool verwaltet** (I-001 Auftrag 4, 06.11.2026, Umsetzungs-Agent nach
  Prüfung am Server): libvirt 11.3 legt externe Snapshots an und setzt sie zurück, das Löschen (block-commit) scheitert
  aber an AppArmor (`deny … w` für Backing-Dateien). Darum eigene Liste in den VM-Metadaten, Löschen per block-stream in
  einer angehaltenen Hilfs-VM. NVRAM und TPM-Zustand werden bewusst nicht mitkopiert (Secure Boot bleibt, BitLocker in
  Master-VMs aus). Löschen nur bei ausgeschalteter VM. Details [VM.md](VM.md).

## ✅ Erledigt – Änderungsprotokoll

Neueste zuoberst.

### 25.11.2026
- **I-012 – BitLocker entsperren (nur lesend, für Datei-Backups)** (Von: Claude; Entscheide Dominik 25.11.; Prompt
  [I-012](prompts/I-012-bitlocker-entsperren.md)). **Agent:** `profiles`, `browse`, `estimate` und `backup` nehmen
  optional `bitlocker: {"<partition>": "<schlüssel>"}`; `filebackup.Mounts` öffnet die Partition mit
  `dislocker -r` (FUSE) und hängt `dislocker-file` mit `ro,loop` ein, Aufräumen umgekehrt auch bei Fehlern.
  Format geprüft, falscher Schlüssel → „Wiederherstellungsschlüssel passt nicht zu <Partition>“, Meldungen und
  Agent-Log ohne Schlüssel; `profiles` meldet `bitlocker: true`. Schreibend (`Mounts(write=True)`, `deploy`) bleibt
  BitLocker gesperrt; ohne dislocker „Agent-Stick zu alt für BitLocker – neuen Stick erstellen“. **Tool:**
  `bitlocker_keys.py` (Format + Blockprüfung durch 11, Ablage pro Gerät nur root-lesbar unter
  `/etc/okula-recovery/bitlocker/`, Ordner 0700/Datei 0600, atomar, Rechte geprüft) über den neuen Root-Helfer
  `okula-bitlocker` (sudo, Schlüssel nur über stdin; `install.sh`). *Backup erstellen …*: Rahmen *BitLocker* mit
  Feld *Wiederherstellungsschlüssel* (verdeckt, Einfügen möglich), Häkchen *Für dieses Gerät speichern* (nur
  passender Schlüssel), Knopf *Entsperren*; gespeicherter Schlüssel automatisch, danach Profile neu. Automatisierung:
  Benutzerdaten mit gespeichertem Schlüssel; ohne/falscher Schlüssel Abbruch wie B-025 (Meldung um
  „BitLocker-Schlüssel im Gerätefenster hinterlegen“ ergänzt), nichts gelöscht. Gerätefenster → *Übersicht*:
  *BitLocker-Schlüssel hinterlegt* ja/nein mit *Schlüssel hinterlegen …*/*Entfernen*; Gerät bzw. VM löschen löscht
  die Schlüssel mit. Nie in Geräte-JSON, Inventar, Exporten, Logs oder Verlauf. Bewusst **nicht**: Disk-Image aus
  belegten Blöcken (bleibt Rohkopie), Schreiben auf BitLocker, Benutzerpasswort; Schlüssel beim Zusammenführen von
  Geräten nicht übernommen. **Neuer Agent-Stick und Netzwerkstart neu vorbereiten nötig** (`dislocker`, `fuse3` in
  `stick.BUNDLED_PACKAGES`). Hilfe (F1) „Datei-Backup“, „Automatisierung“, „Gerät verbinden“, „Inventar, Garantie,
  Windows 11“, „Probleme lösen“; TECHNIK.md „BitLocker entsperren (I-012)“, AUTOMATISIERUNG.md. Tests
  `tests/test_bitlocker.py`, `BackupBlockerTest` in `tests/test_automation.py`. Prüfung [TESTS.md](TESTS.md) „I-012“.
- **B-028 – Fehler werden als ok/Erfolg gemeldet (Sammelpunkt)** (Von: Okuli (Review), 25.11.; Prompt
  [B-028](prompts/B-028-fehler-als-ok.md); [REVIEW-2026-11-25.md](REVIEW-2026-11-25.md) R-client 4, 5, 10, R-win 1–4).
  **Tool:** Anpassen-Ergebnis `error`/`not_generalized` bzw. kein Windows, obwohl das Image eine NTFS-Partition hat
  (`jobs.customize_problems`, `jobs.image_has_windows`), ist in der Automatisierung ein Fehler in Schritt 3 (kein
  „erfolgreich“, kein Abschluss/Neustart, Automatisierung bleibt an); *Image zurückspielen* mit *Danach anpassen*
  meldet „Warnung beim Anpassen: …“ statt „und angepasst“; `r.get('part', '?')` statt `KeyError`. Ausnahme in
  `Engine._execute` → Phase Fehler mit Verlauf, Lauf bleibt nie auf „läuft“ (`Engine._internal_error`). „Abgebrochen“
  nur, wenn die Ausnahme selbst der Abbruch ist (`jobs.is_cancel_error`) – sonst bleibt die Ursache in Log, Verlauf
  und Banner. **Windows-Skripte:** `install.cmd` bricht bei Kopierfehlern von `unattend.xml`, `SetupComplete.cmd`,
  Software (`xcopy`) und Startskripten ab (`goto fehler`, Protokoll, kein „fertig“/Neustart); fehlende Installer im
  Software-Skript = FEHLER, „schon installiert“ nur mit ok-Eintrag im Protokoll (`Test-OkulaDone`); `reg unload`
  nach 10 Versuchen erfolglos → FEHLER des Bausteins; Sperrbildschirm bei Home und „Wiederinstallation sperren“ bei
  Pro/Home als „Hinweis“ statt „ok“. Hilfe (F1) „Automatisierung“, „Windows anpassen“, „Software installieren“,
  „Probleme lösen“ und AUTOMATISIERUNG.md ergänzt. Kein neuer Agent-Stick nötig. R-client 9 (Esc-Countdown) ist mit B-027 erledigt. **Nicht** umgesetzt (ausserhalb des
  Prompts): Anzeige „abgebrochen“ in `ui.py`
  (Verlauf von Hand gestarteter Aufträge prüft weiter nur `job.cancel`). Prüfung [TESTS.md](TESTS.md) „B-028“.
- **B-027 – Image galt als fertig, obwohl eine Datei offen war oder fehlte** (Von: Okuli (Review), 25.11.; Prompt
  [B-027](prompts/B-027-image-vollstaendig.md); [REVIEW-2026-11-25.md](REVIEW-2026-11-25.md) R-client 1, 7, 8, 9).
  Nur `agentclient.py`: Bei `end` ohne `begin`, mit offener Datei oder mit fehlender Datei aus dem Plan (ausser
  `optional`, z. B. `.sfdisk`) gibt es „Image unvollständig: … fehlt – Image wurde verworfen“, der `.partial`-Ordner
  wird aufgeräumt. Eine neue Datei, bevor die vorige fertig ist, gilt als Protokollfehler. Dateien und
  `okula-image.json` werden vor dem Umbenennen geflusht und mit `fsync` geschrieben, danach Arbeits- und Elternordner
  (Netzlaufwerke ohne Ordner-`fsync`: ohne). Ordnername: freier Name in einer Schleife (`…-2`, `…-3`); ein
  `.partial`-Rest gleichen Namens wird übersprungen, nicht gelöscht. Ist der Agent nicht erreichbar, bleibt kein
  leerer `.partial`-Ordner mehr liegen. Schlüsseldatei: neu über `.tmp` (0600) und atomar an den Platz (harter Link,
  sonst `os.replace`); vorhanden, aber leer/ungültig → Fehler mit Pfad, Datei bleibt unverändert (kein stiller neuer
  Schlüssel mehr). Countdown: Verbindungsabbruch, keine Rückmeldung 10 s nach Ablauf, unbekanntes Ergebnis, andere
  Fehlermeldung oder Gerät nicht erreichbar → `AgentError` (Automatisierung: „abgebrochen“), nie „start“; selbst
  gezählt wird nur noch bei „Unbekannter Befehl“ (alter Agent). Am Agent nichts geändert, kein neuer Agent-Stick
  nötig. Hilfe (F1) „Automatisierung“ ergänzt. Tests `ImageCompleteTest`, `CountdownTest`, `KeyTest` in
  `tests/test_imaging.py`. Prüfung [TESTS.md](TESTS.md) „B-027“.
- **B-025 – Automatisierung löscht BitLocker-Disk ohne Backup** (Von: Okuli (Review), 25.11.; Prompt
  [B-025](prompts/B-025-automatisierung-bitlocker-backup.md); [REVIEW-2026-11-25.md](REVIEW-2026-11-25.md) R-client 2;
  realer Fall HP ZBook). Backup „Benutzerdaten“: hat eine Partition der Zieldisk im Profil-Ergebnis des Agents ein
  `error` (BitLocker oder nicht einhängbar, z. B. Ruhezustand/Schnellstart), bricht der Lauf in Schritt 1 ab, bevor
  etwas gelöscht wird (`automation.backup_blocker`, `AutomationError`): Phase Fehler, Automatisierung bleibt
  eingeschaltet, Meldung in Verlauf und Banner, z. B. „Backup nicht möglich: nvme0n1p3 ist mit BitLocker verschlüsselt –
  nichts gelöscht. BitLocker in Windows ausschalten oder Backup „ganze Disk“ wählen.“ Ohne Fehler und ohne Benutzer
  (leere Disk, Linux ohne /home) wie bisher weiter. Fehler auf anderen Disks zählen nicht. Andere Datei-Backups vor
  dem Löschen gibt es nicht (Backup-Dialoge zeigen den Fehler je Partition an, löschen nichts). Hilfe (F1)
  „Automatisierung“ und AUTOMATISIERUNG.md ergänzt. Tests `BackupBlockerTest` in `tests/test_automation.py`. Prüfung
  [TESTS.md](TESTS.md) „B-025“.
- **B-026 – Image liess sich löschen/verschieben, während es zurückgespielt wird** (Von: Okuli (Review), 25.11.;
  Prompt [B-026](prompts/B-026-image-loeschen-waehrend-restore.md); [REVIEW-2026-11-25.md](REVIEW-2026-11-25.md)
  R-ui 1). **Umgesetzt:** Zurückspielen (auch „VM-Disk vergrössern und zurückspielen“), Zwilling, Windows-/Linux-
  Installation und Automatisierung tragen das gelesene Image bzw. die ISO in `Job.source` ein (`JobManager.start(…,
  source=…)`). Gemeinsame Prüfung `JobManager.in_use(*pfade)` / `busy_paths()`: gesperrt, wenn ein laufender Auftrag
  den Pfad, etwas darin oder einen Pfad in diesem Ordner liest. Geprüft vor: Image/ISO löschen, Ordner löschen (Archiv
  und Betriebssysteme), Verschieben per Maus (Image, ISO, Ordner), „Nach „Nicht einsortiert““, Umbenennen (Ordner,
  ISO, Reiter „Dateien“), Löschen im Reiter „Dateien“ (über `_confirm_delete`, nochmals nach der Rückfrage) und
  `delete_backup` (gleiche Prüfung statt eigener). Meldung „… wird gerade von „<Auftrag>“ verwendet – erst nach Ende
  löschen/verschieben.“, nichts passiert. „Alte Demo-Images vom NAS löschen …“ überspringt belegte Images (Hinweis in
  der Statuszeile). Hilfe (F1) „Images verwalten“ ergänzt. Tests `tests/test_inuse.py`. Nicht erfasst: Programme der
  Software-Bibliothek, die ein Auftrag gerade überträgt (Löschen in der Software-Bibliothek prüft nicht).
- **B-022 – Startmenü-Liste wirkt auf neu installiertem Windows nicht** (Von: Okuli, 25.11.; Prompt
  [B-022](prompts/B-022-startmenue-neuinstallation.md); Befund VM-Win11-clean, Direktinstallation mit Ä-046, Windows 11
  Pro 25H2 26200.8037). **Ursache** (Belege TECHNIK.md „Startmenü auf neu installiertem Windows (B-022)“): belegt –
  die GPO-Variante kam mit KB5062660, der Support-Artikel führt die Start-Pins-Neuerung unter „Gradual rollout“;
  belegt nicht die Ursache – Edition (Pro unterstützt) und „temporary enterprise feature control“ (Startmenü nicht in
  der Liste); plausibel – die Gruppenrichtlinie ist auf frisch installierten Geräten noch nicht freigeschaltet;
  Vermutung – wann die Freischaltung kommt. **Umgesetzt:** Startmenü-Baustein meldet ohne wirksames Paket
  **„Hinweis“ statt „ok“** („Wirkung nicht sicher – …“, Zähler „mit Hinweis“ in der Schlusszeile), Hinweis auch im Log
  des Auftrags (Agent offline), in der Vorschau der Direktinstallation, im Tooltip und in der Hilfe (F1).
  **Bereitstellungspaket** (Policy CSP `Policies/Start/ConfigureStartPins`, Learn-Weg ohne Geräteverwaltung)
  vorbereitet: Vorlage `okula_recovery/assets/startpins/customizations.xml`; liegt `StartPins.ppkg` mit passender
  `StartPins.ppkg.json` daneben, installiert das Skript es (`Install-ProvisioningPackage -QuietInstall`) für alle Wege
  (Direktinstallation, Agent offline + Startskript, Startskript) – erzeugen nur unter Windows mit Windows Configuration
  Designer (Okuli). **Protokoll der Direktinstallation:** Zeilen von `install.cmd`/`SetupComplete.cmd` gleicht das
  Skript beim ersten Schreiben ins Format `JJJJ-MM-TT hh:mm:ss` an und speichert die Datei als UTF-8 mit BOM;
  Neustart-Zeile der Software vor dem Skript. Tests `tests/test_startmenue_neuinstallation.py` (vom Agent nicht
  ausgeführt). Prüfung [TESTS.md](TESTS.md) „B-022“.
- **Ä-046 – Windows anpassen beim Aufsetzen mitgeben: neue Maschine in einem Durchgang** (Von: Dominik, 24.11.;
  Prompt [Ä-046](prompts/AE-046-anpassen-beim-aufsetzen.md)). Häkchen **Windows anpassen** mit *Vorlage* (Standard
  „Clean“) und *Einstellungen …* (Dialog *Windows anpassen* im Auswahlmodus, Knopf *Übernehmen*, ohne automatische
  Anmeldung) in *OS installieren …*, *Image zurückspielen* → *Danach anpassen* und im Reiter *Automatisierung*
  (`Settings.tweak`, auch in Vorlagen, Rückfrage nennt die Auswahl). **Direktinstallation:** `install.cmd` setzt nach
  `dism` Startmenü-Richtlinie + `StartPins.json` (ab 24H2), Widgets, Sperrbildschirm und Microsoft-Benutzererfahrungen
  offline im neuen Hive (`reg load`), Marke `start-offline.ok` mit `source=setup`; Startskript auf der Setup-Partition
  (`okula/gp`, nach der Software), Aufruf zuletzt in `SetupComplete.cmd` nach dem Ende der Software-Aufgabe (höchstens
  30 min, Neustart der Software danach); Log mit Hinweis zum OEM-Schlüssel (B-013). Nicht beim Master (Audit-Modus):
  ausgegraut mit Grund. **Zurückspielen/Automatisierung:** nach der Software `jobs.send_tweak_choice` (Agent-Befehl
  `tweak`, Startskript + Offline-Teil wie *Windows anpassen*). Verlauf „Windows anpassen (Vorlage …) – wird …
  umgesetzt“, Protokoll am Gerät wie bisher, Nachlauf 30 min wie bisher. Hilfe (F1): *OS installieren* (Kapitel
  *Windows / Linux installieren*), *Image zurückspielen*, *Automatisierung*, *Windows anpassen*; TECHNIK.md („Beim
  Aufsetzen mitgeben“, Belege). Tests `tests/test_anpassen_aufsetzen.py` (neu). **Kein neuer Agent-Stick** (Agent
  unverändert; B-021 braucht ihn ohnehin). Prüfung [TESTS.md](TESTS.md) „Ä-046 Neue Maschine in einem Durchgang“.

### 24.11.2026
- **Ä-045 – Zwei Neustart-Knöpfe: „Neustart in Windows“ und „Neustart in den Agent“** (Von: Dominik, 24.11.; Prompt
  [Ä-045](prompts/AE-045-neustart-knoepfe.md)). Statt „Neu starten“ überall zwei Knöpfe mit Beschriftung
  (`uikit.power_buttons`: `reboot-windows`, `reboot-agent`, Symbol *Herunterfahren*) – unter der Geräteliste, im
  Gerätefenster, im Rechtsklick-Menü (auch VMs, `vm_actions`); ausgegraut mit Grund im Tooltip
  (`ui.reboot_why`, `update_power_buttons`). Regeln und Texte in `okula_recovery/neustart.py` (ohne GTK).
  **VM:** Startreihenfolge je Knopf eindeutig (`virsh.set_boot_runtime`: Windows = Disk zuerst + Agent abbestellt,
  Agent = Netzwerk zuerst + Agent angefordert), dann Neustart über den Agent bzw. ACPI; *Neustart in den Agent* nur mit
  Netzwerkstart. **Echte Geräte:** neuer Agent-Befehl `bootnext` (`wininstall.set_boot_next`): UEFI-BootNext einmalig
  auf den Windows Boot Manager bzw. auf BootCurrent (Stick oder Netzwerk, Rückfall Netzwerk-Eintrag); BootOrder bleibt.
  Beim Netzwerkstart zusätzlich „Agent beim nächsten Start“ gesetzt bzw. abbestellt. Nicht steuerbar (BIOS-Modus, alter
  Agent, kein Eintrag) → Rückfrage „Startziel nicht festgelegt“ mit ehrlichem Hinweis (Stick abziehen bzw. im
  Startmenü der Firmware wählen). **Nach dem Senden** (*Windows anpassen*, *Software installieren*) fragt das Tool nach
  dem Ende des Auftrags direkt „Jetzt in Windows neu starten?“ (*Neustart in Windows* / *Später*). Hilfe (F1):
  *Geräte verwalten*, Gerätefenster, *Virtuelle Maschinen*, *Windows anpassen*, *Software installieren*; Hinweis im
  Dialog *Software installieren*. Demo-Gerät kennt `bootnext`. Tests `tests/test_neustart.py` (neu), `tests/test_demo.py`.
  **Neuer Agent-Stick nötig** (`agent.py`, `wininstall.py`). Prüfung [TESTS.md](TESTS.md) „Ä-045 Neustart-Knöpfe“.
- **B-021 – Windows anpassen: Rest vor der ersten Anmeldung (Sperrbildschirm, Werbe-Platzhalter, Agent-Uhr)** (Von:
  Okuli, 24.11.; Prompt [B-021](prompts/B-021-rest-vor-anmeldung.md); Gesamttest B-020 an VM-Win11-clean ab „frisch“,
  Windows 11 Pro Build 26200). **Sperrbildschirm:** *Sperrbildschirm aus* schickt `lock_screen_off` mit
  (`wintweaks.offline_request`), der Agent (`deploy.tweak_offline`, gleicher hivexsh-Lauf) setzt
  `Policies\Microsoft\Windows\Personalization\NoLockScreen` = 1 – laut Policy CSP
  `ADMX_ControlPanelDisplay/CPL_Personalization_NoLockScreen` bei Pro, Enterprise, Education ab Windows 11 21H2 (Home
  nicht aufgeführt → Hinweis in Log und Protokoll). **Werbe-Platzhalter:** laut Microsoft Learn „dynamically delivered
  apps“; abschaltbar nur über `AllowWindowsConsumerFeatures` („redirect tiles“) bzw. `DisableCloudOptimizedContent` –
  beide nicht für Pro. *Wiederinstallation von Werbe-Apps sperren* setzt `CloudContent\DisableWindowsConsumerFeatures`
  = 1 jetzt zusätzlich offline (wirkt bei Enterprise/Education ab der ersten Anmeldung); bei Pro/Home ehrlicher Hinweis
  statt „ok“: Log des Auftrags (Edition aus dem Hive, `deploy.windows_edition`), Protokoll der Startmenü-Zeile
  (`$adsNote`) und *Wiederinstallation …*, Tooltips (*Startmenü* nennt die Platzhalter nicht mehr als entfernt) und Hilfe
  (F1): von Hand „Von Start lösen“. **Agent-Uhr:** Ursache RTC in Ortszeit (Windows), vom Live-System als UTC gelesen,
  Zeitzone Europe/Zurich rechnet nochmals dazu. Jede Anfrage des Tools trägt die Server-Uhr (`now`, `wire.send_json`
  bei `cmd`), der Agent stellt vor jedem Befehl die Systemuhr (`agent.sync_clock`, ab 5 s Abweichung,
  `clock_settime`) – Hardware-Uhr unverändert. Log-Texte „Einstellungen vor dem Windows-Start nicht gesetzt“ bzw.
  „Agent zu alt für Sperrbildschirm bzw. Werbe-Richtlinie“, Dialogtext, Demo-Gerät, Hilfe (F1) *Windows anpassen* und
  *Gerät verbinden* (Uhrzeit des Agents), TECHNIK.md (Belege, geprüfte weitere Werte). Tests
  `tests/test_rest_vor_anmeldung.py` (neu), `tests/test_offline_tweak.py` angepasst. **Neuer Agent-Stick nötig**
  (`deploy.py`, `agent.py`, `wire.py`). Prüfung [TESTS.md](TESTS.md) Abschnitt 26 „Korrektur B-021“.
- **B-020 – Windows anpassen: Startmenü und Widgets offline, gleichzeitige Startskripte** (Von: Okuli, 24.11.; Prompt
  [B-020](prompts/B-020-offline-statt-wettlauf.md); Gesamttest an VM-Win11-clean ab „frisch“ mit B-019:
  `SyncForegroundPolicy` war gesetzt, die Anmeldung kam trotzdem vor dem Okula-Skript; beide Startskripte räumten
  gleichzeitig auf). **Offline beim Senden:** *Windows anpassen* schickt für die gewählten Optionen
  (`wintweaks.offline_request`) den Teil mit, der vor der ersten Anmeldung wirken muss; der Agent
  (`deploy.tweak_offline`) liest `CurrentBuild` aus dem Hive und schreibt bei *Startmenü: Werbe-Kacheln entfernen* ab
  Build 26100 `%ProgramData%\Okula\StartPins.json`, `ConfigureStartPins` = 1 und `ConfigureStartPinsJSON` =
  `%ProgramData%\Okula\StartPins.json` (REG_EXPAND_SZ), benennt `start2.bin`/`start.bin` in **allen** Profilen um und legt
  die Marke `start-offline.ok` ab; bei *Widgets* `Policies\Microsoft\Dsh\AllowNewsAndInterests` = 0. Hive-Schreiben
  verallgemeinert (`deploy.set_hive_values`: je Schlüssel ein `setval`, alle in einem hivexsh-Lauf, vorhandene Werte
  mitgeschrieben und geprüft; Fehler → Hive unverändert, nichts umbenannt, Hinweis im Log des Auftrags). Das Startskript
  setzt die Werte weiterhin selbst; mit Marke entfallen Umbenennen und Nachholen im Nachlauf (Protokoll „Startmenü schon
  beim Senden vor dem Windows-Start zurückgesetzt …“). **SyncForegroundPolicy zurückgebaut:** wird nicht mehr gesetzt;
  eine noch gesicherte Altlast stellt das letzte Startskript (bzw. der Notfall im `.cmd`) her. **Gleichzeitige
  Startskripte:** `Restore-OkulaStart` unter dem Mutex `Global\OkulaStartRestore` (höchstens 120 s Wartezeit),
  Entscheidung „letztes Skript“ unter der Sperre; schon zurückgelegte Gruppenrichtlinie wird nicht nochmals gelöscht,
  „nicht vorhanden“ (anderes Skript war schneller) ist kein FEHLER, Hinweis bzw. FEHLER nur, wenn danach noch etwas
  übrig ist. Nachlauf-Auslöser „jetzt + 30 min“ bleibt. Log im Tool (`jobs.offline_lines`, auch „Agent zu alt“), Dialogtext,
  Hilfe (F1) *Windows anpassen* (Abschnitt „Vor dem Windows-Start“ statt „Anmeldung wartet“) und *Software installieren*,
  TECHNIK.md (Befund: Windows wartet nicht auf Startskripte). Tests `tests/test_offline_tweak.py` (neu),
  `tests/test_sync_policy.py` (allgemeines Hive-Schreiben, kein SyncForegroundPolicy mehr, Altlast),
  `tests/test_wintweaks.py`. **Neuer Agent-Stick nötig** (`deploy.py`). Prüfung [TESTS.md](TESTS.md) Abschnitt 26
  „Korrektur B-020“.
- **B-019 – Okula-Startskripte laufen parallel zur Anmeldung** (abgelöst durch B-020: Windows wartet trotz
  `SyncForegroundPolicy` nicht auf die Startskripte) (Von: Okuli, 24.11.; Prompt
  [B-019](prompts/B-019-startskript-vor-anmeldung.md); Gesamttest an VM-Win11-clean, Windows 11 Pro 25H2: Skript
  begann 15 s nach der Anmeldung, Startmenü-Richtlinie ohne Wirkung, Wetter blieb, Nachlauf ohne nächsten Lauf).
  **Hauptlösung:** Beim Ablegen eines Okula-Startskripts (*Windows anpassen*, *Software installieren*, auch nach
  *Danach anpassen* und in der Automatisierung) setzt der Agent offline im Hive `SOFTWARE`
  `Policies\Microsoft\Windows NT\CurrentVersion\Winlogon\SyncForegroundPolicy` = 1 („Beim Neustart des Computers und
  bei der Anmeldung immer auf das Netzwerk warten“) – die Anmeldung wartet, bis die Startskripte fertig sind
  (`deploy.set_sync_policy`: Kopie `SOFTWARE.okula-tmp`, `hivexsh -w`, Prüfung mit dem eigenen Leser
  `winprofile.Hive.values`, erst dann zurückschreiben; unsauberer Hive, fremder Werttyp, fehlendes hivexsh → Hive
  unverändert, Hinweis im Log des Auftrags). Stand von vorher in `GroupPolicy\SyncForegroundPolicy.okula-nachher`
  („fehlt“/„dword:N“, bleibt beim zweiten Startskript); das letzte Startskript stellt ihn in `Restore-OkulaStart` her
  (Notfall im `.cmd` mit `reg add`/`reg delete`). *Software installieren* wartet nur noch 180 s, wenn danach noch ein
  Okula-Startskript aussteht (600 s `MaxGPOScriptWait` für alle zusammen). **Nachlauf:** ist beim Anlegen schon jemand
  angemeldet (`explorer.exe` läuft), zusätzlicher einmaliger Auslöser „jetzt + 30 min“. **Startmenü:** geladene Profile
  (`Win32_UserProfile.Loaded`) werden nicht umbenannt, Hinweis „… beim Lauf angemeldet – Startmenü dort nicht
  zurückgesetzt …“; der Nachlauf holt es einmalig nach (`-StartSids`), nur wenn der Benutzer dann abgemeldet ist.
  Log im Tool (`jobs.sync_line`), Hilfe (F1) *Windows anpassen* (Abschnitt „Anmeldung wartet“) und *Software
  installieren*, TECHNIK.md. Tests `tests/test_sync_policy.py` (Hive setzen/sichern/behalten, Fehler lassen den Hive
  unverändert, Rückbau in beiden Skripten und im `.cmd`, Nachlauf-Auslöser, Startmenü, Wartezeit, Log),
  `tests/test_wintweaks.py` angepasst. **Neuer Agent-Stick nötig** (`deploy.py`, `winprofile.py`). Prüfung
  [TESTS.md](TESTS.md) Abschnitt 26 „Korrektur B-019“.
- **B-018 – Windows anpassen: Startmenü bestehender Konten, Registry-Reste beim Aufräumen** (Von: Okuli, 24.11.;
  Prompt [B-018](prompts/B-018-startmenue-bestehende-konten.md); Befund an VM-Win11-clean, Windows 11 Pro 25H2).
  **Startmenü:** *Startmenü: Werbe-Kacheln entfernen (Windows 11)* benennt ab Build 26100 nach dem Setzen der
  Richtlinie in jedem Profil (`Win32_UserProfile`, nicht `Special`, unter `C:\Users`) die gespeicherte `start2.bin`
  (und ggf. `start.bin`) in `…\StartMenuExperienceHost_cw5n1h2txyewy\LocalState` in `start2.bin.okula-<JJJJMMTT-hhmmss>`
  um (Sicherung, nicht gelöscht) – sonst hat sie bei bestehenden Konten Vorrang vor der Richtlinie. Gesperrte Datei
  oder nicht lesbare Profilliste → Hinweis in der Protokollzeile, kein FEHLER. Protokoll: „gilt für neue Konten und –
  einmalig zurückgesetzt – für bestehende: Startmenü von N Profil(en) zurückgesetzt …; eigene Anheftungen der Benutzer
  gehen dabei verloren“; gleicher Satz im Tooltip und in der Hilfe. Vor 24H2 (MDM-Bridge) und im Nachlauf kein
  Umbenennen. **Aufräumen** (`RESTORE_START`, auch *Software installieren*): Wert `Script` per
  `$entry.GetValue('Script')` statt `Get-ItemProperty` (InvalidCastException am 16-Byte-QWORD `ExecTime`); entfernt
  eigene Einträge und Altlasten (`okula-*.cmd`, das nicht mehr im Startup-Ordner liegt), löscht leere GPO-Listen und
  nummeriert die übrigen Unterschlüssel lückenlos nach (`Update-OkulaGpNumbers`; ob Windows Lücken verträgt, ist
  ungeprüft). Fehler in der Registrierung nur als Hinweis. Kein neuer Agent-Stick (nur Skript aus dem Tool). Tests
  `tests/test_wintweaks.py` (Umbenennen nur bei `START_CLEAN` ab 26100, nicht im Nachlauf; `GetValue('Script')`,
  Altlasten, Hinweis statt Abbruch). Prüfung [TESTS.md](TESTS.md) Abschnitt 26 „Korrektur B-018“.

### 19.11.2026
- **Ä-044 – Software installieren an einem Gerät mit Windows** (Von: Dominik, 19.11.; Prompt
  [Ä-044](prompts/Ä-044-software-installieren.md); Anlass: virtio-Gasttools nicht auf VM-Win11-clean installierbar).
  Neuer Eintrag **„Software installieren …“** im Rechtsklick-Menü des Geräts (unter „Windows anpassen …“), unter
  *Tools* und als Knopf im Gerätefenster; gleiche Bereitschaft wie *Windows anpassen* (Agent verbunden und aktuell,
  Windows laut Inventar, BitLocker/kein Windows → „nichts gesendet“; `devices.windows_disk` aus `ui.py` herausgelöst).
  Dialog `SoftwareInstallDialog` mit der bestehenden Liste aus der Software-Bibliothek (nur „bereit“/„nur kopieren“
  wählbar, übrige ausgegraut mit Grund; Text „beim nächsten Windows-Start“). Auftrag `jobs.software_work` (Art
  `software`, „Software installieren“ im Reiter *Aufträge* mit Fortschritt) über `jobs.send_software` – derselbe Weg wie
  *Danach anpassen* (Installer nach `ProgramData\Okula\Software`, Startskript der lokalen Gruppenrichtlinie, Protokoll
  `C:\Windows\Temp\okula-software.log`). Verlauf „Software installieren (VLC media player 3.0.24, …) – wird beim
  nächsten Start installiert“. Zusammen mit *Windows anpassen* in beiden Reihenfolgen: das zweite Skript trägt sich nur
  in `scripts.ini` ein, das zuletzt laufende stellt die Gruppenrichtlinie her (Log-Hinweis bei `shared`). Kein Neustart
  durch das Tool (wie *Windows anpassen*). Hilfe (F1) Kapitel *Software installieren* (neuer Abschnitt „An einem Gerät
  mit Windows“), Hinweise in *Windows anpassen*, Gerätefenster, *Demo-Gerät*; TECHNIK.md. Tests
  `tests/test_software_device.py` (Bereitschaft, Menüeinträge, Auftrag mit Disk und Auswahl, Skript, beide
  Reihenfolgen mit *Windows anpassen*; Dialog nur mit GTK). **Kein neuer Agent-Stick nötig** (Agent-Befehl `software`
  seit I-020 unverändert). Prüfung [TESTS.md](TESTS.md) Abschnitt 28 an VM-Win11-clean mit den virtio-Gasttools.
- **I-041 – Test-VMs mit QEMU-Gastagent** (Von: Okuli/Dominik, 19.11.; Prompt [I-041](prompts/I-041-vm-gastagent.md)).
  Option *Gastagent (nur Test-VMs)* im VM-Profil (`VmProfile.guest_agent`, Standard aus, Tooltip mit dem Grund) bei
  *Neue virtuelle Maschine* und *Hardware ändern …* (nur ausgeschaltet). Eingeschaltet: `<controller type='virtio-serial'>`
  und `<channel type='unix'>` mit `org.qemu.guest_agent.0` (Socket von libvirt); ausgeschaltet beide weg, sonst XML
  gleich – Disk/Overlay-Kette, Snapshots, Zwilling, Startreihenfolge unverändert (Tests auf dem erzeugten XML und mit
  nachgebildetem virsh). Kennzeichen *Gastagent* in der Geräteliste, im Gerätefenster „Gastagent: antwortet / keine
  Antwort“ (`Virsh.guest_ping`, im Hintergrund, Timeout 3 s, alle 30 s). Warnung „VM mit Gastagent – virtio-Treiber
  und qemu-ga sind im Image. Für Master-Images ohne Gastagent arbeiten.“ (Rückfrage, nicht gesperrt) bei *Disk-Image
  erstellen …*, *Als Master-Image markieren* und *OS installieren …* mit Audit-Modus. Gasttools (Fedora virtio-win)
  über die Software-Bibliothek: neuer Typ „virtio-win-Gasttools (Burn)“ mit `/install /quiet /norestart`, die MSI wie
  jedes MSI `/qn /norestart`. Hilfe (F1) *Virtuelle Maschinen* (Abschnitt Gastagent) und *Software installieren*,
  [VM.md](VM.md), [TECHNIK.md](TECHNIK.md), Tests `tests/test_vm_guest_agent.py`. **Kein neuer Agent-Stick nötig.**
  Prüfung [TESTS.md](TESTS.md) Abschnitt 27.
- **B-017 – Windows anpassen an Win11 24H2 Pro: Startmenü-Richtlinie und falsche FEHLER-Zeilen** (Von: Okuli, 19.11.;
  Test VM-Win11-test, Build 26100.8036). **Startmenü:** ab Build 26100 die Gruppenrichtlinie wie in `StartMenu.admx` –
  JSON als Datei `C:\ProgramData\Okula\StartPins.json` (UTF-8 ohne BOM, bleibt liegen), `ConfigureStartPins` = 1
  (DWORD) und `ConfigureStartPinsJSON` = Pfad (REG_EXPAND_SZ) unter `HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer`;
  der falsche REG_SZ-Wert aus Ä-042 wird ersetzt. MDM-Bridge nur noch vor 24H2, scheitert sie: FEHLER „Windows 11 vor
  24H2: Startmenü nur mit Geräteverwaltung“. `applyOnce` bleibt; `packagedAppId` wie in den JSON-Beispielen von
  Microsoft Learn (Tabellen dort: `packagedAppID`). **Entfernen:** nach `Remove-AppxPackage -AllUsers` wird die
  Bereitstellungsliste neu gelesen, 0x80070002/0x80070003 bei `Remove-AppxProvisionedPackage` gilt als „schon entfernt“;
  die Protokollzeile nennt die entfernten Pakete immer („X, Y entfernt; Fehler: Z: …“) – auch im Nachlauf und bei den
  Windows-Funktionen. **Widgets:** zusätzlich Richtlinie `Policies\Microsoft\Dsh\AllowNewsAndInterests` = 0 (Policy CSP
  NewsAndInterests, Pro) – Wetter weg aus der Taskleiste. **Aufräumen:** ein leerer Ordner, den Windows gerade
  verwendet, ist nur ein Hinweis; FEHLER nur, wenn `scripts.ini` bzw. die Registrierung des Startskripts bleibt (der
  Rückbau der Registrierung lief vorher an dieser Stelle nicht mehr weiter). Hilfe (F1) *Windows anpassen*, Tooltips,
  Tests `tests/test_wintweaks.py`. **Kein neuer Agent-Stick nötig.** Prüfung [TESTS.md](TESTS.md) Abschnitt 26,
  „Korrektur B-017“.

### 18.11.2026
- **Ä-042 – Windows anpassen: Win11 wirklich clean** (Von: Dominik, 18.11.; Befund: nach „alles angehakt“ standen
  WhatsApp, LinkedIn, Outlook, Adobe Express, Audiorecorder, Clipchamp, Kurznotizen, Teams im Startmenü – grösstenteils
  Platzhalter-Kacheln, nicht installiert). Neue Option **„Startmenü: Werbe-Kacheln entfernen (Windows 11)“** (Gruppe
  Explorer und Desktop): Richtlinie Policy CSP `Start/ConfigureStartPins` über die MDM-Bridge (WMI
  `MDM_Policy_Config01_Start02`, als SYSTEM; Pro ab 21H2), Ersatz ab 24H2 über den Gruppenrichtlinien-Wert
  `Policies\Microsoft\Windows\Explorer\ConfigureStartPins`; Kacheln Edge, Explorer, Einstellungen, Rechner, Editor,
  Fotos, Paint, Snipping Tool, Terminal, `applyOnce` (ab 24H2 mit KB5062660 nur einmal); Windows 10 ohne Wirkung
  (Protokoll). **16 neue App-Häkchen** (Outlook (neu)/Mail und Kalender, Teams, Clipchamp, Audiorecorder, Kurznotizen,
  To Do, Journal, Karten, Uhr (Wecker), Family, Schnellhilfe, Power Automate, Dev Home, Copilot, Widgets, Werbe-Apps
  WhatsApp/LinkedIn/Adobe Express/Spotify/Disney+/Facebook·Instagram/TikTok/Prime Video/Netflix/Candy Crush); „Bing“
  nennt Bing Search. **Schutzliste** `wintweaks.PROTECTED` (Rechner, Editor, Paint, Fotos, Snipping Tool, Terminal,
  Edge, Sicherheit, App-Installer, Frameworks, Codecs, Treiber-Apps) im Skript und per Test gegen alle Muster.
  **Nachlauf** „Später nachgeladene Apps nochmals entfernen (nach der Anmeldung)“: geplante Aufgabe (SYSTEM) 30 min nach
  der ersten Anmeldung, entfernt die gewählten Apps nochmals, löscht danach Aufgabe und Skript (läuft sie nie, löscht
  Windows sie nach 30 Tagen). Paketlisten werden nur einmal gelesen (10-Minuten-Grenze der Startskripte).
  „Wiederinstallation … sperren“: Tooltip und Protokoll ehrlich (Richtlinie nur Enterprise/Education, Edition im
  Protokoll). **Vorlage „Clean“** (Apps ausser Kamera/Store, Nachlauf, Sperren, OneDrive, Cortana, Startmenü, Tipps,
  Telemetrie, Werbe-ID, Fehlerberichte, Bing-Suche); „Player“ und „Laptop“ um neue Apps, Startmenü und Nachlauf
  ergänzt. Hilfe (F1) Kapitel *Windows anpassen*: Platzhalter-Kacheln, Clean, was bleibt. Tests `tests/test_wintweaks.py`.
  **Kein neuer Agent-Stick nötig** (Skript entsteht im Tool). Prüfung [TESTS.md](TESTS.md) Abschnitt 26.
  **Ergänzung 18.11. (Entscheid Dominik): Gruppe „Windows-Programme“** – 13 Häkchen, Standard aus und in keiner
  Vorlage: Rechner, Editor, Paint, Fotos, Snipping Tool, Terminal, Medienwiedergabe (`Microsoft.ZuneMusic`; „Groove/Filme
  & TV“ heisst jetzt „Filme & TV“ und entfernt nur noch `Microsoft.ZuneVideo`), Medien-Erweiterungen (Warnung im Tooltip)
  als Store-Apps; WordPad, Schrittaufzeichnung, Windows Media Player (klassisch), Internet Explorer 11 (auch IE-Modus),
  Math-Eingabe als Windows-Funktionen (`Remove-WindowsCapability`, Namen aus Microsoft Learn „Available features on
  demand“, WMP aus Microsoft Q&A); Editor, Paint, Snipping Tool entfernen unter Windows 10 auch die gleichnamige
  Windows-Funktion. Schutzliste zweistufig: `PROTECTED_ALWAYS` (Edge, Einstellungen, Suche, Sicherheit, App-Installer,
  Shell, Frameworks, Treiber-Apps) nie; Rechner/Editor/Paint/Fotos/Snipping/Terminal/Medienwiedergabe/Codecs nur über
  ihr eigenes Häkchen (`-Explicit`) – per Test abgesichert. Hilfe, TECHNIK, TESTS Abschnitt 26 ergänzt.
- **Ä-043 – Software-Bibliothek: alle gängigen Installer-Typen erkennen** (Von: Dominik, 18.11.; Anlass: Luminex
  Araneo 1.10.2 = Qt Installer Framework 4.6.1 nicht erkannt, Name „AraneoInstaller“, Version leer). Neuer Baustein
  `installerinfo.py` (nur lesend, ohne neue Abhängigkeit): PE-Kopf mit Abschnitten und angehängten Daten, Ressourcen
  (Versionsinfo, Manifest – auch hinter 8 MB), Qt-Ressourcen (rcc), NSIS-Kopf (deflate/LZMA), Compound File mit
  MSI-Tabelle `Property`, MSIX/APPX-Manifest. Erkannt mit Parametern: MSI, **MSP**, **MSU**, **MSIX/APPX/Bündel**,
  NSIS, **electron-builder** (`/S /allusers`), Inno Setup, InstallShield (MSI), WiX Burn, **Microsoft-Bootstrapper**
  (`/install /quiet /norestart`, 1638), **Qt Installer Framework** ab 4.0 (`install --root "<TargetDir>" …`,
  `@ApplicationsDirX64@` → `C:\Program Files`), **Advanced Installer**, **InstallAware**, **Wise**, **InstallBuilder**
  (`--mode unattended`); nur erkannt mit Hinweis („Parameter fehlt“): **InstallScript** (Antwortdatei), Qt IFW vor 4.0,
  Setup Factory, Clickteam, Smart Install Maker, Actual Installer, CreateInstall, Ghost Installer, **IExpress,
  7-Zip-SFX, WinRAR-SFX**; Squirrel weiter „nur von Hand“. Rückgabewerte je Typ (MSI 0/1641/3010, wusa 0/3010/2359302).
  **Name, Version, Hersteller** aus Versionsinfo, MSI, Qt-IFW-`config.xml`, App-Manifest bzw. NSIS-Skript; neues Feld
  `publisher`; „…Installer“/„…Setup“ fällt weg. Fenster *Software-Bibliothek*: Spalte **Hersteller** (bearbeitbar),
  Typen ausgeschrieben, unter der Liste Typ/Hersteller/Installer/Status und bei „Parameter fehlt“ **„Was tun: …“**, Knopf
  und Rechtsklick-Menü **„Neu erkennen“** (`software.redetect`; von Hand geänderte Angaben nur nach Rückfrage
  *Überschreiben*), *Bearbeiten …* mit Hersteller und Vorschlag der Erkennung; Laden auch `.msp`, `.msu`, `.msix`,
  `.msixbundle`, `.appx`, `.appxbundle`. Skript am Gerät: MSP `msiexec /p`, MSU `wusa.exe`, MSIX
  `Add-AppxProvisionedPackage -Online -SkipLicense`. Ergebnis an den 37 Installern in `Verteilen\Software` geprüft
  (Araneo → Qt IFW, „Araneo“ 1.10.2, Luminex Network Intelligence). Hilfe (F1) Kapitel *Software installieren*: erkannte
  Typen mit Parametern, „Parameter fehlt – was tun“, *Neu erkennen*. Tabelle Typen/Kennung/Parameter/Quellen in
  [TECHNIK.md](TECHNIK.md) (Quellen aus dem Gedächtnis, „nicht abgerufen“). Tests `tests/test_installerinfo.py`.
  **Kein neuer Agent-Stick nötig.** Prüfung [TESTS.md](TESTS.md) Abschnitt 25 (Teil Ä-043).
- **Ä-041 – Software-Bibliothek im Tool (statt Ordner `Verteilen\Software`)** (Von: Dominik, 18.11.): Neuer Eintrag
  **Extras → „Software-Bibliothek …“**: oben **„Ins Tool laden …“** (`.exe`/`.msi`), **„Ordner laden …“** (Installer mit
  Dateien daneben, z. B. `YSUSB_V213_Win/setup.exe`; bei mehreren Installern Rückfrage) und Ziehen und Ablegen, Kopie mit
  Fortschritt und *Abbrechen* (erst `.…partial`, nichts Halbes); darunter die Liste mit Programm, Version, Typ, Parameter,
  Rückgabewerte, Status, Grösse – direkt in der Zeile bearbeitbar, Art und Installer über *Bearbeiten …*, *Löschen* mit
  Rückfrage, Suchfeld. Ablage NAS `Software-Bibliothek/<key>-<version>/` mit Beschreibung `.okula.json` (Format von
  I-020, dazu SHA-256 des Inhalts und Herkunft). Gleicher Inhalt → „schon in der Bibliothek“, nicht doppelt; neue Version
  übernimmt die Parameter der vorigen (`_adopt`), die alte bleibt bis zum Löschen. Die Auswahl *Software installieren*
  (OS installieren, *Danach anpassen*, Automatisierung) liest nur noch die Bibliothek; gespeicherte Auswahlen werden über
  den `key` aufgelöst, sonst „fehlt in der Bibliothek“. Knopf *Software …* im Reiter *Dateien* entfernt (ein Ort).
  Beim Verbinden mit dem NAS löscht das Tool in `Verteilen\Software` nur die I-020-Beschreibungen
  `.<Name>.okula.json` (Statuszeile, stderr). Demo: Beispiel-Einträge in der Bibliothek des Demo-Speichers. Hilfe (F1):
  Kapitel „Software installieren“ neu (Laden, Parameter, neue Version, Ablage), Hinweise in *Ordner senden*, *Windows /
  Linux installieren*, *Demo-Gerät*, Überblick. Tests `tests/test_software.py`. Übertragung ans Gerät unverändert
  (Ablage am Gerät jetzt `ProgramData\Okula\Software\<Eintrag>\…`). **Kein neuer Agent-Stick nötig.** Prüfung
  [TESTS.md](TESTS.md) Abschnitt 25.

### 17.11.2026
- **B-016 – Agent-Stick: GRUB meldet „file `/boot/grub/font.pf2' not found“** (Von: Dominik, 17.11.):
  `GRUB_CFG` in `stick.py` prüft vor jedem `loadfont` mit `[ -f … ]`, ob die Schrift da ist (zuerst
  `/boot/grub/font.pf2`, sonst `$prefix/fonts/unicode.pf2`), verschachtelte `if` statt `elif loadfont`. Grafisches Menü
  mit Okula-Logo unverändert. Netzwerkstart (`pxe.py`) lädt keine Schrift – keine Änderung nötig. Test
  `test_grub_cfg_font_only_if_present`. **Neuer Agent-Stick nötig.** Prüfung [TESTS.md](TESTS.md) Abschnitt 24.
- **I-020 – Software aus `Verteilen\Software` automatisch installieren** (Von: Claude/Dominik, 31.10., neu
  ausgerichtet 17.11.): Neue Liste **„Software installieren“** (Häkchen, Suchfeld, Programm, Version, Grösse, Status,
  Gesamtgrösse) in *OS installieren …* (Windows, auch mit *Für Master-Image (Audit-Modus)* → landet im Master),
  *Image zurückspielen* unter *Danach anpassen* und im Reiter *Automatisierung* (Schritt *Anpassen*,
  `Settings.install_software`, auch in Vorlagen). Katalog `software.py`: `.exe`/`.msi` und Unterordner in
  `Verteilen\Software` erscheinen von selbst; versteckte Beschreibung `.<Name>.okula.json` (Typ, Parameter,
  Rückgabewerte, Art, SHA-256); Erkennung MSI, NSIS, Inno Setup, InstallShield, WiX Burn, Squirrel → „nur von Hand“,
  sonst „Parameter fehlt“ (nicht wählbar); neue Version übernimmt die Parameter der alten. Pflege im Reiter *Dateien* →
  **Software …** (Art, Installer im Ordner, Parameter, Rückgabewerte; Sammelordner „nur kopieren“). Am Gerät:
  Installer nach `C:\ProgramData\Okula\Software`, Startskript der lokalen Gruppenrichtlinie (wie I-039) legt eine
  einmalige geplante Aufgabe als SYSTEM an (keine 10-Minuten-Grenze), Installation still nacheinander, Protokoll
  `C:\Windows\Temp\okula-software.log`, Installer danach gelöscht, bei 3010 ein Neustart am Schluss. Neuer
  Agent-Befehl `software` (Zurückspielen, Automatisierung); Direktinstallation über die Setup-Partition, `install.cmd`
  und `SetupComplete.cmd`. Startskripte von Software und *Windows anpassen* können gleichzeitig ausstehen. Log und
  Verlauf „Software: … (wird beim ersten Start installiert)“. Demo-Gerät mit drei Beispiel-Installern. Hilfe (F1):
  neues Kapitel „Software installieren“, Verweise in *Image zurückspielen*, *Automatisierung*, *Windows / Linux
  installieren*, *Demo-Gerät*. Details [TECHNIK.md](TECHNIK.md), Tests `tests/test_software.py`. **Neuer Agent-Stick
  nötig.** Prüfung: [TESTS.md](TESTS.md) Abschnitt 23.
- **Ä-040 – Master-Image: Einstellungen des Administrators aus dem Audit-Modus übernehmen** (Von: Dominik, 17.11.;
  Befund Master CompactPlayer: Desktop-Anordnung, Explorer und Taskleiste fehlten den Benutzern). Neues Häkchen
  **„Einstellungen des Administrators übernehmen (Master)“** im Dialog *Image zurückspielen* unter *Danach anpassen*
  und in der Automatisierung (Schritt *Anpassen*, `Settings.copy_profile`, auch in Vorlagen), Standard an, Tooltip.
  Antwortdatei: `CopyProfile=true` in specialize (`master_unattend(…, copy_profile)`), ohne Option unverändert.
  Agent (`winprofile.py`, Befehl `customize` mit `copy_profile`, nur generalisiertes Windows): Quellprofil
  Administrator (sonst einziges mit Pins, nie Default/Public), Pins aus `User Pinned\TaskBar\*.lnk`, Reihenfolge und
  Store-Apps aus `Taskband\Favorites` (eigener regf-Leser, nur lesend; sonst nach Datum), Explorer/Edge über
  `DesktopApplicationID`, übrige über Startmenü-Verknüpfungen für alle (vorhandene oder Kopie unter `Programs\Okula`)
  → `LayoutModification.xml` (`PinListPlacement="Replace"`) im Standardprofil und im Administrator-Profil, vorhandenes
  Startlayout bleibt. Log „Einstellungen des Administrators werden übernommen – Taskleiste: …“, alter Agent → „Agent zu
  alt“. Demo-Gerät simuliert. Startmenü-Kacheln und Windows 11 offen (Begründung [TECHNIK.md](TECHNIK.md)). Hilfe (F1)
  Kapitel *Master-Image*, *Automatisierung*, *Image zurückspielen*; Doku [MASTER-IMAGE.md](MASTER-IMAGE.md). Neue
  Tests `tests/test_copyprofile.py`. **Neuer Agent-Stick nötig.** Prüfung: [TESTS.md](TESTS.md) Abschnitt 22.
- **I-037 – Grafikkarte im Inventar und im Gerätefenster** (Von: Dominik, 11.11., hochgestuft 17.11.; Anlass Master
  CompactPlayer mit NVIDIA GeForce GT 740, Video-Server mit mehreren GPUs). Agent: `inventory.gpus()` (Schlüssel
  `gpus` in `collect()`) erfasst PCI-Klasse `03xx` mit Adresse, IDs, Hersteller-/Modell-/Subsystem-Namen und Treiber
  über `lspci -vmm -nn -D -k`, ohne `lspci` aus `/sys/bus/pci/devices` plus `pci.ids` (ohne Datenbank nur IDs);
  HDMI-Audio (`04xx`) zählt nicht. `pciutils` in `stick.BUNDLED_PACKAGES` (Agent-Stick und Netzwerkstart; `pci.ids`
  über `libpci3`). Übersicht: Zeile „Grafikkarte“ bzw. „Grafikkarte 1/2/…“ nach PCI-Adresse, z. B. „NVIDIA GeForce GT
  740 (GK107)  (0000:01:00.0)“, Tooltip mit IDs, Hersteller der Karte und Treiber; altes Inventar → keine Zeile.
  Demo-Gerät mit Intel Iris Xe. Digitaler Zwilling: nur Hinweis und Vorschauzeile (✖), VM-Hardware unverändert.
  Kein VRAM (ohne Treiber nicht zuverlässig). Hilfe (F1) Kapitel Gerätefenster, Glossar „Inventar“ und Zwilling
  ergänzt. Neue Tests `tests/test_inventory_gpu.py`. **Neuer Agent-Stick nötig.** Prüfung: [TESTS.md](TESTS.md)
  Abschnitt 21.
- **B-015 – Windows-Direktinstallation: Gerät startete nach der Installation wieder die Setup-Partition**
  (Von: Dominik/Okuli, 17.11.; CompactPlayer 1, AMI-Firmware 2014: Firmware-Eintrag „UEFI OS“ der Setup-Partition vor
  `{bootmgr}`, `install.cmd` lief ein zweites Mal). `install.cmd` setzt nach `bcdboot` den Windows Boot Manager an die
  erste Stelle (`bcdedit /set {fwbootmgr} displayorder {bootmgr} /addfirst`), `bcdedit /enum firmware` vorher und
  nachher sowie der Rückgabewert ins `install.log`; Fehler nur protokolliert, kein Abbruch. Keine zusätzliche
  `bcdboot`-Option (Standard ist schon „zuerst“), Einträge der Setup-Partition werden bewusst nicht entfernt
  (Begründung in [TECHNIK.md](TECHNIK.md), „Startreihenfolge nach der Installation“). Hilfe (F1) unverändert (beschreibt
  die Startreihenfolge nicht). Neuer Test `test_install_cmd_boot_order`. **Kein neuer Agent-Stick.** Prüfung:
  [TESTS.md](TESTS.md) Abschnitt 20.
- **B-014 – Windows-Direktinstallation: Windows-Partition nicht gefunden, wenn auf der Disk schon ein Windows lag**
  (Von: Dominik/Okuli, 17.11.; CompactPlayer 1, Installation 421a8299: C: in Windows PE mit altem Inhalt, Bezeichnung
  „Windows“, ohne Markierung). Agent: nach dem Partitionieren auf allen vier Partitionen `wipefs -a` und Anfang
  (16 MiB) und Ende (1 MiB, NTFS-Backup-Bootsektor) mit Nullen (`O_DIRECT` + `fsync`), ext4-Zwischenablage ohne
  Discard (`-E nodiscard`), vor `mkntfs` erneut löschen; nach `mkntfs` + Markierung Prüfung direkt von der Disk
  (`sync`, `blockdev --flushbufs`, `drop_caches`, `blkid -p` = ntfs „OKULAWIN“, Markierung nur lesend eingehängt) –
  sonst Abbruch „Schreiben auf die Disk wird nicht übernommen – Disk prüfen“ ohne BootNext/Neustart. `install.cmd`:
  Markierung, sonst genau ein Laufwerk „OKULAWIN“, sonst Fehler; altes Windows wird nie formatiert. Ursache
  (belegt/vermutet, Quellen) in [TECHNIK.md](TECHNIK.md), „Betriebssystem direkt auf ein Gerät installieren“. Hilfe
  (F1) *Windows / Linux installieren* → „Fehler am Gerät“. Neue Tests: Löschen auf Probe-Dateien (inkl. mkntfs ohne
  root), Prüfung nach dem Schreiben, Ablauf `install()`, kein Neustart im Fehlerfall, `install.cmd`-Text.
  **Agent betroffen – neuer Agent-Stick nötig.** Prüfung: [TESTS.md](TESTS.md) Abschnitt 20.
- **Ä-039 – Windows-Direktinstallation: Fehler am Gerät besser erkennbar** (Von: Dominik, 12.11.; mit B-014):
  Im Fehlerfall schreibt `install.cmd` die Laufwerksliste (`diskpart` → `list volume`) und je Laufwerk C–Z
  Markierung ja/nein und `dir` (Bezeichnung, Inhalt, freier Platz) ins `install.log`, dazu die nicht vorhandenen
  Laufwerke. Oben im Editor ein Kasten: „Nach dem Schliessen dieses Fensters schaltet sich das Geraet aus. Fuer eine
  Eingabeaufforderung vorher Shift+F10 druecken.“ plus Ausweichweg über *Datei → Öffnen* →
  `X:\Windows\System32\cmd.exe`. Ob Shift+F10 in diesem Zustand wirkt, ist am Gerät zu prüfen.
- **I-039 – Windows anpassen …** (Von: Dominik, 17.11.; Optionen aus dem TGF-TuningPack 4.3): Neue Funktion wie
  *Ordner senden* – Menü *Tools* und Rechtsklick auf das Gerät „Windows anpassen …“ (unter „Ordner senden“), Knopf
  im Gerätefenster. Dialog mit Vorlage (*Player*, *Laptop*, *Keine*; danach einzeln änderbar, „Vorlage: Player
  (geändert)“) und Häkchen in den Gruppen Apps (11 Store-App-Gruppen, Wiederinstallation sperren, OneDrive, Cortana),
  Updates, Betrieb, Datenschutz, Explorer und Desktop, Dienste, Anmeldung (automatische Anmeldung mit Benutzername/
  Passwort – ohne beide kein *Senden*, Hinweis Klartext in der Registrierung). Das Tool erzeugt ein PowerShell-Skript
  (`wintweaks.py`, je Option ein Baustein mit try/catch, Store-Apps zuletzt, „alle Benutzer“ = alle Profile und
  Standardprofil); neuer Agent-Befehl `tweak` legt es als **einmaliges Startskript der lokalen Gruppenrichtlinie** ab
  (`deploy.install_startup_script`: `scripts.ini`/`gpt.ini` ergänzt, Version erhöht, Originale als `*.okula-nachher`).
  Beim nächsten Start läuft es als SYSTEM vor der Anmeldung, löscht sich und den Startmechanismus zuerst (Notfall-
  Aufräumen in der `.cmd`, falls PowerShell nicht startet), dann die Einstellungen; Protokoll
  `C:\Windows\Temp\okula-windows-anpassen.log` ohne Passwort. Schnellstart/Ruhezustand → Meldung wie bei *Ordner
  senden*; kein Windows → Meldung, nichts gesendet. Auftrag „Windows anpassen“, Verlauf mit Kurzform der Auswahl.
  Demo-Gerät meldet „fertig“. Hilfe: neues Kapitel „Windows anpassen“, Gerätefenster und Demo-Gerät ergänzt.
  Details [TECHNIK.md](TECHNIK.md), Tests `tests/test_wintweaks.py` (Skript je Option und Vorlage, Passwort, Aufräumen,
  Startmechanismus auf Probe-Verzeichnis mit vorhandener Richtlinie, Ablehnung ohne Windows/bei Schnellstart, Auftrag,
  „Agent zu alt“), `tests/test_deploy.py` (Loop-Disk, root), `tests/test_demo.py`; Prüfung [TESTS.md](TESTS.md)
  Abschnitt 19. **Neuer Agent-Stick nötig.** Kombination mit *Danach anpassen*, Direktinstallation und
  Automatisierung folgt später.

### 12.11.2026
- **I-038 – Windows-Direktinstallation „Für Master-Image (Audit-Modus)“** (Von: Dominik, 12.11.; Anlass: Master-Image
  für CompactPlayer): Neues Häkchen im Dialog *OS installieren …* (nur Windows, Standard aus, `WinOptions.audit_mode`).
  Windows wird wie bisher ohne Eingriff installiert und startet danach im **Audit-Modus**. Konto, Benutzername,
  Passwort, Windows-Schlüssel und Computername ausgegraut und ignoriert (Audit hat Vorrang, keine Kontonamen-Prüfung);
  Region, Datenschutz und BitLocker bleiben wählbar. Antwortdatei: specialize wie bisher plus Region
  (International-Core, weil Reseal/Audit alle übrigen oobeSystem-Einstellungen ignoriert); **auditUser** RunSynchronous:
  `SetupComplete.cmd` (Setup-Partition weg, C: gross – ob es im Audit-Modus von selbst läuft, belegt Microsoft
  nicht), dann `Panther\unattend.xml` löschen (sofort und abgekoppelt nach 2 min erneut); **oobeSystem** nur
  `Reseal/Mode=Audit`. Log: Zusammenfassung und nächste Schritte (Sysprep, Disk-Image, als Master markieren);
  Verlauf „Windows-Installation … für Master-Image (Audit-Modus) → …: vorbereitet …“. Ohne Häkchen ist die
  Antwortdatei unverändert (Strukturtest). `master_unattend`/`deploy.py` unverändert. Hilfe: Kapitel „Master-Image“
  und „Windows / Linux installieren“ (inkl. Snapshot vor Sysprep bei VMs). Doku [MASTER-IMAGE.md](MASTER-IMAGE.md),
  [TECHNIK.md](TECHNIK.md); Tests `AuditModeTest`, `DirectUnchangedTest` (`tests/test_winunattend.py`),
  `tests/test_winsetup.py`; Prüfung [TESTS.md](TESTS.md) Abschnitt 17. Kein neuer Agent-Stick.
- **B-012 – Windows-Konto „Benutzer“ bricht die Einrichtung ab** (Von: Dominik, gemeldet 12.11.; VM-Zwilling
  „VM-CompactPlayer-1“, `setuperr.log`: „UserAccounts: failed to create user account 'Benutzer' (0x80070563)“, danach
  OOBE-Neustart-Schleife): In deutschem Windows heisst die eingebaute Gruppe Builtin\Users „Benutzer“. Standardname
  jetzt **„Okula“** (`WinOptions.local_account`, Vorbelegung „Benutzername“ in beiden Dialogen – Boot-Stick und
  „OS installieren …“ – aus `WinOptions`). Neue Prüfung `winunattend.pruefe_kontoname(name)` (Meldung oder `None`):
  reservierte Namen von Gruppen und eingebauten Konten deutsch/englisch (`RESERVED_ACCOUNT_NAMES`, ohne
  Gross-/Kleinschreibung, nach `strip()`), mehr als 20 Zeichen, Punkt am Ende, Zeichen `" / \ [ ] : ; | = , + * ? < >`.
  Leer bleibt erlaubt (kein Konto in der Antwortdatei, Windows fragt beim ersten Start selbst). „OS installieren …“:
  Meldung in der Prüfliste unter der Disk, *Installieren* gesperrt, zusätzlich Abbruch beim Bestätigen
  („Nicht gestartet: …“); leer → Hinweis. Boot-Stick: Prüfung beim Start, Fehlerfenster „Benutzername nicht
  möglich“ und Log-Zeile, Stick wird nicht gelöscht. Keine stille Korrektur, Gruppe bleibt `Administrators`.
  Hilfe: Kapitel „Windows / Linux installieren“ (Abschnitt Windows-Konto) und „Sticks erstellen“. Details
  [TECHNIK.md](TECHNIK.md), Tests `KontonameTest` in `tests/test_winunattend.py`, Prüfung [TESTS.md](TESTS.md)
  Abschnitt 16. Kein neuer Agent-Stick (winunattend läuft nur auf dem Server).

### 11.11.2026
- **B-011 – Hardware-Test meldet Prozessor-Fehler seit dem Start** (Von: Dominik, gemeldet 11.11.; SRV-002: CPU 3
  meldet jede Sekunde korrigierte MCE, Bank 0, gründlicher Test 10.11. trotzdem „ok, mce 0“): „CPU unter Last“ wertet
  jetzt alle Machine-Check-Meldungen seit dem Start aus. Kernel-Protokoll ohne `journalctl -g` gelesen
  (`journalctl -k -b -o short-monotonic`, sonst `dmesg`), in Python gefiltert, Rückgabewert/Fehler geprüft; liefert
  keine Quelle Daten → Detail „Hardware-Fehler nicht prüfbar“ statt stillschweigend 0. Ereignisse (`CPU n: Machine
  Check … Bank b: <Status>`, „Machine check events logged“ = ohne Zuordnung) nach CPU, Bank und Art (Bit 61:
  korrigiert/nicht korrigiert) gruppiert, je Gruppe Anzahl und bis 3 Beispielzeilen. Neu während der Last oder nicht
  korrigiert → rot; nur vor dem Test → gelb „Hardware-Fehler seit dem Start gemeldet (CPU 3, Bank 0: 12 Mal) –
  BIOS-Update bzw. Prozessor prüfen“; Temperatur/Drosselung unverändert, der schlechtere Status gilt. `values`: `mce`
  (neu), `mce_boot`, `mce_groups`. Gilt für Schnelltest und Gründlich; Gerätefenster und PDF zeigen Kurztext und
  Details wie bisher; Demo-Agent unverändert. Nur echte Fehlerzeilen zählen (Startmeldungen wie „mce: CPU supports 10
  MCE banks“ nicht). Ursache für „mce 0“ trotz Fehlern am Stick nicht am Gerät nachgeprüft:
  PCRE2 fehlt kaum (Debian-`grep` hängt von `libpcre2-8-0` ab), Foto (11.11.) und Test (10.11.) stammen aus
  verschiedenen Starts; `-g`/PCRE2 als Fehlerquelle entfällt jetzt ohnehin, „nicht prüfbar“ wird sichtbar. Hilfe: Kapitel „Hardware-Test“. Details [TECHNIK.md](TECHNIK.md), Tests
  `MceTest` in `tests/test_hwtest.py`, Prüfung [TESTS.md](TESTS.md) Abschnitt 15. **Neuer Agent-Stick nötig.**

### 10.11.2026
- **B-009 – Tests grün auch als normaler Benutzer** (Von: Okuli, gemeldet 10.11.): Vier Tests in `test_imaging`/
  `test_jobs` scheiterten ohne `/usr/sbin` im PATH an „No such file or directory: 'sfdisk'“. Neues Hilfsmodul
  `okula_recovery/systools.py` mit `SBIN_DIRS`, `find_tool()` (zuerst PATH, dann `/usr/local/sbin`, `/usr/sbin`,
  `/sbin`) und `resolve()` (Befehl mit vollem Programmpfad); `clonezilla.py` nutzt es statt der eigenen Kopie.
  `imaging.py` sucht alle Werkzeuge darüber (Verfügbarkeit `tool_status`, partclone-Variante, zstd, pigz,
  Restore-Prüfung) und startet sfdisk, partclone, wipefs, partx, udevadm, mkswap, blkid, lsblk mit vollem Pfad; im
  Plan bleibt der Programmname ohne Pfad (das Tool liest daraus die partclone-Variante). `systools.py` gehört zu
  den Agent-Modulen. Tests mocken `imaging.find_tool` statt `shutil.which`; RealPartcloneTest wird übersprungen,
  wenn `/var/log/partclone.log` nicht beschreibbar ist („… (Test braucht root)“); neu `FindToolTest`. Im Betrieb
  (root, sbin im PATH) keine Änderung; neuer Agent-Stick nicht nötig (optional). `usbtools.find_tool` (eigene
  Liste inkl. `/usr/bin`, `/bin`) bewusst nicht umgestellt.
- **B-008 – Projektübersicht im Dunkelmodus: Auswahlfelder kaum lesbar** (Von: Okuli, gemeldet 10.11.): `style.css`
  setzte Farben per `prefers-color-scheme: dark`, aber kein `color-scheme` → Firefox zeichnete `<select>` und die
  aufgeklappte Liste mit hellen Systemfarben, die Schrift war hell (hell auf hell). Neu: `color-scheme: light dark`
  auf `:root` (im Dunkel-Block `dark`), `option`/`optgroup` mit `var(--card)`/`var(--text)`; nur im Dunkelmodus
  zusätzlich Platzhaltertext, deaktivierte Felder, Fokusrahmen, Häkchen (`accent-color`) und Scrollbalken in den
  Farben der Seite. Hellmodus unverändert, kein Umbau, keine neuen Texte, Hilfe unberührt. Kein neuer Agent-Stick.
  Test: [TESTS.md](TESTS.md) Abschnitt 12.
- **Ä-038 – Agent-Stick: Meldung „fertig, jetzt abziehen“ und Prüfung am Schluss** (Von: Dominik/Okuli, gemeldet
  10.11., Anlass B-010): Nach `sync` hängt der Root-Helfer den Stick schreibgeschützt neu ein und prüft
  (`stick.verify_stick`): `live/okula-agent.squashfs` > 0 Byte mit Squashfs-Kopf `hsqs`, `live/filesystem.squashfs`
  so gross wie im ISO, Kernel und initrd vorhanden, beim Restore-Stick das Image auf der Datenpartition. Fehler →
  `ERROR Prüfung am Schluss fehlgeschlagen: …` statt `DONE`. Gerät weg oder E/A-Fehler beim Bau → „Stick wurde
  während des Schreibens abgezogen – Stick neu erstellen.“ (`stick.explain_unplugged`). Am Ende Fenster
  „Agent-Stick fertig“/„Restore-Stick fertig“ („Der Stick kann jetzt abgezogen werden.“, OK) bzw. rot „Stick nicht
  fertig“ mit Grund und „Stick nicht verwenden – neu erstellen.“ (Schliessen); während des Baus Hinweis unter dem
  Balken „Stick erst abziehen, wenn „Stick fertig“ erscheint.“ *Boot-Stick aus ISO …* endete ebenso unauffällig
  (nur Balkentext) → gleiches Fenster („Boot-Stick fertig“), ohne Datei-Prüfung. `uikit.confirm_error` kann Titel
  und roten Text; Knopf heisst überall „Schliessen“ (vorher GTK-Standard). Neu `uikit.info`. Hilfe: Kapitel
  *Erste Schritte* und *Sticks erstellen*. Kein neuer Agent-Stick. Tests: [TESTS.md](TESTS.md) Abschnitt 14.
- **B-010 – Agent-Stick startete am Videoserver-PC (SRV-002) nicht** (Von: Dominik, gemeldet 10.11.): live-boot
  „Can not mount /dev/loop1 (…/live/okula-agent.squashfs)“ → BusyBox-Shell. Ursache (Okuli): Der Stick war unvollständig –
  `okula-agent.squashfs` 0 Byte; Kernel-Protokoll: Stick-Bau 09:31:13 gestartet, Stick 09:31:37 abgezogen („lost async
  page write“). Netzwerkstart klappte (Supermicro X11SSV-Q, i5-6600T, BIOS 2.0 von 2016). Stick neu erstellt → Start
  am Gerät ok (Dominik). Kein Code-Fehler; dass der Abbruch unbemerkt blieb, behebt Ä-038. Nebenbefund: CPU 3 meldet
  laufend korrigierte Machine-Check-Fehler (Bank 0) – Hardware/BIOS des Geräts, Empfehlung BIOS-Update; Anzeige im
  Tool: I-036.
- **Ä-007 – Bestätigung beim Einschalten der Automatisierung** (Von: Claude, Laien-Test 31.10.): Wer die
  Automatisierung von Hand einschaltet (Häkchen *Auto* in der Geräteliste oder Schalter im Reiter *Automatisierung*),
  sieht zuerst eine rote Zusammenfassung (`automation.confirm_summary`): Disk, die gelöscht wird, Image (Master/eigenes,
  Anzeigename wie im Reiter), Gerätename danach (mit Windows-Name), Backup vorher, bei VMs Snapshot vorher, Abschluss,
  bei „Nach 3 Tagen wieder einschalten“ der Hinweis darauf. Verbunden: Knopf „Löschen und neu aufsetzen“, Satz zum
  30-s-Countdown; nicht verbunden: Knopf „Einschalten“, Satz zum nächsten Verbinden. *Abbrechen* ist Standard und lässt
  alles aus (nichts gespeichert, kein Verlaufseintrag). Unvollständige Einstellungen → Fehlermeldung statt Rückfrage –
  jetzt auch beim Schalter im Reiter (vorher liess er sich unvollständig einschalten). `uikit.confirm` kann den Text
  rot zeigen (`red=True`). Ausschalten, Wieder-Einschalten nach 3 Tagen und Stopp-Knopf ■ ohne Rückfrage; Vorlage
  anwenden ändert `enabled` nicht. Hilfe (Kapitel Automatisierung, Aufbau des Fensters, Spalte „Auto“) ergänzt, Tests
  `ConfirmSummaryTest`. Kein neuer Agent-Stick; am Server `git pull && sudo ./install.sh`, Tool neu starten.
  Test: [TESTS.md](TESTS.md) Abschnitt 5.
- **B-007 – Anpassen an kleinere Disk: belegte Blöcke im partclone-Kopf richtig lesen** (Von: Okuli, gemeldet
  10.11.): partclone-Kopf Format 0002 hat bei grossen Images `usedblocks = 0`; `shrink.parse_pcl_header` las nur dieses
  Feld → „belegt 0.0 GB … Anpassen: möglich“ beim 1-TB-Image. Jetzt: bei `usedblocks = 0` gilt das Feld danach
  (`used_bitmap`, wenn > 0 und ≤ `totalblock`); beide 0 oder unplausibel (auch `usedblocks` > `totalblock`) →
  „Belegter Platz im Image nicht lesbar – Anpassen nicht möglich“. Format 0001 unverändert. Ä-002-Prüfung (`plan`) und
  Ä-037-Platzprüfung (`used_bytes`) nutzen denselben Weg; `used_bytes` fällt bei unlesbarem Kopf wie bisher auf die
  Grösse der Image-Datei zurück. Tests mit nachgebauten echten Köpfen (`tests/test_shrink.py`). Kein neuer Agent-Stick;
  am Server `git pull && sudo ./install.sh`, Tool neu starten. Test: [TESTS.md](TESTS.md) Abschnitt 13.
- **Ä-037 – VM-Disk beim Zurückspielen vergrössern** (Von: Dominik): Ist die Disk einer VM kleiner als die Quelldisk
  des Images, zeigt *Image zurückspielen …* zwei Optionsfelder: „VM-Disk auf <N> GB vergrössern und zurückspielen“
  (Standard, N = Quelldisk aufgerundet auf ganze GB) und „Image an die kleinere Disk anpassen“ (Ä-002, nur wenn die
  Prüfung „lässt sich anpassen“ meldet). Vergrössern ausgegraut mit Grund bei Snapshots oder zu wenig Platz im Pool
  `okula` (belegte Daten des Images + 10 %, mind. 10 GB). Ein Auftrag mit 4 Schritten: VM herunterfahren (sauber,
  nach 60 s hart) → Disk vergrössern (`Virsh.set_profile`) → Einschalten und Agent starten (wartet auf einen *neuen*
  Agent, prüft die Grösse der Zieldisk) → ggf. Vorher Snapshot (erst jetzt) → Zurückspielen. Verlauf „VM-Disk von
  128 GB auf 513 GB vergrössert“. Profil **VM-Win11 jetzt 256 GB** („Okula NVMe SSD 256GB“); bestehende VMs bleiben.
  Echte Geräte unverändert. Hilfe (Kapitel „Image zurückspielen“, „Virtuelle Maschinen“), Details
  [TECHNIK.md](TECHNIK.md) und [VM.md](VM.md), Prüfung [TESTS.md](TESTS.md) Abschnitt 13. Kein neuer Agent-Stick.
- **I-034 – Projektübersicht im Tool** (Von: Dominik): *Extras → Projektübersicht …* startet einen Webserver nur auf
  127.0.0.1 (freier Port, Token in der URL) und öffnet die Seite in Firefox. Liest bei jedem Laden `docs/` des Repos
  (TESTS.md offen + Vorbereitung, Bugs/Änderungen/Ideen, Kurzübersicht, Entscheidungen, Übergabe-Punkte, Prompts mit
  Status); Tests abhaken (ok/Fehler) und kommentieren, Kommentar/Prio-/Status-Wunsch zu jedem Eintrag, neue Notizen,
  Übersicht mit Zählern, Suche und Filter. Rückmeldungen in `~/.local/share/okula-recovery/projekt-rueckmeldungen.json`
  (0600, atomar, defekte Datei beiseitegelegt); verwaiste Rückmeldungen unter „Rückmeldungen ohne Eintrag“.
  Projektordner unter *Menü → Einstellungen …*. Hilfe-Kapitel „Projektübersicht“. Details [TECHNIK.md](TECHNIK.md),
  Prüfung [TESTS.md](TESTS.md) Abschnitt 12. Kein neuer Agent-Stick.

### 06.11.2026
- **I-001 – Virtuelle Maschinen im Tool erledigt** (Von: Dominik, alle 4 Aufträge am 06.11.2026): VM-Grundlage mit
  Nacharbeit 1b, VMs im Tool, Digitaler Zwilling (mit Ä-036), Snapshots. Konzept, Entscheide und Abweichungen:
  [VM.md](VM.md); Prüfungen im Tool offen: [TESTS.md](TESTS.md) Abschnitte 8–11.
- **I-001 Auftrag 4 – Snapshots der VMs** (Von: Dominik): Reiter **„Snapshots“** im Gerätefenster einer VM – Liste
  (Titel, Datum, automatisch, Grösse, „◀ aktueller Stand“), *Snapshot erstellen …*, *Zurück zu diesem Snapshot …*
  (Rückfrage „Alle Änderungen seit … gehen verloren“), *Löschen …* (mit Fortschritt), alles nur bei ausgeschalteter
  VM; Platzwarnung unter 50 GB frei. Häkchen **„Vorher Snapshot“** (nur VMs, Standard an) in *Image zurückspielen*,
  *OS installieren* und in der Automatisierung: Snapshot direkt vor dem Auftrag bei laufendem Agent, schlägt er fehl,
  startet nichts. Verlauf „Snapshot ‚…‘ erstellt / zurückgesetzt / gelöscht“. Zurückspringen stellt das Vor-Inventar
  und Ä-036 („Disk leer“) wie zum Zeitpunkt des Snapshots her. *VM löschen …* entfernt alle Overlays; *Hardware
  ändern …* sperrt Disk vergrössern bei Snapshots. **Technik** (Entscheid oben, Details [VM.md](VM.md)): externe
  qcow2-Overlays im Pool-Verzeichnis, Liste in den VM-Metadaten, Löschen per block-stream in einer Hilfs-VM (libvirts
  block-commit scheitert an AppArmor), NVRAM/TPM bleiben. **Abweichungen:** keine libvirt-Snapshot-Metadaten, Löschen
  nur ausgeschaltet, Twin-Bestücken ohne Snapshot. Hilfe: Abschnitt „Snapshots“ im Kapitel „Virtuelle Maschinen“,
  Häkchen in „Image zurückspielen“, „Windows / Linux installieren“, „Automatisierung“. Tests
  `tests/test_vm_snapshots.py`, `tests/test_automation.py`. Am Server mit Probe-VMs (BIOS und UEFI + Secure Boot +
  TPM) geprüft ([TESTS.md](TESTS.md), Abschnitt 11 für den Ablauf im Tool). Kein neuer Agent-Stick.
- **I-001 Auftrag 3 – Digitaler Zwilling** (Von: Dominik): **„VM mit dieser Hardware erstellen …“** im Gerätefenster
  (oben rechts) und im Rechtsklick auf ein Gerät (nicht für VMs/DEMO-PC, ohne Inventar ausgegraut).
  `vm.profile_from_inventory`: Firmware aus der Partitionstabelle der Systemdisk, Secure Boot/TPM, Disk (Grösse,
  SATA/NVMe, Modell), CPU-Name und Kerne (≤ Server-Kerne − 2), RAM (≤ frei − 4 GB), SMBIOS genau; Identität
  abgewandelt (`VM-`-Seriennummern, UUID `0c1a0000-…`, Disk-Seriennummer `VM…`, eigene MAC), Netzwerkkarte immer
  Intel, OEM-Key nie. Vorschau *Gerät → VM* mit ✔/~/✖ und Hinweisen, Name änderbar, Platz/RAM-Prüfung, Häkchen
  „Letztes Image des Geräts einspielen“ (Standard an, Master mit ★). Mit Image ein Auftrag auf der VM: Einschalten
  und Agent starten → bis 5 min warten → Zurückspielen mit Prüfung, ohne Anpassen → Herunterfahren; Fehler: Meldung,
  VM bleibt. Merkmal `vm.twin_of`, Verlauf bei beiden, Zeile „Zwilling von“ (anklickbar) in der Übersicht der VM.
  **Abweichungen** (Details [VM.md](VM.md)): RAM auf ganze GB aufgerundet (Inventar = MemTotal), zweiter Zwilling
  `0c1a0001-…`, neues Profilfeld `chassis_serial`. Hilfe: Abschnitt „Digitaler Zwilling“ im Kapitel „Virtuelle
  Maschinen“, neuer Knopf im Kapitel „Gerät verbinden“ (Gerätefenster). Tests `tests/test_vm_twin.py`. Am Server mit
  `virsh` geprüft; Ablauf mit Image offen ([TESTS.md](TESTS.md) Abschnitt 10). Kein neuer Agent-Stick.
- **Ä-036 – VM mit leerer Disk: Rückfrage statt UEFI-Menü** (Von: Dominik/Claude, gemeldet 06.11.): „Einschalten“
  einer VM, deren Disk noch nie ein System hatte (keine Partitionen, im Verlauf keine Installation, kein Zurückspielen,
  kein Start von ISO), fragt: *Einschalten und Agent starten*, *Von ISO starten …*, *Trotzdem einschalten*. Gilt für
  alle VMs. Hilfe-Kapitel „Virtuelle Maschinen“ ergänzt. Prüfung am Server: [TESTS.md](TESTS.md) Abschnitt 9.
- **I-001 Auftrag 2 – VMs im Tool** (Von: Dominik): Fester Ordner „Virtuelle Maschinen“ in der Geräteliste (keine
  Unterordner, VMs nicht herausziehbar, echte Geräte nicht hinein), Zustand der VM in der Statusspalte (alle 5 s ein
  `virsh list`). **Extras → Neue virtuelle Maschine …** bzw. Rechtsklick auf den Ordner: Profil, Name, Hardware,
  Prüfung von Platz und RAM; legt VM und Geräteeintrag an (Identität = SMBIOS-UUID, Vor-Inventar mit Kabel-Karte,
  Netzwerkstart sofort frei). Aktionen per Rechtsklick und im Gerätefenster: Einschalten, Einschalten und Agent
  starten, Von ISO starten … (ISO-Bibliothek, CIFS ohne Umbesitzen), Bildschirm (virt-viewer), Herunterfahren /
  Neu starten (ohne Agent über ACPI), Ausschalten …, Hardware ändern …, VM löschen …. Wake-on-LAN-Stellen schalten
  VMs über libvirt ein; Reiter Netzwerk ohne Wake-on-LAN/„Netzwerkstart zuerst“ bei VMs. **Abweichung:**
  Startreihenfolge Disk → Netzwerk mit Umstellung der laufenden VM (QEMU `bootindex`) statt fest Netzwerk → Disk –
  OVMF zeigt nach grub-`exit` das Setup-Menü statt die Disk zu starten (am Server geprüft, Details [VM.md](VM.md)).
  Hilfe: Kapitel „Virtuelle Maschinen“, Begriff „Virtuelle Maschine (VM)“, Verweise aus „Master-Image“, „Geräte
  verwalten“, „Anzeigen im Fenster“. Neues Modul `vm_dialogs.py`, Tests `test_vm_devices.py` und Erweiterungen in
  `test_vm.py`. Am Server Ende zu Ende geprüft ([TESTS.md](TESTS.md)). Kein neuer Agent-Stick.
- **I-001 Auftrag 1b – VM-Nacharbeit** (Von: Projektleitung, Abnahme Auftrag 1): `install.sh` installiert
  `qemu-system-modules-spice` (ohne das Modul kein SPICE-Bildschirm). Disk der VM als Datei im Pool-Verzeichnis
  (`type="file"`) statt Pool-Volume – nur so legt libvirt die AppArmor-Freigabe an; Anlegen/Vergrössern/Löschen
  weiterhin über den Pool `okula`. VM-Legacy mit Intel e1000 statt Realtek rtl8139 (Windows-Treiber); rtl8139 bleibt
  wählbar. Verständliche Meldungen bei fehlendem SPICE und nicht lesbarer Disk-Datei. Am Server alle drei Profile
  erstellt, gestartet, ausgeschaltet und gelöscht (Bildschirm per VNC-Testkopie). Kein neuer Agent-Stick.
- **I-001 Auftrag 1 – VM-Grundlage** (Von: Dominik): `install.sh` installiert QEMU/KVM, libvirt, OVMF, swtpm und
  virt-viewer, nimmt den Benutzer in die Gruppe `libvirt` auf, legt den Speicherpool `okula` an und schaltet das
  libvirt-Standardnetz ab. Netzwerkbrücke `br0` per `okula-bridge` (NetworkManager, gleiche MAC und IP wie `eno2`,
  Rückfall nach 45 s, `--no-bridge`). Netzwerkstart schreibt seine dnsmasq-Konfiguration vor jedem Dienststart neu,
  wenn die Schnittstelle wechselt (`eno2` → `br0`). Neues Modul `vm.py`: Profile VM-Win11/-Legacy/-Klein, libvirt-XML
  ohne virtio, NVMe per `qemu:override` (libvirt 11.3 hat den Bus noch nicht), Aktionen über virsh. Noch keine
  Oberfläche, kein neuer Agent-Stick. Abweichungen in [VM.md](VM.md). Tests `test_vm.py`, `test_bridge.py`,
  `InterfaceChangeTest`.

### 05.11.2026
- **B-006 BIOS-Reiter: unlesbare Einträge beim HP EliteBook 850 G1** (Von: Dominik): `hp-bioscfg` liefert auf dem
  BIOS L71 nur 8 Einträge mit kaputten Namen (`\r`, `Î`, `þ`, Steuerzeichen), leeren Werten und „max. 0 Zeichen“ – der
  Treiber versteht dieses alte BIOS nicht. Tool: unlesbare Einträge ausgeblendet, Hinweis unter „Schnittstelle“,
  „SPM“ als Secure Platform Management statt Passwort, Secure Boot im BIOS-Modus „– (nur im UEFI-Modus)“, leere
  Werte „–“, kein „max. 0 Zeichen“/„enumeration“. Kein neuer Stick nötig. Tests `GarbledDriverTest`.
- **I-023 Hardware-Test** (Von: Claude/Dominik): Reiter „Hardware-Test“ im Gerätefenster, nur lesend. Schnelltest
  (≈ 5 min: Akku, Temperaturen, SMART kurz, RAM-Teil, 1 min CPU-Last, Netzwerk-Durchsatz) und Gründlich (≈ 1–3 h:
  zusätzlich SMART lang, Oberfläche lesen, 15 min CPU-Last, grösserer RAM-Test). Ampel je Bereich mit Einzelheiten,
  die letzten 10 Tests beim Gerät, Verlauf, PDF-Prüfprotokoll mit Unterschriftsfeld. Agent `hwtest.py` + Befehl
  `hwtest` (Abbrechen, Disk-Sperre; **neuer Agent-Stick nötig**), Tool `hwreport.py`/`hw_tab.py`, Demo-Gerät mit
  simulierten Werten (Netzwerk echt). Hilfe-Kapitel „Hardware-Test“. Tests `tests/test_hwtest.py`. Teil 2 → I-033.
- **B-005 „BIOS nicht lesbar: Verbindung unerwartet beendet“** (Von: Dominik, HP EliteBook 850 G1 mit hp-bioscfg):
  Das BIOS meldet Namen in Windows-1252 (Byte 0xCE) – Python übernimmt sie als Platzhalterzeichen, `wire.send_json`
  brach mit UnicodeEncodeError ab und der Agent schloss die Verbindung ohne Antwort. Fix: biosread dekodiert Namen und
  Werte als UTF-8, sonst Windows-1252, und schreibt Werte in derselben Kodierung zurück; `send_json` ersetzt nicht
  darstellbare Zeichen statt abzubrechen (auch für Dateinamen im Datei-Backup); der Agent beantwortet jeden internen
  Fehler mit einer Meldung (Traceback im Journal); nur noch der Treiber des Herstellers wird geladen (keine
  „dell_wmi_sysman: Unable to run“-Zeilen mehr). **Neuer Agent-Stick nötig.** Tests `OldEncodingTest`.
- **I-032 Reiter „BIOS“ im Gerätefenster** (Von: Dominik): Grundangaben (BIOS-Version, Boot-Modus, Secure Boot, TPM,
  BIOS-Passwort, UEFI-Startreihenfolge) für alle Geräte; Einstellungen über `firmware-attributes` (HP `hp-bioscfg`,
  Dell `dell-wmi-sysman`, Lenovo `think-lmi`). Stand beim Gerät gespeichert, Vergleich mit einem anderen Gerät („Nur
  Unterschiede“, wichtige Einstellungen zuerst), Suche, CSV, Ändern mit Passwortabfrage (nie gespeichert) und Warnung
  vor riskanten Werten; gilt nach dem Neustart, Eintrag im Verlauf. Agent `biosread.py` + Befehle `bios`/`bios_set`
  (**neuer Agent-Stick nötig**), Tool `biosinfo.py`/`bios_tab.py`, Demo-Gerät mit simuliertem HP-BIOS. Hilfe-Kapitel
  „BIOS“. Tests `tests/test_bios.py` (nachgebautes sysfs, Setzen mit Passwort, Vergleich, CSV, Demo-Agent). I-015
  (BIOS-Update) bleibt offen.
- **Ä-035 Name und Logo in Alt+Tab und Dock** (Von: Dominik): statt „__main__.py“ mit Standard-Symbol steht „Okula
  Recovery Tool“ mit dem Okula-Logo. Programm-ID `ch.okula.RecoveryTool` überall gleich: GApplication-ID (Wayland),
  WM_CLASS Name und Klasse (X11, `GLib.set_prgname`, `Gdk.set_program_class`), Startmenü-Datei neu
  `ch.okula.RecoveryTool.desktop` mit `StartupWMClass` (install.sh ersetzt die alte `okula-recovery.desktop`, auch im Autostart).
- **Ä-034 Netzwerkstart sichtbar** (Von: Dominik/Claude): Gerätefenster → Netzwerk → „Netzwerkstart-Protokoll“ (letzte
  6 h, alle 5 s neu): Anfrage BIOS/UEFI, Antwort bzw. „nicht freigeschaltet“, shim/grub/Startart/Kernel/initrd bzw.
  pxelinux, Live-System und Agent per HTTP, Fehler rot mit Grund; Zusammenfassung oben (auch „Dienst läuft nicht“,
  „keine Anfrage angekommen“). Root-Helfer `pxe log` liest das Journal, `pxelog.py` übersetzt; HTTP-Meldungen mit MAC.
  Mit echten Abläufen im Labor verifiziert (dnsmasq 2.91, OVMF + shim/grub, SeaBIOS/iPXE + pxelinux, nicht
  freigeschaltet) – Aufzeichnungen als Testdaten. Dazu Korrektur B-003: Kabel-Karten aus dem Inventar zählen auch mit
  lokal vergebener MAC (VMs). Hilfe „Netzwerkstart“, „Probleme lösen“. Tests `tests/test_pxelog.py`.
- **Ä-033 Rechtsklick auf ein Gerät → „Netzwerkstart“** (Von: Dominik): Untermenü „Einschalten“ und „Einschalten und
  Agent starten“ (Wake-on-LAN wie im Reiter Netzwerk). Nicht mögliches ausgegraut, Grund im Tooltip (schon verbunden,
  keine Kabel-Netzwerkkarte, Netzwerkstart nicht eingerichtet bzw. für das Gerät aus, „Netzwerkstart zuerst“ fehlt);
  dieselbe Prüfung (`MainWindow.wake_options`) gilt für die Knöpfe im Gerätefenster. Hilfe „Geräte verwalten“.
- **B-003 Netzwerk-Reiter bei Geräten im BIOS-Modus** (Von: Dominik, gemeldet 05.11., HP EliteBook 850 G1 – Stick per
  CSM im Legacy-Modus gestartet): „Netzwerkstart zuerst“ meldete erst nach dem Klick „nur im BIOS-Setup änderbar“.
  Neu: Hinweis vorab mit BIOS-Taste; nach Umstellen im BIOS-Setup vermerkt der Schalter „von Hand eingestellt“, dann
  gehen „Agent beim nächsten Start“ und „Einschalten und Agent starten“ wie bei UEFI (`devices.bios_mode`). Dazu:
  Netzwerkkarten-Liste ohne zufällige MACs, Mobilfunk-Modem („wwp…“) nicht mehr als „Kabel“/PXE-tauglich
  (`nic_kind`, `netboot_macs`); eigenes Zahnrad-Symbol (`okula-settings-symbolic`), weil `emblem-system-symbolic`
  im Icon-Thema des Servers fehlt (blaues Quadrat). Hilfe „Netzwerkstart“, TECHNIK. Tests `NetworkCardsTest`.
- **B-002 „Stick abziehen“ zur falschen Zeit** (Von: Dominik, gemeldet 05.11.): Nach „OS installieren … vorbereitet“
  hiess es „Stick JETZT abziehen“, 15 s später Neustart – der Agent läuft aber vom Stick, ohne ihn klappt der Neustart
  nicht. Richtig: Stick stecken lassen, BootNext startet einmalig von der Disk; abziehen, sobald die Installation
  läuft. Nach dem Zurückspielen: erst herunterfahren, dann abziehen. Texte im Tool-Log, Installations-Dialog,
  Automatisierung (Banner), Restore-Stick, Hilfe, TECHNIK. Die Meldung am Gerät (agent.py) erscheint erst mit einem
  neu erstellten Agent-Stick – bis dahin gilt: Stick stecken lassen.
- **Ä-032 Spaltenbreiten verstellbar und gemerkt** (Von: Dominik): Geräte, Images, Dateien, Backups – alle Spalten mit
  der Maus verstellbar (vorher sperrten die dehnende Spalte und Mindestbreiten, z. B. „Status“ 340 px), Breiten je
  Liste in `spalten.json`; nur verstellte Spalten werden gespeichert. Mit echtem Maus-Ziehen (xdotool) und Neustart
  geprüft. Hilfe „Anzeigen im Fenster“. Tests `tests/test_colstate.py`.
  Ergänzt: auch im Gerätefenster (Aufträge, Disks, Images, Backups, Netzwerk, Verlauf; Breiten für alle Geräte gleich).
- **B-001 Baugleiche Geräte wurden zu einem zusammengeführt** (Von: Dominik, gemeldet 05.11.): zwei „CompactPlayer“
  ohne UUID und Seriennummer – vereint sehr wahrscheinlich über die gleiche Disk-Seriennummer („Board getauscht, Disk geblieben“).
  Fix nur im Tool: Platzhalter-UUIDs/-Seriennummern (auch Disk) nie als Identität, zufällige MACs nicht beim
  Wiedererkennen; ist ein passender Eintrag gerade über einen anderen Agent verbunden → eigenes Gerät („Name (2)“),
  gemeinsame Kennungen in `geraete/mehrdeutig.ids`; alter vereinter Eintrag wird getrennt; gleiche Agent-ID mit
  anderer Beacon-MAC → „ID@MAC“. Kein neuer Agent-Stick. Hilfe „Geräte verwalten“. Tests `test_devices.LookalikeDevicesTest`.

### 31.10.2026
- **Ä-031 Bandbreite – Tage:** Tage im Zeitfenster hell (begrenzt), übrige dunkel (unbegrenzt), in hellem und dunklem Design; Tooltip und Hilfe ergänzt (Von: Dominik).
- **I-030 Bandbreite begrenzen** (Von: Claude/Dominik, Prio 🟡): Menü → Einstellungen … → Rahmen „Bandbreite“ als
  erster Abschnitt – Schalter (Standard aus), Höchstwert 10–10'000 Mbit/s (Standard 300, mit MB/s), optional nur im
  Zeitfenster von/bis mit Tagen (Standard Mo–Fr 07:00–18:00, über Mitternacht möglich). Ein gemeinsamer Token-Bucket
  (`bandwidth.py`) für alle Aufträge, nur im Tool an `wire.send_data`/`recv_frame` – Agent unverändert, kein neuer
  Stick. Wirkt sofort auch auf laufende Aufträge, gilt fürs Demo-Gerät, NAS-Zugriffe des Servers bleiben unbegrenzt.
  Anzeige „begrenzt: … Mbit/s“ in der LAN-Kurve, Log-Zeile zu Beginn jedes Auftrags, Restzeit nach Änderung neu.
  `config.json` + Export/Import (Restore-Stick kopiert `bandwidth.py` mit). Hilfe: „Erste Schritte“ (4.),
  „Anzeigen im Fenster“, „Probleme lösen“.
  Tests `tests/test_bandwidth.py` (±10 %, parallel, Zeitfenster, Ändern im Lauf, Ende-zu-Ende über den Demo-Agent).
- **Ä-030 NAS-Leiste:** Symbole „NAS im Browser öffnen“ und „NAS-Verbindung einrichten“ direkt nebeneinander (eigene Box ohne Abstand), 16 px Abstand nur noch zum Text (Von: Dominik).
- **Ä-029 Legende Images:** „Image-Datei“ heisst neu „Sonstiges Image“ (passend zu „Sonstige ISO“) (Von: Dominik).
- **Ä-028 Herunterfahren / Neu starten als Symbole** (Von: Dominik, Variante 1 von 3): Systemsymbole
  `system-reboot-symbolic` und `system-shutdown-symbolic` wie die übrigen Symbolknöpfe, Name als Tooltip –
  im Hauptfenster rechts unter der Geräteliste (neu auch „Neu starten“) und im Gerätefenster (`uikit.power_buttons`).
  Menü Tools → „Gerät herunterfahren“ entfernt (Rechtsklick auf ein Gerät bietet beides weiterhin an).
- **Ä-027 Demo vollständig ohne NAS** (Von: Dominik): eigener Demo-Speicher `demo/` im Konfig-Ordner
  (`demostore.py`, Aufbau wie auf dem NAS: images/, Backups/, Verteilen/ mit Beispielprojekten). Alle Aufträge des
  DEMO-PC (Disk-Image, Zurückspielen, Datei-Backup, Ordner senden, Automatisierung) laufen nur dort
  (`MainWindow.root_for`, `automation.Engine(root_for=…)`). Sperren in beide Richtungen (`demostore.allowed`).
  Fertige Images „DEMO-Master-Win11“ (★ Master, Prüfung ✔) und „DEMO-Image-beschaedigt“ (ein Byte verändert,
  Prüfung ✖). Reiter Images/Backups: Bereich „Demo (lokal, nicht auf dem NAS)“, auch ohne NAS; alte Demo-Images
  auf dem NAS ausgeblendet, Löschen per Rechtsklick. Extras → Demo-Daten zurücksetzen … (mit Rückfrage).
  Hilfe „Demo-Gerät“ neu. Tests `tests/test_demostore.py` (ganzer Vorführablauf ohne NAS und mit unverändertem NAS).
- **I-007 Image prüfen (von Hand):** Rechtsklick auf ein Okula- oder Clonezilla-Image → „Image prüfen …“, auf einen
  Ordner (auch „Nicht einsortiert“) → „Alle Images im Ordner prüfen …“ (mit Unterordnern), ebenso im Gerätefenster
  (Reiter Images). Prüfung auf dem Server ohne Gerät (`imagecheck.py`: SHA256 bzw. `clonezilla.verify`), nur lesend;
  eigenes Fenster mit Prozent, Restzeit, Abbrechen und Zusammenfassung („3 Images geprüft: 2 ✔, 1 ✖“).
  Ergebnis mit Datum, Datei und Meldung in `okula-image.json` („check“) bzw. `okula-check.json`; Spalte „Geprüft“
  (✔ Datum grün / ✖ beschädigt rot, Tooltip). Beschädigt: roter Hinweis beim Zurückspielen und in der
  Automatisierung (Reiter und Log), Zurückspielen bleibt möglich. Löschen während der Prüfung gesperrt; Eintrag im
  Verlauf des Geräts. Kein Zeitplan (Entscheid Dominik). Tests `tests/test_imagecheck.py`.
- **Ä-026 README kurz:** Startseite auf GitHub nur noch Zweck, Funktionen, Installation und Links; die ausführliche
  Beschreibung steht neu in [TECHNIK.md](TECHNIK.md) (Verweise in den Docs angepasst).
- **Ä-025 Hilfe abgeschlossen (H23–H25), README im Handbuch-Stil** (Von: Dominik):
  - H23: Kapitel nach Arbeitsablauf (Datei-Backup nach Image zurückspielen, Demo-Gerät ans Ende), Kapitel
    „Inventar, Garantie, Windows 11“; alle Querverweise „Kapitel <i>…</i>“ zeigen auf bestehende Kapitel.
  - H24: Suchfeld über der Kapitelliste (Ctrl+F): filtert nach Titel und Text (alle Wörter, Gross/Klein egal,
    NFC), Treffer gelb, erstes Treffer-Kapitel, „Keine Treffer“; Esc leert zuerst die Suche. Logik ohne GTK in
    `helpsearch.py`.
  - H25: `tests/test_help.py` (Markup, alle Einträge aus `MENU_LABELS` in der Hilfe, Querverweise, keine Anrede,
    keine Ich-Form in Fortschritt/Log); Menüleiste aus `MENU_LABELS` (ui.py).
  - README ohne Anrede, neue Abschnitte Firewall (alle Ports), Typischer Ablauf, Inventar/Garantie/Windows 11,
    Master-Image, Hilfe/Tastenkürzel. Begriff „Windows-Schlüssel“ statt „Windows-Key/Produktschlüssel“ in der Oberfläche.
  - Sichtprüfung: alle 24 Kapitel hell/dunkel; Farbwörter als Farbfeld (gelb war im dunklen Design unlesbar),
    doppelte Punkte nach „…“ entfernt; letzte Ich-Formen umgestellt („Partitionstabelle wird übernommen“,
    „install.wim wird … geteilt“, „Prüfmuster wird geschrieben“, PXE-Boot „Agent-Teil wird geladen“).
  - Nebenbei: zwei veraltete Testtexte aus Ä-024 nachgeführt.
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
