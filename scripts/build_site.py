#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static Markdown → HTML Builder für /wissen
Version: 2025-09-08 16:45 (Europe/Berlin)

Änderungen in dieser Version:
- Sprachsichere Link-Umschreibung: Alle internen Links werden zu /wissen/<lang>/... normalisiert.
- Korrekte Behandlung relativer Pfade (../, ./, bare) und .md → Pretty-URL (/index.html).
- HTML-Rewriter fasst href/src in <a>, <link>, <img>, <script> an (auch unquoted/Single-Quotes).
- Whitelist-Deployment in site/: nur /de, /en, /assets, /sitemap.xml, /robots.txt, /version.json, /index.html.
- Sitemap-Generator und robots.txt.
- Root-Weiterleitung: /wissen/index.html leitet auf /wissen/de/ (serverseitig zusätzlich in .htaccess, siehe unten).

Benötigte Python-Pakete:
- markdown  (wird in der GitHub Action installiert)

Aufruf:
  python scripts/build_site.py --base-url https://www.vertaefelungen.de/wissen
"""

from __future__ import annotations
import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    import markdown  # type: ignore
except Exception:
    print("[build_site] Hinweis: 'markdown' wird in der Action installiert.", file=sys.stderr)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_LANGS = ("de", "en")
SRC_DIRS = [REPO_ROOT / "de", REPO_ROOT / "en"]
ASSETS_DIR = REPO_ROOT / "assets"
OUT_ROOT = REPO_ROOT / "site"

# ---------- Hilfsfunktionen ----------

_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp://", "ftps://")
def is_external(url: str) -> bool:
    u = url.strip()
    if not u or u.startswith("#"):
        return True  # Anker oder leer behandeln wir als "extern" für den Rewriter
    low = u.lower()
    return low.startswith(_EXTERNAL_SCHEMES)

def _strip_md_and_index(p: PurePosixPath) -> PurePosixPath:
    """
    Wandelt Pfade wie 'foo/bar.md' → 'foo/bar/' und 'foo/index.md' → 'foo/'
    """
    if p.name.lower() in ("readme.md", "_index.md"):
        return p.parent
    if p.name.lower() == "index.md":
        return p.parent
    if p.suffix.lower() == ".md":
        return p.with_suffix("")
    return p

def _resolve_relative(target_raw: str, current_dir_rel: PurePosixPath) -> PurePosixPath:
    """
    Löst relative Links ('../x', './y', 'z') gegen das Verzeichnis des aktuellen
    Dokuments (relativ zum Sprachwurzelordner) auf.
    """
    # Normalisieren auf posix
    t = target_raw.strip().replace("\\", "/")
    if t.startswith("./"):
        t = t[2:]
    # pathlib löst '..' sauber auf
    candidate = (current_dir_rel / t).resolve().relative_to(Path.cwd().resolve())
    # Die obige resolve/relative_to-Nummer funktioniert nur stabil, wenn current_dir_rel
    # bereits relativ zu CWD ist. Fallback:
    try:
        return PurePosixPath(str(candidate))
    except Exception:
        # Rein logische Auflösung
        parts = list(current_dir_rel.parts)
        for seg in t.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(seg)
        return PurePosixPath(*parts)

_HREF_RE = re.compile(r'''(?P<attr>\b(?:href|src)\s*=\s*)(?P<q>["']?)(?P<url>[^"'\s>]+)(?P=q)''', re.IGNORECASE)

def _to_wissen_abs(lang: str, target_rel_to_lang: PurePosixPath) -> str:
    # Pretty-URL: immer mit abschließendem Slash
    pretty = _strip_md_and_index(target_rel_to_lang)
    s = f"/wissen/{lang}/{pretty.as_posix().lstrip('/')}"
    if not s.endswith("/"):
        s += "/"
    return s

def rewrite_links_in_html(html_text: str, lang: str, current_doc_rel_dir: PurePosixPath) -> str:
    """
    Rewrites all internal links to /wissen/<lang>/...
    """
    def repl(m: re.Match) -> str:
        attr, q, url = m.group("attr"), m.group("q") or '"', m.group("url")
        u = url.strip()

        # Keine Umschreibung für externe Ziele oder reine Anker
        if is_external(u) or u.startswith("#"):
            return f'{attr}{q}{u}{q}'

        # Bereits korrekt sprachpräfixierte /wissen/<lang>/... belassen
        low = u.lower()
        if low.startswith(f"/wissen/{lang}/"):
            return f'{attr}{q}{u}{q}'

        # /wissen/ ohne Sprachpräfix → Sprachpräfix ergänzen
        if low.startswith("/wissen/") and not low.startswith(f"/wissen/{lang}/"):
            rest = u.split("/wissen/", 1)[1].lstrip("/")
            return f'{attr}{q}/wissen/{lang}/{rest}{"/" if not rest.endswith("/") else ""}{q}'

        # Sprachpräfix fälschlich als /de/ oder /en/ direkt hinter Root → in /wissen/<lang>/ umwandeln
        if low.startswith("/de/") or low.startswith("/en/"):
            rest = u.split("/", 2)[2] if u.count("/") >= 2 else ""
            return f'{attr}{q}/wissen/{lang}/{rest}{"/" if rest and not rest.endswith("/") else ""}{q}'

        # Root-absolute interne Pfade ("/foo/bar") → /wissen/<lang>/foo/bar
        if low.startswith("/"):
            rest = u.lstrip("/")
            return f'{attr}{q}/wissen/{lang}/{rest}{"/" if not rest.endswith("/") else ""}{q}'

        # Relative Pfade → gegen aktuelles Verzeichnis auflösen
        resolved = _resolve_relative(u, current_doc_rel_dir)
        return f'{attr}{q}{_to_wissen_abs(lang, resolved)}{q}'

    return _HREF_RE.sub(repl, html_text)

def render_markdown(md_text: str) -> str:
    try:
        return markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except Exception:
        # Minimal-Fallback (no deps)
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

def collect_md_files() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for lang in SRC_LANGS:
        root = REPO_ROOT / lang
        if not root.is_dir():
            continue
        for p in root.rglob("*.md"):
            out.append((lang, p))
    return out

def out_path_for(lang: str, src_path: Path) -> Path:
    rel = src_path.relative_to(REPO_ROOT / lang)
    # index.md → Zielverzeichnis
    if rel.name.lower() in ("index.md", "_index.md", "readme.md"):
        target_dir = OUT_ROOT / lang / rel.parent
        return target_dir / "index.html"
    # foo.md → foo/index.html
    target_dir = OUT_ROOT / lang / rel.with_suffix("")
    return target_dir / "index.html"

def build_sitemap(entries: list[str], out_file: Path, base_url: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = []
    for e in sorted(set(entries)):
        loc = f"{base_url.rstrip('/')}/{e.lstrip('/')}"
        urls.append(f"<url><loc>{html.escape(loc)}</loc><lastmod>{ts}</lastmod></url>")
    xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" \
          "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + \
          "\n".join(urls) + "\n</urlset>\n"
    out_file.write_text(xml, encoding="utf-8")

def write_robots(out_file: Path, base_url: str) -> None:
    txt = f"""User-agent: *
