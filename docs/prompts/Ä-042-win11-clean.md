# Ä-042 – Windows anpassen: Win11 wirklich clean (Startmenü-Platzhalter, fehlende Apps, Vorlage „Clean“)

Status: freigegeben · erstellt 18.11.2026 von der Projektleitung · Freigabe: Dominik 18.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, die Einträge Ä-042, I-039, Ä-040 und „📌 Entscheidungen“ in
`docs/AENDERUNGEN.md`, `docs/prompts/I-039-windows-anpassen.md`, in `docs/TECHNIK.md` den Abschnitt *Windows anpassen*.
Gearbeitet wird in der eigenen Kopie (lokaler Branch `agent/AE-042`); nicht pullen, nicht pushen. 1–2 Commits.
Microsoft Learn (`learn.microsoft.com`) und `support.microsoft.com` darfst du mit WebFetch lesen – Quellen nennen.

## Ziel

Nach *Windows anpassen* mit allem angehakt ist ein Windows 11 **wirklich sauber**: keine Werbe-Kacheln (WhatsApp,
LinkedIn, Adobe Express, Clipchamp, Audiorecorder, Kurznotizen, Teams …) im Startmenü, keine nachgeladenen Werbe-Apps,
keine Outlook (neu)/Dev Home/Bing Search. Nützliche Windows-Bordmittel bleiben.

## Befund (18.11., Win11-VM nach *Windows anpassen* mit allem angehakt)

Dominik sah danach noch: WhatsApp, LinkedIn, Outlook, Adobe Express, Audiorecorder, Clipchamp, Kurznotizen, Teams.
`Get-AppxPackage -AllUsers` (Liste von Dominik) enthält davon **nur** `Microsoft.OutlookForWindows`, dazu
`Microsoft.Windows.DevHome` und `Microsoft.BingSearch` – **nicht** WhatsApp, LinkedIn, Adobe Express, Clipchamp,
SoundRecorder, StickyNotes, MSTeams. Folgerung (Okuli): Das sind **Platzhalter-Kacheln** im Standard-Startlayout von
Win11, die erst beim Klick bzw. später im Hintergrund installiert werden. Ausserdem:
- `DisableWindowsConsumerFeatures` (Option „Wiederinstallation von Werbe-Apps sperren“) wirkt laut Microsoft Learn
  (Policy CSP Experience/AllowWindowsConsumerFeatures) **nur bei Enterprise/Education, nicht bei Pro**.
- `Start/ConfigureStartPins` (Policy CSP Start; GPO `Software\Policies\Microsoft\Windows\Explorer\ConfigureStartPins`,
  JSON) gilt laut Microsoft Learn **auch für Pro**, ab Win11 21H2 per CSP, per GPO ab 24H2 mit KB5062660.
- `Microsoft.BingSearch` blieb trotz Häkchen „Bing“ (`Microsoft.Bing*`) – Ursache klären (später nachgeliefert?
  Provisioned nicht entfernt? Fehler im Protokoll `C:\Windows\Temp\okula-anpassen.log` bzw. wie es heisst).
- Auf der VM fehlen auch Rechner, Editor, Paint, Fotos, Snipping Tool, Terminal – das Tool entfernt sie nicht und soll
  sie auch künftig **nicht** entfernen.

## Anforderungen

1. **Startmenü leeren/ersetzen** (neue Option „Startmenü: Werbe-Kacheln entfernen“, Gruppe Apps bzw. Explorer):
   Win11-Startlayout so setzen, dass nur gewünschte Kacheln (z. B. Edge, Explorer, Einstellungen, Rechner, Editor,
   Fotos, Snipping Tool, Terminal – sofern installiert) bzw. gar keine stehen. Weg wählen und mit Quelle begründen:
   `ConfigureStartPins` (Richtlinie, Wirkung bei Pro, Build-Abhängigkeit, „nur einmal anwenden“-Variante, damit
   Benutzer später selbst anheften können) und/oder `start2.bin`/`LayoutModification.json` im Standardprofil.
   Muss für **neue Benutzer** und den **bestehenden** Benutzer wirken. Zusammenspiel mit Ä-040 (`winprofile.py`,
   LayoutModification.xml für die Taskleiste) beachten – nichts davon kaputt machen. Win10: Option ohne Wirkung bzw.
   ausgeblendet, sauber begründet.
