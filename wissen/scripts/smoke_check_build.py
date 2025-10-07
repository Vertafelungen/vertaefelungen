#!/usr/bin/env python3
"""
Smoke-Check für den Hugo-Build der Wissensseite.
Prüft: public/de/index.html, public/en/index.html, public/sitemap.xml, kein �, min. Dateizahl.
Exitcodes: 0 ok | 2 Pflichtdatei fehlt | 3 Encoding-/Inhaltsfehler
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

def read_text_safely(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="strict")
    except Exception:
        return p.read_text(encoding="utf-8", errors="replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-dir", default="wissen/public")
    ap.add_argument("--min-files", type=int, default=25)
    a = ap.parse_args()

    pub = Path(a.public_dir).resolve()
    need = [pub / "de" / "index.html", pub / "en" / "index.html", pub / "sitemap.xml"]
    missing = [p for p in [pub] + need if not p.exists()]
    if missing:
        for m in missing: print(f"[SMOKE] fehlt: {m}", file=sys.stderr)
        sys.exit(2)

    cnt = sum(1 for _ in pub.rglob("*") if _.is_file())
    if cnt < a.min_files:
        print(f"[SMOKE] zu wenige Dateien: {cnt} < {a.min_files}", file=sys.stderr); sys.exit(2)

    for p in need[:2]:
        if "�" in read_text_safely(p):
            print(f"[SMOKE] Encoding-Fehlerzeichen in: {p}", file=sys.stderr); sys.exit(3)

    print(f"[SMOKE] OK – {cnt} Dateien.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
