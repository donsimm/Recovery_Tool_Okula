# Automatisierung

Ziel: Ein Gerät, das schon im Tool erfasst ist und dessen Automatisierung eingeschaltet ist, wird automatisch
neu aufgesetzt, sobald es im LAN auftaucht (mit Agent gestartet: Stick oder Netzwerkstart). Start nach 30 Sekunden.

Stand: **umgesetzt** (29.10.2026). Details in [TECHNIK.md](TECHNIK.md), Bedienung in der Hilfe (F1); Prüfungen am realen System: [TESTS.md](TESTS.md).

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
| 1 | Vorher sichern | Option ein/aus; Auswahl **Benutzerdaten** oder **ganze Disk (Disk-Image)**. Benutzerdaten: ist eine Partition der Zieldisk nicht lesbar (BitLocker, Ruhezustand/Schnellstart), bricht der Lauf ab – nichts gelöscht (B-025). BitLocker mit im Gerätefenster hinterlegtem Wiederherstellungsschlüssel: Partition nur lesend geöffnet, Benutzerdaten gesichert (I-012); ohne bzw. mit falschem Schlüssel Abbruch („… BitLocker-Schlüssel im Gerätefenster hinterlegen …“) |
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
   **BitLocker (I-012):** gesichert wird nur mit gespeichertem Wiederherstellungsschlüssel (nur root-lesbar,
   `/etc/okula-recovery/bitlocker/`); das Tool fragt nie nach einem Schlüssel und verändert die BitLocker-Disk vor dem
   Zurückspielen nie. Details [TECHNIK.md](TECHNIK.md) „BitLocker entsperren (I-012)“.
4. **Hauptschalter** zum Pausieren aller Automatisierungen.
5. **Vorab prüfen:** passt das Image auf die Disk, ist es unbeschädigt – erst danach wird etwas gelöscht.
6. **Rückfrage beim Einschalten von Hand (Ä-007):** Häkchen *Auto* und Schalter im Reiter zeigen zuerst eine rote
   Zusammenfassung (`automation.confirm_summary`, Dialog `uikit.confirm(…, red=True)`): Disk, die gelöscht wird, Image,
   Gerätename danach, Backup, bei VMs Snapshot, Abschluss, Wieder-Einschalten nach 3 Tagen. Ist das Gerät verbunden,
   heisst der Knopf „Löschen und neu aufsetzen“ (danach sofort Countdown), sonst „Einschalten“. *Abbrechen* ist
   Standard und lässt alles aus. Die Rückfrage sitzt in den Auslösern (`ui._on_auto_toggled`,
   `automation_tab._changed`), nicht in `save_automation`/`consider`. Unvollständige Einstellungen → Meldung, was
   fehlt, keine Rückfrage. Ohne Rückfrage: Ausschalten, Wieder-Einschalten nach 3 Tagen (`Engine.tick`), Aufheben des
   Stopps ■, Vorlage anwenden (ändert `enabled` nicht), Import der Einstellungen (übernimmt den exportierten Zustand).

## Gleichzeitige Automatisierungen

- **Höchstens N gleichzeitig** (N in Menü → Einstellungen; schont Netz und NAS); weitere Geräte warten in einer Warteschlange.
- In der **Übersicht klar anzeigen:** Countdown, wartet (Platz in der Warteschlange), läuft (Schritt x/5, Fortschritt),
  fertig, Fehler.

## Protokoll

- Jeder Schritt mit Startzeit, Dauer und Ergebnis im **Verlauf des Geräts**.
- Bei Fehler: Schritt und Meldung im Verlauf, Status „Fehler“ in der Übersicht.
- **Anpassen nicht gelungen (B-028, 25.11.2026):** Meldet `customize` für eine Partition `error` oder
  `not_generalized` oder – wenn das Image eine NTFS-Partition hat (Windows erwartet) – gar kein Windows, gilt
  Schritt 3 als **Fehler** (`jobs.customize_problems`): kein „Automatisierung erfolgreich“, kein Abschluss/Neustart,
  das Häkchen bleibt an. Beim Zurückspielen von Hand (`jobs.restore_work`) steht im Ergebnis „Warnung beim Anpassen: …“
  statt „und angepasst“.
- **Abbruch und Fehler (B-028):** Als „abgebrochen“ zählt ein Auftrag nur, wenn die Ausnahme selbst der Abbruch ist
  (`jobs.is_cancel_error`: Meldung beginnt mit „Abgebrochen“ bzw. Klasse `Cancelled`). Ein Fehler, nach dem noch
  Abbrechen geklickt wurde, behält seine Ursache in Log, Verlauf und Banner.
- **Fehler im Tool selbst (B-028):** Wirft der Ablauf ausserhalb des Auftrags (Speichern, Verlauf, Anzeige), endet der
  Lauf mit Status „Fehler“ und Eintrag im Verlauf – er bleibt nie auf „läuft“ stehen.

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
