# I-043 – Ordner einfärben (Geräteliste und Archiv)

Status: abgenommen (Okuli 26.11., Commits 7e70f75, c68b097; Doku von Okuli) · erstellt 26.11.2026 von der Projektleitung · Freigabe: Dominik 26.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag I-043 in `docs/AENDERUNGEN.md`.
Lokaler Branch `agent/I-043`; nicht pullen, nicht pushen. 2–3 Commits (Logik + Tests, Oberfläche, Hilfe/Doku).

## Ziel

Ordner in der Geräteliste (Kunden/Gruppen) und im Archiv (Images/ISOs) lassen sich per Kontextmenü einfärben,
damit man sie auf einen Blick unterscheidet. Die Farbe bleibt beim Umbenennen und Verschieben erhalten.

## Entscheide

- Umfang „beide“ (Geräteliste und Archiv) – Dominik 25.11. Cockpit-Idee ID-0003.
- Etwa 8 feste Farben oder „Keine“, keine freie Farbwahl.
- Speicherung (Empfehlung Okuli): kleine versteckte Datei **im Ordner selbst** (z. B. `.okula-ordner.json`,
  `{"color": "<schlüssel>"}`). So wandert die Farbe beim Umbenennen/Verschieben automatisch mit (beide Bäume sind
  echte Verzeichnisse: `devices.py` Store-Ordner, `archive.py` unter `ARCHIVE_DIR` auf dem NAS).

## Anforderungen

1. Gemeinsame Funktionen (z. B. in einem kleinen Modul `folder_colors.py`): Farbliste (Schlüssel, deutscher Name,
   Farbwert hell/dunkel), `get_color(path)`, `set_color(path, key|None)` (None = Datei löschen). Unbekannte
   Schlüssel oder kaputte Datei → keine Farbe, kein Fehler. Schreiben atomar (tmp + rename).
2. Die versteckte Datei darf nirgends als Gerät, Image oder Inhalt auftauchen: prüfen in `devices.py` (Laden,
   `delete_folder` „nicht leer“ – ein Ordner nur mit der Farbdatei gilt als leer und wird samt Datei gelöscht),
   `archive.py` (`scan` überspringt Punktdateien schon – bestätigen; Löschen leerer Ordner analog), Export/Inventar,
   Transfer (`transfer.py`) und überall, wo Ordnerinhalte gezählt oder kopiert werden.
3. Kontextmenü auf Ordnern: Eintrag „Farbe …“ mit Untermenü bzw. kleinem Dialog (Farbfelder + Namen, „Keine“).
   Geräteliste: bei Ordner-Menüs in `ui.py` (~2398 „Ordner umbenennen …“); Archiv: bei den Ordner-Menüs
   (~794/896/903 „Umbenennen …“). Nicht für den Ordner „Virtuelle Maschinen“ (VM_FOLDER) – oder dort erlaubt,
   falls trivial; sonst ausblenden.
4. Anzeige: farbiger Punkt bzw. kurzer Balken vor dem Ordnernamen in beiden Bäumen (z. B. Pixbuf/Icon-Spalte oder
   Markup `●`), lesbar im hellen und dunklen Design (je Farbe passender Ton). Ohne Farbe: unverändert.
5. Tests: get/set/None, kaputte Datei, Farbe bleibt nach `rename_folder`/`move_folder` (devices und archive),
   versteckte Datei erscheint nicht als Gerät/Image, leerer Ordner mit Farbdatei lässt sich löschen.

## Nicht Teil dieses Auftrags

- Farben für einzelne Geräte oder Images, freie Farbwahl, Farbe in Exporten/PDF.
- Änderungen an `nas.py` (`rename_retry`) – parallel arbeitet B-031 dort.

## Hinweise zum Code

- Agent betroffen? nein (kein neuer Agent-Stick).
- Reihenfolge: Logik + Tests, dann Oberfläche, zuletzt Hilfe/Doku.

## Oberfläche und Texte

- Menüeintrag „Farbe …“; Farben z. B. Rot, Orange, Gelb, Grün, Türkis, Blau, Violett, Grau; „Keine Farbe“.
- Schreibstil laut `CLAUDE.md`.

## Abnahmekriterien

- [ ] Farbe setzen/entfernen in Geräteliste und Archiv; bleibt nach Umbenennen, Verschieben und Neustart des Tools
- [ ] Farbdatei taucht nirgends als Inhalt auf; leere eingefärbte Ordner lassen sich löschen
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .` (genau so, ohne `cd`, ohne Pipe, ohne `2>&1`)
- [ ] Hilfe (F1) in `okula_recovery/help_window.py` ergänzt, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: **nur den eigenen Eintrag I-043** auf erledigt und ins Protokoll (26.11.) –
      Kurzübersicht und „Als Nächstes“ nicht anfassen
- [ ] `docs/TESTS.md`: kurzer Abschnitt „I-043“ mit Prüfschritten am Server

## Abschluss

1. Commits `I-043: …`, nur lokal auf `agent/I-043`, nur eigene Dateien (`git add <Pfade>`, nie `-A`/`.`).
2. Oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Rückmeldung: was geändert, Commits, Testergebnis, Abweichungen, Schritte für den Server.
