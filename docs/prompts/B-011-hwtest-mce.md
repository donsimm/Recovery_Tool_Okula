# B-011 – Hardware-Test: Prozessor-Fehler seit dem Start melden

Status: freigegeben · erstellt 11.11.2026 von der Projektleitung · Freigabe: Dominik 11.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, den Eintrag B-011 in `docs/AENDERUNGEN.md` (und I-036 zur Einordnung),
`okula_recovery/hwtest.py`, `tests/test_hwtest.py` (falls vorhanden, sonst die Tests zum Hardware-Test suchen),
Kapitel „Hardware-Test“ in `okula_recovery/help_window.py`. Gearbeitet wird in der eigenen Kopie (lokaler Branch
`agent/B-011`); nicht pullen, nicht pushen. Shell-Befehle einzeln ausführen.

## Ziel

Der Hardware-Test („CPU unter Last“) meldet Machine-Check-Fehler (MCE) des Prozessors auch dann, wenn sie schon
vor dem Test im Kernel-Log stehen. Anlass: Videoserver SRV-002 zeigt am Bildschirm korrigierte Fehler von CPU 3
(Bank 0), der gründliche Test vom 10.11. meldete trotzdem „ok, mce 0“.

## Befund (Okuli, 11.11.)

`hwtest.cpu()` liest vor der Last `mce0 = _mce_lines()` und zählt danach nur Zeilen, die neu dazugekommen sind
(`hwtest.py` um Zeile 338 und 364). Fehler seit dem Start werden verworfen.

**Wichtiger:** Foto vom Bildschirm SRV-002 (11.11., Agent-Stick 0.2.0) zeigt die Meldungen **jede Sekunde**:
```
mce: [Hardware Error]: PROCESSOR 0:506e3 TIME 1794387393 SOCKET 0 APIC 6 microcode f0
mce: [Hardware Error]: CPU 3: Machine Check: 0 Bank 0: d400008000040150
mce: [Hardware Error]: TSC 0 ADDR 1ffff993a5650
```
Trotzdem ergab der gründliche Test (15 min Volllast) `mce: 0` neue Zeilen – die Erkennung selbst funktioniert auf
dem Stick also nicht. **Ursache zuerst klären** (Vermutungen, alle prüfen und mit Tests absichern):
- `journalctl -g` braucht PCRE2 (wird zur Laufzeit geladen); fehlt `libpcre2-8` im Live-System, liefert
  `journalctl` einen Fehler statt Zeilen – der Rückgabewert wird heute nicht geprüft, stdout leer → 0.
- Journal enthält die Kernel-Meldungen nicht (journald nicht aktiv/flüchtig) oder `-q` verschluckt den Fehler.
- Zeitlimit 30 s bei sehr vielen Zeilen.
Lösung robust machen: **ohne `-g`** lesen (`journalctl -k -b -o cat --no-pager` bzw. `dmesg`/`/dev/kmsg` als
Ersatz) und in Python filtern (Gross-/Kleinschreibung egal); Rückgabewert und Fehler prüfen; liefert keine Quelle
Daten, im Ergebnis „Hardware-Fehler nicht prüfbar“ als Detail vermerken statt stillschweigend 0.
Prüfen, ob `libpcre2-8` (bzw. das Paket für `journalctl -g`) in der Paketliste des Agent-Sticks fehlt
(`stick.py`/Bauskript) – wenn ja, im Abschluss melden; die Python-Filterung reicht als Lösung.

## Anforderungen

1. **Alle MCE-Meldungen seit dem Start** auswerten (`journalctl -k -b`, wie bisher; falls `journalctl` fehlt
   oder nichts liefert: `dmesg` als Ersatz, wenn verfügbar).
