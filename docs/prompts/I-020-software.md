# I-020 – Software aus dem Ordner „Software“ automatisch installieren

Status: freigegeben · erstellt 17.11.2026 von der Projektleitung · Freigabe: Dominik 17.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, die Einträge I-020, I-039, Ä-040 und „📌 Entscheidungen“
in `docs/AENDERUNGEN.md`, `docs/ORDNER-SENDEN.md`, `docs/MASTER-IMAGE.md`, in `docs/TECHNIK.md` die Abschnitte zur
Windows-Direktinstallation, zu *Danach anpassen*, *Ordner senden* und *Windows anpassen* (Startmechanismus).
Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde (lokaler Branch `agent/I-020`); nicht pullen,
nicht pushen. Grosser Auftrag: in **2–3 sinnvoll getrennten Commits** (Katalog/Erkennung → Ablauf/Agent → Oberfläche).

## Ziel

Programme aus `Verteilen\Software` auf dem NAS lassen sich per Häkchen auswählen und werden auf dem Gerät **still und
ohne Klicks** installiert – bei *OS installieren …* (auch mit *Für Master-Image (Audit-Modus)* → landet im Master),
beim *Image zurückspielen* mit *Danach anpassen* und in der Automatisierung. Neue Software, die in den Ordner gelegt
wird, erscheint automatisch in der Liste.

## Entscheide aus dem Brainstorming

- Quelle ist der Ordner `Verteilen\Software` mit festen, getesteten Versionen – **nicht winget** (Dominik 17.11.).
- In *OS installieren*, *Image zurückspielen* (*Danach anpassen*) und Automatisierung, jeweils dieselbe Liste
  (Dominik 17.11.).
- Neue Software erscheint automatisch; eine neue Version eines Programms übernimmt die Parameter der alten;
  Parameter liegen in einer versteckten Beschreibung neben dem Installer (Dominik 17.11.).

## Anforderungen

