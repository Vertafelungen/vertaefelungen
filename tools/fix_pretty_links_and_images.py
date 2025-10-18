
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_pretty_links_and_images.py
Version: v2025-10-18-1

Zweck
-----
- Ersetzt interne Markdown-Links auf *.md durch Pretty-URLs ("/name/")
- Repariert Bild-Referenzen vom Muster "<code>-1.ext" -> "<code>-01.ext",
  wenn die 2-stellige Datei existiert (z. B. s10004-1.png -> s10004-01.png).
- Arbeitet standardmäßig unter "wissen/content/de/oeffentlich/produkte/leisten",
  kann aber auf jeden Content-Pfad angewandt werden.

Verwendung
----------
# Dry-Run (nur Bericht):
python tools/fix_pretty_links_and_images.py --root "wissen/content/de/oeffentlich/produkte/leisten"

# Anwenden:
python tools/fix_pretty_links_and_images.py --root "wissen/content/de/oeffentlich/produkte/leisten" --apply

Optionen
--------
--root (str)   : Startverzeichnis
--apply        : Änderungen schreiben (ohne: nur Dry-Run)
--report (str) : Report-Datei (Default: tools/reports/fix-links-images-<ts>.md)
"""

from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from datetime import datetime

MD_LINK_RE   = re.compile(r'(?<!\!)\[[^\]]*\]\(([^)]+)\)')  # normale Links (kein Bild: ![]())
IMG_MD_RE    = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
IMG_HTML_RE  = re.compile(r'<img[^>]*\s+src=[\"\\\']([^\"\\\']+)[\"\\\']', re.IGNORECASE)

# Codes: pNNNN, sNNNN, wNNNN (erweiterbar)
SINGLE_DIGIT_IMG_RE = re.compile(r'^(?P<code>[psw]\\d{4})-(?P<n>\\d)(?P<ext>\\.[A-Za-z0-9]+)$', re.IGNORECASE)

def is_http_like(href: str) -> bool:
    href = href.strip().lower()
    return href.startswith("http://") or href.startswith("https://")

def is_anchor(href: str) -> bool:
    return href.strip().startswith("#")

def rewrite_md_link(href: str) -> str:
    """Wandelt 'name.md' in 'name/' um (Anker/Query werden beibehalten)."""
    s = href.strip()
    if is_http_like(s) or is_anchor(s):
        return s
    # split hash/query
    q = ""
    h = ""
    if "?" in s:
        s, q = s.split("?", 1)
        q = "?" + q
    if "#" in s:
        s, h = s.split("#", 1)
        h = "#" + h
    if s.lower().endswith(".md"):
        s = s[:-3]  # ohne .md
        if not s.endswith("/"):
            s = s + "/"
    return s + q + h

def normalize_single_digit_image(ref: str, page_dir: Path) -> tuple[str, list[str]]:
    """Falls ref 'code-1.ext' ist und 'code-01.ext' existiert, liefere neue Ref + Hinweis."""
    notes = []
    s = ref.strip()
    # absolute root-pfade nicht anfassen
    if s.startswith("/") or is_http_like(s):
        return s, notes
    m = SINGLE_DIGIT_IMG_RE.match(s)
    if not m:
        return s, notes
    code = m.group("code")
    n = m.group("n")
    ext = m.group("ext")
    if len(n) == 1:
        candidate = f"{code}-{int(n):02d}{ext.lower()}"
        cand_path = (page_dir / candidate).resolve()
        if cand_path.exists():
            notes.append(f"Bild-Ref aktualisiert: {s} -> {candidate}")
            return candidate, notes
    return s, notes

def process_file(md_path: Path) -> tuple[bool, str, list[str]]:
    """Liest md, rewritet Links & Bilder. Liefert (changed, new_text, notes)."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    notes: list[str] = []
    changed = False

    # 1) Markdown-Links auf .md -> Pretty
    def _md_link_repl(m):
        href = m.group(1)
        new = rewrite_md_link(href)
        nonlocal changed
        if new != href:
            changed = True
            notes.append(f"Link: {href} -> {new}")
        return m.group(0).replace(href, new, 1)

    text2 = MD_LINK_RE.sub(_md_link_repl, text)

    # 2) Bild-Refs: Markdown
    page_dir = md_path.parent
    def _img_md_repl(m):
        ref = m.group(1)
        new, ns = normalize_single_digit_image(ref, page_dir)
        nonlocal changed
        if ns:
            changed = True
            notes.extend(ns)
        return m.group(0).replace(ref, new, 1)

    text3 = IMG_MD_RE.sub(_img_md_repl, text2)

    # 3) Bild-Refs: HTML <img src="...">
    def _img_html_repl(m):
        ref = m.group(1)
        new, ns = normalize_single_digit_image(ref, page_dir)
        nonlocal changed
        if ns:
            changed = True
            notes.extend(ns)
        return m.group(0).replace(ref, new, 1)

    text4 = IMG_HTML_RE.sub(_img_html_repl, text3)

    return changed, text4, notes

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="z. B. wissen/content/de/oeffentlich/produkte/leisten")
    ap.add_argument("--apply", action="store_true", help="Änderungen schreiben (ohne: Dry-Run)")
    ap.add_argument("--report", default=None, help="Report-Datei (Markdown)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        sys.exit(1)

    md_files = [p for p in root.rglob("*.md") if p.is_file()]
    total = len(md_files)
    changes = 0
    report_lines = []
    report_lines.append(f"# Fix Report – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append(f"- Root: `{root}`")
    report_lines.append(f"- Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    report_lines.append(f"- Dateien: {total}")
    report_lines.append("")

    for md in sorted(md_files, key=lambda p: str(p).lower()):
        changed, new_text, notes = process_file(md)
        if changed:
            changes += 1
            report_lines.append(f"## {md}")
            for n in notes:
                report_lines.append(f"- {n}")
            report_lines.append("")
            if args.apply:
                md.write_text(new_text, encoding="utf-8")

    report_lines.append("")
    report_lines.append(f"**Summary:** {changes} / {total} Dateien geändert.")

    # Report-Datei
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = Path(args.report) if args.report else Path("tools/reports") / f"fix-links-images-{ts}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report: {report_path}")
    print(f"Changed files: {changes}/{total}")

if __name__ == "__main__":
    main()
