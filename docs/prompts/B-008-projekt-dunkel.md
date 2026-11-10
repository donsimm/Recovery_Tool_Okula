# B-008 – Projektübersicht im Dunkelmodus: Auswahlfelder lesbar

Status: freigegeben · erstellt 10.11.2026 von der Projektleitung · Freigabe: Dominik 10.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, den Eintrag B-008 in `docs/AENDERUNGEN.md`,
`okula_recovery/assets/projekt/style.css`, `index.html`, `app.js`. Gearbeitet wird in der eigenen Kopie
(lokaler Branch `agent/B-008`); nicht pullen, nicht pushen. Shell-Befehle einzeln ausführen.

## Ziel

Extras → Projektübersicht … (öffnet in Firefox) ist im Dunkelmodus überall gut lesbar, besonders die
Auswahlfelder „Art der Notiz“ (z. B. „Idee“) und der Filter „Priorität: alle“ – heute hellgrau auf weiss.

## Befund (Okuli, 10.11.)

- `style.css` setzt Farben über Variablen mit `@media (prefers-color-scheme: dark)`, aber kein `color-scheme`.
  Firefox zeichnet `<select>` und die aufgeklappte Liste (`<option>`) darum mit hellen Systemfarben,
  während `color: inherit` die helle Schrift übernimmt → hell auf hell.

## Anforderungen

1. Dunkelmodus: `<select>` geschlossen und aufgeklappt (Optionen), Eingabefelder, Textfeld und Knöpfe haben
   dunklen Hintergrund und helle Schrift. Hellmodus unverändert.
2. Lösung über CSS: `color-scheme: light dark` auf `:root` (bzw. `dark` im Dark-Block) und, wo nötig,
   ausdrückliche Farben für `option` (`background: var(--card); color: var(--text)`).
3. Restliche Seite im Dunkelmodus kurz durchsehen (Platzhaltertext, Fokusrahmen, deaktivierte Felder,
   Scrollbalken) und offensichtlich Unlesbares mitbeheben – nur Farben, kein Umbau.

## Nicht Teil dieses Auftrags

- Keine Änderungen an Layout, Funktionen, `projekt.py`/`projekt_server.py` oder dem GTK-Tool.
- Kein Umschalter hell/dunkel.

## Hinweise zum Code

- Agent betroffen (neuer Agent-Stick nötig)? nein.
- Falls es Tests zu den Assets gibt (z. B. `tests/test_projekt*.py`), diese grün halten.

## Oberfläche und Texte

- Keine neuen Texte. Hilfe (F1) nur anpassen, falls dort etwas zu Farben/Dunkelmodus der Projektübersicht steht.

## Abnahmekriterien

- [ ] CSS wie oben; Hellmodus sieht aus wie vorher
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`
- [ ] `docs/AENDERUNGEN.md`: B-008 ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: unter „Offen“ (Abschnitt 12 Projektübersicht): „Dunkelmodus: Art der Notiz und Filter
      Priorität lesbar, auch aufgeklappt“

## Abschluss

1. Ein Commit `B-008: Projektübersicht dunkel lesbar`, **nur lokal** auf `agent/B-008` – **nicht pushen**.
   **Nur eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit danach ist ok).
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis, offene Punkte oder Abweichungen vom Prompt.
