# Übergabe – 25.11.2026, ca. 09:30

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` → `~/okuli/UEBERGABE.md` → Dominik den Stand nennen.

**Limit:** Dominik 25.11.: vorerst **keine Agenten starten** (5-Stunden-Limit). Agenten nur nach der Modell-Tabelle in
`~/okuli/agenten/REGELN.md` (sonnet/opus medium, high nur für Architektur/heikle Fehler), grosse Bauten allein.

## Stand (alles gepusht, Branch `claude/blissful-goldberg-mo3xda`, zuletzt a07af6d0)

Abgenommen 24./25.11. (Tests 850 OK, skipped 69):
- **B-018** Startmenü bestehender Konten, Registry-Reste – an der VM geprüft.
- **B-019** SyncForegroundPolicy – wirkungslos (Windows wartet nicht auf Startskripte), abgelöst durch B-020.
- **B-020** Startmenü/Widgets offline beim Senden (hivexsh), Mutex für gleichzeitige Startskripte – an der VM ab
  „frisch“ geprüft (Wetter weg, Protokolle ohne FEHLER, Nachlauf nach 30 min).
- **B-021** Sperrbildschirm offline (`NoLockScreen`), `DisableWindowsConsumerFeatures` offline, Agent-Uhr nach dem
  Server (`now` in jeder Anfrage, `agent.sync_clock`), ehrliche Hinweise zu Werbe-Platzhaltern. **An der VM
  ungeprüft:** Sperrbildschirm (Option beim Test nicht angehakt), Agent-Uhr.
- **Ä-045** Zwei Neustart-Knöpfe (BootNext im Agent) – an der VM geprüft (Dominik: „Knöpfe haben funktioniert“).
  Offen: Abschluss „Neustart“ der Automatisierung noch alt (bewusst wegen Ä-046), echtes Gerät mit Stick.
- **Ä-046** Windows anpassen beim Aufsetzen (OS installieren, Danach anpassen, Automatisierung inkl. Vorlagen) – an der
  VM (Direktinstallation, Win11 Pro 25H2 26200.8037) geprüft: ein Durchgang, Software → Anpassen vor der ersten
  Anmeldung, kein Wetter, Nachlauf 09:05 ok. Zurückspielen/Automatisierung ungeprüft.
- **B-022** Startmenü-Liste auf neu installiertem Windows: Gruppenrichtlinie „Configure Start Pins“ wirkt dort nicht
  (KB5062660 „gradual rollout“). Lösung: **Bereitstellungspaket** `okula_recovery/assets/startpins/StartPins.ppkg`
  (+ `StartPins.ppkg.json` = `start_pins_json()`), von Okuli mit ICD (ADK in VM-Win11-clean, `C:\okuli`) erzeugt.
  Von Hand an der VM geprüft: `Install-ProvisioningPackage … -QuietInstall` → PolicyManager hat `ConfigureStartPins`,
  nach Ab-/Anmelden (start2.bin umbenannt) **genau die 9 Okula-Kacheln, ohne WhatsApp/Adobe Express/LinkedIn**.
  **Ungeprüft:** das Tool gibt das Paket selbst mit (Direktinstallation/Agent/Startskript). Ändert sich die
  Kachelliste, Paket neu erzeugen (Anleitung TECHNIK.md; ICD aus dem ADK-Ordner aufrufen, `/StoreFile:` relativ).

Dominik hat installiert und den Agent-Stick neu gemacht (Stand Ä-046; B-022 braucht keinen neuen Stick).

## Als Nächstes

1. **Letzter VM-Durchgang (ohne Agenten):** `git pull && sudo ./install.sh`, Tool neu starten. VM-Win11-clean:
   Direktinstallation mit virtio + Windows anpassen **Clean mit allen Häkchen** (inkl. Sperrbildschirm). Prüfen:
   kein Sperrbildschirm, Startmenü nur Okula-Kacheln (Paket vom Tool), kein Wetter, Protokoll einheitlich
   (Datum, Umlaute, Startmenü „ok“ statt Hinweis, wenn das Paket greift), Agent-Zeitstempel in Ortszeit.
   Optional: Zurückspielen mit *Danach anpassen*.
2. **Danach Aufräumen** (Dominik 25.11., „sinnvollen Stand finden“): Version taggen; Code-Review in Abschnitten
   (Lese-Agenten sonnet, z. B. `ui.py` > 3400 Zeilen); Doku entrümpeln (Zeile „Als Nächstes“ in AENDERUNGEN.md ist
   riesig, offene Tests in TESTS.md sichten); Okulis Regeln und Gedächtnis gemeinsam durchgehen; Ideen einsortieren
   (22 im Tool + ID-0003, S-0001, S-0002 im Cockpit/Sekretär).
3. Nach dem Aufräumen: Ä-045-Nacharbeit (Automatisierung), I-042 Microsoft 365 einzeln, B-013/B-004 an echten Geräten.

## Offen / Beobachtungen
- **HP ZBook (Intel Core Ultra):** Agent-Stick „Selected boot image did not authenticate“ (Secure Boot). Empfehlung
  an Dominik: BIOS F10 → Security → Secure Boot Configuration → „Enable MS UEFI CA key“ = Yes → **hat geholfen**
  (Dominik 25.11.). Kandidat für die Hilfe (F1) / Vorabprüfung (Ä-010): Hinweis bei „did not authenticate“.
- Erster B-020-Lauf am 24.11. (snap-5) zeigte das alte Startmenü – mit B-022 erklärt (Gruppenrichtlinie nicht
  freigeschaltet).
- VM-Win11-clean läuft (Direktinstallation 25.11., Konto „Okula“, ADK installiert, Testdateien `start2.bin.okuli-*`).

## Learnings
- Windows wartet bei der Anmeldung nicht auf Startskripte – was vor der ersten Anmeldung wirken muss, offline setzen.
- „Configure Start Pins“ per Gruppenrichtlinie ist stufenweise freigeschaltet; das Bereitstellungspaket (Policy CSP)
  wirkt bei Pro ohne MDM. WMI-Bridge `MDM_Policy_Config01_Start02` hat dort kein `ConfigureStartPins`.
- Vor dem Start eines VM-Tests prüfen, ob die VM wirklich auf „frisch“ steht (neue Disk `snap-N`).
- Software still als SYSTEM aus dem Internet installieren blockiert die Claude-Code-Prüfung → Dominik installiert.
