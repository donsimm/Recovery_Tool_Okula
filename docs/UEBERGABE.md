# Übergabe – 26.11.2026, ca. 15:00

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` → `~/okuli/UEBERGABE.md` → Dominik den Stand nennen.

## Stand (alles gepusht, Branch `claude/blissful-goldberg-mo3xda`, letzter Code-Commit 65bdd8d, Tests 987 OK)

Seit 25.11. umgesetzt und von Okuli abgenommen (Diff, Tests; Fenster-Tests mit `DISPLAY=:0`), **alles am realen
System ungeprüft** – Abschnitte in TESTS.md:
- B-027, B-028 (Review), **I-012 BitLocker** lesend entsperren (Root-Helfer `okula-bitlocker`).
- **Ä-050** Info-Feld Software-Bibliothek, **I-042 Office** (Bibliothekstyp, Apps einzeln, XML je Auftrag),
  **Ä-051** Ordner senden: Software wie Content, **Ä-053** „Alle“ ersetzt ganzen Ordner,
  **Ä-052 + B-029** USB-Vorgänge nicht modal + Liste „USB-Vorgänge“, Abbrechen erzwungen, Seriennummer-Prüfung,
  **B-030** `nas.rename_retry` (10 × 2 s).
- Server: `git pull && sudo ./install.sh` (Root-Helfer geändert), **neuer Agent-Stick + Netzwerkstart** (dislocker,
  einzelne Dateien senden). Dominik hat am 26.11. installiert (B-030-Meldung erschien).
- Ausserhalb des Tools: `~/Downloads/Office installieren.cmd` (Doppelklick, fordert Admin an, installiert Office
  aus dem Ordner daneben) – von Dominik noch nicht unter Windows getestet.

## B-030 – Ursache gefunden, Fix B-031 vorgeschlagen (Freigabe Dominik offen)

- Office-Ordner (USB `/media/dominik/FF5B-1D10/Office`, 3,7 GB) laden scheiterte trotz B-030 (10 × 2 s).
- **Ursache (von Okuli gemessen):** nach dem Durchsuchen des neuen Ordners hält der Linux-CIFS-Client einen
  Verzeichnis-Zugriff offen, bis `dir_cache_timeout` abläuft (`/sys/module/cifs/parameters/dir_cache_timeout` = 30).
  So lange verweigert das NAS das Umbenennen (EACCES). Echte Ladefunktion mit langer Wiederholung: **ok nach 35 s**.
  Das NAS (Synology) ist nicht schuld; erste Vermutung (Indexierung/Virenscan) war falsch.
- **Office ist geladen:** `Software-Bibliothek/office-16.0.20625.20142` (von Okuli über `software.load` mit
  längerer Wartezeit erzeugt) – Dominik soll im Tool prüfen, ob als „Office“ mit Version erkannt.
- **B-031 (Vorschlag, noch nicht freigegeben):** `nas.RENAME_ATTEMPTS`/`RENAME_PAUSE` auf bis zu ~90 s
  (z. B. 30 × 3 s), Anzeige „Ordner wird fertiggestellt …“, Test anpassen. Klein, opus medium. Alternative
  (nicht empfohlen): fstab-Option `nohandlecache` (bremst jeden NAS-Zugriff).

## Als Nächstes

1. **B-031** freigeben lassen und umsetzen (oben). Office ist schon geladen.
2. **I-044 Raspberry Pi** (Extras → „Raspberry Pi …“, Schritt 1 SD-Karte; Netzwerk = Schritt 2). Dominik 26.11.:
   Modelle 3B bis 5, Images speichern/wiederverwenden, Pi-OS-Abbilder bereitstellen, **beim Schreiben alle
   Anpassungen** (wie Raspberry Pi Imager). Okulis Zusammenfassung zur Bestätigung offen: Format nur belegte
   Bereiche + „Als .img exportieren“; Pi-OS-Abbilder in der OS-Bibliothek, Bereich „Raspberry Pi“.
   Fakten (raspberrypi.com, abgerufen 26.11.2026): Trixie-Images (ab 24.11.2025) = cloud-init auf der Boot-Partition
   (`user-data` mit `#cloud-config`: hostname, timezone, users/passwd-Hash, ssh_authorized_keys, `enable_ssh`,
   `ssh_pwauth`, `rpi:`-Optionen; `network-config` Netplan v2, `wifis`, `renderer: NetworkManager`,
   `regulatory-domain`; `meta-data`). Ältere: `ssh`-Datei, `userconf.txt` (`user:hash`, `openssl passwd -6`),
   firstrun.sh; `wpa_supplicant.conf` ab Bookworm wirkungslos. cloud-init nur beim ersten Start → gespeicherte
   Player-Images offline im ext4-rootfs anpassen. Pi 3B (ohne +) kein Netzwerkstart.
   Gross → mit vollem 5-h-Limit starten (Reset 17:50).
3. **I-043** Ordner einfärben. Kleines: Ausführungsrecht `packaging/okula-bitlocker`, BitLocker-Schlüssel beim
   Zusammenführen, `ui.py:135`/`ui.py:4202` (bei Ä-048).

## Learnings
- Limit: drei Agenten (B-030 $1.6, Ä-053 $1.7, Ä-052 $8.3) ≈ 64 %. Grosse Bauten nur mit frischem Limit.
- Parallele Agenten: Doku-Konflikte per Skript (beide Seiten behalten), danach Tabellenzeilen erledigter Einträge
  von Hand entfernen und Kurzübersicht zählen (`grep -c "^| B-"` je Abschnitt).
- Fenster-Tests laufen am Server mit `DISPLAY=:0 python3 -m unittest …` (Agenten können das nicht).
- Fehler „nur beim Tool, nicht bei Probe“: die echte Funktion mit gemessener Wiederholung laufen lassen statt raten –
  so wurde bei B-030 die 30-s-Sperre (CIFS `dir_cache_timeout`) sichtbar. Vermutungen erst nach Messung melden.
- Geräte sind **Okulas Mietgeräte**, nicht Kundengeräte (Gedächtnis `okula-mietgeraete`).
