#!/usr/bin/env python3
# Version: 2025-10-07 16:30 Europe/Berlin
# Robuster Frontmatter-Fixer:
# - entfernt BOM/Control/Zero-Width
# - normalisiert NBSP und exotische Spaces
# - entfernt LSEP/PSEP
# - rückt Tabs in YAML auf Spaces um
# - zieht verirrte Textzeilen aus YAML in den Body
# - sorgt dafür, dass die Frontmatter bei Spalte 1 beginnt
from __future__ import annotations
from pathlib import Path
import re, sys, unicodedata

ROOT    = Path(__file__).resolve().parents[1]  # .../wissen
CONTENT = ROOT / "content"

# Control-Chars (ohne TAB), BOM
CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
BOM     = "\ufeff"

# Unicode-Sonderzeichen normalisieren:
SPACE_MAP = {
    # Alle gängigen Space-Varianten -> normales Leerzeichen
    **{ord(c): " " for c in " \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000"},
    # Zero-width & Markierungen entfernen
    ord("\u200B"): None,  # ZWSP
    ord("\u200C"): None,  # ZWNJ
    ord("\u200D"): None,  # ZWJ
    ord("\u2060"): None,  # WJ
    ord("\u200E"): None,  # LRM
    ord("\u200F"): None,  # RLM
    # Line/Paragraph Separator -> Space (YAML mag die nicht)
    ord("\u2028"): " ",   # LSEP
    ord("\u2029"): " ",   # PSEP
}

def normalize_unicode(s: str) -> str:
    # NFKC vereinheitlicht typografische Varianten (z. B. „ﬁ“)
    return unicodedata.normalize("NFKC", s).translate(SPACE_MAP)

def sanitize_all(s: str) -> str:
    if not s:
        return s
    s = s.replace(BOM, "")
    s = CTRL_RE.sub(" ", s)
    s = s.replace("\r\n", "\n")
    s = normalize_unicode(s)
    return s

def ensure_frontmatter_starts_at_col1(s: str) -> str:
    # Alles vor erstem ---\n (inkl. Unicode-Spaces) entfernen
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
    # Führende Tabs im YAML-Kopf → zwei Spaces je Tab
    return re.sub(r'^\t+', lambda m: "  " * len(m.group(0)), head, flags=re.M)

# Erlaubte Key-Zeilen und Block/Liste erkennen
KEY_LINE  = re.compile(r'^\s*[^:#\-\s][^:]*:\s*(\|[+-]?|\>|[^\#].*)?$')
LIST_ITEM = re.compile(r'^\s*-\s+.*$')
INDENTED  = re.compile(r'^\s+')

def normalize_yaml_head(head: str):
    """
    Entfernt 'verirrte' reine Textzeilen aus dem YAML-Head → Body.
    Gibt (fixed_head, stray_lines) zurück.
    """
    lines = head.split("\n")
    fixed, stray = [], []
    in_block = False
    for ln in lines:
        if in_block:
            fixed.append(ln)
            if not INDENTED.match(ln) and ln.strip() != "":
                in_block = False
            continue
        if ln.strip() == "" or ln.lstrip().startswith("#"):
            fixed.append(ln); continue
        if KEY_LINE.match(ln):
            fixed.append(ln)
            if ln.rstrip().endswith(("|", "|-", "|+", ">")):
                in_block = True
            continue
        if LIST_ITEM.match(ln):
            fixed.append(ln); continue
        # sonst: verirrter Text
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
        if s != raw:
            p.write_text(s, encoding="utf-8"); print(f"[FIX] {p} (sanitize only)")
            return True
        return False

    head = sanitize_all(head)
    head = detab_head(head)
    head, stray = normalize_yaml_head(head)
    if stray:
        body = ("\n".join(stray) + "\n\n" + body.lstrip())

    head, body = pull_last_sync_into_head(head, body)

    fixed = f"---\n{head}---\n{body.lstrip()}"
    if fixed != raw:
        p.write_text(fixed, encoding="utf-8")
        print(f"[FIX] {p}")
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
