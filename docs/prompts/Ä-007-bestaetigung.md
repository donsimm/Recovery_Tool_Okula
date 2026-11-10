# Ä-007 – Bestätigung beim Einschalten der Automatisierung

Status: umgesetzt (Commit 1f5c409) · erstellt 10.11.2026 von Okuli (Projektleitung) · Freigabe: Dominik 10.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag Ä-007 in `docs/AENDERUNGEN.md`,
`docs/AUTOMATISIERUNG.md`, `okula_recovery/automation.py`, `okula_recovery/automation_tab.py`,
`okula_recovery/ui.py` (`_on_auto_toggled`, `save_automation`), `okula_recovery/uikit.py` (`confirm`).
Gearbeitet wird in der eigenen Kopie (lokaler Branch `agent/AE-007`); nicht pullen, nicht pushen.
Shell-Befehle einzeln ausführen (kein `&&`), keine Hintergrundprozesse.

## Ziel

Wer die Automatisierung eines Geräts von Hand einschaltet, sieht vorher eine rote Zusammenfassung, was gelöscht und
aufgesetzt wird, und bestätigt sie ausdrücklich. Heute genügt ein Klick auf das Häkchen *Auto* in der Geräteliste:
Ist das Gerät verbunden, startet nach 30 s ohne Rückfrage das Löschen der Disk.

## Entscheide aus dem Brainstorming (Dominik, 10.11.2026)

- **Variante B:** Rückfrage bei **jedem Einschalten von Hand** (Häkchen *Auto* in der Geräteliste und Schalter im
  Reiter *Automatisierung*), egal ob das Gerät gerade verbunden ist.
- Das automatische Wieder-Einschalten nach 3 Tagen (`rearm`, `AutomationManager.tick`) bleibt **ohne** Rückfrage;
  die Zusammenfassung erwähnt es, wenn die Option an ist.
- Der Hauptschalter ■ (Stopp über der Geräteliste) fragt beim Aufheben des Stopps **nicht** nach.
- Kein Eintippen des Gerätenamens (Variante C verworfen). Der Countdown von 30 s mit Esc bleibt unverändert.

## Anforderungen

1. **Zusammenfassung als Funktion in `automation.py`** (ohne GTK, testbar), z. B.
   `confirm_summary(dev, s, connected: bool) -> tuple[str, str, str]` → (Titel, Text, Knopfbeschriftung):
   - Titel: „Automatisierung für <Gerätename> einschalten?“
   - Text (Zeilen): Disk, die gelöscht wird (`s.disk_label`, sonst Modell/Grösse aus dem Inventar);
     Image (Master-Name bzw. eigenes Image, Anzeigename wie im Reiter); Gerätename danach (Windows-Name wie im
     Häkchen „Danach anpassen“, falls verwendet); Backup vorher: nein / Benutzerdaten / ganze Disk;
     bei VMs: Snapshot vorher ja/nein; Abschluss (Neustart/Herunterfahren/nichts);
     wenn `s.rearm`: „Nach dem Durchlauf in 3 Tagen wieder aktiv.“ (Wortlaut an `REARM_LABEL` anlehnen).
   - Verbunden: Zeile „Das Gerät ist verbunden – das Löschen beginnt nach 30 s Countdown.“, Knopf
     **„Löschen und neu aufsetzen“**.
   - Nicht verbunden: Zeile „Beim nächsten Verbinden wird die Disk gelöscht.“, Knopf **„Einschalten“**.
   - Fehlende Angaben (`problems`) bleiben wie heute ein Fehler vor der Rückfrage (keine Rückfrage, wenn unvollständig).
2. **Rückfrage-Dialog** in der Oberfläche: wiederverwendbar über `uikit.confirm` oder eine kleine Erweiterung davon
   (rote/destruktive Darstellung des Knopfs wie bei bestehenden Lösch-Dialogen, *Abbrechen* als Standard).
