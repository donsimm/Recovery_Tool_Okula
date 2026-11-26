# B-031 – Umbenennen auf dem NAS: bis ~90 s warten (CIFS dir_cache_timeout)

Status: abgenommen (Okuli 26.11., Commit 48a6659) · erstellt 26.11.2026 von der Projektleitung · Freigabe: Dominik 26.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Einträge B-030 (Protokoll 26.11.) und B-031 in
`docs/AENDERUNGEN.md`, `docs/prompts/B-030-nas-umbenennen.md`. Lokaler Branch `agent/B-031`; nicht pullen,
nicht pushen. 1 Commit.

## Befund (von Okuli gemessen, 26.11.2026)

B-030 (`nas.rename_retry`, 10 × 2 s ≈ 18 s Wartezeit) reicht nicht: Nach dem Durchsuchen eines frisch kopierten
Ordners hält der Linux-CIFS-Client einen Verzeichnis-Zugriff offen, bis `dir_cache_timeout` abläuft
(`/sys/module/cifs/parameters/dir_cache_timeout` = 30 s). So lange verweigert das NAS das Umbenennen (EACCES).
Mit längerer Wiederholung klappte das Laden des Office-Ordners nach ~35 s. Das NAS (Synology) ist nicht schuld –
die Vermutung „Indexierung/Virenscan“ in der Fehlermeldung ist falsch.

## Anforderungen

1. `nas.RENAME_ATTEMPTS`/`RENAME_PAUSE` so, dass insgesamt bis ~90 s gewartet wird (z. B. 30 × 3 s). Optional:
   Wartezeit aus `dir_cache_timeout` ableiten (lesen, falls vorhanden; mindestens 3 × dieser Wert, Obergrenze
   ~120 s, Rückfall 90 s) – nur wenn einfach und getestet.
2. Anzeige „Ordner wird fertiggestellt …“ bleibt (einmal). Wenn sinnvoll ergänzen: „(bis 90 s)“ o. ä.
3. Fehlermeldung `rename_failed_message`: Hinweis auf Indexierung/Virenscan ersetzen durch einen zutreffenden,
   z. B. „… – nochmals versuchen; der Netzwerkzugriff des Servers hält den Ordner noch kurz offen“.
4. Tests in `tests/test_rename_retry.py` anpassen (Summe der Wartezeit, Meldungstext), kein echtes Warten.
5. Gilt automatisch für alle Aufrufer von B-030 (software, agentclient, backups, nasfiles, oslib, shrink) –
   prüfen, dass dort keine eigene kürzere Wartezeit übergeben wird.

## Nicht Teil dieses Auftrags

- `/etc/fstab` bzw. Mount-Optionen (`nohandlecache`) – bewusst nicht.
- Oberflächen-Dateien (`ui.py`, `help_window.py` usw.) nur falls zwingend; parallel arbeitet I-043 dort.

## Doku und Grenzen

- Nur den eigenen Eintrag B-031 in `docs/AENDERUNGEN.md` auf erledigt setzen und ins Protokoll (26.11.) –
  **Kurzübersicht und „Als Nächstes“ nicht anfassen**. `docs/TESTS.md`: im Abschnitt „B-030“ einen Satz zu B-031
  ergänzen (grosser Ordner laden darf bis ~90 s „Ordner wird fertiggestellt …“ zeigen).
- Kein neuer Agent-Stick.
- Tests ausführen genau so (ohne `cd`, ohne Pipe, ohne `2>&1`): `python3 -m unittest discover -s tests -t .`

## Abschluss

1. Ein Commit `B-031: …`, nur lokal, nur eigene Dateien (`git add <Pfade>`, nie `-A`).
2. Oben `Status: umgesetzt (Commit <hash>)` setzen.
3. Rückmeldung: was geändert, Commit, Testergebnis, Abweichungen.
