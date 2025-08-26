#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baut eine statische Site aus Markdown für /wissen und erzeugt eine Sitemap.
- README.md -> index.html im Ordner
- foo.md    -> foo/index.html (pretty URLs)
- Frontmatter (optional): title, slug, lang, description, noindex, faq (Liste), image, counterpart
- Fügt Canonical, JSON-LD (WebPage/FAQ/Breadcrumbs/Organization/WebSite), Breadcrumbs-HTML hinzu
- Erzeugt Auto-Indexseiten für Ordner ohne README.md
- Schreibt site/sitemap.xml
- Schreibt zusätzlich site/.htaccess (Whitelist für sitemap.xml/robots.txt, keine Umschreibung für Dateien mit Endung)
- Optional: hreflang-Paare, wenn de/en-Gegenstück existiert
"""

import os, sys, shutil, pathlib, datetime, json
from typing import Dict, Tuple, List
try:
    import yaml
except Exception:
    yaml = None
import markdown
import xml.etree.ElementTree as ET

# --- ENV / CONFIG ---
BASE_URL     = os.environ.get("BASE_URL", "").rstrip("/")        # z.B. https://www.vertaefelungen.de/wissen
CONTENT_ROOT = os.environ.get("CONTENT_ROOT", ".").strip().rstrip("/")  # z.B. wissen (Repo-Unterordner) oder .
EXCLUDE_DIRS = set(filter(None, (os.environ.get("EXCLUDE_DIRS", "") or "").split(",")))

if not BASE_URL:
    print("ERROR: BASE_URL not set", file=sys.stderr); sys.exit(1)

ROOT = pathlib.Path(CONTENT_ROOT or ".").resolve()
OUT  = pathlib.Path("site").resolve()
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
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.tile{display:block;border:1px solid #eee;border-radius:8px;overflow:hidden;text-decoration:none}
.tile-body{padding:12px}
.tile-title{font-weight:600;margin-bottom:.25rem}
.tile-teaser{color:#555;font-size:.9rem}
.tile-thumb img{display:block;width:100%;height:auto}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace}
"""

HTACCESS = r"""
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
RewriteCond %{REQUEST_URI} \.[^/]+$
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
    <p>Quelle: <a href="{canonical}">{canonical}</a></p>
  </div>
</footer>
</body>
</html>
"""

MD_EXT = ["extra","toc","sane_lists","smarty"]

def parse_frontmatter(text: str):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            head = text[3:end].strip()
            body = text[end+4:]
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

def breadcrumbs_html(md_rel: pathlib.Path) -> str:
    parts = md_rel.parent.parts if md_rel.name.lower()=="readme.md" else md_rel.with_suffix("").parts
    if not parts:
        return f'<a href="{BASE_URL}">Start</a>'
    crumbs, acc = [], []
    for seg in parts:
        acc.append(seg)
        href = "/".join([BASE_URL] + acc)
        crumbs.append(f'<a href="{href}">{seg}</a>')
    return ' / '.join(crumbs)

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
    toc = getattr(md, "toc", "")
    return html, toc


