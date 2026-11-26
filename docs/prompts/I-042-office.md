# I-042 – Microsoft 365 Apps einzeln installieren (Office, Click-to-Run)

Status: Entwurf · erstellt 26.11.2026 von der Projektleitung · Entscheide Dominik 25./26.11. · Freigabe: –

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag I-042 und „📌 Entscheidungen“ (Office, 26.11.)
in `docs/AENDERUNGEN.md`, Protokoll-Einträge I-020, Ä-041, Ä-043, Ä-044, Ä-050 (Software-Bibliothek, Erkennung,
Software installieren, Info-Feld), `docs/TECHNIK.md` Abschnitt Software. Lokaler Branch `agent/I-042`; nicht pullen,
nicht pushen. **Drei Commits:** Teil A (Bibliothek/Erkennung), Teil B (Auswahl und Konfiguration), Teil C
(Installation auf dem Gerät, Hilfe, Doku). Nach jedem Teil alle Tests grün.

Kein Internet im Agent: Die nötigen Fakten von Microsoft Learn stehen unten („Belege“) – nur diese verwenden, nichts
dazuerfinden; Unsicheres in der Rückmeldung nennen.

## Ziel

Die Geräte sind Okulas **Mietgeräte** (viele Modelle). Office (Microsoft 365 Apps) soll sich wie jedes andere
Programm aus der Software-Bibliothek still installieren lassen – mit **einzeln wählbaren Apps**. Aktiviert wird nie
im Tool: der Mieter meldet sich in Office mit seinem eigenen Microsoft-365-Konto an (kein Schlüssel, kein Okula-Konto).

## Entscheide (Dominik 25./26.11.) – verbindlich

- Produkte je Auftrag wählbar: **Apps for business** (`O365BusinessRetail`) oder **Apps for enterprise**
  (`O365ProPlusRetail`). Kauf-Office 2024 nicht.
- Sprache `de-de`; Kanal `Current`; 64 Bit; Updates eingeschaltet (Office aktualisiert sich danach selbst).
- Apps einzeln: **Word, Excel, PowerPoint, Outlook (klassisch), OneNote, OneDrive** vorausgewählt; **Access,
  Publisher** wählbar, aus. **Teams** wird nie über Office installiert (eigener Bibliothekseintrag, falls gewünscht).
  Neues Outlook (`OutlookForWindows`) und Skype for Business (`Lync`) immer ausschliessen.
- **Quelle A (Standard):** Dominik lädt Office auf einem Windows-PC mit dem ODT herunter (`setup.exe /download`)
  und lädt den Ordner (`setup.exe`, `download.xml`, `Office\Data\<Version>\…`) mit *Ordner laden …* in die Bibliothek.
  Installation dann **ohne Internet** aus der lokalen Kopie. **Quelle B (Rückfall):** Eintrag ohne `Office\Data`
  (nur `setup.exe`) → das Gerät lädt beim Installieren aus dem Internet (kein `SourcePath`); im Tool deutlich als
  „lädt aus dem Internet“ markiert.

## Teil A – Bibliothek und Erkennung (`software.py`, `installerinfo.py`, `software_ui.py`)

