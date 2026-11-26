# Ordner an Geräte senden

Ziel: vordefinierte Ordner vom NAS per Mausklick auf den Desktop eines Geräts kopieren.

Stand: **umgesetzt** (29.10.2026). Details in [TECHNIK.md](TECHNIK.md), Bedienung in der Hilfe (F1); Prüfungen am realen System: [TESTS.md](TESTS.md).

## Struktur auf dem NAS

Im Reiter **Dateien** anpassbar (Inhalte hinzufügen, ändern, löschen).

```
Verteilen/
├── Software/        Auswahl (Ä-051) – jeder Unterordner und jede Datei ist ein eigener Eintrag
│   ├── Browser/
│   ├── OBS & plugin/
│   ├── …
│   └── Reader_de_install.exe
├── Test Files/      fix – wird immer als ganzer Ordner kopiert
└── Content/         wird selbst nicht kopiert, enthält Projekte zur Auswahl
    ├── Projekt A/
    ├── Projekt B/
    └── …
```

- Die Ordnernamen `Software`, `Test Files` und `Content` sind **fix**.
- `Software` (seit Ä-051, 26.11.2026) und `Content` sind Auswahl-Ordner: Die Einträge darin werden einzeln
  gewählt. Unter `Software` zählen Unterordner **und** einzelne Dateien direkt im Ordner (Ordner zuerst,
  alphabetisch; versteckte Einträge und Links nicht). Häkchen *Alle* = jeder Eintrag, auch später hinzugekommene –
  so gilt auch die alte Einstellung „Software“ (vor Ä-051) in Automatisierung und Vorlagen.
- `Test Files` wird immer ganz gesendet.
- `Software` ist ein **Werkzeug-Ordner für Geräte unterwegs** (Sammlungen, ZIP-Archive, portable Tools). Für
  *Software installieren* wird er seit Ä-041 weder gelesen noch beschrieben – die Programme dafür liegen in der
  Software-Bibliothek (`Software-Bibliothek/` neben `Verteilen`, *Extras → Software-Bibliothek …*).

## Ziel auf dem Gerät

Immer der **öffentliche Desktop für alle Benutzer**: `C:\Users\Public\Desktop` (erscheint bei jedem Benutzer, auch bei
später angelegten).

| Gesendet | Ergebnis auf dem Desktop |
|---|---|
| Software → Ordner „Browser“ | `Software\Browser\…` |
| Software → Datei `Reader_de_install.exe` | `Software\Reader_de_install.exe` |
| Software → Alle | `Software\<jeder Eintrag>` |
| Test Files | `Test Files\…` |
| Content → Projekt A | `Content\Projekt A\…` |

**Erneut senden = ersetzen:** Der vorhandene Eintrag auf dem Desktop wird durch den aktuellen Stand vom NAS ersetzt
(alter Inhalt weg). Bei Software und Content betrifft das nur die gewählten Einträge, andere Inhalte unter
`Software\` bzw. `Content\` bleiben (auch bei *Alle*: Einträge, die es auf dem NAS nicht mehr gibt, bleiben auf dem
Desktop). Fehlen gespeicherte Einträge auf dem NAS, nennt das Log sie, der Rest wird gesendet.

**Agent:** Einzelne Dateien aus `Software` brauchen einen Agent ab Ä-051 (neuer Agent-Stick bzw. Netzwerkstart); ein
älterer meldet „Agent zu alt …“. Ordner gehen auch mit älteren Agents.

Linux (später, falls nötig): öffentlicher Desktop gibt es nicht – Schreibtisch jedes Benutzers
(`~/Schreibtisch` bzw. `~/Desktop` laut `user-dirs.dirs`), Besitzer = Benutzer.

## Bedienung (Vorschlag)

- Rechtsklick auf ein Gerät → **„Ordner senden ▸ Software …“**, **„▸ Test Files“**, **„▸ Content …“**.
- Gleiche Funktion im **Gerätefenster** (Knopf *Ordner senden …*).
- „Software …“ und „Content …“ öffnen den Dialog *Ordner senden* mit Listen und Häkchen (eins oder mehrere; bei
  Software zusätzlich *Alle*). „Test Files“ sendet ohne Dialog.
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
