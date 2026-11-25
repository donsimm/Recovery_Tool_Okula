# I-012 – BitLocker entsperren (lesend, für das Backup der Benutzerdaten)

Status: Entwurf · erstellt 25.11.2026 von der Projektleitung · Entscheide Dominik 25.11. · Freigabe: –

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag I-012 und „📌 Entscheidungen“ (BitLocker, 25.11.)
in `docs/AENDERUNGEN.md`, Protokoll-Eintrag **B-025** (Abbruch bei BitLocker), `docs/AUTOMATISIERUNG.md`,
`docs/TECHNIK.md` (Datei-Backup, Agent-Stick). Lokaler Branch `agent/I-012`; nicht pullen, nicht pushen.
**Drei Commits:** Teil A (Agent), Teil B (Tool), Teil C (Stick, Hilfe, Doku). Nach jedem Teil alle Tests grün.

## Ziel

Mit dem **Wiederherstellungsschlüssel** (48 Ziffern) öffnet der Agent eine BitLocker-Partition **nur lesend** und
das Tool kann davon **Benutzerdaten sichern** – von Hand (Backup-Dialoge) und in der Automatisierung (heute Abbruch
nach B-025). Ohne Schlüssel bleibt alles wie heute.

## Entscheide (Dominik 25.11.) – verbindlich

1. **Umfang nur Lesen für Datei-Backups** (Benutzerdaten, Ordner/Partitionen-Backup, Durchsuchen). **Nicht**:
   Disk-Image aus belegten Blöcken (bleibt Rohkopie – sonst lägen Kundendaten unverschlüsselt auf dem NAS, kommt erst
   mit Ä-003), **nicht** Schreiben auf BitLocker (Software/Anpassen/Ordner senden/Datei-Restore bleiben gesperrt).
2. **Schlüssel:** Standard = beim Auftrag eingeben; Häkchen „Für dieses Gerät speichern“. Gespeichert nur root-lesbar
   unter `/etc/okula-recovery/bitlocker/` (Ordner 0700, Datei 0600 pro Gerät, atomar schreiben). **Nie** in
   Geräte-JSON, Inventar, Inventar-Export, Einstellungs-Export/-Übertragung, Logs, Verlauf oder späteres Webinterface.
   Im Gerätefenster nur „BitLocker-Schlüssel hinterlegt: ja/nein“ mit „Schlüssel hinterlegen …“ / „Entfernen“.
   Die Automatisierung kann nur mit gespeichertem Schlüssel sichern, sonst Abbruch wie heute (B-025-Meldung um
   „oder BitLocker-Schlüssel im Gerätefenster hinterlegen“ ergänzen).
3. **Immer nur lesend** entsperren (`dislocker -r`, NTFS mit `ro`); das Tool verändert eine BitLocker-Disk nie.
4. **Nur Wiederherstellungsschlüssel**, kein Benutzerpasswort.

## Teil A – Agent (`filebackup.py`, ggf. `inventory.py`, `agent.py`)

- Anfragen `profiles`, `browse`, `filebackup`/`backup` (bestehende Befehle) nehmen optional
  `bitlocker: {"<partition>": "<schlüssel>"}` entgegen. `Mounts` (lesend) öffnet eine BitLocker-Partition mit
  Schlüssel: `dislocker -r -V <dev> -p<schlüssel> -- <tmpdir>` (FUSE), dann `<tmpdir>/dislocker-file` per
  `ntfs-3g`/`mount` mit `ro,loop` (bestehende RO-Optionen wiederverwenden). Aufräumen in umgekehrter Reihenfolge
  (umount, `fusermount3 -u` bzw. umount des FUSE-Punkts), auch bei Fehlern.
- Der Schlüssel erscheint **nie** in Prozessliste-Logs, Fehlermeldungen oder dem Agent-Log (Meldungen von dislocker
  vor dem Weitergeben vom Schlüssel säubern). Format prüfen (8 Blöcke à 6 Ziffern, Bindestriche optional) vor dem
  Aufruf; falscher Schlüssel → klare Meldung „Wiederherstellungsschlüssel passt nicht zu <Partition>“.
- `profiles` ohne Schlüssel: wie heute (`error: "BitLocker – nicht lesbar"`), zusätzlich `bitlocker: true` im Eintrag,
  damit das Tool gezielt nach dem Schlüssel fragen kann. Mit passendem Schlüssel: Benutzer wie bei NTFS.
