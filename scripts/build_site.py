#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baut eine statische Site aus Markdown für /wissen und erzeugt eine Sitemap.
- README.md -> index.html im Ordner
- foo.md    -> foo/index.html (pretty URLs)
- Frontmatter (optional): title, slug, lang, description, noindex
- Fügt Canonical, JSON-LD (WebPage), Breadcrumbs hinzu
- Erzeugt Auto-Indexseiten für Ordner ohne README.md
- Schreibt site/sitemap.xml
- Schreibt zusätzlich site/.htaccess (Whitelist für sitemap.xml/robots.txt, keine Umschreibung für Dateien mit Endung)
"""

import os, sys, re, shutil, pathlib, datetime, json
from typing import Dict, Tuple, List

try:
    import yaml
except Exception:
    yaml = None

import markdown
import xml.etree.ElementTree as ET

BASE_URL     = os.environ.get("BASE_URL", "").rstrip("/")
CONTENT_ROOT = os.environ.get("CONTENT_ROOT", ".").strip().rstrip("/")
EXCLUDE_DIRS = set(filter(None, (os.environ.get("EXCLUDE_DIRS", "") or "").split()))

if not BASE_URL:
    print("ERROR: BASE_URL not set", file=sys.stderr); sys.exit(1)

ROOT = pathlib.Path(CONTENT_ROOT)
OUT  = pathlib.Path("site")
OUT.mkdir(parents=True, exist_ok=True)

STYLE_CSS = """
html,body{margin:0;padding:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif;line-height:1.6}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
.site-header{border-bottom:1px solid #e5e5e5}
.brand{font-weight:600;margin-right:20px;text-decoration:none}
.site-nav a{margin-right:12px;text-decoration:none}
.content{padding:24px 0}
.page h1{font-size:2rem;margin:0 0 1rem}
.page h2{margin-top:2rem}
.page img{max-width:100%}
.breadcrumbs{font-size:.9rem;color:#666;margin-bottom:12px}
.toc{border:1px solid #eee;padding:12px;background:#fafafa;margin:12px 0}
.dir-list ul{list-style: none;padding-left:0}
.dir-list li{margin:.35rem 0}
.dir-list a{text-decoration:none}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace}
"""

HTACCESS = """
# .htaccess im /wissen/ Ordner
DirectoryIndex index.html

<IfModule mod_rewrite.c>
RewriteEngine On
RewriteBase /wissen/

# (A) sitemap.xml & robots.txt nicht umschreiben
RewriteRule ^(sitemap\.xml|robots\.txt)$ - [L]

# (B) existierende Dateien/Ordner direkt ausliefern
RewriteCond %{REQUEST_FILENAME} -f [OR]
RewriteCond %{REQUEST_FILENAME} -d
RewriteRule ^ - [L]

# (C) keine Umschreibung für Dateien mit Endung (.xml, .css, .js, .jpg, .html, …)
RewriteCond %{REQUEST_URI} \\.[^/]+$
RewriteRule ^ - [L]

# (D) Pretty URLs
RewriteRule ^(.+?)/?$ $1/index.html [L]
</IfModule>

<IfModule mod_mime.c>
  AddType application/xml .xml
</IfModule>
"""

BASE_HTML = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="{base}/assets/style.css">
<script type="application/ld+json">
{json_ld}
</script>
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="{base}/">Vertäfelung &amp; Lambris · Wissen</a>
    <nav class="site-nav">
      <a href="{base}/">Start</a>
      <a href="{base}/de/">DE</a>
      <a href="{base}/en/">EN</a>
      <a href="https://www.vertaefelungen.de" rel="external">vertaefelungen.de</a>
    </nav>
  </div>
</header>
<main class="content wrap">
  <nav class="breadcrumbs">{breadcrumbs}</nav>
  <article class="page">
    <h1>{title}</h1>
    <div class="toc">{toc}</div>
    <div class="md">{content}</div>
  </article>
</main>
<footer class="site-footer">
  <div class="wrap">
    <p>© {year} Vertäfelung &amp; Lambris · <a href="https://www.vertaefelungen.de/de/content/2-impressum">Impressum</a> · <a href="https://www.vertaefelungen.de/de/content/7-datenschutzerklaerung">Datenschutz</a></p>
    <p>Quelle: <a href="{canonical}">{canonical}</a> · Lizenz: CC BY-NC-ND 4.0 · Autor: Vertäfelung &amp; Lambris</p>
  </div>
</footer>
</body>
</html>
"""

MD_EXT = ["extra","toc","sane_lists","smarty"]

def parse_frontmatter(text: str):
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            head = parts[0].lstrip("-").strip()
            body = parts[1]
            if yaml:
                try:
                    meta = yaml.safe_load(head) or {}
                except Exception:
                    meta = {}
            else:
                meta = {}
            return meta, body
    return {}, text

def pretty_url_for(md_rel: pathlib.Path) -> pathlib.Path:
    if md_rel.name.lower() == "readme.md":
        out_dir = OUT / md_rel.parent
        out = out_dir / "index.html"
    else:
        out_dir = OUT / md_rel.with_suffix("")
        out = out_dir / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out

def canonical_for(md_rel: pathlib.Path) -> str:
    if md_rel.name.lower() == "readme.md":
        path = md_rel.parent.as_posix().strip("/")
    else:
        path = md_rel.with_suffix("").as_posix().strip("/")
    return "/".join(s for s in [BASE_URL, path] if s)

def breadcrumbs(md_rel: pathlib.Path) -> str:
    parts = md_rel.parent.parts if md_rel.name.lower()=="readme.md" else md_rel.with_suffix("").parts
    crumbs, acc = [], []
    for seg in parts:
        acc.append(seg)
        href = "/".join([BASE_URL] + acc)
        crumbs.append(f'<a href="{href}">{seg}</a>')
    return " / ".join(crumbs) if crumbs else f'<a href="{BASE_URL}">Start</a>'

def jsonld_webpage(title, canonical, description, lang="de"):
    data = {
      "@context": "https://schema.org",
      "@type": "WebPage",
      "name": title,
      "url": canonical,
      "inLanguage": lang,
      "description": description,
      "publisher": {
        "@type": "Organization",
        "name": "Vertäfelung & Lambris",
        "url": "https://www.vertaefelungen.de"
      },
      "license": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
      "isPartOf": {
        "@type": "WebSite",
        "name": "vertaefelungen.de",
        "url": "https://www.vertaefelungen.de"
      }
    }
    return json.dumps(data, ensure_ascii=False, indent=2)

def collect_markdown(root: pathlib.Path):
    mds = []
    for p in root.rglob("*.md"):
        if any(seg in EXCLUDE_DIRS for seg in p.parts):
            continue
        mds.append(p)
    mds.sort(key=lambda x: (0 if x.name.lower()=="readme.md" else 1, x.as_posix()))
    return mds

def render_md(md_text: str):
    md = markdown.Markdown(extensions=MD_EXT, extension_configs={"toc": {"permalink": True}})
    html = md.convert(md_text)
    toc = md.toc if hasattr(md, "toc") else ""
    return html, toc

def ensure_assets():
    dst = OUT / "assets"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    for maybe in ("assets", "bilder", "images"):
        src = ROOT / maybe
        if src.exists() and src.is_dir():
            shutil.copytree(src, OUT / maybe, dirs_exist_ok=True)
    (OUT / ".htaccess").write_text(HTACCESS.strip() + "\n", encoding="utf-8")

def write_dir_autoindex(dir_path: pathlib.Path):
    rel = dir_path.relative_to(ROOT)
    out = OUT / rel / "index.html"
    if out.exists():
        return
    items = []
    for p in sorted(dir_path.iterdir()):
        if p.is_dir() and any(q.suffix==".md" for q in p.glob("*.md")):
            href = "/".join([BASE_URL] + [*p.relative_to(ROOT).parts])
            items.append(f'<li><a href="{href}/">{p.name}/</a></li>')
        elif p.suffix == ".md" and p.name.lower() != "readme.md":
            href = "/".join([BASE_URL, p.relative_to(ROOT).with_suffix("").as_posix()])
            items.append(f'<li><a href="{href}/">{p.stem}</a></li>')
    html_list = "<div class='dir-list'><ul>" + "\n".join(items) + "</ul></div>"
    title = rel.as_posix() if rel.as_posix() != "." else "Start"
    canonical = "/".join([BASE_URL, rel.as_posix().strip("/")]) if rel.as_posix()!="." else BASE_URL
    page = BASE_HTML.format(
        lang="de",
        title=title,
        description=f"Inhaltsverzeichnis: {title}",
        robots="index,follow",
        canonical=canonical,
        base=BASE_URL,
        breadcrumbs=breadcrumbs(rel / "README.md"),
        toc="",
        content=html_list,
        json_ld=jsonld_webpage(title, canonical, f"Inhaltsverzeichnis: {title}"),
        year=datetime.date.today().year
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

def main():
    ensure_assets()
    urls = []

    for d in sorted(set(p.parent for p in ROOT.rglob("*.md"))):
        write_dir_autoindex(d)

    for md_path in collect_markdown(ROOT):
        raw = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)

        title = meta.get("title") or meta.get("titel_de") or md_path.stem.replace("-", " ").title()
        description = (meta.get("description") or meta.get("beschreibung_md_de") or "").strip()
        lang = (meta.get("lang") or "de").strip()
        noindex = bool(meta.get("noindex", False))

        html, toc = render_md(body)
        rel = md_path.relative_to(ROOT)
        canonical = canonical_for(rel)
        robots = "noindex,nofollow" if noindex else "index,follow"

        page = BASE_HTML.format(
            lang=lang,
            title=title,
            description=description[:160],
            robots=robots,
            canonical=canonical,
            base=BASE_URL,
            breadcrumbs=breadcrumbs(rel),
            toc=toc,
            content=html,
            json_ld=jsonld_webpage(title, canonical, description[:160], lang),
            year=datetime.date.today().year
        )
        out_file = pretty_url_for(rel)
        out_file.write_text(page, encoding="utf-8")

        if not noindex:
            urls.append({"loc": canonical, "lastmod": datetime.date.today().isoformat()})

    NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = ET.Element("urlset", attrib={"xmlns": NS})
    for e in urls:
        url_el = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_el, "loc"); loc.text = e["loc"]
        lm  = ET.SubElement(url_el, "lastmod"); lm.text = e["lastmod"]
    xml_bytes = ET.tostring(urlset, encoding="utf-8", xml_declaration=True)
    (OUT / "sitemap.xml").write_bytes(xml_bytes)

    print("OK – gebaut nach:", OUT.resolve())
    print("Seiten:", len(urls))
    print("Sitemap:", (OUT / "sitemap.xml").as_posix())

if __name__ == "__main__":
    main()
