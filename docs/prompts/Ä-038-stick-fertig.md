# Ä-038 – Agent-Stick: Meldung „fertig, jetzt abziehen“ und Prüfung am Schluss

Status: umgesetzt (Commit ca975e5) · erstellt 10.11.2026 von Okuli (Projektleitung) · Freigabe: Dominik 10.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag Ä-038 (und B-010 im Erledigt-Protokoll) in `docs/AENDERUNGEN.md`,
`okula_recovery/stick.py` (Stick-Bau, `emit("DONE", …)`), `okula_recovery/stick_dialog.py` (`start_write`,
`_on_written`), `okula_recovery/usbtools.py` (`run_helper`). Gearbeitet wird in der eigenen Kopie (lokaler Branch
`agent/AE-038`); nicht pullen, nicht pushen. Shell-Befehle einzeln ausführen (kein `&&`), keine Hintergrundprozesse.

## Ziel

Nach *Agent-USB-Stick erstellen …* (und *Restore-Stick aus Image …*) ist unübersehbar, ob der Stick fertig ist und
abgezogen werden darf. Ein unvollständiger Stick wird schon am Server erkannt, nicht erst am Gerät.

## Befund (Okuli, 10.11.)

Ein Stick wurde 24 s nach dem Start abgezogen (Kernel: „lost async page write“, FAT nicht sauber ausgehängt). Das
Ende zeigte nur der Balken („Fehlgeschlagen“ + Log), das blieb unbemerkt. Auf dem Stick: `live/filesystem.squashfs`
vorhanden, `live/okula-agent.squashfs` **0 Byte** → am Gerät „Can not mount /dev/loop1 (…okula-agent.squashfs)“,
BusyBox-Shell (B-010).

## Anforderungen

1. **Prüfung am Schluss** (`stick.py`, nach `sync`, vor dem Aushängen bzw. danach erneut eingehängt – wie es sicherer
   ist): `live/<AGENT_LAYER>` existiert, ist > 0 Byte und beginnt mit dem Squashfs-Kopf (`hsqs`);
   `live/filesystem.squashfs` hat dieselbe Grösse wie im ISO; Kernel und initrd vorhanden. Beim Restore-Stick
   zusätzlich das Image auf der Datenpartition (vorhanden, Grösse > 0). Schlägt etwas fehl → Abbruch mit klarer
   Meldung (kein „DONE“). Prüfung als eigene Funktion, ohne Root testbar (Ordner als Argument).
2. **Abziehen während des Baus:** Verschwindet das Gerät (`device` existiert nicht mehr) oder schlägt ein Schritt
   mit E/A-Fehler fehl, lautet die Meldung „Stick wurde während des Schreibens abgezogen – Stick neu erstellen.“ statt
   einer technischen Fehlermeldung.
3. **Popup am Ende** (`stick_dialog._on_written`):
   - Erfolg: Dialog „Agent-Stick fertig“ (bzw. „Restore-Stick fertig“), Text „Der Stick kann jetzt abgezogen werden.“,
     Knopf „OK“. Der Balken zeigt weiter „Stick bereit“.
   - Fehler: roter Fehlerdialog „Stick nicht fertig“ mit dem Grund und dem Satz „Stick nicht verwenden – neu
     erstellen.“, Knopf „Schliessen“. Der Balken zeigt weiter „Fehlgeschlagen“, das Log bleibt.
   - Wiederverwendbar über die vorhandenen Helfer in `uikit.py` (`confirm_error` o. ä.), kein neues Muster.
4. Während des Baus deutlicher Hinweis im Dialog (Text unter dem Balken): „Stick erst abziehen, wenn „Stick fertig“
   erscheint.“
5. *Boot-Stick aus ISO …* (`isostick.py`/`os_dialogs.py`): nur prüfen, ob das Ende dort genauso unauffällig ist; falls
   ja, dasselbe Popup (ohne die Datei-Prüfung aus 1). In der Rückmeldung nennen.

## Nicht Teil dieses Auftrags

- Keine Erkennung alter/unvollständiger Sticks beim blossen Einstecken (später eigener Punkt, falls gewünscht).
- Keine Änderung am Inhalt des Sticks, am Agent oder am Netzwerkstart. Kein neuer Agent-Stick nötig.

## Hinweise zum Code

- `stick.py` läuft als root über `okula-make-stick` (Helfer); Meldungen gehen per `emit(...)` an den Dialog.
- `copy_tree` schreibt mit `fsync`; ein E/A-Fehler beim Abziehen kommt als Ausnahme aus `_run`/Dateizugriff.
- Agent betroffen (neuer Agent-Stick nötig)? **nein**.

## Oberfläche und Texte

- Exakt: „Agent-Stick fertig“, „Restore-Stick fertig“, „Der Stick kann jetzt abgezogen werden.“, „Stick nicht
  fertig“, „Stick nicht verwenden – neu erstellen.“, „Stick wurde während des Schreibens abgezogen – Stick neu
  erstellen.“, „Stick erst abziehen, wenn „Stick fertig“ erscheint.“
- Schreibstil laut `CLAUDE.md` (Handbuch-Stil ohne Anrede).

## Abnahmekriterien

- [ ] Tests für die Prüfung (Ordner mit gültigem Stick; Agent-Teil 0 Byte; falscher Kopf; filesystem.squashfs zu
      klein; Restore-Image fehlt) und für die Meldung beim Abziehen
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .` (bekannt rot: B-009, als `okuli-agent` evtl.
      `RealPartcloneTest` – melden)
- [ ] Hilfe (F1) in `okula_recovery/help_window.py`: Kapitel zum Agent-Stick (Erste Schritte, Agent-Stick) um das
      Popup und „erst abziehen, wenn …“ ergänzen; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Ä-038 ins „✅ Erledigt“-Protokoll, Kurzübersicht
- [ ] `docs/TESTS.md`: Prüfschritte unter „Offen“ (Stick fertig → Popup; Stick während des Baus abziehen → rotes
      Popup mit Satz zum Abziehen)
- [ ] `docs/TECHNIK.md`: Absatz zur Prüfung am Schluss

## Abschluss

1. Ein Commit `Ä-038: Agent-Stick – Meldung „fertig“ und Prüfung am Schluss` (oder wenige, sinnvoll getrennt),
   **nur lokal** auf `agent/AE-038`, nur eigene Dateien (`git add <Pfade>`, nie `-A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit ok).
3. Rückmeldung: Änderungen, Commits, Testergebnis, Ergebnis zu Punkt 5, Abweichungen.
