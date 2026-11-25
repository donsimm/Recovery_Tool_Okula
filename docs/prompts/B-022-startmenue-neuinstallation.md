# B-022 – Startmenü-Liste wirkt auf neu installiertem Windows nicht

Status: offen · erstellt 25.11.2026 von der Projektleitung · Freigabe: Dominik 25.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge B-022, Ä-046, B-021, B-020, B-018, B-017, Ä-042
in `docs/AENDERUNGEN.md`, Abschnitte zu Startmenü/ConfigureStartPins in `docs/TECHNIK.md`. Lokaler Branch
`agent/B-022`; nicht pullen, nicht pushen. 1–3 Commits. Heikler Fehler: zuerst belegen, dann bauen.

## Befund (Okuli, 25.11., VM-Win11-clean, Direktinstallation mit Ä-046, Windows 11 Pro 25H2 Build 26200.8037)

- Vor dem ersten Start gesetzt (Setup-Umgebung, `reg load`): `HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer`
  `ConfigureStartPins` = 1 (DWORD), `ConfigureStartPinsJSON` = `%ProgramData%\Okula\StartPins.json` (REG_EXPAND_SZ);
  Datei vorhanden, ACL SYSTEM/Administratoren F, Benutzer RX, UTF-8 ohne BOM. `StartMenu.admx` kennt die Richtlinie.
- Gruppenrichtlinie (Computer) um 08:35:04 fertig, Anmeldung des neuen Kontos „Okula“ 08:35:17, Profil neu (kein
  `start2.bin` im Standardprofil). Startmenü: **Standard-Layout** (Outlook, Store, Xbox, Solitaire, WhatsApp …).
- Gegenproben: abmelden, `start2.bin` umbenennen, neu anmelden → wieder Standard-Layout; dasselbe mit JSON ohne
  `applyOnce` → Standard-Layout. Die Richtlinie wirkt auf dieser Installation **gar nicht**.
- Vorher (24.11., VM ab Snapshot „frisch“, gleiche Build-Linie 26200, länger in Betrieb) wirkte dieselbe Richtlinie
  (offline gesetzt) bei der ersten Anmeldung. Einmal (erster Lauf 24.11.) wirkte sie dort ebenfalls nicht – Ursache
  damals ungeklärt.
- WMI-Bridge: `root\cimv2\mdm\dmmap` `MDM_Policy_Config01_Start02` hat bei Pro ohne MDM-Anmeldung **keine**
  Eigenschaft `ConfigureStartPins` (nur `StartLayout` u. a.) – der heutige Weg „vor 24H2“ geht dort also auch nicht.
- Microsoft Learn („Configure the Start menu“): CSP lässt sich auch über **Bereitstellungspakete** (PPKG) setzen,
  „used at deployment time or for unmanaged devices“; GPO erst ab 24H2 mit KB5062660.

## Anforderungen

1. **Ursache belegen** (Microsoft Learn, Support-Artikel zu KB5062660 und Folge-Updates, Release-Notes): Ist die
   GPO-Variante von „Configure Start Pins“ stufenweise freigeschaltet (Controlled Feature Rollout), an eine
   Bedingung geknüpft (Update-Stand, Online-Konfiguration, Edition, Entra/AD) oder anders erklärbar? Klar trennen:
   belegt / plausibel / Vermutung.
2. **Weg wählen, der auf neu installiertem Windows 11 Pro sicher wirkt**, in dieser Reihenfolge prüfen und begründen:
   - Bereitstellungspaket (PPKG) mit `Policies/Start/ConfigureStartPins`: Lässt es sich ohne Windows Configuration
     Designer erzeugen (Format, Signatur nötig?) bzw. einmalig erzeugen und als Datei im Repo ablegen? Wie wird es
     angewendet (Setup: Ordner/Unattend `ProvisioningPackage`, laufendes System: `Install-ProvisioningPackage
     -QuietInstall`)? Wirkung bei Pro ohne MDM belegen.
   - Andere belegte Wege (z. B. `LayoutModification.json` im Standardprofil – Microsoft Learn OEM-Anpassung; Grenzen
     nennen: nur Zusatz-Pins?).
   - Wenn kein sicherer Weg: GPO weiter setzen (wirkt, wo freigeschaltet) und **ehrlicher Hinweis** in Protokoll,
     Tooltip und Hilfe („Startmenü-Liste greift auf frisch installierten Geräten evtl. nicht …“), kein „ok“ ohne
     Wirkung. Optional prüfen, ob sich die Wirkung am Gerät erkennen lässt (z. B. nach der Anmeldung im Nachlauf
     `start2.bin`/Startmenü auswerten) – nur wenn belegbar.
   - Gilt für alle Wege von *Windows anpassen*: Agent offline (B-020), Startskript, Direktinstallation (Ä-046).
3. **Schönheitsfehler Protokoll Direktinstallation** (`okula-windows-anpassen.log`):
   - Erste Zeile aus `install.cmd` hat das Format `25.11.2026  8:28:45,79` statt `2026-11-25 08:28:45` wie der Rest –
     angleichen (z. B. Zeit in cmd zerlegen oder die Zeile vom Skript beim ersten Start nachtragen).
   - Die Datei beginnt ohne BOM (von cmd angelegt) → Windows PowerShell 5.1 `Get-Content` und ältere Editoren zeigen
     Umlaute falsch („StartmenÃ¼“). Einheitlich lesbar machen (z. B. UTF-8 mit BOM beim ersten Schreiben durch das
     Skript, wenn die Datei nur ASCII enthält) – ohne vorhandene Zeilen zu verlieren.
4. **Tests:** gewählter Weg (Erzeugung/Ablage/Anwendung, nachgebildet), Hinweistexte, Protokoll-Format.
   Hilfe (F1), `docs/TESTS.md` Abschnitt „B-022“: Direktinstallation Win11 Pro → Startmenü bei der ersten Anmeldung mit
   festen Kacheln (bzw. ehrlicher Hinweis), Protokoll einheitlich und mit Umlauten lesbar.

## Nicht Teil dieses Auftrags

- I-042, Werbe-Platzhalter (B-021 – nur von Hand lösbar bei Pro).

## Abnahmekriterien

- [ ] Ursache mit Quellen (belegt / plausibel / Vermutung getrennt)
- [ ] Startmenü-Liste auf neu installiertem Pro: belegter Weg umgesetzt oder ehrlich gemeldet
- [ ] Protokoll Direktinstallation einheitlich, Umlaute lesbar
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md`

## Abschluss

1. Commit(s) mit `B-022: …` im Titel, nur lokal auf deinem Branch; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Ursache, Änderungen, Commits, Testergebnis (oder: Tests nicht ausführbar), Quellen, neuer
   Agent-Stick ja/nein, offene Punkte, was Okuli an der VM prüfen soll.
