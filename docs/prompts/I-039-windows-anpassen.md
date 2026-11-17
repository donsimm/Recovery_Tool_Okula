# I-039 – Windows anpassen … (Einstellungen nach der Installation)

Status: umgesetzt (Commit 7442001) · erstellt 17.11.2026 von der Projektleitung · Freigabe: Dominik 17.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag I-039 in `docs/AENDERUNGEN.md`
(Tabelle und „📌 Entscheidungen“), `docs/ORDNER-SENDEN.md` (Vorbild für Bedienung und Ablauf) und in `docs/TECHNIK.md`
die Abschnitte zu *Ordner senden* und *Anpassen*. Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet
wurde (lokaler Branch `agent/I-039`); nicht pullen, nicht pushen.

## Ziel

Nach einer Installation (oder jederzeit) lassen sich an einem Gerät mit Windows per Häkchen Einstellungen umstellen
oder abschalten – Store-Apps entfernen, Windows Update aus, Energie für Dauerbetrieb, automatische Anmeldung usw.
Bedienung wie *Ordner senden*: Gerät läuft mit dem Agent, Dialog wählen, senden; beim nächsten Windows-Start setzt
Windows die Einstellungen selbst um. Vorgegebene Vorlagen „Player“ und „Laptop“ setzen die Häkchen mit einem Klick.

## Entscheide aus dem Brainstorming

- Eigene Funktion **„Windows anpassen …“** wie *Ordner senden* (Dominik 17.11.). Kombination mit *Danach anpassen*,
  Direktinstallation und Automatisierung kommt **später**, nicht in diesem Auftrag.
- Umsetzung über ein **einmaliges Startskript**: Der Agent legt es auf die Windows-Partition, Windows führt es beim
  nächsten Start **ohne Anmeldung als SYSTEM** aus; danach entfernt es sich selbst (Dominik 17.11.).
- Vorlagen **„Player“** und **„Laptop“** fest vorgegeben (keine eigenen Vorlagen speichern) (Dominik 17.11.).
- **Automatische Anmeldung** gehört dazu (Dominik 17.11.).
- Optionen aus dem TGF-TuningPack 4.3 ausgewählt; riskante Punkte bewusst nicht (Liste unter „Nicht Teil“).

## Anforderungen

