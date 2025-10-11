#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repariert Markdown-Dateien mit *offenem* YAML-Frontmatter:
- Datei beginnt mit einer Zeile, die exakt '---' (optional nur Whitespace dahinter) enthält
  (Regex ^---\s*$, also linksbündig).
- Es existiert *kein* weiterer Abschluss-Delimiter ^---\s*$.
Dann wird ein minimaler, gültiger Header vorangestellt.

Idempotent: Mehrfachlauf ist unkritisch.
"""

from __future__ import annotations
from pathlib import Path
import re

CONTENT = Path(__file__).resolve().parents[1] / "content"

START_RE = re.compile(r'^---\s*$')  # nur linksbündig gültig
END_RE   = re.compile(r'^---\s*$')  # nur linksbündig gültig

def has_unclosed_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    if not lines:
        return False
    # Start muss in Zeile 1 exakt '---' sein
    if not START_RE.match(lines[0]):
        return False
    # Suchen nach einem *gültigen* Abschluss (links­bündig)
    for i in range(1, len(lines)):
        if END_RE.match(lines[i]):
            return False  # gültig geschlossen → kein Fix nötig
    return True  # kein gültiger Abschluss gefunden

def fix_open_frontmatter(text: str) -> str:
    """
    Entfernt das einsame eröffnende '---' und ersetzt es
    durch einen minimalen, gültigen Header.
    """
    lines = text.splitlines()
    # Body = alles nach der ersten Zeile; führende Leerzeilen weg
    body = "\n".join(lines[1:]).lstrip("\n")
    fixed = (
        "---\n"
        "# auto-repaired: missing end YAML frontmatter delimiter\n"
        "---\n\n"
        f"{body}"
    )
    return fixed

def main() -> int:
    repaired = 0
    for p in CONTENT.rglob("*.md"):
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # Zeilenenden normalisieren, damit Regex arbeitet
        t = t.replace("\r\n", "\n").replace("\r", "\n")
        if has_unclosed_frontmatter(t):
            p.write_text(fix_open_frontmatter(t), encoding="utf-8")
            repaired += 1
    print(f"Repaired files (open frontmatter): {repaired}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