Allow: /wissen/
Sitemap: {base_url.rstrip('/')}/sitemap.xml
"""
    out_file.write_text(txt, encoding="utf-8")

def copy_assets():
    # Whitelist: nur assets nach site/assets kopieren (falls vorhanden)
    dst = OUT_ROOT / "assets"
    if dst.exists():
        shutil.rmtree(dst)
    if ASSETS_DIR.is_dir():
        shutil.copytree(ASSETS_DIR, dst)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://www.vertaefelungen.de/wissen")
    args = ap.parse_args()

    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    copy_assets()

    sitemap_entries: list[str] = []

    for lang, src_path in collect_md_files():
        md = src_path.read_text(encoding="utf-8")
        html_body = render_markdown(md)
        # current_doc_rel_dir: z. B. '' oder 'oeffentlich/produkte/...'
        current_rel_dir = PurePosixPath(
            str(src_path.relative_to(REPO_ROOT / lang).parent).replace("\\", "/")
        )
        rewritten = rewrite_links_in_html(html_body, lang=lang, current_doc_rel_dir=current_rel_dir)
        doc_html = write_html_document(rewritten, title="Wissen")

        out_file = out_path_for(lang, src_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(doc_html, encoding="utf-8")

        # Sitemap-Eintrag: relative URL unterhalb /wissen/
        rel_url = str(out_file.relative_to(OUT_ROOT)).replace("\\", "/")
        sitemap_entries.append(rel_url)

    # Sitemap & robots
    build_sitemap(sitemap_entries, OUT_ROOT / "sitemap.xml", args.base_url)
    write_robots(OUT_ROOT / "robots.txt", args.base_url)

    # Build-Marker zur Deploy-Verifikation
    version = {
        "built_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "builder": "build_site.py",
        "base_url": args.base_url,
        "pages": len(sitemap_entries),
    }
    (OUT_ROOT / "version.json").write_text(json.dumps(version, ensure_ascii=False, indent=2), encoding="utf-8")

    # Root-Index: serverseitige Redirect-Regel kommt zusätzlich aus .htaccess
    (OUT_ROOT / "index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=/wissen/de/">'
        '<link rel="canonical" href="/wissen/de/">Weiterleitung …',
        encoding="utf-8"
    )

    print(f"[build_site] Fertig: {OUT_ROOT}")

if __name__ == "__main__":
    sys.exit(main())
