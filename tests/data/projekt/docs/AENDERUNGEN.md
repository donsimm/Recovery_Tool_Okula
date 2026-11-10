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
| 🐞 Bugs | 1 | 0 | 0 |
| 🔧 Änderungen | 7 | 0 | 0 |
| 💡 Ideen | 21 | 0 | 0 |
| 🧪 Tests am realen System | siehe [TESTS.md](TESTS.md) | | |

Erledigt 31.10. (Reihenfolge): Ä-014 ✔ → Ä-011 ✔ → I-024 ✔ → Ä-002 ✔ → I-025 ✔ → I-013 ✔ – **ein neuer Agent-Stick** (Version 0.2.0, für I-024 und Ä-002) und `sudo ./install.sh` (Garantie-Helfer, python3-reportlab).
Erledigt 31.10. zusätzlich: I-007 ✔ (Image prüfen) → Ä-027 ✔ (Demo ohne NAS) → Ä-028 ✔ (Ein/Aus-Symbole) → Ä-029 ✔ (Legende) → Ä-030 ✔ (NAS-Leiste) → I-030 ✔ (Bandbreite) → Ä-031 ✔ (Tage hell/dunkel).
Als Nächstes: **I-001 VMs erledigt** ✔ 06.11. (alle 4 Aufträge, [VM.md](VM.md)) – Auftrag 3 „Digitaler Zwilling“ und Auftrag 4 „Snapshots“ umgesetzt, Abnahme offen; am Server `git pull && sudo ./install.sh`, Tool neu starten, kein neuer Agent-Stick; Tests [TESTS.md](TESTS.md) Abschnitte 9, 10 und 11 (inkl. Master-Ablauf mit Snapshot „vor Sysprep“). Daneben Tests am realen System in [TESTS.md](TESTS.md) – Abschnitt 2 (Netzwerk, nach UEFI-Umstellung), 3 (Master-Image mit VMs), 5 (Automatisierung) und 7 (inkl. I-007: Dauer für ein grosses Image).
Vorschlag Reihenfolge (Analyse 31.10.): **Ä-007** (Sicherheit für Laien, klein) → **I-005/I-006** (Aufbewahrung, zweite Kopie) → Ä-005 (CI) → **Ä-006, Ä-010** (Assistent) → I-008 (Meldungen) → Rest nach Bedarf.

## 🐞 Bugs

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| B-004 | 🔴 | offen | Dominik | **HP EliteBook 850 G1 in „UEFI Native (Without CSM)“: Agent-Stick wird nicht angezeigt, Netzwerkstart (UEFI IPv4) scheitert – im Tool kein Hinweis.** Stick: MBR + FAT32 (Typ 0x0c) mit Debian-shim; PXE: Proxy-DHCP mit `pxe-prompt`/`pxe-service` BC_EFI/X86-64_EFI. Befund 05.11. (BIOS-Fotos): Secure Boot aus, Fast Boot aus, USB device boot an; **„PXE Internal IPV4 NIC boot“ aus** (nur „PXE Internal NIC boot“ = Legacy an) → im UEFI-Modus gibt es keinen Netzwerkstart; F9 zeigt nur „Boot From EFI File“ – auch der Stick fehlt. Nächster Test: IPV4 NIC boot an; Stick über „Boot From EFI File“ → EFI/boot/bootx64.efi starten (liest die Firmware die FAT-Partition?). BIOS-Vergleich 05.11.: einziger lesbarer Unterschied die **BIOS-Version** – EliteBook 2 (geht nicht) L71 **01.49** (2020), EliteBook 1 (geht) L71 **01.11** (2014); Einstellungen über Linux nicht lesbar (B-006) | 05.11. |

## 🔧 Änderungen / Verbesserungen

