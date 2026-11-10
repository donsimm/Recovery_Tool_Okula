# Übergabe – 06.11.2026, Nachmittag

Sitzung „projektleitung recovery tool“ (erste Projektleitungs-Sitzung). Nächste Sitzung: zuerst `CLAUDE.md`,
`docs/PROJEKTLEITUNG.md`, dann diese Datei, dann `docs/EINGANG.md` (heute leer) – und Dominik den Stand kurz nennen.

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