2. **Bewertung:**
   - neue Fehler während der Last → **fail** (rot), wie heute;
   - nur Fehler vor dem Test → **warn** (gelb). Kurztext z. B. „Hardware-Fehler seit dem Start gemeldet
     (CPU 3, Bank 0: 12 Mal) – BIOS-Update bzw. Prozessor prüfen“;
   - keine → wie heute (Temperatur/Drosselung entscheidet).
   Temperatur- und Drosselungsbewertung bleiben unverändert und kombinieren sich wie bisher (schlechtester Status gilt).
3. **Zusammenfassen:** Meldungen nach CPU und Bank gruppieren (aus Zeilen wie
   `mce: [Hardware Error]: CPU 3: Machine Check: 0 Bank 0: d000004000010005` bzw. `… Machine check events logged`;
   „corrected“/„uncorrected“ unterscheiden, wo erkennbar). Details: je Gruppe Anzahl, dazu höchstens 3 Beispielzeilen
   gekürzt. Zeilen ohne CPU/Bank (z. B. „Machine check events logged“) zählen als „ohne Zuordnung“.
   Ein Ereignis besteht aus mehreren Zeilen (PROCESSOR …, CPU n: Machine Check …, TSC … ADDR …) – gezählt wird die
   Zeile „CPU n: Machine Check: … Bank b: <status>“. Status-Bit 61 (UC) = 0 → „korrigiert“, 1 → „nicht korrigiert“
   (nicht korrigiert → immer rot). Die Zeilen oben aus dem Foto als Testdaten verwenden.
4. `values` des Ergebnisses: `mce` (neu während der Last, wie bisher), zusätzlich `mce_boot` (Anzahl seit Start)
   und `mce_groups` (Liste {cpu, bank, count, kind}). Bestehende Auswertungen (Protokoll-PDF, Verlauf, Anzeige
   im Gerätefenster) müssen weiter funktionieren und den gelben Zustand sinnvoll zeigen.
5. Auch der **Schnelltest** profitiert automatisch (gleiche Funktion).
6. **Demo-Agent** (`demo_agent.py`), falls er Hardware-Test-Ergebnisse liefert: unverändert lassen, ausser er
   bricht durch die neuen Felder.

## Nicht Teil dieses Auftrags

- I-036 (Hardware-Fehler ausserhalb des Tests im Gerätefenster/Liste anzeigen, `rasdaemon`) – nicht umsetzen.
- Keine Änderungen an anderen Testschritten.

## Hinweise zum Code

- Agent betroffen (neuer Agent-Stick nötig)? **ja** (`hwtest.py` läuft auf dem Stick).
- Parser als reine Funktion (Text → Gruppen) mit Unit-Tests; `_mce_lines` bleibt austauschbar für Tests.

## Oberfläche und Texte

- Schreibstil laut `CLAUDE.md` (ohne Anrede). Hilfe F1, Kapitel „Hardware prüfen (Hardware-Test)“: Satz zu
  „CPU unter Last“ ergänzen: gelb, wenn seit dem Start des Geräts Hardware-Fehler gemeldet wurden; rot, wenn
  während der Last neue dazukommen.

## Abnahmekriterien

- [ ] Fehler nur vor dem Test → gelb mit Gruppierung; neue während der Last → rot; keine → unverändert
- [ ] Neue Tests (Parser mit echten Beispielzeilen, Bewertung vorher/während/keine, fehlendes journalctl);
      alle Tests grün: `python3 -m unittest discover -s tests -t .`
- [ ] Hilfe (F1) angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: B-011 ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Abschnitt 15 ist schon eingetragen – bei Abweichungen anpassen
- [ ] `docs/TECHNIK.md`: Abschnitt Hardware-Test ergänzt

## Abschluss

1. Ein Commit `B-011: Hardware-Test meldet Prozessor-Fehler seit dem Start`, **nur lokal** auf `agent/B-011` –
   **nicht pushen**. **Nur eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen (eigener kleiner Commit danach ist ok).
3. Abschlussmeldung: was geändert wurde, Commits, Testergebnis, neuer Agent-Stick nötig (ja), Schritte für den
   Server, offene Punkte oder Abweichungen vom Prompt.
