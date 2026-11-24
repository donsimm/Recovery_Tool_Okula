# B-021 – Windows anpassen: Rest vor der ersten Anmeldung (Sperrbildschirm, Werbe-Platzhalter, Agent-Uhr)

Status: offen · erstellt 24.11.2026 von der Projektleitung · Freigabe: Dominik 24.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge B-021, B-020, B-018, B-017, Ä-042 in
`docs/AENDERUNGEN.md`, Prompt B-020. Lokaler Branch `agent/B-021`; nicht pullen, nicht pushen. 2–3 Commits.

## Befund (Okuli, 24.11., VM-Win11-clean ab „frisch“, Windows 11 Pro Build 26200, mit B-020)

- Offline-Teil von B-020 wirkt: Vor dem Start lagen `ConfigureStartPins`, `ConfigureStartPinsJSON`
  (`%ProgramData%\…`, REG_EXPAND_SZ – wird aufgelöst, geprüft), `AllowNewsAndInterests`, `StartPins.json`, Marke und
  umbenanntes `start2.bin` auf der Disk. Erste Anmeldung: Okula-Kacheln, kein Wetter, beide Protokolle ohne FEHLER.
- **Sperrbildschirm** erschien beim ersten Start noch (Dominik). `NoLockScreen` setzt heute nur das Startskript.
- **Werbe-Platzhalter:** Im Startmenü stehen zusätzlich zu den Kacheln aus `StartPins.json` **WhatsApp, Adobe Express,
  LinkedIn** (auch mit `applyOnce: true`, auch wenn die Richtlinie bei einer späteren Anmeldung nochmals greift).
  Die Option „Werbe-Apps (WhatsApp, LinkedIn, Spotify …)“ meldet „nicht vorhanden“ (es sind Platzhalter, keine
  installierten Pakete). Microsoft Learn (Customize the Windows 11 Start layout): Pins = Microsoft-Apps +
  „dynamically delivered apps“ + OEM. Edition Pro: `DisableWindowsConsumerFeatures` wirkt laut Protokoll nicht.
- **Agent-Uhr:** Zeitstempel des Agents 1 h vor (Umbenennung `start2.bin.okula-20261124-170748` um 16:07 Ortszeit;
  Windows-Dateizeiten stimmen). Vermutlich steht die RTC in Ortszeit (Windows), der Agent liest sie als UTC, oder die
  Zeitzone des Agents fehlt.

## Anforderungen

1. **Sperrbildschirm offline:** Bei gewählter Option `Personalization\NoLockScreen` = 1 (DWORD, Hive `SOFTWARE`,
   `Policies\Microsoft\Windows\Personalization`) im Offline-Teil von B-020 mitschreiben (`offline_request` /
   `tweak_offline`, gleicher Hive-Lauf). Wirkung bei Windows 11 Pro belegen (Microsoft Learn; ist der Wert bei Pro
   wirksam?). Wenn nicht wirksam: ehrlicher Hinweis im Protokoll/Hilfe statt „ok“.
2. **Weitere Werte prüfen:** Gehe die Optionen von *Windows anpassen* durch und nenne, welche weiteren reinen
   HKLM-Werte vor der ersten Anmeldung wirken müssen und sicher offline geschrieben werden können (z. B. Widgets,
   Copilot-Richtlinie, Cloud-Inhalte). Nur Maschinen-Werte (`SOFTWARE`), keine Benutzer-Hives. Kurz begründen; nur
   eindeutige Fälle umsetzen, den Rest in der Abschlussmeldung auflisten.
3. **Werbe-Platzhalter im Startmenü:** Herausfinden (Microsoft Learn, belegbar), woher WhatsApp/Adobe Express/LinkedIn
   kommen und wie sie bei Windows 11 Pro zuverlässig ausbleiben – bevorzugt offline vor der ersten Anmeldung
   (Maschinen-Richtlinie oder Standardprofil `Users\Default\NTUSER.DAT` für neue Konten; bestehende Profile im
   Startskript). Einfachste belegbare Lösung; falls keine sichere Lösung: ehrlicher Hinweis in Protokoll und Hilfe.
   Keine Registry-„Tricks“ ohne Quelle.
4. **Agent-Uhr:** Ursache finden (Agent-Stick/Netzwerkstart: Zeitzone, `hwclock`/RTC-Modus, NTP vom Server?) und so
   beheben, dass Zeitstempel des Agents (Umbenennung, Marke, Logs) Ortszeit Europe/Zurich zeigen. Windows-RTC
   (Ortszeit) nicht verändern.
5. **Tests:** Offline-Wert Sperrbildschirm (hivexsh nachgebildet wie `tests/test_offline_tweak.py`), ggf. weitere
   Werte, Platzhalter-Lösung, Zeitstempel/Zeitzone. Hilfe (F1), `docs/TESTS.md` Abschnitt 26 „Korrektur B-021“:
   kein Sperrbildschirm beim ersten Start, Startmenü ohne WhatsApp/Adobe Express/LinkedIn, Zeitstempel in Ortszeit.

## Nicht Teil dieses Auftrags

- Ä-046 (Windows anpassen beim Aufsetzen), Ä-045, I-042.

## Abnahmekriterien

- [ ] Sperrbildschirm offline gesetzt (mit Beleg zur Wirkung bei Pro)
- [ ] Werbe-Platzhalter mit belegtem Weg entfernt oder ehrlich gemeldet
- [ ] Agent-Zeitstempel in Ortszeit
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md`

## Abschluss

1. Commit(s) mit `B-021: …` im Titel, nur lokal auf deinem Branch; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis (oder: Tests nicht ausführbar), Quellen, neuer
   Agent-Stick ja/nein, offene Punkte (inkl. Liste aus Anforderung 2).
