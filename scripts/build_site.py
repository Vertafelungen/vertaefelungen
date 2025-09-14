#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py
Version: 2025-09-14 19:35 (Europe/Berlin)

Build static HTML pages from Markdown (de/en) into /site.
- Renders README.md -> index.html, other *.md -> <name>.html
- Parses YAML front matter at the top (--- ... ---)
- Ensures index pages (README.md) for key folders if missing
- Normalizes paths and writes UTF-8 with BOM-safe handling

Usage:
  python scripts/build_site.py \
      --content-root . \
      --out-dir site \
      --base-url "https://www.vertaefelungen.de/wissen"
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional

import markdown  # >=3.6
import yaml      # >=6.0.1


# ----------------------------
# Utilities
# ----------------------------

def read_text_utf8(path: Path) -> str:
    # Strict UTF-8 read; fail fast with helpful message
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def safe_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" to avoid CRLF surprises on runner
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def split_front_matter(src: str) -> Tuple[Dict, str]:
    """
    Extract YAML front matter from the top of a markdown file.

    Front matter must start at the very beginning:

        ---
        key: value
        ---
        # Markdown Content

    Returns (meta_dict, body_text).
    If no front matter is found, returns ({}, original_text).
    """
    if not src.startswith("---"):
        return {}, src

    # Find closing '---' on a line by itself
    # We read line-by-line to be resilient against large files
    buf = io.StringIO(src)
    first = buf.readline()
    if first.strip() != "---":
        return {}, src

    yaml_lines = []
    for line in buf:
        if line.strip() == "---":
            # end of YAML
            break
        yaml_lines.append(line)
    else:
        # No closing '---'
        return {}, src

    # The rest is the markdown body
    body = buf.read()

    meta: Dict = {}
    yaml_text = "".join(yaml_lines)
    if yaml_text.strip():
        try:
            meta = yaml.safe_load(yaml_text) or {}
            if not isinstance(meta, dict):
                meta = {}
        except Exception as e:
            raise ValueError(
                f"YAML front matter parse error: {e}"
            ) from e
    return meta, body


def md_to_html(md_text: str, base_url: Optional[str]) -> str:
    """
    Convert Markdown to HTML.
    """
    extensions = [
        "extra",
        "toc",
        "sane_lists",
        "smarty",
    ]
    extension_configs = {
        "toc": {"permalink": True},
    }
    html = markdown.markdown(md_text, extensions=extensions,
                             extension_configs=extension_configs,
                             output_format="html5")
    return html


def target_html_path(out_dir: Path, lang: str, src_md: Path, content_root: Path) -> Path:
    """
    Compute target HTML path for a given source markdown file.
    README.md -> index.html
    foo.md    -> foo.html
    """
    rel = src_md.relative_to(content_root / lang)
    if src_md.name.lower() == "readme.md":
        # e.g. de/faq/README.md -> site/de/faq/index.html
        return out_dir / lang / rel.parent / "index.html"
    else:
        # e.g. de/faq/lieferung.md -> site/de/faq/lieferung.html
        return out_dir / lang / rel.with_suffix(".html")


def ensure_index(folder: Path, title: str) -> None:
    """
    Make sure a README.md exists in folder. If missing, create a minimal stub.
    """
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.md"
    if not readme.exists():
        stub = f"""---
titel: {title}
---

# {title}

*Inhalt folgt.*
"""
        safe_write_text(readme, stub)


# ----------------------------
# Build process
# ----------------------------

def render_markdown(src_md: Path, out_html: Path, base_url: Optional[str]) -> None:
    src_text = read_text_utf8(src_md)
    meta, body = split_front_matter(src_text)

    # Title for template
    title = meta.get("titel") or meta.get("title") or ""

    html_body = md_to_html(body, base_url)

    # Minimal HTML template (you can replace with a file/template engine later)
    html = f"""<!doctype html>
<html lang="{'de' if 'de' in out_html.parts else 'en'}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
</head>
<body>
{html_body}
</body>
</html>
"""
    safe_write_text(out_html, html)
    print(f"✅ gebaut: {out_html.as_posix()}")


def build_language(
    lang: str,
    content_root: Path,
    out_dir: Path,
    base_url: Optional[str],
) -> None:
    """
    Build a single language (de/en).
    """
    lang_root = content_root / lang
    if not lang_root.exists():
        print(f"⚠️  Sprache '{lang}' nicht gefunden: {lang_root}")
        return

    # WICHTIG: Index für /oeffentlich/produkte sicherstellen (geänderter Pfad!)
    products_folder = lang_root / "oeffentlich" / "produkte"
    ensure_index(products_folder, "Produkte" if lang == "de" else "Products")

    # Optional: weitere Ordner-Indexe zentral erzwingen (Beispiele)
    # ensure_index(lang_root / "faq", "FAQ" if lang == "en" else "FAQ")
    # ensure_index(lang_root / "docs", "Dokumente" if lang == "de" else "Documents")

    # Alle *.md rendern
    for src_md in lang_root.rglob("*.md"):
        # Nur echte Dateien
        if not src_md.is_file():
            continue
        out_html = target_html_path(out_dir, lang, src_md, content_root)
        try:
            render_markdown(src_md, out_html, base_url)
        except UnicodeDecodeError as e:
            print(f"❌ UTF-8 Fehler in {src_md}: {e}")
            raise
        except Exception as e:
            print(f"❌ Render-Fehler in {src_md}: {e}")
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Markdown to static HTML.")
    parser.add_argument("--content-root", default=".", help="Root with language folders de/en")
    parser.add_argument("--out-dir", default="site", help="Output folder")
    parser.add_argument("--base-url", default="", help="Optional absolute base URL (without trailing slash)")
    args = parser.parse_args()

    content_root = Path(args.content_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    base_url = args.base_url.strip() or None

    # Clean or create output dir
    out_dir.mkdir(parents=True, exist_ok=True)

    for lang in ("de", "en"):
        build_language(lang, content_root, out_dir, base_url)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail with non-zero exit for CI, but show a helpful message
        print(f"\n💥 Build abgebrochen: {exc}\n", file=sys.stderr)
        raise
