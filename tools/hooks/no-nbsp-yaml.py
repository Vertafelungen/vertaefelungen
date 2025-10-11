#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import re, sys, unicodedata

FM_RE = re.compile(r'^---\n(.*?\n)---\n', re.S)
BAD_ZERO_WIDTH = {"\u200B","\u200C","\u200D","\u2060","\u200E","\u200F"}
NBSP = "\u00A0"

def check_file(p: Path) -> list[str]:
    txt = p.read_text(encoding="utf-8", errors="ignore")
    m = FM_RE.match(txt)
    if not m:
        return []
    head = m.group(1)
    errs = []
    if "\t" in head:
        errs.append("TAB in YAML head")
    if NBSP in head:
        errs.append("NBSP in YAML head")
    if any(ch in head for ch in BAD_ZERO_WIDTH):
        errs.append("Zero-Width char in YAML head")
    return errs

def main(argv):
    bad = False
    for arg in argv[1:]:
        p = Path(arg)
        if not p.exists():
            continue
        errs = check_file(p)
        if errs:
            bad = True
            print(f"[BLOCK] {p}: " + "; ".join(errs))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
