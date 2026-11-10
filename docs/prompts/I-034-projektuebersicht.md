# I-034 – Projektübersicht im Tool

Status: umgesetzt (Commit 0910836) · erstellt 10.11.2026 von der Projektleitung · Freigabe: Dominik 10.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag I-034 in `docs/AENDERUNGEN.md`,
den Aufbau von `docs/TESTS.md`, `docs/AENDERUNGEN.md`, `docs/UEBERGABE.md` und den `Status:`-Zeilen in `docs/prompts/*.md`
(diese Dateien sind die Datenquelle). Arbeitsbranch `claude/blissful-goldberg-mo3xda`; vorher `git pull`.

## Ziel

Dominik soll den ganzen Projektstand an einem Ort sehen und direkt Rückmeldungen geben können: Unter
**Extras → Projektübersicht …** öffnet sich in Firefox eine interaktive Seite mit allen offenen Tests (abhaken oder
kommentieren), allen offenen Bugs, Änderungen und Ideen (kommentieren, Priorität oder Status als Wunsch), den offenen
Punkten der letzten Übergabe und den Prompts mit Status. Die Rückmeldungen landen in einer Datei, die die
Projektleitung liest und in die Doku überträgt. Die Seite ändert **nie** selbst die Markdown-Dateien.

## Entscheide aus dem Brainstorming

- Ort: **im Tool**, Menü Extras (Dominik 10.11.), nicht als externe Webseite.
- Datenquelle: **live aus dem Repo** `~/recovery_tool_okula/docs` (nach `git pull` sofort aktuell, ohne Installation);
  Ordner änderbar (Dominik 10.11.).
- Anzeige: **Firefox**, kleiner Webserver im Tool-Prozess, **nur auf 127.0.0.1** (Dominik 10.11.).
- Rückmeldungen: Datei **ausserhalb von Git**, `~/.local/share/okula-recovery/projekt-rueckmeldungen.json`
  (Dominik 10.11.). Die Projektleitung überträgt sie und setzt dabei selbst `uebernommen` in dieser Datei.
- Umfang (Dominik 10.11.): Tests abhaken/kommentieren, Kommentar zu jedem Eintrag, **freie neue Notiz**,
  **Prio-/Status-Wunsch**, **Übersicht oben** mit Zählern, **Suche und Filter**.

## Anforderungen

1. **Menüeintrag** `Projektü_bersicht …` unter `E_xtras` (in `MENU_LABELS`, nach „Neue _virtuelle Maschine …“ mit
   eigenem Trenner davor). Startet beim ersten Aufruf den Webserver und öffnet die Seite mit `uikit.open_url`
   (läuft das Tool unter sudo, öffnet sie als `SUDO_USER`); weitere Aufrufe öffnen nur die Seite erneut.
2. **Webserver:** `ThreadingHTTPServer` in einem Daemon-Thread, gebunden an `127.0.0.1`, freier Port (Port 0).
   Zufälliges Token pro Tool-Start (`secrets.token_urlsafe`) als Teil der URL; alle Anfragen ohne gültiges Token →
   403. Schreibende Anfragen nur per `POST` mit JSON und Token (kein CSRF über fremde Webseiten). Endet mit dem Tool.
   Keine externen Dateien/CDNs: HTML, CSS und JS liegen im Paket (z. B. `okula_recovery/assets/projekt/`).
3. **Projektordner:** Standard `~/recovery_tool_okula` des aufrufenden Benutzers (bei sudo: Home von `SUDO_USER`),
   änderbar unter *Menü → Einstellungen …* (Feld „Projektordner (Repo)“, mit Ordnerwahl), gespeichert in der
   bestehenden Konfiguration. Fehlt der Ordner oder `docs/`, zeigt die Seite einen klaren Hinweis statt eines Fehlers.
4. **Daten bei jedem Laden neu einlesen** (Knopf „Neu laden“ auf der Seite, kein Neustart des Tools nötig):
   - `docs/TESTS.md`, Teil „## Offen – am realen System testen“: Abschnitte `### …` als Gruppen, jede Zeile
     `- [ ]` / `- [x]` als Testpunkt inkl. eingerückter Folgezeilen; Absätze unter der Überschrift als Gruppentext.
     Erledigte (`[x]`) erscheinen abgehakt und grau. Zusätzlich die Liste „## Vorbereitung am neuen Server“.
   - `docs/AENDERUNGEN.md`: die Tabellen 🐞 Bugs, 🔧 Änderungen, 💡 Ideen (alle Spalten), die Kurzübersicht
     (Zähler, Zeilen „Als Nächstes“ und „Vorschlag Reihenfolge“) und „📌 Entscheidungen“ (nur lesen, eingeklappt).
   - `docs/UEBERGABE.md`: Abschnitt „## Offen und als Nächstes“ – jeder nummerierte Punkt ist ein Eintrag.
   - `docs/prompts/*.md` (ohne `VORLAGE.md`): Titel (erste Zeile) und `Status:`-Zeile.
   - Inline-Markdown einfach darstellen (fett, `code`, Links, Kursiv), **alles HTML-escapen** (kein Roh-HTML aus
     den Dateien). Unbekannte Strukturen überspringen statt abstürzen.
