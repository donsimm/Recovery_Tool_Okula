# B-020 – Windows anpassen: Startmenü und Widgets offline setzen, Okula-Startskripte gleichzeitig

Status: umgesetzt (Commit 62f5b1f, Doku 3f5f493) · erstellt 24.11.2026 von der Projektleitung · Freigabe: Dominik 24.11. (Gesamttest an der VM)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge B-020, B-019, B-018, B-017, Ä-044 in
`docs/AENDERUNGEN.md`, Prompts B-019 und B-018. Lokaler Branch `agent/B-020`; nicht pullen, nicht pushen. 2–3 Commits.

## Befund (Okuli, 24.11., VM-Win11-clean ab „frisch“, mit B-019 und neuem Agent)

- **B-019 hilft nicht:** `SyncForegroundPolicy` = 1 war offline gesetzt (geprüft), sauberer Hive, hivexsh-Weg
  funktioniert. Die Gruppenrichtlinie war um 10:31:59 vor der Anmeldung fertig (Ereignis 8000). Die Anmeldung kam um
  10:32:01, das Okula-Skript startete trotzdem erst um 10:32:06. Windows wartet bei der Anmeldung also nicht auf
  Startskripte; auf diesen Weg ist kein Verlass.
- **Startskripte gleichzeitig:** `okula-windows-anpassen` und `okula-software` starteten beide um 10:32:06–08 und
  räumten gleichzeitig auf. Folge im Software-Protokoll: FEHLER „Registrierung Scripts\Startup nicht ganz
  aufgeräumt … `…\Startup\0\0` nicht vorhanden“ und „SyncForegroundPolicy nicht zurückgesetzt … nicht vorhanden“
  (das andere Skript war schneller). `Restore-OkulaStart` geht von nacheinander laufenden Skripten aus.
- Startmenü wie in B-019 vorgesehen nicht zurückgesetzt („Okula-test beim Lauf angemeldet“). Sonst alles ok.

## Ziel

Alles, was **vor der ersten Anmeldung** wirken muss, schreibt der **Agent offline** beim Senden (Windows aus, Disk
eingehängt). Den Hive-Schreibweg aus B-019 (`set_sync_policy`: Kopie → `hivexsh -w` → prüfen → zurück, sauberer
Hive) dafür verallgemeinern. Das Startskript macht den Rest, auch wenn es parallel zur Anmeldung läuft.

## Anforderungen

1. **Offline beim Senden von „Windows anpassen“** (nur für die gewählten Optionen; Build aus dem Hive,
   `CurrentBuild`):
   - `START_CLEAN`, ab Build 26100:
     - `%ProgramData%\Okula\StartPins.json` schreiben (Inhalt wie heute, UTF-8 ohne BOM).
     - Im Hive `SOFTWARE` `Policies\Microsoft\Windows\Explorer` die Werte `ConfigureStartPins` = 1 (DWORD) und
       `ConfigureStartPinsJSON` = Pfad (REG_EXPAND_SZ, z. B. `%ProgramData%\Okula\StartPins.json`, oder den absoluten
       Pfad) setzen.
     - In **allen** Profilen unter `Users\*\AppData\Local\Packages\Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy\LocalState`
       `start2.bin`/`start.bin` in `*.okula-<Zeitstempel>` umbenennen.
   - Widgets: `Policies\Microsoft\Dsh\AllowNewsAndInterests` = 0 (DWORD).
   - Mehrere Werte in **einem** hivexsh-Lauf pro Schlüssel. Vorhandene Werte mitschreiben wie in B-019, danach prüfen.
     Fehler → Hive unverändert, Hinweis im Auftragslog. Das Startskript setzt die Werte wie heute zusätzlich
     (doppelt schadet nicht, und so bleibt es wirksam, falls offline nicht ging).
   - Im Startskript: Das Umbenennen von `start2.bin` und das Nachholen im Nachlauf (`-StartSids`) entfallen, wenn
     offline schon umbenannt wurde. Dafür eine Marke ablegen, z. B. `%ProgramData%\Okula\start-offline.ok`. Ohne Marke
     wie heute (Hinweis bzw. Nachholen). Protokolltext anpassen.
2. **SyncForegroundPolicy (B-019) zurückbauen:** nicht mehr setzen. Restore bleibt für Altlasten: Liegt
   `GroupPolicy\SyncForegroundPolicy.okula-nachher` noch, wird der Stand wiederhergestellt. Doku und Hilfe: Satz „die
   Anmeldung wartet“ entfernen, Befund oben in TECHNIK.md festhalten (Windows wartet nicht auf Startskripte).
   `hivexsh`-Weg und Prüfungen bleiben als allgemeine Funktion.
3. **Gleichzeitige Okula-Startskripte:** `Restore-OkulaStart` (auch Software) mit einer Sperre ausführen
   (z. B. benannter Mutex `Global\OkulaStartRestore` in PowerShell, Wartezeit mit Grenze). Nur das **letzte**
   Skript stellt `gpt.ini`/`scripts.ini` und Altlasten her. „Letztes“ gilt erst, wenn das andere Skript seine `.cmd`
   wirklich gelöscht hat; die Entscheidung unter der Sperre treffen. „Eintrag nicht vorhanden“ bzw. „Wert nicht
   vorhanden“, weil das andere Skript schneller war, ist kein FEHLER. Echter Fehler nur, wenn danach noch etwas
   übrig ist. Der Notfall-Teil im `.cmd` (PowerShell startet nicht) bleibt einfach.
4. **Nachlauf:** Der zweite Auslöser „jetzt + 30 min“ aus B-019 bleibt.
5. **Tests:**
   - Offline-Werte für `START_CLEAN` bzw. Widgets (hivexsh nachgebildet wie in `tests/test_sync_policy.py`).
   - Umbenennen in allen Profilen; Marke; das Skript überspringt mit Marke.
   - Kein SyncForegroundPolicy mehr gesetzt, Altlast wird wiederhergestellt.
   - Sperre und „anderes Skript war schneller“ ohne FEHLER.
   - Hilfe (F1), `docs/TESTS.md` Abschnitt 26 „Korrektur B-020“: Startmenü und Wetter sind bei der ersten Anmeldung
     richtig, auch wenn die Anmeldung vor dem Skript kommt; beide Protokolle ohne FEHLER.

## Nicht Teil dieses Auftrags

- Ä-046 (Windows anpassen beim Aufsetzen), Ä-045, I-042.

## Abnahmekriterien

- [ ] Startmenü-Richtlinie, JSON, Widgets-Richtlinie und Umbenennen `start2.bin` offline beim Senden
- [ ] SyncForegroundPolicy nicht mehr gesetzt; Altlast wird zurückgestellt
- [ ] Zwei gleichzeitige Okula-Startskripte räumen ohne falschen FEHLER auf
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md`

## Abschluss

1. Commit(s) mit `B-020: …` im Titel, nur lokal auf deinem Branch; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis (oder: Tests nicht ausführbar), Quellen, neuer
   Agent-Stick ja/nein, offene Punkte.
