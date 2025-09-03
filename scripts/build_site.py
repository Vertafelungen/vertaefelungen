#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import markdown, yaml

MD_EXTENSIONS = ['extra','meta','sane_lists','toc']
FRONTMATTER_RE = re.compile(r'^\s*---\s*\n(.*?)\n---\s*\n', re.DOTALL)

def load_frontmatter_and_body(text: str):
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
        body = text[m.end():]
    else:
        fm, body = {}, text
    return fm, body

def md_to_html(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=MD_EXTENSIONS)

def _md_target_to_pretty(target: str) -> str:
    clean = target.split('#')[0]
    frag = '' if '#' not in target else '#' + target.split('#', 1)[1]
    if clean.endswith('.md'):
        name = Path(clean).name.lower()
        if name in ('readme.md','_index.md','index.md'):
            base = str(Path(clean).parent).replace('\\','/')
            if base and not base.endswith('/'):
                base += '/'
            return base + frag
        stem = Path(clean).stem
        base = str(Path(clean).parent / stem).replace('\\','/')
        if not base.endswith('/'):
            base += '/'
        return base + frag
    return target

ABS_URL_RE = re.compile(r'\((/[^)]+)\)')

def rewrite_md_links_in_markdown(markdown_text: str, lang_prefix: str) -> str:
    # /wissen/... -> /wissen/<lang>/...
    def fix_abs(m):
        url = m.group(1)
        low = url.lower().strip()
        if low.startswith(('http://','https://','mailto:','/wissen/de/','/wissen/en/')):
            return m.group(0)
        if low.startswith('/wissen/'):
            tail = url.split('/wissen/',1)[1].lstrip('/')
            return '(' + f'/wissen/{lang_prefix}/{tail}' + ')'
        return m.group(0)
    md = ABS_URL_RE.sub(fix_abs, markdown_text)

    # *.md -> pretty
    link_re = re.compile(r'(\[([^\]]+)\]\(([^)]+)\))')
    def repl(m):
        full, text, url = m.group(0), m.group(2), m.group(3).strip()
        if url.lower().startswith(('http://','https://','mailto:')):
            return full
        new = _md_target_to_pretty(url)
        return f'[{text}]({new})' if new != url else full
    return link_re.sub(repl, md)

def adjust_relative_assets_in_markdown(md_text: str, moved_down: bool) -> str:
    """Wenn Seite nach /<stem>/index.html verschoben wird, müssen
       relative Asset-Pfade (Bilder, PDFs, …) um eine Ebene nach oben."""
    if not moved_down:
        return md_text

    def fix(url: str) -> str:
        u = url.strip()
        low = u.lower()
        if low.startswith(('http://','https://','mailto:','/')):
            return u
        if low.endswith('.md'):
            return u
        if u.startswith('../'):
            return u
        return '../' + u

    # Bilder ![alt](url)
    img_re = re.compile(r'(!\[[^\]]*\]\(([^)]+)\))')
    def img_sub(m):
        full, url = m.group(0), m.group(2)
        return full.replace(url, fix(url), 1)
    md_text = img_re.sub(img_sub, md_text)

    # Normale Links [text](url)
    a_re = re.compile(r'(\[[^\]]+\]\(([^)]+)\))')
    def a_sub(m):
        full, url = m.group(0), m.group(2)
        return full.replace(url, fix(url), 1)
    return a_re.sub(a_sub, md_text)

def sanitize_internal_links_in_html(html: str, moved_down: bool):
    # href="*.md" -> pretty
    def repl_href(match):
        href = match.group(1)
        if href.startswith(('http://','https://','mailto:')):
            return f'href="{href}"'
        new = _md_target_to_pretty(href)
        return f'href="{new}"'
    html = re.sub(r'href="([^"]+)"', repl_href, html)

    # <img src="relative.png"> -> ../relative.png wenn moved_down
    if moved_down:
        def repl_src(match):
            src = match.group(1)
            low = src.lower()
            if low.startswith(('http://','https://','data:','/')):
                return f'src="{src}"'
            if src.startswith('../'):
                return f'src="{src}"'
            return f'src="../{src}"'
        html = re.sub(r'src="([^"]+)"', repl_src, html)
    return html

def make_breadcrumbs(rel_parts):
    crumbs = ['<nav class="breadcrumbs">']
    for i, part in enumerate(rel_parts):
        label = quote(part.replace('-', ' ').title())
        if i == len(rel_parts)-1:
            crumbs.append(f'<span>{label}</span>')
        else:
            up = '../' * (len(rel_parts)-i-1)
            crumbs.append(f'<a href="{up}">{label}</a>')
    crumbs.append('</nav>')
    return '\n'.join(crumbs)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')

