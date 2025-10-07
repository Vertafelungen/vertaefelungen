#!/usr/bin/env python3
# Version: 2025-10-07 14:35 Europe/Berlin
from __future__ import annotations
from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]  # .../wissen
CONTENT = ROOT / "content"

CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')  # Tabs (0x09) NICHT, die ersetzen wir gezielt in YAML
BOM = "\ufeff"

def sanitize_all(s: str) -> str:
    if not s:
        return s
    s = s.replace(BOM, "")
    s = CTRL_RE.sub(" ", s)
    s = s.replace("\r\n", "\n")
    return s

def ensure_frontmatter_starts_at_col1(s: str) -> str:
    # Alles vor dem ersten "---\n" wegtrimmen (Whitespace), damit die Frontmatter wirklich bei Spalte 1 startet
    m = re.search(r'(?m)^[ \t]*---\n', s)
    if not m:
        return s  # Datei ohne Frontmatter: unverändert
    start = m.start()
    return s[start:]  # alles davor weg

def detab_yaml_head(s: str) -> str:
    m = re.match(r'^---\n(.*?\n)---\n', s, flags=re.S)
    if not m:
        return s
    head = m.group(1)
    # Tabs am Zeilenanfang in zwei Spaces je Tab umwandeln
    def repl(line: str) -> str:
        leading_tabs = re.match(r'^\t+', line)
        if not leading_tabs:
            return line
        return line.replace('\t', '  ', leading_tabs.end())
    fixed = "\n".join(repl(ln) for ln in head.split("\n"))
    return s.replace(head, fixed, 1)

def pull_last_sync_into_frontmatter(s: str) -> str:
    m = re.match(r'^---\n(.*?\n)---\n(.*)$', s, flags=re.S)
    if not m:
        return s
    fm, body = m.group(1), m.group(2)
    ms = re.search(r'^\s*last_sync:\s*".*?"\s*$', body, flags=re.M)
    if ms and "last_sync:" not in fm:
        fm = fm.rstrip("\n") + "\n" + ms.group(0) + "\n"
        body = body[:ms.start()] + body[ms.end():]
    return f"---\n{fm}---\n{body.lstrip()}"

def fix_file(p: Path) -> bool:
    raw = p.read_text(encoding="utf-8", errors="replace")
    s = sanitize_all(raw)
    s = ensure_frontmatter_starts_at_col1(s)
    s = detab_yaml_head(s)
    s = pull_last_sync_into_frontmatter(s)
    if s != raw:
        p.write_text(s, encoding="utf-8")
        print(f"[FIX] {p}")
        return True
    return False

def main():
    changed = 0
    for f in CONTENT.rglob("*.md"):
        # ALLE .md prüfen – keine Vorab-Heuristik mehr
        try:
            if fix_file(f):
                changed += 1
        except Exception as e:
            print(f"[WARN] {f}: {e}", file=sys.stderr)
    print(f"✓ repariert: {changed} Dateien")
    return 0

if __name__ == "__main__":
    sys.exit(main())
