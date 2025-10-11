#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Einfacher Post-Build Smoke-Test für den Hugo-Output.

Prüft:
- Verzeichnis existiert
- Mindestens N HTML-Dateien (Default 25) → --min-files 25
- sitemap.xml vorhanden
- (Optional) Mindestens eine Produktseite (de/en) existiert
- (Optional) In einigen Produktseiten kommt JSON-LD vor

Beendet sich mit Exit 2 bei Fehler.
"""

from __future__ import annotations
from pathlib import Path
import argparse
import sys

def find_files(base: Path, pattern: str):
    return list(base.rglob(pattern))

def has_ld_json(html_path: Path) -> bool:
    try:
        txt = html_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return '<script type="application/ld+json">' in txt

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-dir", default="wissen/public", help="Pfad zum Hugo-Output")
    ap.add_argument("--min-files", type=int, default=25, help="Mindestanzahl .html Dateien")
    args = ap.parse_args()

    public = Path(args.public_dir)
    if not public.exists():
        print(f"[ERR] Output-Verzeichnis existiert nicht: {public}", file=sys.stderr)
        return 2

    html_files = find_files(public, "*.html")
    if len(html_files) < args.min_files:
        print(f"[ERR] Zuwenig HTML-Dateien ({len(html_files)} < {args.min_files}).", file=sys.stderr)
        return 2

    # sitemap
    if not (public / "sitemap.xml").exists():
        print("[ERR] sitemap.xml fehlt.", file=sys.stderr)
        return 2

    # Produktseiten prüfen (optional, nur warnen, wenn nicht vorhanden)
    prod_de = find_files(public / "de" / "oeffentlich" / "produkte", "index.html")
    prod_en = find_files(public / "en" / "public" / "products", "index.html")
    if not prod_de and not prod_en:
        print("[WARN] Keine Produktseiten gefunden (de/en).")

    # JSON-LD (optional, nur warnen)
    sample_pages = (prod_de[:3] + prod_en[:2])[:5]
    if sample_pages:
        pages_with_ld = sum(1 for p in sample_pages if has_ld_json(p))
        if pages_with_ld == 0:
            print("[WARN] In den Stichproben wurde kein JSON-LD gefunden.")

    print(f"Smoke-Check OK – HTML: {len(html_files)}, Produkte: de={len(prod_de)}, en={len(prod_en)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