1. **Optionen** (Schlüssel im Code englisch/kurz, Beschriftung wie hier). Jede Option ist ein Baustein in PowerShell
   (Windows PowerShell 5.1, Windows 10 22H2 und Windows 11), unabhängig von den anderen, Fehler werden protokolliert und
   der nächste Baustein läuft weiter.

   | Gruppe | Option (Beschriftung) | Umsetzung (Richtung) |
   |---|---|---|
   | Apps | Store-Apps entfernen: Xbox · Bing (Wetter, News …) · Groove/Filme & TV · Solitaire · Kontakte · Smartphone-Link · Kamera · Office/Office-Hub · 3D-Viewer/Paint 3D/Mixed Reality · Feedback-Hub/Tipps/Hilfe · Microsoft Store | je Gruppe Name-Muster; `Remove-AppxPackage -AllUsers` **und** `Remove-AppxProvisionedPackage -Online` (sonst bricht ein späteres Sysprep ab); Frameworks (VCLibs, .NET.Native, UI.Xaml), `NonRemovable` und NVIDIA/Realtek/Intel-Apps nie |
   | Apps | Wiederinstallation von Werbe-Apps sperren | Richtlinie `CloudContent\DisableWindowsConsumerFeatures=1`, ContentDeliveryManager-Werte (u. a. `SilentInstalledAppsEnabled`, `PreInstalledAppsEnabled`, `OemPreInstalledAppsEnabled`) für alle vorhandenen Benutzer **und** das Standardprofil (`C:\Users\Default\NTUSER.DAT`) |
   | Apps | OneDrive entfernen | Prozess beenden, `OneDriveSetup.exe /uninstall`, Run-Eintrag im Standardprofil weg, Richtlinie `DisableFileSyncNGSC=1` |
   | Apps | Cortana aus | Richtlinie `Windows Search\AllowCortana=0` |
   | Updates | Windows Update aus | Richtlinie `WindowsUpdate\AU\NoAutoUpdate=1` |
   | Updates | Keine Treiber über Windows Update | `ExcludeWUDriversInQualityUpdate=1`, `DriverSearching\SearchOrderConfig=0` |
   | Updates | Keine automatischen App-Updates | `WindowsStore\AutoDownload=2` |
   | Betrieb | Energieplan Höchstleistung | `powercfg /setactive` (GUID Höchstleistung; fehlt er, aus Vorlage duplizieren) |
   | Betrieb | Bildschirm und Standby nie ausschalten | `powercfg /change monitor-timeout-ac 0`, `standby-timeout-ac 0` (auch `-dc`) |
   | Betrieb | Ruhezustand aus | `powercfg /hibernate off` |
   | Betrieb | Schnellstart aus | `HiberbootEnabled=0` (hilft auch dem Agent: NTFS sauber) |
   | Betrieb | Sperrbildschirm aus | Richtlinie `Personalization\NoLockScreen=1` |
   | Betrieb | Tipps, Vorschläge und Benachrichtigungen aus | ContentDeliveryManager `SubscribedContent-*`, `SystemPaneSuggestionsEnabled=0`, `SoftLandingEnabled=0`; Toasts aus (`PushNotifications\ToastEnabled=0`) – für alle Benutzer und Standardprofil |
   | Betrieb | Einrastfunktion und Anschlagverzögerung aus | `Accessibility\StickyKeys\Flags=506`, `Keyboard Response\Flags=122` – alle Benutzer und Standardprofil |
   | Datenschutz | Telemetrie minimal | Richtlinie `DataCollection\AllowTelemetry=0` (Pro: wirkt wie 1), Dienst DiagTrack deaktivieren |
   | Datenschutz | Werbe-ID aus | Richtlinie `AdvertisingInfo\DisabledByGroupPolicy=1` |
   | Datenschutz | Standort aus | Richtlinie `LocationAndSensors\DisableLocation=1` |
   | Datenschutz | Fehlerberichte aus | Richtlinie `Windows Error Reporting\Disabled=1` |
   | Datenschutz | Bing-Suche im Startmenü aus | `DisableWebSearch=1`, `ConnectedSearchUseWeb=0`; Benutzer: `BingSearchEnabled=0` |
   | Explorer und Desktop | Dateiendungen anzeigen | `HideFileExt=0` – alle Benutzer und Standardprofil |
   | Explorer und Desktop | Versteckte Dateien anzeigen | `Hidden=1` |
   | Explorer und Desktop | Explorer öffnet „Dieser PC“ | `LaunchTo=1` |
   | Explorer und Desktop | Symbole „Dieser PC“ und „Netzwerk“ auf dem Desktop | `HideDesktopIcons\NewStartPanel` CLSID-Werte = 0 |
   | Explorer und Desktop | Suchfeld und Taskansicht aus der Taskleiste | `SearchboxTaskbarMode=0`, `ShowTaskViewButton=0` |
   | Dienste | Windows Search · Xbox-Dienste · SysMain · Remote-Registrierung · Druckwarteschlange | je Häkchen: Dienst stoppen, Starttyp *Deaktiviert* |
   | Anmeldung | Automatische Anmeldung (Benutzername, Passwort) | Winlogon `AutoAdminLogon=1`, `DefaultUserName`, `DefaultPassword`, `DefaultDomainName` = Computername; Konto fehlt → Fehler im Protokoll, nichts setzen |

   „Für alle Benutzer“ heisst: Werte unter `HKU\<SID>` aller vorhandenen lokalen Profile (geladene direkt, sonst
   `NTUSER.DAT` laden/entladen) **und** im Standardprofil, damit auch später angelegte Konten sie bekommen.

2. **Vorlagen** (fest im Code):
   - **Player:** alles an ausser *Kamera*, *Druckwarteschlange*; automatische Anmeldung an (Felder müssen ausgefüllt
     werden, sonst lässt sich nicht senden).
   - **Laptop:** Apps ausser *Kamera* und *Microsoft Store*; Wiederinstallation sperren; Cortana aus; Updates **nicht**
     anfassen; Betrieb nur *Schnellstart aus*, *Tipps … aus*, *Einrastfunktion … aus*; Datenschutz alles;
     Explorer und Desktop alles; Dienste nur *Xbox-Dienste* und *Remote-Registrierung*; keine automatische Anmeldung.
   - Auswahl einer Vorlage setzt die Häkchen; danach sind einzelne Häkchen änderbar (Anzeige „Vorlage: Player (geändert)“).

