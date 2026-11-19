# Ä-044 – Software installieren an einem Gerät mit Windows

Status: umgesetzt (Commit 4858192) · erstellt 19.11.2026 von der Projektleitung · Freigabe: Dominik 19.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge Ä-044, I-020, Ä-041 und I-039 in
`docs/AENDERUNGEN.md`, in `docs/TECHNIK.md` *Software installieren / Software-Bibliothek* und *Windows anpassen*.
Lokaler Branch `agent/AE-044`; nicht pullen, nicht pushen. 1–2 Commits.

## Ziel

Im Geräte-Menü (Liste und Gerätefenster) gibt es **„Software installieren …“**, gleich aufgebaut wie
**„Windows anpassen …“** (`ui.py`, `on_tweak_windows`): Gerät mit Agent und erkanntem Windows → Auswahl aus der
Software-Bibliothek → der Agent legt Installer und Startskript ab → Windows installiert beim nächsten Start ohne Klick,
Protokoll `C:\Windows\Temp\okula-software.log`. Gilt für echte Geräte und VMs.

## Befund

Heute lässt sich Software nur beim Aufsetzen mitgeben (*OS installieren*, *Danach anpassen* nach dem Zurückspielen,
Automatisierung). Der Unterbau ist vorhanden: `jobs.send_software` / `jobs.software_plan`, Agent-Befehl `software`
(`deploy.py`, `software()`), Skript `software.build_script`, Auswahl aus der Bibliothek (Ä-041). Anlass 19.11.:
virtio-Gasttools (I-041) in der Bibliothek, aber an VM-Win11-clean (Windows läuft schon) nicht installierbar.

## Anforderungen

1. **Menüeintrag** „Software installieren …“ neben „Windows anpassen …“, gleiche Bereitschaftsregeln (Agent verbunden,
   Windows erkannt, BitLocker → Meldung wie bei Windows anpassen).
2. **Auswahl:** vorhandene Auswahl aus der Bibliothek wiederverwenden (nur „bereit“ wählbar, „Parameter fehlt“ und
   „nur von Hand“ ausgegraut mit Grund, wie in *OS installieren*). Mehrfachauswahl, Reihenfolge wie dort.
3. **Ablauf:** wie *Danach anpassen* (Software ablegen + Startskript der lokalen Gruppenrichtlinie, I-020), aber auf ein
   bereits eingerichtetes Windows; Zusammenspiel mit einem gleichzeitig abgelegten „Windows anpassen“ (beide
   Startskripte, das letzte räumt auf – `RESTORE_START`) muss stimmen. Danach Neustart in Windows anbieten wie bei
   Windows anpassen (bzw. gleiches Verhalten übernehmen).
4. **Verlauf/Jobs:** Eintrag „Software installieren (VLC 3.0.24, …) – wird beim nächsten Start installiert“, Fortschritt
   im Jobs-Reiter wie bei den anderen Aufträgen.
5. **Hilfe (F1)**, Kapitel *Software installieren*: neuer Weg „an einem Gerät mit Windows“; TESTS.md-Abschnitt.
6. **Tests:** Menüeintrag/Bereitschaft (ohne GTK, wo möglich), Auftrag an `send_software` mit richtiger Disk und
   Auswahl, Skript enthält die Programme, Zusammenspiel mit Windows anpassen (beide Startskripte).

## Nicht Teil dieses Auftrags

- Neue Installer-Typen, Änderungen an der Bibliothek, Deinstallation.
- Agent ändern – voraussichtlich **kein neuer Agent-Stick** nötig (Befehl `software` gibt es); bestätigen.

## Abnahmekriterien

- [ ] „Software installieren …“ im Geräte-Menü, gleiche Bereitschaft wie Windows anpassen
- [ ] Auswahl nur aus der Bibliothek, nicht bereite Einträge ausgegraut
- [ ] Ablage und Startskript wie bei *Danach anpassen*; zusammen mit Windows anpassen korrekt
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md` (neuer Abschnitt, Test an
      VM-Win11-clean mit den virtio-Gasttools: danach `virsh qemu-agent-command VM-Win11-clean '{"execute":"guest-ping"}'`)

## Abschluss

1. Commit(s) mit `Ä-044: …` im Titel, nur lokal auf `agent/AE-044`; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis, neuer Agent-Stick ja/nein, offene Punkte.
