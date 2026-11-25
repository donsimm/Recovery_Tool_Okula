# B-025 – Automatisierung löscht BitLocker-Disk ohne Backup

Status: offen · erstellt 25.11.2026 von der Projektleitung (Code-Review) · Freigabe: Dominik 25.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag B-025 in `docs/AENDERUNGEN.md`,
`docs/REVIEW-2026-11-25.md` (R-client Befund 2), `docs/AUTOMATISIERUNG.md`. Lokaler Branch `agent/B-025`;
nicht pullen, nicht pushen. 1–2 Commits.

## Befund (am Code bestätigt)

- `automation.py` ~Zeile 560–579, Schritt 1 „Backup: Benutzerdaten“ (`s.backup` und nicht `backup_mode == "image"`):
  `backups.get_profiles()` → Agent `filebackup.profiles()`. Eine BitLocker-Partition kommt dort mit
  `"error": "BitLocker – nicht lesbar"` und `users: []` zurück (`filebackup.py` ~125); ebenso Partitionen, die sich
  nicht einhängen lassen (`entry["error"] = str(e)`, z. B. Windows im Ruhezustand/Schnellstart, NTFS dirty).
- Die Automatisierung ignoriert `error`, findet keine Benutzer, loggt „Keine Benutzerprofile auf der Zieldisk –
  nichts zu sichern“ und **löscht danach die Disk**. Realer Fall 25.11.: HP ZBook mit BitLocker.

## Anforderungen

1. Backup „Benutzerdaten“ gewählt und auf der Zieldisk gibt es eine Partition mit `error` (BitLocker oder nicht
   lesbar) → **Lauf abbrechen, nichts löschen**. Meldung im Verlauf/Banner klar, z. B.
   „Backup nicht möglich: <Partition> ist mit BitLocker verschlüsselt – nichts gelöscht. BitLocker in Windows
   ausschalten oder Backup ‚ganze Disk‘ wählen.“ (Text für nicht lesbare Partition sinngemäss, inkl. Hinweis
   Schnellstart/Ruhezustand). Phase = Fehler, Automatisierung bleibt eingeschaltet (wie bei anderen Fehlern vor dem
   Löschen – bestehendes Verhalten prüfen und angleichen).
2. Keine Partition mit `error`, aber auch keine Benutzer (leere Disk, Linux ohne /home, Windows ohne Profile) →
   wie bisher weiter, Log-Zeile bleibt.
3. Gleiches Muster prüfen für andere Stellen, an denen vor dem Löschen ein Datei-Backup gemacht wird
   (z. B. `jobs.py`/`ui.py` beim Zurückspielen mit „vorher sichern“, falls vorhanden) – nur beheben, wenn dort
   derselbe stille Ausfall belegbar ist; sonst in der Rückmeldung erwähnen.
4. Tests (unittest, bestehende Muster in `tests/` für automation nachbilden): BitLocker-Partition → Abbruch ohne
   Löschauftrag an den Agent; unlesbare Partition → Abbruch; keine Profile ohne Fehler → läuft weiter.
5. Doku: Eintrag B-025 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (25.11.) verschieben (Muster
   der übrigen Einträge), `docs/AUTOMATISIERUNG.md` falls dort das Backup beschrieben ist, `docs/TESTS.md` kurzer
   Abschnitt „B-025“ (VM oder ZBook mit BitLocker: Automatisierung mit Backup Benutzerdaten → Abbruch, Disk unverändert).
   Hilfe (F1) nur, wenn dort das Backup der Automatisierung beschrieben ist.

## Grenzen

- Nicht in `ui.py`, `archive.py`, `jobs.py` (ausser Punkt 3 belegt) ändern – dort arbeitet parallel B-026.
- Kein BitLocker-Entsperren (das ist I-012).
- Tests ausführen: `python3 -m unittest discover -s tests -t .` – alle grün vor dem Commit.
