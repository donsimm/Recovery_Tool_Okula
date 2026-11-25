# Übergabe – 25.11.2026, ca. 16:30

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` → `~/okuli/UEBERGABE.md` → Dominik den Stand nennen.

**Agenten:** wieder erlaubt (Pause am Vormittag galt nur dem 5h-Limit). Strikt nach Modell-Tabelle in
`~/okuli/agenten/REGELN.md`: Reviews sonnet medium, Umsetzung opus medium, high nur für Architektur/heikle Fehler.
**Neu 25.11.:** Agenten können `python3 -m unittest discover -s tests -t .` jetzt ausführen (Zusatz-Tool
`"Bash(python3 -m unittest:*)"` und im Auftrag ausdrücklich: ohne cd, ohne Pipe, ohne `2>&1`).

## Stand (alles gepusht, Branch `claude/blissful-goldberg-mo3xda`, zuletzt bd76066, Tests 864 OK, skipped 69)

- **Tag `v0.2.0`** (4ec57fc) nach dem letzten VM-Durchgang: VM-Win11-clean, Direktinstallation + Windows anpassen
  „Clean“ – Startmenü nur Okula-Kacheln über das Paket vom Tool (frisches Windows **ohne ADK**), kein Wetter, kein
  Sperrbildschirm (Durchgang 2 mit Option), Protokoll 68 ok/0 Fehler, Zeitstempel Ortszeit. Windows Home ungeprüft.
- Befunde daraus erfasst: **B-023** (Startmenü-Hinweis trotz Paket, „Startmenue“), **B-024** (OneDrive-Rückgabewert),
  **Ä-047** (Sperrbildschirm in Vorlage Clean).
- **Code-Review** (4 Lese-Agenten sonnet): `docs/REVIEW-2026-11-25.md`, 34 Befunde. Erfasst als B-025–B-028, Ä-048
  (Robustheit, Sammelpunkt), Ä-049 (`ui.py` aufteilen, Mixin-Vorschlag im Bericht).
- **B-025** (Automatisierung löscht BitLocker-Disk ohne Backup → bricht jetzt ab) und **B-026** (Image/ISO/Ordner
  während eines Auftrags gegen Löschen/Verschieben/Umbenennen gesperrt) umgesetzt (opus medium), von Okuli
  abgenommen (Diff, Tests). **Am realen System ungeprüft** – TESTS.md „B-025“, „B-026“.
  Server: `git pull && sudo ./install.sh`, Tool neu starten, kein neuer Agent-Stick.
- **Doku aufgeräumt:** AENDERUNGEN.md Kopf = Kurzstand + „Als Nächstes“ (5 Punkte); TESTS.md „Übersicht (Stand
  25.11.)“ mit bestätigten und priorisierten offenen Prüfungen (die Häkchen in den alten Abschnitten sind nicht gepflegt).

## Als Nächstes

1. **Ordnung weiter** (Dominik 25.11.): Okulis Regeln und Gedächtnis gemeinsam durchgehen; Ideen einsortieren
   (22 im Tool + ID-0003 „Ordner einfärben“, S-0001, S-0002 im Cockpit/Sekretär). I-012 (BitLocker entsperren)
   hochstufen vorschlagen – realer Fall ZBook 25.11.
2. **B-027, B-028** mit zwei Umsetzungs-Agenten (opus medium); Prompts nach Muster `docs/prompts/B-025-…`, Quelle
   `docs/REVIEW-2026-11-25.md`. Dann Ä-047, B-023, B-024 (klein, zusammen möglich).
3. Zweite Review-Runde (`vm.py`, `help_window.py`, Dialoge, übrige Module), danach Ä-048/Ä-049.
4. Am realen Gerät: B-025 (ZBook mit BitLocker), B-026 (Demo-Gerät), B-013, B-004, Ä-045 mit Stick.

## Offen / Beobachtungen
- **HP ZBook Fury G1i** (SN 5CG5345KVV, Philippe): CPU drosselt wegen Wärme, Lüfter 100 %. BIOS 01.05.01 = neuestes
  (HP-Liste Board 8DE2), Einstellungen Werkszustand, Lüfter sauber → Empfehlung HP-Garantie mit F2-Diagnose (Failure ID).
  Backup der Benutzerordner scheitert an BitLocker → Empfehlung: in Windows kopieren, **Wiederherstellungsschlüssel
  vor dem Service sichern**. Secure-Boot-Hinweis („Enable MS UEFI CA key“) in Ä-010 aufgenommen.
- VM-Win11-clean läuft (Durchgang 2, snap-8). Disk lässt sich nur lesend prüfen:
  `qemu-nbd --read-only -c /dev/nbd0 --image-opts driver=qcow2,file.driver=file,file.filename=<snap>,file.locking=off`,
  dann `ntfs-3g -o ro`. Protokoll: `C:\Windows\Temp\okula-windows-anpassen.log`.

## Learnings
- Protokolle aus einer laufenden VM selbst lesen statt Dominik abtippen lassen (qemu-nbd nur lesend, siehe oben).
- Vorlage „Clean“ enthält nicht alle Optionen – bei Tests „alle Häkchen“ die Kopfzeile „(geändert)“ und die Zeilen
  im Protokoll prüfen, nicht nur das Ergebnis am Bildschirm.
- Zwei Agenten parallel ändern beide `AENDERUNGEN.md`/`TESTS.md` → beim Zusammenführen Konflikt; Auftrag: „nur
  eigenen Eintrag ändern“, Kurzübersicht danach selbst nachführen.
- Windows wartet bei der Anmeldung nicht auf Startskripte – was vor der ersten Anmeldung wirken muss, offline setzen.
- „Configure Start Pins“ per Gruppenrichtlinie ist stufenweise freigeschaltet; das Bereitstellungspaket wirkt bei Pro.
