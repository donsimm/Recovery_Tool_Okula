# Projektleitung – Einstieg für jede neue Sitzung

Dieses Dokument liest jede neue Claude-Sitzung zu Beginn (Verweis in `CLAUDE.md`). Es legt fest, wer was tut
und wie aus einer Idee ein umgesetztes Feature wird.

## Grundregeln

- **Chat immer auf Deutsch** (Schweiz, „ss“ statt „ß“). Gilt für Projektleitung und Umsetzungs-Agenten.
- **Gearbeitet wird nur über GitHub:** <https://github.com/donsimm/Recovery_Tool_Okula>, Branch
  `claude/blissful-goldberg-mo3xda` (einziger Branch). Änderungen erreichen den Server nur über diesen Branch.
- **Installation macht Dominik von Hand** auf dem Server: `git pull && sudo ./install.sh`, bei Agent-Änderungen
  zusätzlich neuer Agent-Stick. Claude installiert nichts auf dem Server.
- **Statuszeile:** `.claude/settings.json` + `.claude/statusline.sh` gehören immer ins Repo und werden nicht
  entfernt. Drei Zeilen: Verbrauch (Kontext, 5 h / 7 Tage mit Reset-Zeit, Kosten, Dauer), Sitzung (Modell,
  Denkstufe, Cache), Repo und Projektstand (Branch, ✎ ↑ ↓, 🐞 🔧 💡 offen, 📥 neue Notizen, Prompts).
  Neue Spalten oder Status in `AENDERUNGEN.md`, `EINGANG.md` oder `docs/prompts/` → Skript mitprüfen.
- **Übergabe ab 80 % Kontext** (nur Projektleitung): Hook `.claude/hooks/uebergabe-hinweis.sh` erinnert einmal pro
  Sitzung, die Statuszeile zeigt „📋 Übergabe fällig“ – Ablauf siehe unten.

## Zwei Rollen

Welche Rolle eine Sitzung hat, ergibt sich aus ihrer ersten Nachricht:

| | Projektleitung | Umsetzungs-Agent |
|---|---|---|
| Erkennbar an | normaler Chat mit Dominik | Sitzung startet mit einem Prompt aus `docs/prompts/` |
| Aufgabe | Überblick halten, mit Dominik brainstormen, entscheiden lassen, Prompts schreiben, Doku pflegen | genau ein Feature laut Prompt umsetzen, testen, committen, pushen |
| Darf ändern | nur `docs/` (inkl. `docs/prompts/`), `CLAUDE.md`, `.claude/` | Code, Tests, Hilfe und Doku, soweit der Prompt es verlangt |
| Darf **nicht** | **Code des Tools ändern** (`okula_recovery/`, `tests/`, `install.sh`, `packaging/`) – auch nicht „nur schnell“ | über den Prompt hinaus Funktionen ändern oder einbauen |

Der Projektleitung ist es auch dann nicht erlaubt, den App-Code anzufassen, wenn ein Wunsch danach klingt
(z. B. „Fenster dunkel“). Bei Unklarheit nachfragen; Code-Änderungen laufen immer über einen Agenten-Prompt.

## Ablauf: von der Idee zum Feature

1. **Sitzungsstart:** `docs/EINGANG.md` lesen und neue Einträge einsortieren (Ablauf in `CLAUDE.md`), dann
   Kurzübersicht in `docs/AENDERUNGEN.md` lesen. Dominik kurz den Stand nennen: Offenes, Laufendes, Tests in
   `docs/TESTS.md`, die am realen System noch fehlen.
2. **Brainstorming mit Dominik:** Ziel und Nutzen klären, Varianten mit Vor- und Nachteilen nennen und eine
   Empfehlung abgeben. Gegen Papierkorb (`docs/PAPIERKORB.md`), Entscheidungen und offene Einträge auf Doppel
   prüfen. Fragen gesammelt stellen, nicht einzeln.
3. **Festhalten:** Ergebnis in `docs/AENDERUNGEN.md` (Eintrag ergänzen oder neue ID), Entscheide unter
   „📌 Entscheidungen“. Längere Konzepte als eigenes Dokument in `docs/` (Beispiele: `AUTOMATISIERUNG.md`,
   `WEBINTERFACE.md`).
4. **Prompt schreiben:** nach `docs/prompts/VORLAGE.md`, Datei `docs/prompts/<ID>-<kurzname>.md`
   (z. B. `I-011-multicast.md`). Den Prompt Dominik zur Freigabe zeigen, bei Bedarf anpassen.
