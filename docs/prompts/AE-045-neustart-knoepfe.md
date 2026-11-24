# Ä-045 – Zwei klare Neustart-Knöpfe: „Neustart in Windows“ und „Neustart in den Agent“

Status: umgesetzt (Commit 874121e) · erstellt 24.11.2026 von der Projektleitung · Freigabe: Dominik 24.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag Ä-045 in `docs/AENDERUNGEN.md`, dazu I-001
(VMs), I-041, Ä-044. Lokaler Branch `agent/AE-045`; nicht pullen, nicht pushen. 1–3 Commits.

Parallel arbeitet ein zweiter Agent an Ä-046 (Windows anpassen beim Aufsetzen: `winsetup.py`, `restore_dialog.py`,
`automation_tab.py`, `wintweaks.py`). Dort nichts ändern; Doku-Einträge knapp und an eigener Stelle.

## Befund (Dominik 24.11.)

Nach *Windows anpassen* / *Software installieren* bestätigt man alles mit „Neu starten“. Wohin das Gerät startet,
hängt still vom Zustand ab (VM: Netzwerk zuerst, wenn der Agent angefordert ist, sonst Disk zuerst – `ui.py` um Zeile
2872, Stand vor B-020; Stelle selbst suchen). Dominik findet das verwirrend: Er weiss nicht, ob er jetzt in Windows oder
in den Agent startet.

## Anforderungen

1. **Zwei Knöpfe** statt „Neu starten“, überall wo heute neu gestartet wird (Gerätemenü, Gerätefenster, Dialog nach
   dem Senden – selbst alle Stellen suchen):
   - **„Neustart in Windows“** – startet von der Disk; abgelegte Aufträge (Startskripte) laufen dort.
   - **„Neustart in den Agent“** – startet über Netzwerk bzw. Agent-Stick.
2. **VMs:** Startreihenfolge pro Knopf eindeutig setzen (heutige Logik dafür nutzen); keine stille Abhängigkeit mehr
   vom Zustand.
3. **Echte Geräte:** Prüfen, was das Tool steuern kann, wenn der Agent läuft (z. B. `efibootmgr --bootnext` auf den
   Windows-Boot-Manager bzw. die Netzwerk-/Stick-Option; BIOS/Legacy-Geräte). Was nicht sicher steuerbar ist: ehrlicher
   Hinweis im Dialog (z. B. „Agent-Stick abziehen, dann startet Windows“). Belegen, nicht raten. Ändert sich Agent-Code,
   „neuer Agent-Stick nötig“ melden.
4. **Nach dem Senden** fragt der Dialog direkt: „Jetzt in Windows neu starten?“ (Knöpfe „Neustart in Windows“ /
   „Später“); kein Umweg über ein Menü.
5. Knöpfe nur zeigen, wenn sie gehen (Gerät erreichbar, VM vorhanden); sonst ausgegraut mit Tooltip-Grund.
6. **Tests:** Startreihenfolge VM je Knopf, echtes Gerät (nachgebildet), Dialog nach dem Senden, Texte. Hilfe (F1)
   anpassen (überall „Neu starten“ ersetzen), `docs/TESTS.md` neuer Abschnitt „Ä-045 Neustart-Knöpfe“: VM-Win11-clean
   beide Knöpfe, ein echtes Gerät mit Agent-Stick.

## Nicht Teil dieses Auftrags

- Ä-046, I-042.

## Abnahmekriterien

- [ ] Überall zwei eindeutige Knöpfe, VM startet je Knopf richtig
- [ ] Echte Geräte: gesteuert oder ehrlicher Hinweis
- [ ] Dialog nach dem Senden fragt direkt nach dem Neustart in Windows
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TESTS.md`

## Abschluss

1. Commit(s) mit `Ä-045: …` im Titel, nur lokal auf deinem Branch; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis (oder: Tests nicht ausführbar), Quellen, neuer
   Agent-Stick ja/nein, offene Punkte.
