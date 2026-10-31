# Okula Recovery Tool

Geräte im LAN sichern, wiederherstellen und neu aufsetzen – Images und Backups liegen auf dem NAS.
Server: Debian 13 mit Xfce, Python 3 und GTK 3.

![Oberfläche](docs/screenshot.png)

**Funktionen:** Disk-Images und Datei-Backups · Zurückspielen (auch auf kleinere Disks) · Master-Image für viele
Geräte · Automatisierung · Windows/Linux direkt installieren · Netzwerkstart und Wake-on-LAN · Inventar, Garantie,
Windows-11-Prüfung, Export als CSV/PDF · Agent-, Boot- und Restore-Sticks · USB klonen und formatieren.

## Installation

```bash
sudo apt install git
git clone https://github.com/donsimm/recovery_tool_okula.git
cd recovery_tool_okula
git checkout claude/blissful-goldberg-mo3xda
sudo ./install.sh --autostart
```

Update: `git pull && sudo ./install.sh`. Danach im Tool: NAS verbinden (Ctrl+N) und Agent-Stick erstellen.

## Dokumentation

- **Bedienung:** Hilfe im Tool (**F1**, mit Suche)
- **Technik und Details:** [docs/TECHNIK.md](docs/TECHNIK.md)
- **Änderungen, Ideen, Entscheidungen:** [docs/AENDERUNGEN.md](docs/AENDERUNGEN.md) · Notizen: [docs/EINGANG.md](docs/EINGANG.md)
- **Tests am realen System:** [docs/TESTS.md](docs/TESTS.md)

Tests: `python3 -m unittest discover -s tests -t .`
