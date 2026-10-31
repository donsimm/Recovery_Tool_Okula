# Automatisierung

Ziel: Ein Gerät, das schon im Tool erfasst ist und dessen Automatisierung eingeschaltet ist, wird automatisch
neu aufgesetzt, sobald es im LAN auftaucht (mit Agent gestartet: Stick oder Netzwerkstart). Start nach 30 Sekunden.

Stand: **umgesetzt** (29.10.2026). Bedienung im [README](../README.md); Prüfungen am realen System: [TESTS.md](TESTS.md).

## Auslöser

- Nur Geräte, die **schon im Tool erfasst** sind **und** deren Automatisierung **an** ist.
- Das Gerät meldet sich im LAN (Agent-Beacon) → **30 Sekunden Countdown** → Start.
- Kein Zeitplan, kein Wake-on-LAN, keine Automatisierung pro Ordner.

## Oberfläche

- **Geräteübersicht:** zusätzliche Spalte mit Häkchen **„Automatisierung“** ein/aus.
- **Gerätefenster:** neuer Reiter **„Automatisierung“** mit allen Einstellungen und dem Hinweis:
  *„Die Automatisierung läuft einmal und schaltet sich nach erfolgreichem Durchlauf selbst aus. Nach 3 Tagen
  schaltet sie sich wieder ein (abschaltbar).“* (Keine Option „immer“.)
- **Option im Reiter: „Nach 3 Tagen wieder einschalten“** – Standard **ein**.
- **Hauptschalter:** Stopp-Knopf ■ über der Geräteliste, rot nur solange pausiert (auch Menü → Einstellungen).
- **Vorlagen** im Reiter: Einstellungen als Vorlage speichern (z. B. „Schulungs-PC zurücksetzen“) und anderen
  Geräten zuweisen.

## Ablauf (Schritte im Reiter)

| # | Schritt | Einstellung |
|---|---|---|
| 1 | Vorher sichern | Option ein/aus; Auswahl **Benutzerdaten** oder **ganze Disk (Disk-Image)** |
| 2 | Image zurückspielen | Auswahl: **Master-Image** (markierte Images) oder **eigenes Image** |
| 3 | Anpassen: Gerätename aus dem Tool, Windows-Key | läuft **immer** (siehe [MASTER-IMAGE.md](MASTER-IMAGE.md)) |
| 4 | Ordner senden: Software, Test Files, Content-Projekte | Option im Reiter (siehe [ORDNER-SENDEN.md](ORDNER-SENDEN.md)) |
| 5 | Abschluss: Neustart in Windows / herunterfahren / nichts | Option im Reiter |

Nach Schritt 5 setzt das Tool die Startreihenfolge auf „lokal“ zurück (falls „Netzwerkstart zuerst“ aktiv war).

## Sicherheit

1. **Countdown sichtbar** im Tool und am Gerät: *„Automatisierung startet in 30 s – Esc zum Abbrechen“*;
   im Tool ein Abbrechen-Knopf.
2. **Nur einmal in 3 Tagen:** nach erfolgreichem Durchlauf schaltet sich das Häkchen selbst aus (keine Endlosschleife
   bei jedem Start mit Stick/Netzwerkstart). Nach **3 Tagen** (gerechnet ab Ende des erfolgreichen Durchlaufs)
   schaltet das Tool es **wieder ein** – ausser im Reiter ist „Nach 3 Tagen wieder einschalten“ aus. Die Übersicht zeigt
   in dieser Zeit z. B. *„wieder aktiv in 5 h“*.
3. **Zieldisk über die Seriennummer** festgelegt, nicht `/dev/sda`. Andere Disk eingebaut → Abbruch, nichts gelöscht.
4. **Hauptschalter** zum Pausieren aller Automatisierungen.
5. **Vorab prüfen:** passt das Image auf die Disk, ist es unbeschädigt – erst danach wird etwas gelöscht.

## Gleichzeitige Automatisierungen

- **Höchstens N gleichzeitig** (N in Menü → Einstellungen; schont Netz und NAS); weitere Geräte warten in einer Warteschlange.
- In der **Übersicht klar anzeigen:** Countdown, wartet (Platz in der Warteschlange), läuft (Schritt x/5, Fortschritt),
  fertig, Fehler.

## Protokoll

- Jeder Schritt mit Startzeit, Dauer und Ergebnis im **Verlauf des Geräts**.
- Bei Fehler: Schritt und Meldung im Verlauf, Status „Fehler“ in der Übersicht.

## Entscheide (29.10.2026)

- **Wert für N:** einstellbar über **Menüleiste → Menü → Einstellungen …** (Vorschlag Standard: 2).
- **Master-Image:** Images bekommen eine Option **„Als Master-Image markieren“** (Rechtsklick und Details im
  Images-Baum, Symbol/Kennzeichen in der Liste). Im Reiter „Automatisierung“ wird bei *Master-Image* aus den markierten
  Images gewählt; *eigenes Image* = beliebiges Image.
- **Bei Fehler:** sofort abbrechen und das Gerät in den **normalen Agent-Betrieb** zurückversetzen (verbunden, bereit
  für Arbeiten von Hand). Ist das nicht möglich, den Fehler **überall anzeigen, wo es geht**:
  - Tool: Status „Fehler“ (rot) in der Übersicht, Meldung in der Statuszeile, Gerätefenster, Verlauf des Geräts;
  - am Gerät (Agent-Bildschirm): *„Automatisierung fehlgeschlagen: <Schritt/Grund>. Gerät neu starten bzw. neu
    anschliessen.“*
  - kein automatischer neuer Versuch; das Häkchen bleibt an, damit ein neuer Start (Gerät neu anschliessen) es erneut
    versucht.
- **Abbrechen am Gerät:** Taste **Esc** (üblichste Abbruchtaste – BIOS/Boot-Menüs, Windows-Dialoge). Im Countdown
  steht: *„Automatisierung startet in 30 s – Esc zum Abbrechen“*.

- **Schritt 3 „Anpassen“** läuft immer (keine Option).
- **Wieder einschalten nach 3 Tagen** (bis 31.10.2026: 24 h): Option im Reiter, Standard ein. Ist sie aus, bleibt das Häkchen nach dem
  Durchlauf aus, bis es jemand von Hand einschaltet.
