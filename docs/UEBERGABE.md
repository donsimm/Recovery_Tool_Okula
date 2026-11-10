# Übergabe – 10.11.2026, ca. 10:35

Sitzung „Okuli“ (Projektleitung heisst jetzt **Okuli**). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` →
diese Datei → `docs/EINGANG.md` (leer) → `~/okuli/UEBERGABE.md` (Leitstand) → Dominik den Stand nennen.

## Stand

- **Neue Arbeitsweise (alles in `~/okuli/agenten/REGELN.md` und `PROJEKTLEITUNG.md`):** Okuli startet Agenten selbst mit
  `~/.claude/agenten/agent.sh` (run_in_background), Agenten laufen als Benutzer **`okuli-agent`** (kein sudo, kein
  Zugriff auf /home/dominik) in eigener Kopie auf Branch `agent/<ID>`; Ergebnis mit `~/.claude/agenten/holen.sh`,
  prüfen, `--ff-only`, pushen, `holen.sh … --aufraeumen`. **Okuli hat volles sudo** (`/etc/sudoers.d/okuli`).
  Agenten: Shell-Befehle einzeln (kein `&&`), keine Hintergrundprozesse; Server-/GUI-Prüfungen macht Okuli.
- **I-034 Projektübersicht** (0910836) abgenommen, installiert, am Server getestet (TESTS.md 12, 6 Punkte ✔).
- **Ä-037 VM-Disk beim Zurückspielen vergrössern + VM-Win11 256 GB** (55ed0dd) abgenommen, **von Okuli installiert**
  (`sudo ./install.sh`, Tool von Dominik neu gestartet), am Server getestet mit Probe-VM (TESTS.md 13, 5 Punkte ✔; 9: 2 ✔).
- **Neue Bugs:** B-007 🔴 (Ä-002 liest belegte Blöcke falsch → „Anpassen möglich“ bei 1-TB-Image), B-008 ⚪
  (Projektübersicht dunkel: Auswahlfelder unlesbar). Befund zu Ä-010: BIOS/MBR-Image ohne Warnung auf UEFI-VM.
- **VM-Win11 hat Dominik selbst gelöscht** (09:32). Am Server gibt es derzeit **keine VMs**.
- **Okuli-Cockpit** (eigenes Projekt `~/okuli-cockpit`, siehe `~/okuli/PROJEKTE.md`): läuft als Dienst, Link im LAN
  mit Schlüssel (`~/okuli-cockpit/link.sh`).
- **Kontext-Arbeitsgrenze 400k** (Dominik: nie Auto-Compact): Statuszeilen und Übergabe-Hinweis rechnen in % von 400k.

## Offen und als Nächstes

1. **B-007 starten, sobald das 5h-Limit zurückgesetzt ist (12:50; stand 97 %):** Prompt `docs/prompts/B-007-shrink-belegt.md`
   (freigegeben, Status B-007 „in Arbeit“), Auftragsdatei z. B.:
   `printf 'B-007 belegte Blöcke im partclone-Kopf\n\nLies docs/prompts/B-007-shrink-belegt.md und setze ihn um. Nicht pullen, nicht pushen, nur lokal committen. Shell-Befehle einzeln ausführen.\n' > <scratchpad>/b007.md`
   `~/.claude/agenten/agent.sh umsetzen ~/recovery_tool_okula <scratchpad>/b007.md - "Bash(python3 -m unittest:*),Bash(python3 -c:*)" opus medium B-007`
   Abnahme: Tests; echter Kopf `/mnt/okula-nas/Archiv/XX Test Images/2026-10-29_1133_nvme0n1/nvme0n1p4.ntfs.pcl.zst`
   (`zstd -dc … | head -c 200`, `shrink.parse_pcl_header`) muss ~397 GB belegt ergeben; dann `sudo ./install.sh`,
   Dominik Tool neu starten lassen, TESTS.md eintragen.
2. Tests, die Okuli noch selbst machen kann (Tool über AT-SPI, vorher bei Dominik fragen – er hat für 10.11. „bitte
   testen“ freigegeben): Abschnitt 11 (Snapshots), Rest von 12 und 13, Teile von 9/10. Hilfsskript:
   `/tmp/claude-1000/…/scratchpad/ui.py` ist weg nach Neustart – Muster: `gi.repository.Atspi`, App
   `ch.okula.RecoveryTool`, Knöpfe per `get_action_iface().do_action(0)`; Probe-VMs nur mit eigenem Namen, Netzwerk
   der VM bei fremden Images mit `virsh domif-setlink <vm> <mac> down --config` trennen.
3. Danach: Ä-007 (Bestätigung vor dem Löschen) brainstormen; die 4 roten Tests als Bug aufnehmen.
4. Dominik empfehlen: in `/config` „Auto-compact“ ausschalten (zusätzliche Sicherheit zur 400k-Grenze).

## Entscheide dieser Sitzung (alle in AENDERUNGEN.md bzw. PROJEKTLEITUNG.md / ~/okuli eingetragen: ja)

- Projektleitung heisst Okuli; Leitstand-Repo `~/okuli` (privat, github.com/donsimm/okuli).
- Okuli startet Agenten selbst; Agenten als `okuli-agent` ohne sudo; Okuli volles sudo und darf installieren.
- Tool-Tests: Okuli darf im laufenden Tool klicken, vorher fragen.
- Projektübersicht im Tool (Firefox, 127.0.0.1); Ä-037 so wie umgesetzt; Kontextgrenze 400k.

## Learnings

- Dominik will, dass Okuli selbst startet, installiert und testet – Fragen kurz, Empfehlung zuerst.
- `claude setup-token` braucht ein echtes Terminal (nicht `!`). Token liegt in `/home/okuli-agent/.claude-token`.
- Agenten mit `dontAsk` scheitern an verketteten Befehlen und Hintergrundprozessen → in der Rolle verboten.
- Laufende Bash-Skripte nie in place überschreiben (atomar ersetzen), sonst bricht ein laufender `agent.sh`.
- Firefox im Headless-Modus macht den Screenshot vor dem Nachladen → WebKit-Offscreen mit Wartezeit
  (`WEBKIT_DISABLE_COMPOSITING_MODE=1`); Firefox-Adresse aus `sessionstore-backups/recovery.jsonlz4` (mozlz4).
- 5h-Limit im Blick behalten (Cockpit „KI“): heute ~13 $ für 7 Agentenläufe, Limit bei 97 % um 10:30.
