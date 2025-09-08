#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static Markdown → HTML Builder für /wissen
Version: 2025-09-08 18:05 (Europe/Berlin)

Neu ggü. 17:35:
- Nachpolitur 'finalize_root_links()': fängt verbleibende href/src="/wissen/..." ohne Sprachpräfix
  (case-insensitive, whitespace-tolerant, single/double/unquoted) und setzt sie auf /wissen/<lang>/...
- Validator im Workflow kann dadurch strenger bleiben.
"""

from __future__ import annotations
import argparse, html, json, os, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    import markdown  # type: ignore
except Exception:
    print("[build_site] Hinweis: 'markdown' wird in der Action installiert.", file=sys.stderr)

_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp://", "ftps://")
# tolerant: href|src = optional spaces, optional quotes, any URL chars bis zum schließenden Quote/Whitespace/>, case-insensitive
_HREF_RE = re.compile(r'''(?P<attr>\b(?:href|src)\s*=\s*)(?P<q>["']?)(?P<url>[^"'\s>]+)(?P=q)''', re.IGNORECASE)

def is_external(url: str) -> bool:
    u = url.strip()
    if not u or u.startswith("#"):
        return True
    return u.lower().startswith(_EXTERNAL_SCHEMES)

def _strip_md_and_index(p: PurePosixPath) -> PurePosixPath:
    n = p.name.lower()
    if n in ("readme.md", "_index.md", "index.md"):
        return p.parent
    if p.suffix.lower() == ".md":
        return p.with_suffix("")
    return p

def _resolve_relative(target_raw: str, current_dir_rel: PurePosixPath) -> PurePosixPath:
    t = target_raw.strip().replace("\\", "/")
    if t.startswith("./"):
        t = t[2:]
    parts = list(current_dir_rel.parts)
    for seg in t.split("/"):
        if seg in ("", "."): continue
        if seg == "..":
            if parts: parts.pop()
        else:
            parts.append(seg)
    return PurePosixPath(*parts)

def _to_wissen_abs(lang: str, target_rel_to_lang: PurePosixPath) -> str:
    pretty = _strip_md_and_index(target_rel_to_lang)
    s = f"/wissen/{lang}/{pretty.as_posix().lstrip('/')}"
    if not s.endswith("/"): s += "/"
    return s

def rewrite_links_in_html(html_text: str, lang: str, current_doc_rel_dir: PurePosixPath) -> str:
    def repl(m: re.Match) -> str:
        attr, q, url = m.group("attr"), m.group("q") or '"', m.group("url")
        u = url.strip()
        if is_external(u) or u.startswith("#"):
            return f'{attr}{q}{u}{q}'
        low = u.lower()

        # korrekt -> lassen
        if low.startswith(f"/wissen/{lang}/"):
            return f'{attr}{q}{u}{q}'

        # /wissen/ ohne Sprachpräfix -> ergänzen
        if low.startswith("/wissen/") and not low.startswith(f"/wissen/{lang}/"):
            rest = u.split("/wissen/", 1)[1].lstrip("/")
            tail = "" if (not rest or rest.endswith("/")) else "/"
            return f'{attr}{q}/wissen/{lang}/{rest}{tail}{q}'

        # /de/... oder /en/... direkt unter Root -> in /wissen/<lang>/...
        if low.startswith("/de/") or low.startswith("/en/"):
            rest = u.split("/", 2)[2] if u.count("/") >= 2 else ""
            tail = "" if (not rest or rest.endswith("/")) else "/"
            return f'{attr}{q}/wissen/{lang}/{rest}{tail}{q}'

        # Root-absolute interne Pfade -> /wissen/<lang>/...
        if low.startswith("/"):
            rest = u.lstrip("/")
            tail = "" if rest.endswith("/") else "/"
            return f'{attr}{q}/wissen/{lang}/{rest}{tail}{q}'

        # Relativpfade -> auflösen
        resolved = _resolve_relative(u, current_doc_rel_dir)
        return f'{attr}{q}{_to_wissen_abs(lang, resolved)}{q}'

    return _HREF_RE.sub(repl, html_text)

# --- NEU: Nachpolitur, falls irgendwas durchgerutscht ist ---------------------
# fängt ALLE Formen von href/src="/wissen/..." ohne Sprachpräfix ein
_ROOT_WISSEN_FIX = re.compile(
    r'''(?P<attr>\b(?:href|src)\s*=\s*)(?P<q>["']?)(?P<lead>\s*/\s*wissen\s*/\s*)(?P<rest>[^"'\s>]*)\s*(?P=q)''',
    re.IGNORECASE
)

def finalize_root_links(html_text: str, lang: str) -> str:
    def repl(m: re.Match) -> str:
        attr, q = m.group("attr"), m.group("q") or '"'
        rest = (m.group("rest") or "").lstrip("/")
        # wenn bereits de/ oder en/ am Anfang -> nichts tun
        if rest.lower().startswith(("de/", "en/")):
            return f'{attr}{q}/wissen/{rest}{q}'
        tail = "" if (not rest or rest.endswith("/")) else "/"
        return f'{attr}{q}/wissen/{lang}/{rest}{tail}{q}'
    return _ROOT_WISSEN_FIX.sub(repl, html_text)
# -----------------------------------------------------------------------------

def render_markdown(md_text: str) -> str:
    try:
        return markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except Exception:
        return "<pre>" + html.escape(md_text) + "</pre>"

def write_html_document(body: str, title: str = "Wissen") -> str:
    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="/wissen/assets/style.css">
<main class="container">
{body}
</main>
"""

