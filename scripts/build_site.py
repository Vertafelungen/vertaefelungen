#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Static Markdown → HTML Builder für /wissen
Version: 2025-09-08 14:00 (Europe/Berlin)

Änderungen in dieser Version:
- Asset-Kopie HART gehärtet: .git, .github, scripts, tools, de, en usw. werden NICHT nach site/ kopiert.
- Verhindert, dass .git-Objekte auf den Server deployt werden (Ursache deiner Permission-Fehler).
- (Beibehalt) Robuster Link-Rewriter (Markdown & HTML) inkl. optionalem Titel, Quotes, Case, unquoted href.
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import markdown
import yaml

# ---------- Markdown/Frontmatter ----------

MD_EXTENSIONS = ['extra', 'meta', 'sane_lists', 'toc']
FRONTMATTER_RE = re.compile(r'^\s*---\s*\n(.*?)\n---\s*\n', re.DOTALL)

def load_frontmatter_and_body(text: str):
    m = FRONTMATTER_RE.match(text)
    if m:
        fm_text = m.group(1)
        body = text[m.end():]
        try:
            fm = yaml.safe_load(fm_text) or {}
        except Exception:
            fm = {}
        return fm, body
    return {}, text

def md_to_html(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=MD_EXTENSIONS, output_format='xhtml')

# ---------- URL/Link Utilities ----------

def _md_target_to_pretty(target: str) -> str:
    clean = target.split('#')[0]
    frag = '' if '#' not in target else '#' + target.split('#', 1)[1]
    if clean.endswith('.md'):
        name = Path(clean).name.lower()
        if name in ('readme.md', '_index.md', 'index.md'):
            base = str(Path(clean).parent).replace('\\', '/')
            if base and not base.endswith('/'):
                base += '/'
            return base + frag
        stem = Path(clean).stem
        base = str(Path(clean).parent / stem).replace('\\', '/')
        if not base.endswith('/'):
            base += '/'
        return base + frag
    return target

def _add_lang_and_wissen_prefix(url: str, lang: str) -> str:
    u = (url or '').strip()
    low = u.lower()
    if low.startswith(('http://', 'https://', 'mailto:', 'tel:', 'data:', '#')):
        return u
    if low.startswith('/wissen/de/') or low.startswith('/wissen/en/'):
        return u
    if low.startswith('/wissen/'):
        tail = u.split('/wissen/', 1)[1].lstrip('/')
        return f'/wissen/{lang}/{tail}'
    if low.startswith('/de/') or low.startswith('/en/'):
        return '/wissen' + u
    if u.startswith('/'):
        return f'/wissen/{lang}/{u.lstrip("/")}'
    return u

MD_LINK_WITH_OPT_TITLE = re.compile(
    r'\[([^\]]+)\]\(\s*'
    r'(?P<url>/[^)\s]+|[^)\s][^)]*)'
    r'(?:\s+"(?P<title>[^"]*)")?'
    r'\s*\)'
)

def rewrite_md_links_in_markdown(markdown_text: str, lang_prefix: str) -> str:
    def repl(m):
        text  = m.group(1)
        url   = (m.group('url') or '').strip()
        title = m.group('title')
        if url.lower().startswith(('http://','https://','mailto:','tel:','#','data:')):
            new_url = url
        else:
            new_url = _add_lang_and_wissen_prefix(url, lang_prefix)
            new_url = _md_target_to_pretty(new_url)
        return f'[{text}]({new_url} "{title}")' if title is not None else f'[{text}]({new_url})'
    return MD_LINK_WITH_OPT_TITLE.sub(repl, markdown_text)

def adjust_relative_assets_in_markdown(md_text: str, moved_down: bool) -> str:
    if not moved_down:
        return md_text
    def fix(u: str) -> str:
        low = u.lower().strip()
        if low.startswith(('http://', 'https://', 'mailto:', 'tel:', 'data:', '/')): return u
        if low.endswith('.md'): return u
        if u.startswith('../'): return u
        return '../' + u
    img_re = re.compile(r'(!\[[^\]]*\]\(([^)]+)\))')
    md_text = img_re.sub(lambda m: m.group(0).replace(m.group(2), fix(m.group(2)), 1), md_text)
    a_re = re.compile(r'(\[[^\]]+\]\(([^)]+)\))')
    return a_re.sub(lambda m: m.group(0).replace(m.group(2), fix(m.group(2)), 1), md_text)

