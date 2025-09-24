#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py — erzeugt korrekte /wissen/index.html und bereinigt localhost-Links
Version: v2025-09-24 16:57

Was es macht:
1) Schreibt /wissen/index.html mit Redirect auf /wissen/de/
2) Legt eine minimale .htaccess in /wissen/ an (falls nicht vorhanden)
3) Entfernt im gesamten Verzeichnis /wissen/ alle Vorkommen von:
   - http://localhost:1315
   - http://127.0.0.1:1315
   - https://localhost:1315
   - https://127.0.0.1:1315
   und ersetzt sie durch leere Hostanteile (relative Pfade),
   optional wird ein vorhandenes <base href="...localhost..."> auf /wissen/ umgestellt.

Hinweis: Skript aus Repo-Root starten.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]  # Repo-Root
WISSEN = ROOT / "wissen"

INDEX_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Wissensdatenbank | Vertäfelung & Lambris</title>
  <link rel="canonical" href="/wissen/de/">
  <meta http-equiv="refresh" content="0; url=/wissen/de/">
</head>
<body>
  <p>Weiterleitung zur <a href="/wissen/de/">deutschen Übersicht</a> …</p>
</body>
</html>
""".strip() + "\n"

HTACCESS = """# /wissen/.htaccess — statische Auslieferung DE/EN
DirectoryIndex index.html index.htm
Options -Indexes

<IfModule mod_negotiation.c>
  Options -MultiViews
</IfModule>

<IfModule mod_php.c>
  php_flag engine off
</IfModule>

<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteBase /wissen/

  # Statische Dateien/Ordner direkt ausliefern
  RewriteCond %{REQUEST_FILENAME} -f [OR]
  RewriteCond %{REQUEST_FILENAME} -d
  RewriteRule . - [L]

  # /wissen -> index.html
  RewriteRule ^$ index.html [L]

  # /wissen/de -> /wissen/de/index.html (analog /en)
  RewriteRule ^(de|en)/?$ $1/index.html [L]
</IfModule>
""".strip() + "\n"


def write_index_html():
    WISSEN.mkdir(parents=True, exist_ok=True)
    (WISSEN / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    print("✓ /wissen/index.html geschrieben")


def ensure_htaccess():
    ht = WISSEN / ".htaccess"
    if not ht.exists() or ht.read_text(encoding="utf-8", errors="ignore").strip() == "":
        ht.write_text(HTACCESS, encoding="utf-8")
        print("✓ /wissen/.htaccess geschrieben")
    else:
        print("• /wissen/.htaccess vorhanden – nicht überschrieben")


def strip_localhost_links():
    # Muster für harte Dev-URLs
    host_patterns = [
        r"http://localhost:1315",
        r"https://localhost:1315",
        r"http://127\.0\.0\.1:1315",
        r"https://127\.0\.0\.1:1315",
    ]
    host_re = re.compile("|".join(host_patterns), flags=re.IGNORECASE)

    # base-Tag auf /wissen/ setzen, falls es auf localhost zeigt
    base_tag_re = re.compile(r'(<base\s+href=)["\'](.*?)["\']', flags=re.IGNORECASE)

    changed_files = 0
    for p in WISSEN.rglob("*"):
        if p.suffix.lower() in {".html", ".htm", ".xml", ".json", ".txt", ".md"} and p.is_file():
            try:
                txt = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Fallback – notfalls binär lesen und ignorieren
                try:
                    txt = p.read_text(encoding="latin-1")
                except Exception:
                    continue

            orig = txt

            # base href auf /wissen/ korrigieren, wenn es auf localhost zeigt
            def _fix_base(m):
                href = m.group(2)
                if "localhost" in href or "127.0.0.1" in href:
                    return f'{m.group(1)}"/wissen/"'
                return m.group(0)

            txt = base_tag_re.sub(_fix_base, txt)

            # localhost-Hostteile entfernen (wir wollen relative/Root-Pfade)
            txt = host_re.sub("", txt)

            if txt != orig:
                p.write_text(txt, encoding="utf-8")
                changed_files += 1

    print(f"✓ localhost-Links bereinigt in {changed_files} Datei(en)")


def main():
    write_index_html()
    ensure_htaccess()
    strip_localhost_links()
    print("Fertig.")

if __name__ == "__main__":
    main()
