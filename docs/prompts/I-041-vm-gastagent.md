# I-041 – Test-VMs mit QEMU-Gastagent

Status: offen · erstellt 19.11.2026 von der Projektleitung · Freigabe: Dominik 19.11.

## Rolle und Einstieg

Du bist ein Umsetzungs-Agent für das Okula Recovery Tool. Chat auf Deutsch (Schweiz, „ss“).
Vor dem Start lesen: `CLAUDE.md`, `docs/PROJEKTLEITUNG.md`, Eintrag I-041 in `docs/AENDERUNGEN.md`, `docs/VM.md`
(Grundsätze, Profile, Snapshots), in `docs/TECHNIK.md` *Software installieren / Software-Bibliothek*.
Lokaler Branch `agent/I-041`; nicht pullen, nicht pushen. 1–2 Commits.

## Ziel

Die Projektleitung (Okuli, auf dem Server mit sudo) soll in einer Test-VM unter Windows selbst Befehle ausführen und
die Ausgabe lesen können – ohne Netzwerkzugang, ohne Passwort, ohne Bildschirm –, z. B.
`virsh qemu-agent-command <VM> '{"execute":"guest-exec","arguments":{"path":"powershell.exe","arg":[…],"capture-output":true}}'`.
Anlass: Der Test von „Windows anpassen“ (Ä-042/B-017) ging am 19.11. nur über Bildschirmfotos, `virsh send-key` und
das schreibgeschützte Einhängen der Disk.

## Rahmen

`vm.py` hält fest: **nur Standard-Hardware, keine virtio-Geräte** – ein Image aus der VM soll auf echten Geräten
laufen. Der Gastagent braucht einen virtio-serial-Kanal. Darum:

- Nur als **Option im VM-Profil**, Standard **aus**, Bezeichnung „Gastagent (nur Test-VMs)“, Tooltip mit dem Grund.
- Eingeschaltet: Controller `virtio-serial` + `<channel type='unix'><target type='virtio' name='org.qemu.guest_agent.0'/></channel>`
  (libvirt legt den Socket selbst an). Ausschalten entfernt beides. Profil ändern wie heute (VM aus); Snapshots,
  Zwilling (I-001 Auftrag 3), AppArmor-Regeln und Laufwerkskette dürfen nicht leiden – prüfen.
- **Gasttools in Windows:** kein eigener Download-Code. Weg über die Software-Bibliothek (Ä-041/I-020): Dominik lädt
  `virtio-win-guest-tools.exe` (bzw. `virtio-win-gt-x64.msi` + `qemu-ga-x86_64.msi`) in die Bibliothek; prüfen, dass die
  Erkennung (Ä-043) Typ und stille Parameter richtig setzt (Burn: `/install /quiet /norestart`, MSI: `/qn /norestart`),
  sonst Erkennung bzw. Vorbelegung ergänzen. In Hilfe und `docs/VM.md` beschreiben: Quelle (Fedora virtio-win, stabile
  Version), was installiert wird, wie man es wieder entfernt.
- **Schutz vor Verwechslung:** Wird aus einer VM mit Gastagent ein Master gemacht (Sysprep/Image-Erstellung), Hinweis
  „VM mit Gastagent – virtio-Treiber und qemu-ga sind im Image. Für Master-Images ohne Gastagent arbeiten.“ (Warnung,
  nicht sperren). Liste/Gerätefenster: kleines Kennzeichen „Gastagent“.
- Optional, wenn klein: Statuszeile im Gerätefenster „Gastagent: antwortet / keine Antwort“ (`guest-ping`, mit Timeout,
  nicht im GTK-Thread).

## Nicht Teil dieses Auftrags

- Befehle aus dem Tool heraus in der VM ausführen (Oberfläche dafür) – das macht die Projektleitung mit `virsh`.
- Automatische Anmeldung des Testkontos, OpenSSH/WinRM, echte Geräte.

## Hinweise zum Code

- `okula_recovery/vm.py` (Profil → XML, `memballoon model="none"` als Vorbild für Geräte ohne virtio), Profil-Dialog,
  `device_window.py`, Master-/Sysprep-Ablauf, `software.py`/`installerinfo.py` (Erkennung).
- Neuer Agent-Stick nötig? Voraussichtlich **nein** – bestätigen.

## Abnahmekriterien

- [ ] Option im Profil, Standard aus; XML mit/ohne Kanal korrekt (Tests auf dem erzeugten XML); Ein-/Ausschalten ändert nur das
- [ ] Snapshots, Zwilling, Start mit Overlay-Kette unverändert (Tests)
- [ ] Gasttools über die Bibliothek installierbar (Erkennung/Parameter belegt, Test mit Probe-Datei)
- [ ] Warnung beim Master aus einer VM mit Gastagent; Kennzeichen in Liste/Gerätefenster
- [ ] Alle Tests grün: `python3 -m unittest discover -s tests -t .`; Hilfe (F1) angepasst, `tests/test_help.py` grün
- [ ] `docs/AENDERUNGEN.md` (Protokoll, Kurzübersicht), `docs/VM.md`, `docs/TECHNIK.md`, `docs/TESTS.md` (neuer
      Abschnitt: Option einschalten, Gasttools installieren, `virsh qemu-agent-command <VM> '{"execute":"guest-ping"}'`
      antwortet, Option aus → Kanal weg)

## Abschluss

1. Commit(s) mit `I-041: …` im Titel, nur lokal auf `agent/I-041`; nur eigene Dateien committen.
2. Status oben auf `umgesetzt (Commit <hash>)`.
3. Kurze Abschlussmeldung: Änderungen, Commits, Testergebnis, Quellen (libvirt-/virtio-win-Doku; aus dem Gedächtnis →
   vermerken), neuer Agent-Stick ja/nein, offene Punkte.
