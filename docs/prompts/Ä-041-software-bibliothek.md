# Ä-041 – Software-Bibliothek im Tool (statt Ordner `Verteilen\Software`)

Status: freigegeben · erstellt 18.11.2026 von der Projektleitung · Freigabe: Dominik 18.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, die Einträge Ä-041 und I-020 sowie „📌 Entscheidungen“ in
`docs/AENDERUNGEN.md`, `docs/prompts/I-020-software.md`, `docs/ORDNER-SENDEN.md`, in `docs/TECHNIK.md` den Abschnitt
zu *Software installieren* (I-020).
Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde (lokaler Branch `agent/AE-041`); nicht pullen,
nicht pushen. Grösserer Auftrag: in **2–3 sinnvoll getrennten Commits** (Bibliothek/Ablage → Fenster → Umstellung der
Auswahl, Aufräumen, Hilfe/Doku).

## Ziel

Die Software für „Software installieren“ (I-020) kommt aus einer **eigenen Software-Bibliothek des Tools**, nicht mehr
aus `Verteilen\Software`. Der Ordner `Verteilen\Software` ist wieder nur Werkzeug-Ordner für *Ordner senden*
(Geräte unterwegs) und wird vom Software-Katalog weder gelesen noch beschrieben.

## Befund (18.11.)

I-020 liest `Verteilen\Software` (ein Ordner = ein Eintrag mit genau einem Installer). Dominiks Ordner sind
Werkzeugsammlungen (z. B. „OBS & plugin“ mit 6 Dateien, „Browser“ mit Chrome und Firefox, ZIP-Archive, portable Tools)
→ 12 von 21 Einträgen ohne Installer bzw. „Parameter fehlt“. Zudem liegen dort jetzt 21 versteckte
`.<Name>.okula.json`, die I-020 angelegt hat.

## Entscheide (Dominik 18.11.)

- Eigene Bibliothek; Zugang im Menü **Extras → „Software-Bibliothek …“**.
- Ein Fenster: oben **„Ins Tool laden …“** (Datei) und **„Ordner laden …“** (Installer, der seine Dateien daneben
  braucht, z. B. Yamaha `YSUSB_V213_Win/setup.exe`), dazu Ziehen und Ablegen; **darunter direkt die Liste** mit den
  Angaben (Name, Version, Typ, Parameter, Rückgabewerte, Status, Grösse), dort bearbeitbar.
- Ablage auf dem NAS im eigenen Ordner **`Software-Bibliothek`** neben `Verteilen` (gesichert, für alle Tool-Rechner
  gleich).
- Die Auswahl „Software installieren“ (OS installieren, Image zurückspielen → *Danach anpassen*, Automatisierung) zeigt
  nur noch die Bibliothek.
- `Verteilen\Software` bleibt für *Ordner senden*; die von I-020 dort angelegten `.okula.json` räumt das Tool weg.

## Anforderungen

1. **Ablage** `Software-Bibliothek/` auf dem NAS (Pfad wie die übrigen NAS-Ordner bestimmen; wird bei Bedarf
   angelegt). Je Eintrag ein eigener Unterordner (z. B. `<key>-<version>/`) mit Installer (bzw. geladenem Ordner) und
   der Beschreibung (Format von I-020 wiederverwenden: Programm, Version, Typ, Parameter, Rückgabewerte, Modus, Installer
   relativ, Grösse, SHA-256). Kein Raten bei Namenskonflikten: gleicher Inhalt (SHA-256) → Hinweis „schon in der
   Bibliothek“, nicht doppelt ablegen.
2. **Laden:** Datei (`.exe`, `.msi`) bzw. Ordner wählen (lokal, USB, NAS – auch aus `Verteilen\Software`), Kopie in die
   Bibliothek mit Fortschritt und Abbruch (Abbruch hinterlässt nichts Halbes), danach Erkennung wie I-020 (`detect`)
   und Parameter vortragen. Beim Ordner: Installer wählen, falls nicht eindeutig. Eine geladene neue Version übernimmt
   die Parameter der vorigen (Logik `_adopt` von I-020); die alte Version bleibt, bis man sie löscht.
3. **Liste im selben Fenster:** Spalten wie oben, Status „bereit“ / „Parameter fehlt“ / „nur von Hand“ /
   „nur kopieren“; Parameter, Rückgabewerte, Modus, Name und Version bearbeiten (direkt oder über eine Detailzeile –
   passend zum Stil des Tools); Löschen mit Bestätigung; Suchfeld. Die bisherige Pflege (Reiter *Dateien* → Knopf
   „Software …“, `software_ui.py`) wird durch dieses Fenster ersetzt bzw. darin wiederverwendet – keine zwei Orte.