STYLE = """
<style>
:root { --w:900px; --pad:1rem; --fg:#111; --fg2:#666; --link:#222; --muted:#eee; }
body { max-width:var(--w); margin:2rem auto; padding:0 var(--pad); font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif; line-height:1.55; color:var(--fg); }
nav.breadcrumbs { font-size:.9rem; color:var(--fg2); margin:.5rem 0 1rem; }
nav.breadcrumbs a { text-decoration:none; }
ul.index { list-style:none; padding:0; }
ul.index li { margin:.35rem 0; }
code,pre { font-family:ui-monospace,Menlo,Consolas,monospace; }
a { text-decoration:none; border-bottom:1px solid #ddd; color:var(--link); }
a:hover { border-color:#333; }
hr { border:none; border-top:1px solid var(--muted); margin:2rem 0; }
.article-meta { color:var(--fg2); font-size:.9rem; margin:.5rem 0 1rem; }
.pager { display:flex; justify-content:space-between; gap:1rem; margin:2rem 0; }
.pager a { border:1px solid var(--muted); padding:.4rem .6rem; border-radius:.25rem; }
</style>
"""

def render_head(title: str, description: str, base_url: str, canonical_path: str, fm: dict, jsonld: dict):
    canonical = f"{base_url.rstrip('/')}/{canonical_path.lstrip('/')}" if base_url else canonical_path
    og_image = ''
    img = None
    for key in ('image','og_image','cover','thumbnail'):
        val = fm.get(key)
        if isinstance(val,str) and val:
            img = val; break
        if isinstance(val,(list,tuple)) and val:
            img = val[0]; break
    if img:
        og_image = f'<meta property="og:image" content="{img if img.startswith("/") else (base_url.rstrip("/") + "/" + img) if base_url else img}">\n'

    meta = "".join([
        '<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        f'<title>{title}</title>\n',
        f'<link rel="canonical" href="{canonical}">\n',
        f'<meta name="description" content="{description}">\n',
        f'<meta property="og:title" content="{title}">\n',
        f'<meta property="og:description" content="{description}">\n',
        '<meta property="og:type" content="article">\n',
        f'<meta property="og:url" content="{canonical}">\n',
        og_image,
        '<meta name="twitter:card" content="summary_large_image">\n',
        f'<meta name="twitter:title" content="{title}">\n',
        f'<meta name="twitter:description" content="{description}">\n',
    ])
    if fm.get('noindex'):
        meta += '<meta name="robots" content="noindex,follow">\n'

    head = "<!doctype html>\n<html lang=\"de\">\n<head>\n" + meta + STYLE + "</head>\n<body>\n"
    if jsonld:
        head += f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n'
    return head

def render_page(title: str, description: str, body_html: str, breadcrumbs_html: str, base_url: str, canonical_path: str, fm: dict, jsonld: dict, pager_html: str):
    head = render_head(title, description, base_url, canonical_path, fm, jsonld)
    foot = f"""{breadcrumbs_html}
<main>
{body_html}
{pager_html}
</main>
</body>
</html>
"""
    return head + foot

def collect_children(md_files, current_dir: Path):
    items = []
    for p in sorted(md_files):
        if p.parent != current_dir:
            continue
        name = p.name.lower()
        if name in ('readme.md','_index.md','index.md'):
            continue
        fm, _ = load_frontmatter_and_body(p.read_text(encoding='utf-8'))
        title = fm.get('title') or p.stem.replace('-',' ').title()
        url = f"{p.stem}/"
        items.append((title, url))
    return items

def should_exclude(path: Path, exclude_globs):
    s = str(path)
    for g in exclude_globs:
        if path.match(g) or s.startswith(g + '/'):
            return True
    return False

def make_jsonld(fm, title, description, canonical):
    if isinstance(fm.get('schema'), dict):
        obj = fm['schema']
        obj['@context'] = 'https://schema.org'
        if '@type' not in obj:
            obj['@type'] = 'WebPage'
        return obj
    if fm.get('product_id') or fm.get('price'):
        return {
            '@context':'https://schema.org',
            '@type':'Product',
            'name': title,
            'description': description,
            'sku': fm.get('product_id') or fm.get('reference'),
            'url': canonical,
            'offers': {
                '@type':'Offer',
                'price': str(fm.get('price')) if fm.get('price') is not None else None,
                'priceCurrency': fm.get('currency') or 'EUR',
                'availability': 'https://schema.org/InStock' if str(fm.get('verfuegbar') or fm.get('available')).strip() in ('1','true','True') else 'https://schema.org/OutOfStock'
            }
        }
    if any(k in fm for k in ('date','author','tags')):
        return {
            '@context':'https://schema.org',
            '@type':'Article',
            'headline': title,
            'description': description,
            'datePublished': fm.get('date'),
            'author': {'@type':'Person','name': fm.get('author')} if fm.get('author') else None,
            'url': canonical
        }
    return {'@context':'https://schema.org','@type':'WebPage','name':title,'description':description,'url':canonical}

