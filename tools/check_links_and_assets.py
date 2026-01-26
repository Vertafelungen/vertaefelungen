#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_links_and_assets.py
Version: v2025-10-18-1
Prüft Content auf:
- verbotene Links (*.md, localhost)
- Bild-Existenz gem. Frontmatter-Feld 'bilder_liste' (kommagetrennt)

Benötigt: PyYAML
pip install pyyaml
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

CONTENT_ROOTS = [
    Path("wissen/content/de"),
    Path("wissen/content/en"),
]

BAD_LINK_MD = re.compile(r'\[[^\]]*\]\([^\)]*\.md(\#[^\)]*)?\)', re.IGNORECASE)
BAD_LINK_LOCALHOST = re.compile(r'localhost:\d{0,5}', re.IGNORECASE)
REF_SHORTCODE = re.compile(r'{{<\s*(?:relref|ref)\s+["\']([^"\']+)["\']\s*>}}')

def parse_frontmatter(p: Path):
    text = p.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return {}, text
    front = parts[0].lstrip("-").strip()
    body = parts[1]
    data = {}
    try:
        data = yaml.safe_load(front) or {}
    except Exception as e:
        print(f"[WARN] YAML-Frontmatter nicht lesbar: {p} ({e})")
    return data, body

def check_bilder_list(page_dir: Path, fm: dict, problems: list):
    bilder = fm.get("bilder_liste")
    if not bilder:
        return
    # erwartetes Format: "pNNNN-01.jpg,pNNNN-02.png,..." (kommagetrennt)
    names = [x.strip() for x in str(bilder).split(",") if x.strip()]
    for name in names:
        if not (page_dir / name).exists():
            problems.append(f"[BILD FEHLT] {page_dir / name}")

def ref_target_exists(root: Path, target: str) -> bool:
    clean = target.split("#", 1)[0].lstrip("/")
    if not clean:
        return False
    target_path = root / clean
    if target_path.is_file():
        return True
    if (target_path / "_index.md").exists():
        return True
    return False

def main():
    problems = []

    for root in CONTENT_ROOTS:
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            fm, body = parse_frontmatter(md)
            # verbotene Links
            for m in BAD_LINK_MD.finditer(body):
                problems.append(f"[BAD LINK .md] {md}: {m.group(0)}")
            for m in BAD_LINK_LOCALHOST.finditer(body):
                problems.append(f"[BAD LINK localhost] {md}: {m.group(0)}")
            for m in REF_SHORTCODE.finditer(body):
                target = m.group(1).strip()
                if not ref_target_exists(root, target):
                    problems.append(f"[REF NOT FOUND] {md}: {target}")
            # bilder_liste prüfen
            check_bilder_list(md.parent, fm, problems)

    if problems:
        print("SANITY-CHECK PROBLEME:")
        for p in problems:
            print(" -", p)
        sys.exit(2)
    else:
        print("SANITY-CHECK OK")
        sys.exit(0)

if __name__ == "__main__":
    main()
