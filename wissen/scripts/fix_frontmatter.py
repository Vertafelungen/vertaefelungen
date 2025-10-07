#!/usr/bin/env python3
# Version: 2025-10-07 15:25 Europe/Berlin
from __future__ import annotations
from pathlib import Path
import re, sys

ROOT    = Path(__file__).resolve().parents[1]      # .../wissen
CONTENT = ROOT / "content"

# Control-Chars (ohne TAB), BOM entfernen
CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
BOM     = "\ufeff"

# Unicode-Sonderleerzeichen → normales Leerzeichen,
# Zero-Width-Zeichen/LRM/RLM → entfernen
SPACE_MAP = {
    # NBSP + diverse Spaces
    **{ord(c): " " for c in " \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000"},
    # Zero-width / Joiners / Word joiner / LRM/RLM
    ord("\u200B"): None,  # ZWSP
    ord("\u200C"): None,  # ZWNJ
    ord("\u200D"): None,  # ZWJ
    ord("\u2060"): None,  # WJ
    ord("\u200E"): None,  # LRM
    ord("\u200F"): None,  # RLM
}

def normalize_unicode_spaces(s: str) -> str:
    return s.translate(SPACE_MAP)

def sanitize_all(s: str) -> str:
    if not s:
        return s
    s = s.replace(BOM, "")
    s = CTRL_RE.sub(" ", s)
    s = s.replace("\r\n", "\n")
    s = normalize_unicode_spaces(s)
    return s

def ensure_frontmatter_starts_at_col1(s: str) -> str:
    # Alles vor erstem ---\n (inkl. Unicode-Leerzeichen) entfernen
    m = re.search(r'(?m)^[ \t\u00A0\u1680\u2000-\u200B\u202F\u205F\u3000]*---\n', s)
    if not m:
        return s
    return s[m.start():]

def split_head_body(s: str):
    m = re.match(r'^---\n(.*?\n)---\n(.*)$', s, flags=re.S)
    if not m:
        return None, None, s
    return m.group(1), m.group(2), None

def detab_head(head: str) -> str:
    lines = head.split("\n")
    for i, ln in enumerate(lines):
        # führende Tabs → zwei Spaces je Tab; Unicode-Spaces sind schon normalisiert
        m = re.match(r'^(\t+)(.*)$', ln)
        if m:
            lines[i] = '  ' * len(m.group(1)) + m.group(2)
    return "\n".join(lines)

# grobe Heuristik für Key-Zeilen im YAML
KEY_LINE  = re.compile(r'^\s*[^:#\-\s][^:]*:\s*(\|[+-]?|\>|\s*[^#].*)?$')
INDENTED  = re.compile(r'^\s+')

def normalize_yaml_head(head: str):
    """Entfernt 'verirrte' Textzeilen aus YAML-Head → Body."""
    lines = head.split("\n")
    fixed, stray = [], []
    in_block = False
    for ln in lines:
        if in_block:
            fixed.append(ln)
            if not INDENTED.match(ln) and ln.strip() != "":
                in_block = False
            continue
        if KEY_LINE.match(ln) or ln.strip().startswith("#") or ln.strip() == "":
            fixed.append(ln)
            if ln.strip().endswith(("|", "|-", "|+", ">")):
                in_block = True
        else:
            stray.append(ln.strip())
    fixed_head = "\n".join(fixed).strip("\n") + "\n"
    return fixed_head, [x for x in stray if x]

def pull_last_sync_into_head(head: str, body: str):
    ms = re.search(r'^\s*last_sync:\s*".*?"\s*$', body, flags=re.M)
    if ms and "last_sync:" not in head:
        head = head.rstrip("\n") + "\n" + ms.group(0) + "\n"
        body = body[:ms.start()] + ms.string[ms.end():]
    return head, body

def fix_file(p: Path) -> bool:
    raw = p.read_text(encoding="utf-8", errors="replace")
    s = sanitize_all(raw)
    s = ensure_frontmatter_starts_at_col1(s)

    head, body, fallback = split_head_body(s)
    if fallback is not None:
        # keine klassische Frontmatter
        if s != raw:
            p.write_text(s, encoding="utf-8"); print(f"[FIX] {p} (sanitize only)")
            return True
        return False

    head = detab_head(head)
    head, stray = normalize_yaml_head(head)
    if stray:
        body = ("\n".join(stray) + "\n\n" + body.lstrip())

    head, body = pull_last_sync_into_head(head, body)

    fixed = f"---\n{head}---\n{body.lstrip()}"
    if fixed != raw:
        p.write_text(fixed, encoding="utf-8"); print(f"[FIX] {p}")
        return True
    return False

def main():
    changed = 0
    for f in CONTENT.rglob("*.md"):
        try:
            if fix_file(f):
                changed += 1
        except Exception as e:
            print(f"[WARN] {f}: {e}", file=sys.stderr)
    print(f"✓ repariert: {changed} Dateien")
    return 0

if __name__ == "__main__":
    sys.exit(main())