| ID | Prio | Status | Von | Beschreibung | Gemeldet |
|---|---|---|---|---|---|
| Ä-003 | 🟡 | offen | Claude | **Images und Backups auf dem NAS verschlüsseln:** Sie enthalten Personendaten (revDSG Art. 8, Datensicherheit). Minimum: SMB3-Verschlüsselung (`mount.cifs … seal`). Besser: Verschlüsselung im Datenstrom (z. B. `age` nach `zstd`), Schlüssel root-lesbar und zusätzlich auf Papier | 31.10. (Analyse) |
| Ä-004 | 🟡 | offen | Claude | **Zentrales Protokoll:** `/var/log/okula-recovery/` mit logrotate. Festhalten, wer wann was auf welches Gerät gespielt hat. Dazu Menü → „Diagnosepaket exportieren“ (Logs, Version, Konfiguration ohne Geheimnisse), um Fehler an Claude Code zu melden | 31.10. (Analyse) |
| Ä-005 | 🟡 | offen | Claude | **Entwicklung absichern:** GitHub Actions, die alle Tests (über 320) bei jedem Push ausführen. Versionsnummer pflegen (steht noch auf `0.1.0`) und Releases taggen, damit der Server einen geprüften Stand zieht statt den Branch-Kopf. `ui.py` (2780 Zeilen) aufteilen | 31.10. (Analyse) |
| Ä-006 | 🔴 | offen | Claude | **Assistent „Neues Gerät einrichten“:** Sobald ein unbekanntes Gerät auftaucht, fragt ein Hinweis: „Neues Gerät gefunden: HP EliteBook 840 – jetzt einrichten?“. Danach Schritt für Schritt: Name → Ordner/Kunde → Vorlage oder Master-Image → „Sind noch Daten drauf?“ (Ja = Backup) → Zusammenfassung → Start. Heute muss man selbst wissen: Gerät suchen, Doppelklick, Reiter, 5 Abschnitte, Schalter | 31.10. (Laien-Test) |
| Ä-007 | 🔴 | offen | Claude | **Bestätigung vor dem Löschen:** Wird der Schalter eingeschaltet, während das Gerät verbunden ist, startet die Automatisierung ohne Rückfrage nach 30 s und löscht die Disk (`ui.save_automation` → `consider`). Nötig: rote Zusammenfassung „Disk Samsung 256 GB von HP-PC-07 wird gelöscht, Master ‚Win11 Büro‘, neuer Name …, Backup: nein“ mit Knopf „Löschen und neu aufsetzen“ | 31.10. (Laien-Test) |
| Ä-010 | 🟡 | offen | Claude | **Vorabprüfung mit Ampel statt Fehler mitten im Lauf:** Image passt auf die Disk, UEFI/BIOS-Modus passt zum Master, BitLocker auf der Zieldisk (dann ist kein Datei-Backup möglich), Agent-Stick aktuell, Windows-Edition des Masters passt zum Key (Pro/Home). Anzeige: „✔ Bereit“ bzw. „⚠ Achtung: …“ | 31.10. (Laien-Test) |
| Ä-012 | 🟡 | offen | Claude | **Einfache Sprache im Reiter Automatisierung:** „Zieldisk“ → „Festplatte, die gelöscht wird“; Sysprep, Master und Content-Projekte mit einem „?“ pro Abschnitt erklären. Gerätenamen wie „DESKTOP-8F3K2LQ“ markieren und zum Umbenennen auffordern; optional Namensschema pro Vorlage (z. B. `KUNDE-001` fortlaufend) | 31.10. (Laien-Test) |

## 💡 Ideen

