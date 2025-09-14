#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py
Version: 2025-09-14 08:45 (Europe/Berlin)

Zweck:
- Rendert Markdown-Dateien (de/, en/) zu HTML (site/)
- Nutzt YAML-Frontmatter (titel, description, jsonld)
- Fügt <title>, <meta name="description">, hreflang-Links und JSON-LD ein
- Erstellt fehlende Indexseiten (z. B. /wissen/de/oeffentlich/)
- Generiert sitemap.xml und robots.txt
"""

import os
import re
import json
from pathlib import Path
import markdown
import yaml

# ---------------------------
# Frontmatter-Erkennung
# ---------------------------
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

def parse_frontmatter(md_text: str):
    """Extrahiert YAML-Frontmatter und Body aus Markdown."""
    if not md_text:
        return {}, md_text
    m = FRONTMATTER_RE.match(md_text)
    if not m:
        return {}, md_text
    meta = yaml.safe_load(m.group(1)) or {}
    body = md_text[m.end():]
    return meta, body

# ---------------------------
# Helfer
# ---------------------------
def inject_head(html: str, head_snippet: str) -> str:
    """Fügt head_snippet vor </head> ein."""
    if "</head>" in html:
        return html.replace("</head>", head_snippet + "\n</head>", 1)
    if "<body" in html:
        return html.replace("<body", "<body>\n" + head_snippet + "\n", 1)
    return head_snippet + "\n" + html

def find_partner_path(out_html_path: Path) -> tuple[str, str] | None:
    """
    Sucht Pendant in anderer Sprache (de/en).
    Gibt (lang, href) zurück oder None.
    """
    parts = list(out_html_path.parts)
    if "de" in parts:
        parts[parts.index("de")] = "en"
        lang = "en"
    elif "en" in parts:
        parts[parts.index("en")] = "de"
        lang = "de"
    else:
        return None
    partner = Path(*parts)
    if partner.exists():
        href = "/" + str(partner).replace("\\", "/")
        return lang, href
    return None

def ensure_index(folder: Path, title: str = "Übersicht"):
    """Legt leere README.md an, falls Ordner keinen Index hat."""
    index_md = folder / "README.md"
    index_html = folder / "index.html"
    if not index_md.exists() and not index_html.exists():
        index_md.write_text(f"---\ntitel: {title}\n---\n\n*Inhalt folgt.*\n", encoding="utf-8")

# ---------------------------
# Render-Prozess
# ---------------------------
def render_markdown(md_path: Path, out_path: Path):
    """Rendert eine einzelne Markdown-Datei zu HTML mit Frontmatter."""
    md_source = md_path.read_text(encoding="utf-8")
    meta, md_body = parse_frontmatter(md_source)
    html_body = markdown.markdown(md_body, extensions=["tables", "fenced_code"])

    # Kopf-Bausteine
    head_parts = []
    page_title = meta.get("titel") or meta.get("title") or "Vertäfelungen Wissen"
    page_desc  = meta.get("description") or meta.get("beschreibung") or ""

    head_parts.append(f"<title>{page_title}</title>")
    if page_desc:
        head_parts.append(f'<meta name="description" content="{page_desc}">')

    # hreflang
    partner = find_partner_path(out_path)
    if partner:
        plang, phref = partner
        head_parts.append(f'<link rel="alternate" hreflang="{plang}" href="{phref}">')

    # JSON-LD
    if "jsonld" in meta:
        try:
            jsonld_str = json.dumps(meta["jsonld"], ensure_ascii=False)
            head_parts.append(f'<script type="application/ld+json">{jsonld_str}</script>')
        except Exception as e:
            print(f"⚠️ Fehler in JSON-LD bei {md_path}: {e}")

    head_snippet = "\n".join(head_parts)
    final_html = inject_head(html_body, head_snippet)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_html, encoding="utf-8")
    print(f"✅ gebaut: {out_path}")

# ---------------------------
# Sitemap & Robots
# ---------------------------
def generate_sitemap(site_root: Path, base_url: str):
    urls = []
    for html_file in site_root.rglob("*.html"):
        rel_path = html_file.relative_to(site_root)
        url = base_url.rstrip("/") + "/" + str(rel_path).replace("\\", "/")
        urls.append(url)

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in sorted(urls):
        sitemap += f"  <url><loc>{u}</loc></url>\n"
    sitemap += "</urlset>\n"

    (site_root / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (site_root / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {base_url.rstrip('/')}/sitemap.xml\n",
        encoding="utf-8"
    )
    print("✅ sitemap.xml & robots.txt erzeugt")

# ---------------------------
# Main
# ---------------------------
def main(content_root=".", out_dir="site", base_url="https://www.vertaefelungen.de/wissen"):
    content_root = Path(content_root)
    out_dir = Path(out_dir)

    for lang in ["de", "en"]:
        for md_file in (content_root / lang).rglob("*.md"):
            rel = md_file.relative_to(content_root)
            out_html = out_dir / rel.with_suffix(".html")
            render_markdown(md_file, out_html)

        # Indexseiten für Oberordner erzeugen
        ensure_index(content_root / lang / "oeffentlich", "Öffentlich")
        ensure_index(content_root / lang / "produkte", "Produkte")

    # Sitemap/Robots erzeugen
    generate_sitemap(out_dir, base_url)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--content-root", default=".")
    p.add_argument("--out-dir", default="site")
    p.add_argument("--base-url", default="https://www.vertaefelungen.de/wissen")
    args = p.parse_args()
    main(args.content_root, args.out_dir, args.base_url)
