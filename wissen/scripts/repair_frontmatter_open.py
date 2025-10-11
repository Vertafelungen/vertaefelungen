#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repariert Markdown-Dateien mit *offenem* YAML-Frontmatter:
- Datei beginnt mit '---' (erste Zeile),
- es existiert KEIN zweites '---' als schließender Delimiter.
Lösung: wir entfernen das einzelne eröffnende '---' und setzen
einen minimalen, leeren Header davor, damit Hugo/Parser nicht abstürzen.

Skript ist idempotent: Mehrfachlauf schadet nicht.
"""

from __future__ import annotations
from pathlib import Path

CONTENT = Path(__file__).resolve().parents[1] / "content"

def has_unclosed_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    if not lines:
        return False
    if lines[0].strip() != '---':
        return False
    # nach erstem '---' kein weiteres '---' als Zeile gefunden?
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            return False
    return True

def main() -> int:
    repaired = 0
    for p in CONTENT.rglob("*.md"):
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        t = t.replace("\r\n","\n").replace("\r","\n")
        if has_unclosed_frontmatter(t):
            lines = t.splitlines()
            # entferne das erste '---'
            body = "\n".join(lines[1:]).lstrip("\n")
            fixed = (
                "---\n"
                "# auto-repaired: missing end YAML frontmatter delimiter\n"
                "---\n\n"
                f"{body}"
            )
            p.write_text(fixed, encoding="utf-8")
            repaired += 1
    print(f"Repaired files (open frontmatter): {repaired}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