def out_path_for(out_root: Path, lang: str, lang_root: Path, src_path: Path) -> Path:
    rel = src_path.relative_to(lang_root)
    if rel.name.lower() in ("index.md", "_index.md", "readme.md"):
        target_dir = out_root / lang / rel.parent
        return target_dir / "index.html"
    target_dir = out_root / lang / rel.with_suffix("")
    return target_dir / "index.html"

def build_sitemap(entries: list[str], out_file: Path, base_url: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = []
    for e in sorted(set(entries)):
        loc = f"{base_url.rstrip('/')}/{e.lstrip('/')}"
        urls.append(f"<url><loc>{html.escape(loc)}</loc><lastmod>{ts}</lastmod></url>")
    xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + \
          "\n".join(urls) + "\n</urlset>\n"
    out_file.write_text(xml, encoding="utf-8")

def write_robots(out_file: Path, base_url: str) -> None:
    out_file.write_text(f"User-agent: *\nAllow: /wissen/\nSitemap: {base_url.rstrip('/')}/sitemap.xml\n", encoding="utf-8")

def copy_assets(assets_dir: Path, out_root: Path):
    dst = out_root / "assets"
    if dst.exists(): shutil.rmtree(dst)
    if assets_dir.is_dir(): shutil.copytree(assets_dir, dst)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://www.vertaefelungen.de/wissen", type=str)
    ap.add_argument("--content-root", default=".", type=str, help="Repo-Root, das de/ und en/ enthält")
    ap.add_argument("--out-dir", default="site", type=str, help="Ausgabeverzeichnis")
    args = ap.parse_args()

    repo_root = Path(args.content_root).resolve()
    out_root  = Path(args.out_dir).resolve()
    lang_dirs = {lang: repo_root / lang for lang in ("de","en")}
    assets_dir = repo_root / "assets"

    if out_root.exists(): shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    copy_assets(assets_dir, out_root)

    sitemap_entries: list[str] = []

    for lang, lang_root in lang_dirs.items():
        if not lang_root.is_dir(): continue
        for src_path in lang_root.rglob("*.md"):
            md = src_path.read_text(encoding="utf-8")
            html_body = render_markdown(md)

            current_rel_dir = PurePosixPath(str(src_path.relative_to(lang_root).parent).replace("\\","/"))
            rewritten = rewrite_links_in_html(html_body, lang=lang, current_doc_rel_dir=current_rel_dir)
            # --- Nachpolitur ---
            rewritten = finalize_root_links(rewritten, lang=lang)

            doc_html = write_html_document(rewritten, title="Wissen")
            out_file = out_path_for(out_root, lang, lang_root, src_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(doc_html, encoding="utf-8")

            rel_url = str(out_file.relative_to(out_root)).replace("\\","/")
            sitemap_entries.append(rel_url)

    build_sitemap(sitemap_entries, out_root / "sitemap.xml", args.base_url)
    write_robots(out_root / "robots.txt", args.base_url)

    (out_root / "version.json").write_text(
        json.dumps({
            "built_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "builder": "build_site.py",
            "base_url": args.base_url,
            "out_dir": str(out_root),
            "content_root": str(repo_root),
            "pages": len(sitemap_entries),
        }, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (out_root / "index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=/wissen/de/">'
        '<link rel="canonical" href="/wissen/de/">Weiterleitung …',
        encoding="utf-8"
    )
    print(f"[build_site] Fertig: {out_root}")

if __name__ == "__main__":
    sys.exit(main())
