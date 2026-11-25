# B-028 – Fehler werden als ok/Erfolg gemeldet (Sammelpunkt)

Status: abgenommen (Okuli 25.11., Commits 5517106, c824914) · erstellt 25.11.2026 von der Projektleitung (Code-Review) · Freigabe: Dominik 25.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag B-028 in `docs/AENDERUNGEN.md`,
`docs/REVIEW-2026-11-25.md` Abschnitte „R-client“ Befunde **4, 5, 10** und „R-win“ Befunde **1–4**,
`docs/AUTOMATISIERUNG.md`. Lokaler Branch `agent/B-028`; nicht pullen, nicht pushen.
**Zwei Commits:** Teil A (Tool), dann Teil B (Windows-Skripte).

## Teil A – Tool (`automation.py`, `jobs.py`)

1. **Anpassen-Ergebnis (R-client 4, von Okuli bestätigt; `automation.py` ~625–636, `jobs.py` ~462–468):**
   `error` und `not_generalized` – und eine leere Ergebnisliste, wenn ein Windows-Master zurückgespielt wurde –
   sind in der Automatisierung ein **Fehler** (Phase Fehler, Automatisierung bleibt an, kein „erfolgreich“, kein
   Neustart als Erfolg). In `restore_work` mindestens eine Warnung im Ergebnis statt „zurückgespielt und angepasst“.
   `r.get('part', '?')` statt `r['part']`.
2. **`_execute` ohne `except` (R-client 5, `automation.py` ~403–409):** In `_run` jede Ausnahme abfangen →
   `phase="error"`, `run.text` mit Ursache, Verlauf schreiben; der Lauf darf nie auf „running“ hängen bleiben.
3. **Abbruch überdeckt Fehler (R-client 10, `jobs.py` ~164, `automation.py` ~485):** nur als „abgebrochen“ werten,
   wenn die Ausnahme selbst der Abbruch ist (`AgentError("Abgebrochen…")` bzw. bestehendes Muster); sonst Fehler mit
   Ursache in Log, Verlauf und Banner.
4. Tests: je Fall (error, not_generalized, leer bei Windows, KeyError-Fall, Ausnahme in `_execute`, Fehler + später
   Abbruch) nach bestehenden Mustern.

## Teil B – Windows-Skripte (`winsetup.py`, `software.py`, `wintweaks.py`)

1. **R-win 1 (`winsetup.py` ~256–259, dazu `xcopy` in SOFTWARE_COPY/STARTUP_COPY):** nach `copy`/`xcopy`
   `if errorlevel 1 goto fehler` (bzw. bestehendes Fehler-Label); kein „fertig“ und kein `wpeutil reboot` nach
   einem Kopierfehler, Fehler im Log.
2. **R-win 2 (`software.py` ~1252):** fehlende Installer beim **ersten** Lauf als FEHLER zählen; „schon erledigt“
   nur, wenn das Log bereits einen ok-Eintrag für dieses Programm hat (oder Marke pro Programm).
3. **R-win 3 (`wintweaks.py` ~1371–1375, `Invoke-OkulaAllUsers`):** scheitert `reg unload` in allen Versuchen →
   als Hinweis/Fehler protokollieren statt verschlucken.
4. **R-win 4 (`wintweaks.py` ~368, ~277–278):** Zeilen, die eine Einschränkung melden („wirkt evtl. nicht“, „wirkt
   bei $edition nicht“), mit Präfix „Hinweis: “, damit der Mechanismus aus B-022 (~1001) sie als Hinweis zählt.
   Den `$adsNote`-Teil (B-023) und OneDrive (B-024) **nicht** anfassen – eigene Einträge.
5. Tests: bestehende Tests für erzeugte Skripte erweitern (Text enthält Prüfungen/Präfixe).

## Doku

Nur den eigenen Eintrag B-028 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum heute)
verschieben – **Kurzübersicht und „Als Nächstes“ nicht anfassen** (macht Okuli). `docs/TESTS.md` Abschnitt „B-028“
(Automatisierung mit nicht generalisiertem Master → Fehler statt Erfolg; Software-Installation mit fehlendem
Installer → FEHLER im Protokoll). `docs/AUTOMATISIERUNG.md` und Hilfe (F1) anpassen, wo das Ergebnis der
Automatisierung beschrieben ist.

## Grenzen

- **Nicht** `agentclient.py` (dort arbeitet parallel B-027), nicht `ui.py`, nicht `agent.py`.
- Kein neuer Agent-Stick nötig (Skripte erzeugt das Tool); falls doch, in der Rückmeldung sagen.
- Tests ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .` –
  alle grün vor jedem Commit.
- Rückmeldung: was geändert (Teil A/B getrennt), Commits, Testergebnis, Offenes.
