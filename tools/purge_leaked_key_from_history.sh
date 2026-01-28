#!/usr/bin/env bash
set -euo pipefail

TARGET_FILE="alttext-automatisierung-8398e2703b3b.json"

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo ist nicht installiert. Installiere es z.B. via:"
  echo "  pip install git-filter-repo"
  exit 1
fi

echo "Entferne ${TARGET_FILE} aus der Git-Historie..."
git filter-repo --path "$TARGET_FILE" --invert-paths

cat <<'EOF'

History-Rewrite abgeschlossen.

Als nächstes (manuell) ausführen:
  git push --force --all
  git push --force --tags

Wichtig: Alle Mitwirkenden müssen ihre lokalen Repos neu klonen oder hard resetten.
EOF