def _rewrite_attr_quotes(html: str, attr: str, lang_prefix: str, moved_down: bool) -> str:
    pattern = re.compile(rf'{attr}\s*=\s*([\'"])(.*?)\1', re.IGNORECASE)
    def repl(m):
        quote_ch = m.group(1)
        url = (m.group(2) or '').strip()
        low = url.lower()
        if low.startswith(('http://','https://','mailto:','tel:', '#', 'data:')):
            new = url
        else:
            new = _add_lang_and_wissen_prefix(url, lang_prefix)
            if attr.lower() == 'href':
                new = _md_target_to_pretty(new)
            if moved_down and attr.lower() == 'src':
                if not new.startswith(('/', 'http://', 'https://', 'data:', 'mailto:', 'tel:', '#')) and not new.startswith('../'):
                    new = '../' + new
        return f'{attr}={quote_ch}{new}{quote_ch}'
    return pattern.sub(repl, html)

def sanitize_internal_links_in_html(html: str, moved_down: bool, lang_prefix: str = 'de'):
    html = _rewrite_attr_quotes(html, 'href', lang_prefix, moved_down)
    html = _rewrite_attr_quotes(html, 'src',  lang_prefix, moved_down)
    # unquoted href=/pfad
    html = re.sub(
        r'(?i)href\s*=\s*(/[^\'"\s>]+)',
        lambda m: f'href="{_md_target_to_pretty(_add_lang_and_wissen_prefix(m.group(1), lang_prefix))}"',
        html
    )
    return html

# ---------- Rendering ----------

STYLE = """
<style>
:root { --w: 900px; --pad: 1rem; --fg: #111; --fg2: #666; --link: #222; --muted: #eee; }
body { max-width: var(--w); margin: 2rem auto; padding: 0 var(--pad);
       font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
       line-height: 1.55; color: var(--fg); }
nav.breadcrumbs { font-size: .9rem; color: var(--fg2); margin: .5rem 0 1rem; }
nav.breadcrumbs a { text-decoration: none; }
ul.index { list-style: none; padding: 0; }
ul.index li { margin: .35rem 0; }
code,pre { font-family: ui-monospace, Menlo, Consolas, monospace; }
a { text-decoration: none; border-bottom: 1px solid #ddd; color: var(--link); }
a:hover { border-color: #333; }
hr { border: none; border-top: 1px solid var(--muted); margin: 2rem 0; }
.article-meta { color: var(--fg2); font-size: .9rem; margin: .5rem 0 1rem; }
.pager { display: flex; justify-content: space-between; gap: 1rem; margin: 2rem 0; }
.pager a { border: 1px solid var(--muted); padding: .4rem .6rem; border-radius: .25rem; }
</style>
"""

def render_head(title: str, description: str, base_url: str, canonical_path: str, fm: dict, jsonld: dict):
    canonical = f"{base_url.rstrip('/')}/{canonical_path.lstrip('/')}" if base_url else canonical_path
    head = "<!doctype html>\n<html lang=\"de\">\n<head>\n"
    head += '<meta charset="utf-8">\n'
    head += '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    head += f"<title>{title}</title>\n<link rel=\"canonical\" href=\"{canonical}\">\n"
    head += STYLE + "</head>\n<body>\n"
    if jsonld:
        head += f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n'
    return head

def make_breadcrumbs(rel_parts):
    crumbs = ['<nav class="breadcrumbs">']
    for i, part in enumerate(rel_parts):
        label = quote(part.replace('-', ' ').title())
        if i == len(rel_parts) - 1:
            crumbs.append(f'<span>{label}</span>')
        else:
            up = '../' * (len(rel_parts) - i - 1)
            crumbs.append(f'<a href="{up}">{label}</a>')
    crumbs.append('</nav>')
    return '\n'.join(crumbs)

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

