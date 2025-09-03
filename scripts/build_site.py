#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Minimal, robuste Static-Site-Engine für /wissen
# - Pretty URLs (README/_index -> /, foo.md -> /foo/)
# - Sprache DE/EN aus Pfad, absolute /wissen/...-Links werden zu /wissen/<lang>/...
# - Alle *.md-Links -> Pretty-URLs (auch mit #anker)
# - Breadcrumbs + Autoverzeichnisliste
# - Kopiert ALLE Nicht-Markdown-Assets 1:1
# - Schreibt optionale sitemap.xml (nur wenn --sitemap gesetzt)
#
# CLI:
#   python scripts/build_site.py --content-root . --out-dir site --base-url https://www.vertaefelungen.de/wissen --sitemap
import argparse, re, sys, shutil, datetime
from pathlib import Path
from urllib.parse import quote
import markdown, yaml

MD_EXTENSIONS=['extra','meta','sane_lists','toc']
FRONTMATTER_RE = re.compile(r'^\s*---\s*\n(.*?)\n---\s*\n', re.DOTALL)

def load_frontmatter(text:str):
    m=FRONTMATTER_RE.match(text)
    if not m: return {}, text
    try: fm = yaml.safe_load(m.group(1)) or {}
    except Exception: fm = {}
    return fm, text[m.end():]

def md_to_html(md:str)->str:
    return markdown.markdown(md, extensions=MD_EXTENSIONS)

def to_pretty(target:str)->str:
    clean=target.split('#')[0]; frag='' if '#' not in target else '#' + target.split('#',1)[1]
    if clean.endswith('.md'):
        name=Path(clean).name.lower()
        if name in ('readme.md','_index.md','index.md'):
            base=str(Path(clean).parent).replace('\\','/')
            if base and not base.endswith('/'): base+='/'
            return base+frag
        stem=Path(clean).stem; base=str(Path(clean).parent/stem).replace('\\','/')
        if not base.endswith('/'): base+='/'
        return base+frag
    return target

def rewrite_md(markdown_text:str, lang:str)->str:
    # /wissen/... -> /wissen/<lang>/...  (wenn kein /de/ oder /en/ folgt)
    def fix_abs(m):
        url=m.group(1); low=url.lower()
        if low.startswith(('http://','https://','mailto:','/wissen/de/','/wissen/en/')): return m.group(0)
        if low.startswith('/wissen/'):
            tail=url.split('/wissen/',1)[1].lstrip('/')
            return '('+f'/wissen/{lang}/{tail}'+')'
        return m.group(0)
    md=re.sub(r'\((/[^)]+)\)', fix_abs, markdown_text)

    # *.md -> pretty
    link_re=re.compile(r'(\[([^\]]+)\]\(([^)]+)\))')
    def repl(m):
        full,text,url=m.group(0),m.group(2),m.group(3).strip()
        if url.lower().startswith(('http://','https://','mailto:')): return full
        new=to_pretty(url)
        return f'[{text}]({new})' if new!=url else full
    return link_re.sub(repl, md)

def sanitize_html(html:str)->str:
    def repl(m):
        href=m.group(1)
        if href.startswith(('http://','https://','mailto:')): return f'href="{href}"'
        return f'href="{to_pretty(href)}"'
    return re.sub(r'href="([^"]+)"', repl, html)

def breadcrumbs(parts):
    if not parts: return ''
    bits=['<nav class="breadcrumbs">']
    for i,part in enumerate(parts):
        label=quote(part.replace('-',' ').title())
        if i==len(parts)-1: bits.append(f'<span>{label}</span>')
        else:
            up='../'*(len(parts)-i-1)
            bits.append(f'<a href="{up}">{label}</a>')
    bits.append('</nav>'); return '\n'.join(bits)

def html_shell(title, body, crumbs, base_url, canonical):
    head=f'''<!doctype html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="canonical" href="{base_url.rstrip('/')}/{canonical.lstrip('/')}">
<style>
body{{max-width:900px;margin:2rem auto;padding:0 1rem;font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;line-height:1.55}}
nav.breadcrumbs{{font-size:.9rem;color:#666;margin:.5rem 0 1rem}}
nav.breadcrumbs a{{text-decoration:none}}
ul.index{{list-style:none;padding:0}} ul.index li{{margin:.35rem 0}}
a{{text-decoration:none;border-bottom:1px solid #ddd}} a:hover{{border-color:#333}}
</style></head><body>
{crumbs}<main>'''
    foot='</main></body></html>'
    return head+body+foot

