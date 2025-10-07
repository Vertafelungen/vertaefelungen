#!/usr/bin/env python3
"""
Smoke-Check für den Hugo-Build der Wissensseite.

Prüft minimal:
- existiert <public>/de/index.html und <public>/en/index.html?
- existiert <public>/sitemap.xml?
- keine offensichtlichen UTF-8-Fehler (�) in den Startseiten
- mindestens N Dateien generiert

Exitcode:
  0 = ok  |  2 = fehlende Pflichtdateien  |  3 = Encoding-/Inhaltsfehler
"""

from __future__ import annotations
import argparse, sys
from pathlib import Path

def read_text_safely(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="strict")
    except Exception:
        # Fallback, falls Encoding schief ist – wir wollen es erkennen:
        return p.read_text(encoding="utf-8", errors="replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-dir", default="wissen/public", help="Pfad zum Hugo-Ausgabeverzeichnis")
    ap.add_argument("--min-files", type=int, default=25, help="Minimal erwartete Dateianzahl")
    args = ap.parse_args()

    pub = Path(args.public_dir).resolve()
    de_idx = pub / "de" / "index.html"
    en_idx = pub / "en" / "index.html"
    sitemap = pub / "sitemap.xml"

    missing = [p for p in (pub, de_idx, en_idx, sitemap) if not p.exists()]
    if missing:
        for m in missing:
            print(f"[SMOKE] fehlt: {m}", file=sys.stderr)
        sys.exit(2)

    # Sehr grobe Plausibilität: genug Dateien?
    file_count = sum(1 for _ in pub.rglob("*") if _.is_file())
    if file_count < args.min_files:
        print(f"[SMOKE] zu wenige Dateien im Build: {file_count} < {args.min_files}", file=sys.stderr)
        sys.exit(2)

    # Encoding-Quickcheck auf den Startseiten
    for p in (de_idx, en_idx):
        txt = read_text_safely(p)
        if "�" in txt:
            print(f"[SMOKE] Encoding-Fehlerzeichen in: {p}", file=sys.stderr)
            sys.exit(3)

    print(f"[SMOKE] OK – {file_count} Dateien, Startseiten + sitemap vorhanden.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
