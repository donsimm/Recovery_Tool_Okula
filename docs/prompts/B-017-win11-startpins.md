# B-017 – Windows anpassen an Win11 24H2 Pro: Startmenü-Kacheln, falsche FEHLER-Zeilen, Widgets

Status: offen · erstellt 19.11.2026 von der Projektleitung · Freigabe: Dominik 19.11. (Test an der VM)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge B-017 und Ä-042 in `docs/AENDERUNGEN.md`,
`docs/prompts/Ä-042-win11-clean.md`. Lokaler Branch `agent/B-017`; nicht pullen, nicht pushen. 1–2 Commits.

## Befund (Okuli, 19.11., VM-Win11-test, Windows 11 Pro 24H2 Build 26100.8036, Protokoll
`C:\Windows\Temp\okula-windows-anpassen.log` gelesen)

1. **Startmenü:** Danach angeheftet: Edge, Einstellungen, WhatsApp, Adobe Express, LinkedIn, Explorer – die Liste aus
   `START_PINS` wurde nicht angewendet. Protokoll: „Gruppenrichtlinie ConfigureStartPins gesetzt (Policy CSP: Ungültige
   Eigenschaft "ConfigureStartPins")“. Die MDM-Bridge klappt an diesem unverwalteten Pro also nicht. Der Ersatz
   schreibt den JSON-**Text** als String in `HKLM\Software\Policies\Microsoft\Windows\Explorer\ConfigureStartPins`.
   Laut `C:\Windows\PolicyDefinitions\StartMenu.admx` der VM (geprüft) ist die Richtlinie aber so definiert:
   ```xml
   <policy name="ConfigureStartPins" class="Both" key="Software\Policies\Microsoft\Windows\Explorer"
           valueName="ConfigureStartPins">  <!-- enabledValue decimal 1 / disabledValue 0 -->
     <supportedOn ref="windows:SUPPORTED_Windows_11_0_24H2" />
     <elements><text id="ConfigureStartPins_Name" valueName="ConfigureStartPinsJSON" expandable="true"/></elements>
   ```
   Microsoft Learn („Customize the Start layout“, GPO-Tabelle): Wert = „Path to the JSON file“.
2. **Falsche FEHLER-Zeilen:** 19× „<App> (vorinstalliert): Das System kann die angegebene Datei/den angegebenen Pfad
   nicht finden“ (Outlook, Teams, Clipchamp, Rechner, Medien-Erweiterungen …), obwohl die Apps weg sind.
   Vermutung: `Remove-AppxPackage -AllUsers` entfernt bei 24H2 auch die Bereitstellung, die zwischengespeicherte Liste
   aus `Get-OkulaPackages 'Provisioned'` ist danach veraltet. Weil `Remove-OkulaApps` bei Fehlern wirft, fehlen die
   tatsächlich entfernten Pakete im Protokoll.
3. **Widgets:** Wetter („11°C Nuvoloso“) bleibt in der Taskleiste, Option Widgets war gewählt (Protokoll: Fehler wie 2.).
4. **Aufräumen:** „Startskript und Gruppenrichtlinie aufräumen: Das Element unter "…\Scripts\Startup" kann nicht
   entfernt werden, da es gerade verwendet wird“ als FEHLER – `scripts.ini` ist aber entfernt, nur der leere Ordner
   bleibt (geprüft). Kein echter Fehler.

## Anforderungen

