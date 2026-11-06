#!/usr/bin/env bash
# Statuszeile für Claude Code (Projektvorgabe, siehe docs/PROJEKTLEITUNG.md): Kontext, 5 h, 7 Tage
export LC_NUMERIC=C
input=$(cat)
ctx=$(jq -r '.context_window.used_percentage // 0' <<<"$input")
s5=$(jq -r '.rate_limits.five_hour.used_percentage // 0' <<<"$input")
d7=$(jq -r '.rate_limits.seven_day.used_percentage // 0' <<<"$input")
bar=$(awk -v p="$ctx" 'BEGIN{f=int(p/10+.5);for(i=1;i<=10;i++)printf(i<=f?"█":"░")}')
printf '%s %.0f%% │ 5h %.0f%% 7d %.0f%%' "$bar" "$ctx" "$s5" "$d7"
