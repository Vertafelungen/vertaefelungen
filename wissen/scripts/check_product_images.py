#!/usr/bin/env python3
"""
Lightweight verification that product pages ship their bundle images.

Usage:
    python scripts/check_product_images.py [public_dir] [page ...]

If no pages are provided, a curated sample set of product detail pages is checked.
The script parses <img> tags, ensures at least one is present, and verifies that
all referenced image targets exist inside the built public/ output.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, List, Tuple
from urllib.parse import urlparse
import sys

SAMPLE_PAGES = [
    "de/oeffentlich/produkte/halbhohe-vertaefelungen/21-p0009/index.html",
    "de/oeffentlich/produkte/halbhohe-vertaefelungen/23-p0001/index.html",
    "de/oeffentlich/produkte/lueftungsrosetten/73-blr5/index.html",
]


class ImgParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        if tag.lower() == "img":
            data = dict(attrs)
            src = data.get("src")
            if src:
                self.sources.append(src)


def _candidate_paths(root: Path, parsed_path: str) -> Iterable[Path]:
    """Return possible file system targets for a generated URL path."""
    relative_path = parsed_path.lstrip("/")
    yield root / relative_path

    # When baseURL contains a path prefix (e.g. /wissen/), generated URLs can
    # legitimately include that prefix even though files live without it in
    # the published folder. Try stripping the prefix as a fallback.
    if relative_path.startswith("wissen/"):
        yield root / relative_path[len("wissen/") :]


def find_missing_targets(root: Path, page: Path) -> Tuple[List[str], List[str]]:
    html = page.read_text(encoding="utf-8")
    parser = ImgParser()
    parser.feed(html)

    missing: List[str] = []
    for src in parser.sources:
        url = urlparse(src)
        candidate_found = False
        for candidate in _candidate_paths(root, url.path):
            if candidate.exists():
                candidate_found = True
                break
        if not candidate_found:
            missing.append(src)

    return parser.sources, missing


def main(argv: List[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("public")
    page_args = argv[2:]
    pages = [Path(p) for p in (page_args or SAMPLE_PAGES)]

    all_ok = True
    for page in pages:
        page_path = root / page
        if not page_path.exists():
            print(f"[ERROR] Page not found: {page_path}")
            all_ok = False
            continue

        sources, missing = find_missing_targets(root, page_path)
        if not sources:
            print(f"[ERROR] No <img> tags found in {page}")
            all_ok = False
            continue

        if missing:
            print(f"[ERROR] Missing targets for {page}:")
            for src in missing:
                print(f"  - {src}")
            all_ok = False
        else:
            print(f"[OK] {page}: {len(sources)} images, all present")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
