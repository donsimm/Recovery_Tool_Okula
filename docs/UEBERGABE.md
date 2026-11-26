# Übergabe – 26.11.2026 (Stand nach Sitzung 25./26.11.)

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` → `~/okuli/UEBERGABE.md` → Dominik den Stand nennen.

## Stand (alles gepusht, Branch `claude/blissful-goldberg-mo3xda`, letzter Code-Commit f91cea8 (I-012), Tests 918 OK)

- **B-027** (Image unvollständig als fertig; Ordnername; Schlüsseldatei atomar; Esc-Countdown) – 8a0b686.
- **B-028** (Anpassen-Fehler/Ausnahmen/Abbruch in Automatisierung; Windows-Skripte: Kopierfehler, fehlende
  Installer, `reg unload`, „Hinweis: “) – 5517106, c824914.
- **I-012 BitLocker entsperren** (nur lesend, Datei-Backups; Schlüssel optional pro Gerät root-only in
  `/etc/okula-recovery/bitlocker/`, Root-Helfer `okula-bitlocker` per sudo) – e908064, 4deceae, f91cea8.
  Entscheide unter „📌 Entscheidungen“.
- Alle drei von Okuli abgenommen (Diff, Tests), **am realen System ungeprüft** – TESTS.md „B-027“, „B-028“, „I-012“.
  Server: `git pull && sudo ./install.sh`, **neuer Agent-Stick und Netzwerkstart neu vorbereiten** (dislocker).
- Ideen eingeordnet: ID-0003 → **I-043** Ordner einfärben (Geräteliste + Archiv); I-012 war auf 🔴 hochgestuft.

## Als Nächstes (Reihenfolge Dominik 25.11.)

1. **I-042 Office** – Fragen an Dominik gestellt 26.11., dann Prompt.
2. **Software-Bibliothek: Info-Feld** (Wunsch Dominik 26.11.) – als Ä-050 erfassen, Umfang mit Dominik klären.
3. **I-043** Ordner einfärben.
4. Kleines: Ausführungsrecht `packaging/okula-bitlocker` im Repo; BitLocker-Schlüssel beim Zusammenführen von
   Geräten übernehmen; `ui.py:135` Startdialog bei kaputter Schlüsseldatei; `ui.py:4202` „abgebrochen“ im Verlauf
   (bei Ä-048). Dann Ä-047/B-023/B-024, Datensicherheit (I-016, I-006, Ä-003), I-017, I-011.

## Learnings
- **5-h-Limit:** zwei opus-medium-Agenten (B-027/B-028) ≈ 45 %, I-012 allein (3 Teile, 18 Min., $6.86) ≈ 50 %.
  Vor jedem Start Statuszeile prüfen (`~/.claude/state/statusbar/*.json`, `five_hour`).
- Parallele Agenten nur mit getrennten Dateien; Befunde dafür notfalls zwischen Einträgen verschieben (R-client 9 → B-027).
- Agenten können `chmod`/`git update-index --chmod` nicht – Ausführungsrechte für neue Skripte im Prompt erwähnen
  oder nachher setzen lassen.
