# scripts/build_site.py
# Version: 2025-09-22 11:02 (Europe/Berlin)

from __future__ import annotations
import argparse, html, re, shutil
from pathlib import Path
import urllib.parse as up
import markdown

ASSET_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".css", ".js", ".json"}

def try_fix_mojibake(text: str) -> str:
    # Erkennung von mojibake (Ã¼, â€™, Â) und Korrektur durch Neu-Decodierung
    if "Ã" in text or "â" in text or "Â" in text:
        try:
            fixed = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            # Nur zurückgeben, wenn die Umkodierung tatsächlich Zeichen repariert hat:
            if fixed.count("Ã") < text.count("Ã"):
                return fixed
        except Exception:
            pass
    return text

def load_markdown(p: Path) -> str:
    raw = p.read_text(encoding="utf-8", errors="replace")
    raw = html.unescape(raw)
    raw = try_fix_mojibake(raw)
    return raw

def md_to_html(md_text: str) -> str:
    return markdown.markdown(
        md_text,
        extensions=["tables", "toc", "fenced_code", "sane_lists", "attr_list", "md_in_html"],
        output_format="xhtml"
    )

def wrap_html(title: str, body: str, base_url: str, lang: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<base href="{base_url}/{lang}/">
<title>{html.escape(title or "")}</title>
<style>
  body{{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.6;margin:2rem;max-width:60rem}}
  pre,code{{font-family:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace}}
  img{{max-width:100%;height:auto}}
  hr{{margin:2rem 0}}
</style>
</head>
<body>
{body}
</body>
</html>"""

_LINK_RE = re.compile(r'(href|src)=(["\'])(.+?)\2', re.IGNORECASE)

def fix_links_in_html(html_text: str, page_src_dir: Path, lang: str) -> str:
    """Normalisiert interne Links:
       - *.md → *.html
       - /wissen/... ohne Sprachpfad → /wissen/<lang>/...
       - Fehlende Endungen bei internen Zielen → entsprechendes .html oder Slash anhängen."""
    def norm(url: str) -> str:
        if url.startswith(("http://", "https://", "mailto:", "data:", "#")):
            return url
        parsed = up.urlsplit(url)
        path = parsed.path or ""
        # 1. .md → .html
        if path.endswith(".md"):
            path = path[:-3] + ".html"
        # 2. Sprachpräfix für absolute /wissen/-Links ergänzen
        if path.startswith("/wissen/") and not path.startswith(("/wissen/de/", "/wissen/en/")):
            path = f"/wissen/{lang}/" + path[len("/wissen/"):]
        # 3. Wenn Pfad auf existierendes Verzeichnis zeigt → Slash anhängen
        if path and not path.endswith(("/", ".html", ".htm")):
            # Bestimme Pfad relativ zum aktuellen Quellverzeichnis:
            try:
                target_dir = (page_src_dir / path).resolve()
            except Exception:
                target_dir = None
            if target_dir and target_dir.is_dir():
                path = path + "/"
            # 4. Falls es eine MD/HTML-Datei zu einem endungslosen Pfad gibt → .html anhängen
            elif "." not in Path(path).name:
                rel_md = page_src_dir / f"{path}.md"
                rel_html = page_src_dir / f"{path}.html"
                if rel_md.exists() or rel_html.exists():
                    path = path + ".html"
        # Zusammensetzen und zurückgeben
        return up.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
    def repl(m):
        attr, q, url = m.groups()
        return f'{attr}={q}{norm(url)}{q}'
    return _LINK_RE.sub(repl, html_text)

def copy_assets(src_dir: Path, dst_dir: Path) -> None:
    for p in src_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in ASSET_EXT:
            rel = p.relative_to(src_dir)
            out = dst_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)

def build_lang(content_root: Path, out_root: Path, lang: str, base_url: str):
    src = content_root / lang
    if not src.exists():
        return
    for md in src.rglob("*.md"):
        rel = md.relative_to(src)
        if md.name.lower() == "readme.md":
            out_rel = rel.parent / "index.html"
            page_title = rel.parent.name.replace("-", " ").title()
        else:
            out_rel = rel.with_suffix(".html")
            page_title = md.stem
        out = out_root / lang / out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        md_text   = load_markdown(md)
        body_html = md_to_html(md_text)
        body_html = fix_links_in_html(body_html, md.parent, lang=lang)
        page = wrap_html(page_title, body_html, base_url=base_url, lang=lang)
        out.write_text(page, encoding="utf-8")
    copy_assets(src, out_root / lang)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content-root", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--base-url", default="/wissen")
    args = ap.parse_args()
    content_root = Path(args.content_root).resolve()
    out_root     = Path(args.out_dir).resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    for lang in ("de", "en"):
        build_lang(content_root, out_root, lang, base_url=args.base_url)
    print(f"✅ Build abgeschlossen: {out_root}")

if __name__ == "__main__":
    main()
