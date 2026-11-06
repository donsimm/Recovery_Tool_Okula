#!/usr/bin/env bash
# Hook UserPromptSubmit: ab 80 % Kontext einmal pro Sitzung eine Übergabe vorschlagen (nur Projektleitung,
# siehe docs/PROJEKTLEITUNG.md → „Übergabe an die nächste Sitzung“). Den Kontextstand legt
# .claude/statusline.sh je Sitzung in $d/<session_id>.ctx ab. Nur lesend bis auf die Marke „schon gemeldet“.
input=$(cat)
sid=$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null)
[[ "$sid" =~ ^[A-Za-z0-9_-]+$ ]] || exit 0
d="${XDG_RUNTIME_DIR:-/tmp}/okula-claude-$(id -u)"
f="$d/$sid.ctx"; mark="$d/$sid.uebergabe"
[ -f "$f" ] && [ ! -e "$mark" ] || exit 0
p=$(head -c 8 "$f"); p=${p%%.*}
[[ "$p" =~ ^[0-9]+$ ]] && (( p >= 80 )) || exit 0
touch "$mark"
jq -n --arg p "$p" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: (
  "Hinweis (Hook Übergabe): Der Kontext dieser Sitzung ist zu " + $p + " % belegt. Gilt nur für die Rolle " +
  "Projektleitung (docs/PROJEKTLEITUNG.md) – als Umsetzungs-Agent diesen Hinweis ignorieren. Zuerst die " +
  "aktuelle Nachricht beantworten, dann Dominik vorschlagen, jetzt die Übergabe nach docs/PROJEKTLEITUNG.md " +
  "→ „Übergabe an die nächste Sitzung“ in docs/UEBERGABE.md zu schreiben, zu committen und zu pushen und " +
  "danach eine neue Sitzung zu starten.")}}'
