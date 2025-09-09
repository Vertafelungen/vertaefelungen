#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static Markdown → HTML Builder für /wissen
Version: 2025-09-09 12:55 (Europe/Berlin)

Neu in dieser Version:
- Asset-Links (Dateiendung) bleiben relativ; nur Seiten-Links werden auf /wissen/<lang>/… normalisiert.
- Kopiert alle Nicht-Markdown-Dateien aus de/ und en/ 1:1 nach site/<lang>/…
- Erzeugt automatisch Pretty-URL-ALIASSE für fehlende Produkt-Variantenslugs:
  z.B. site/de/.../p0009-1-1-1-c/index.html → Redirect auf /wissen/de/.../p0009/
- Root-/wissen/-Fix, kein Slash an Dateipfaden, Alias-Redirects für FAQ-Kurzpfade,
  Sitemap/robots/version & Root-Redirect bleiben.
"""

from __future__ import annotations
import argparse, html, json, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    import markdown  # type: ignore
except Exception:
    print("[build_site] Hinweis: 'markdown' wird in der Action installiert.", file=sys.stderr)

# ----------------------------- Utilities -------------------------------------

_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp://", "ftps://")
_ATTR_RE = re.compile(r'''(?P<attr>\b(?:href|src)\s*=\s*)(?P<q>["']?)(?P<url>[^"'\s>]+)(?P=q)''',
                      re.IGNORECASE)
_ASSET_EXT = re.compile(r"""\.[A-Za-z0-9]{1,8}(?:[?#].*)?$""")  # .png .jpg .css .js .pdf …

# Produkt-Slug-Erkennung
# Basis: p0009  — Varianten: p0009-1-1-1-c etc.
_BASE_PROD_RE = re.compile(r"""(^|/)p(\d{4,})(/|$)""")
_VARIANT_PROD_RE = re.compile(r"""(^|/)p(\d{4,})(-[^/]+)+(/)?$""")

def is_external(url: str) -> bool:
    u = url.strip()
    if not u or u.startswith("#"):
        return True
    return u.lower().startswith(_EXTERNAL_SCHEMES)

def looks_like_file(path: str) -> bool:
    """Heuristik: hat der Pfad eine Dateiendung?"""
    return bool(_ASSET_EXT.search(path))

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
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return PurePosixPath(*parts)

def _to_wissen_abs(lang: str, target_rel_to_lang: PurePosixPath) -> str:
    """Aus Pfad relativ zu <lang>-Root eine hübsche absolute Wissen-URL machen."""
    pretty = _strip_md_and_index(target_rel_to_lang)
    s = f"/wissen/{lang}/{pretty.as_posix().lstrip('/')}"
    if not looks_like_file(s) and not s.endswith("/"):
        s += "/"
    return s

# --------------------------- Link-Rewriter -----------------------------------

def rewrite_links_in_html(html_text: str, lang: str, current_doc_rel_dir: PurePosixPath) -> str:
    """
    Pass 1:
    - Seitenlinks → /wissen/<lang>/…
    - Asset-Links (Dateien mit Endung):
        * Relativ (z. B. "bild.png", "../img/a.jpg") → UNVERÄNDERT (Validator erwartet relative Einbindung).
        * Root-absolute ("/…") → /wissen/<lang>/… mit korrekt gesetztem Slash/ohne bei Dateien.
    """
    def repl(m: re.Match) -> str:
        attr, q, url = m.group("attr"), (m.group("q") or '"'), m.group("url")
        u = url.strip()
        low = u.lower()

        # Externes oder Anker → unverändert
        if is_external(u) or u.startswith("#"):
            return f'{attr}{q}{u}{q}'

        def join_lang(rest: str) -> str:
            rest_clean = rest.lstrip("/")
            if looks_like_file(rest_clean):
                tail = ""
            else:
                tail = "" if rest_clean.endswith("/") else "/"
            return f'/wissen/{lang}/{rest_clean}{tail}'

        is_file_like = looks_like_file(u)

        # Bereits korrekt /wissen/<lang>/…
        if low.startswith(f"/wissen/{lang}/"):
            return f'{attr}{q}{u}{q}'

        # Root-absolute /wissen/… ohne korrektes Präfix → ergänzen
        if low.startswith("/wissen/") and not low.startswith(f"/wissen/{lang}/"):
            rest = u.split("/wissen/", 1)[1]
            return f'{attr}{q}{join_lang(rest)}{q}'

        # Root-absolute /de/...|/en/... → /wissen/<lang>/…
        if low.startswith("/de/") or low.startswith("/en/"):
            rest = u.split("/", 2)[2] if u.count("/") >= 2 else ""
            return f'{attr}{q}{join_lang(rest)}{q}'

        # Sonstige Root-absolute "/" → /wissen/<lang>/…
        if low.startswith("/"):
            rest = u.lstrip("/")
            return f'{attr}{q}{join_lang(rest)}{q}'

        # *** Relativpfade ***
        if is_file_like:
            # Assets relativ bleiben relativ
            return f'{attr}{q}{u}{q}'

        # Seiten relativ → auf /wissen/<lang>/… normalisieren
        resolved = _resolve_relative(u, current_doc_rel_dir)
        return f'{attr}{q}{_to_wissen_abs(lang, resolved)}{q}'

    return _ATTR_RE.sub(repl, html_text)

# Pass 2: verbleibende /wissen/-Root-Links ohne Sprachpräfix reparieren
_ROOT_WISSEN_FIX = re.compile(
    r'''(?P<attr>\b(?:href|src)\s*=\s*)(?P<q>["']?)\s*/\s*wissen\s*/\s*(?P<rest>[^"'\s>]*)\s*(?P=q)''',
    re.IGNORECASE
)

def finalize_root_links(html_text: str, lang: str) -> str:
    def repl(m: re.Match) -> str:
        attr, q = m.group("attr"), (m.group("q") or '"')
        rest = (m.group("rest") or "").lstrip("/")

        if not rest:
            return f'{attr}{q}/wissen/{lang}/{q}'

        if rest.lower().startswith(("de/", "en/")):
            return f'{attr}{q}/wissen/{rest}{q}'

        tail = "" if (looks_like_file(rest) or rest.endswith("/")) else "/"
        return f'{attr}{q}/wissen/{lang}/{rest}{tail}{q}'
    return _ROOT_WISSEN_FIX.sub(repl, html_text)

# Pass 3: harte Absicherung
def extra_safety_pass(html_text: str, lang: str) -> str:
    html_text = html_text.replace('href="/wissen/"', f'href="/wissen/{lang}/"')
    html_text = html_text.replace("href='/wissen/'", f"href='/wissen/{lang}/'")
    return html_text

# ------------------------------ Rendering ------------------------------------

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

# ------------------------------ Alias-Redirects ------------------------------

def write_redirect_index(to_url_abs: str) -> str:
    return (
        '<!doctype html><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0; url={html.escape(to_url_abs)}">'
        f'<link rel="canonical" href="{html.escape(to_url_abs)}">Weiterleitung …'
    )

def create_faq_alias_redirects(out_root: Path) -> list[str]:
    """Kurze FAQ-URLs → Themen-Ordner."""
    added: list[str] = []
    rules = [
        ("de", "oeffentlich/faq/themen", "oeffentlich/faq"),
        ("en", "public/faq/topics", "public/faq"),
    ]
    for lang, src_base, alias_base in rules:
        src_dir = out_root / lang / src_base
        alias_dir = out_root / lang / alias_base
        if not src_dir.is_dir():
            continue
        for child in src_dir.iterdir():
            if not child.is_dir():
                continue
            slug = child.name
            target_abs = f"/wissen/{lang}/{src_base}/{slug}/"
            alias_target_dir = alias_dir / slug
            alias_index = alias_target_dir / "index.html"
            if not alias_index.exists():
                alias_target_dir.mkdir(parents=True, exist_ok=True)
                alias_index.write_text(write_redirect_index(target_abs), encoding="utf-8")
                added.append(f"{lang}/{alias_base}/{slug}/index.html")
    return added

def create_missing_variant_aliases(out_root: Path) -> list[str]:
    """
    Sucht in allen HTML-Dateien nach Links auf Varianten-Slugs (pNNNN-.../).
    Falls es keine Seite site/<lang>/.../<variant>/index.html gibt, wird ein
    Redirect dorthin erzeugt, der auf die Basis pNNNN/ verweist.
    """
    created: list[str] = []

    def ensure_alias(lang: str, base_dir: Path, variant_dir: Path):
        alias_index = variant_dir / "index.html"
        if alias_index.exists():
            return
        # Ziel: Basis-Seite (Pretty URL)
        rel_from_lang = variant_dir.relative_to(out_root / lang)
        target_abs = f"/wissen/{lang}/{rel_from_lang.as_posix().rsplit('/', 1)[0]}/"
        # base_dir ist der pNNNN-Ordner
        target_abs = f"/wissen/{lang}/{base_dir.relative_to(out_root / lang).as_posix().rstrip('/')}/"
        variant_dir.mkdir(parents=True, exist_ok=True)
        alias_index.write_text(write_redirect_index(target_abs), encoding="utf-8")
        created.append(str(alias_index.relative_to(out_root)))

    for html_file in out_root.rglob("*.html"):
        text = html_file.read_text(errors="ignore")
        for m in re.finditer(r'href=["\'](/wissen/(de|en)/[^"\']+)["\']', text, flags=re.IGNORECASE):
            url = m.group(1)
            # Nur Varianten-Pattern zulassen
            if not _VARIANT_PROD_RE.search(url.split("/wissen/",1)[1]):
                continue
            # Zielpfad unter site/
            rel = url.split("/wissen/", 1)[1].lstrip("/")
            lang = rel.split("/", 1)[0]
            rest = rel.split("/", 1)[1] if "/" in rel else ""
            target_dir = out_root / lang / rest.strip("/")
            # base_dir = …/pNNNN
            parts = target_dir.parts
            # finde pNNNN-Teil
            base_dir = None
            for i in range(len(parts)):
                if re.fullmatch(r"p\d{4,}", parts[i] or ""):
                    base_dir = Path(*parts[: i + 1])
            if base_dir is None:
                continue
            # Variante ist target_dir; Basis ist base_dir
            ensure_alias(lang, base_dir, target_dir)

    return created

# ------------------------ Assets aus de/ und en/ kopieren --------------------

_IGNORE_NAMES = {".DS_Store", "Thumbs.db"}

def copy_language_assets(lang: str, lang_root: Path, out_root: Path) -> None:
    """Kopiert alle Nicht-Markdown-Dateien aus lang_root nach site/<lang>/… (Struktur beibehalten)."""
    for src in lang_root.rglob("*"):
        if not src.is_file():
            continue
        if src.name in _IGNORE_NAMES:
            continue
        if src.suffix.lower() == ".md":
            continue
        rel = src.relative_to(lang_root)
        dst = out_root / lang / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

# ------------------------------ Sitemap/robots --------------------------------

def build_sitemap(entries: list[str], out_file: Path, base_url: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = []
    for e in sorted(set(entries)):
        loc = f"{base_url.rstrip('/')}/{e.lstrip('/')}"
        urls.append(f"<url><loc>{html.escape(loc)}</loc><lastmod>{ts}</lastmod></url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "\n".join(urls) + "\n</urlset>\n"
    )
    out_file.write_text(xml, encoding="utf-8")

def write_robots(out_file: Path, base_url: str) -> None:
    out_file.write_text(
        f"User-agent: *\nAllow: /wissen/\nSitemap: {base_url.rstrip('/')}/sitemap.xml\n",
        encoding="utf-8"
    )

def copy_assets_dir(assets_dir: Path, out_root: Path) -> None:
    dst = out_root / "assets"
    if dst.exists():
        shutil.rmtree(dst)
    if assets_dir.is_dir():
        shutil.copytree(assets_dir, dst)

# ----------------------------------- Main ------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://www.vertaefelungen.de/wissen", type=str)
    ap.add_argument("--content-root", default=".", type=str, help="Repo-Root mit de/ und en/")
    ap.add_argument("--out-dir", default="site", type=str, help="Ausgabeverzeichnis")
    args = ap.parse_args()

    repo_root = Path(args.content_root).resolve()
    out_root  = Path(args.out_dir).resolve()
    lang_dirs = {lang: repo_root / lang for lang in ("de", "en")}
    assets_dir = repo_root / "assets"

    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    copy_assets_dir(assets_dir, out_root)

    sitemap_entries: list[str] = []

    # 1) HTML aus Markdown bauen
    for lang, lang_root in lang_dirs.items():
        if not lang_root.is_dir():
            continue
        for src_path in lang_root.rglob("*.md"):
            md = src_path.read_text(encoding="utf-8")
            html_body = render_markdown(md)

            current_rel_dir = PurePosixPath(
                str(src_path.relative_to(lang_root).parent).replace("\\", "/")
            )
            # Rewriter-Kaskade
            rewritten = rewrite_links_in_html(html_body, lang=lang, current_doc_rel_dir=current_rel_dir)
            rewritten = finalize_root_links(rewritten, lang=lang)
            rewritten = extra_safety_pass(rewritten, lang=lang)

            doc_html = write_html_document(rewritten, title="Wissen")
            out_file = out_path_for(out_root, lang, lang_root, src_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(doc_html, encoding="utf-8")

            rel_url = str(out_file.relative_to(out_root)).replace("\\", "/")
            sitemap_entries.append(rel_url)

    # 2) Nicht-MD-Assets kopieren
    for lang, lang_root in lang_dirs.items():
        if lang_root.is_dir():
            copy_language_assets(lang, lang_root, out_root)

    # 3) Alias-Redirects erzeugen
    sitemap_entries += create_faq_alias_redirects(out_root)
    created_variants = create_missing_variant_aliases(out_root)
    sitemap_entries += created_variants

    # 4) Sitemap/robots/version + Root-Redirect
    build_sitemap(sitemap_entries, out_root / "sitemap.xml", args.base_url)
    write_robots(out_root / "robots.txt", args.base_url)

    out_root.joinpath("version.json").write_text(
        json.dumps({
            "built_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "builder": "build_site.py",
            "base_url": args.base_url,
            "out_dir": str(out_root),
            "content_root": str(repo_root),
            "pages": len(sitemap_entries),
            "created_variant_aliases": created_variants,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Root → /wissen/de/
    out_root.joinpath("index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=/wissen/de/">'
        '<link rel="canonical" href="/wissen/de/">Weiterleitung …',
        encoding="utf-8"
    )

    print(f"[build_site] Fertig: {out_root}")

if __name__ == "__main__":
    sys.exit(main())
