#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Static site builder for /wissen with pretty URLs and robust .md link rewriting.

import argparse
import re
import sys
import shutil
from pathlib import Path
from urllib.parse import quote

import yaml
import markdown

MD_EXTENSIONS = ['extra', 'meta', 'sane_lists', 'toc']
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
    """Map foo.md -> foo/, README.md/_index.md/index.md -> ./"""
    clean = target.split('#')[0]
    frag = '' if '#' not in target else '#' + target.split('#', 1)[1]
    if clean.endswith('.md'):
        name = Path(clean).name.lower()
        if name in ('readme.md', '_index.md', 'index.md'):
            base = str(Path(clean).parent).replace('\\', '/')
            if base and not base.endswith('/'):
                base += '/'
            return base + frag
        else:
            stem = Path(clean).stem
            base = str(Path(clean).parent / stem).replace('\\', '/')
            if not base.endswith('/'):
                base += '/'
            return base + frag
    return target

def rewrite_md_links_in_markdown(markdown_text: str) -> str:
    """Rewrite all Markdown links [text](url.md#frag) -> [text](pretty/)."""
    link_re = re.compile(r'(\[([^\]]+)\]\(([^)]+)\))')
    def repl(m):
        full, text, url = m.group(0), m.group(2), m.group(3).strip()
        low = url.lower()
        if low.startswith(('http://', 'https://', 'mailto:')):
            return full
        new = _md_target_to_pretty(url)
        if new != url:
            return f'[{text}]({new})'
        return full
    return link_re.sub(repl, markdown_text)

def sanitize_internal_links_in_html(html: str):
    """Safety net: convert any remaining href="*.md" to pretty URLs in HTML."""
    def repl(match):
        href = match.group(1)
        if href.startswith(('http://','https://','mailto:')):
            return f'href="{href}"'
        new = _md_target_to_pretty(href)
        return f'href="{new}"'
    return re.sub(r'href="([^"]+)"', repl, html)

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

def render_page(title: str, body_html: str, breadcrumbs_html: str, base_url: str, canonical_path: str):
    head = f'''<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="canonical" href="{base_url.rstrip('/')}/{canonical_path.lstrip('/')}">
<style>
body{{max-width:900px;margin:2rem auto;padding:0 1rem;font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;line-height:1.55}}
nav.breadcrumbs{{font-size:.9rem;color:#666;margin:.5rem 0 1rem}}
nav.breadcrumbs a{{text-decoration:none}}
ul.index{{list-style:none;padding:0}}
ul.index li{{margin:.35rem 0}}
code,pre{{font-family:ui-monospace,Menlo,Consolas,monospace}}
a{{text-decoration:none;border-bottom:1px solid #ddd}}
a:hover{{border-color:#333}}
hr{{border:none;border-top:1px solid #eee;margin:2rem 0}}
</style>
</head>
<body>
{breadcrumbs_html}
<main>
'''
    foot = '''
</main>
</body>
</html>'''
    return head + body_html + foot

def collect_children(md_files, current_dir: Path):
    items = []
    for p in sorted(md_files):
        if p.parent != current_dir:
            continue
        name = p.name.lower()
        if name in ('readme.md', '_index.md', 'index.md'):
            continue
        fm, _ = load_frontmatter_and_body(p.read_text(encoding='utf-8'))
        title = fm.get('title') or p.stem.replace('-', ' ').title()
        url = f"{p.stem}/"
        items.append((title, url))
    return items

def should_exclude(path: Path, exclude_globs):
    s = str(path)
    for g in exclude_globs:
        if path.match(g) or s.startswith(g + '/'):
            return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--content-root', default='.', help='Root to scan for Markdown')
    ap.add_argument('--out-dir', default='build', help='Output directory for HTML')
    ap.add_argument('--base-url', default='', help='Absolute base URL (e.g. https://www.vertaefelungen.de/wissen)')
    ap.add_argument('--exclude', default='.git,.github,tools,scripts,build,dist,venv,__pycache__', help='Comma-separated globs/paths to exclude')
    args = ap.parse_args()

    content_root = Path(args.content_root).resolve()
    out_root = Path(args.out_dir).resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    exclude_globs = [e.strip() for e in args.exclude.split(',') if e.strip()]
    md_files = [p for p in content_root.rglob('*.md') if not should_exclude(p.relative_to(content_root), exclude_globs)]

    for md_path in sorted(md_files):
        rel = md_path.relative_to(content_root)
        text = md_path.read_text(encoding='utf-8')
        fm, body_md = load_frontmatter_and_body(text)
        title = fm.get('title') or rel.stem.replace('-', ' ').title()

        # PRE-PROCESS: rewrite Markdown links pointing to *.md to pretty URLs
        body_md = rewrite_md_links_in_markdown(body_md)

        name_low = md_path.name.lower()
        if name_low in ('readme.md', '_index.md', 'index.md'):
            out_dir = out_root.joinpath(rel.parent)
            out_file = out_dir.joinpath('index.html')
            canonical_path = str(rel.parent).replace('\\', '/') + '/'
        else:
            out_dir = out_root.joinpath(rel.parent, rel.stem)
            out_file = out_dir.joinpath('index.html')
            canonical_path = str(Path(rel.parent, rel.stem)).replace('\\', '/') + '/'

        rel_parts = [p for p in canonical_path.strip('/').split('/') if p]
        breadcrumbs_html = make_breadcrumbs(rel_parts) if rel_parts else ''

        # Convert to HTML
        body_html = md_to_html(body_md)

        # POST-PROCESS: safety net in final HTML
        body_html = sanitize_internal_links_in_html(body_html)

        # Directory index listing
        if name_low in ('readme.md', '_index.md', 'index.md'):
            children = collect_children(md_files, md_path.parent)
            if children:
                items = '\n'.join(f'<li><a href="{quote(url)}">{title}</a></li>' for title, url in children)
                body_html += f'\n<hr/>\n<ul class="index">\n{items}\n</ul>\n'

        html = render_page(title, body_html, breadcrumbs_html, args.base_url or '', canonical_path)
        write_file(out_file, html)

    print(f'[build_site] Done. Built HTML into: {out_root}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