1. **Katalog** (neues Modul, z. B. `okula_recovery/software.py`, ohne GTK):
   - Einträge = Installer-Dateien direkt in `Software\` (`.exe`, `.msi`) **und** Unterordner (Programm mit mehreren
     Dateien, z. B. „Barco Eventmaster Toolset“: einmal festlegen, welche Datei der Installer ist; der ganze Ordner wird
     mitgenommen). `System Tools` und ähnliche Sammelordner: jede Datei einzeln wählbar oder als „nur kopieren“ –
     sinnvolle Lösung wählen und begründen.
   - Versteckte Beschreibung neben dem Eintrag (Muster `oslib`: `.<Name>.okula.json`): Programmname, Version,
     Installer-Typ, Parameter für die stille Installation, erwartete Rückgabewerte (0, 3010 = Neustart nötig), „nur von
     Hand“ (lässt sich nicht still installieren), Prüfsumme/Grösse.
   - **Erkennung des Installer-Typs** ohne Ausführen: `.msi` → `msiexec /i … /qn /norestart`; in `.exe` nach Kennungen
     suchen (NSIS → `/S`, Inno Setup → `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-`, InstallShield, WiX Burn
     → `/quiet /norestart`, Squirrel …; Quellen nennen). Erkannt → sofort wählbar; unbekannt → **„Parameter fehlt“**,
     nicht wählbar, bis Parameter hinterlegt sind.
   - **Neue Version:** gleicher Programmname (aus Dateiname/Versionsinfo der .exe/.msi, z. B. `vlc-3.0.24-win64.exe`
     ↔ `vlc-3.0.23-win64.exe`) → Parameter der vorigen Beschreibung übernehmen; Hinweis im Katalog.
2. **Pflege im Reiter *Dateien*** (bzw. passender Dialog): Software-Einträge mit Typ und Status (erkannt / Parameter
   fehlt / nur von Hand); Parameter bearbeiten; bei Unterordnern Installer wählen; „nur von Hand“ setzen.
3. **Auswahl** – gleiche Liste mit Häkchen und Suchfeld:
   - *OS installieren …* (Windows-ISO; auch mit Audit-Modus),
   - *Image zurückspielen* im Bereich *Danach anpassen* (nur Windows),
   - Automatisierung (Schritt *Anpassen* oder eigener Schritt – passend zum bestehenden Ablauf; Auswahl gespeichert wie
     die übrigen Einstellungen).
   Anzeige der Gesamtgrösse.
4. **Ablauf auf dem Gerät:**
   - Die gewählten Installer kommen mit auf die Disk (Direktinstallation: Setup-Partition bzw. später Windows-
     Partition; Zurückspielen: Windows-Partition schreibend, wie *Ordner senden*), Ziel z. B.
     `C:\ProgramData\Okula\Software\…`; Übertragung wie *Ordner senden* (Tool liest NAS, Agent schreibt).
   - Installation **beim ersten Windows-Start als SYSTEM**, nacheinander, still, mit Protokoll
     `C:\Windows\Temp\okula-software.log` (je Programm: Start, Ende, Rückgabewert, ok/Fehler). Ein Fehler stoppt die
     übrigen nicht. Danach Installer-Dateien löschen. 3010 → nach dem letzten Programm **ein** Neustart.
   - Startmechanismus: den von I-039 (Startskript der lokalen Gruppenrichtlinie, `deploy.install_startup_script`)
     wiederverwenden oder begründet einen anderen wählen. **Nicht** `SetupComplete.cmd` als einziges Mittel (läuft bei
     OEM-Schlüssel nicht, B-013). Windows bricht Startskripte nach 10 Minuten ab – lange Installationen dürfen daran
     nicht scheitern (z. B. Installation in einem eigenen Prozess/einer einmaligen Aufgabe, die das Startskript anlegt,
     oder Wartezeit-Richtlinie für diesen Lauf); Lösung mit Quelle begründen.
   - **Master (Audit-Modus, I-038):** Installation läuft im Audit-Modus beim ersten Start, damit die Programme im Image
     landen; Reihenfolge mit dem Aufräumen der Setup-Partition und dem Löschen von `Panther\unattend.xml` abstimmen.
   - **Generalisiertes Image mit *Danach anpassen*:** Installation erst nach der Ersteinrichtung (Startskript läuft
     dann), Zusammenspiel mit Ä-040 (CopyProfile) und I-039 prüfen.
5. **Im Tool:** Log des Auftrags nennt die gewählten Programme; Verlauf des Geräts „Software: VLC, Adobe Reader …
   (wird beim ersten Start installiert)“. Ergebnis vom Gerät zurücklesen ist **nicht** Teil.
6. **Demo-Gerät:** Auswahl vorführbar (meldet „fertig“).
7. **Tests:** Erkennung je Typ (Probe-Dateien mit Kennungen), Versionswechsel übernimmt Parameter, „Parameter fehlt“
   nicht wählbar, erzeugtes Installationsskript (Reihenfolge, Rückgabewerte, Protokoll, Löschen, ein Neustart bei 3010,
   nur ASCII wo cmd), Ablage auf Probe-Verzeichnis, Auswahl in Automatisierung gespeichert.

## Nicht Teil dieses Auftrags

- winget/Internet-Downloads, Deinstallieren, Updates bestehender Installationen, Ergebnis zurück ins Tool lesen.
- Linux.

## Hinweise zum Code

- Katalog-Muster: `oslib.py` (versteckte Beschreibung), `distribute.py`/`nasfiles.py` (Ordner `Verteilen`, Reiter
  *Dateien*), Übertragung: `jobs.deliver_work`, `agentclient.deliver`, `deploy.deliver`.
- Direktinstallation: `os_dialogs.InstallDialog`, `winsetup.py` (Setup-Partition, `extra`-Dateien, `install_cmd`),
  `wininstall.install` (Agent).
- Zurückspielen/Automatisierung: `restore_dialog.py` (*Danach anpassen*), `ui.py` um Zeile 3630, `automation.py`,
  `automation_tab.py`.
- Startmechanismus: `deploy.install_startup_script`, `wintweaks.py` (Skript-Bausteine, Protokoll).
- Agent betroffen (neuer Agent-Stick nötig)? **ja**.

## Oberfläche und Texte

- Bereich/Liste **„Software installieren“** mit Häkchen, Suchfeld, Spalten Programm, Version, Grösse, Status.
- Status-Texte: „bereit“, „Parameter fehlt“, „nur von Hand“. Schreibstil laut `CLAUDE.md`.
- Hilfe (F1): neues Kapitel „Software installieren“ (Ordner, neue Software/Version, Parameter, Ablauf, Protokoll) und
  Verweise aus *OS installieren*, *Image zurückspielen*, Automatisierung.

## Abnahmekriterien

- [ ] Neue Datei in `Software\` erscheint in der Liste; MSI/NSIS/Inno erkannt; unbekannt → „Parameter fehlt“
- [ ] Neue Version übernimmt Parameter der alten
- [ ] Auswahl in *OS installieren*, *Danach anpassen* und Automatisierung; Installer landen auf der Disk; Skript
      installiert beim ersten Start still, protokolliert, räumt auf
- [ ] Lange Installationen werden nicht nach 10 Minuten abgebrochen (Lösung begründet)
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests wie oben
- [ ] Hilfe (F1) angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Eintrag ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: neuer Abschnitt „Software installieren (I-020)“ – VM: Direktinstallation mit VLC + Adobe Reader,
      Master im Audit-Modus mit Software, Zurückspielen mit *Danach anpassen*, Programm mit „Parameter fehlt“,
      neue Version
- [ ] `docs/TECHNIK.md` ergänzt
- [ ] Demo-Gerät: vorführbar

## Abschluss

1. 2–3 Commits mit `I-020: …` im Titel, **nur lokal** auf `agent/I-020` – **nicht pushen**. **Nur eigene Dateien
   committen** (`git add <Pfade>`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Commits, Testergebnis, neuer Agent-Stick ja, Schritte für den Server, gewählte
   Lösungen mit Quellen (Erkennung, Startmechanismus, 10-Minuten-Grenze), offene Punkte.
