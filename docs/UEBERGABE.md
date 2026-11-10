# Übergabe – 10.11.2026, 14:40

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` (leer) → `~/okuli/UEBERGABE.md` (Leitstand) → Dominik den Stand nennen.

## Stand

Alles committet, gepusht und am Server installiert (letzter Commit dieser Übergabe). Am Server: keine VMs (alle
Probe-VMs gelöscht), Tool läuft mit Stand Ä-038.

- **B-007** (belegte Blöcke im partclone-Kopf, abf61f8) abgenommen, installiert, am Server getestet (Probe-VM 64 GB +
  1-TB-Image → „Anpassen: nicht möglich … 397.7 GB belegt“).
- **Ä-007** (Rückfrage beim Einschalten der Automatisierung, 1f5c409) abgenommen, installiert, getestet (Probe-VMs:
  Schalter im Reiter verbunden/nicht verbunden/unvollständig; Häkchen *Auto* von Dominik).
- **Ä-038** (Agent-Stick: Popup „fertig“, Prüfung am Schluss, Meldung beim Abziehen; ca975e5) abgenommen, installiert,
  getestet (Okuli: Stick-Bau mit Popup, Agent-Teil am Server geprüft; Dominik: Log, Start am Gerät).
- **B-010** erledigt: Videoserver SRV-002 (Supermicro X11SSV-Q, i5-6600T, BIOS 2.0/2016) startete nicht vom Stick –
  Stick war unvollständig (09:31 nach 24 s abgezogen, `okula-agent.squashfs` 0 Byte). Netzwerkstart klappte, Stick neu
  erstellt → ok. Nebenbefund: CPU 3 meldet laufend korrigierte MCE (Bank 0) → Dominik empfohlen: BIOS-Update.
- Neu aufgenommen: **B-009** ⚪ (4 Tests rot ohne `/usr/sbin` im PATH, 1 Test braucht root), **I-035** ⚪ (Hinweis,
  wenn VM-Disk grösser als freier Platz), **I-036** ⚪ (Hardware-Fehler MCE/WHEA im Tool anzeigen).
- **Okuli-Cockpit** (`~/okuli-cockpit`, a4debe0): veraltete Sitzung „Okuli“ verdrängte die aktive → behoben, Dienst neu
  gestartet. Cockpit-Repo hat **keinen GitHub-Remote** (nur lokal).

## Offen und als Nächstes

1. Tests am realen System, gesammelt (Dominik testet gern später):
   - Ä-007 (TESTS.md 5): „bestätigen → Countdown“, Rückfrage beim DEMO-PC
   - Ä-038 (TESTS.md 14): Stick während des Baus abziehen → rotes Popup; Restore-Stick fertig; Boot-Stick fertig;
     Knopf „Schliessen“ bei anderen Fehlermeldungen
   - Ä-037 (TESTS.md 13): „Beide Wege nicht möglich“, zu wenig Platz im Pool, Abbrechen bei 3/4, echtes Gerät
   - weiterhin offen: Abschnitte 2, 3, 5, 7, 9–11 laut TESTS.md
2. Nächstes Thema laut Vorschlag: **I-005/I-006** (Aufbewahrung, zweite Kopie) brainstormen; kleine Kandidaten:
   **B-009** (Tests mit vollem Pfad/sbin), **B-008** (Projektübersicht dunkel).
3. Offene Frage an Dominik: Cockpit-Repo auf GitHub sichern (Remote einrichten)?
4. Dominik empfehlen (noch nicht erledigt?): `/config` → Auto-compact aus.

## Entscheide dieser Sitzung (in AENDERUNGEN.md „📌 Entscheidungen“: ja)

- Ä-007 Variante B: Rückfrage bei jedem Einschalten von Hand; keine Rückfrage beim Wieder-Einschalten nach 3 Tagen und
  beim Stopp ■; kein Eintippen (Dominik 10.11.).
- Ä-038: Popup „Stick fertig – jetzt abziehen“ gewünscht (Dominik 10.11.), Umfang laut Prompt freigegeben.

## Learnings

- **Agent-Kurznamen ohne Umlaut:** Ä-IDs als `AE-0NN` (Branch `agent/AE-007`).
- **AT-SPI im Tool:** Während ein modaler Dialog (`dlg.run()`) offen ist, findet `Atspi` die App kurz nicht – 1–2 s
  warten und erneut suchen. Combo-Auswahl: Combo per `do_action(0)` öffnen, dann Menüeintrag `do_action(0)`
  (`Atspi.Selection` löst kein `changed` aus). Namensfeld: `Atspi.EditableText.set_text_contents`. Häkchen *Auto*
  (Zellen-Renderer) lässt sich nicht auslösen → Dominik klicken lassen. TextView-Log nicht lesbar.
  Hilfsskript lag im Scratchpad (`ui.py`, weg nach Neustart): `app()`, `walk`, `find(role,name)`, `click`, `menu`.
- Automatisierungs-Test braucht ein Gerät mit Inventar (Zieldisk) → Probe-VM einmal mit Agent starten, dann einrichten.
- Stick-Probleme zuerst am Server prüfen: `unsquashfs -s live/okula-agent.squashfs`, Kernel-Journal nach
  „USB disconnect“/„lost async page write“ zur Bauzeit; PXE-Journal zeigt, ob ein Gerät überhaupt per Netz startete.
- Geräte-Inventar liegt in `~/.local/share/okula-recovery/geraete/**.json` (auch Unterordner pro Gruppe).
