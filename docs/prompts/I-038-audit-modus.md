# I-038 – Windows-Direktinstallation „Für Master-Image (Audit-Modus)“

Status: freigegeben · erstellt 12.11.2026 von der Projektleitung · Freigabe: Dominik 12.11. („Audit-Modus planen und umsetzen“)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag **I-038** in `docs/AENDERUNGEN.md`,
`docs/MASTER-IMAGE.md` und in `docs/TECHNIK.md` die Abschnitte „Master-Image (Sysprep)“ und Windows-Installation.
Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde (lokaler Branch `agent/I-038`);
nicht pullen, nicht pushen.

## Ziel

Ein Master-Image soll sich ganz über das Tool vorbereiten lassen. Im Dialog „OS installieren …“ gibt es neu die
Option **„Für Master-Image (Audit-Modus)“**. Windows wird wie bei der heutigen Direktinstallation ohne Eingriff
aufgespielt, startet danach aber direkt im **Audit-Modus** (eingebauter Administrator, kein Konto angelegt).
Dort richtet Dominik Treiber und Programme ein, führt Sysprep aus und erstellt mit dem Agent-Stick ein Disk-Image,
das er als Master markiert. Funktioniert gleich am echten Gerät und am VM-Zwilling.

## Hintergrund

- Heute richtet die Direktinstallation Windows vollständig ein (Konto, Computername, Schlüssel, Region) und
  überspringt den ersten Einrichtungsbildschirm – dort bräuchte es **Ctrl+Shift+F3** für den Audit-Modus.
- Microsoft: In der Antwortdatei bewirkt im Durchgang **oobeSystem** die Komponente
  `Microsoft-Windows-Deployment` → `Reseal` → `Mode` = `Audit`, dass Windows nach der Installation im Audit-Modus
  startet (Durchgänge auditSystem/auditUser laufen dann; der eingebaute Administrator meldet sich automatisch an).
  Bitte gegen Microsoft Learn („Reseal“, „Boot Windows to Audit Mode or OOBE“, „Windows Setup Automation
  Overview / implicit answer file search“) prüfen und im Code mit Quelle kommentieren.
- **Wichtig – Antwortdatei darf nicht ins Image:** Die Direktinstallation legt die Antwortdatei unter
  `C:\Windows\Panther\unattend.xml` ab (`winsetup.install_cmd`). Windows sucht bei jedem Setup-Durchgang implizit
  in `%WINDIR%\Panther`. Bliebe sie dort, würde jedes Gerät aus dem Master wieder in den Audit-Modus starten.
  Beim Zurückspielen eines Master-Images überschreibt `deploy.py` diese Datei zwar mit der eigenen
  (`Windows/Panther/unattend.xml`), trotzdem muss die Audit-Antwortdatei entfernt werden, bevor Sysprep läuft
  (Image sauber, auch für Clonezilla oder Zurückspielen ohne „Danach anpassen“).

## Anforderungen

1. **Option im Dialog** „OS installieren …“ (`InstallDialog` in `okula_recovery/os_dialogs.py`), nur bei
   Windows-ISOs sichtbar/aktiv: Häkchen **„Für Master-Image (Audit-Modus)“**, standardmässig aus. Ist es an:
   - Felder Lokales Konto, Benutzername, Passwort, Windows-Schlüssel und der Hinweis zum Computernamen sind
     ausgegraut bzw. werden ignoriert (kein Konto, kein Computername, kein Schlüssel in der Antwortdatei).
   - Region Schweiz, Datenschutz-Fragen, BitLocker-Option bleiben wählbar (sie wirken auf das Master-Image).
     BitLocker-Verhinderung standardmässig an lassen.
   - Die Zusammenfassung im Dialog bzw. `winunattend.summary()` nennt „Startet im Audit-Modus für ein
     Master-Image (kein Konto, kein Computername, kein Schlüssel)“.
2. **Antwortdatei** (`okula_recovery/winunattend.py`): neues Feld in `WinOptions`, z. B. `audit_mode: bool = False`.
   Bei `audit_mode`:
   - oobeSystem: `Microsoft-Windows-Deployment` → `Reseal` → `Mode=Audit` (ForceShutdownNow nicht setzen).
   - Kein `LocalAccount`, kein `AutoLogon` für ein eigenes Konto, keine FirstLogonCommands, kein ComputerName,
     kein ProductKey (auch wenn in den Optionen gesetzt – Audit hat Vorrang).
   - Im Durchgang **auditUser** (oder auditSystem, je nach Microsoft-Doku geeigneter) einen RunSynchronous-Befehl,
     der `%WINDIR%\Panther\unattend.xml` löscht (bzw. umbenennt), damit sie nicht ins Image kommt. Begründung im
     Kommentar. Wenn ein Löschen während des Durchgangs laut Doku nicht sicher ist: Alternative wählen (z. B.
     in `SetupComplete.cmd` bzw. ein Skript, das im Audit-Modus beim Anmelden einmal läuft) und in der
     Abschlussmeldung erklären.
   - Bestehende Teile (Region, BitLocker, Datenschutz) wie bisher.