5. **Stabile Schlüssel** für Einträge: Bugs/Änderungen/Ideen über ihre ID (`B-004`); Tests und Übergabe-Punkte über
   Abschnitt + normalisierten Text (z. B. SHA-1 der ersten 200 Zeichen ohne Markdown/Leerraum). Jede Rückmeldung
   speichert zusätzlich den angezeigten Text als Kopie. Passt eine Rückmeldung zu keinem Eintrag mehr (Text in der
   Doku geändert), erscheint sie in einem Bereich „Rückmeldungen ohne Eintrag“ – **nichts geht verloren**.
6. **Rückmeldungen pro Eintrag** (Speichern sofort, kleine Bestätigung „gespeichert“):
   - Tests: Häkchen „ok“ bzw. „Fehler“ (zwei Zustände plus leer) und Kommentarfeld.
   - Bugs/Änderungen/Ideen: Kommentar; Wunsch-Priorität (🔴/🟡/⚪); Wunsch-Status (*als Nächstes*, *zurückstellen*,
     *streichen*, *erledigt*).
   - Übergabe-Punkte und Prompts: Kommentar.
   - Angezeigt wird der eigene Wunsch neben dem Ist-Stand aus der Doku (z. B. „Prio 🟡 → Wunsch 🔴“).
7. **Neue Notiz:** Feld oben mit Art (Bug / Änderung / Idee / Frage) und Text → eigener Eintrag in der Datei,
   in der Seite unter „Meine neuen Notizen“ sichtbar und bearbeitbar/löschbar, solange nicht übernommen.
8. **Datei** `~/.local/share/okula-recovery/projekt-rueckmeldungen.json` (Benutzer wie Punkt 3, Rechte 0600,
   Ordner anlegen, bei sudo Besitzer `SUDO_USER`). Atomar schreiben (temp + `os.replace`), Lesefehler → Datei
   als `….defekt-<zeit>.json` beiseitelegen und neu beginnen, mit Hinweis auf der Seite. Aufbau (UTF-8, eingerückt,
   von Hand lesbar):
   ```json
   {"version": 1,
    "eintraege": {
      "<schlüssel>": {"art": "test|bug|aenderung|idee|uebergabe|prompt", "bezug": "Abschnitt 11 / B-004 / …",
                      "text": "<Kopie des Eintrags>", "haken": "ok|fehler|null", "kommentar": "…",
                      "prio_wunsch": "🔴|🟡|⚪|null", "status_wunsch": "…|null",
                      "geaendert": "2026-11-10T14:03:00", "uebernommen": null}},
    "notizen": [{"id": "n-…", "art": "bug|aenderung|idee|frage", "text": "…",
                 "erstellt": "…", "geaendert": "…", "uebernommen": null}]}
   ```
   `uebernommen` setzt nur die Projektleitung (Datum). Übernommene Rückmeldungen zeigt die Seite grau mit
   „übernommen TT.MM.“; eine neue Änderung daran setzt `uebernommen` wieder auf `null`.
9. **Übersicht oben:** Zähler offene Tests je Abschnitt (offen / von dir abgehakt / Fehler), Bugs/Änderungen/Ideen
   offen, Anzahl neuer (nicht übernommener) Rückmeldungen; „Als Nächstes“ aus der Kurzübersicht; Prompts mit Status.
   Stand der Daten: Zeit des Einlesens und `git log -1 --format='%h %cd'` des Projektordners (falls Git verfügbar).
10. **Suche und Filter:** Suchfeld über alle Texte; Filter nach Art (Tests, Bugs, Änderungen, Ideen, Offene Punkte,
    Prompts), Priorität, „nur mit meinen Rückmeldungen“, „nur neue (nicht übernommen)“, „erledigte Tests ausblenden“.
    Filter- und Klappzustand im `localStorage` des Browsers (nur Komfort).
11. Seite schlicht und gut lesbar, hell/dunkel nach Systemeinstellung, brauchbar ab 1024 px Breite; Abschnitte
    einklappbar. Kein Login nötig (nur localhost + Token).

## Nicht Teil dieses Auftrags

- Kein Schreiben in Markdown-Dateien, kein `git`-Schreiben (commit/pull/push) aus dem Tool.
- Kein Zugriff aus dem LAN, keine Benutzerverwaltung (das ist I-004 Webinterface).
- Keine Anzeige von „Bereits geprüft“ und „✅ Erledigt“ (höchstens Zähler).
- Keine Änderungen an Agent, PXE-Dienst oder `install.sh` (ausser falls nötig, Assets mitkopieren – `cp -r okula_recovery`
  kopiert sie bereits).

