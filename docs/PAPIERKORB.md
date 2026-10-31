# Papierkorb – gestrichene Ideen und Änderungen

Punkte, die bewusst **nicht** umgesetzt werden. Sie bleiben hier zum Nachlesen, werden aber nicht wieder
vorgeschlagen. Zurückholen: Zeile nach [AENDERUNGEN.md](AENDERUNGEN.md) zurückverschieben (gleiche ID, Status „offen“).

| ID | Gestrichen | Von | Was | Grund / Notiz |
|---|---|---|---|---|
| Ä-001 | 31.10.2026 | Claude | **Aufträge als Systemdienst statt im Programmfenster:** Dienst `okula-recoveryd` (systemd) führt Aufträge, Automatisierung und Netzwerkstart aus; das Fenster wird nur noch Anzeige und Bedienung (lokaler Socket). | Nicht gewünscht (Entscheid Dominik). Aufwand ca. 2'000–3'000 Zeilen, Risiko im Kern. Folge: Aufträge und Automatisierung laufen nur, solange das Tool geöffnet ist; Webinterface (I-004) und Zeitplan (I-010) müssen im Fenster-Prozess laufen. Günstige Alternative, falls nötig: Schliessen bei laufendem Auftrag mit Rückfrage, Autostart mit automatischer Anmeldung. |
| I-002 | 31.10.2026 | früher | **Nobara/Zorin direkt installieren** (ohne Boot-Stick). | Gestrichen (Entscheid Dominik). Deren Installer (Calamares bzw. ohne Autoinstall) erlauben keine unbeaufsichtigte Installation; Boot-Stick bleibt der Weg. |
| I-019 | 31.10.2026 | Claude | **Disk direkt klonen:** HDD → SSD im Gerät über den Agent, Gerät → Gerät ohne NAS, Partitionsgrösse beim Klonen anpassen. | Nicht nötig (Entscheid Dominik). Abgedeckt durch *Extras → USB klonen* am Server (Disk per USB-Adapter) und den Weg Disk-Image → Zurückspielen (auch auf kleinere Disk, Ä-002). |
| Ä-008 | 31.10.2026 | Claude | **Nach dem Restore Windows starten, auch wenn der Stick noch steckt** (BootNext nach Restore/Automatisierung). | Nicht nötig (Entscheid Dominik). Geräte mit „Netzwerkstart zuerst“ steuert das Tool pro Neustart (Windows oder einmal Agent); Hinweis „Stick abziehen“ genügt. |
| – | 31.10.2026 | Claude | **Startmenü am Gerät bei „Netzwerkstart zuerst“** (3 s Auswahl Windows/Agent). | Nicht aufnehmen (Entscheid Dominik): Auswahl pro Neustart im Tool (Reiter „Netzwerk“) reicht. |
| Ä-009 | 31.10.2026 | Claude | **Vorauswahl** von Zieldisk und Master im Reiter Automatisierung, Standard-Vorlage für neue Geräte. | Nicht gewünscht (Entscheid Dominik). |
| – | 31.10.2026 | Claude | **Multicast automatisch in der Automatisierung** (Variante A: Geräte mit gleichem Master sammeln und gemeinsam aufsetzen). | Nicht gewünscht (Entscheid Dominik): Multicast nur von Hand über Extras → Multicast (I-011). |
| – | 31.10.2026 | Claude | **Herunterfahren bei laufendem Windows/Linux** (Fernabschaltung per `net rpc shutdown`, SSH oder Vorbereitung im Master). | Nicht aufnehmen (Entscheid Dominik): Herunterfahren nur über den Agent genügt; Windows-Weg bräuchte gespeicherte Admin-Passwörter. |
| I-031 | 31.10.2026 | Claude | **Geräte-Etikett mit QR-Code** (Name, Seriennummer, Kunde drucken; Scan öffnet das Gerät). | Nicht gewünscht (Entscheid Dominik). |
| I-010 | 31.10.2026 | Claude | **Backups nach Zeitplan** (Wake-on-LAN → Agent → Datei-Backup → herunterfahren). | Nicht gewünscht (Entscheid Dominik). |
| Ä-013 | 31.10.2026 | Claude | **Klare Fertig-Meldung und Übergabeprotokoll** nach der Automatisierung. | Nicht gewünscht (Entscheid Dominik). |