- Schreibende Wege (`Mounts(write=True)`, `deploy.py`) bleiben bei BitLocker gesperrt – Test dafür.
- Fehlt `dislocker` auf dem Stick (alter Stick): Meldung „Agent-Stick zu alt für BitLocker – neuen Stick erstellen“.

## Teil B – Tool

- Speicher-Modul (eigene kleine Datei, z. B. `bitlocker_keys.py`): lesen/schreiben/löschen pro Geräte-ID unter
  `/etc/okula-recovery/bitlocker/`, Rechte prüfen, nie in andere Exporte. Schlüssel normalisieren und validieren
  (48 Ziffern, Blockprüfung laut BitLocker: jeder 6er-Block durch 11 teilbar – mit Learn/Quelle belegen oder weglassen).
- Backup-Dialoge (`backup_dialogs.py`): Partition mit `bitlocker: true` → Hinweis und Feld „Wiederherstellungsschlüssel“
  (verdeckt, Einfügen erlaubt) + Häkchen „Für dieses Gerät speichern“; gespeicherter Schlüssel wird automatisch
  verwendet. Danach Profile neu abfragen.
- Automatisierung (`automation.py`): bei Backup „Benutzerdaten“ gespeicherten Schlüssel mitschicken; BitLocker ohne
  Schlüssel oder falscher Schlüssel → Abbruch wie B-025, nichts gelöscht.
- Gerätefenster (`device_window.py`): Zeile „BitLocker-Schlüssel hinterlegt: ja/nein“ + Knöpfe; nur sichtbar, wenn das
  Inventar eine BitLocker-Partition zeigt oder ein Schlüssel hinterlegt ist. Gerät löschen → Schlüssel mit löschen.
- `ui.py` nur, wo unvermeidbar (Verdrahtung); keine Umbauten.

## Teil C – Stick, Hilfe, Doku

- `dislocker` (Debian-Paket, hängt an `libdislocker0.7t64`, `libfuse3-4`, `libruby3.3`) in `stick.py`
  `BUNDLED_PACKAGES` bzw. die Paketliste des Live-Systems/Netzwerkstarts aufnehmen – bestehendes Muster prüfen und
  gleich behandeln; ebenso `fuse3`, falls nötig. **Neuer Agent-Stick und neues Netzwerkstart-Image nötig** –
  in Protokoll-Eintrag und TESTS.md sagen.
- Hilfe (F1): Kapitel Backup/Automatisierung/Gerätefenster anpassen (heute „BitLocker: nur 1:1“, „BitLocker ausschalten“
  – Texte ab ~Zeile 409, 489, 685, 1509 in `help_window.py` prüfen). Handbuch-Stil ohne Anrede.
- `docs/TECHNIK.md` Abschnitt BitLocker (Ablauf, Speicherort, Sicherheit), `docs/AUTOMATISIERUNG.md`.
- Nur den eigenen Eintrag I-012 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (Datum heute) –
  **Kurzübersicht und „Als Nächstes“ nicht anfassen** (macht Okuli). `docs/TESTS.md` Abschnitt „I-012“ (VM mit
  BitLocker: Backup Benutzerdaten von Hand mit Schlüssel; falscher Schlüssel; Automatisierung mit gespeichertem
  Schlüssel; Schlüsseldatei-Rechte; nichts in Export/Inventar).

## Tests

Agent-Seite mit gemocktem `subprocess` (dislocker/mount-Aufrufe, Aufräumen bei Fehler, Schlüssel nicht im Log, nur
`-r`), Schlüssel-Speicher (Rechte, atomar, Löschen, nicht im Export), Automatisierung (mit/ohne/falschem Schlüssel),
Hilfe-Tests grün. Ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`):
`python3 -m unittest discover -s tests -t .`

## Grenzen

- Kein Disk-Image-Umbau (`imaging.py` Rohkopie bleibt), kein Schreiben auf BitLocker, kein Benutzerpasswort.
- Keine Schlüssel in Testdaten, die echt aussehen könnten – offensichtliche Testwerte verwenden.
- Rückmeldung: was geändert (Teil A/B/C), Commits, Testergebnis, Offenes, ob neuer Stick/PXE-Image nötig.
