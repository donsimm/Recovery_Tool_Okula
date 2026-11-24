# Ä-046 – Windows anpassen beim Aufsetzen mitgeben: neue Maschine in einem Durchgang

Status: offen · erstellt 24.11.2026 von der Projektleitung · Freigabe: Dominik 24.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge Ä-046, B-021, B-020, B-013, I-038, I-039, I-020,
Ä-040, Ä-044 in `docs/AENDERUNGEN.md`, Prompts B-020 und B-021. Lokaler Branch `agent/AE-046`; nicht pullen, nicht
pushen. Grosser Bau: in **Abschnitte von 2–3 Commits**; ist der Kontext knapp, sauber an einer Abschnittsgrenze
aufhören und in der Abschlussmeldung sagen, was fehlt.

Parallel arbeitet ein zweiter Agent an Ä-045 (Neustart-Knöpfe, v. a. `ui.py`, `device_window.py`, Dialog nach dem
Senden). Dort nur ändern, was für Ä-046 nötig ist; Doku-Einträge knapp und an eigener Stelle, damit Okuli sauber
zusammenführen kann.

## Heute (Dominik 24.11.)

Neue Maschine: *OS installieren* (Direktinstallation, mit Software aus der Bibliothek) → danach Gerät nochmals in den
Agent → *Windows anpassen* senden → neu starten. Zwei Durchgänge. *Software installieren* gibt es beim Aufsetzen
schon (I-020: Direktinstallation, *Image zurückspielen → Danach anpassen*, Automatisierung) – diesem Muster folgen.

## Ziel

„Windows anpassen“ (Vorlage bzw. eigene Auswahl wie im Dialog *Windows anpassen*) lässt sich überall dort mitgeben, wo
heute *Software installieren* mitgeht:

1. **OS installieren** (Direktinstallation, `winsetup.py`/`winunattend.py`): Windows ist beim Senden noch nicht
   installiert, ein Hive existiert noch nicht. Das Anpassen-Skript muss **vor der ersten Anmeldung** laufen
   (Windows wartet bei der Anmeldung nicht auf Startskripte – B-020). Bevorzugt in der Setup-Phase als SYSTEM (z. B.
   wie I-038 über `SetupComplete.cmd` bzw. dort, wo heute die Software aus der Bibliothek installiert wird). Belegen
   (Microsoft Learn), wann der gewählte Weg läuft. **B-013 beachten:** Mit OEM-Schlüssel läuft `SetupComplete.cmd`
   nicht (ausser Enterprise) – einen Weg wählen, der auch dann läuft, oder ehrlich melden.
   - Was B-020/B-021 offline schreibt (Startmenü-Richtlinie + `StartPins.json`, Widgets, Sperrbildschirm,
     Microsoft-Benutzererfahrungen), muss hier ebenfalls vor der ersten Anmeldung wirken: entweder in der Setup-Phase
     setzen (vor dem ersten Profil – dann entfällt das Umbenennen von `start2.bin`) oder nach dem Anwenden des Images
     offline in den Hive schreiben. Einfachsten sicheren Weg wählen und begründen.
   - Reihenfolge mit Software aus der Bibliothek festlegen (z. B. erst Software, dann Anpassen – „Store-Apps
     entfernen“ darf nichts treffen, was die Software braucht) und begründen.
2. **Image zurückspielen → Danach anpassen** (`restore_dialog.py`, Ä-040): Nach dem Zurückspielen liegt der Hive vor –
   wie *Windows anpassen* heute: Startskript ablegen + `deploy.tweak_offline`.
3. **Automatisierung** (`automation_tab.py`, `automation.py`), auch in **Vorlagen**: Auswahl „Windows anpassen“ mit
   Vorlage; wird bei Direktinstallation bzw. Zurückspielen mitgegeben.

Gemeinsam:
- Auswahl wie im bestehenden Dialog *Windows anpassen* (Vorlagen, Optionen, Tooltips) wiederverwenden, nicht
  nachbauen.
- Protokoll am Gerät wie heute (`C:\Windows\Temp\okula-windows-anpassen.log`), Log im Tool, Nachlauf (30 min) wie
  heute.
- Master-Image (Audit-Modus, I-038) und Sysprep: Klären, ob Anpassen dort angeboten werden darf; im Zweifel beim
  Master ausblenden bzw. warnen (wie bei Software/Ä-040) und begründen.
- Ohne Auswahl ändert sich nichts am heutigen Ablauf.

## Tests

- Direktinstallation: Skript und Setup-Schritt werden erzeugt, Reihenfolge mit Software, OEM-Fall (B-013).
- Zurückspielen: Startskript und Offline-Werte wie bei *Windows anpassen*.
- Automatisierung inkl. Vorlage: Auswahl gespeichert, geladen und mitgegeben.
- Hilfe (F1): Kapitel *OS installieren*, *Image zurückspielen*, *Automatisierung*, *Windows anpassen*.
- `docs/TESTS.md` neuer Abschnitt „Ä-046 Neue Maschine in einem Durchgang“: VM-Win11 mit Direktinstallation +
  Software (virtio) + Windows anpassen (Clean, alle Häkchen) in einem Durchgang; bei der ersten Anmeldung Startmenü,
  kein Wetter, kein Sperrbildschirm; Protokolle ohne FEHLER; Nachlauf nach 30 min. Zusätzlich Zurückspielen mit
  *Danach anpassen*.

## Nicht Teil dieses Auftrags

- Ä-045 (Neustart-Knöpfe), I-042 (Microsoft 365).

## Abnahmekriterien

- [ ] Windows anpassen in OS installieren, Image zurückspielen (Danach anpassen) und Automatisierung (inkl. Vorlagen)
- [ ] Wirkt vor der ersten Anmeldung (Weg belegt), OEM-Fall behandelt oder ehrlich gemeldet
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md`

## Abschluss

1. Commit(s) mit `Ä-046: …` im Titel, nur lokal auf deinem Branch; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis (oder: Tests nicht ausführbar), Quellen, neuer
   Agent-Stick ja/nein, offene Punkte.