4. **Auswahl umstellen:** `software.scan`/Katalog liest nur noch die Bibliothek. Übertragung auf das Gerät
   (Direktinstallation, Zurückspielen, Automatisierung) unverändert, nur mit der neuen Quelle. Gespeicherte Auswahlen
   der Automatisierung/Vorlagen: über den `key` weiter auflösen; Eintrag nicht mehr vorhanden → wie bisher als fehlend
   melden, nicht still überspringen.
5. **Aufräumen `Verteilen\Software`:** Beim ersten Start nach dem Update (bzw. beim ersten Zugriff) die von I-020
   angelegten versteckten Dateien `.<Name>.okula.json` mit `"format": "okula-software"` dort löschen – **nur** diese,
   sonst nichts; Ergebnis ins Log. Nichts automatisch in die Bibliothek übernehmen.
6. **Demo-Modus:** Bibliothek mit Beispiel-Einträgen vorführbar, ohne das NAS zu verändern (Muster `demostore.py`).
7. **Tests:** Laden Datei/Ordner (Probe-Verzeichnis), Doppel per SHA-256, Abbruch ohne Reste, neue Version übernimmt
   Parameter, Katalog liest nur die Bibliothek (nicht `Verteilen\Software`), Aufräumen löscht nur `okula-software`-
   Beschreibungen, Auflösen gespeicherter Auswahl über `key`, Menüeintrag in `MENU_LABELS`/`tests/test_help.py`.

## Nicht Teil dieses Auftrags

- Ablauf am Gerät (Startskript, geplante Aufgabe, Protokoll) – bleibt wie I-020.
- ZIP entpacken, portable Tools erkennen, winget/Downloads, Deinstallieren.
- Änderungen an *Ordner senden*.

## Hinweise zum Code

- `okula_recovery/software.py` (Katalog, `detect`, `_adopt`, Beschreibung), `software_ui.py` (bisherige Pflege),
  `nasfiles.py`/`distribute.py` (NAS-Pfade, Reiter *Dateien*), `ui.py` (`MENU_LABELS`, `actions` um Zeile 240),
  `os_dialogs.py`, `restore_dialog.py`, `automation.py`/`automation_tab.py`, `winsetup.plan`, `demostore.py`.
- Kopieren mit Fortschritt: vorhandene Muster (z. B. ISO hinzufügen, Reiter *Dateien*) wiederverwenden.
- Agent betroffen (neuer Agent-Stick nötig)? Voraussichtlich **nein** – in der Abschlussmeldung bestätigen.

## Oberfläche und Texte

- Menü Extras: **„Software-Bibliothek …“**; Fenstertitel „Software-Bibliothek“.
- Knöpfe „Ins Tool laden …“, „Ordner laden …“, „Löschen“. Schreibstil laut `CLAUDE.md`.
- Hilfe (F1): Kapitel „Software installieren“ auf die Bibliothek umschreiben (Laden, Parameter, neue Version, Ablage);
  Hinweis, dass `Verteilen\Software` nur für *Ordner senden* ist.

## Abnahmekriterien

- [ ] Extras → Software-Bibliothek: Datei und Ordner laden, Liste mit Angaben bearbeitbar, Löschen
- [ ] Auswahl „Software installieren“ zeigt nur die Bibliothek; `Verteilen\Software` wird nicht mehr gelesen/beschrieben
- [ ] Von I-020 angelegte `.okula.json` in `Verteilen\Software` entfernt, sonst nichts
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests wie oben
- [ ] Hilfe (F1) angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Ä-041 ins „✅ Erledigt“-Protokoll, Kurzübersicht; `docs/TECHNIK.md`, `docs/TESTS.md`
      (Abschnitt 23 anpassen oder neuer Abschnitt 25 „Software-Bibliothek“), `docs/ORDNER-SENDEN.md` nachgeführt
- [ ] Demo: vorführbar

## Abschluss

1. 2–3 Commits mit `Ä-041: …` im Titel, **nur lokal** auf `agent/AE-041` – **nicht pushen**. **Nur eigene Dateien
   committen** (`git add <Pfade>`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Commits, Testergebnis, neuer Agent-Stick ja/nein, Schritte für den Server, offene
   Punkte.
