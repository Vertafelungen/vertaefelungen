#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quote/escape risky YAML scalar values inside frontmatter:
- Any single-line value containing ':' or '&' or '#' or '%' or '@' etc. gets double-quoted
- Smart quotes/dashes are normalized
- After quoting, the header is parsed and re-dumped via yaml.safe_dump (idempotent)

This targets errors like: "mapping values are not allowed here" at titles/meta fields.
"""

from __future__ import annotations
from pathlib import Path
import re
import yaml

ROOT    = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

START = re.compile(r'^\s*---\s*$')
END   = re.compile(r'^\s*---\s*$')

SMART_REPL = {
    "\u2013": "-", "\u2014": "-",             # en/em dash
    "\u2018": "'", "\u2019": "'",             # single quotes
    "\u201C": '"', "\u201D": '"',             # double quotes
    "\u00A0": " ", "\u202F": " ",             # NBSPs
}

RISK_CHARS = re.compile(r'[:&#%@!?\[\]\{\},]')  # chars that often break YAML when unquoted

KEY_LINE  = re.compile(r'^([A-Za-z0-9_.-]+)\s*:\s*(.*)$')

def _nl(s: str) -> str:
    return s.replace("\r\n","\n").replace("\r","\n")

def normalize_smart(s: str) -> str:
    for k,v in SMART_REPL.items():
        s = s.replace(k,v)
    return s

def find_header(lines: list[str]) -> tuple[int,int] | None:
    if not lines: return None
    if not START.match(lines[0]): return None
    j = 1
    while j < len(lines) and not END.match(lines[j]):
        j += 1
    if j >= len(lines): return None
    return (0,j)

def try_parse(header_text: str) -> dict | None:
    try:
        data = yaml.safe_load(header_text)
        if data is None: data = {}
        if not isinstance(data, dict): data = {"_value": data}
        return data
    except Exception:
        return None

def quote_if_risky(val: str) -> str:
    s = val.strip()
    if s == "" or s.startswith('"') or s.startswith("'"):
        return s
    if RISK_CHARS.search(s):
        s = s.replace('"', '\\"')
        return f'"{s}"'
    return s

def repair_lines(header_lines: list[str]) -> list[str]:
    out = []
    for line in header_lines:
        m = KEY_LINE.match(line)
        if not m:
            out.append(normalize_smart(line))
            continue
        key, raw = m.group(1), m.group(2)
        raw = normalize_smart(raw)
        # only quote single-line scalars (ignore lists/dicts/multiline)
        if raw.strip().startswith(("-", "[", "{", "|", ">", "*", "&")):
            out.append(f"{key}: {raw}")
        else:
            out.append(f"{key}: {quote_if_risky(raw)}")
    return out

def process_file(p: Path) -> bool:
    txt = _nl(p.read_text(encoding="utf-8"))
    lines = txt.splitlines()
    span = find_header(lines)
    if not span:
        return False
    start, end = span
    header_text = "\n".join(lines[start+1:end])

    # fast path: if it parses, re-dump canonical and done
    data = try_parse(header_text)
    if data is not None:
        dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000).rstrip("\n")
        new = ["---", *dumped.splitlines(), "---", "", *lines[end+1:]]
        new_txt = "\n".join(new)
        if not new_txt.endswith("\n"): new_txt += "\n"
        if new_txt != txt:
            p.write_text(new_txt, encoding="utf-8")
            return True
        return False

    # fallback: line-wise quoting then parse again
    repaired = repair_lines(lines[start+1:end])
    repaired_text = "\n".join(repaired)
    data2 = try_parse(repaired_text)
    if data2 is None:
        # give up for this file; let guard show detail
        return False

    dumped = yaml.safe_dump(data2, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000).rstrip("\n")
    new = ["---", *dumped.splitlines(), "---", "", *lines[end+1:]]
    new_txt = "\n".join(new)
    if not new_txt.endswith("\n"): new_txt += "\n"
    p.write_text(new_txt, encoding="utf-8")
    return True

def main() -> int:
    changed = 0
    for md in CONTENT.rglob("*.md"):
        try:
            if process_file(md):
                changed += 1
        except Exception as e:
            print(f"[WARN] scalar repair failed for {md}: {e}")
    print(f"Scalar repairs: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