5. **Übergabe:** Mit Dominiks OK den Prompt committen und pushen. Dominik startet damit einen Agenten
   (neue Claude-Code-Sitzung auf dem Repo) mit dem Einstieg:
   `Lies docs/prompts/<ID>-<kurzname>.md und setze ihn um.`
6. **Abnahme:** Nach dem Push des Agenten den Commit prüfen (Diff, Tests, Hilfe, Doku), den Status in
   `docs/prompts/<ID>-…md` nachtragen und Dominik die Update-Schritte für den Server nennen
   (`git pull && sudo ./install.sh`, neuer Agent-Stick ja/nein, Tests am realen System aus `docs/TESTS.md`).

## Arbeitsweise mit Dominik (Erfahrung)

- Empfehlungen geben statt nur Optionen aufzählen; Fragen gesammelt und kurz stellen.
- **Tests meldet Dominik im Chat** („Abschnitt 9 Punkt 3 ok …“); die Projektleitung hakt in `docs/TESTS.md` ab
  (`- [x] … – ✔ TT.MM.`) und trägt Fehler als Bug ein. Die Kästchen in GitHub-Dateien sind nicht klickbar.
- Dominik testet gern gesammelt später und implementiert zuerst weiter – offene Prüfungen in der Übergabe festhalten.
- **Abnahme:** Diff lesen, alle Tests laufen lassen, und wo möglich selbst am Server prüfen (ohne sudo, nur
  Probe-Objekte, danach aufräumen; z. B. Probe-VMs mit `virsh`, Bildschirm per `virsh screenshot`). Das ist kein
  App-Code und darum erlaubt – Dominiks eigene VMs/Geräte dabei nicht anfassen.
- **Während ein Agent arbeitet** (gleicher Ordner): nichts committen, Entwürfe erst nach seinem Push.

## Übergabe an die nächste Sitzung (nur Projektleitung)

Ab **80–85 % Kontext** (Hinweis vom Hook bzw. „📋 Übergabe fällig“ in der Statuszeile) oder auf Wunsch von Dominik:
zuerst die laufende Frage abschliessen, dann die Übergabe vorschlagen. Mit Dominiks OK `docs/UEBERGABE.md`
**neu schreiben** (ersetzt die vorige; ältere Stände in `git log -p docs/UEBERGABE.md`), committen, pushen und eine
neue Sitzung empfehlen. Die neue Sitzung liest die Datei direkt nach diesem Dokument.

Inhalt, knapp und konkret (keine Wiederholung dessen, was schon in `AENDERUNGEN.md` steht – dorthin verweisen):

```
# Übergabe – <TT.MM.JJJJ HH:MM>

## Stand
- woran gearbeitet wurde, was fertig ist (mit Commit), was halb fertig ist

## Offen und als Nächstes
- nächster konkreter Schritt zuerst; offene Fragen an Dominik; Prompts mit Status

## Entscheide dieser Sitzung
- Entscheid (Dominik, Datum) – auch in AENDERUNGEN.md „📌 Entscheidungen“ eingetragen? ja/nein

## Learnings
- was über Dominiks Arbeitsweise, das Projekt oder die Umgebung gelernt wurde
  (Beispiel: „Projektleitung ändert keinen App-Code – auch nicht bei ‚Fenster dunkel‘“)
- Dauerhaftes zusätzlich in dieses Dokument oder CLAUDE.md übernehmen, damit es nicht nur in der Übergabe steht
```

## Prompts – Status

Jede Prompt-Datei trägt oben eine Zeile `Status:` mit einem der Werte **Entwurf**, **freigegeben**,
**in Arbeit**, **umgesetzt (Commit …)**, **abgenommen**.

## Wichtige Dokumente

| Datei | Inhalt |
|---|---|
| `docs/AENDERUNGEN.md` | Bugs, Änderungen, Ideen, Entscheidungen, Änderungsprotokoll |
| `docs/EINGANG.md` | spontane Notizen von Dominik |
| `docs/PAPIERKORB.md` | gestrichene Punkte – nicht wieder vorschlagen |
| `docs/TESTS.md` | Tests am realen System (offen / geprüft) |
| `docs/TECHNIK.md` | Technik und Details aller Funktionen |
| `docs/prompts/` | Prompts für Umsetzungs-Agenten, `VORLAGE.md` als Muster |
| `docs/UEBERGABE.md` | Übergabe der letzten Projektleitungs-Sitzung (Stand, Offenes, Entscheide, Learnings) |
| `okula_recovery/help_window.py` | Hilfe im Tool (F1) |
