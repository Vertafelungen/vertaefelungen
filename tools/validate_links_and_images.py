#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_links_and_images.py
Version: v2025-10-18-1 (Europe/Berlin)

Checks (blocking):
- Links auf .md-Dateien im Markdown (intern)  -> ERROR
- 'localhost' in Links                        -> ERROR
- Für jede Markdown-Seite:
  - Existieren referenzierte Bilder (![](pfad) und <img src="pfad">) relativ zum Seitenordner? -> ERROR bei fehlenden Dateien
  - (Optional) Warnung, wenn Bilder außerhalb des Page-Bundles referenziert werden

Nutzung:
python tools/validate_links_and_images.py --content-root "wissen/content"
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

MD_LINK_RE   = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
IMG_MD_RE    = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
IMG_HTML_RE  = re.compile(r"<img[^>]*\s+src=[\"']([^\"']+)[\"']", re.IGNORECASE)

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8", errors="replace")

def is_http_like(href: str) -> bool:
    href = href.strip().lower()
    return href.startswith("http://") or href.startswith("https://")

def is_local_ref(href: str) -> bool:
    href = href.strip().lower()
    return href.startswith("#")

def normalize_rel(href: str) -> str:
    return href.split("?")[0].split("#")[0].strip()

def collect_markdowns(root: Path) -> List[Path]:
    return [p for p in root.rglob("*.md") if p.is_file()]

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--content-root", required=True, help="z. B. wissen/content")
    args = ap.parse_args()

    content_root = Path(args.content_root).resolve()
    if not content_root.exists():
        print(f"ERROR: content-root not found: {content_root}", file=sys.stderr)
        sys.exit(1)

    errors: List[str] = []
    warnings: List[str] = []

    # Scanne alle Markdown-Seiten
    for md in collect_markdowns(content_root):
        txt = read_text(md)

        # 1) Links auf .md & localhost
        for m in MD_LINK_RE.finditer(txt):
            href = m.group(1).strip()
            if is_local_ref(href):
                continue
            low = href.lower()
            if ".md" in low:
                errors.append(f"{md}: Link auf Markdown-Datei gefunden -> {href}")
            if "localhost" in low:
                errors.append(f"{md}: Link auf localhost gefunden -> {href}")

        # 2) Bilder-Referenzen (Markdown & HTML)
        #    - Wir prüfen nur relative Pfade (keine http/https)
        img_refs: List[str] = []
        img_refs += [normalize_rel(m.group(1)) for m in IMG_MD_RE.finditer(txt)]
        img_refs += [normalize_rel(m.group(1)) for m in IMG_HTML_RE.finditer(txt)]

        page_dir = md.parent
        for ref in img_refs:
            if not ref or is_http_like(ref) or ref.startswith("/"):
                # externe oder Root-absolute Bildpfade -> Warnung (nicht blocking), da Page-Bundle empfohlen ist
                if ref.startswith("/"):
                    warnings.append(f"{md}: Root-absolute Bildreferenz -> {ref} (empfohlen: relativ im Page-Bundle)")
                continue
            img_path = (page_dir / ref).resolve()
            if not img_path.exists():
                errors.append(f"{md}: Bildreferenz nicht gefunden -> {ref}")

    # Ausgabe
    if warnings:
        print("WARNUNGEN:")
        for w in warnings:
            print(f"- {w}")
        print("")

    if errors:
        print("FEHLER:")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)

    print("OK: Link- & Bild-Validierung ohne Fehler.")

if __name__ == "__main__":
    main()
