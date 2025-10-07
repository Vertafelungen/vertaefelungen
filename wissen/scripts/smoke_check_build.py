#!/usr/bin/env python3
# smoke_check_build.py
# Version: 2025-10-07 14:40 Europe/Berlin
"""
Smoke-Check für den Hugo-Build der Wissensseite.

Prüft:
- Pflichtdateien: public/de/index.html, public/en/index.html, public/sitemap.xml
- Mindest-Dateianzahl
- Encoding (kein �)
- <link rel="canonical"> auf /de/ und /en/
- hreflang-Alternates auf /de/ und /en/
- Sitemap: urlset-Namespaces, xhtml:link Support, mindestens eine DE- und EN-URL

Exitcodes:
0 = OK
2 = Pflichtdatei fehlt / zu wenige Dateien
3 = Inhaltliche Fehler (Encoding/canonical/hreflang/Sitemap)
"""

from __future__ import annotations
import argparse, sys, re
from pathlib import Path

def read_text(p: Path) -> str:
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
    args = ap.parse_args()

    pub = Path(args.public_dir).resolve()
    need = [pub / "de" / "index.html", pub / "en" / "index.html", pub / "sitemap.xml"]
    missing = [p for p in need if not p.exists()]
    if not pub.exists():
        print(f"[SMOKE] fehlt: {pub}", file=sys.stderr)
        sys.exit(2)
    if missing:
        for m in missing:
            print(f"[SMOKE] fehlt: {m}", file=sys.stderr)
        sys.exit(2)

    # Dateianzahl
    cnt = sum(1 for _ in pub.rglob("*") if _.is_file())
    if cnt < args.min_files:
        print(f"[SMOKE] zu wenige Dateien: {cnt} < {args.min_files}", file=sys.stderr)
        sys.exit(2)

    # Seiten laden
    de = read_text(pub / "de" / "index.html")
    en = read_text(pub / "en" / "index.html")

    # Encoding
    if "�" in de or "�" in en:
        print("[SMOKE] Encoding-Fehlerzeichen in /de/ oder /en/ gefunden.", file=sys.stderr)
        sys.exit(3)

    # canonical vorhanden?
    if not has(r'rel=["\']canonical["\']', de) or not has(r'rel=["\']canonical["\']', en):
        print("[SMOKE] canonical-Link fehlt auf /de/ oder /en/.", file=sys.stderr)
        sys.exit(3)

    # hreflang vorhanden (de & en auf beiden Startseiten)
    if not (has(r'hreflang=["\']de["\']', de) and has(r'hreflang=["\']en["\']', de)):
        print("[SMOKE] hreflang-Links fehlen auf /de/.", file=sys.stderr)
        sys.exit(3)
    if not (has(r'hreflang=["\']de["\']', en) and has(r'hreflang=["\']en["\']', en)):
        print("[SMOKE] hreflang-Links fehlen auf /en/.", file=sys.stderr)
        sys.exit(3)

    # Sitemap prüfen
    sm = read_text(pub / "sitemap.xml")
    # Grundstruktur + Namespace
    if not has(r'<urlset[^>]+sitemaps\.org/schemas/sitemap/0\.9', sm):
        print("[SMOKE] Sitemap ohne urlset-Standard-Namespace.", file=sys.stderr)
        sys.exit(3)
    # xhtml-Alternate Namespace (für hreflang-Verweise)
    if not has(r'xmlns:xhtml=["\']http://www\.w3\.org/1999/xhtml["\']', sm):
        print("[SMOKE] Sitemap ohne xmlns:xhtml (hreflang-Alternates fehlen?).", file=sys.stderr)
        sys.exit(3)
    # Mindestens eine DE- und EN-URL
    if "/de/" not in sm or "/en/" not in sm:
        print("[SMOKE] Sitemap enthält nicht sowohl /de/ als auch /en/ URLs.", file=sys.stderr)
        sys.exit(3)

    # WARNUNG (nicht fatal): Unterordner-Robots entdeckt?
    robots_sub = pub / "robots.txt"
    if robots_sub.exists():
        print("[SMOKE][WARN] /wissen/robots.txt gefunden. Crawler werten nur /robots.txt am Domain-Root aus.")

    print(f"[SMOKE] OK – {cnt} Dateien, Sitemap & Meta-Checks bestanden.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