## Hinweise zum Code

- Neues Modul z. B. `okula_recovery/projekt.py` (Einlesen + JSON-Datei, ohne GTK, gut testbar) und
  `okula_recovery/projekt_server.py` (HTTP); in `ui.py` nur Menüeintrag + Aktion. `ui.py` nicht weiter aufblähen.
- Muster: HTTP-Server wie in `pxe.py` (`ThreadingHTTPServer`, `BaseHTTPRequestHandler`), URL öffnen mit
  `uikit.open_url`, Konfiguration wie bestehende Einstellungen in `config.py`/`settings_dialogs.py`.
- Parser robust gegen die echte Doku testen: Tests mit Kopien von Ausschnitten der echten Dateien (in `tests/data/`)
  und gegen die aktuellen Dateien im Repo (darf nicht abstürzen, findet B-004, Abschnitt 11, I-034).
- Tests: Parser, Schlüssel/verwaiste Rückmeldungen, Datei (atomar, defekte Datei, `uebernommen` zurücksetzen),
  Server (Token fehlt → 403, POST speichert, nur 127.0.0.1).
- Agent betroffen (neuer Agent-Stick nötig)? **nein**.

## Oberfläche und Texte

- Menü: `E_xtras` → `Projektü_bersicht …`; Einstellungen: Feld „Projektordner (Repo)“.
- Seitentitel „Projektübersicht – Okula Recovery Tool“; Knöpfe „Neu laden“, „Speichern“ (falls nicht automatisch),
  „Neue Notiz“; Bereiche „Tests am realen System“, „Bugs“, „Änderungen“, „Ideen“, „Offene Punkte (Übergabe)“,
  „Prompts“, „Meine neuen Notizen“, „Rückmeldungen ohne Eintrag“.
- Schreibstil laut `CLAUDE.md` (Handbuch-Stil ohne Anrede, auch auf der Webseite).
- Hilfe (F1): neues Kapitel „Projektübersicht“ – wozu, wo die Daten herkommen, wo die Rückmeldungen liegen, dass die
  Seite nur lokal erreichbar ist und die Doku erst durch die Projektleitung geändert wird.

## Abnahmekriterien

- [ ] Extras → Projektübersicht … öffnet Firefox mit der Seite; zweiter Aufruf öffnet die gleiche Seite (gleicher Port)
- [ ] Alle offenen Tests aus TESTS.md (Abschnitte 2–11 + Vorbereitung) sind da; Häkchen „ok“/„Fehler“ und
      Kommentar bleiben nach „Neu laden“ und nach Tool-Neustart erhalten
- [ ] Alle offenen Bugs, Änderungen, Ideen mit ID, Prio, Text; Kommentar, Prio- und Status-Wunsch speicherbar
- [ ] Offene Punkte aus UEBERGABE.md und Prompts mit Status sichtbar und kommentierbar
- [ ] Neue Notiz anlegen, ändern, löschen
- [ ] Übersicht oben mit Zählern; Suche und alle Filter wirken
- [ ] Nach Änderung eines Testtexts in TESTS.md erscheint die alte Rückmeldung unter „Rückmeldungen ohne Eintrag“
- [ ] `uebernommen` von Hand in der JSON gesetzt → Eintrag grau „übernommen TT.MM.“; erneute Änderung → wieder neu
- [ ] Anfrage ohne Token → 403; Server nicht von anderer Adresse als 127.0.0.1 erreichbar
- [ ] Projektordner fehlt → verständlicher Hinweis auf der Seite
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .` (bekannt rot: die 4 Tests aus `test_imaging`
      und `test_jobs` laut `docs/UEBERGABE.md` – nicht verschlechtern); neue Tests für Parser, Datei, Server
- [ ] Hilfe (F1) in `okula_recovery/help_window.py` angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: I-034 ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Prüfschritte für das reale System unter „Offen“ (neuer Abschnitt 12)
- [ ] `docs/TECHNIK.md`: Abschnitt „Projektübersicht“ (Datenquelle, Dateiformat, Schlüssel, Sicherheit)
- [ ] Demo-Gerät: nicht nötig

## Abschluss

1. Ein Commit (oder wenige, sinnvoll getrennt) mit der ID im Titel, z. B. `I-034: Projektübersicht im Tool`; pushen auf
   `claude/blissful-goldberg-mo3xda`. **Nur eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`):
   Die Projektleitung arbeitet im selben Ordner, fremde Entwürfe (z. B. andere Dateien in `docs/prompts/`) bleiben liegen.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (im selben Commit).
3. Abschlussmeldung im Chat: was geändert wurde, Testergebnis, ob ein neuer Agent-Stick nötig ist (nein), Schritte für
   den Server (`git pull && sudo ./install.sh`), offene Punkte oder Abweichungen vom Prompt.
