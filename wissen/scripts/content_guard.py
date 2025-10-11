#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Content Guard (strict, mit temporärer Entschärfung für Altdateien ohne Frontmatter)

Prüft alle Markdown-Dateien unter `wissen/content/**`:
- UTF-8, kein BOM, keine Zero-Width, NBSP, C0/C1 (nur Prüfen; Dateien werden nicht verändert)
- YAML-Frontmatter vorhanden & parsebar (TEMP: fehlender Frontmatter → WARN statt ERR)
- Pfad ↔ type-Konsistenz:
   * /de/oeffentlich/produkte/ oder /en/public/products/  -> type: "produkte"
   * /de/faq/ oder /en/faq/                               -> type: "faq"
- Pflichtfelder & Datentypen
- Tabs im YAML-Header verboten
- Exit 2, wenn echte Fehler (Parsing, Typ-Mismatch, Pflichtfelder etc.)

Nach der Bereinigung/ Migration kann WARN -> ERR zurückgestellt werden.
"""

from __future__ import annotations
from pathlib import Path
import re
import sys
import yaml

ROOT    = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)

BOM = "\ufeff"
NBSP = "\u00A0"
ZERO = {"\u200B","\u200C","\u200D","\u2060","\uFEFF","\u200E","\u200F"}

def normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

def find_nbsp(s: str) -> bool:
    return NBSP in s

def find_zero_width(s: str) -> bool:
    return any(z in s for z in ZERO)

def has_tabs(s: str) -> bool:
    return "\t" in s

def is_index_file(p: Path) -> bool:
    return p.name.lower() == "_index.md"

def is_product_path(p: Path) -> bool:
    s = p.as_posix()
    return "/de/oeffentlich/produkte/" in s or "/en/public/products/" in s

def is_faq_path(p: Path) -> bool:
    s = p.as_posix()
    return "/de/faq/" in s or "/en/faq/" in s

def expected_type_for(p: Path) -> str | None:
    if is_product_path(p): return "produkte"
    if is_faq_path(p):     return "faq"
    return None

KEY_LINE  = re.compile(r'^\s*[^:#\-\s][^:]*:\s*(\|[+-]?|\>|[^\#].*)?$')
LIST_ITEM = re.compile(r'^\s*-\s+.*$')

def check_yaml_shape(head: str) -> str | None:
    lines = head.splitlines()
    in_block = False
    for i, ln in enumerate(lines, 1):
        if in_block:
            if ln.strip() == "" or ln.startswith("  ") or ln.startswith("\t"):
                continue
            in_block = False
        if ln.strip() == "" or ln.lstrip().startswith("#"):
            continue
        if KEY_LINE.match(ln):
            if ln.rstrip().endswith(("|", "|-", "|+", ">",)):
                in_block = True
            continue
        if LIST_ITEM.match(ln):
            continue
        return f"YAML-Strukturfehler in Zeile {i}: '{ln[:60]}'"
    return None

def guard_file(p: Path) -> tuple[list[str], list[str]]:
    warns: list[str] = []
    errs:  list[str] = []

    try:
        raw = p.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as e:
        errs.append(f"{p}: Datei ist nicht UTF-8: {e}")
        return warns, errs

    s = normalize_newlines(raw)

    if s.startswith(BOM):
        errs.append(f"{p}: BOM gefunden – bitte ohne BOM speichern.")
    if find_nbsp(s):
        errs.append(f"{p}: NBSP (U+00A0) gefunden.")
    if find_zero_width(s):
        errs.append(f"{p}: Zero-Width-Steuerzeichen gefunden.")

    m = FM_RE.match(s)
    if not m:
        # TEMP: fehlender Frontmatter ist vorerst nur eine WARNUNG,
        # damit die Altbestände den Lauf nicht blockieren.
        if is_product_path(p) or is_faq_path(p):
            warns.append(f"{p}: Kein YAML-Frontmatter gefunden (TEMP: warn).")
        return warns, errs

    head = m.group(1)

    if has_tabs(head):
        errs.append(f"{p}: Tabs im YAML-Header – bitte nur Spaces verwenden.")

    shape_err = check_yaml_shape(head)
    if shape_err:
        errs.append(f"{p}: {shape_err}")
        return warns, errs

    try:
        fm = yaml.safe_load(head) or {}
    except Exception as e:
        errs.append(f"{p}: YAML-Parsing fehlgeschlagen: {e}")
        return warns, errs

    if not isinstance(fm, dict):
        errs.append(f"{p}: YAML-Header ist kein Mapping (dict).")
        return warns, errs

    if is_index_file(p):
        return warns, errs

    exp = expected_type_for(p)
    if exp and (fm.get("type") != exp):
        errs.append(f"{p}: Erwarte type='{exp}' für diese Pfadstruktur.")
        fm.setdefault("type", exp)

    t = fm.get("type")

    if t == "produkte":
        if not isinstance(fm.get("title"), str) or not fm.get("title"):
            errs.append(f"{p}: Pflichtfeld 'title' fehlt/ist leer.")
        if not isinstance(fm.get("slug"), str) or not fm.get("slug"):
            errs.append(f"{p}: Pflichtfeld 'slug' fehlt/ist leer.")

        if "varianten" in fm and fm["varianten"] not in (None, "", []):
            if not isinstance(fm["varianten"], list):
                errs.append(f"{p}: 'varianten' muss eine Liste sein.")

        if isinstance(fm.get("bilder"), list) and isinstance(fm.get("bilder_alt"), list):
            if len(fm["bilder"]) != len(fm["bilder_alt"]):
                errs.append(f"{p}: 'bilder' und 'bilder_alt' haben unterschiedliche Längen.")

        if "in_stock" in fm and not isinstance(fm["in_stock"], bool):
            errs.append(f"{p}: 'in_stock' muss boolean sein.")
        if "price_cents" in fm and not isinstance(fm["price_cents"], int):
            errs.append(f"{p}: 'price_cents' muss Integer (Cent) sein.")

    elif t == "faq":
        if not isinstance(fm.get("title"), str) or not fm.get("title"):
            errs.append(f"{p}: Pflichtfeld 'title' fehlt/ist leer.")
        if not isinstance(fm.get("slug"), str) or not fm.get("slug"):
            errs.append(f"{p}: Pflichtfeld 'slug' fehlt/ist leer.")

    return warns, errs

def main() -> int:
    all_warns: list[str] = []
    all_errs:  list[str] = []

    for p in CONTENT.rglob("*.md"):
        w, e = guard_file(p)
        all_warns.extend([f"[WARN] {x}" for x in w])
        all_errs.extend([f"[ERR]  {x}" for x in e])

    for w in all_warns:
        print(w)
    if all_errs:
        for e in all_errs:
            print(e, file=sys.stderr)
        return 2

    print("Content Guard: OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