def write(path:Path, content:str):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding='utf-8')

def collect_children(md_files, cur:Path):
    items=[]
    for p in sorted(md_files):
        if p.parent!=cur: continue
        name=p.name.lower()
        if name in ('readme.md','_index.md','index.md'): continue
        fm,_=load_frontmatter(p.read_text(encoding='utf-8'))
        title=fm.get('title') or p.stem.replace('-',' ').title()
        items.append((title, f"{p.stem}/"))
    return items

def should_exclude(path:Path, globs):
    s=str(path)
    for g in globs:
        if path.match(g) or s.startswith(g+'/'): return True
    return False

def maybe_add_index_list(name_low, md_files, md_path, body_html):
    if name_low in ('readme.md','_index.md','index.md'):
        children=collect_children(md_files, md_path.parent)
        if children:
            items='\n'.join(f'<li><a href="{quote(url)}">{title}</a></li>' for title,url in children)
            body_html += f'\n<hr/>\n<ul class="index">\n{items}\n</ul>\n'
    return body_html

def build(args):
    root=Path(args.content_root).resolve()
    out=Path(args.out_dir).resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    exclude=[e.strip() for e in args.exclude.split(',') if e.strip()]

    # Copy assets
    all_files=[p for p in root.rglob('*') if not should_exclude(p.relative_to(root), exclude)]
    for src in all_files:
        if src.is_dir() or src.suffix.lower()=='.md': continue
        rel=src.relative_to(root); dst=out/rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)

    # Render md
    md_files=[p for p in root.rglob('*.md') if not should_exclude(p.relative_to(root), exclude)]
    url_entries=[]

    for md in sorted(md_files):
        rel=md.relative_to(root)
        fm, body_md = load_frontmatter(md.read_text(encoding='utf-8'))
        title = fm.get('title') or rel.stem.replace('-',' ').title()

        lang = rel.parts[0] if len(rel.parts)>0 and rel.parts[0] in ('de','en') else 'de'
        body_md = rewrite_md(body_md, lang)

        name_low=md.name.lower()
        if name_low in ('readme.md','_index.md','index.md'):
            out_dir = out/rel.parent; out_file = out_dir/'index.html'
            canonical = (str(rel.parent).replace('\\','/') + '/')
        else:
            out_dir = out/rel.parent/rel.stem; out_file = out_dir/'index.html'
            canonical = (str((rel.parent/rel.stem)).replace('\\','/') + '/')

        parts=[p for p in canonical.strip('/').split('/') if p]
        crumbs=breadcrumbs(parts)
        html = md_to_html(body_md)
        html = sanitize_html(html)
        html = maybe_add_index_list(name_low, md_files, md, html)

        final = html_shell(title, html, crumbs, args.base_url or '', canonical)
        write(out_file, final)

        # sitemap entries
        url_entries.append((args.base_url.rstrip('/') + '/' + canonical.lstrip('/'), datetime.date.today().isoformat()))

    if args.sitemap:
        write_sitemap(out, url_entries)

def write_sitemap(out_root:Path, entries):
    from xml.sax.saxutils import escape
    lines=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc,lastmod in entries:
        lines.append(f'  <url><loc>{escape(loc)}</loc><lastmod>{lastmod}</lastmod></url>')
    lines.append('</urlset>')
    (out_root/'sitemap.xml').write_text('\n'.join(lines), encoding='utf-8')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--content-root', default='.', help='Root to scan for Markdown')
    ap.add_argument('--out-dir', default='site', help='Output directory for HTML')
    ap.add_argument('--base-url', default='', help='Absolute base URL (e.g. https://www.vertaefelungen.de/wissen)')
    ap.add_argument('--exclude', default='.git,.github,tools,scripts,build,dist,venv,__pycache__', help='Comma-separated globs/paths to exclude')
    ap.add_argument('--sitemap', action='store_true', help='Write sitemap.xml into out-dir')
    args=ap.parse_args()
    build(args); print(f'[build_site] Built → {Path(args.out_dir).resolve()}')

if __name__=='__main__':
    sys.exit(main())
