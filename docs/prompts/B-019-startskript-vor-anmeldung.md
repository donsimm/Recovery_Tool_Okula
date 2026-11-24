# B-019 – Okula-Startskripte laufen parallel zur Anmeldung

Status: offen · erstellt 24.11.2026 von der Projektleitung · Freigabe: Dominik 24.11. (Gesamttest an der VM)

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge B-019, B-018, B-017, Ä-044, I-039, I-020 in
`docs/AENDERUNGEN.md`. Lokaler Branch `agent/B-019`; nicht pullen, nicht pushen. 1–3 Commits.

## Befund (Okuli, 24.11., VM-Win11-clean ab Snapshot „frisch“, Windows 11 Pro 25H2, über den Gastagenten)

„Windows anpassen“ (alle Optionen) und „Software installieren“ (virtio) zusammen gesendet. Beide Protokolle fehlerfrei
(71 ok, 0 Fehler; Software 1 ok). Aufräumen und Registry sauber (B-018 wirkt). Aber:

- Event-Log: Start 09:25:24. Gruppenrichtlinie „Scripts-Erweiterung abgeschlossen in 140 ms“ um 09:25:28 (Ereignis
  5016), gleichzeitig interaktive Anmeldung Okula-test (4624, Typ 2, Konto ohne Passwort). Das Okula-Skript beginnt
  erst um 09:25:43, **nach** der Anmeldung. Das Startskript läuft also asynchron. Microsoft Learn (Policy CSP
  ADMX_Logon/SyncForegroundPolicy): Auf Clients ist die Verarbeitung standardmässig nicht synchron.
- Folgen:
  - **Startmenü:** `start2.bin` wurde um 09:25:54 umbenannt. Die laufende Shell schrieb um 09:26:58 eine neue Datei
    mit dem alten Layout (WhatsApp, Adobe Express, LinkedIn …). Die Richtlinie wirkt deshalb nicht, auch nicht bei
    der nächsten Anmeldung.
  - **Widgets:** Das Wetter bleibt in der Taskleiste (Paket und Richtlinie erst nach Start von Explorer).
  - **Nachlauf:** Die Aufgabe „Okula Windows anpassen Nachlauf“ (Auslöser: Anmeldung + 30 min) wurde um 09:27
    angelegt, nach der Anmeldung. Sie hat keinen nächsten Lauf und läuft erst bei der nächsten Anmeldung.
  - **Sperrbildschirm** erschien noch (NoLockScreen = 1 gesetzt). Vermutlich gleiche Ursache, ungeprüft.
- Am 19.11. war das nicht sichtbar, weil dort nach dem Lauf neu angemeldet bzw. neu gestartet wurde.

## Anforderungen

1. **Startskripte vor der Anmeldung (Hauptlösung):** Beim Ablegen eines Okula-Startskripts (Windows anpassen,
   Software installieren, *Danach anpassen*) im Offline-Hive `SOFTWARE` die Richtlinie
   `Policies\Microsoft\Windows NT\CurrentVersion\Winlogon\SyncForegroundPolicy` = 1 (DWORD, „Always wait for the network
   at computer startup and logon“, Logon.admx) setzen. Vorher den Stand sichern (Wert fehlt / vorhandener Wert), so wie
   heute `gpt.ini`/`scripts.ini` mit `__AFTER__` gesichert werden.
   - Das letzte Startskript stellt den Stand in `Restore-OkulaStart` wieder her: entfernen oder alten Wert zurück.
   - Schreiben offline mit `hivexsh -w` (Paket `libhivex-bin` ist auf dem Agent-Stick, `stick.py`) oder einem
     gleichwertigen Weg. Hive sicher behandeln: Kopie, schreiben, prüfen, zurück; bei Fehler unverändert lassen und
     melden.
   - Belegen (Microsoft Learn), dass Startskripte damit vor der Anmeldung fertig laufen. Grenze `MaxGPOScriptWait`
     (Standard 600 s) beachten: Software läuft schon als geplante Aufgabe (I-020). Prüfen, ob „Windows anpassen“
     sicher darunter bleibt (Gesamtlauf heute ~90 s).
2. **Nachlauf robust:** Ist beim Anlegen der Aufgabe schon jemand angemeldet, zusätzlich einen einmaligen
   Zeit-Auslöser „jetzt + 30 min“ setzen, damit er trotzdem läuft.
3. **Startmenü robust:** Ist beim Umbenennen von `start2.bin` das Profil geladen (Benutzer angemeldet), protokollieren
   („Startmenü greift erst nach erneutem Lauf / Neustart“) und im Nachlauf **einmalig** nachholen, nur für diese Profile
   und nur, wenn der Benutzer dann nicht angemeldet ist. Sonst Hinweis. Einfache, belegbare Lösung wählen; wenn nicht
   sauber möglich, nur ehrlicher Hinweis im Protokoll.
4. **Agent-Stick:** Ändert sich Agent-Code (`deploy.py`), in der Abschlussmeldung „neuer Agent-Stick nötig“ angeben.
5. **Tests:** Hive-Änderung (Setzen, Sichern, Wiederherstellen; Fehler lässt Hive unverändert), Restore im Skript,
   Nachlauf-Auslöser bei angemeldetem Benutzer, Texte. Hilfe (F1) und `docs/TESTS.md` Abschnitt 26 „Korrektur B-019“:
   Anmeldung erst nach Ende des Skripts (Ereignis 5016 vs. 4624), Startmenü und Wetter ohne weiteren Neustart richtig,
   Nachlauf läuft nach 30 min, `SyncForegroundPolicy` danach wie vorher.

## Nicht Teil dieses Auftrags

- Ä-045 (Neustart-Knöpfe), I-042, neue Optionen.

## Abnahmekriterien

- [ ] SyncForegroundPolicy offline gesetzt und vom letzten Startskript wiederhergestellt
- [ ] Nachlauf läuft auch, wenn beim Anlegen schon jemand angemeldet ist
- [ ] Startmenü: geladenes Profil ehrlich gemeldet bzw. nachgeholt
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/TECHNIK.md`, `docs/TESTS.md`

## Abschluss

1. Commit(s) mit `B-019: …` im Titel, nur lokal auf deinem Branch; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis (oder: Tests nicht ausführbar), Quellen, neuer
   Agent-Stick ja/nein, offene Punkte.
