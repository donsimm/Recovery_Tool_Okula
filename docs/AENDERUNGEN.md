# Änderungen, Entscheidungen und offene Punkte

Arbeitsnotizen zum Okula Recovery Tool. Details zu jeder Funktion stehen im [README](../README.md),
der genaue Verlauf in `git log`.

## Änderungsprotokoll

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

## Entscheidungen

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

## Offene Punkte / zu testen

- [ ] Debian-Direktinstallation mit der echten Debian-13.7.0-Netinst-ISO nochmals testen (Fix vom 29.10.).
- [ ] Doppelten HP-Eintrag nach Update prüfen (automatisch zusammengeführt oder von Hand).
- [ ] Auf echter Hardware: Reiter „Netzwerk“, Wake-on-LAN, „Netzwerkstart zuerst“, Agent beim nächsten Start.
- [ ] Neuer Server: Agent-Stick neu erstellen bzw. Agent-Schlüssel importieren, Netzwerkstart neu „Vorbereiten“.
- [ ] Firewall: auf dem neuen Server ist kein ufw installiert; mit `sudo nft list ruleset` prüfen, ob Regeln aktiv
      sind (sonst nichts zu tun).

## Ideen

- **Windows-Master-Image mit Sysprep** (entschieden, noch nicht programmiert): Image beim Zurückspielen pro Gerät
  anpassen – Gerätename aus dem Tool, Windows-Key, Benutzer, Region Schweiz. Anleitung und Plan:
  [MASTER-IMAGE.md](MASTER-IMAGE.md).
- **Ordner an Geräte senden** (entschieden, noch nicht programmiert): `Software` und `Test Files` (fix) sowie
  gewählte Projekte aus `Content` vom NAS auf den öffentlichen Desktop kopieren, erneut senden ersetzt.
  Plan: [ORDNER-SENDEN.md](ORDNER-SENDEN.md).
- **Automatisierung** (entschieden, noch nicht programmiert): erfasste Geräte mit Häkchen „Automatisierung“ werden
  30 s nach dem Auftauchen im LAN einmal neu aufgesetzt – Backup (optional), Master- oder eigenes Image, Anpassen,
  Ordner senden (optional), Abschluss; Vorlagen, höchstens N gleichzeitig, Protokoll.
  Plan: [AUTOMATISIERUNG.md](AUTOMATISIERUNG.md).
- **Gerätename = Name im Tool** bei Neuinstallation und Zurückspielen (offen: fix oder im Dialog änderbar).

- Nobara/Zorin direkt installieren: nur möglich, falls deren Installer eine unbeaufsichtigte Installation
  erhält; aktuell nicht vorgesehen.
