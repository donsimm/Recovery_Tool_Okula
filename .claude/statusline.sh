#!/usr/bin/env bash
# Statuszeile für Claude Code (Projektvorgabe, siehe docs/PROJEKTLEITUNG.md), drei Zeilen:
#   1. Verbrauch: Kontext, 5 h / 7 Tage mit Reset-Zeit, Kosten, Dauer, geänderte Zeilen
#   2. Sitzung:   Modell, Denkstufe, Thinking, Name, Version, Cache
#   3. Repo:      Branch, ungespeicherte Dateien, ↑ nicht gepusht / ↓ auf GitHub neuer (Stand letzter Pull),
#                 Projektstand aus docs/ (offene Bugs/Änderungen/Ideen, Notizen im Eingang, Prompts)
# Ohne Netzwerk, liest nur – ausser dem Kontextstand je Sitzung für den Übergabe-Hook
# (.claude/hooks/uebergabe-hinweis.sh). Läuft bei jeder Aktualisierung der Statuszeile.
export LC_NUMERIC=C
input=$(cat)

sid=$(jq -r '.session_id // empty' <<<"$input")
if [[ "$sid" =~ ^[A-Za-z0-9_-]+$ ]]; then
  sd="${XDG_RUNTIME_DIR:-/tmp}/okula-claude-$(id -u)"
  mkdir -p -m 700 "$sd" 2>/dev/null && jq -r '.context_window.used_percentage // 0' <<<"$input" > "$sd/$sid.ctx" 2>/dev/null
fi

IFS=$'\t' read -r ctx s5 s5r d7 d7r cost dur api add del model effort think sname ver warm hit dir < <(
  jq -r '[
    (.context_window.used_percentage // 0),
    (.rate_limits.five_hour.used_percentage // ""), (.rate_limits.five_hour.resets_at // ""),
    (.rate_limits.seven_day.used_percentage // ""), (.rate_limits.seven_day.resets_at // ""),
    (.cost.total_cost_usd // ""), (.cost.total_duration_ms // ""), (.cost.total_api_duration_ms // ""),
    (.cost.total_lines_added // 0), (.cost.total_lines_removed // 0),
    (.model.display_name // "?"), (.effort.level // ""), (.thinking.enabled // false),
    (.session_name // ""), (.version // ""),
    (.prompt_cache.warm | if . == null then "" else . end), (.prompt_cache.hit_ratio // ""),
    (.workspace.project_dir // .cwd // ".")
  ] | map(tostring | if . == "" then "-" else . end) | @tsv' <<<"$input")

R=$'\e[0m'; DIM=$'\e[2m'; YEL=$'\e[33m'; RED=$'\e[31m'
# Prozent einfärben: ab 70 % gelb, ab 90 % rot
pct() {
  [ "$1" = "-" ] && { printf '–'; return; }
  local p; p=$(printf '%.0f' "$1")
  if (( p >= 90 )); then printf '%s%d%%%s' "$RED" "$p" "$R"
  elif (( p >= 70 )); then printf '%s%d%%%s' "$YEL" "$p" "$R"
  else printf '%d%%' "$p"; fi
}
mins() {
  local m=$(( $(printf '%.0f' "$1") / 60000 ))
  if (( m >= 60 )); then printf '%d h %02d min' $((m / 60)) $((m % 60)); else printf '%d min' "$m"; fi
}

# Zeile 1 – Verbrauch
f=$(awk -v p="$ctx" 'BEGIN{print int(p/10+.5)}'); bar=""
for i in 1 2 3 4 5 6 7 8 9 10; do if (( i <= f )); then bar+="█"; else bar+="░"; fi; done
l1="$bar $(pct "$ctx")"
(( $(printf '%.0f' "$ctx") >= 80 )) && l1+=" ${YEL}📋 Übergabe fällig${R}"
l1+=" │ 5h $(pct "$s5")"
[ "$s5r" != "-" ] && l1+=" ${DIM}bis $(date -d "@$s5r" +%H:%M)${R}"
l1+=" · 7d $(pct "$d7")"
[ "$d7r" != "-" ] && l1+=" ${DIM}bis $(LC_TIME=de_CH.UTF-8 date -d "@$d7r" '+%a %H:%M')${R}"
[ "$cost" != "-" ] && l1+=" │ \$$(printf '%.2f' "$cost")"
if [ "$dur" != "-" ]; then
  l1+=" · $(mins "$dur")"
  [ "$api" != "-" ] && l1+=" ${DIM}($(mins "$api") Rechenzeit)${R}"
fi
l1+=" · +$add/−$del"

# Zeile 2 – Sitzung
l2="$model"
[ "$effort" != "-" ] && l2+=" · $effort"
[ "$think" = "true" ] && l2+=" · 🧠"
[ "$sname" != "-" ] && l2+=" │ $sname"
[ "$ver" != "-" ] && l2+=" │ v$ver"
if [ "$warm" = "true" ]; then
  l2+=" │ ♨ Cache warm"
  [ "$hit" != "-" ] && l2+=" $(awk -v h="$hit" 'BEGIN{printf "%.0f", h*100}')%"
elif [ "$warm" = "false" ]; then
  l2+=" │ ❄ Cache kalt"
fi

# Zeile 3 – Repo und Projektstand
g() { git --no-optional-locks -C "$dir" "$@" 2>/dev/null; }
l3=""
br=$(g branch --show-current)
if [ -n "$br" ]; then
  short=$(sed -E 's#^claude/##; s/-[a-z0-9]{6}$//' <<<"$br")
  l3="⎇ $short"
  n=$(g status --porcelain | wc -l); (( n > 0 )) && l3+=" ✎$n"
  if ab=$(g rev-list --left-right --count '@{u}...HEAD'); then
    read -r behind ahead <<<"$ab"
    (( ahead > 0 )) && l3+=" ↑$ahead"; (( behind > 0 )) && l3+=" ↓$behind"
  fi
fi
a="$dir/docs/AENDERUNGEN.md"
if [ -f "$a" ]; then
  cnt() { grep -E "^\| $1-[0-9]+ " "$a" | awk -F'|' '$4 ~ /offen|in Arbeit/' | wc -l; }
  l3+="${l3:+ │ }🐞$(cnt B) 🔧$(cnt Ä) 💡$(cnt I)"
fi
e="$dir/docs/EINGANG.md"
if [ -f "$e" ]; then
  ne=$(awk '/^## Neue Einträge/{s=1; next} s && /<!--/{c=1} s && !c && /^[-*] /{n++} c && /-->/{c=0} END{print n+0}' "$e")
  (( ne > 0 )) && l3+=" 📥$ne neu"
fi
st=$(grep -h '^Status:' "$dir"/docs/prompts/*.md 2>/dev/null | grep -v 'erstellt <')
if [ -n "$st" ]; then
  pe=$(grep -c '^Status: Entwurf' <<<"$st"); pf=$(grep -c '^Status: freigegeben' <<<"$st")
  pa=$(grep -c '^Status: in Arbeit' <<<"$st")
  (( pe > 0 )) && l3+=" 📝$pe Entwurf"
  (( pf > 0 )) && l3+=" ▶$pf freigegeben"
  (( pa > 0 )) && l3+=" ⚙$pa in Arbeit"
fi

printf '%s\n%s' "$l1" "$l2"
[ -n "$l3" ] && printf '\n%s' "$l3"
exit 0
