#!/usr/bin/env python3
# Version: 2025-10-07 14:05 Europe/Berlin
"""
Smoke-Check für den Hugo-Build.
STRICT_SMOKE=1 prüft zusätzlich BOM/Steuerzeichen und Frontmatter.
"""
from __future__ import annotations
import argparse, os, sys, re
from pathlib import Path

CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.I) is not None

def check_markdown_frontmatter(content: str) -> bool:
    # sehr einfache Frontmatter-Prüfung
    if content.startswith("\ufeff"):
        return False
    if not content.startswith("---"):
        return False
    if CTRL_RE.search(content[:1000]):  # nur im Kopf scannen
        return False
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-dir", default="wissen/public")
    ap.add_argument("--min-files", type=int, default=25)
    a = ap.parse_args()
    strict = os.getenv("STRICT_SMOKE", "") not in ("", "0", "false", "False")

    pub = Path(a.public_dir).resolve()
    need = [pub / "de" / "index.html", pub / "en" / "index.html", pub / "sitemap.xml", pub / "robots.txt"]
    missing = [p for p in [pub] + need if not p.exists()]
    if missing:
        for m in missing: print(f"[SMOKE] fehlt: {m}", file=sys.stderr)
        sys.exit(2)

    cnt = sum(1 for _ in pub.rglob("*") if _.is_file())
    if cnt < a.min_files:
        print(f"[SMOKE] zu wenige Dateien: {cnt} < {a.min_files}", file=sys.stderr); sys.exit(2)

    de = read_text(pub / "de" / "index.html")
    en = read_text(pub / "en" / "index.html")
    if "�" in de or "�" in en:
        print(f"[SMOKE] Encoding-Fehlerzeichen in /de/ oder /en/", file=sys.stderr); sys.exit(3)

    if strict:
        # Check canonical/hreflang
        for page, txt in (("de", de), ("en", en)):
            if not has(r'rel=["\']canonical["\']', txt):
                print(f"[SMOKE] canonical fehlt auf /{page}/", file=sys.stderr); sys.exit(3)
            if not (has(r'hreflang=["\']de["\']', txt) and has(r'hreflang=["\']en["\']', txt)):
                print(f"[SMOKE] hreflang fehlt/ist unvollständig auf /{page}/", file=sys.stderr); sys.exit(3)
        # Grober Scan aller Markdown-Dateien, um zukünftige BOM/Steuerzeichen zu fangen
        content_root = Path(__file__).resolve().parents[1] / "content"
        bad = []
        for md in content_root.rglob("*.md"):
            head = md.read_text(encoding="utf-8", errors="replace")[:1200]
            if not check_markdown_frontmatter(head):
                bad.append(str(md))
        if bad:
            print("[SMOKE] Ungültige Frontmatter/BOM in:", file=sys.stderr)
            for b in bad: print(" -", b, file=sys.stderr)
            sys.exit(3)

    robots = read_text(pub / "robots.txt")
    if "Sitemap:" not in robots:
        print("[SMOKE] robots.txt ohne Sitemap-Zeile", file=sys.stderr); sys.exit(3)

    print(f"[SMOKE] OK – {cnt} Dateien (strict={int(strict)}).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