3. **Häkchen *Auto*** (`ui._on_auto_toggled`): Beim Einschalten erst die Rückfrage; bei *Abbrechen* bleibt alles aus
   (nichts gespeichert, kein Verlaufseintrag, Häkchen wieder aus). Ausschalten weiterhin ohne Rückfrage.
4. **Schalter im Reiter *Automatisierung*** (`automation_tab._changed`): gleiche Rückfrage nur beim Wechsel aus → ein;
   bei *Abbrechen* Schalter zurück auf aus, ohne Speichern (Achtung auf `_updating`, damit kein zweites Signal
   auslöst). Andere Änderungen im Reiter bei eingeschalteter Automatisierung fragen **nicht** nach.
5. Andere Wege, die `enabled` setzen (Vorlage anwenden, `tick`/rearm, Einstellungen importieren): prüfen und kurz
   in der Rückmeldung nennen. Vorlage anwenden darf eine ausgeschaltete Automatisierung nicht stillschweigend
   einschalten – falls das heute passiert, ebenfalls mit Rückfrage.
6. Demo-Gerät: Rückfrage erscheint dort genauso.

## Nicht Teil dieses Auftrags

- Kein Eintippen zur Bestätigung, keine Änderung am Countdown, am Ablauf der Automatisierung oder am Agent.
- Keine Rückfrage beim Hauptschalter ■ und beim Wieder-Einschalten nach 3 Tagen.
- Keine sprachlichen Umbauten im Reiter (das ist Ä-012).

## Hinweise zum Code

- `ui.save_automation` startet über `automation.consider` den Countdown, wenn das Gerät verbunden ist – die Rückfrage
  muss **vorher** kommen (also in den Auslösern, nicht in `consider`).
- Ob verbunden: `self.online_agent(dev) is not None` (Hauptfenster).
- Agent betroffen (neuer Agent-Stick nötig)? **nein**.

## Oberfläche und Texte

- Knöpfe exakt: „Abbrechen“, „Löschen und neu aufsetzen“ bzw. „Einschalten“.
- Schreibstil laut `CLAUDE.md` (Handbuch-Stil ohne Anrede; Disk, Zieldisk, Master-Image wie in der Oberfläche).

## Abnahmekriterien

- [ ] Häkchen *Auto* bei verbundenem Gerät → Rückfrage mit Zusammenfassung und „Löschen und neu aufsetzen“;
      *Abbrechen* → aus, kein Countdown, kein Verlaufseintrag
- [ ] Nicht verbunden → Rückfrage mit „Einschalten“ und Satz zum nächsten Verbinden
- [ ] Schalter im Reiter *Automatisierung* verhält sich gleich; Ausschalten ohne Rückfrage
- [ ] Unvollständig eingerichtet → wie bisher Fehler, keine Rückfrage
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .` (bekannt rot ohne `/usr/sbin` im PATH: 4 Tests,
      B-009; als `okuli-agent` evtl. `RealPartcloneTest` – melden). Neue Tests für `confirm_summary`
      (verbunden/nicht verbunden, Backup-Arten, VM mit Snapshot, rearm an/aus)
- [ ] Hilfe (F1) in `okula_recovery/help_window.py`: Kapitel zur Automatisierung und Häkchen *Auto* um die Rückfrage
      ergänzen, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Ä-007 ins „✅ Erledigt“-Protokoll, Kurzübersicht; Entscheide unter „📌 Entscheidungen“
- [ ] `docs/TESTS.md`: Prüfschritte in Abschnitt 5 (Automatisierung) unter „Offen“
- [ ] `docs/TECHNIK.md` bzw. `docs/AUTOMATISIERUNG.md`: kurzer Absatz zur Rückfrage

## Abschluss

1. Ein Commit `Ä-007: Bestätigung beim Einschalten der Automatisierung` (oder wenige, sinnvoll getrennt), **nur lokal**
   auf `agent/AE-007`, nur eigene Dateien (`git add <Pfade>`, nie `-A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit ok).
3. Rückmeldung: Änderungen, Commits, Testergebnis, weitere Stellen, die `enabled` setzen, Abweichungen.