def load_site_manifest() -> list:
    candidates = [ROOT / "site_manifest.json", ROOT / "assets" / "site_manifest.json"]
    for c in candidates:
        if c.exists():
            try:
                import json as _json
                data = _json.loads(c.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "items" in data:
                    return data["items"]
                if isinstance(data, list):
                    return data
            except Exception as e:
                print("WARN: site_manifest.json konnte nicht geladen werden:", e, file=sys.stderr)
    return []

def _lang_from_rel(rel: pathlib.Path) -> str:
    for part in rel.parts:
        if part.lower() == "en":
            return "en"
    return "de"

def render_category_landing(dir_path: pathlib.Path, manifest: list):
    rel = dir_path.relative_to(ROOT)
    out = OUT / rel / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    lang = _lang_from_rel(rel)
    base = "/" + rel.as_posix().strip("/") + ("/" if rel.as_posix() != "." else "")
    def _is_direct_child(pth: str) -> bool:
        p = pth.strip("/")
        b = base.strip("/")
        if not p.startswith(b):
            return False
        rest = p[len(b):]
        return rest != "" and "/" not in rest.strip("/")
    items = [it for it in manifest if isinstance(it, dict) and it.get("path")]
    here = [it for it in items if _is_direct_child(it["path"])]
    if not here:
        here = [it for it in items if it["path"].strip("/").startswith(base.strip("/"))]
    def _t(it):
        return it.get(f"title_{lang}") or it.get("title") or it.get("path").rstrip("/").split("/")[-1]
    def _z(it):
        return it.get(f"teaser_{lang}") or it.get("teaser") or ""
    here.sort(key=lambda it: (it.get("order", 9999), _t(it).lower()))
    tiles = []
    for it in here:
        href = (BASE_URL.rstrip("/") + it["path"]).rstrip("/") + "/"
        thumb = it.get("thumb") or ""
        title = _t(it); teaser = _z(it)
        img = f'<div class="tile-thumb"><img src="{thumb}" alt="" loading="lazy"></div>' if thumb else ""
        tiles.append(f'<a class="tile" href="{href}">{img}<div class="tile-body"><div class="tile-title">{title}</div><div class="tile-teaser">{teaser}</div></div></a>')
    page_title = "Start" if rel.as_posix()=="." else rel.as_posix()
    crumbs = []; acc = []
    for part in rel.parts:
        acc.append(part)
        href = BASE_URL + "/" + "/".join(acc) + "/"
        crumbs.append(f'<a href="{href}">{part}</a>')
    bc_html = "" if not crumbs else "<nav class=\"breadcrumbs\">" + " / ".join(crumbs) + "</nav>"
    html = f"""<!doctype html>
<html lang="{lang}">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title} - Wissen</title>
<link rel="stylesheet" href="{BASE_URL}/assets/style.css">
<body>
<header class="site-header"><div class="wrap">
  <a class="brand" href="{BASE_URL}/">Wissen</a>
  <nav class="site-nav"><a href="{BASE_URL}/">Start</a></nav>
</div></header>
<main class="content"><div class="wrap page">
  {bc_html}
  <h1>{page_title}</h1>
  <div class="tiles">{''.join(tiles) if tiles else '<p>Keine Inhalte gefunden.</p>'}</div>
</div></main>
</body>
</html>"""
    out.write_text(html, encoding="utf-8")
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
        elif p.suffix.lower() == ".md" and p.name.lower() != "readme.md":
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
        breadcrumbs=breadcrumbs_html(rel / "README.md"),
        toc="",
        content=html_list,
        year=datetime.date.today().year
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

def write_sitemap(urls: List[Dict[str,str]]):
    NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = ET.Element("urlset", attrib={"xmlns": NS})
    seen = set()
    for e in urls:
        key = (e["loc"], e["lastmod"])
        if key in seen:
            continue
        seen.add(key)
        url_el = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_el, "loc"); loc.text = e["loc"]
        lm  = ET.SubElement(url_el, "lastmod"); lm.text = e["lastmod"]
    xml_bytes = ET.tostring(urlset, encoding="utf-8", xml_declaration=True)
    (OUT / "sitemap.xml").write_bytes(xml_bytes)

def main():
    ensure_assets()
    urls = []

    # Manifest-gestützte Landingpages statt Autoindex
    manifest = load_site_manifest()
    if manifest:
        cat_dirs = sorted({ (ROOT / (it.get('path','/').strip('/'))).resolve() if it.get('path') else ROOT for it in manifest if isinstance(it, dict) and it.get('type')=='category' })
        for d in cat_dirs:
            if str(d).startswith(str(ROOT)):
                render_category_landing(d, manifest)

    for md_path in collect_markdown(ROOT):
        raw = md_path.read_text(encoding="utf-8")
        meta, body = ({}, raw) if raw.strip()[:3] != '---' else parse_frontmatter(raw)
        title = (meta.get("title") or md_path.stem.replace("-", " ").title())
        description = (meta.get("description") or "").strip()
        lang = (meta.get("lang") or "de").strip()

        html, toc = render_md(body)
        rel = md_path.relative_to(ROOT)
        canonical = canonical_for(rel)
        robots = "noindex,nofollow" if bool(meta.get("noindex", False)) else "index,follow"

        page = BASE_HTML.format(
            lang=lang,
            title=title,
            description=description[:160],
            robots=robots,
            canonical=canonical,
            base=BASE_URL,
            breadcrumbs=breadcrumbs_html(rel),
            toc=toc,
            content=html,
            year=datetime.date.today().year
        )

        out_file = pretty_url_for(rel)
        out_file.write_text(page, encoding="utf-8")

        if robots.startswith("index"):
            urls.append({"loc": canonical, "lastmod": datetime.date.today().isoformat()})

    # Root-Landingpage aus Manifest (falls vorhanden)
    if 'manifest' in locals() and manifest:
        render_category_landing(ROOT, manifest)

    write_sitemap(urls)
    print("OK – gebaut nach:", OUT)
    print("Seiten:", len(urls))

if __name__ == "__main__":
    main()
