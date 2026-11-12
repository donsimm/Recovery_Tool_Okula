# B-012 – Windows-Konto „Benutzer“ bricht die Einrichtung ab

Status: freigegeben · erstellt 12.11.2026 von der Projektleitung · Freigabe: Dominik 12.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag **B-012** in `docs/AENDERUNGEN.md`.
Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde (lokaler Branch `agent/B-012`);
nicht pullen, nicht pushen.

## Ziel

Eine Windows-Direktinstallation läuft ohne Eingriff durch, ohne an der Kontoerstellung hängenzubleiben.
Der vorbelegte Kontoname kollidiert heute in deutschem Windows mit der eingebauten Gruppe „Benutzer“, die
Einrichtung bricht ab und landet in einer Neustart-Schleife. Nach dem Fix ist der Standardname unkritisch,
und ein Name, der mit einer eingebauten Gruppe oder einem reservierten Namen kollidiert, wird im Dialog
abgefangen, bevor die Installation startet.

## Hintergrund (Befund 12.11.)

- `WinOptions.local_account` steht auf `"Benutzer"` (okula_recovery/winunattend.py). Daraus entsteht in der
  `autounattend.xml` ein `LocalAccount` mit `Name=Benutzer`, Gruppe `Administrators`, plus
  `net user "Benutzer" /logonpasswordchg:yes` (LogonCommands).
- In deutschem Windows heisst die eingebaute Gruppe `Builtin\Users` lokalisiert **„Benutzer“**. Das Anlegen des
  Kontos scheitert mit `0x80070563`, danach OOBE-Schleife (oobeldr `0x8030000b`/`0x8030000c`).
  Beleg: `Windows\Panther\UnattendGC\setuperr.log` → „UserAccounts: failed to create user account 'Benutzer'“.
- Das Aufspielen von Windows (dism) selbst ist fehlerfrei. Es geht ausschliesslich um den Kontonamen.

## Anforderungen

1. **Standardname ändern:** `WinOptions.local_account` und die Vorbelegung des Felds „Benutzername“ in
   `okula_recovery/os_dialogs.py` (zwei Stellen, `self.w_user = Gtk.Entry(text="Benutzer", …)`, Zeilen ~337 und
   ~584) auf **„Okula“** setzen. Nur diese Vorbelegung, Eingaben des Benutzers bleiben möglich.
2. **Reservierte Namen im Dialog abfangen:** Bestätigt der Benutzer die Installation mit einem lokalen Konto,
   dessen Name (nach `strip()`, Vergleich ohne Gross-/Kleinschreibung) einem reservierten Windows-Namen
   entspricht, wird die Installation **nicht gestartet**, sondern eine verständliche Meldung gezeigt, die den
   Namen nennt und zum Ändern auffordert. Liste mindestens:
   `Benutzer, Benutzerin, Administrator, Administratoren, Administrator-Gruppe, Administratoren-Gruppe, Gast,
   Gäste, Jeder, Users, User, Administrators, Guest, Guests, Everyone, System, Network, Local, Default,
   DefaultAccount, WDAGUtilityAccount, Konto`. Ebenso abfangen: leerer Name bei aktivem „Lokales Konto“
   (falls das Feld leer sein darf, Windows-Verhalten dokumentieren – aber kein Abbruch), Name länger als
   20 Zeichen, Name endet auf Punkt, oder Name enthält eines der Zeichen `" / \ [ ] : ; | = , + * ? < >`.
3. Die Prüfung gehört in die Logik (z. B. eine Funktion `pruefe_kontoname(name) -> str|None` in
   `winunattend.py`, die bei Problem die Meldung ergibt, sonst `None`), damit sie testbar ist; der Dialog ruft
   sie beim Bestätigen auf und zeigt die Meldung wie bei anderen Validierungen im selben Dialog.
4. Gilt für **beide** Dialoge (Boot-Stick und „OS installieren …“). Keine stillschweigende Korrektur des
   Namens – der Benutzer entscheidet.

