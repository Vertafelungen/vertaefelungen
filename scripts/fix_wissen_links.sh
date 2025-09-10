#!/usr/bin/env bash
# fix_wissen_links.sh
# Version: 2025-09-09 15:10 (Europe/Berlin)
# Zweck: Ersetzt Links, die mit /wissen/ beginnen, aber kein Sprachpräfix haben,
#        in den Quell-Dateien (de/, en/). Unterstützt HTML-Attribute (href/src)
#        mit/ohne Anführungszeichen sowie Markdown-Links [..](/wissen/...).

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

fix_lang() {
  local L="$1"          # de | en
  local DIR="$L"
  [ -d "$DIR" ] || return 0

  echo "🔧 Normalisiere /wissen/ → /wissen/${L}/ in ${DIR}/"

  # 1) HTML-Attribute mit Anführungszeichen (href|src = ' oder ")
  find "$DIR" -type f \( -name '*.md' -o -name '*.markdown' -o -name '*.html' -o -name '*.htm' \) -print0 \
    | xargs -0 -r perl -0777 -i -pe 's/\b(href|src)\s*=\s*(["'\'"'])\/wissen\/(?!de\/|en\/)/$1=$2\/wissen\/'"$L"'\//gi'

  # 2) HTML-Attribute ohne Anführungszeichen → wir fügen doppelte Quotes hinzu
  find "$DIR" -type f \( -name '*.md' -o -name '*.markdown' -o -name '*.html' -o -name '*.htm' \) -print0 \
    | xargs -0 -r perl -0777 -i -pe 's/\b(href|src)\s*=\s*\/wissen\/(?!de\/|en\/)/$1="\/wissen\/'"$L"'\/"/gi'

  # 3) Markdown-Links: [Text](/wissen/…)
  find "$DIR" -type f \( -name '*.md' -o -name '*.markdown' \) -print0 \
    | xargs -0 -r perl -0777 -i -pe 's/\]\(\s*\/wissen\/(?!de\/|en\/)/](\/wissen\/'"$L"'\/)/gi'
}

echo "➡️  Trockentest (nur anzeigen), wo noch /wissen/ ohne Präfix vorkommt:"
grep -RIn --color=never -E '\b(href|src)\s*=\s*["'"'"']?\/wissen\/(?!de\/|en\/)|\]\(\s*\/wissen\/(?!de\/|en\/)' de en || true
echo

read -r -p "Fortfahren und ersetzen? [y/N] " go
if [[ "${go:-N}" != "y" && "${go:-N}" != "Y" ]]; then
  echo "Abgebrochen."
  exit 0
fi

fix_lang de
fix_lang en

echo
echo "✅ Fertig. Prüfe Änderungen mit:  git diff"
echo "Wenn alles gut aussieht:        git add -A && git commit -m 'fix: normalize /wissen/ links with language prefix' && git push"