3. **Startskript:** Mechanismus selbst wählen und in `TECHNIK.md` begründen. Bedingungen: läuft beim nächsten Start
   **vor/ohne Anmeldung als SYSTEM** auf Windows 10 Pro 22H2 und Windows 11 Pro; wird vom Agent **offline** (Linux,
   Windows-Partition mit ntfs-3g, Werkzeuge auf dem Stick, z. B. `hivexsh -w` aus libhivex-bin) eingerichtet;
   **bestehende Einstellungen bleiben erhalten** (z. B. eine vorhandene lokale Gruppenrichtlinie nicht überschreiben,
   sondern ergänzen bzw. nach dem Lauf wiederherstellen); läuft genau einmal und räumt sich danach vollständig auf
   (Skript, Registrierung/Aufgabe); läuft bei einem Fehler nicht in einer Schleife. Bekannte Kandidaten:
   Startskript der lokalen Gruppenrichtlinie (`System32\GroupPolicy\gpt.ini` + `Machine\Scripts\scripts.ini`) oder
   ein Dienst/Eintrag, der offline im SOFTWARE/SYSTEM-Hive angelegt wird. Microsoft Learn als Quelle nennen.
4. **Protokoll** auf dem Gerät: `C:\Windows\Temp\okula-windows-anpassen.log` (Zeitstempel, je Option ok/Fehler).
   Passwort der automatischen Anmeldung **nie** ins Protokoll, nicht in die Vorlagen, nicht in Verlauf/Log des Tools;
   im Skript auf der Disk nur so lange wie nötig (Skript löscht sich nach dem Lauf; Passwort steht danach – wie bei
   Windows üblich – nur in Winlogon). Im Dialog Hinweis, dass das Passwort im Klartext in der Registrierung liegt.
5. **Ablauf im Tool** wie *Ordner senden*: Gerät läuft mit dem Agent; Windows-Partition finden (gleiche Logik);
   Windows im Ruhezustand/Schnellstart (NTFS nicht sauber) → klare Meldung wie bei *Ordner senden*; kein Windows auf
   der Disk → Meldung, nichts tun. Auftrag in der Auftragsliste, Eintrag im Verlauf des Geräts mit den gewählten
   Optionen (Kurzform). Neuer Agent-Befehl (z. B. `tweak`) – ein älterer Agent meldet „Agent zu alt …“ (`_old_agent`).
6. **Demo-Gerät:** Befehl annehmen und „fertig“ melden (wie `deliver` im `demo_agent.py`).

## Nicht Teil dieses Auftrags

- Kombination mit *Danach anpassen*, Direktinstallation, Automatisierung, Master-Ablauf (später).
- Eigene Vorlagen speichern; Software installieren (I-020); Ergebnis-Protokoll zurück ins Tool lesen.
- Bewusst **nie** (Entscheid 17.11., aus dem TuningPack gestrichen): Utilman durch CMD ersetzen, Sicherheitscenter oder
  Defender aus, Microsoft-Server sperren (hosts/Firewall), Zeitsynchronisation aus, Admin-Freigaben aus,
  Gaming-/TCP/IP-/Speicher-„Tweaks“, Entwicklermodus, Core Parking, Windows-Fehlerwiederherstellung beim Start aus.
- Linux-Systeme.

## Hinweise zum Code

- Vorbild *Ordner senden*: Menü `ui.py` (`MENU_LABELS`, `on_send_folders`, Kontextmenü um Zeile 2232),
  Gerätefenster `device_window.py` (Knopf „Ordner senden …“), Dialog `automation_tab.SendFoldersDialog`,
  Auftrag `jobs.deliver_work`, Client `agentclient.deliver`/`customize`, Agent `agent.py` (Befehlsliste um Zeile 454,
  Beschriftungen um Zeile 293/314/355) und `deploy.deliver`/`deploy.customize` (Windows-Partition einhängen).
