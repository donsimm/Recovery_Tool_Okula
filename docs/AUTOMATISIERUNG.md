# Automatisierung (geplant, noch nicht programmiert)

Ziel: Ein Gerät, das schon im Tool erfasst ist und dessen Automatisierung eingeschaltet ist, wird automatisch
neu aufgesetzt, sobald es im LAN auftaucht (mit Agent gestartet: Stick oder Netzwerkstart). Start nach 30 Sekunden.

Stand: Idee/Entscheid vom 29.10.2026. Im Tool ist dafür noch nichts gebaut.

## Auslöser

- Nur Geräte, die **schon im Tool erfasst** sind **und** deren Automatisierung **an** ist.
- Das Gerät meldet sich im LAN (Agent-Beacon) → **30 Sekunden Countdown** → Start.
- Kein Zeitplan, kein Wake-on-LAN, keine Automatisierung pro Ordner.

## Oberfläche

- **Geräteübersicht:** zusätzliche Spalte mit Häkchen **„Automatisierung“** ein/aus.
- **Gerätefenster:** neuer Reiter **„Automatisierung“** mit allen Einstellungen und dem Hinweis:
  *„Die Automatisierung läuft einmal und schaltet sich nach erfolgreichem Durchlauf selbst aus.“*
  (Keine Option „immer“.)
- **Hauptschalter** (Menü): alle Automatisierungen pausieren, z. B. bei Wartung am NAS.
- **Vorlagen** im Reiter: Einstellungen als Vorlage speichern (z. B. „Schulungs-PC zurücksetzen“) und anderen
  Geräten zuweisen.

## Ablauf (Schritte im Reiter)

| # | Schritt | Einstellung |
|---|---|---|
| 1 | Vorher sichern (Backup der Benutzerdaten) | Option ein/aus |
| 2 | Image zurückspielen | Auswahl: **Master-Image** oder **eigenes Image** wählen |
| 3 | Anpassen: Gerätename aus dem Tool, Windows-Key | immer (siehe [MASTER-IMAGE.md](MASTER-IMAGE.md)) |
| 4 | Ordner senden: Software, Test Files, Content-Projekte | Option im Reiter (siehe [ORDNER-SENDEN.md](ORDNER-SENDEN.md)) |
| 5 | Abschluss: Neustart in Windows / herunterfahren / nichts | Option im Reiter |

Nach Schritt 5 setzt das Tool die Startreihenfolge auf „lokal“ zurück (falls „Netzwerkstart zuerst“ aktiv war).

## Sicherheit

1. **Countdown sichtbar** im Tool und am Gerät: *„Automatisierung startet in 30 s – Taste drücken zum Abbrechen“*;
   im Tool ein Abbrechen-Knopf.
2. **Nur einmal:** nach erfolgreichem Durchlauf schaltet sich das Häkchen selbst aus (keine Endlosschleife bei jedem
   Start mit Stick/Netzwerkstart).
3. **Zieldisk über die Seriennummer** festgelegt, nicht `/dev/sda`. Andere Disk eingebaut → Abbruch, nichts gelöscht.
4. **Hauptschalter** zum Pausieren aller Automatisierungen.
5. **Vorab prüfen:** passt das Image auf die Disk, ist es unbeschädigt – erst danach wird etwas gelöscht.

## Gleichzeitige Automatisierungen

- **Höchstens N gleichzeitig** (schont Netz und NAS); weitere Geräte warten in einer Warteschlange.
- In der **Übersicht klar anzeigen:** Countdown, wartet (Platz in der Warteschlange), läuft (Schritt x/5, Fortschritt),
  fertig, Fehler.

## Protokoll

- Jeder Schritt mit Startzeit, Dauer und Ergebnis im **Verlauf des Geräts**.
- Bei Fehler: Schritt und Meldung im Verlauf, Status „Fehler“ in der Übersicht.

## Noch offen

- Wert für N (Vorschlag: 2–3, im Menü einstellbar).
- Was gilt als **Master-Image**? Vorschlag: ein im Images-Baum markiertes Image oder das neueste Image in einem
  Ordner „Master“ – so wird ein aktualisierter Master automatisch verwendet.
- Verhalten bei **Fehler:** Häkchen bleibt an, aber kein automatischer neuer Versuch, bis das Gerät neu startet?
- Abbrechen am Gerät: welche Taste (Vorschlag: beliebige Taste bzw. Esc).
