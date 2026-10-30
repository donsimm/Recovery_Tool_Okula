# Änderungen, Bugs, Ideen und Entscheidungen

Zentrale Übersicht zum Okula Recovery Tool. Details zu jeder Funktion stehen im [README](../README.md),
der genaue Verlauf in `git log`, Prüfungen in [TESTS.md](TESTS.md).

**Ablauf:** Spontane Notizen kommen nach [EINGANG.md](EINGANG.md). Claude sortiert sie hier in die passende
Kategorie ein (mit ID), leert den Eingang und hält die Kurzübersicht aktuell.

**IDs:** `B-` Bug · `Ä-` Änderung/Verbesserung · `I-` Idee · Status: **offen**, **in Arbeit**, **erledigt**
(→ ins Protokoll verschieben), **zurückgestellt**. Priorität: 🔴 hoch · 🟡 mittel · ⚪ tief.

## Kurzübersicht

| Kategorie | Offen | In Arbeit | Zurückgestellt |
|---|---|---|---|
| 🐞 Bugs | 0 | 0 | 0 |
| 🔧 Änderungen | 0 | 0 | 0 |
| 💡 Ideen | 2 | 0 | 2 |
| 🧪 Tests am realen System | siehe [TESTS.md](TESTS.md) | | |

Als Nächstes: Tests „Fixes von heute“ in [TESTS.md](TESTS.md) (Debian-Direktinstallation, doppelter HP-Eintrag).

## 🐞 Bugs

| ID | Prio | Status | Beschreibung | Gemeldet |
|---|---|---|---|---|
| – | | | keine offenen Bugs | |

## 🔧 Änderungen / Verbesserungen

| ID | Prio | Status | Beschreibung | Gemeldet |
|---|---|---|---|---|
| – | | | keine offenen Änderungswünsche | |

## 💡 Ideen

| ID | Prio | Status | Beschreibung |
|---|---|---|---|
| I-001 | ⚪ | offen | **Virtuelle Maschine (VM) im Tool:** ISOs/Images in einer VM auf dem Server installieren, testen, ändern und wieder Images erstellen. Details und offene Fragen: [VM.md](VM.md) |
| I-002 | ⚪ | zurückgestellt | Nobara/Zorin direkt installieren – nur möglich, falls deren Installer eine unbeaufsichtigte Installation erhält |
| I-003 | ⚪ | zurückgestellt | Nicht generalisierte 1:1-Images anpassen (Name per Registry, Key per Skript) |
| I-004 | 🟡 | offen | **Webinterface für den Fernzugriff:** Geräteübersicht und Gerätereiter im Browser (HTTPS, Anmeldung, über VPN); pro Gerät „Im Webinterface sichtbar“ (Reiter Netzwerk). Offen: nur anschauen oder auch Aktionen, Benutzer/Rechte, LAN oder VPN. Details: [WEBINTERFACE.md](WEBINTERFACE.md) |

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

### 30.10.2026
- **Demo-Gerät (Vorführung):** Extras → Demo-Gerät startet einen simulierten Agent auf dem Server („DEMO-PC“).
  Alle Aufträge lassen sich vorführen (≈ 45 s), Fehler auf Knopfdruck; nur 127.0.0.1, keine echte Disk,
  Demo-Images nur auf den DEMO-PC zurückspielbar.
- **Fortschrittsbalken:** grün während des Auftrags, rot wenn er fehlgeschlagen ist (bis der nächste startet).
- Hilfe: alle Kapitel auf den neuen Stand (Master-Image, Ordner senden, Automatisierung, Demo-Gerät).
- **Automatisierung, Schritt 1 Backup:** wahlweise Benutzerdaten oder **ganze Disk als Disk-Image** aufs NAS.
- **Hauptschalter Automatisierung:** roter Stopp-Knopf ■ über der Geräteliste (statt Menü Tools); solange pausiert,
  sind die Häkchen „Auto“ und der Schalter im Reiter ausgegraut.
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
