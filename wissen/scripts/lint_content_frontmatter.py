#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lint & Auto-Fix für ungeschlossenes YAML-Frontmatter in Markdown-Dateien.

Verbesserungen:
- Liest binär, dekodiert bevorzugt UTF-8, fällt auf CP-1252 (latin-1) zurück
- Entfernt UTF-8 BOM, normalisiert CRLF->LF
- Erkennt schließendes '---' per Regex (auch mit Whitespace)
- Setzt schließendes '---' an plausibler Stelle
- Schreibt IMMER UTF-8 (ohne BOM), LF

ENV:
  AUTOFIX_FRONTMATTER=1  -> automatisch reparieren (sonst nur melden)

Exit:
  0 = OK (oder alles repariert)
  1 = Probleme gefunden (ohne Auto-Fix)
"""
from __future__ import annotations

from pathlib import Path
import os, sys, re

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIR = REPO_ROOT / "wissen" / "content"

RE_CLOSER = re.compile(r'^\s*---\s*$', re.MULTILINE)
RE_YAML_KEY = re.compile(r'^\s*[A-Za-z0-9_-]+\s*:\s*')   # title: '...'
RE_YAML_LIST = re.compile(r'^\s*-\s+')
RE_CODE_FENCE = re.compile(r'^\s*```')

def read_text_any(p: Path) -> str:
    b = p.read_bytes()
    # strip UTF-8 BOM if present
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        # Fallback auf CP-1252/latin-1
        return b.decode("cp1252")

def normalize_lf(t: str) -> str:
    return t.replace("\r\n", "\n").replace("\r", "\n")

def starts_with_frontmatter(t: str) -> bool:
    t2 = t.lstrip("\ufeff")  # evtl. BOM im Text
    return t2.startswith("---")

def has_closing_delimiter(t: str) -> bool:
    # suche einen schließenden '---' NACH der ersten Zeile
    t = normalize_lf(t)
    if not starts_with_frontmatter(t):
        return False
    # Position der ersten Zeile
    nl = t.find("\n")
    if nl == -1:
        return False
    rest = t[nl+1:]
    m = RE_CLOSER.search(rest)
    return m is not None

def is_yamlish_line(line: str) -> bool:
    s = line.rstrip("\n")
    if s.strip() == "":
        return True
    if s.strip().startswith("#"):
        return True
    if RE_YAML_KEY.match(s):
        return True
    if RE_YAML_LIST.match(s):
        return True
    return False

def detect_insert_after(lines: list[str]) -> int:
    # lines[0] ist '---'
    for i in range(1, len(lines)):
        L = lines[i]
        if RE_CLOSER.match(L):
            return i
        if is_yamlish_line(L):
            continue
        # Content beginnt (Überschrift, Text, Code-Fence etc.) -> schließe davor
        return i - 1
    return len(lines) - 1

def fix_text(t: str) -> str:
    t = normalize_lf(t.lstrip("\ufeff"))
    lines = t.split("\n")
    if not lines or lines[0].strip() != "---":
        return t
    insert_after = detect_insert_after(lines)
    new = []
    new.append("---")
    new.extend(lines[1:insert_after+1])
    new.append("---")
    new.extend(lines[insert_after+1:])
    out = "\n".join(l.rstrip("\n") for l in new)
    if not out.endswith("\n"):
        out += "\n"
    return out

def main() -> int:
    autofix = os.environ.get("AUTOFIX_FRONTMATTER", "").strip().lower() in {"1","true","yes"}
    bad = []
    fixed_count = 0

    for p in CONTENT_DIR.rglob("*.md"):
        try:
            raw = read_text_any(p)
        except Exception:
            # wenn selbst binär kaputt -> später vom Build erwischt
            continue

        if starts_with_frontmatter(raw) and not has_closing_delimiter(raw):
            if autofix:
                new = fix_text(raw)
                if new != raw:
                    p.write_text(new, encoding="utf-8", newline="\n")
                    fixed_count += 1
            else:
                bad.append(p)

    if bad:
        print("Frontmatter-Lint: ungeschlossenes '---' in folgenden Dateien:", file=sys.stderr)
        for f in sorted(bad):
            print(" -", f.relative_to(REPO_ROOT), file=sys.stderr)
        print("Setze AUTOFIX_FRONTMATTER=1, um automatisch zu reparieren.", file=sys.stderr)
        return 1

    print(f"Frontmatter-Lint OK. Auto-fixed: {fixed_count}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
