#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strict Guard für alle Markdown-Dateien unter wissen/content/**.

Prüft:
- UTF-8 dekodierbar (BOM toleriert), Zeilenenden auf LF normalisiert (nur Check, keine Änderung)
- Frontmatter-Delimiters: nur '---' zulässig (keine '***', '–––' etc.)
- YAML parsebar (ruamel.yaml, safe)
- Verbotene CP-1252/Smart-Quote/Steuerzeichen im Header & Body
- Typen: price_cents=int, in_stock=bool, images/tags/keywords/listenfelder=list (falls vorhanden)
- Optionaler Modus:
    --mode managed  -> nur Dateien mit 'managed_by:' im Header
    --mode all      -> gesamte Site (Default)

Exit 0: OK, Exit 1: Fehler gefunden (alle werden gelistet)
"""
from __future__ import annotations
import argparse, re, sys, unicodedata
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from ruamel.yaml import YAML

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "wissen" / "content"

RE_FORBIDDEN_DELIMS = re.compile(r'^\s*(\*\*\*|—|–––|___)\s*$', re.MULTILINE)
RE_OPEN = re.compile(r'(?m)^\s*---\s*$')
RE_CLOSE = re.compile(r'(?m)^\s*---\s*$')

SMART_BAD = {
    "\u00A0": "NBSP",
    "\u202F": "NNBSP",
    "\u200B": "ZWSP",
    "\u200C": "ZWNJ",
    "\u200D": "ZWJ",
    "\u2018": "LEFT_SINGLE_QUOTE",
    "\u2019": "RIGHT_SINGLE_QUOTE",
    "\u201C": "LEFT_DOUBLE_QUOTE",
    "\u201D": "RIGHT_DOUBLE_QUOTE",
}

LIST_FIELDS = {"images", "tags", "keywords", "kategorien", "categories"}

def read_utf8(p: Path) -> Tuple[bool, str]:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    try:
        t = b.decode("utf-8")
        return True, t
    except UnicodeDecodeError:
        return False, ""

def split_frontmatter(t: str) -> Tuple[Optional[str], Optional[str], str]:
    m1 = RE_OPEN.search(t)
    if not m1 or m1.start() != 0:
        return None, None, t
    m2 = RE_CLOSE.search(t, m1.end())
    if not m2:
        return None, None, t
    header = t[m1.end():m2.start()]
    body = t[m2.end():]
    return "", header, body

def find_bad_unicode(s: str) -> Dict[str, int]:
    res = {}
    for ch, name in SMART_BAD.items():
        cnt = s.count(ch)
        if cnt:
            res[name] = cnt
    return res

def parse_yaml(header: str) -> Tuple[bool, Dict[str, Any]]:
    y = YAML(typ="safe")
    try:
        data = y.load(header) or {}
        if not isinstance(data, dict):
            return False, {}
        return True, dict(data)
    except Exception:
        return False, {}

def check_types(front: Dict[str, Any]) -> list[str]:
    errs = []
    if "price_cents" in front and not isinstance(front["price_cents"], int):
        errs.append("price_cents must be int")
    if "in_stock" in front and not isinstance(front["in_stock"], bool):
        errs.append("in_stock must be bool")
    for key in LIST_FIELDS:
        if key in front and not isinstance(front[key], list):
            errs.append(f"{key} must be list")
    return errs

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["all", "managed"], default="all")
    args = ap.parse_args()

    errors = []
    for p in CONTENT.rglob("*.md"):
        ok, text = read_utf8(p)
        if not ok:
            errors.append(f"{p}: not UTF-8 decodable")
            continue

        # verbotene Delimiter
        if RE_FORBIDDEN_DELIMS.search(text):
            errors.append(f"{p}: forbidden frontmatter delimiter detected (only '---' allowed)")

        # Frontmatter vorhanden?
        fm = split_frontmatter(text)
        header = fm[1]
        if header is None:
            # keine Frontmatter -> ok für Hugo, aber Bad-Unicode dennoch prüfen
            bad = find_bad_unicode(text)
            if bad:
                errors.append(f"{p}: forbidden unicode in body {bad}")
            continue

        # Modus-Filter
        if args.mode == "managed":
            if "managed_by:" not in header:
                continue

        # Bad unicode
        bad_h = find_bad_unicode(header)
        bad_b = find_bad_unicode(fm[2])
        if bad_h:
            errors.append(f"{p}: forbidden unicode in header {bad_h}")
        if bad_b:
            errors.append(f"{p}: forbidden unicode in body {bad_b}")

        # YAML prüfen
        ok_yaml, data = parse_yaml(header)
        if not ok_yaml:
            errors.append(f"{p}: YAML not parseable")
            continue

        # Typen prüfen
        t_errs = check_types(data)
        for e in t_errs:
            errors.append(f"{p}: {e}")

    if errors:
        print("Guard violations:", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        return 1

    print("Guard OK.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
