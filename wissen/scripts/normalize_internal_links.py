#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/scripts/normalize_internal_links.py
Version: 2026-02-24 10:30 Europe/Berlin
"""

from __future__ import annotations

from pathlib import Path

REPLACEMENTS = [
    ("](/wissen/de/", "](/de/"),
    ("](/wissen/en/", "](/en/"),
    ("(/wissen/de/", "(/de/"),
    ("(/wissen/en/", "(/en/"),
    ("https://www.vertaefelungen.de/wissen/de/", "/de/"),
    ("https://www.vertaefelungen.de/wissen/en/", "/en/"),
]


def normalize_text(text: str) -> str:
    out = text
    for old, new in REPLACEMENTS:
        out = out.replace(old, new)
    return out


def main() -> int:
    root = Path("content")
    changed = 0
    for md in sorted(root.rglob("*.md")):
        src = md.read_text(encoding="utf-8", errors="replace")
        dst = normalize_text(src)
        if dst != src:
            md.write_text(dst, encoding="utf-8", newline="\n")
            changed += 1
    print(f"[normalize_internal_links] changed files: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
