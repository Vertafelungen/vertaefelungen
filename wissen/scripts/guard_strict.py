#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Strikter Content-Guard:
- findet alle index.md unter wissen/content/** und prüft:
  * Frontmatter vorhanden (--- / ---)
  * YAML parsebar, UTF-8 ohne BOM
  * Pflichtfelder: title, slug, type=="produkte"
  * Verbotene Zeichen: NBSP, ZWSP, CP-1252-Ctrl (#x80-#x9F)
  * Typen: price_cents:int?, in_stock:bool?
"""

import sys
import re
from pathlib import Path
from ruamel.yaml import YAML

ROOT = Path("wissen/content")
FORBIDDEN = re.compile(r"[\u0080-\u009f\u00a0\u200b\u200c\u200d]")  # CP-1252 ctrl, NBSP, ZW

def fail(msg):
    print(f"[ERR] {msg}")
    sys.exit(2)

def warn(msg):
    print(f"[WARN] {msg}")

def check_file(p: Path):
    txt = p.read_text(encoding="utf-8")
    if FORBIDDEN.search(txt):
        fail(f"{p}: verbotene Sonderzeichen (CP-1252/NBSP/ZW) gefunden.")

    # Frontmatter extrahieren
    if not txt.startswith("---"):
        fail(f"{p}: Frontmatter muss mit '---' beginnen.")
    parts = txt.split("\n---", 2)
    if len(parts) < 2:
        fail(f"{p}: Ende von Frontmatter '---' fehlt.")

    header = parts[0] + "\n---"
    body = parts[1]

    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        fm = yaml.load(txt.split("---", 2)[1])
    except Exception as e:
        fail(f"{p}: YAML-Parsing fehlgeschlagen: {e}")

    # Pflichtfelder
    title = fm.get("title")
    slug  = fm.get("slug")
    ctype = fm.get("type")

    if not isinstance(title, str) or not title.strip():
        fail(f"{p}: Pflichtfeld 'title' fehlt/leer.")
    if not isinstance(slug, str) or not slug.strip():
        fail(f"{p}: Pflichtfeld 'slug' fehlt/leer.")
    if ctype != "produkte":
        fail(f"{p}: Feld 'type' muss 'produkte' sein.")

    # Typen
    if "price_cents" in fm and not isinstance(fm["price_cents"], int):
        fail(f"{p}: 'price_cents' muss Integer sein (Cent).")
    if "in_stock" in fm and not isinstance(fm["in_stock"], bool):
        fail(f"{p}: 'in_stock' muss boolean sein.")

def main():
    if not ROOT.exists():
        print("[guard] kein content-Verzeichnis gefunden, überspringe.")
        return 0

    files = sorted(ROOT.rglob("index.md"))
    if not files:
        print("[guard] keine index.md-Dateien gefunden.")
        return 0

    for p in files:
        check_file(p)

    print("[guard] OK – alle Dateien bestanden.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
