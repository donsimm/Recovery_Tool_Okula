# Ä-043 – Software-Bibliothek: alle gängigen Installer-Typen erkennen

Status: freigegeben · erstellt 18.11.2026 von der Projektleitung · Freigabe: Dominik 18.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, die Einträge Ä-043, Ä-041 und I-020 in
`docs/AENDERUNGEN.md`, in `docs/TECHNIK.md` den Abschnitt *Software installieren / Software-Bibliothek*.
Gearbeitet wird in der eigenen Kopie (lokaler Branch `agent/AE-043`); nicht pullen, nicht pushen.
1–2 Commits (Erkennung + Tests → Oberfläche/Hilfe/Doku).

## Ziel

Beim Laden in die Software-Bibliothek erkennt das Tool **möglichst jeden gängigen Installer-Typ** und trägt Name,
Version, Hersteller und die Parameter für die stille Installation selbst ein. Dominik weiss nicht, welche Software
noch kommt (Medientechnik: Luminex, Barco, Blackmagic, Resolume, Yamaha, Dante, OBS, Companion …) – die Erkennung soll
breit sein. Was nicht sicher erkannt wird, bleibt „Parameter fehlt“, aber mit einem hilfreichen Hinweis.

## Befund (18.11., Okuli)

`AraneoInstaller.exe` (Luminex Araneo 1.10.2) wurde nicht erkannt: **Qt Installer Framework 4.6.1** (Kennung „Built
with Qt Installer Framework 4.6.1“, eingebettete `Updates.xml` mit `<ApplicationName>`, `<ApplicationVersion>`,
`<Publisher>` in der Konfiguration, Komponenten mit `<Default>true</Default>`). Programmname wurde „AraneoInstaller“
statt „Araneo“, Version leer.

## Anforderungen

1. **Erkennung erweitern** (`okula_recovery/software.py`, `KINDS`, `detect_bytes`; ohne Ausführen der Datei, nur Lesen).
   Mindestens diese Typen, je mit Kennung, Parametern und Quelle (Herstellerdoku; aus dem Gedächtnis → im Code-Kommentar
   „Quelle nicht abgerufen“ vermerken):
   - bestehend prüfen/schärfen: MSI, NSIS, Inno Setup, InstallShield (MSI-basiert vs. **InstallScript** → braucht
     Antwortdatei → „Parameter fehlt“ mit Hinweis), WiX Burn, Squirrel („nur von Hand“)
   - **Qt Installer Framework** (≥ 4.0: `install --root "<Ziel>" --accept-licenses --accept-messages --default-answer
     --confirm-command`; Ziel aus `<TargetDir>` – `@ApplicationsDirX64@` → `C:\Program Files`; < 4.0 → „Parameter fehlt“
     mit Hinweis auf Steuerskript)
   - **Advanced Installer** (EXE-Bootstrapper: `/exenoui /qn /norestart` o. ä. – Doku prüfen)
   - **InstallAware**, **Wise Installation**, **Setup Factory**, **InstallBuilder (BitRock/VMware)**
     (`--mode unattended`), **Clickteam Install Creator**, **Smart Install Maker**, **Actual Installer**,
     **CreateInstall**, **Ghost Installer** – soweit Kennung und Parameter belegbar
   - **electron-builder (NSIS)**: zusätzlich `/allusers` (Installation für alle Benutzer, sonst nur für SYSTEM)
   - **Microsoft-Bootstrapper**: VC++ Redistributable, .NET-Runtime u. ä. (Burn: `/install /quiet /norestart`)
   - **IExpress**, **7-Zip-SFX**, **WinRAR-SFX**: als solche erkennen; wenn kein sicherer stiller Weg → „Parameter fehlt“
     mit Hinweis („selbstentpackendes Archiv – Inhalt prüfen“)
   - **MSIX/APPX/…bundle** (`.msix`, `.msixbundle`, `.appx`, `.appxbundle`): neue Art, Installation für alle Benutzer
     per `Add-AppxProvisionedPackage -Online -PackagePath … -SkipLicense` – im Installationsskript am Gerät (I-020)
     ergänzen; Laden in die Bibliothek erlauben
   - **MSU/MSP** (`.msu` → `wusa.exe … /quiet /norestart`, `.msp` → `msiexec /p … /qn /norestart`): neue Arten,
     Skript am Gerät ergänzen
   - Rückgabewerte je Typ sinnvoll vorbelegen (z. B. MSI 0/1641/3010, wusa 0/3010/2359302 = schon installiert)
