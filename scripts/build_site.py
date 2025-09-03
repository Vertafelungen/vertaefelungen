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
    head = "<!doctype html>\n<html lang=\"de\">\n<head>\n"
    head += f"<title>{title}</title>\n<link rel=\"canonical\" href=\"{canonical}\">\n"
    head += STYLE + "</head>\n<body>\n"
    if jsonld:
        head += f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n'
    return head

def render_page(title, description, body_html, breadcrumbs_html, base_url, canonical_path, fm, jsonld, pager_html):
    head = render_head(title, description, base_url, canonical_path, fm, jsonld)
    return head + f"""{breadcrumbs_html}
<main>
{body_html}
{pager_html}
</main>
</body>
</html>
"""

def should_exclude(path: Path, exclude_globs):
    s = str(path)
    for g in exclude_globs:
        if path.match(g) or s.startswith(g + '/'):
            return True
    return False

def build_sitemap(entries, out_path: Path, base_url: str):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod, noindex in entries:
        if noindex: continue
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
    ap.add_argument('--content-root', default='.', help='Root mit Markdown')
    ap.add_argument('--out-dir', default='site', help='Output-Verzeichnis')
    ap.add_argument('--base-url', default='', help='Basis-URL')
    args = ap.parse_args()

    content_root = Path(args.content_root).resolve()
    out_root = Path(args.out_dir).resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # Output-Verzeichnis ausschließen
    exclude_globs = [str(out_root.relative_to(content_root))] if out_root.is_relative_to(content_root) else []

    # Assets kopieren
    for src in content_root.rglob('*'):
        if src.is_dir() or src.suffix.lower() == '.md':
            continue
        if src.is_relative_to(out_root):
            continue
        rel = src.relative_to(content_root)
        dst = out_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src != dst:
            shutil.copy2(src, dst)

    md_files = [p for p in content_root.rglob('*.md') if not p.is_relative_to(out_root)]
    sitemap_entries = []

    for md_path in sorted(md_files):
        rel = md_path.relative_to(content_root)
        text = md_path.read_text(encoding='utf-8')
        fm, body_md = load_frontmatter_and_body(text)
        title = fm.get('title') or rel.stem.replace('-',' ').title()
        description = fm.get('description') or ''

        lang = rel.parts[0] if len(rel.parts)>0 and rel.parts[0] in ('de','en') else 'de'
        body_md = rewrite_md_links_in_markdown(body_md, lang_prefix=lang)

        name_low = md_path.name.lower()
        is_index = name_low in ('readme.md','_index.md','index.md')
        moved_down = not is_index

        body_md = adjust_relative_assets_in_markdown(body_md, moved_down)

        if is_index:
            out_dir = out_root / rel.parent
            out_file = out_dir / 'index.html'
            canonical_path = str(rel.parent).replace('\\','/') + '/'
        else:
            out_dir = out_root / rel.parent / rel.stem
            out_file = out_dir / 'index.html'
            canonical_path = str(Path(rel.parent, rel.stem)).replace('\\','/') + '/'

        breadcrumbs_html = make_breadcrumbs([p for p in canonical_path.strip('/').split('/') if p])
        body_html = md_to_html(body_md)
        body_html = sanitize_internal_links_in_html(body_html, moved_down)

        html = render_page(title, description, body_html, breadcrumbs_html, args.base_url or '', canonical_path, fm, {}, '')
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(html, encoding='utf-8')

        lastmod = datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        sitemap_entries.append((canonical_path, lastmod, bool(fm.get('noindex'))))

    if args.base_url:
        build_sitemap(sitemap_entries, out_root / 'sitemap.xml', args.base_url)

    print(f"[build_site] Fertig: {out_root}")

if __name__ == '__main__':
    sys.exit(main())
