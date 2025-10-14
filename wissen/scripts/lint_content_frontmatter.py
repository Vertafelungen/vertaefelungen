#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Fix für Frontmatter-Delimiters in wissen/content/**:
- erkennt auch falsche Delimiter (***, —, –––, ___) und wandelt sie in '---' um
- schließt fehlendes schließendes '---'
- robust bei UTF-8/CP-1252, BOM, CRLF
- schreibt UTF-8 + LF

ENV:
  AUTOFIX_FRONTMATTER=1 -> schreiben, sonst nur melden
  LINT_VERBOSE=1        -> Liste der geänderten Dateien
"""
from __future__ import annotations
import os, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "wissen" / "content"

RE_BAD_DELIM = re.compile(r'^\s*(\*\*\*|—|–––|___)\s*$', re.MULTILINE)
RE_OPEN = re.compile(r'^\s*\ufeff?\s*---\s*$', re.MULTILINE)
RE_CLOSE = re.compile(r'^\s*---\s*$', re.MULTILINE)

def read_any(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252")
    return t.replace("\r\n", "\n").replace("\r", "\n")

def write_utf8_lf(p: Path, t: str) -> None:
    if not t.endswith("\n"):
        t += "\n"
    p.write_text(t, encoding="utf-8", newline="\n")

def normalize_bad_delims(t: str) -> str:
    # wenn die allererste Zeile ein bad delimiter ist -> ersetze durch '---'
    lines = t.split("\n")
    if not lines:
        return t
    if RE_BAD_DELIM.match(lines[0] or ""):
        lines[0] = "---"
    # schließenden Delimiter suchen; wenn letzte Delim-Zeile bad ist -> fixen
    for i in range(1, len(lines)):
        if RE_BAD_DELIM.match(lines[i] or ""):
            lines[i] = "---"
            break
        if RE_CLOSE.match(lines[i] or ""):
            break
    return "\n".join(lines)

def has_unclosed_frontmatter(t: str) -> bool:
    if not t.lstrip("\ufeff").startswith("---"):
        return False
    lines = t.split("\n")
    # suche schließendes '---'
    for i in range(1, len(lines)):
        if RE_CLOSE.match(lines[i] or ""):
            return False
    return True

def fix_text(t: str) -> str:
    t = normalize_bad_delims(t)
    if not t.lstrip("\ufeff").startswith("---"):
        return t
    lines = t.split("\n")
    # schließendes '---' ergänzen falls fehlt
    if has_unclosed_frontmatter(t):
        # füge '---' nach YAML-ähnlichem Block ein (hier pragmatisch: nach Zeile 1)
        lines.insert(1, "---")
    return "\n".join(lines)

def main() -> int:
    apply = os.environ.get("AUTOFIX_FRONTMATTER", "") in {"1", "true", "yes"}
    verbose = os.environ.get("LINT_VERBOSE", "") in {"1", "true", "yes"}
    fixed = []

    for p in ROOT.rglob("*.md"):
        raw = read_any(p)
        new = fix_text(raw)
        if new != raw:
            if apply:
                write_utf8_lf(p, new)
            fixed.append(p)

    if verbose:
        if fixed:
            print("Auto-fixed files:")
            for f in fixed:
                print(" +", f.relative_to(REPO))
        else:
            print("Auto-fix: no changes")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
