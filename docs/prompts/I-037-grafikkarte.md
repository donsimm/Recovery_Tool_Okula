# I-037 – Grafikkarte im Inventar und im Gerätefenster

Status: umgesetzt (Commit c7e64b9) · erstellt 17.11.2026 von der Projektleitung · Freigabe: Dominik 17.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, den Eintrag I-037 in `docs/AENDERUNGEN.md`, in
`docs/TECHNIK.md` den Abschnitt zum Inventar. Gearbeitet wird in der eigenen Kopie, in der der Agent gestartet wurde
(lokaler Branch `agent/I-037`); nicht pullen, nicht pushen.

## Ziel

Das Inventar eines Geräts enthält seine Grafikkarten (Hersteller, Modell), und das Gerätefenster zeigt sie in der
*Übersicht*. Anlass: Für den Master des CompactPlayers (NVIDIA GeForce GT 740, braucht den passenden Treiber) liess
sich die Grafikkarte nur über ein altes Clonezilla-Image (`Info-lspci.txt`) herausfinden.

## Entscheide aus dem Brainstorming

- Auf 🟡 hochgestuft und freigegeben (Dominik 17.11.).
- Nur anzeigen – keine Treiber-Automatik, keine Regeln/Warnungen in diesem Auftrag.

## Anforderungen

1. **Agent (`inventory.py`)**: neue Funktion `gpus()` → Liste je Grafikgerät (PCI-Klasse `0x03xxxx`: VGA, 3D,
   Display) mit mindestens: PCI-Adresse, Hersteller-ID und Geräte-ID (`vendor`, `device`, hex), Hersteller- und
   Modellname, Subsystem (Hersteller des Geräts/der Karte, falls verfügbar), Kernel-Treiber (falls gebunden).
   - Namen bevorzugt über `lspci -mm -nn -D` (bzw. `-vmm`); fehlt `lspci`, aus `/sys/bus/pci/devices/*/{class,vendor,
     device,subsystem_vendor,subsystem_device}` und, falls vorhanden, der `pci.ids`-Datenbank
     (`/usr/share/misc/pci.ids` bzw. `/usr/share/hwdata/pci.ids`); ohne Datenbank nur die IDs.
   - Fehlende Werkzeuge = weniger Angaben, kein Fehler (wie die übrigen Inventar-Funktionen).
   - In `collect()` als Schlüssel `"gpus"` aufnehmen; ältere Inventare ohne den Schlüssel bleiben gültig.
2. **Agent-Stick**: `pciutils` (und, falls nicht automatisch dabei, die `pci.ids`-Datenbank) in die Paketliste
   (`stick.py`) bzw. Netzwerkstart aufnehmen, falls noch nicht enthalten. Grösse des Sticks im Blick behalten.
3. **Gerätefenster → Übersicht**: Zeile(n) „Grafikkarte“ (bei mehreren „Grafikkarte 1“, „Grafikkarte 2“), Text z. B.
   „NVIDIA GeForce GT 740 (GK107)“; Hersteller-Kurzname (NVIDIA, AMD, Intel) statt langer Firmennamen, wo eindeutig.
   Ohne Angabe (altes Inventar) → keine Zeile bzw. „–“ wie bei den anderen Feldern.
   **Mehrere Karten** (Video-Server mit 2–4 GPUs plus Onboard-Grafik): jede Karte einzeln, auch gleiche Modelle;
   Reihenfolge nach PCI-Adresse, die PCI-Adresse (z. B. `0000:03:00.0`) mit anzeigen (Tooltip oder in Klammern),
   damit gleiche Karten unterscheidbar sind. Mitgezählte Zusatzfunktionen derselben Karte (z. B. HDMI-Audio, Klasse
   `0x04`) gehören **nicht** dazu – nur Klasse `0x03`.
4. **Demo-Gerät**: Beispiel-Grafikkarte im Demo-Inventar (`demo_agent.py`).
5. **Digitaler Zwilling** (VM-Profil aus dem Inventar): Grafikkarte nur als Information übernehmen (z. B. in der
   Beschreibung), **nicht** nachbilden; nichts an der VM-Hardware ändern.
6. Tests: `gpus()` mit Beispielausgaben von `lspci` (Intel + NVIDIA, nur Intel, keine, Video-Server mit zwei
   gleichen NVIDIA-Karten + Onboard-Grafik + HDMI-Audio-Funktionen) und mit nachgebautem
   `/sys`-Baum ohne `lspci` (mit und ohne `pci.ids`), Anzeige in der Übersicht (Formatierung, mehrere Karten,
   altes Inventar), Demo-Inventar.

## Nicht Teil dieses Auftrags

- Treiber-Empfehlungen, Warnungen, Spalte in der Geräteliste, Filter.
- Grafikspeicher (VRAM) – nur falls ohne Aufwand zuverlässig (sonst weglassen und in der Abschlussmeldung nennen).
- Weitere Hardware (Audio, USB-Geräte).

## Hinweise zum Code

- `okula_recovery/inventory.py` (`collect`, Muster: `batteries()`, `network()`), `okula_recovery/device_window.py`
  (Übersicht um Zeile 425), `okula_recovery/demo_agent.py`, `okula_recovery/stick.py` (Paketliste), VM-Profil
  (`vm*.py`, Profil aus dem Inventar).
- Agent betroffen (neuer Agent-Stick nötig)? **ja**.
- Reihenfolge: zuerst Agent (Inventar, Paketliste), dann Anzeige.

## Oberfläche und Texte

- Bezeichnung in der Übersicht: **„Grafikkarte“**. Schreibstil laut `CLAUDE.md`.
- Hilfe (F1): im Kapitel zum Gerätefenster/Übersicht die neue Angabe erwähnen.

## Abnahmekriterien

- [ ] Inventar enthält `gpus` mit Hersteller/Modell bzw. IDs; ohne `lspci` und ohne Datenbank kein Fehler
- [ ] Übersicht zeigt die Grafikkarte(n); altes Inventar ohne `gpus` funktioniert
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; neue Tests wie oben
- [ ] Hilfe (F1) in `okula_recovery/help_window.py` angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md`: Eintrag ins „✅ Erledigt“-Protokoll, Kurzübersicht aktualisiert
- [ ] `docs/TESTS.md`: Abschnitt „Grafikkarte im Inventar (I-037)“ – CompactPlayer (NVIDIA GT 740), ein Laptop mit
      Intel-Grafik, VM; Inventar neu einlesen → Übersicht
- [ ] `docs/TECHNIK.md`: Inventar-Abschnitt ergänzt
- [ ] Demo-Gerät: Grafikkarte sichtbar

## Abschluss

1. Ein Commit (oder wenige) `I-037: Grafikkarte im Inventar`, **nur lokal** auf `agent/I-037` – **nicht pushen**.
   **Nur eigene Dateien committen** (`git add <Pfade>`, nie `git add -A`/`.`).
2. In dieser Datei oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Abschlussmeldung: Änderungen, Commits, Testergebnis, neuer Agent-Stick ja, Schritte für den Server, Grösse/Paket
   auf dem Stick, offene Punkte oder Abweichungen.
