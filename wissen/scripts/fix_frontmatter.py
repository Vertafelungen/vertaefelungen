#!/usr/bin/env python3
# Version: 2025-10-07 14:05 Europe/Berlin
# Entfernt BOM/Steuerzeichen und zieht last_sync in die Frontmatter

from __future__ import annotations
from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]  # .../wissen
CONTENT = ROOT / "content"

CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
BOM = "\ufeff"

def sanitize(s: str) -> str:
    if not s:
        return s
    s = s.replace(BOM, "")
    s = CTRL_RE.sub(" ", s)
    s = s.replace("\r\n", "\n")
    return s

def pull_last_sync_into_frontmatter(txt: str) -> str:
    # Falls last_sync außerhalb der Frontmatter steht, in die Frontmatter heben.
    m = re.match(r'^---\n(.*?\n)---\n(.*)$', txt, flags=re.S)
    if not m:
        return txt
    fm, body = m.group(1), m.group(2)
    # last_sync im Body suchen
    ms = re.search(r'^\s*last_sync:\s*".*?"\s*$', body, flags=re.M)
    if ms and "last_sync:" not in fm:
        fm = fm.rstrip("\n") + "\n" + ms.group(0) + "\n"
        body = body[:ms.start()] + body[ms.end():]
    return f"---\n{fm}---\n{body.lstrip()}"

def fix_file(p: Path) -> bool:
    raw = p.read_text(encoding="utf-8", errors="replace")
    fixed = sanitize(raw)
    fixed = pull_last_sync_into_frontmatter(fixed)
    if fixed != raw:
        p.write_text(fixed, encoding="utf-8")
        print(f"[FIX] {p}")
        return True
    return False

def main():
    md_files = list(CONTENT.rglob("*.md"))
    changed = 0
    for f in md_files:
        # Nur Dateien mit Frontmatter anfassen
        peek = f.read_text(encoding="utf-8", errors="replace")[:4]
        if "---" not in peek and "\ufeff---" not in peek:
            continue
        if fix_file(f):
            changed += 1
    print(f"✓ repariert: {changed} Dateien")

if __name__ == "__main__":
    sys.exit(main())
