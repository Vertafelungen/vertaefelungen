#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
normalize_yaml_values.py
- Sanitizes and normalizes YAML frontmatter in Markdown files.
- Quotes risky string values, coerces typed fields, removes NBSP/ZeroWidth etc.
- Works for both DE (oeffentlich/produkte/…) and EN (public/products/…).
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # → repo root
CONTENT_DIR = ROOT / "wissen" / "content"

# Files to touch: index.md der Produktseiten + evtl. Einzeldateien (sl0001.md etc.)
GLOBS = [
    "**/produkte/**/index.md",   # DE
    "**/products/**/index.md",   # EN
    "**/produkte/**/sl*.md",     # DE Einzeldateien (falls vorhanden)
    "**/products/**/sl*.md",     # EN Einzeldateien (falls vorhanden)
]

# Characters to remove / normalize
NBSP = "\u00A0"
ZWSP = "\u200B"
ZWNJ = "\u200C"
ZWJ  = "\u200D"
BOM  = "\uFEFF"
SMARTS = {
    "\u201C": '"',  # left double smart quote
    "\u201D": '"',  # right double smart quote
    "\u2018": "'",  # left single smart quote
    "\u2019": "'",  # right single smart quote
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
}

BOOL_KEYS  = {"in_stock", "in_stock_de", "in_stock_en", "verfuegbar", "available"}
INT_KEYS   = {"price_cents", "preis_cents", "preis_cent", "preis_in_cent", "price_in_cents"}
ALWAYS_QUOTE_KEYS = {
    # häufig problematische Textfelder
    "title", "titel", "meta_title", "meta_titel",
    "description", "beschreibung", "meta_description", "meta_beschreibung",
    "meta_desc", "meta_description_en", "meta_description_de",
    "kategorie", "category",
    "slug", "reference", "produkt_id", "product_id",
    "bilder", "alt", "image_alt",
}

HEADER_RE = re.compile(r"^---\s*$", re.MULTILINE)


def sanitize_text(s: str) -> str:
    if not s:
        return s
    s = s.replace(NBSP, " ").replace(BOM, "")
    for ch in (ZWSP, ZWNJ, ZWJ):
        s = s.replace(ch, "")
    for bad, good in SMARTS.items():
        s = s.replace(bad, good)
    return s


def split_frontmatter(text: str):
    """
    returns (fm, body, ok)
    """
    m = list(HEADER_RE.finditer(text))
    if len(m) >= 2 and m[0].start() == 0:
        fm = text[m[0].end(): m[1].start()]
        body = text[m[1].end():]
        return fm, body, True
    # kein oder offener Header → versuchen zu retten
    # ersetze evtl. "***" als Start durch "---"
    if text.startswith("***"):
        text = "---" + text[3:]
        m = list(HEADER_RE.finditer(text))
        if len(m) >= 2 and m[0].start() == 0:
            fm = text[m[0].end(): m[1].start()]
            body = text[m[1].end():]
            return fm, body, True
    return "", text, False


KV_RE = re.compile(r"^\s*([A-Za-z0-9_\-\.]+)\s*:\s*(.*)$")


def needs_quotes(val: str) -> bool:
    t = val.strip()
    if t == "" or t.startswith(('"', "'", "[", "{", "|", ">")):
        return False  # already quoted/structured or empty
    # YAML-reservierte Zeichen/Pattern → sicherheitshalber quoten
    if ":" in t or "#" in t:
        return True
    if t.startswith(("~", "null", "Null", "NULL")):
        return True
    # führende/abschließende Spaces
    if t != t.strip():
        return True
    return False


def coerce_bool(raw: str) -> str:
    t = raw.strip().strip('"').strip("'").lower()
    if t in {"true", "yes", "ja", "1"}:
        return "true"
    if t in {"false", "no", "nein", "0"}:
        return "false"
    # Unklar → lieber quoted String statt kaputtem bool
    return f'"{raw.strip()}"'


def to_cents(raw: str) -> str:
    # erlaubt: "49,75", "49.75", "49", "49 €", etc.
    t = raw.strip().strip('"').strip("'")
    # nur Ziffern, Punkt, Komma behalten
    t = re.sub(r"[^\d,\.]", "", t)
    if not t:
        return '"0"'
    # normalize: Komma als Dezimaltrennzeichen → Punkt
    if "," in t and "." not in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        euros = float(t)
        cents = int(round(euros * 100))
        return str(cents)
    except Exception:
        # lieber quoted String als kaputter Integer
        return f'"{raw.strip()}"'


def fix_key_value_line(line: str):
    m = KV_RE.match(line)
    if not m:
        return line

    key, val = m.group(1), m.group(2)
    key_l = key.lower()
    v_clean = sanitize_text(val)

    # trailing Kommentare entfernen, wenn nicht quoted
    if not v_clean.strip().startswith(('"', "'")) and " #" in v_clean:
        v_clean = v_clean.split(" #", 1)[0].rstrip()

    # Sonderfall: einzelnes öffnendes/abschließendes '…' aus Sheet
    t = v_clean.strip()
    if (t.startswith("'") and not t.endswith("'")) or (t.endswith("'") and not t.startswith("'")):
        t = t.strip("'").strip()

    # Typen coercen
    if key_l in BOOL_KEYS:
        v_final = coerce_bool(t)
    elif key_l in INT_KEYS:
        v_final = to_cents(t)
    else:
        # Strings quoten wenn nötig
        if key in ALWAYS_QUOTE_KEYS or needs_quotes(t):
            t = t.replace("\\", "\\\\").replace('"', r"\"")
            v_final = f'"{t}"'
        else:
            v_final = t

    return f"{key}: {v_final}\n"


def normalize_frontmatter(fm: str) -> str:
    out = []
    for raw in fm.splitlines(keepends=True):
        line = sanitize_text(raw.rstrip("\n"))
        if not line.strip():
            out.append("\n")
            continue
        if line.lstrip().startswith("#"):
            out.append(line + "\n")
            continue
        out.append(fix_key_value_line(line))
    return "".join(out)


def process_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = sanitize_text(text)

    fm, body, ok = split_frontmatter(text)
    if not ok:
        # kein valider Header am Anfang → nicht anfassen
        return False

    fm_norm = normalize_frontmatter(fm)

    new_text = f"---\n{fm_norm}---\n{body.lstrip()}"
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main():
    total = 0
    changed = 0
    for pattern in GLOBS:
        for p in CONTENT_DIR.glob(pattern):
            if not p.is_file():
                continue
            total += 1
            try:
                if process_file(p):
                    changed += 1
            except Exception as ex:
                print(f"[WARN] could not normalize: {p}  → {ex}", file=sys.stderr)
    print(f"[normalize_yaml_values] touched={changed} scanned={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