def build_sitemap(entries, out_path: Path, base_url: str):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod, noindex in entries:
        if noindex:
            continue
        loc = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        lines.append('  <url>')
        lines.append(f'    <loc>{loc}</loc>')
        if lastmod:
            lines.append(f'    <lastmod>{lastmod}</lastmod>')
        lines.append('  </url>')
    lines.append('</urlset>')
    out_path.write_text('\n'.join(lines), encoding='utf-8')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--content-root', default='.', help='Root to scan for Markdown')
    ap.add_argument('--out-dir', default='build', help='Output directory for HTML')
    ap.add_argument('--base-url', default='', help='Absolute base URL')
    ap.add_argument('--exclude', default='.git,.github,tools,scripts,build,dist,venv,__pycache__', help='Excludes')
    ap.add_argument('--sitemap', action='store_true', help='Generate sitemap.xml')
    args = ap.parse_args()

    content_root = Path(args.content_root).resolve()
    out_root = Path(args.out_dir).resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    exclude_globs = [e.strip() for e in args.exclude.split(',') if e.strip()]

    # Alle Nicht-Markdown-Assets kopieren
    all_files = [p for p in content_root.rglob('*') if not should_exclude(p.relative_to(content_root), exclude_globs)]
    for src in all_files:
        if src.is_dir() or src.suffix.lower() == '.md':
            continue
        rel = src.relative_to(content_root)
        dst = out_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Markdown-Seiten bauen
    md_files = [p for p in content_root.rglob('*.md') if not should_exclude(p.relative_to(content_root), exclude_globs)]
    sitemap_entries = []

    by_dir = {}
    for p in sorted(md_files):
        by_dir.setdefault(p.parent, []).append(p)

    for md_path in sorted(md_files):
        rel = md_path.relative_to(content_root)
        text = md_path.read_text(encoding='utf-8')
        fm, body_md = load_frontmatter_and_body(text)
        title = fm.get('title') or rel.stem.replace('-',' ').title()
        description = fm.get('description') or fm.get('meta_description') or ''

        lang = rel.parts[0] if len(rel.parts) > 0 and rel.parts[0] in ('de','en') else 'de'
        body_md = rewrite_md_links_in_markdown(body_md, lang_prefix=lang)

        name_low = md_path.name.lower()
        is_index = name_low in ('readme.md','_index.md','index.md')
        moved_down = not is_index  # non-index pages werden nach /<stem>/index.html gelegt

        # Relative Asset-Referenzen anpassen (..)
        body_md = adjust_relative_assets_in_markdown(body_md, moved_down=moved_down)

        if is_index:
            out_dir = out_root.joinpath(rel.parent)
            out_file = out_dir.joinpath('index.html')
            canonical_path = str(rel.parent).replace('\\','/') + '/'
        else:
            out_dir = out_root.joinpath(rel.parent, rel.stem)
            out_file = out_dir.joinpath('index.html')
            canonical_path = str(Path(rel.parent, rel.stem)).replace('\\','/') + '/'

        rel_parts = [p for p in canonical_path.strip('/').split('/') if p]
        breadcrumbs_html = make_breadcrumbs(rel_parts) if rel_parts else ''

        body_html = md_to_html(body_md)
        body_html = sanitize_internal_links_in_html(body_html, moved_down=moved_down)

        if is_index:
            children = collect_children(md_files, md_path.parent)
            if children:
                items = '\n'.join(f'<li><a href="{quote(url)}">{t}</a></li>' for t, url in children)
                body_html += f'\n<hr/>\n<ul class="index">\n{items}\n</ul>\n'

        # (optional) einfache Prev/Next
        pager_html = ''
        siblings = by_dir.get(md_path.parent, [])
        if len(siblings) > 1 and md_path in siblings:
            i = siblings.index(md_path)
            prev_html = next_html = ''
            if i > 0:
                p = siblings[i-1]
                prev_title = load_frontmatter_and_body(p.read_text(encoding='utf-8'))[0].get('title') or p.stem.replace('-',' ').title()
                prev_url = '../' + ('' if p.name.lower() in ('readme.md','_index.md','index.md') else p.stem + '/')
                prev_html = f'<a href="{prev_url}">&larr; {prev_title}</a>'
            if i < len(siblings)-1:
                n = siblings[i+1]
                next_title = load_frontmatter_and_body(n.read_text(encoding='utf-8'))[0].get('title') or n.stem.replace('-',' ').title()
                next_url = '../' + ('' if n.name.lower() in ('readme.md','_index.md','index.md') else n.stem + '/')
                next_html = f'<a style="margin-left:auto" href="{next_url}">{next_title} &rarr;</a>'
            if prev_html or next_html:
                pager_html = f'<div class="pager">{prev_html}{next_html}</div>'

        canonical = f"{args.base_url.rstrip('/')}/{canonical_path.lstrip('/')}" if args.base_url else canonical_path
        try:
            jsonld = make_jsonld(fm, title, description, canonical)
        except Exception:
            jsonld = {}

        html = render_page(title, description, body_html, breadcrumbs_html, args.base_url or '', canonical_path, fm, jsonld, pager_html)
        write_file(out_file, html)

        lastmod = datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        sitemap_entries.append((canonical_path, lastmod, bool(fm.get('noindex'))))

    if args.sitemap and args.base_url:
        build_sitemap(sitemap_entries, out_root / 'sitemap.xml', args.base_url)

    print(f'[build_site] Built HTML into: {out_root}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
