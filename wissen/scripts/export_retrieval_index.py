#!/usr/bin/env python3
"""Export a retrieval-friendly JSON index from built Hugo HTML output."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin
import re

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT / "wissen" / "public"
SOURCE_LABEL = "vertaefelungen-main / Phase 6.1"

EXCLUDED_FILES = {"404.html", "index.xml", "sitemap.xml", "robots.txt"}
PLACEHOLDER_MARKERS = {
    "Platzhalter",
    "In Vorbereitung",
    "Weitere Inhalte folgen",
}

CONTENT_ID_KEYS = {"content_id", "content-id", "contentid"}
CONTENT_TYPE_KEYS = {"content_type", "content-type", "contenttype"}
TOPIC_KEYS = {"topic", "content_topic", "content-topic"}
AUDIENCE_KEYS = {"audience", "content_audience", "content-audience"}

DATA_ATTR_MAP = {
    "data-content-id": "content_id",
    "data-content_id": "content_id",
    "data-content-type": "content_type",
    "data-content_type": "content_type",
    "data-topic": "topic",
    "data-audience": "audience",
}


@dataclass
class ParsedPage:
    canonical_url: Optional[str] = None
    title_text: Optional[str] = None
    h1_text: Optional[str] = None
    description: Optional[str] = None
    robots: Optional[str] = None
    modified_time: Optional[str] = None
    lastmod: Optional[str] = None
    content_id: str = ""
    content_type: Optional[str] = None
    topic: Optional[str] = None
    audience: Optional[str] = None
    found_main: bool = False
    headings: List[str] = field(default_factory=list)
    main_text_parts: List[str] = field(default_factory=list)


class MainParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.data = ParsedPage()
        self._in_main = False
        self._main_depth = 0
        self._ignore_depth = 0
        self._in_heading: Optional[str] = None
        self._heading_buffer: List[str] = []
        self._in_title = False
        self._title_buffer: List[str] = []
        self._in_h1 = False
        self._h1_buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): v for k, v in attrs}

        self._capture_data_attrs(attrs_dict)

        if tag == "main" and attrs_dict.get("id") == "main" and not self._in_main:
            self._in_main = True
            self._main_depth = 1
            self.data.found_main = True
            self._capture_data_attrs(attrs_dict)
            return

        if self._in_main:
            if tag in {"script", "style"}:
                self._ignore_depth += 1
            if tag in {"h2", "h3"} and self._in_heading is None:
                self._in_heading = tag
                self._heading_buffer = []

        if tag == "title":
            self._in_title = True
            self._title_buffer = []

        if tag == "h1" and self.data.h1_text is None:
            self._in_h1 = True
            self._h1_buffer = []

        if tag == "link":
            rel = (attrs_dict.get("rel") or "").lower()
            href = attrs_dict.get("href")
            if href and "canonical" in rel and not self.data.canonical_url:
                self.data.canonical_url = href

        if tag == "meta":
            name = (attrs_dict.get("name") or "").lower()
            prop = (attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content")
            if not content:
                return
            if name == "description" and self.data.description is None:
                self.data.description = content
            if name == "robots" and self.data.robots is None:
                self.data.robots = content
            if prop == "article:modified_time" and self.data.modified_time is None:
                self.data.modified_time = content
            if (name == "lastmod" or prop == "lastmod") and self.data.lastmod is None:
                self.data.lastmod = content

            field_key = name or prop
            if field_key in CONTENT_ID_KEYS and not self.data.content_id:
                self.data.content_id = content
            if field_key in CONTENT_TYPE_KEYS and self.data.content_type is None:
                self.data.content_type = content
            if field_key in TOPIC_KEYS and self.data.topic is None:
                self.data.topic = content
            if field_key in AUDIENCE_KEYS and self.data.audience is None:
                self.data.audience = content

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._in_main:
            if tag == "main":
                self._main_depth -= 1
                if self._main_depth <= 0:
                    self._in_main = False
            if tag in {"script", "style"} and self._ignore_depth:
                self._ignore_depth -= 1
            if self._in_heading == tag:
                text = normalize_text("".join(self._heading_buffer))
                if text:
                    self.data.headings.append(text)
                self._in_heading = None
                self._heading_buffer = []

        if tag == "title" and self._in_title:
            text = normalize_text("".join(self._title_buffer))
            self.data.title_text = text or self.data.title_text
            self._in_title = False

        if tag == "h1" and self._in_h1:
            text = normalize_text("".join(self._h1_buffer))
            if text:
                self.data.h1_text = text
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_buffer.append(data)
        if self._in_h1:
            self._h1_buffer.append(data)
        if not self._in_main or self._ignore_depth:
            return
        if self._in_heading is not None:
            self._heading_buffer.append(data)
        self.data.main_text_parts.append(data)

    def _capture_data_attrs(self, attrs: Dict[str, Optional[str]]) -> None:
        for key, target in DATA_ATTR_MAP.items():
            value = attrs.get(key)
            if not value:
                continue
            if target == "content_id" and not self.data.content_id:
                self.data.content_id = value
            elif target == "content_type" and self.data.content_type is None:
                self.data.content_type = value
            elif target == "topic" and self.data.topic is None:
                self.data.topic = value
            elif target == "audience" and self.data.audience is None:
                self.data.audience = value


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def load_base_url(repo_root: Path) -> str:
    config_path = repo_root / "wissen" / "hugo.toml"
    if not config_path.exists():
        return ""
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
        base_url = str(data.get("baseURL", "")).strip()
    except Exception:
        return ""
    if base_url and not base_url.endswith("/"):
        base_url += "/"
    return base_url


def to_fallback_url(path: Path, root: Path, base_url: str) -> str:
    rel = path.relative_to(root).as_posix()
    if rel.endswith("index.html"):
        rel = rel[: -len("index.html")]
    if rel and not rel.endswith("/") and not rel.endswith(".html"):
        rel += "/"
    if base_url:
        return urljoin(base_url, rel)
    return "/" + rel.lstrip("/")


def detect_lang(url: str) -> str:
    match = re.search(r"/wissen/(de|en)/", url)
    if match:
        return match.group(1)
    match = re.search(r"/(de|en)/", url)
    if match:
        return match.group(1)
    return ""


def truncate_text(text: str, max_len: int) -> tuple[str, bool]:
    marker = "…[truncated]"
    if len(text) <= max_len:
        return text, False
    if max_len <= len(marker):
        return marker[:max_len], True
    return text[: max_len - len(marker)] + marker, True


def parse_html(path: Path) -> ParsedPage:
    parser = MainParser()
    html = path.read_text(encoding="utf-8")
    parser.feed(html)
    parser.close()
    return parser.data


def build_page_entry(
    parsed: ParsedPage,
    url: str,
    lang: str,
    max_body_len: int,
) -> Dict[str, object]:
    title = parsed.title_text or parsed.h1_text or ""
    description = parsed.description or ""
    updated_at = parsed.modified_time or parsed.lastmod or ""
    robots = (parsed.robots or "").lower()
    indexable = "noindex" not in robots

    body_text = normalize_text(" ".join(parsed.main_text_parts))
    body_text, _ = truncate_text(body_text, max_body_len)

    entry: Dict[str, object] = {
        "url": url,
        "lang": lang,
        "title": title,
        "description": description,
        "headings": parsed.headings,
        "body_text": body_text,
        "updated_at": updated_at,
        "indexable": indexable,
        "content_id": parsed.content_id or "",
        "is_placeholder": body_text in PLACEHOLDER_MARKERS,
    }
    if parsed.content_type:
        entry["content_type"] = parsed.content_type
    if parsed.topic:
        entry["topic"] = parsed.topic
    if parsed.audience:
        entry["audience"] = parsed.audience
    return entry


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser(description="Export retrieval index JSON from public HTML.")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="Root directory with built HTML")
    ap.add_argument(
        "--report",
        default="artifacts/retrieval_export_report.json",
        help="Path to write JSON report",
    )
    ap.add_argument(
        "--base-url",
        default=None,
        help="Override base URL for fallback URL generation",
    )
    ap.add_argument("--max-body-length", type=int, default=12000)
    args = ap.parse_args()

    root = Path(args.root)
    base_url = args.base_url or load_base_url(REPO_ROOT)
    report_path = Path(args.report)

    html_files = sorted(p for p in root.rglob("*.html") if p.name not in EXCLUDED_FILES)
    pages_by_lang: Dict[str, List[Dict[str, object]]] = {"de": [], "en": []}

    warnings: List[str] = []
    skipped_missing_main: List[str] = []
    skipped_unknown_lang: List[str] = []

    for html_path in html_files:
        parsed = parse_html(html_path)
        if not parsed.found_main:
            rel = html_path.relative_to(root).as_posix()
            skipped_missing_main.append(rel)
            continue

        fallback_url = to_fallback_url(html_path, root, base_url)
        canonical = parsed.canonical_url
        if canonical:
            url = urljoin(base_url or fallback_url, canonical)
        else:
            url = fallback_url

        lang = detect_lang(url)
        if not lang:
            skipped_unknown_lang.append(html_path.relative_to(root).as_posix())
            continue

        entry = build_page_entry(parsed, url, lang, args.max_body_length)
        if lang in pages_by_lang:
            pages_by_lang[lang].append(entry)

    for lang in pages_by_lang:
        pages_by_lang[lang] = sorted(pages_by_lang[lang], key=lambda item: str(item.get("url", "")))

    export_dir = root / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    generated_at = iso_timestamp()
    for lang, pages in pages_by_lang.items():
        output = {
            "generated_at": generated_at,
            "source": SOURCE_LABEL,
            "pages": pages,
        }
        output_path = export_dir / f"index.{lang}.json"
        output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if skipped_missing_main:
        warnings.append(f"Missing <main id=\"main\"> in {len(skipped_missing_main)} page(s).")
    if skipped_unknown_lang:
        warnings.append(f"Unknown language in {len(skipped_unknown_lang)} page(s).")

    report = {
        "generated_at": generated_at,
        "source": SOURCE_LABEL,
        "root": str(root),
        "files_scanned": len(html_files),
        "pages_written": {lang: len(pages) for lang, pages in pages_by_lang.items()},
        "skipped": {
            "missing_main": skipped_missing_main,
            "unknown_lang": skipped_unknown_lang,
        },
        "warnings": warnings,
    }

    if report_path.parent:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Exported {sum(len(p) for p in pages_by_lang.values())} pages.")
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
