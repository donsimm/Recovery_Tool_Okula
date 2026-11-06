# Übergabe – 06.11.2026, Nachmittag

Sitzung „projektleitung recovery tool“ (erste Projektleitungs-Sitzung). Nächste Sitzung: zuerst `CLAUDE.md`,
`docs/PROJEKTLEITUNG.md`, dann diese Datei, dann `docs/EINGANG.md` (heute leer) – und Dominik den Stand kurz nennen.

## Stand

- **Arbeitsweise eingerichtet:** Projektleitung (diese Rolle) brainstormt mit Dominik, schreibt Prompts nach
  `docs/prompts/VORLAGE.md`, Umsetzungs-Agenten setzen um, Projektleitung nimmt ab. Gearbeitet wird **lokal auf dem
  Server** (`~/recovery_tool_okula`, Hostname `Recovery-Tool-Server`), gepusht mit `gh` (Konto donsimm, Git-Name nur im
  Repo: Dominik Simmen). Repo heisst jetzt `github.com/donsimm/Recovery_Tool_Okula`.
- **Claude-Code-Einstellungen im Repo:** Statuszeile (3 Zeilen, `.claude/statusline.sh`) und Übergabe-Hook ab 80 %
  Kontext (`.claude/hooks/uebergabe-hinweis.sh`). In `~/.claude/settings.json`: Auto-Modus als Standard, eigene
  Statuszeile (wird vom Projekt überschrieben).
- **I-001 Virtuelle Maschinen – alle 4 Aufträge umgesetzt** (Konzept und Abweichungen: `docs/VM.md`):

  | Auftrag | Commit | Abnahme |
  |---|---|---|
  | 1 VM-Grundlage (Pakete, Brücke `br0`, `vm.py`) | 8d1e851 | ✔ inkl. Probe-VMs am Server |
  | 1b Nacharbeit (SPICE-Paket, Disk als Datei/AppArmor, e1000) | 2ecc04f | ✔ inkl. virt-viewer, Secure Boot Enabled |
  | 2 VMs im Tool (Ordner, Neue VM, Starten, Bildschirm, Hardware ändern) | 450dfa9 | ✔ |
  | 3 Digitaler Zwilling + Ä-036 leere Disk | 3e7182f | ✔ (Ablauf mit Image im Tool noch ungetestet) |
  | 4 Snapshots (externe qcow2-Overlays, „Vorher Snapshot“) | 2dadd10 | ✔ Code/Tests; Ablauf im Tool ungetestet |

- **Am Server installiert:** Stand bis Auftrag 2 (+ 1b). **Auftrag 3 und 4 noch nicht installiert.**
- **VMs am Server:** `VM-Win11` (ausgeschaltet; Windows 11 per „OS installieren …“ = Direktinstallation, taugt **nicht**
  als Master-Referenz). `VM-Klein` wurde am 06.11. um 13:20 **über das Tool gelöscht** (laut Geräteablage; vermutlich
  Dominiks Test „VM löschen“ – **bei Dominik bestätigen**).
- **Tests:** 455 Tests, immer dieselben **4 roten** (`test_imaging` ConsoleAndPowerTest.test_image_shows_progress_on_console,
  EndToEndTest.test_full_image, EndToEndTest.test_failure_leaves_no_partial; `test_jobs`
  ParallelJobsTest.test_two_disks_in_parallel_same_disk_refused) – auch auf dem unveränderten Stand vom Morgen.

## Offen und als Nächstes

1. **Dominik installiert Auftrag 3 + 4:** `cd ~/recovery_tool_okula && git pull && sudo ./install.sh`, Tool neu starten
   (kein neuer Agent-Stick).
