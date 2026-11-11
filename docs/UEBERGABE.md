# Übergabe – 11.11.2026, 14:30

Sitzung „Okuli“ (Projektleitung). Nächste Sitzung: `CLAUDE.md` → `docs/PROJEKTLEITUNG.md` → diese Datei →
`docs/EINGANG.md` (leer) → `~/okuli/UEBERGABE.md` (Leitstand: Cockpit, Sekretär) → Dominik den Stand nennen.

## Stand

Alles committet und gepusht. Am Server installiert (Dominik 11.11.) bis inkl. B-011; Netzwerkstart neu eingerichtet
(Agent-Image 11.11. 09:34 mit neuem `hwtest.py`). Keine Agenten laufen.

- **B-009** (Tests ohne sbin im PATH, 3ef6bd7): abgenommen – 526 Tests grün mit und ohne sbin; neues Modul
  `systools.py` (auch auf dem Stick).
- **B-008** (Projektübersicht dunkel, 8d4d914): abgenommen; Prüfung „aufgeklappt“ in Firefox offen (TESTS.md 12).
- **B-011** (Hardware-Test meldet MCE seit dem Start, d6d39ff): abgenommen und **am Gerät bestätigt** – SRV-002 per
  Netzwerkstart, Schnelltest gelb „CPU 3, Bank 0: 37 Mal korrigiert“ (TESTS.md 15 ✔). PCRE2-Vermutung war falsch
  (journalctl/PCRE2 im Live-System vorhanden); Fehler kommen schubweise.
- **I-037** neu ⚪ (Grafikkarte im Inventar/Übersicht, aus Cockpit-Idee ID-0002).
- **EI-Werkstatt** (10.11. gefragt): nicht im Netz, nicht im Inventar – offen, ob es noch kommt.

## Offen und als Nächstes

1. **SRV-002:** CPU-Tausch empfohlen (i5-6600T/6500T, Sockel 1151; Microcode f0 ist der letzte) – Dominik entscheidet.
2. Tests am realen System (gesammelt): TESTS.md 15 Gegenprobe EliteBook (grün „keine seit dem Start“); 1 „Image
   erstellen/zurückspielen wie bisher“ (B-009 Agent-Code); 12 B-008 aufgeklappt; weiterhin 5, 13, 14 und 2, 3, 7, 9–11.
3. Nächstes Thema laut Vorschlag: **I-005/I-006** (Aufbewahrung, zweite Kopie) brainstormen; klein: I-037.
4. Neuer Agent-Stick (für Stick-Start statt Netzwerk) bei Gelegenheit – der alte Stick hat noch den Stand vor B-011.

## Entscheide dieser Sitzung (in AENDERUNGEN.md „📌 Entscheidungen“: nein – nur Umsetzungsdetails)

- B-008/B-009 per Agent ohne weiteres Brainstorming (Dominik 11.11.).
- B-011: Fehler vor dem Test gelb, während der Last oder nicht korrigiert rot (Prompt freigegeben 11.11.).

## Learnings

- **Gerät startet vom alten Stick statt per Netz**, wenn ein Stick steckt („Netzwerk zuerst“ aus): erkennbar daran,
  dass im Journal von `okula-pxe` nur DHCP mit Hostname `okula-…` erscheint, kein TFTP. Ergebnis im Inventar ohne
  neue Felder (z. B. `mce_boot`) = alter Agent. Vor Tests Stick abziehen.
- PXE-Image prüfen: `sudo unsquashfs -l /var/lib/okula-recovery/pxe/http/okula-agent.squashfs`; Inhalt mit
  `unsquashfs -d … <pfad>` lesen.
- Zwei Agenten parallel auf dem Recovery Tool → Konflikt nur in `AENDERUNGEN.md` (Kurzübersicht/Protokoll);
  zweiten Branch rebasen und Doku-Konflikt von Hand lösen, Zähler prüfen.
- Firefox headless (`--screenshot`) fotografiert vor dem `fetch` – für Seiten mit Daten eine Kopie mit kleinem
  `stub.js` (fetch → feste Daten) fotografieren.
- Agenten dürfen `node --check` nicht – JS nur gelesen; Okuli prüft Seiten per Foto.