2. **Weitere Apps** als Häkchen (Store-Apps, je Gruppe sinnvoll, Muster belegen): Outlook (neu)
   `Microsoft.OutlookForWindows`, Mail/Kalender `microsoft.windowscommunicationsapps`, Teams `MSTeams`/
   `MicrosoftTeams`, Clipchamp `Clipchamp.Clipchamp`, Audiorecorder `Microsoft.WindowsSoundRecorder`, Kurznotizen
   `Microsoft.MicrosoftStickyNotes`, Dev Home `Microsoft.Windows.DevHome`, Copilot `Microsoft.Copilot`/
   `Microsoft.Windows.Ai.Copilot.Provider`, To Do `Microsoft.Todos`, Power Automate `Microsoft.PowerAutomateDesktop`,
   Journal, Family `MicrosoftCorporationII.MicrosoftFamily`, Schnellhilfe `MicrosoftCorporationII.QuickAssist`,
   Karten `Microsoft.WindowsMaps`, Wecker `Microsoft.WindowsAlarms`, Erste Schritte `Microsoft.Getstarted`,
   Widgets `MicrosoftWindows.Client.WebExperience`, Bing Search `Microsoft.BingSearch`, sowie die nachgeladenen
   Werbe-Apps (WhatsApp `5319275A.WhatsAppDesktop`, LinkedIn, Adobe Express, Spotify, Disney+, Instagram, TikTok,
   Prime Video … – Paketnamen belegen, sonst mit Wildcard sicher genug wählen). **Nie** entfernen: Frameworks
   (VCLibs, WindowsAppRuntime, UI.Xaml, .NET), System-/NonRemovable-Pakete, Edge, Rechner, Editor, Paint, Fotos,
   Snipping Tool, Terminal, Store (bleibt eigenes Häkchen), Sicherheit, Treiber-Apps.
3. **Werbe-Apps, die später kommen:** Nachgeladene Apps kommen u. U. erst nach der ersten Anmeldung/nach Updates.
   Lösung mit Quelle: z. B. CDM-Werte (bestehend), Platzhalter weg (Punkt 1), und/oder ein einmaliger zweiter
   Aufräumlauf (geplante Aufgabe nach der ersten Anmeldung bzw. nach x Minuten, entfernt sich selbst, Protokoll).
   Klären, warum `Microsoft.BingSearch` blieb, und beheben.
4. **Option „Wiederinstallation von Werbe-Apps sperren“:** Text/Tooltip ehrlich: Richtlinie wirkt nur bei
   Enterprise/Education; bei Pro wirken die CDM-Werte und Punkt 1/3.
5. **Vorlage „Clean“:** alle Apps-Häkchen inkl. neuer, Startmenü leeren, Werbe-Apps sperren, Tipps aus, Telemetrie
   minimal, Bing-Suche aus usw. – Store und Kamera bleiben wählbar (in „Clean“ aus = bleiben installiert). Vorlagen
   „Player“/„Laptop“ um die neuen Apps und die Startmenü-Option ergänzen (Laptop: Kurznotizen/Audiorecorder ok zu
   entfernen? → wie die übrigen Apps behandeln, im Bericht nennen).
6. **Tests:** neue Optionen im erzeugten Skript, Muster nie auf Schutzliste (Test: keine Option trifft
   Rechner/Editor/Paint/Fotos/Snipping/Terminal/Edge/Frameworks), Startlayout-Datei/Richtlinie korrekt, Vorlage „Clean“,
   zweiter Aufräumlauf (Skript: legt Aufgabe an, entfernt sich), nur ASCII wo cmd.

## Nicht Teil dieses Auftrags

- Rechner, Editor, Paint, Fotos, Snipping Tool, Terminal, Edge entfernen.
- Windows 10 neu gestalten (bleibt wie I-039), Store-Apps installieren, Software-Bibliothek.

## Hinweise zum Code

- `okula_recovery/wintweaks.py` (`OPTIONS`, `_apps`, `Remove-OkulaApps` um Zeile 490, `TEMPLATES`, `build_script`),
  `winprofile.py` (Ä-040, LayoutModification.xml), `deploy.py`, Dialog *Windows anpassen*, Automatisierung (Vorlagen).
- Agent betroffen (neuer Agent-Stick nötig)? Voraussichtlich **nein** (Skript wird im Tool erzeugt) – bestätigen.

## Oberfläche und Texte

- Neue Häkchen in den bestehenden Gruppen, Vorlage „Clean“ im Vorlagen-Auswahlfeld. Schreibstil laut `CLAUDE.md`.
- Hilfe (F1), Kapitel *Windows anpassen*: Startmenü-Kacheln (warum Platzhalter), Vorlage „Clean“, was bleibt.

## Abnahmekriterien

- [ ] Startmenü nach „Clean“ ohne Werbe-Kacheln (Lösung mit Quelle, Pro-tauglich, neue und bestehende Benutzer)
- [ ] Neue App-Häkchen; Schutzliste per Test abgesichert
- [ ] Später nachgeladene Werbe-Apps werden entfernt; Bing Search geklärt
- [ ] Vorlage „Clean“; „Player“/„Laptop“ ergänzt
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; Hilfe angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md` (neuer Abschnitt „Win11
      clean (Ä-042)“: VM Win11 Pro, Vorlage „Clean“, Startmenü prüfen, nach 1 h/Neustart nochmals prüfen, Appx-Liste)

## Abschluss

1. 1–2 Commits mit `Ä-042: …` im Titel, **nur lokal** auf `agent/AE-042` – **nicht pushen**. Nur eigene Dateien committen.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Commits, Testergebnis, gewählte Lösung Startmenü mit Quellen, Liste der Pakete je
   Häkchen, neuer Agent-Stick ja/nein, offene Punkte.