1. **Startmenü (`START_CLEAN`, `wintweaks.py` um Zeile 320–352):**
   - JSON als Datei ablegen, z. B. `C:\ProgramData\Okula\StartPins.json` (UTF-8 ohne BOM; Ordner bleibt beim
     Aufräumen und beim Nachlauf erhalten).
   - Ab Build 26100: Richtlinie wie im ADMX setzen – `ConfigureStartPins` = 1 (DWORD), `ConfigureStartPinsJSON` =
     Pfad (REG_EXPAND_SZ) unter `HKLM\Software\Policies\Microsoft\Windows\Explorer`. Den bisherigen falschen
     String-Wert ersetzen (beim erneuten Lauf auf bereits angepassten Geräten).
   - MDM-Bridge nur noch für Builds < 26100 versuchen (oder zusätzlich, wenn sie nicht stört); klappt sie nicht,
     ehrlich als FEHLER melden („Windows 11 vor 24H2: Startmenü nur mit Geräteverwaltung“).
   - `applyOnce` beibehalten. Prüfen (Microsoft Learn), ob `packagedAppId` oder `packagedAppID` die richtige
     Schreibweise ist, und an Learn angleichen.
   - Protokoll-/Tooltip-Text anpassen.
2. **Entfernen (`Remove-OkulaApps`):** vor `Remove-AppxProvisionedPackage` prüfen, ob das Paket noch bereitgestellt
   ist (Liste nach dem Entfernen der installierten Pakete neu lesen bzw. Fehler 0x80070002/0x80070003 als „schon
   entfernt“ werten). Protokollzeile nennt immer die entfernten Pakete, auch wenn es zusätzlich echte Fehler gibt
   (z. B. „X, Y entfernt; Fehler: Z: …“). Gleiche Logik im Nachlauf.
3. **Widgets:** zusätzlich die Richtlinie „Widgets nicht zulassen“ setzen (`HKLM\Software\Policies\Microsoft\Dsh`,
   `AllowNewsAndInterests` = 0 – mit Microsoft Learn belegen, Policy CSP NewsAndInterests), damit das Wetter aus der
   Taskleiste verschwindet, auch wenn das Paket bleibt.
4. **Aufräumen:** „wird verwendet“ beim leeren Ordner `Scripts\Startup` nicht als FEHLER, sondern als ok mit Hinweis;
   echter Fehler nur, wenn `scripts.ini` bzw. die Registrierung des Startskripts bleibt.
5. **Tests** (`tests/test_wintweaks.py` o. ä.): erzeugtes Skript enthält `ConfigureStartPinsJSON`, DWORD 1, Pfad,
   JSON-Datei-Inhalt gültig; Widgets-Richtlinie; Neu-Lesen bzw. Fehlercode-Behandlung bei vorinstallierten Paketen.

## Nicht Teil dieses Auftrags

- Neue Optionen oder Vorlagen; Änderungen an den Paketlisten.
- „Empfohlen“-Bereich („Erste Schritte“) – nur in der Rückmeldung sagen, ob es dafür eine Richtlinie gibt, die bei
  Pro wirkt (Microsoft Learn), nicht umsetzen.

## Hinweise zum Code

- `okula_recovery/wintweaks.py`: `START_PINS`, `start_pins_json`, Option `START_CLEAN`, `Remove-OkulaApps`
  (um Zeile 685), Nachlauf (um Zeile 756), Aufräumen. Neuer Agent-Stick nötig? Voraussichtlich **nein** – bestätigen.

## Abnahmekriterien

- [ ] Startmenü-Richtlinie wie im ADMX (DWORD + Pfad), JSON-Datei bleibt erhalten
- [ ] Keine FEHLER mehr für schon entfernte vorinstallierte Pakete; entfernte Pakete stehen immer im Protokoll
- [ ] Widgets-Richtlinie gesetzt; Aufräumen meldet „Ordner in Verwendung“ nicht als FEHLER
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`
- [ ] `docs/AENDERUNGEN.md` (B-017 ins Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md` Abschnitt 26
      (Prüfpunkte: Startmenü nur mit den festen Kacheln, keine Wetteranzeige, Protokoll ohne falsche FEHLER)

## Abschluss

1. Commit(s) mit `B-017: …` im Titel, nur lokal auf `agent/B-017`; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis, Quellen, neuer Agent-Stick ja/nein, Antwort zu „Empfohlen“.
