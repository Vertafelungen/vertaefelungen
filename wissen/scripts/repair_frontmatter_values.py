#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Normalize YAML values in frontmatter:
- Quote scalars that need quoting (contain ':', '#', '*', '[', ']', '{', '}', '&', '!', '|', '>', '%', '@', '`'
  or start with '-' or '*' or contain leading/trailing spaces).
- Transform inline lists like 'key: - item1, - item2' into proper block lists:
      key:
        - item1
        - item2
- Keep existing quotes as-is.
- Idempotent: multiple runs are safe.

This script assumes a standard frontmatter delimitation:
  ---\n
  (yaml)
  ---\n
at the beginning of the file.
"""

from __future__ import annotations
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

START_RE = re.compile(r'^---\s*$')
END_RE   = re.compile(r'^---\s*$')
LINE_RE  = re.compile(r'^([A-Za-z0-9_\-]+)\s*:\s*(.*)$')

def normalize_nl(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

# characters that force quoting (YAML specials or ambiguous)
NEEDS_QUOTE_CHARS = set(':#*[]{}&!|>%@`')

def needs_quotes(value: str) -> bool:
    v = value.strip()
    if v == "":
        return False
    # already quoted
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return False
    # starts like list/alias
    if v.startswith("-") or v.startswith("*"):
        return True
    # contains specials or colon
    if any(ch in v for ch in NEEDS_QUOTE_CHARS):
        return True
    # leading/trailing spaces after stripping -> already handled above
    return False

def quote(value: str) -> str:
    v = value.strip()
    # escape inner double quotes
    v = v.replace('"', '\\"')
    return f'"{v}"'

def split_inline_list(rest: str) -> list[str] | None:
    """
    Recognize ' - item1, - item2' and split into items.
    Returns None if the pattern doesn't match.
    """
    s = rest.strip()
    if not s.startswith("- "):
        return None
    # split on ', - ' if present, else single item
    parts = [p.strip() for p in s[2:].split(", - ")]
    # filter empties
    return [p for p in parts if p]

def process_frontmatter(lines: list[str], start: int, end: int) -> list[str]:
    """
    Normalize lines[start+1:end] (exclusive end) as YAML header.
    """
    out: list[str] = []
    i = start + 1
    while i < end:
        ln = lines[i]
        m = LINE_RE.match(ln)
        if not m:
            # keep non key: value lines (comments/blank/indented) as-is
            out.append(ln)
            i += 1
            continue

        key = m.group(1)
        rest = m.group(2)

        # Case: inline list after colon
        items = split_inline_list(rest)
        if items is not None:
            out.append(f"{key}:")
            for it in items:
                # quote each item if needed
                out.append(f"  - {quote(it) if needs_quotes(it) else it}")
            i += 1
            continue

        # Normal scalar on same line
        val = rest
        if needs_quotes(val):
            val = quote(val)
        out.append(f"{key}: {val}")
        i += 1

    return out

def normalize_file(p: Path) -> bool:
    t = p.read_text(encoding="utf-8")
    t = normalize_nl(t)
    lines = t.splitlines()
    if not lines:
        return False

    # must start with '---'
    if not START_RE.match(lines[0]):
        return False

    # find end delimiter
    j = 1
    while j < len(lines) and not END_RE.match(lines[j]):
        j += 1
    if j >= len(lines):
        # no end delimiter -> leave to other repair step
        return False

    before = lines[:1]
    header = process_frontmatter(lines, 0, j)
    after  = lines[j+1:]
    new_lines = before + header + ["---"] + [""] + after  # blank line after header for readability
    new_t = "\n".join(new_lines)
    if not new_t.endswith("\n"):
        new_t += "\n"
    if new_t != t:
        p.write_text(new_t, encoding="utf-8")
        return True
    return False

def main() -> int:
    changed = 0
    for p in CONTENT.rglob("*.md"):
        try:
            if normalize_file(p):
                changed += 1
        except Exception as e:
            print(f"[WARN] Failed to normalize {p}: {e}")
    print(f"Normalized YAML values in: {changed} files")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
