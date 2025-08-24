#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baut eine statische Site aus Markdown für /wissen und erzeugt eine Sitemap.
"""

import os, sys, re, shutil, pathlib, datetime, json
from typing import Dict, List
try:
    import yaml
except Exception:
    yaml = None
import markdown
import xml.etree.ElementTree as ET

# --- ENV / CONFIG ---
BASE_URL     = os.environ.get("BASE_URL", "").rstrip("/")
CONTENT_ROOT = os.environ.get("CONTENT_ROOT", ".").strip().rstrip("/")
EXCLUDE_DIRS = set(filter(None, (os.environ.get("EXCLUDE_DIRS", "") or "").split(",")))

if not BASE_URL:
    print("ERROR: BASE_URL not set", file=sys.stderr); sys.exit(1)

ROOT = pathlib.Path(CONTENT_ROOT or ".").resolve()
OUT  = pathlib.Path("site").resolve()
OUT.mkdir(parents=True, exist_ok=True)

STYLE_CSS = """html,body{margin:0;padding:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif;line-height:1.6}"""

HTACCESS = r"""
# .htaccess im /wissen/ Ordner
DirectoryIndex index.html
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteBase /wissen/
RewriteRule ^(sitemap\.xml|robots\.txt)$ - [L]
RewriteCond %{REQUEST_FILENAME} -f [OR]
RewriteCond %{REQUEST_FILENAME} -d
RewriteRule ^ - [L]
RewriteCond %{REQUEST_URI} \.[^/]+$
RewriteRule ^ - [L]
RewriteRule ^(.+?)/?$ $1/index.html [L]
</IfModule>
"""

BASE_HTML = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
</head>
<body>
<header><a href="{base}/">Wissen</a></header>
<main>
  <nav>{breadcrumbs}</nav>
  <h1>{title}</h1>
  <div>{toc}</div>
  <div>{content}</div>
</main>
</body>
</html>
"""

MD_EXT = ["extra","toc"]

def parse_frontmatter(text: str):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            head = text[3:end].strip()
            body = text[end+4:]
            if yaml:
                try: meta = yaml.safe_load(head) or {}
                except Exception: meta = {}
            else: meta = {}
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

def breadcrumbs_html(md_rel: pathlib.Path) -> str:
    parts = md_rel.parent.parts if md_rel.name.lower()=="readme.md" else md_rel.with_suffix("").parts
    if not parts: return f'<a href="{BASE_URL}">Start</a>'
    crumbs, acc = [], []
    for seg in parts:
        acc.append(seg)
        href = "/".join([BASE_URL] + acc)
        crumbs.append(f'<a href="{href}">{seg}</a>')
    return ' / '.join(crumbs)

def collect_markdown(root: pathlib.Path):
    mds = []
    for p in root.rglob("*.md"):
        if any(seg in EXCLUDE_DIRS for seg in p.parts): continue
        mds.append(p)
    mds.sort(key=lambda x: (0 if x.name.lower()=="readme.md" else 1, x.as_posix()))
    return mds

def render_md(md_text: str):
    md = markdown.Markdown(extensions=MD_EXT, extension_configs={"toc": {"permalink": True}})
    html = md.convert(md_text)
    toc = getattr(md, "toc", "")
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
    if out.exists(): return
    items = []
    for p in sorted(dir_path.iterdir()):
        if p.is_dir() and any(q.suffix==".md" for q in p.glob("*.md")):
            href = "/".join([BASE_URL] + [*p.relative_to(ROOT).parts])
            items.append(f'<li><a href="{href}/">{p.name}/</a></li>')
        elif p.suffix.lower() == ".md" and p.name.lower() != "readme.md":
            href = "/".join([BASE_URL, p.relative_to(ROOT).with_suffix("").as_posix()])
            items.append(f'<li><a href="{href}/">{p.stem}</a></li>')
    html_list = "<ul>" + "\n".join(items) + "</ul>"
    title = rel.as_posix() if rel.as_posix() != "." else "Start"
    canonical = "/".join([BASE_URL, rel.as_posix().strip("/")]) if rel.as_posix()!="." else BASE_URL
    page = BASE_HTML.format(lang="de",title=title,description=f"Inhalt: {title}",
                            canonical=canonical,base=BASE_URL,
                            breadcrumbs=breadcrumbs_html(rel / "README.md"),
                            toc="",content=html_list)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

def write_sitemap(urls: List[Dict[str,str]]):
    NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = ET.Element("urlset", attrib={"xmlns": NS})
    for e in urls:
        url_el = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_el, "loc"); loc.text = e["loc"]
        lm  = ET.SubElement(url_el, "lastmod"); lm.text = e["lastmod"]
    xml_bytes = ET.tostring(urlset, encoding="utf-8", xml_declaration=True)
    (OUT / "sitemap.xml").write_bytes(xml_bytes)

def main():
    ensure_assets()
    urls = []
    for d in sorted(set(p.parent for p in ROOT.rglob("*.md"))):
        write_dir_autoindex(d)
    for md_path in collect_markdown(ROOT):
        raw = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)
        title = meta.get("title") or md_path.stem
        description = (meta.get("description") or "").strip()
        lang = (meta.get("lang") or "de").strip()
        html, toc = render_md(body)
        rel = md_path.relative_to(ROOT)
        canonical = canonical_for(rel)
        page = BASE_HTML.format(lang=lang,title=title,description=description[:160],
                                canonical=canonical,base=BASE_URL,
                                breadcrumbs=breadcrumbs_html(rel),
                                toc=toc,content=html)
        out_file = pretty_url_for(rel)
        out_file.write_text(page, encoding="utf-8")
        urls.append({"loc": canonical, "lastmod": datetime.date.today().isoformat()})
    # Root-Autoindex sicherstellen
    write_dir_autoindex(ROOT)
    # Sitemap
    write_sitemap(urls)
    print("OK – gebaut nach:", OUT)

if __name__ == "__main__":
    main()