- PowerShell-Bausteine als Textvorlagen in einem eigenen Modul (z. B. `okula_recovery/wintweaks.py`): Optionen,
  Vorlagen, Skript-Erzeugung – ohne GTK, gut testbar. Das Skript im Tool erzeugen und an den Agent senden; der Agent
  legt es nur ab und richtet den Start ein.
- Agent betroffen (neuer Agent-Stick nötig)? **ja** (neuer Befehl). Werkzeug fürs Hive-Schreiben auf dem Stick
  prüfen (`stick.py`, Paketliste); fehlt eins, ergänzen.
- Reihenfolge: zuerst Agent, dann Tool-Logik (`wintweaks.py`, Auftrag), zuletzt Oberfläche.
- Tests: Skript-Erzeugung je Option und Vorlage (enthält erwartete Befehle, Passwort nie im Protokollteil, Selbst-
  Aufräumen vorhanden), Einrichtung des Startmechanismus auf einem Probe-Verzeichnis/Probe-Hive, Vorlagen-Häkchen,
  Ablehnung bei fehlendem Windows, Demo-Agent.

## Oberfläche und Texte

- Menü Gerät und Kontextmenü: **„Windows _anpassen …“** direkt unter „Ordner senden …“; Gerätefenster: Knopf
  **„Windows anpassen …“** neben „Ordner senden …“.
- Dialog „Windows anpassen“: oben *Vorlage* (Auswahl: Player, Laptop, Keine), darunter Gruppen mit Häkchen
  (Beschriftungen wie in der Tabelle), Gruppe *Anmeldung* mit Benutzername/Passwort (Passwort verdeckt), unten
  Hinweis „Wird beim nächsten Windows-Start umgesetzt. Protokoll: C:\Windows\Temp\okula-windows-anpassen.log“,
  Knöpfe *Abbrechen* / *Senden*. Bei vielen Häkchen scrollbar, Fenstergrösse passend.
- Schreibstil laut `CLAUDE.md` (Handbuch-Stil ohne Anrede, Fortschritt als Vorgang: „Einstellungen werden übertragen …“).

## Abnahmekriterien

- [ ] Dialog mit allen Optionen; Vorlagen setzen die Häkchen wie beschrieben; automatische Anmeldung ohne Felder
      sperrt *Senden*
- [ ] Senden an ein Gerät mit Agent legt Skript und Startmechanismus an; Windows im Schnellstart → klare Meldung
- [ ] Skript: jede Option einzeln, Fehler stoppen den Rest nicht, Protokoll ohne Passwort, Selbst-Aufräumen
- [ ] Bestehende lokale Gruppenrichtlinie bzw. Einträge bleiben erhalten (Test mit Probe-Daten)
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests wie oben
- [ ] Hilfe (F1) in `okula_recovery/help_window.py`: neues Kapitel „Windows anpassen“ (Optionen, Vorlagen, Ablauf,
      Hinweis Passwort im Klartext, Protokoll), Menüeintrag in `MENU_LABELS`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Eintrag ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Abschnitt 19 „Windows anpassen (I-039)“ – VM mit Windows 10 und Windows 11: Vorlage Player
      senden → Neustart → Apps weg, automatische Anmeldung, Energie, Protokoll vorhanden, Skript und
      Startmechanismus weg; zweiter Start ohne erneuten Lauf; Laptop-Vorlage; Gerät im Schnellstart
- [ ] `docs/TECHNIK.md`: Abschnitt ergänzt (Mechanismus mit Begründung und Quelle, Bausteine, Sicherheit Passwort)
- [ ] Demo-Gerät: Funktion vorführbar (meldet „fertig“)

## Abschluss

1. Ein Commit (oder wenige, sinnvoll getrennt) mit der ID im Titel, z. B. `I-039: Windows anpassen`, **nur lokal** auf
   dem Branch `agent/I-039` – **nicht pushen**, das macht Okuli nach der Abnahme. **Nur eigene Dateien committen**
   (`git add <Pfade>`, nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit danach ist ok).
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis, ob ein neuer Agent-Stick nötig ist, Schritte für
   den Server (`git pull && sudo ./install.sh`), gewählter Startmechanismus mit Quelle, offene Punkte oder
   Abweichungen vom Prompt.
