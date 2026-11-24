# B-018 – Windows anpassen: Startmenü bei bestehenden Konten, Registry-Reste beim Aufräumen

Status: umgesetzt (Commit bd17480) · erstellt 24.11.2026 von der Projektleitung · Freigabe: Dominik 24.11. (Test an der VM)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge B-018, B-017, Ä-042, Ä-044 in
`docs/AENDERUNGEN.md`, `docs/prompts/B-017-win11-startpins.md`. Lokaler Branch `agent/B-018`; nicht pullen, nicht
pushen. 1–2 Commits.

## Befund (Okuli, 24.11., VM-Win11-clean, Windows 11 Pro 25H2, über den QEMU-Gastagenten geprüft)

1. **Startmenü:** Die Richtlinie aus B-017 (`ConfigureStartPins` = 1, `ConfigureStartPinsJSON` = Pfad,
   `applyOnce: true`) ist korrekt gesetzt.
   - Neues lokales Konto „Probe“, erste Anmeldung: genau die 9 Kacheln aus `START_PINS` in der richtigen Reihenfolge.
   - Bestehendes Konto „Okula-test“ (seit 19.11. mehrfach an- und abgemeldet, mehrere Neustarts): Startmenü
     unverändert. Erst nachdem `C:\Users\Okula-test\AppData\Local\Packages\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\LocalState\start2.bin`
     umbenannt war, zeigte die nächste Anmeldung die 9 Kacheln. Windows hat eine neue `start2.bin` angelegt.
   - Schluss: Bei bestehenden Profilen hat die gespeicherte `start2.bin` Vorrang. Der Protokolltext „wirkt bei der
     nächsten Anmeldung, auch für bestehende Benutzer“ stimmt so nicht.
2. **Aufräumen (`RESTORE_START`, `wintweaks.py` um Zeile 521, auch von `software.py` genutzt):**
   ```powershell
   $s = [string](Get-ItemProperty -LiteralPath $entry.PSPath -ErrorAction SilentlyContinue).Script
   ```
   wirft `System.InvalidCastException`. Windows legt beim Ausführen des Startskripts den Wert `ExecTime` als
   REG_QWORD mit 16 Byte an, und `-ErrorAction SilentlyContinue` fängt das nicht ab. Folge: Die Einträge mit
   `Script = okula-software.cmd` unter `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\Scripts\Startup\0\0`
   und `…\Group Policy\State\Machine\Scripts\Startup\0\0` bleiben liegen. `scripts.ini` ist entfernt, also ohne Wirkung,
   aber unsauber.

## Anforderungen

1. **Startmenü bestehender Konten (Option `START_CLEAN`, ab Build 26100):** Für jedes vorhandene Benutzerprofil
   (`Win32_UserProfile`, nicht `Special`, Ordner unter `C:\Users`) die `start2.bin` (und, falls vorhanden, `start.bin`)
   im oben genannten `LocalState` in `start2.bin.okula-<Datum>` umbenennen, nicht löschen. Ist das Profil gerade
   geladen (Datei gesperrt), dann Hinweis im Protokoll, kein FEHLER. Die Option läuft im Startskript vor der Anmeldung,
   dort sollte nichts gesperrt sein. Protokollzeile nennt die Anzahl der betroffenen Profile. Den Text so anpassen, dass
   er stimmt, auch im Tooltip und in der Hilfe: „gilt für neue Konten und – einmalig zurückgesetzt – für bestehende;
   eigene Anheftungen der Benutzer gehen dabei verloren.“ Vor 24H2 (MDM-Bridge) nichts ändern.
2. **Nachlauf:** `start2.bin` dort **nicht** nochmals umbenennen. Die Benutzer sollen danach selbst anheften
   können.
3. **Aufräumen:** Den Wert `Script` ohne Umwandlung aller Werte lesen, z. B.
   `(Get-Item -LiteralPath $entry.PSPath).GetValue('Script')`. Einträge mit dem eigenen Skriptnamen entfernen und eine
   leere GPO-Liste wie bisher löschen. Prüfen, ob nach dem Entfernen die Nummerierung (`0`, `1`, …) lückenlos sein
   muss, und wenn nötig nachnummerieren (Quelle angeben oder als ungeprüft vermerken). Fehler hier als Hinweis, nicht
   als Abbruch des Aufräumens.
4. **Reste früherer Läufe:** Beim nächsten Lauf von *Windows anpassen* oder *Software installieren* auch Einträge
   entfernen, die auf ein `okula-*.cmd` zeigen, das nicht mehr im Startup-Ordner liegt (Altlasten aus B-018).
5. **Tests:** Das Skript enthält das Umbenennen von `start2.bin` nur bei `START_CLEAN` und ab Build 26100, und nicht
   im Nachlauf. Das Aufräumen nutzt `GetValue('Script')` und kein `Get-ItemProperty … .Script` mehr. Der Altlasten-Fall
   ist abgedeckt.

## Nicht Teil dieses Auftrags

- Andere Optionen, Paketlisten, „Empfohlen“-Bereich.
- Agent-Code. Voraussichtlich ist **kein neuer Agent-Stick** nötig; bestätigen.

## Abnahmekriterien

- [ ] Bestehende Profile: `start2.bin` umbenannt (Sicherung), Protokoll mit Anzahl; Nachlauf ohne Umbenennen
- [ ] Texte (Protokoll, Tooltip, Hilfe F1) stimmen
- [ ] Aufräumen ohne InvalidCastException; eigene Einträge und Altlasten entfernt
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (B-018 ins Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md` Abschnitt 26
      („Korrektur B-018“: bestehendes Konto zeigt nach dem Lauf die festen Kacheln; Registry ohne `okula-*`-Einträge
      unter `Group Policy\Scripts\Startup` und `State\Machine\Scripts\Startup`)

## Abschluss

1. Commit(s) mit `B-018: …` im Titel, nur lokal auf `agent/B-018`; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis, Quellen, neuer Agent-Stick ja/nein, offene Punkte.