| ID | Prio | Status | Von | Beschreibung |
|---|---|---|---|---|
| I-003 | ⚪ | offen | früher | **Nicht generalisierte 1:1-Images anpassen:** Gerätename per Registry (Offline-Hive `SYSTEM`: ComputerName/Hostname), Windows-Key per Skript beim ersten Start (`slmgr /ipk`). Achtung: gleiche SID und Gerätekennung auf mehreren Geräten → nur für Einzelplätze ohne Domäne geeignet. Wieder aufgenommen 31.10.2026 |
| I-004 | 🟡 | offen | Dominik | **Webinterface für den Fernzugriff:** Geräteübersicht und Gerätereiter im Browser (HTTPS, Anmeldung, über VPN); pro Gerät „Im Webinterface sichtbar“ (Reiter Netzwerk). Offen: nur anschauen oder auch Aktionen, Benutzer/Rechte, LAN oder VPN. Details: [WEBINTERFACE.md](WEBINTERFACE.md) |
| I-005 | 🔴 | offen | Claude | **Aufbewahrungsregeln:** Pro Gerät die letzten N Images bzw. Backups behalten, ältere automatisch löschen; Master-Images sind geschützt. Vor jedem Auftrag den Platz prüfen (belegte Blöcke + Reserve), sonst gar nicht erst starten |
| I-033 | 🟡 | offen | Dominik/Claude | **Hardware-Test Teil 2:** vollständiger RAM-Test mit memtest86+ als eigener Starteintrag (Agent-Stick und Netzwerkstart; nicht für Secure Boot signiert → dafür Secure Boot kurz aus) mit Ergebnis im Tool; Tests mit Person am Gerät (Tastatur, Lautsprecher, Bildschirm-Testbilder, Kamera); optional Schnelltest als Schritt der Automatisierung | 05.11. |
| I-034 | 🔴 | offen | Dominik | **Projektübersicht im Tool (Extras → Projektübersicht …):** interaktive Webseite (lokal, Firefox) mit allen offenen Tests aus TESTS.md (abhaken, Kommentar), allen Bugs/Änderungen/Ideen aus AENDERUNGEN.md (Kommentar, Prio-/Status-Wunsch), offenen Punkten aus UEBERGABE.md und Prompts mit Status; Kopf mit Zählern, Suche/Filter, Feld „Neue Notiz“. Liest live aus dem Repo, Rückmeldungen in `~/.local/share/okula-recovery/projekt-rueckmeldungen.json`; die Projektleitung übernimmt sie auf Zuruf in die Doku. Prompt: [I-034-projektuebersicht.md](prompts/I-034-projektuebersicht.md) | 10.11. |

Umgesetzte Ideen: Windows-Master-Image mit Sysprep ([MASTER-IMAGE.md](MASTER-IMAGE.md)), Ordner an Geräte senden
([ORDNER-SENDEN.md](ORDNER-SENDEN.md)), Automatisierung ([AUTOMATISIERUNG.md](AUTOMATISIERUNG.md)),
Gerätename = Name im Tool.

## 📌 Entscheidungen

- **Projektübersicht (I-034) im Tool, nicht auf claude.ai** (Entscheid Dominik 10.11.2026): Daten live aus dem Repo (`~/recovery_tool_okula/docs`), Anzeige in Firefox über einen Webserver nur auf 127.0.0.1, Rückmeldungen in einer Datei ausserhalb von Git; die Projektleitung trägt sie auf Zuruf („neue Daten“) in TESTS.md/AENDERUNGEN.md ein und markiert sie als übernommen.
- **„Nach 3 Tagen wieder einschalten“ bleibt standardmässig an** (Automatisierung; Entscheid Dominik 31.10.2026).
- **Netzwerkstart nur für freigeschaltete Geräte:** Nur Geräte, die schon mit dem Agent-Stick liefen und

## ✅ Erledigt – Änderungsprotokoll

Neueste zuoberst.

### 06.11.2026
- **I-001 – Virtuelle Maschinen im Tool erledigt** (Von: Dominik, alle 4 Aufträge am 06.11.2026): VM-Grundlage mit
  Nacharbeit 1b, VMs im Tool, Digitaler Zwilling (mit Ä-036), Snapshots. Konzept, Entscheide und Abweichungen:
  [VM.md](VM.md); Prüfungen im Tool offen: [TESTS.md](TESTS.md) Abschnitte 8–11.
