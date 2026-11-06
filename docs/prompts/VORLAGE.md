# <ID> – <Titel>

Status: Entwurf · erstellt <TT.MM.JJJJ> von der Projektleitung · Freigabe: <offen | Dominik TT.MM.>

> Vorlage für Prompts an Umsetzungs-Agenten. Kopieren nach `docs/prompts/<ID>-<kurzname>.md`, alle `<…>`
> ausfüllen, nicht zutreffende Abschnitte mit „–“ markieren statt löschen.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag <ID> in `docs/AENDERUNGEN.md`
<und weitere Konzeptdokumente>. Arbeitsbranch `claude/blissful-goldberg-mo3xda`; vorher `git pull`.

## Ziel

<Was soll nachher möglich sein, aus Sicht von Dominik bzw. der Person am Server – 2–4 Sätze.>

## Entscheide aus dem Brainstorming

- <Entscheid 1 (Datum, Dominik)>
- <…>

## Anforderungen

1. <Muss-Anforderung, prüfbar formuliert>
2. <…>

## Nicht Teil dieses Auftrags

- <bewusst ausgelassen, damit der Agent nicht ausufert>

## Hinweise zum Code

- <betroffene Module/Funktionen, bestehende Muster, die wiederverwendet werden sollen>
- Agent betroffen (neuer Agent-Stick nötig)? <ja/nein>
- Reihenfolge laut Entscheid: zuerst Agent, dann Tool-Logik, zuletzt Oberfläche.

## Oberfläche und Texte

- Menü-/Knopfnamen: <exakte Beschriftungen>
- Schreibstil laut `CLAUDE.md` (Handbuch-Stil ohne Anrede, Begriffe wie in der Oberfläche).

## Abnahmekriterien

- [ ] <beobachtbares Verhalten 1>
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests für <…>
- [ ] Hilfe (F1) in `okula_recovery/help_window.py` angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Eintrag ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Prüfschritte für das reale System unter „Offen“
- [ ] `docs/TECHNIK.md`: Abschnitt ergänzt
- [ ] Demo-Gerät: <Feature vorführbar / nicht nötig>

## Abschluss

1. Ein Commit (oder wenige, sinnvoll getrennt) mit der ID im Titel, z. B. `<ID>: <Titel>`; pushen auf
   `claude/blissful-goldberg-mo3xda`. **Nur eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`):
   Die Projektleitung arbeitet im selben Ordner, fremde Entwürfe (z. B. andere Dateien in `docs/prompts/`) bleiben liegen.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (im selben Commit).
3. Abschlussmeldung im Chat: was geändert wurde, Testergebnis, ob ein neuer Agent-Stick nötig ist, Schritte für
   den Server (`git pull && sudo ./install.sh`), offene Punkte oder Abweichungen vom Prompt.
