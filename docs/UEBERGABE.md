# Übergabe – 17.11.2026, ca. 14:15

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` → `~/okuli/UEBERGABE.md` → Dominik den Stand nennen.

## Stand

Abgenommen, zusammengeführt und gepusht (zuletzt 62c2a2d5 + Übergabe-Commit):
- **I-039** Windows anpassen … (Vorlagen Player/Laptop, automatische Anmeldung; Startskript der lokalen
  Gruppenrichtlinie) – Test 19 offen.
- **B-014** (mit Ä-039) Windows-Partition vor dem Formatieren an Anfang/Ende nullen, Prüfung nach dem Schreiben,
  `install.cmd` sucht auch „OKULAWIN“, Diagnose im Fehlerfall – Test 20 offen.
- **B-015** `install.cmd` setzt Windows Boot Manager an erste Stelle (AMI-Firmware des CompactPlayers legte „UEFI OS“
  für die Setup-Partition davor) – Test 20 offen.
- **I-037** Grafikkarte(n) im Inventar und in der Übersicht – Test 21: CompactPlayer ✔ (Dominik 17.11.), Rest offen.
- **Ä-040** CopyProfile + Taskleiste (`LayoutModification.xml`) beim Zurückspielen eines Masters, Häkchen
  „Einstellungen des Administrators übernehmen (Master)“ – Test 22 offen.
- Dominik hat am Server installiert und den neuen Agent-Stick (Stand bis I-037) erstellt; **Ä-040 noch nicht
  installiert** (nach I-020 alles zusammen: `git pull && sudo ./install.sh`, Tool neu starten, neuer Agent-Stick).

**Läuft:** Agent **I-020** (Software aus `Verteilen\Software` automatisch installieren; Prompt
`docs/prompts/I-020-software.md`, opus high, gestartet ca. 14:05, Branch `agent/I-020`, Basis 62c2a2d5).
Ergebnis: `~/.claude/agenten/auftraege.md` bzw. `holen.sh . I-020`.

**Master CompactPlayer (Win10 Pro 22H2):** am CompactPlayer 1 gebaut (Audit-Modus, Updates, `master-einrichten.ps1`:
Store-Apps/OneDrive weg, Windows Update aus, NVIDIA 474.82 Standard, VLC, Adobe Reader, Software + Test Files auf
Public Desktop) – Dominik: „hat funktioniert“; spielt ihn gerade auf eine VM. Skript und Installer:
NAS `Verteilen\Content\Installations Tools\`. Anordnung von Symbolen/Taskleiste ging verloren → Ä-040.

## Offen und als Nächstes

1. **I-020 abnehmen**: Agent-Branch basiert auf 62c2a2d5, main hat danach den Übergabe-Commit (nur
   `docs/UEBERGABE.md`) → vor `merge --ff-only` den Branch auf main rebasen (`git rebase claude/blissful-goldberg-mo3xda
   agent/I-020`), Tests, Diff (v. a. 10-Minuten-Grenze der Startskripte, Erkennung der Installer), pushen, aufräumen.
2. **B-016** (GRUB „font.pf2 not found“ beim Stick-Start, harmlos): in `AENDERUNGEN.md` eintragen (🐞, ⚪, Dominik
   17.11.), Prompt `docs/prompts/B-016-grub-font.md` (freigegeben, noch **nicht committet**) committen, Agent starten
   (Kurzname B-016, opus medium).
3. Danach Dominik: `git pull && sudo ./install.sh`, Tool neu starten, **neuer Agent-Stick** (Ä-040, I-020, B-016).
4. Tests am realen System offen: 16, 17, 18, 19, 20, 21 (Laptop/VM/Video-Server), 22, dazu ältere (1, 2, 3, 5, 7, 9–15).
5. Vorschlag danach: I-005/I-006 (Aufbewahrung, zweite Kopie); B-013 (OEM-Schlüssel) prüfen, sobald ein Gerät mit
   BIOS-Schlüssel da ist.

## Entscheide dieser Sitzung (in AENDERUNGEN.md „📌 Entscheidungen“: ja)

- I-039 Windows anpassen: eigene Funktion, Startskript beim nächsten Start, Vorlagen fest, autologon dabei; riskante
  TuningPack-Punkte bewusst nicht.
- Ä-040: Master-Einstellungen ohne Skripte, im Tool (viele Master geplant).
- I-020: Software-Ordner statt winget (feste Versionen, offline, Spezialsoftware; winget unter Win10 ohne Store kaum).
- B-015: Setup-Einträge der Firmware nicht automatisch entfernen (Agent-Entscheid, Begründung in TECHNIK.md).

## Learnings

- **Dominik hat wenig Zeit für Fehlersuche am Gerät** („eigentlich hab ich gar keine Zeit für so zeugs“): kürzester
  Weg zuerst (fertige Befehle), Diagnose nur wenn nötig; Fehlersuche lieber selbst an der VM.
- WinPE-Umgehungen B-014/B-015 (falls alter Stick): `format C: /fs:ntfs /q /y`, `echo Okula > C:\okula-<id>.target`
  (**.target nicht vergessen**), `D:\okula\install.cmd D`; Startreihenfolge: `bcdedit /set {fwbootmgr} displayorder
  {bootmgr} /addfirst`. Editor mit install.log nie schliessen (fährt herunter); cmd über Datei → Öffnen → cmd.exe.
- CompactPlayer: NVIDIA GT 740 (Kepler) → Standard-Treiber 474.82 (DCH braucht Store für die Systemsteuerung); Disk
  vorher MBR/Legacy, jetzt UEFI/GPT.
- Agenten-Kurznamen ohne Umlaut (`AE-040` für Ä-040), sonst lehnt `agent.sh` ab.
- Agent kann am 5-h-Limit abbrechen („Fehler: True“ im Protokoll) → mit Session-ID fortsetzen (`agent.sh … <session-id>`).
- Während ein Agent läuft, nichts committen (sonst kein `--ff-only`); Prompts vorher nur als Datei anlegen.
- Okuli-Starter: Dash-Symbol „Okuli“ (`~/.local/share/applications/okuli.desktop` → `~/.local/bin/okuli-start`,
  startet in `~/okuli` mit „sitzung lesen“); GNOME ohne Desktop-Icons-Erweiterung.
