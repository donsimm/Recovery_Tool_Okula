# Übergabe – 12.11.2026, ca. 12:00

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` → `~/okuli/UEBERGABE.md` (Leitstand: Sekretär, NAS, Projektor) → Dominik den Stand nennen.

## Stand

Alles committet und gepusht (zuletzt 9610b742). Keine Agenten laufen. Am Server installiert (Dominik 12.11.) bis inkl.
B-012; **I-038 noch nicht installiert** (`git pull && sudo ./install.sh`, Tool neu starten, kein neuer Agent-Stick).

- **B-012** (Windows-Konto „Benutzer“ = eingebaute Gruppe in deutschem Windows → OOBE-Schleife 0x80070563): abgenommen,
  Standard jetzt „Okula“, reservierte Namen werden im Dialog abgefangen. Befund aus den Panther-Logs des VM-Zwillings
  (Disk read-only mit `qemu-nbd --image-opts …locking=off` gelesen). Test TESTS.md 16 läuft gerade am CompactPlayer.
- **I-038** (Häkchen „Für Master-Image (Audit-Modus)“ in *OS installieren …*): abgenommen (549 Tests, Antwortdatei
  angesehen: nur `Reseal/Mode=Audit`, auditUser räumt Setup-Partition auf und löscht `Panther\unattend.xml`).
  Am Gerät/VM ungeprüft → TESTS.md 17.
- **Ä-039** neu 🟡 (Fehlerfall `install.cmd`: Laufwerksliste ins Protokoll, Hinweis „fährt nach Schliessen herunter“).
- **B-013** neu 🟡 (OEM-Schlüssel → SetupComplete.cmd läuft laut Microsoft nicht → Setup-Partition bleibt?) → TESTS.md 18.
- **VM-CompactPlayer-1** hart ausgeschaltet (Dominik 12.11.; hing in OOBE-Schleife, Windows darin kaputt).

## Offen und als Nächstes

1. **CompactPlayer 1:** Test B-012 (TESTS.md 16) – Ergebnis von Dominik abwarten. Zweiter Fehler „Windows-Partition :“
   (install.cmd findet Marker `okula-<id>.target` nicht, Versuch 09:15): falls er wieder kommt, Editor **offen lassen**,
   Shift+F10 → `diskpart` / `list volume` + `dir C:\ E:\ F:\ G:\` fotografieren lassen (Schliessen des Editors →
   `wpeutil shutdown`). Danach ggf. eigener Bug.
2. **Master-Image CompactPlayer** (Win10): Dominik will einen Master. Weg: I-038 installieren, am VM-Zwilling oder Gerät
   mit Häkchen Audit-Modus → einrichten → Sysprep → Disk-Image → Master (TESTS.md 17). Alternative ohne Tool:
   Microsoft-Stick bzw. VM „Von ISO“ + Ctrl+Shift+F3. Hinweis gegeben: Win10 ohne Support (nur ESU).
3. Tests gesammelt offen: 16, 17, 18, 15 Gegenprobe EliteBook, 1, 12, 5, 13, 14, 2, 3, 7, 9–11.
4. Hinweise des B-012-Agenten (nicht eingetragen, bei Bedarf als Ä): Kontoname = Computername wird nicht geprüft;
   Konto im Master-Ablauf/Automatisierung (`master_unattend`) wird nicht geprüft.
5. Danach laut Vorschlag: **I-005/I-006** brainstormen; klein: I-037, Ä-039.
6. **SRV-002:** CPU-Tausch – Entscheid Dominik weiter offen. Neuer Agent-Stick (Stand vor B-011) weiter offen.

## Entscheide dieser Sitzung (in AENDERUNGEN.md „📌 Entscheidungen“: nein – Umsetzungsdetails)

- B-012: Standardname „Okula“, reservierte Namen abfangen, nie still korrigieren (Dominik 12.11.).
- I-038: Master über Direktinstallation im Audit-Modus, kein Sysprep-Knopf (Dominik 12.11. „planen und umsetzen“).

## Learnings

- **install.cmd:** Schliessen des Editors mit `install.log` fährt das Gerät sofort herunter (`wpeutil shutdown`) – vorher
  Shift+F10 für eine zweite Eingabeaufforderung (→ Ä-039).
- **Direktinstallation ≠ Master:** Sie überspringt den OOBE-Bildschirm (kein Ctrl+Shift+F3); gilt auch für VMs. Für
  Master: I-038 oder Microsoft-Stick/„Von ISO“.
- **VM-Disk lesen ohne Eingriff:** `sudo modprobe nbd; sudo qemu-nbd -r -c /dev/nbd7 --image-opts
  "driver=qcow2,file.driver=file,file.filename=<snap>.qcow2,file.locking=off,backing.driver=qcow2,backing.file.driver=file,backing.file.filename=<basis>.qcow2,backing.file.locking=off"`,
  read-only mounten, danach `umount` + `qemu-nbd -d`. Windows-Protokolle: `Windows\Panther\UnattendGC\setuperr.log`.
- Windows in OOBE-Fehlerschleife reagiert nicht auf `virsh shutdown` → nur `virsh destroy` (mit OK von Dominik).
- Dominiks Bildschirmfotos im Chat können alt sein (Datei aus `~/Bilder/Bildschirmfotos`) – Datum im Bild prüfen.
- Agenten dürfen `py_compile` und `mkdir /tmp/…` nicht – Okuli kompiliert und testet bei der Abnahme selbst.
