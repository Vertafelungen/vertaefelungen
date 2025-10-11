#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Normalize YAML values in frontmatter with a two-stage strategy:

1) Try to parse the frontmatter block with PyYAML (safe_load).
   - If it loads, dump it back (safe_dump) to produce canonical, valid YAML.
2) If parsing fails, salvage:
   - Tokenize "key:" occurrences line by line.
   - Collect simple block lists under a key:
         key:
           - item
           - item 2
     and convert inline lists like "key: - a, - b" to block lists.
   - Treat everything after the first "key:" token as a scalar (quoted when needed).
   - Finally dump with safe_dump (allow_unicode=True, sort_keys=False).

Idempotent and defensive against odd characters (&, *, :, { }, [ ], #, etc.).
"""

from __future__ import annotations
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

START_RE = re.compile(r'^\s*---\s*$')
END_RE   = re.compile(r'^\s*---\s*$')

# tokenizers / recognizers
KEY_LINE  = re.compile(r'^([A-Za-z0-9_\-]+)\s*:\s*(.*)$')
LIST_ITEM = re.compile(r'^\s*-\s+(.*)$')
KEY_TOKEN = re.compile(r'(?<!\S)([A-Za-z0-9_\-]+)\s*:\s*')  # finds key: at word boundaries

# characters that require quoting if used in scalars
NEEDS_QUOTE_CHARS = set(':#*[]{}&!|>%@`')

def normalize_nl(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

def needs_quotes(value: str) -> bool:
    v = value.strip()
    if v == "":
        return False
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return False
    if v.startswith("-") or v.startswith("*"):
        return True
    if any(ch in v for ch in NEEDS_QUOTE_CHARS):
        return True
    return False

def quote(value: str) -> str:
    v = value.strip().replace('"', '\\"')
    return f'"{v}"'

def split_inline_list(rest: str) -> list[str] | None:
    s = rest.strip()
    if not s.startswith("- "):
        return None
    parts = [p.strip() for p in s[2:].split(", - ")]
    return [p for p in parts if p]

def extract_header_span(lines: list[str]) -> tuple[int, int] | None:
    if not lines or not START_RE.match(lines[0]):
        return None
    j = 1
    while j < len(lines) and not END_RE.match(lines[j]):
        j += 1
    if j >= len(lines):
        return None
    return (0, j)  # start at 0 ('---'), end index of closing '---' line

def parse_with_pyyaml(header_text: str) -> dict | None:
    try:
        data = yaml.safe_load(header_text)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            # Convert scalars/lists to mapping to keep frontmatter shape
            data = {"_value": data}
        return data
    except Exception:
        return None

def salvage_header(lines: list[str], start: int, end: int) -> dict:
    """
    Build a dictionary from lines[start+1:end] without trusting YAML parser.
    Rules:
    - key: inline list (- a, - b) -> block list
    - key: value (quote when needed)
    - block lists:
          key:
            - item
            - item2
    - Duplicate keys: last wins.
    """
    data: dict = {}
    i = start + 1
    current_key: str | None = None
    current_list: list | None = None

    def close_list():
        nonlocal current_key, current_list
        if current_key is not None and current_list is not None:
            data[current_key] = current_list
        current_key = None
        current_list = None

    while i < end:
        ln = lines[i]

        # list item under an open list
        mli = LIST_ITEM.match(ln)
        if mli and current_key is not None:
            item = mli.group(1).strip()
            if needs_quotes(item):
                item = quote(item)
            # store raw string; safe_dump will handle quotes properly
            current_list.append(item.strip('"'))
            i += 1
            continue

        # key: rest
        mk = KEY_LINE.match(ln)
        if mk:
            # closing previous list if any
            close_list()

            key = mk.group(1)
            rest = mk.group(2)

            # inline list?
            items = split_inline_list(rest)
            if items is not None:
                lst = []
                for it in items:
                    if needs_quotes(it):
                        it = quote(it)
                    lst.append(it.strip('"'))
                data[key] = lst
                i += 1
                continue

            # scalar value
            val = rest.strip()
            if val == "":
                # could be start of block list in next lines
                current_key = key
                current_list = []
                i += 1
                continue

            if needs_quotes(val):
                val = quote(val)
            data[key] = val.strip('"')
            i += 1
            continue

        # non-matching line → end of current list if present; keep as comment?
        close_list()
        i += 1

    close_list()
    return data

def rebuild_frontmatter_dict(text: str) -> tuple[str, bool]:
    text = normalize_nl(text)
    lines = text.splitlines()
    span = extract_header_span(lines)
    if not span:
        return text, False
    start, end = span
    header_block = "\n".join(lines[start+1:end])  # between '---' and '---'

    # 1) try YAML
    data = parse_with_pyyaml(header_block)
    if data is None:
        # 2) salvage
        data = salvage_header(lines, start, end)

    # dump back canonical
    dumped = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    ).rstrip("\n")

    new_lines = []
    new_lines.append("---")
    new_lines.extend(dumped.splitlines())
    new_lines.append("---")
    # keep a blank line after frontmatter
    new_lines.append("")
    new_lines.extend(lines[end+1:])

    new_text = "\n".join(new_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    return new_text, (new_text != text)

def normalize_file(p: Path) -> bool:
    t = p.read_text(encoding="utf-8")
    new_t, changed = rebuild_frontmatter_dict(t)
    if changed:
        p.write_text(new_t, encoding="utf-8")
    return changed

def main() -> int:
    changed = 0
    for p in CONTENT.rglob("*.md"):
        try:
            if normalize_file(p):
                changed += 1
        except Exception as e:
            print(f"[WARN] normalize failed for {p}: {e}")
    print(f"Normalized YAML frontmatter in: {changed} files")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
