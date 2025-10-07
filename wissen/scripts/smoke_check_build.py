#!/usr/bin/env python3
# Version: 2025-10-07 13:45 Europe/Berlin
"""
Smoke-Check für den Hugo-Build der Wissensseite.
Prüft: public/de/index.html, public/en/index.html, public/sitemap.xml, public/robots.txt,
kein �, min. Dateizahl, canonical und hreflang.
Exitcodes: 0 ok | 2 Pflichtdatei fehlt | 3 Encoding-/Inhaltsfehler
"""
from __future__ import annotations
import argparse, sys, re
from pathlib import Path

def read_text_safely(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="strict")
    except Exception:
        return p.read_text(encoding="utf-8", errors="replace")

def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.I) is not None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-dir", default="wissen/public")
    ap.add_argument("--min-files", type=int, default=25)
    a = ap.parse_args()

    pub = Path(a.public_dir).resolve()
    need = [pub / "de" / "index.html", pub / "en" / "index.html", pub / "sitemap.xml", pub / "robots.txt"]
    missing = [p for p in [pub] + need if not p.exists()]
    if missing:
        for m in missing: print(f"[SMOKE] fehlt: {m}", file=sys.stderr)
        sys.exit(2)

    cnt = sum(1 for _ in pub.rglob("*") if _.is_file())
    if cnt < a.min_files:
        print(f"[SMOKE] zu wenige Dateien: {cnt} < {a.min_files}", file=sys.stderr); sys.exit(2)

    de = read_text_safely(pub / "de" / "index.html")
    en = read_text_safely(pub / "en" / "index.html")
    if "�" in de or "�" in en:
        print(f"[SMOKE] Encoding-Fehlerzeichen in /de/ oder /en/", file=sys.stderr); sys.exit(3)

    # canonical vorhanden?
    if not has(r'rel=["\']canonical["\']', de) or not has(r'rel=["\']canonical["\']', en):
        print("[SMOKE] canonical-Link fehlt auf /de/ oder /en/", file=sys.stderr); sys.exit(3)

    # hreflang vorhanden?
    if not (has(r'hreflang=["\']de["\']', de) and has(r'hreflang=["\']en["\']', de)):
        print("[SMOKE] hreflang-Links fehlen auf /de/", file=sys.stderr); sys.exit(3)
    if not (has(r'hreflang=["\']de["\']', en) and has(r'hreflang=["\']en["\']', en)):
        print("[SMOKE] hreflang-Links fehlen auf /en/", file=sys.stderr); sys.exit(3)

    robots = read_text_safely(pub / "robots.txt")
    if "Sitemap:" not in robots:
        print("[SMOKE] robots.txt ohne Sitemap-Zeilen", file=sys.stderr); sys.exit(3)

    print(f"[SMOKE] OK – {cnt} Dateien.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
