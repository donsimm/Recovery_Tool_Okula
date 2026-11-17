# Ä-040 – Master-Image: Einstellungen aus dem Audit-Modus übernehmen (CopyProfile, Taskleiste)

Status: freigegeben · erstellt 17.11.2026 von der Projektleitung · Freigabe: Dominik 17.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag Ä-040 in `docs/AENDERUNGEN.md`,
`docs/MASTER-IMAGE.md`, in `docs/TECHNIK.md` die Abschnitte zu *Danach anpassen* / Master-Image und I-038.
Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde (lokaler Branch `agent/Ä-040`); nicht pullen,
nicht pushen.

## Ziel

Was im Audit-Modus am Master eingerichtet wird (Anordnung der Desktop-Symbole, Explorer-Ansicht, Taskleiste mit
angehefteten Programmen, weitere Benutzereinstellungen des Administrators), haben nach dem Zurückspielen mit
*Danach anpassen* alle Benutzer – **ohne Skripte und ohne Handgriffe am Gerät**. Dominik macht Master-Images von sehr
vielen Maschinen.

## Entscheide aus dem Brainstorming

- Umsetzung im Tool, nicht über Skripte im Master (Dominik 17.11.).
- `CopyProfile=true` in der Antwortdatei des Tools; die angehefteten Taskleisten-Symbole zusätzlich über
  `LayoutModification.xml` im Standardprofil, weil CopyProfile sie unter Windows 10 nicht zuverlässig übernimmt.

## Anforderungen

1. **CopyProfile:** `winunattend.master_unattend()` schreibt in specialize `Microsoft-Windows-Shell-Setup/CopyProfile`
   = `true`, wenn die neue Option an ist. Microsoft Learn prüfen (Pass, Bedingungen: genau ein lokales Profil mit
   Anpassungen, Administrator im Audit-Modus; Auswirkungen auf bereits vorhandene Konten) und in `TECHNIK.md`
   festhalten.
2. **Option in der Oberfläche:** Im Dialog *Image zurückspielen* im Bereich *Danach anpassen* ein Häkchen
   **„Einstellungen des Administrators übernehmen (Master)“**, standardmässig **an**; gleiche Option in der
   Automatisierung (Schritt *Anpassen*), Standard an; gespeichert wie die übrigen Anpass-Optionen. Tooltip: was
   übernommen wird, dass es nur bei Master-Images (Sysprep) wirkt.
3. **Taskleiste ohne Skript:** Beim Anpassen (`deploy.customize`, Agent, Windows-Partition schreibend eingehängt):
   - Angeheftete Taskleisten-Symbole des Profils, in dem im Audit-Modus gearbeitet wurde (normalerweise
     `Users\Administrator`; robust: das Profil mit Anpassungen bestimmen, nie Default/Public), aus
     `AppData\Roaming\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\*.lnk` lesen.
   - Daraus eine `LayoutModification.xml` für Windows 10 (`CustomTaskbarLayoutCollection`, `PinListPlacement="Replace"`,
     `taskbar:DesktopApp DesktopApplicationLinkPath=…`; die .lnk an einen Ort legen, den alle Benutzer lesen, z. B.
     `ProgramData\Microsoft\Windows\Start Menu\Programs\Okula\` oder vorhandene Startmenü-Verknüpfungen nutzen) nach
     `Users\Default\AppData\Local\Microsoft\Windows\Shell\LayoutModification.xml` schreiben. Reihenfolge wie beim
     Administrator. Explorer/Edge/Store-Pins sinnvoll behandeln (z. B. Explorer über `DesktopApplicationID`).
   - Startmenü-Layout (Kacheln) ebenfalls übernehmen, falls aus dem Profil zuverlässig ableitbar; sonst weglassen und
     begründen.
   - Windows 11: Verhalten prüfen (anderes Format, `LayoutModification.json`/`.xml` für Taskleiste) – mindestens nichts
     kaputt machen; wenn einfach, unterstützen, sonst in `TECHNIK.md` als offen festhalten.
   - Keine Pins gefunden oder Option aus → nichts schreiben.
4. **Log und Verlauf:** Ergebnis im Auftrags-Log („Einstellungen des Administrators werden übernommen – Taskleiste:
   VLC, Explorer …“). Nicht generalisiertes Windows → Option wirkungslos, wie heute nichts ändern.
5. **Doku:** `MASTER-IMAGE.md` (Schritt „Im Audit-Modus einrichten“: Symbole, Taskleiste, Ansicht einfach am
   Administrator einrichten – das Tool übernimmt sie), Hilfe (F1) im Kapitel zum Master/Zurückspielen und
   Automatisierung.
6. **Tests:** `master_unattend` mit/ohne CopyProfile (gültiges XML, richtiger Pass), Lesen der Pins aus einem
   nachgebauten Profilbaum, erzeugte `LayoutModification.xml` (Reihenfolge, Pfade, gültiges XML), Option aus →
   nichts geschrieben, Automatisierung übernimmt die Option.

## Nicht Teil dieses Auftrags

- Software installieren (I-020), Windows anpassen (I-039), Domäne.
- Nicht generalisierte Images (I-003).

## Hinweise zum Code

- `okula_recovery/winunattend.py` (`master_unattend`, specialize Shell-Setup um Zeile 219), `restore_dialog.py`
  (Häkchen „Danach anpassen …“), `ui.py` um Zeile 3630 und `automation.py` um Zeile 604 (Aufrufe von
  `master_unattend`), `automation_tab.py` (Schritt *Anpassen*), `deploy.customize` (Agent), `agentclient.customize`.
- Agent betroffen (neuer Agent-Stick nötig)? **ja** (Taskleiste wird auf dem Agent geschrieben).

## Oberfläche und Texte

- Häkchen: **„Einstellungen des Administrators übernehmen (Master)“**. Schreibstil laut `CLAUDE.md`.

## Abnahmekriterien

- [ ] Antwortdatei mit `CopyProfile=true` (Option an), ohne (Option aus)
- [ ] Taskleisten-Pins des Administrators landen als `LayoutModification.xml` im Standardprofil
- [ ] Option im Dialog und in der Automatisierung, Standard an, gespeichert
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests wie oben
- [ ] Hilfe (F1) angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Eintrag ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: neuer Abschnitt „Einstellungen aus dem Audit-Modus (Ä-040)“ – VM: im Audit-Modus Symbole
      anordnen, VLC und Explorer an die Taskleiste heften, Explorer-Ansicht ändern → Sysprep → Image → mit *Danach
      anpassen* zurückspielen → Benutzer hat Anordnung, Taskleiste, Ansicht; zweiter neuer Benutzer ebenso
- [ ] `docs/TECHNIK.md` und `docs/MASTER-IMAGE.md` ergänzt
- [ ] Demo-Gerät: nicht nötig (Option sichtbar)

## Abschluss

1. Ein Commit (oder wenige) `Ä-040: Einstellungen des Administrators im Master übernehmen`, **nur lokal** auf
   `agent/Ä-040` – **nicht pushen**. **Nur eigene Dateien committen** (`git add <Pfade>`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Commits, Testergebnis, neuer Agent-Stick ja, Schritte für den Server, Quellen,
   offene Punkte (v. a. Windows 11, Startmenü).
