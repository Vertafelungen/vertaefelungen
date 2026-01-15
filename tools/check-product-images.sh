#!/usr/bin/env bash
set -euo pipefail

public_root=${1:-wissen/public}
base_path_prefix=${2:-/wissen}

public_root_abs=$(realpath -m "$public_root")

if [[ ! -d "$public_root_abs" ]]; then
  echo "ERROR: public_root not found: $public_root" >&2
  exit 1
fi

missing=0
checked=0

extract_sources() {
  python - "$1" <<'PY'
from html.parser import HTMLParser
import sys

class Parser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img" and "src" in attrs:
            print("SRC\t" + attrs["src"])
        if tag == "source" and "srcset" in attrs:
            print("SRCSET\t" + attrs["srcset"])

parser = Parser()
with open(sys.argv[1], encoding="utf-8", errors="ignore") as handle:
    parser.feed(handle.read())
PY
}

process_src() {
  local src=$1
  local html_file=$2
  local html_dir=$3
  local path
  local resolved_abs

  src=$(echo "$src" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  if [[ -z "$src" ]]; then
    return
  fi

  if [[ "$src" =~ ^[a-zA-Z][a-zA-Z0-9+.-]*: ]]; then
    if [[ "$src" =~ ^https?:// ]]; then
      path=$(echo "$src" | sed -E 's#^https?://[^/]+#/#')
    else
      return
    fi
  elif [[ "$src" == //* ]]; then
    path=$(echo "$src" | sed -E 's#^//[^/]+#/#')
  else
    path="$src"
  fi

  path=${path%%\#*}
  path=${path%%\?*}
  if [[ -z "$path" ]]; then
    return
  fi

  if [[ -n "$base_path_prefix" && "$path" == "$base_path_prefix"* ]]; then
    path=${path#"$base_path_prefix"}
  fi

  if [[ "$path" == /* ]]; then
    path=${path#/}
    if [[ -z "$path" ]]; then
      return
    fi
    resolved_abs=$(realpath -m "$public_root_abs/$path")
  else
    resolved_abs=$(realpath -m "$html_dir/$path")
  fi

  checked=$((checked + 1))

  case "$resolved_abs" in
    "$public_root_abs"|"$public_root_abs"/*)
      ;;
    *)
      echo "MISSING: $html_file -> $src -> $resolved_abs (outside public root)"
      missing=$((missing + 1))
      return
      ;;
  esac

  if [[ ! -f "$resolved_abs" ]]; then
    echo "MISSING: $html_file -> $src -> $resolved_abs"
    missing=$((missing + 1))
  fi
}

while IFS= read -r -d '' html_file; do
  html_dir=$(dirname "$html_file")
  while IFS=$'\t' read -r kind value; do
    if [[ "$kind" == "SRC" ]]; then
      process_src "$value" "$html_file" "$html_dir"
    elif [[ "$kind" == "SRCSET" ]]; then
      IFS=',' read -ra candidates <<< "$value"
      for candidate in "${candidates[@]}"; do
        url=$(echo "$candidate" | awk '{print $1}')
        process_src "$url" "$html_file" "$html_dir"
      done
    fi
  done < <(extract_sources "$html_file")

done < <(find "$public_root_abs" -type f -name '*.html' -print0)

if [[ $missing -gt 0 ]]; then
  echo "FAIL: $missing missing assets"
  exit 1
fi

echo "OK: $checked images checked"