# ---------- Build / Sitemap ----------

def build_sitemap(entries, out_path: Path, base_url: str):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
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

# ---------- Main ----------

ASSET_TOPLEVEL_ALLOW = {
    # nur diese Top-Level-Verzeichnisse/Dateien werden 1:1 kopiert
    "assets", "bilder", "static", "docs"  # erweitern falls nötig
}
ASSET_DENY_PREFIX = {".git", ".github", "scripts", "tools", "de", "en", "site"}  # nie kopieren

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--content-root', default='.', help='Root mit Markdown (z. B. Repo-Wurzel)')
    ap.add_argument('--out-dir', default='site', help='Output-Verzeichnis')
    ap.add_argument('--base-url', default='', help='Basis-URL (z. B. https://www.vertaefelungen.de/wissen)')
    args = ap.parse_args()

    content_root = Path(args.content_root).resolve()
    out_root = Path(args.out_dir).resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # Assets 1:1 kopieren – aber NUR whitelisted Top-Level, keine .git/.github/scripts/tools/de/en/site
    for src in content_root.rglob('*'):
        if src.is_dir():
            continue
        if src.suffix.lower() == '.md':
            continue
        try:
            if src.is_relative_to(out_root):
                continue
        except AttributeError:
            pass

        rel = src.relative_to(content_root)
        top = rel.parts[0] if rel.parts else ''
        if top in ASSET_DENY_PREFIX:
            continue
        if top not in ASSET_TOPLEVEL_ALLOW and len(rel.parts) > 0:
            # nur whitelisted Toplevel kopieren
            continue
        # keine versteckten .git-Dateien irgendwo tiefer
        if any(part.startswith('.git') for part in rel.parts):
            continue

        dst = out_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src != dst:
            shutil.copy2(src, dst)

    # Markdown-Dateien verarbeiten
    md_files = [p for p in content_root.rglob('*.md') if not p.is_relative_to(out_root)]
    sitemap_entries = []

    for md_path in sorted(md_files):
        rel = md_path.relative_to(content_root)
        text = md_path.read_text(encoding='utf-8')
        fm, body_md = load_frontmatter_and_body(text)
        title = fm.get('title') or rel.stem.replace('-', ' ').title()
        description = fm.get('description') or ''

        lang = rel.parts[0] if len(rel.parts) > 0 and rel.parts[0] in ('de', 'en') else 'de'

        body_md = rewrite_md_links_in_markdown(body_md, lang_prefix=lang)

        name_low = md_path.name.lower()
        is_index = name_low in ('readme.md', '_index.md', 'index.md')
        moved_down = not is_index

        body_md = adjust_relative_assets_in_markdown(body_md, moved_down)

        if is_index:
            out_file = out_root / rel.parent / 'index.html'
            canonical_path = str(Path(rel.parent)).replace('\\', '/') + '/'
        else:
            out_dir = out_root / rel.parent / rel.stem
            out_file = out_dir / 'index.html'
            canonical_path = str(Path(rel.parent, rel.stem)).replace('\\', '/') + '/'

        breadcrumbs_html = make_breadcrumbs([p for p in canonical_path.strip('/').split('/') if p])
        body_html = md_to_html(body_md)
        body_html = sanitize_internal_links_in_html(body_html, moved_down, lang_prefix=lang)
        html = render_page(title, description, body_html, breadcrumbs_html, args.base_url or '', canonical_path, fm, {}, '')

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(html, encoding='utf-8')

        lastmod = datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        sitemap_entries.append((canonical_path, lastmod, bool(fm.get('noindex'))))

    if args.base_url:
        build_sitemap(sitemap_entries, out_root / 'sitemap.xml', args.base_url)

    root_index = out_root / 'index.html'
    root_index.write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=/wissen/de/">'
        '<link rel="canonical" href="/wissen/de/">Weiterleitung …',
        encoding='utf-8'
    )

    print(f"[build_site] Fertig: {out_root}")

if __name__ == '__main__':
    sys.exit(main())
