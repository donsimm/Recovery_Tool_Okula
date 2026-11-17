# B-016 – Agent-Stick: GRUB meldet „file `/boot/grub/font.pf2' not found“

Status: umgesetzt (Commit 1acfed0) · erstellt 17.11.2026 von der Projektleitung · Freigabe: Dominik 17.11. (nach I-020 starten)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag B-016 in `docs/AENDERUNGEN.md`.
Lokaler Branch `agent/B-016`; nicht pullen, nicht pushen. Kleinstauftrag.

## Ziel

Beim Start vom Agent-Stick erscheint keine Fehlermeldung mehr von GRUB; das grafische Menü mit Okula-Logo bleibt.

## Befund

CompactPlayer 1, 17.11. (Foto): Bei jedem Start „error: file `/boot/grub/font.pf2' not found.“, danach startet der
Agent normal. Ursache: `stick.py`, `GRUB_CFG` – `if loadfont /boot/grub/font.pf2; then … elif loadfont unicode` –
GRUB gibt beim ersten fehlgeschlagenen `loadfont` die Meldung aus, bevor der `elif`-Zweig greift.

## Anforderungen

1. `GRUB_CFG`: vor `loadfont /boot/grub/font.pf2` mit `[ -f /boot/grub/font.pf2 ]` prüfen (GRUB-Skript, `&&` ist
   erlaubt bzw. verschachteltes `if`); gleich für den zweiten Versuch (`unicode` → Pfad prüfen, z. B.
   `$prefix/fonts/unicode.pf2`), damit auch dort keine Meldung kommt. Nur ASCII.
2. Gleiche Stelle ggf. im Netzwerkstart (PXE/GRUB-Konfiguration) prüfen und dort ebenso anpassen.
3. Test: erzeugte `grub.cfg` enthält die Prüfungen, gültige `if`/`fi`-Struktur.

## Nicht Teil dieses Auftrags

- Theme, Logo, Menüeinträge.

## Hinweise zum Code

- `okula_recovery/stick.py` (`GRUB_CFG`), ggf. `pxe.py`. Neuer Agent-Stick nötig: **ja** (Stick-Inhalt).

## Abnahmekriterien

- [ ] Keine `loadfont`-Fehlermeldung mehr, grafisches Menü unverändert
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`
- [ ] `docs/AENDERUNGEN.md`: B-016 ins Protokoll, Kurzübersicht; `docs/TESTS.md`: Prüfpunkt „Start ohne GRUB-Meldung“

## Abschluss

1. Commit `B-016: GRUB-Schrift nur laden, wenn vorhanden`, nur lokal auf `agent/B-016`; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung.
