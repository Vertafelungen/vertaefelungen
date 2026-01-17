#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
import tomllib
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLIC_DIR = ROOT / "public"
DEFAULT_CONFIG = ROOT / "hugo.toml"
DEFAULT_PAGES = [
    "/wissen/de/faq/",
    "/wissen/de/produkte/",
    "/wissen/de/lookbook/",
    "/wissen/en/faq/",
    "/wissen/en/products/",
]


def load_base_url() -> str:
    env_url = os.environ.get("HUGO_BASE_URL")
    if env_url:
        return env_url
    if DEFAULT_CONFIG.exists():
        data = tomllib.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        return data.get("baseURL", "").strip()
    return ""


def load_pages() -> list[str]:
    env_pages = os.environ.get("HUGO_SEO_CHECK_PAGES")
    if env_pages:
        return [p.strip() for p in env_pages.split(",") if p.strip()]
    return DEFAULT_PAGES


def html_links(html: str, rel: str) -> list[str]:
    pattern = re.compile(rf"<link[^>]+rel=[\"']{rel}[\"'][^>]*>", re.IGNORECASE)
    matches = pattern.findall(html)
    hrefs = []
    for tag in matches:
        href_match = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        if href_match:
            hrefs.append(unescape(href_match.group(1)))
    return hrefs


def html_hreflang_links(html: str) -> dict[str, str]:
    pattern = re.compile(r"<link[^>]+rel=[\"']alternate[\"'][^>]*>", re.IGNORECASE)
    links: dict[str, str] = {}
    for tag in pattern.findall(html):
        hreflang_match = re.search(r"hreflang=[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        href_match = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        if hreflang_match and href_match:
            links[hreflang_match.group(1).lower()] = unescape(href_match.group(1))
    return links


def candidate_paths(base_url: str, url: str) -> Iterable[Path]:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        url_path = parsed.path
    else:
        url_path = url
    url_path = url_path or "/"
    if not url_path.startswith("/"):
        url_path = f"/{url_path}"

    base_path = ""
    if base_url:
        base_parsed = urlparse(base_url)
        base_path = base_parsed.path.rstrip("/")

    path_variants = [url_path]
    if base_path and url_path.startswith(base_path + "/"):
        path_variants.append(url_path[len(base_path) :])

    for variant in path_variants:
        relative = variant.lstrip("/")
        if relative.endswith(".html"):
            yield Path(relative)
        else:
            yield Path(relative) / "index.html"


def assert_exists(public_dir: Path, url: str, base_url: str) -> None:
    for candidate in candidate_paths(base_url, url):
        if (public_dir / candidate).exists():
            return
    raise AssertionError(f"Expected URL to resolve to a file: {url}")


def main() -> int:
    public_dir = Path(os.environ.get("HUGO_PUBLIC_DIR", DEFAULT_PUBLIC_DIR)).resolve()
    base_url = load_base_url()
    pages = load_pages()

    if not public_dir.exists():
        print(f"Public directory not found: {public_dir}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for page in pages:
        page_path_candidates = list(candidate_paths(base_url, page))
        page_file = next((public_dir / p for p in page_path_candidates if (public_dir / p).exists()), None)
        if not page_file:
            errors.append(f"Page not found for {page}")
            continue

        html = page_file.read_text(encoding="utf-8")
        canonicals = html_links(html, "canonical")
        if len(canonicals) != 1:
            errors.append(f"{page}: expected 1 canonical, found {len(canonicals)}")
            continue

        canonical_url = canonicals[0]
        try:
            assert_exists(public_dir, canonical_url, base_url)
        except AssertionError as exc:
            errors.append(f"{page}: {exc}")

        hreflangs = html_hreflang_links(html)
        for lang in ("de", "en"):
            if lang not in hreflangs:
                errors.append(f"{page}: missing hreflang {lang}")
                continue
            try:
                assert_exists(public_dir, hreflangs[lang], base_url)
            except AssertionError as exc:
                errors.append(f"{page}: {exc}")

    if errors:
        print("SEO smoke check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("SEO smoke check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