## Nicht Teil dieses Auftrags

- Der separate Fehler am echten Gerät „Windows-Partition nicht gefunden“ (zweiter Installationsversuch) – dafür
  fehlt noch das Protokoll vom Gerät, eigener Bug.
- Linux-Installation, Computername-Logik (`computer_name()` bleibt wie sie ist).
- Keine Änderung an der Kontogruppe (bleibt `Administrators`).

## Hinweise zum Code

- Betroffen: `okula_recovery/winunattend.py` (Standardwert, neue Prüffunktion), `okula_recovery/os_dialogs.py`
  (Vorbelegung + Aufruf der Prüfung beim Bestätigen).
- Bestehende Validierungsmuster im selben Dialog wiederverwenden (wie der Disk-Name zur Bestätigung geprüft
  wird); Meldungen im Handbuch-Stil ohne Anrede.
- Die zwei Dialoge mit `w_user`: `BootStickDialog` (Boot-Stick mit `autounattend.xml`) und `InstallDialog`
  („OS installieren …“) – beide anpassen.
- Agent betroffen (neuer Agent-Stick nötig)? **Nein** – `winunattend.py` läuft nur auf dem Server
  (nicht in `stick.AGENT_MODULES`); die `autounattend.xml` schickt der Server mit.
- Reihenfolge: zuerst Tool-Logik, dann Dialoge, zuletzt Texte/Hilfe.

## Oberfläche und Texte

- Feld-/Knopfnamen exakt wie in der Oberfläche: „Lokales Konto statt Microsoft-Konto“, „Benutzername“,
  „OS installieren …“.
- Meldung sachlich, nennt den Namen und den Grund, z. B.: „Der Name ‚Benutzer‘ ist in Windows für eine
  Gruppe vergeben und lässt sich nicht als Konto verwenden. Anderen Benutzernamen eingeben.“

## Abnahmekriterien

- [ ] Standardname im Feld „Benutzername“ und in `WinOptions.local_account` ist „Okula“.
- [ ] Bestätigen mit Kontoname „Benutzer“ (auch „benutzer“, „ Benutzer “) startet die Installation nicht,
      sondern zeigt die Meldung; mit „Okula“ läuft es durch.
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests für `pruefe_kontoname`
      (reservierte Namen, Gross-/Kleinschreibung, Leerzeichen, Sonderzeichen, Länge) und dafür, dass die
      erzeugte `autounattend.xml` den gesetzten Namen enthält.
- [ ] Hilfe (F1) in `okula_recovery/help_window.py` angepasst (Kapitel Windows-Installation: Hinweis, dass
      bestimmte Namen wie „Benutzer“ oder „Administrator“ nicht gehen), `tests/test_help.py` grün.
- [ ] `docs/AENDERUNGEN.md`: B-012 ins „✅ Erledigt“-Protokoll, Kurzübersicht (Bugs) aktualisiert.
- [ ] `docs/TESTS.md`: Prüfschritt am realen System unter „Offen“ (CompactPlayer: Windows mit Standardname
      „Okula“ installieren, läuft ohne Eingriff bis zum Anmeldebildschirm).
- [ ] `docs/TECHNIK.md`: Abschnitt Windows-Installation um die Namensprüfung ergänzt.
- [ ] Demo-Gerät: nicht nötig (am realen Gerät/VM-Zwilling prüft Dominik).

## Abschluss

1. Ein Commit (oder wenige, sinnvoll getrennt) mit der ID im Titel, z. B. `B-012: Windows-Kontoname prüfen`,
   **nur lokal** auf `agent/B-012` – **nicht pushen**. **Nur eigene Dateien committen** (`git add <Pfade>`,
   nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis, neuer Agent-Stick nötig (erwartet: nein),
   Schritte für den Server (`git pull && sudo ./install.sh`), offene Punkte oder Abweichungen vom Prompt.
