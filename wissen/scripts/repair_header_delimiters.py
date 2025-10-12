#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repair Frontmatter delimiters:
- Replace leading/closing "***" (or other stray characters) with '---'
- If an opening delimiter exists but no closing one, auto-close before the first non-header line
- Normalize newline style and ensure a blank line after closing delimiter
"""

from __future__ import annotations
from pathlib import Path
import re

ROOT    = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

START_PATTERNS = (
    re.compile(r'^\s*(\*{3})\s*$'),                      # ***
    re.compile(r'^\s*(—+|–+|―+)\s*$'),                   # em/en dashes
    re.compile(r'^\s*(\-{3})\s*$'),                      # --- (already good)
)
CLOSE_PATTERN = re.compile(r'^\s*(\*{3}|\-+|—+|–+|―+)\s*$')

KEY_LINE = re.compile(r'^[A-Za-z0-9_.-]+\s*:\s*.*$')
INDENTED = re.compile(r'^\s+.+$')

def _nl(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

def looks_like_header_line(line: str) -> bool:
    # simple heuristic: key: value or indented continuation
    return bool(KEY_LINE.match(line)) or bool(INDENTED.match(line)) or line.strip() == ""

def repair_file(p: Path) -> bool:
    txt = _nl(p.read_text(encoding="utf-8"))
    lines = txt.splitlines()

    if not lines:
        return False

    # detect opening delimiter variant at very top (allow initial BOM/blank)
    i = 0
    while i < min(3, len(lines)) and lines[i].strip() == "":
        i += 1
    if i >= len(lines):
        return False

    m = None
    for pat in START_PATTERNS:
        m = pat.match(lines[i])
        if m:
            break
    if not m:
        return False  # no header at top → nothing to do here

    changed = False

    # normalize the opening delimiter to '---'
    if lines[i].strip() != "---":
        lines[i] = "---"
        changed = True

    # find a closing delimiter after i
    j = i + 1
    close_idx = -1
    while j < len(lines):
        if CLOSE_PATTERN.match(lines[j]):
            close_idx = j
            break
        # stop probing header if we hit something clearly not header-like (e.g., '# ', '```')
        if not looks_like_header_line(lines[j]):
            break
        j += 1

    if close_idx == -1:
        # we didn't find a valid closing delimiter → insert before j
        insert_at = j
        lines.insert(insert_at, "---")
        close_idx = insert_at
        changed = True
    else:
        # normalize existing closing delimiter to '---'
        if lines[close_idx].strip() != "---":
            lines[close_idx] = "---"
            changed = True

    # ensure one empty line right after closing delimiter
    if close_idx + 1 < len(lines):
        if lines[close_idx + 1].strip() != "":
            lines.insert(close_idx + 1, "")
            changed = True

    if not changed:
        return False
    new_txt = "\n".join(lines)
    if not new_txt.endswith("\n"):
        new_txt += "\n"
    p.write_text(new_txt, encoding="utf-8")
    return True

def main() -> int:
    fixed = 0
    for md in CONTENT.rglob("*.md"):
        try:
            if repair_file(md):
                fixed += 1
        except Exception as e:
            print(f"[WARN] header delimiter repair failed for {md}: {e}")
    print(f"Header delimiter repairs: {fixed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