1. Neuer Typ **„Office (Microsoft 365 Apps)“** in `KINDS`: erkannt, wenn ein geladener Ordner `setup.exe` (ODT) und
   `Office\Data\<Version>\` enthält (Version aus dem Ordnernamen, z. B. `16.0.19328.20000` → Spalte Version;
   Programm „Microsoft 365 Apps“, Hersteller „Microsoft“). Nur `setup.exe` des ODT ohne `Office\Data` → derselbe Typ
   mit Quelle B. ODT-`setup.exe` sicher von anderen `setup.exe` unterscheiden (Versionsinfo/Produktname des PE,
   siehe bestehende Erkennung; bei Zweifel nicht als Office erkennen).
2. Status „bereit“ ohne Parameter-Eingabe (Parameter erzeugt das Tool je Auftrag, Teil B). In der Liste Typ
   „Office“, Info-Spalte bleibt frei für Dominik; Angaben unter der Liste nennen Quelle A („lokal, Version …,
   … GB“) bzw. B („lädt beim Installieren aus dem Internet“).
3. Mehrere Office-Einträge (z. B. neuere Version) wie bei anderen Programmen: neue Version löst alte ab (bestehendes
   Verhalten), alte bleibt bis zum Löschen.

## Teil B – Auswahl und Konfiguration (Software installieren, Danach anpassen, OS installieren, Automatisierung)

1. Wird in der Software-Auswahl (`SoftwareChooser`) ein Office-Eintrag angehakt, erscheinen darunter die Optionen:
   **Produkt** (business / enterprise, Standard business), Häkchen je App (Vorauswahl oben), Hinweis „Aktivierung:
   Mieter meldet sich mit seinem Microsoft-365-Konto an“. Die Optionen werden mit der gespeicherten Auswahl
   (Vorlagen, Automatisierung, Gerät) gespeichert und geladen – bestehendes Speicherformat erweitern, alte
   Auswahlen ohne Optionen = Vorauswahl.
2. Das Tool erzeugt je Auftrag eine `configuration.xml` (Funktion in `software.py`, gut testbar):
   `<Configuration><Add [SourcePath="…lokaler Ordner…"] OfficeClientEdition="64" Channel="Current">`
   `<Product ID="…"><Language ID="de-de"/>` + `<ExcludeApp ID="…"/>` für jede **nicht** gewählte App sowie immer
   `Lync`, `OutlookForWindows`, `Teams` `</Product></Add>` `<Updates Enabled="TRUE"/>`
   `<Display Level="None" AcceptEULA="TRUE"/>` `<Property Name="FORCEAPPSHUTDOWN" Value="TRUE"/>`
   `</Configuration>`. App-IDs: Word `Word`, Excel `Excel`, PowerPoint `PowerPoint`, Outlook klassisch `Outlook`,
   OneNote `OneNote`, OneDrive **`Groove`**, Access `Access`, Publisher `Publisher`.
   Quelle B: ohne `SourcePath`. Keine Schlüssel, kein `PIDKEY`, keine Aktivierungs-Eigenschaften.

## Teil C – Installation auf dem Gerät, Hilfe, Doku

1. Office-Eintrag geht wie andere Ordner-Einträge aufs Gerät (`ProgramData\Okula\Software\<Eintrag>`), die
   erzeugte XML daneben; das Software-Skript ruft `setup.exe /configure <xml>` und wertet den Rückgabewert wie bei
   anderen Installern aus (0 = ok). Grosse Datenmenge (mehrere GB): prüfen, ob Platzprüfung/Fortschritt/Zeitlimit
   (Software-Skript, `Kill` nach Zeitüberschreitung, B-028) passen – Zeitlimit für Office grosszügig (z. B. 60 min).
   **Windows-Direktinstallation:** prüfen, ob die Setup-Partition für die Office-Daten gross genug bemessen wird
   (`wininstall.layout`/Grösse aus der Software-Auswahl); wenn nicht, mitrechnen.
2. Quelle B ohne Internet am Gerät → FEHLER im Software-Protokoll mit Hinweis „Office lädt aus dem Internet – Gerät
   war offline“ (Rückgabewert von setup.exe), nicht still ok.
3. Hilfe (F1): Kapitel „Software installieren“ / „Die Software-Bibliothek“: Office herunterladen unter Windows
   (Schritte wie unten, PowerShell mit `.\setup.exe /download .\download.xml`, XML-Datei per PowerShell
   `Set-Content` schreiben, nicht mit Word/WordPad), Ordner laden, Optionen, Aktivierung durch den Mieter, Quelle B.
   Handbuch-Stil ohne Anrede.
4. Doku: `docs/TECHNIK.md` Abschnitt Office (Belege unten mit „abgerufen 26.11.2026“). Nur den eigenen Eintrag I-042
   in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum heute) – **Kurzübersicht und „Als
   Nächstes“ nicht anfassen**. `docs/TESTS.md` Abschnitt „I-042“ (Ordner laden → erkannt mit Version; VM: nur Word
   + Excel → nur diese im Startmenü, kein Teams/neues Outlook; Quelle B mit/ohne Internet; Direktinstallation mit
   Office).

## Belege (Microsoft Learn, abgerufen 26.11.2026)

- „Overview of the Office Deployment Tool“: ODT = `setup.exe` + Konfigurationsdatei; Modi `/download` (lädt
  Produkte/Sprachen in `SourcePath`, ein `Office`-Ordner entsteht) und `/configure` (installiert); fehlende Dateien
  werden beim erneuten Download ergänzt. Download Center ID 49117.
- „Configuration options for the Office Deployment Tool“: `ExcludeApp`-IDs `Access, Excel, Groove, Lync, OneDrive,
  OneNote, Outlook, OutlookForWindows, PowerPoint, Publisher, Teams, Word`; für OneDrive **`Groove`** verwenden;
  `OutlookForWindows` = neues Outlook. OneDrive wird sonst mit Word/Excel/PowerPoint automatisch installiert.
  Auf einem Gerät mit Office: gleiche Sprachliste → neue ExcludeApp-Liste ersetzt die alte (Nachinstallieren).
  Beispielwerte `OfficeClientEdition="64"`, `Channel`, `Display Level="None" AcceptEULA="TRUE"`, `Updates Enabled`.
- „Deploy Microsoft 365 Apps from the cloud“: Current Channel als Standard empfohlen.

## Grenzen und Prüfung

- Keine Lizenz-/Aktivierungslogik, kein Kauf-Office, kein Teams-Paket, keine Änderung an anderen Installer-Typen
  ausser dem Nötigen. `ui.py` nur Verdrahtung. Kein neuer Agent-Stick erwartet (sonst sagen).
- Tests (unittest): Erkennung (ODT-Ordner mit/ohne Data, fremde setup.exe nicht), XML-Erzeugung (Produkte, Apps,
  immer ausgeschlossene, Quelle A/B, XML gültig), Speichern/Laden der Optionen, Skript ruft `/configure`.
  Ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .`
- Rückmeldung: was geändert (Teil A/B/C), Commits, Testergebnis, Offenes, Unsicheres zu Office.