3. **Aufräumen der Setup-Partition:** Heute löscht `SetupComplete.cmd` (aus `winsetup.setupcomplete_cmd`) am Ende
   der Einrichtung die Setup-Partition „OKULASETUP“ und vergrössert C:. Prüfen (Microsoft-Doku), ob
   `SetupComplete.cmd` auch beim Start in den Audit-Modus läuft. Falls nicht oder unsicher: dafür sorgen, dass
   das Aufräumen im Audit-Modus trotzdem geschieht (z. B. dasselbe Skript zusätzlich als auditSystem-
   RunSynchronous), sonst landet die Setup-Partition im Master-Image. Mehrfachausführung muss harmlos sein.
4. **Hinweis nach dem Start:** Nach erfolgreichem Vorbereiten zeigt das Tool (Log/Verlauf des Geräts) einen Satz,
   was als Nächstes zu tun ist: „Windows startet im Audit-Modus. Einrichten, dann Sysprep:
   `C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown` – danach Windows nicht mehr starten,
   mit dem Agent-Stick ‚Disk-Image erstellen …‘ und das Image als Master markieren.“ Verlaufseintrag z. B.
   „Windows-Installation … für Master-Image (Audit-Modus) vorbereitet“.
5. **VM-Zwilling:** Für VMs gibt es heute einen Snapshot vor der OS-Installation. Nichts Neues nötig; in Hilfe
   und Doku erwähnen, dass vor Sysprep im VM-Fenster ein Snapshot sinnvoll ist (bestehende Snapshot-Funktion,
   Name wie in der Oberfläche).
6. Automatisierung und Master-Zurückspielen (`master_unattend`, `deploy.py`) **nicht** ändern.

## Nicht Teil dieses Auftrags

- Kein Sysprep-Knopf im Tool, kein Auslösen von Sysprep aus der Ferne (später eigene Idee, falls gewünscht).
- Keine Änderung am Boot-Stick-Dialog.
- Keine Änderung der Partitionierung oder des Ablaufs in `wininstall.py` (Agent).

## Hinweise zum Code

- `winunattend.build()` (oobeSystem-Teil, specialize-Teil), `WinOptions`, `summary()`; `winsetup.py`
  (`install_cmd`, `setupcomplete_cmd`, Plan/extra-Dateien); `os_dialogs.InstallDialog` (`options()`,
  `_update()`, Bestätigen); `jobs.py` (Windows-Installation, Verlaufseintrag).
- B-012 (Prüfung `pruefe_kontoname`) bleibt; bei Audit-Modus ist das Konto aus, also keine Prüfung.
- Agent betroffen (neuer Agent-Stick nötig)? Erwartet **nein** (Antwortdatei und Skripte erzeugt der Server).
  Falls doch etwas am Agent nötig ist: klar in der Abschlussmeldung.
- Bestehende Muster für XML-Bausteine (`_Builder.component/sub/commands`) wiederverwenden.

## Oberfläche und Texte

- Häkchen: **„Für Master-Image (Audit-Modus)“**, Tooltip/Hinweis kurz: „Kein Konto, kein Computername, kein
  Schlüssel – Windows startet im Audit-Modus zum Einrichten und für Sysprep.“
- Schreibstil laut `CLAUDE.md` (Handbuch-Stil ohne Anrede).

## Abnahmekriterien

- [ ] Ohne Häkchen ist die erzeugte Antwortdatei unverändert gegenüber heute (Test vergleicht Struktur).
- [ ] Mit Häkchen: Antwortdatei enthält `Reseal/Mode=Audit` im oobeSystem, kein `LocalAccount`, kein
      `AutoLogon`, kein `ComputerName`, kein `ProductKey`, und den Befehl, der `Panther\unattend.xml` entfernt.
- [ ] Setup-Partition wird auch im Audit-Fall aufgeräumt (Test auf die erzeugten Skripte/Befehle).
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests in `tests/test_winunattend.py`
      bzw. `tests/test_winsetup.py`.
- [ ] Hilfe (F1) in `okula_recovery/help_window.py`: Kapitel „Master-Image“ und „Windows / Linux installieren“ um
      den Weg über „Für Master-Image (Audit-Modus)“ ergänzt; `tests/test_help.py` grün.
- [ ] `docs/MASTER-IMAGE.md` und `docs/TECHNIK.md`: neuer Weg beschrieben (inkl. Hinweis Antwortdatei/Panther).
- [ ] `docs/AENDERUNGEN.md`: I-038 ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert.
- [ ] `docs/TESTS.md`: Prüfschritte unter „Offen“ (VM-Zwilling: Installation mit Häkchen → startet im
      Audit-Modus, Setup-Partition weg, C: gross; `Panther\unattend.xml` fehlt; Sysprep → Image → Master →
      Zurückspielen startet NICHT im Audit-Modus, sondern in die normale Einrichtung mit Name/Key).
- [ ] Demo-Gerät: nicht nötig.

## Abschluss

1. Commits mit der ID im Titel (z. B. `I-038: Direktinstallation für Master-Image (Audit-Modus)`), **nur lokal**
   auf `agent/I-038` – **nicht pushen**. **Nur eigene Dateien committen** (`git add <Pfade>`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis, neuer Agent-Stick nötig ja/nein, Schritte für den
   Server (`git pull && sudo ./install.sh`), welche Microsoft-Aussagen geprüft bzw. nur angenommen wurden
   (Reseal/Audit, SetupComplete im Audit-Modus, Löschen der Antwortdatei), offene Punkte.
