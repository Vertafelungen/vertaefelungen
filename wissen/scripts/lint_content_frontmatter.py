#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lint & Auto-Fix für ungeschlossenes YAML-Frontmatter in Markdown-Dateien (wissen/content/**).

Robust:
- Binäres Lesen, UTF-8 bevorzugt, Fallback CP-1252; BOM entfernen
- CRLF -> LF
- Erkennung von Frontmatter auch mit führenden Spaces/Tabs vor '---'
- Setzt fehlendes schließendes '---' an plausibler Stelle (vor erster Nicht-YAML-Zeile)
- Schreibt immer UTF-8 (ohne BOM), LF
- Verbose-Ausgabe: zeigt alle reparierten Dateien an

ENV:
  AUTOFIX_FRONTMATTER=1  -> automatisch reparieren (sonst nur melden)
  LINT_VERBOSE=1         -> detailierte Ausgabe

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
        return b.decode("cp1252", errors="strict")

def normalize_lf(t: str) -> str:
    return t.replace("\r\n", "\n").replace("\r", "\n")

def starts_with_frontmatter(t: str) -> bool:
    t = normalize_lf(t)
    # BOM/Whitespace vor '---' tolerieren
    i = 0
    while i < len(t) and t[i] in ("\ufeff", " ", "\t"):
        i += 1
    return t[i:].startswith("---")

def has_closing_delimiter(t: str) -> bool:
    t = normalize_lf(t)
    # erste Zeile (inkl. evtl. leading spaces) identifizieren
    lines = t.split("\n")
    if not lines:
        return False
    first = lines[0].lstrip("\ufeff \t")
    if not first.startswith("---"):
        return False
    # Suche schließendes '---' in den Folgezeilen
    for L in lines[1:]:
        if RE_CLOSER.match(L):
            return True
    return False

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
    # lines[0] enthält die erste Zeile (kann leading spaces haben); wir nehmen sie als '---'-Zeile
    for i in range(1, len(lines)):
        L = lines[i]
        if RE_CLOSER.match(L):
            return i
        if is_yamlish_line(L):
            continue
        # Content (Überschrift/Text/Codefence/HR)
        return i - 1
    return len(lines) - 1

def fix_text(t: str) -> str:
    t = normalize_lf(t)
    # leading whitespace vor Zeile 1 bewahren, aber in die erste Zeile zurückgeben
    lines = t.split("\n")
    if not lines:
        return t
    first = lines[0]
    if not first.lstrip("\ufeff \t").startswith("---"):
        return t
    insert_after = detect_insert_after(lines)
    new = []
    # wir erhalten die erste Zeile unverändert (inkl. etwaiger leading spaces)
    new.append(first.rstrip("\n"))
    new.extend(lines[1:insert_after+1])
    new.append("---")
    new.extend(lines[insert_after+1:])
    out = "\n".join(l.rstrip("\n") for l in new)
    if not out.endswith("\n"):
        out += "\n"
    return out

def main() -> int:
    autofix = os.environ.get("AUTOFIX_FRONTMATTER", "").strip().lower() in {"1","true","yes"}
    verbose = os.environ.get("LINT_VERBOSE", "").strip().lower() in {"1","true","yes"}
    bad = []
    fixed = []

    for p in CONTENT_DIR.rglob("*.md"):
        try:
            raw = read_text_any(p)
        except Exception:
            # unlesbar -> Hugo meldet später, hier nicht blocken
            continue

        if starts_with_frontmatter(raw) and not has_closing_delimiter(raw):
            if autofix:
                new = fix_text(raw)
                if new != raw:
                    p.write_text(new, encoding="utf-8", newline="\n")
                    fixed.append(p)
            else:
                bad.append(p)

    if verbose:
        if fixed:
            print("Auto-fixed Frontmatter in:", file=sys.stdout)
            for f in sorted(fixed):
                print(" +", f.relative_to(REPO_ROOT), file=sys.stdout)
        else:
            print("Auto-fixed Frontmatter: none", file=sys.stdout)

    if bad:
        print("Frontmatter-Lint: ungeschlossenes '---' in folgenden Dateien:", file=sys.stderr)
        for f in sorted(bad):
            print(" -", f.relative_to(REPO_ROOT), file=sys.stderr)
        print("Setze AUTOFIX_FRONTMATTER=1, um automatisch zu reparieren.", file=sys.stderr)
        return 1

    print(f"Frontmatter-Lint OK. Auto-fixed: {len(fixed)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
