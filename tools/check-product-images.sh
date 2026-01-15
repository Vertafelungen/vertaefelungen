#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
public_root="$repo_root/wissen/public"

if [[ -d "$public_root/wissen" ]]; then
  public_root="$public_root/wissen"
fi

if [[ ! -d "$public_root" ]]; then
  echo "Public output not found at $public_root. Run hugo before this check." >&2
  exit 1
fi

pages=(
  "de/produkte/halbhohe-vertaefelungen/21-p0009/index.html"
  "de/produkte/lueftungsrosetten/75-blr7/index.html"
)

min_imgs=2

for page in "${pages[@]}"; do
  page_path="$public_root/$page"
  if [[ ! -f "$page_path" ]]; then
    echo "Missing built page: $page_path" >&2
    exit 1
  fi

  img_count=$(grep -o "<img " "$page_path" | wc -l | tr -d ' ')
  if [[ "$img_count" -lt "$min_imgs" ]]; then
    echo "Expected at least $min_imgs <img> tags in $page_path, found $img_count" >&2
    exit 1
  fi

  while IFS= read -r src; do
    src_path=$(echo "$src" | sed -E 's#^https?://[^/]+##')
    if [[ "$public_root" == */wissen ]]; then
      src_path="${src_path#/wissen}"
    fi
    src_path="${src_path#/}"
    file_path="$public_root/$src_path"
    if [[ ! -f "$file_path" ]]; then
      echo "Missing referenced image: $file_path (from $page_path)" >&2
      exit 1
    fi
  done < <(rg -o 'src="[^"]+"' "$page_path" | sed -E 's/src="([^"]+)"/\1/')

  echo "Checked $page_path ($img_count images)."
done