2. **Tests am Server (Dominik will sie gesammelt später machen, meldet Ergebnisse im Chat; Projektleitung hakt in
   `docs/TESTS.md` ab):**
   - Abschnitt **8**: NAS/Geräte über `br0`, Server-Neustart (br0 gleiche IP), Netzwerkstart eines echten Geräts.
   - Abschnitt **9**: Disk-Image von VM-Win11, Bildschirm zweites Öffnen, Hardware ändern, Von ISO, Automatisierung, VM löschen.
   - Abschnitt **10**: Zwilling von **CompactPlayer 1** (hat ein Image auf dem NAS) mit Image einspielen.
   - Abschnitt **11**: Snapshots im Tool.
   - Abschnitt **3**: Master-Image mit VMs (Plan steht dort): VM-Win11 **neu von ISO**, Netzwerk der VM trennen,
     Ctrl+Shift+F3 → Audit-Modus, **Snapshot „vor Sysprep“**, Sysprep, nur „Einschalten und Agent starten“, Image,
     als Master markieren, auf zweite VM (`VM-Win11-B`) mit „Danach anpassen“.
3. **Die 4 roten Tests** als Bug aufnehmen (Vorschlag der Projektleitung vom Morgen, noch **nicht eingetragen**) und
   per Agent klären lassen: Umgebung des Servers oder echter Fehler? Solange sie rot sind, fallen neue Fehler weniger auf.
4. **Nächstes Feature:** Vorschlag Ä-007 (Bestätigung vor dem Löschen bei der Automatisierung) – Brainstorming noch
   nicht begonnen. Reihenfolge-Vorschlag siehe Kurzübersicht in `AENDERUNGEN.md`.
5. Prompt `I-001-4-snapshots.md`: Status nach den Tests von „abgenommen“ bestätigen (Code ist abgenommen).

## Entscheide dieser Sitzung

Alle in `docs/AENDERUNGEN.md` „📌 Entscheidungen“ bzw. `docs/VM.md` eingetragen: ja.
- VMs im LAN (Brücke `br0`), Bildschirm eigenes Fenster, Windows „nicht aktiviert“, OEM-Key nie übernehmen.
- 3 Profile VM-Win11 / VM-Legacy (e1000 statt rtl8139) / VM-Klein; Zwilling: Identität abgewandelt (`VM-…`, UUID
  `0c1a…`, eigene MAC, Disk-Seriennummer), letztes Image einspielen (Standard an), Netzwerkkarte immer Intel.
- „Neue virtuelle Maschine …“ unter Extras + Rechtsklick; Hardware ändern in Auftrag 2; Ordner „Virtuelle Maschinen“ fest.
- Snapshots von Hand nur ausgeschaltet, „Vorher Snapshot“ Standard an, unbegrenzt mit Warnung < 50 GB.
- Startreihenfolge VMs: Disk → Netzwerk, Tool stellt nach Agent-Verbindung um (Agent-Abweichung; OVMF startet nach
  grub-`exit` nicht von der Disk).

## Learnings

- **Projektleitung ändert keinen App-Code** – auch nicht bei harmlos klingenden Wünschen („Fenster immer im Darkmode“
  wurde fälschlich in der App umgesetzt; Dominik: „ich möchte nicht das du was an der app änderst!!“). Steht in `CLAUDE.md`.
- **Agenten committen nur eigene Dateien** – ein Agent hat einen Prompt-Entwurf der Projektleitung mitcommittet. Steht
  in `VORLAGE.md` und in jedem Prompt.
- **Dominik will Empfehlungen statt Optionen**, kurze gesammelte Fragen (AskUserQuestion), Chat auf Deutsch; Tests
  lieber gesammelt später, Implementieren zuerst.
- **Abnahme selbst am Server prüfen lohnt sich:** Probe-VMs (anlegen/starten/`virsh screenshot`/löschen) fanden
  fehlendes SPICE-Paket und AppArmor-Sperre, bevor Dominik testete. Eigene Vermutungen dabei prüfen: „`<product>` bei
  SATA geht nicht“ war falsch, „rtl8139 ohne Windows-Treiber“ richtig.
- **Server-Eigenheiten:** `sudo` nur mit Passwort (Installation macht Dominik); Journal nicht lesbar (Benutzer nicht in
  `adm`) – Netzwerkstart-Protokoll über das Tool; `virsh -c qemu:///system` geht ohne sudo; `pkill -f <muster>` trifft
  die eigene Shell → `pgrep -x`/`kill` verwenden; Bildschirme der VMs mit `virsh screenshot` + GdkPixbuf → PNG ansehen.
- **Zwei Sitzungen im selben Ordner:** Während ein Agent arbeitet, nichts committen; Entwürfe erst nach seinem Push.
