# Papierkorb – gestrichene Ideen und Änderungen

Punkte, die bewusst **nicht** umgesetzt werden. Sie bleiben hier zum Nachlesen, werden aber nicht wieder
vorgeschlagen. Zurückholen: Zeile nach [AENDERUNGEN.md](AENDERUNGEN.md) zurückverschieben (gleiche ID, Status „offen“).

| ID | Gestrichen | Von | Was | Grund / Notiz |
|---|---|---|---|---|
| Ä-001 | 31.10.2026 | Claude | **Aufträge als Systemdienst statt im Programmfenster:** Dienst `okula-recoveryd` (systemd) führt Aufträge, Automatisierung und Netzwerkstart aus; das Fenster wird nur noch Anzeige und Bedienung (lokaler Socket). | Nicht gewünscht (Entscheid Dominik). Aufwand ca. 2'000–3'000 Zeilen, Risiko im Kern. Folge: Aufträge und Automatisierung laufen nur, solange das Tool geöffnet ist; Webinterface (I-004) und Zeitplan (I-010) müssen im Fenster-Prozess laufen. Günstige Alternative, falls nötig: Schliessen bei laufendem Auftrag mit Rückfrage, Autostart mit automatischer Anmeldung. |
| I-002 | 31.10.2026 | früher | **Nobara/Zorin direkt installieren** (ohne Boot-Stick). | Gestrichen (Entscheid Dominik). Deren Installer (Calamares bzw. ohne Autoinstall) erlauben keine unbeaufsichtigte Installation; Boot-Stick bleibt der Weg. |
| I-019 | 31.10.2026 | Claude | **Disk direkt klonen:** HDD → SSD im Gerät über den Agent, Gerät → Gerät ohne NAS, Partitionsgrösse beim Klonen anpassen. | Nicht nötig (Entscheid Dominik). Abgedeckt durch *Extras → USB klonen* am Server (Disk per USB-Adapter) und den Weg Disk-Image → Zurückspielen (auch auf kleinere Disk, Ä-002). |
