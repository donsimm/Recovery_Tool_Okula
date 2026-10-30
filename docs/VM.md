# Virtuelle Maschine (VM) im Tool – Idee

Stand: **Idee** (30.10.2026), noch nicht programmiert. Dominik kommt darauf zurück.

Ziel: Auf dem Server eine echte virtuelle Maschine betreiben, um ISOs und Images zu installieren, zu testen und zu
ändern – und daraus wieder Images zu erstellen (z. B. das Master-Image ohne echtes Referenzgerät).

## Wie es funktionieren würde

- **QEMU/KVM** auf dem Server (Debian-Pakete `qemu-system-x86`, `ovmf`, `swtpm`). Die virtuelle Festplatte ist eine
  Datei (qcow2) auf der SSD des Servers und wächst nur mit dem belegten Platz.
- Die VM steht in der Geräteliste wie ein Gerät (z. B. „VM-Test“) mit drei Knöpfen:
  - **Von ISO starten:** ISO vom NAS wählen (Windows, Ubuntu …) und installieren; der Bildschirm der VM erscheint
    in einem eigenen Fenster.
  - **Mit Agent starten:** wie mit dem Agent-Stick, nur mit einer Agent-ISO (oder Netzwerkstart). Danach geht alles
    wie bei einem echten Gerät: Disk-Image erstellen, zurückspielen, Backup, Ordner senden, Automatisierung.
  - **Normal starten:** das installierte Windows/Linux testen oder ändern.
- **Windows 11:** Secure Boot (OVMF) und TPM 2.0 (swtpm) in der VM vorhanden.

## Typische Abläufe

1. **Master-Image erstellen:** ISO in der VM installieren → Programme einrichten → Sysprep → „Mit Agent starten“
   → Disk-Image erstellen → als Master markieren (siehe [MASTER-IMAGE.md](MASTER-IMAGE.md)).
2. **Image testen:** vorhandenes Image (auch Clonezilla) in die VM zurückspielen und starten.
3. **Image ändern:** Image in die VM → Updates/Programme → neues Image.

## Voraussetzungen am Server

- CPU mit Virtualisierung (Intel VT-x / AMD-V), im BIOS eingeschaltet. Läuft der RecoveryPC selbst als VM:
  „nested virtualization“ nötig.
- RAM: Windows-11-VM mindestens 8 GB → Server besser 16 GB oder mehr.
- SSD: etwa 64–128 GB frei pro VM (auf dem NAS wäre die VM-Festplatte zu langsam).

## Worauf achten

- **Standard-Hardware nachbilden** (SATA-Disk, Intel-Netzwerkkarte e1000e), keine virtio-Treiber – sonst läuft ein
  Image aus der VM auf echten Geräten nicht.
- Auf andere Hardware übertragbar ist ein VM-Image nur **mit Sysprep** (Master-Image).
- **Lizenz:** Windows in der VM braucht zum Aktivieren einen eigenen Key; für die Image-Erstellung reicht meist
  „nicht aktiviert“.
- **Aufwand:** mittel bis gross. Vorhanden: Agent läuft in QEMU (getestet beim Netzwerkstart), Image-Funktionen;
  neu wäre u. a. eine Agent-ISO (statt Stick), VM-Verwaltung im Tool und das VM-Fenster.

## Offene Fragen

1. Hardware des RecoveryPC: CPU, RAM, freier SSD-Platz?
2. VM im LAN sichtbar oder abgeschottet (nur Verbindung zum Server)?
3. Eine VM oder mehrere (z. B. Windows 10 und Windows 11 parallel)?
