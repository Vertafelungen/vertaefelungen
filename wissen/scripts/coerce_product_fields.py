#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coerce typed product fields in YAML frontmatter:
- in_stock  -> boolean
- price_cents -> integer (Cent), tolerant for '15,90 €', '19.90', '1.590,00', '1590' (string)

Runs on all Markdown files under wissen/content and rewrites the frontmatter
canonically (yaml.safe_dump). Idempotent.
"""

from __future__ import annotations
from pathlib import Path
import re
import yaml

ROOT    = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

START_RE = re.compile(r'^\s*---\s*$')
END_RE   = re.compile(r'^\s*---\s*$')

def normalize_nl(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

# ---------- YAML block helpers ----------

def find_header_span(lines: list[str]) -> tuple[int, int] | None:
    if not lines or not START_RE.match(lines[0]):
        return None
    j = 1
    while j < len(lines) and not END_RE.match(lines[j]):
        j += 1
    if j >= len(lines):
        return None
    return (0, j)

def load_header_dict(header_text: str) -> dict | None:
    try:
        data = yaml.safe_load(header_text)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            data = {"_value": data}
        return data
    except Exception:
        return None

def dump_header_dict(data: dict) -> str:
    return yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
    ).rstrip("\n")

# ---------- Coercion helpers ----------

TRUE_SET  = {"true","wahr","yes","y","ja","j","1","x","✓","✔","vorrätig","verfügbar","available","in stock","auf lager","lagernd"}
FALSE_SET = {"false","falsch","no","n","nein","0","✗","×","ausverkauft","nicht verfügbar","out of stock","oos"}

def coerce_bool(val):
    if isinstance(val, bool):
        return val
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in TRUE_SET:
        return True
    if s in FALSE_SET:
        return False
    # tolerate numbers > 0 as True, 0 as False
    if re.fullmatch(r'[+-]?\d+(\.\d+)?', s):
        try:
            return float(s) != 0.0
        except Exception:
            pass
    return None  # don't change if unrecognized

CURR_RE = re.compile(r'(€|eur|euro)', re.I)

def coerce_cents(val):
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(round(val * 100))
    s = str(val).strip()
    if s == "":
        return None
    # Strip currency and spaces
    s = CURR_RE.sub("", s)
    s = re.sub(r'\s', '', s)

    # If looks like 1.234,56 or 1,234.56 -> pick the last separator as decimal, remove the other as thousands
    if re.search(r'[.,]\d{1,2}$', s):
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '')
                s = s.replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace('.', '')
            s = s.replace(',', '.')
        # else: dot decimal already
        try:
            return int(round(float(s) * 100))
        except Exception:
            pass

    # Pure digits -> interpret as integer cents
    if re.fullmatch(r'\d+', s):
        try:
            return int(s)
        except Exception:
            pass

    # Fallback: try plain float
    try:
        return int(round(float(s) * 100))
    except Exception:
        return None

# ---------- Main normalize ----------

def process_file(p: Path) -> bool:
    t = p.read_text(encoding="utf-8")
    t = normalize_nl(t)
    lines = t.splitlines()
    span = find_header_span(lines)
    if not span:
        return False
    start, end = span
    header_text = "\n".join(lines[start+1:end])
    data = load_header_dict(header_text)
    if data is None:
        # can't parse -> leave, earlier repair scripts should have handled most cases
        return False

    changed = False

    # Only coerce when keys exist (no guessing)
    if "in_stock" in data:
        new_b = coerce_bool(data.get("in_stock"))
        if new_b is not None and new_b != data.get("in_stock"):
            data["in_stock"] = new_b
            changed = True

    # price_cents directly
    if "price_cents" in data:
        new_c = coerce_cents(data.get("price_cents"))
        if new_c is not None and new_c != data.get("price_cents"):
            data["price_cents"] = new_c
            changed = True
    else:
        # derive from price / price_eur if vorhanden
        for alt_key in ("price", "price_eur", "preis", "preis_eur"):
            if alt_key in data:
                new_c = coerce_cents(data.get(alt_key))
                if new_c is not None:
                    data["price_cents"] = new_c
                    changed = True
                    break

    if not changed:
        return False

    dumped = dump_header_dict(data)
    new_lines = ["---", *dumped.splitlines(), "---", "", *lines[end+1:]]
    new_text = "\n".join(new_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    p.write_text(new_text, encoding="utf-8")
    return True

def main() -> int:
    changed = 0
    for p in CONTENT.rglob("*.md"):
        try:
            if process_file(p):
                changed += 1
        except Exception as e:
            print(f"[WARN] coerce failed for {p}: {e}")
    print(f"Coerced typed fields in: {changed} files")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
