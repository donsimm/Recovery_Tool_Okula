# Übergabe – 26.11.2026, ca. 14:30

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

## B-030 ist NICHT gelöst – nächster Schritt zuerst

Office-Ordner (USB `/media/dominik/FF5B-1D10/Office`, 19 Dateien, 3,7 GB, `stream.x64.x-none.dat` ~3 GB) laden
scheitert weiter: nach 10 Versuchen „Kopie fertig, aber das NAS lässt den Ordner nicht umbenennen“.
Befunde von Okuli (Probe-Ordner auf dem NAS, aufgeräumt):
- Eigenes Kopieren derselben Dateien (fsync, utime) und **sofortiges** Umbenennen → **ok**.
- Schrittweise wie `software.load`: nach Kopie ok, nach `scan` ok, **nach `_folder_info` (nur os.walk/lstat,
  einige Sekunden später) EACCES** – kleine Probe-Ordner nie betroffen, im eigenen Prozess keine offene Datei.
- Schluss: **zeitabhängig, NAS-seitig** – das Synology öffnet neue grosse Dateien kurz nach dem Schreiben
  (vermutlich Indexierung/Virenscan/Hash) und hält sie länger als 20 s offen. Messung der Sperrdauer lief um 14:30
  (Ergebnis siehe unten, falls nachgetragen).
- Lösungsideen für B-031 (Prompt noch nicht geschrieben): (a) **ohne Umbenennen** – direkt in den endgültigen Ordner
  kopieren mit Marker-Datei `.okula-loading`, `scan` ignoriert Einträge mit Marker, am Ende Marker löschen;
  (b) Erkennung vorab an der Quelle, Beschreibung während des Kopierens schreiben, sofort nach der letzten Datei
  umbenennen, Rückfall (a); (c) Wiederholung bis mehrere Minuten mit Anzeige „NAS prüft die Dateien …“.
  Empfehlung Okuli: (a), gilt auch für Images/Backups/ISOs (dort bisher kein Fehler, aber gleiche Ursache möglich).
  Auf dem Synology prüfen: Universal Search/Indexierung, Antivirus für den Ordner `NAS-BKP`.

## Als Nächstes

1. **B-030/B-031** wie oben lösen, dann Office laden lassen (Dominik wartet darauf).
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
- Fehler „nur beim Tool, nicht bei Probe“: Schritte der Funktion einzeln mit Probe-Ordner nachstellen – so wurde
  der Zeitfaktor bei B-030 sichtbar.
- Geräte sind **Okulas Mietgeräte**, nicht Kundengeräte (Gedächtnis `okula-mietgeraete`).
