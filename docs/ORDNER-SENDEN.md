# Ordner an Geräte senden

Ziel: vordefinierte Ordner vom NAS per Mausklick auf den Desktop eines Geräts kopieren.

Stand: **umgesetzt** (29.10.2026). Details in [TECHNIK.md](TECHNIK.md), Bedienung in der Hilfe (F1); Prüfungen am realen System: [TESTS.md](TESTS.md).

## Struktur auf dem NAS

Im Reiter **Dateien** anpassbar (Inhalte hinzufügen, ändern, löschen).

```
Verteilen/
├── Software/        fix – wird immer als ganzer Ordner kopiert
├── Test Files/      fix – wird immer als ganzer Ordner kopiert
└── Content/         wird selbst nicht kopiert, enthält Projekte zur Auswahl
    ├── Projekt A/
    ├── Projekt B/
    └── …
```

- Die Ordner `Software` und `Test Files` sind **fix** (Namen und Verhalten).
- `Content` ist der einzige Auswahl-Ordner: Die Projekte darin werden einzeln gewählt.
- `Software` ist ein **Werkzeug-Ordner für Geräte unterwegs** (Sammlungen, ZIP-Archive, portable Tools). Für
  *Software installieren* wird er seit Ä-041 weder gelesen noch beschrieben – die Programme dafür liegen in der
  Software-Bibliothek (`Software-Bibliothek/` neben `Verteilen`, *Extras → Software-Bibliothek …*).

## Ziel auf dem Gerät

Immer der **öffentliche Desktop für alle Benutzer**: `C:\Users\Public\Desktop` (erscheint bei jedem Benutzer, auch bei
später angelegten).

| Gesendet | Ergebnis auf dem Desktop |
|---|---|
| Software | `Software\…` |
| Test Files | `Test Files\…` |
| Content → Projekt A | `Content\Projekt A\…` |

**Erneut senden = ersetzen:** Der vorhandene Ordner auf dem Desktop wird durch den aktuellen Stand vom NAS ersetzt
(alter Inhalt weg). Bei Content betrifft das nur die gewählten Projekte, andere Projekte unter `Content\` bleiben.

Linux (später, falls nötig): öffentlicher Desktop gibt es nicht – Schreibtisch jedes Benutzers
(`~/Schreibtisch` bzw. `~/Desktop` laut `user-dirs.dirs`), Besitzer = Benutzer.

## Bedienung (Vorschlag)

- Rechtsklick auf ein Gerät → **„Ordner senden ▸ Software“**, **„▸ Test Files“**, **„▸ Content …“**.
- Gleiche Funktion im **Gerätefenster** (Knopf oder eigener Reiter).
- „Content …“ öffnet eine Liste der Projekte mit Häkchen (eins oder mehrere).
- Fortschritt in der Auftragsliste, Eintrag im Verlauf des Geräts.
- Später möglich: an mehrere Geräte gleichzeitig senden.

## Technik (Idee)

- Das Gerät läuft mit dem Agent (Stick oder Netzwerkstart). Der Agent hängt die Windows-Partition schreibend ein und
  schreibt die Dateien direkt auf die Disk – wie heute „Backup zurückspielen → ins installierte System“.
- Das Tool liest vom NAS und überträgt verschlüsselt an den Agent (wie bei der Direktinstallation); der Agent braucht
  kein NAS-Passwort.
- Ersetzen: zuerst in einen Zwischenordner kopieren, dann alten Ordner löschen und umbenennen – bei Abbruch bleibt
  der alte Stand erhalten.
- Aus der Ferne kombinierbar: Wake-on-LAN → Netzwerkstart mit Agent → Ordner senden → Neustart in Windows.

## Voraussetzungen / Grenzen

- Windows **ganz heruntergefahren** (kein Schnellstart, kein Ruhezustand) – sonst ist die Partition nicht beschreibbar.
- **BitLocker:** verschlüsselte Partition ohne Wiederherstellungsschlüssel nicht beschreibbar.
- *Ordner senden* kopiert die Software nur, installiert nichts. Still installieren beim ersten Start: Liste
  *Software installieren* (I-020) in *OS installieren …*, *Image zurückspielen* und Automatisierung, Programme aus
  der Software-Bibliothek (Ä-041) – Details in [TECHNIK.md](TECHNIK.md), „Software installieren“. Die versteckten
  Beschreibungen `.<Name>.okula.json`, die I-020 im Ordner `Software` angelegt hatte, entfernt das Tool beim
  Verbinden mit dem NAS (nur diese Dateien); solche Dateien würden auch nicht mitgesendet.