2. **Angaben auslesen:** Name, Version, Hersteller aus der Versionsinfo der EXE (`VS_VERSIONINFO`: ProductName,
   ProductVersion/FileVersion, CompanyName), aus MSI (Tabelle `Property`: ProductName, ProductVersion, Manufacturer –
   ohne neue Abhängigkeit, z. B. eigener kleiner CFB-Leser, oder `msiinfo`/`msidump`, falls vorhanden, sonst
   Versionsinfo leer lassen), aus Qt-IFW-`Updates.xml`/`config.xml`. Hersteller als neues Feld `publisher` in der
   Beschreibung und als Spalte/Detail im Fenster. Programmname nicht „…Installer“/„…Setup“ übernehmen, wenn ein besserer
   Name gefunden wird.
3. **Erneut erkennen:** Im Fenster Software-Bibliothek Knopf bzw. Kontextmenü **„Neu erkennen“** für einen Eintrag
   (auch für bereits geladene, z. B. Araneo). Von Hand geänderte Angaben (`edited`) nur nach Rückfrage überschreiben.
4. **Hinweis bei „Parameter fehlt“:** erkannter Typ bzw. „unbekannt“ und was zu tun ist (Herstellerdoku, Test an der VM).
5. **Tests:** Probe-Dateien mit Kennungen für jeden Typ, Versionsinfo-Leser (konstruierte Ressource), MSI-Property-Leser
   (kleine Probe-MSI im Test erzeugen oder als Bytes), Qt-IFW-Probe mit `Updates.xml`/`TargetDir`, MSIX/MSU/MSP im
   erzeugten Installationsskript, „Neu erkennen“ respektiert `edited`.
   Echte Dateien zum Ausprobieren (nur lesen, nicht einchecken): `/mnt/okula-nas/Verteilen/Software/**` (z. B.
   `Araneo (network)/Araneo-1.10.2/AraneoInstaller.exe`, `Okula Monitor/OKULA-Monitor-Setup.exe`, `Companion/*`,
   `Barco Eventmaster Toolset/*`, `PandorasBox V10 (beta)/**`). Ergebnis je Datei in der Rückmeldung auflisten.

## Nicht Teil dieses Auftrags

- Ausführen von Installern, Antwortdateien aufzeichnen, Internet-Downloads, winget.
- Änderungen an *Ordner senden* oder am Ablauf (Startskript, geplante Aufgabe) ausser den neuen Arten MSIX/MSU/MSP.

## Hinweise zum Code

- `okula_recovery/software.py` (`KINDS`, `detect_bytes`, `detect`, Versionsinfo-Leser um Zeile 135, `_fresh_meta`,
  Installationsskript), `software_ui.py` (Fenster, Bearbeiten), `demostore.py`, `help_window.py`.
- Neue Arten im Skript am Gerät: dort, wo heute `msi` gesondert behandelt wird (um Zeile 1090).
- Agent betroffen (neuer Agent-Stick nötig)? Voraussichtlich **nein** – bestätigen.

## Oberfläche und Texte

- Spalte/Detail „Hersteller“; Typ-Namen ausgeschrieben („Qt Installer Framework“, „Advanced Installer“ …).
- Knopf/Kontextmenü „Neu erkennen“. Schreibstil laut `CLAUDE.md`.
- Hilfe (F1), Kapitel „Software installieren“: Liste der erkannten Typen mit Parametern, was bei „Parameter fehlt“ tun.

## Abnahmekriterien

- [ ] Araneo wird als Qt Installer Framework erkannt: Name „Araneo“, Version 1.10.2, Hersteller Luminex, Parameter wie oben
- [ ] Alle aufgeführten Typen erkannt (Tests) oder begründet als „Parameter fehlt“ mit Hinweis
- [ ] Name/Version/Hersteller aus EXE-Versionsinfo und MSI
- [ ] MSIX/MSU/MSP ladbar und im Skript am Gerät
- [ ] „Neu erkennen“ im Fenster, respektiert `edited`
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; Hilfe angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md` (Tabelle Typen/Parameter/Quellen),
      `docs/TESTS.md` (Abschnitt 25 ergänzen: Araneo und ein weiterer neuer Typ an der VM)

## Abschluss

1. 1–2 Commits mit `Ä-043: …` im Titel, **nur lokal** auf `agent/AE-043` – **nicht pushen**. Nur eigene Dateien committen.
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Commits, Testergebnis, Tabelle „Datei → erkannter Typ → Parameter“ für die echten
   Dateien auf dem NAS, neuer Agent-Stick ja/nein, offene Punkte, Quellen.
