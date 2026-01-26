#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PUBLIC_ROOT = REPO_ROOT / "wissen" / "public"
DEFAULT_EXPORT_DE = DEFAULT_PUBLIC_ROOT / "export" / "index.de.json"
DEFAULT_EXPORT_EN = DEFAULT_PUBLIC_ROOT / "export" / "index.en.json"
DEFAULT_REPORT_PATH = REPO_ROOT / "wissen" / "scripts" / "reports" / "retrieval_export_verification_report.json"

FORBIDDEN_TOKENS_DE = [
    "shop",
    "faq",
    "produkte",
    "lookbook",
    "impressum",
    "datenschutz",
    "kontakt",
]
FORBIDDEN_TOKENS_EN = [
    "shop",
    "faq",
    "products",
    "lookbook",
    "imprint",
    "privacy",
    "contact",
]


@dataclass
class VerificationResult:
    hard_fail: bool
    issues: list[dict[str, str]]


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Invalid JSON in {path}: {exc}") from exc


def ensure_export_shape(payload: dict, label: str) -> list[dict]:
    for field in ("generated_at", "source", "pages"):
        if field not in payload:
            raise AssertionError(f"{label}: missing top-level field '{field}'.")
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise AssertionError(f"{label}: 'pages' must be a list.")
    if not pages:
        raise AssertionError(f"{label}: 'pages' is empty.")
    return pages


def ensure_sorted_unique(pages: list[dict], label: str) -> None:
    urls = [str(page.get("url", "")) for page in pages]
    if any(not url for url in urls):
        raise AssertionError(f"{label}: missing url in pages.")
    if urls != sorted(urls):
        raise AssertionError(f"{label}: pages are not sorted by url.")
    if len(urls) != len(set(urls)):
        raise AssertionError(f"{label}: duplicate url entries detected.")

    content_ids = [str(page.get("content_id", "")).strip() for page in pages]
    filtered = [cid for cid in content_ids if cid]
    if len(filtered) != len(set(filtered)):
        raise AssertionError(f"{label}: duplicate content_id entries detected.")


def ensure_language_urls(pages: list[dict], lang: str, label: str) -> None:
    expected_fragment = f"/wissen/{lang}/"
    for page in pages:
        url = str(page.get("url", ""))
        if expected_fragment not in url:
            raise AssertionError(f"{label}: url missing '{expected_fragment}': {url}")


def ensure_quality_minimum(pages: list[dict], label: str) -> None:
    for page in pages:
        title = str(page.get("title", "")).strip()
        body_text = str(page.get("body_text", "")).strip()
        if not title:
            raise AssertionError(f"{label}: missing title for {page.get('url', '')}")
        if not body_text:
            raise AssertionError(f"{label}: missing body_text for {page.get('url', '')}")


def select_sample_indices(total: int, sample_size: int = 10) -> list[int]:
    if total <= sample_size:
        return list(range(total))
    indices = {0, total - 1}
    for step in range(1, sample_size - 1):
        idx = round(step * (total - 1) / (sample_size - 1))
        indices.add(idx)
    return sorted(indices)


def url_to_public_path(public_root: Path, url: str) -> Path:
    parsed = urlparse(url)
    path = parsed.path or url
    if not path.startswith("/"):
        path = f"/{path}"
    if path.endswith(".html"):
        return public_root / path.lstrip("/")
    if not path.endswith("/"):
        path = f"{path}/"
    return public_root / path.lstrip("/") / "index.html"


def extract_main_html(html: str) -> str | None:
    match = re.search(r"<main[^>]*\bid=[\"']main[\"'][^>]*>(.*?)</main>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return match.group(1)


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(unescape(text).split())


def has_nav_like_fragments(text: str) -> bool:
    lowered = text.lower()
    tokens = FORBIDDEN_TOKENS_DE + FORBIDDEN_TOKENS_EN
    positions: list[int] = []
    for token in tokens:
        idx = lowered.find(token)
        if idx != -1:
            positions.append(idx)
    if len(positions) < 3:
        return False
    positions.sort()
    window = 240
    for i in range(len(positions) - 2):
        if positions[i + 2] - positions[i] <= window:
            return True
    return False


def extract_headings(main_html: str) -> set[str]:
    headings: set[str] = set()
    for tag in ("h2", "h3"):
        pattern = re.compile(rf"<{tag}[^>]*>(.*?)</{tag}>", re.IGNORECASE | re.DOTALL)
        for match in pattern.findall(main_html):
            text = strip_tags(match)
            if text:
                headings.add(text)
    return headings


def check_sample_pages(
    pages: list[dict],
    public_root: Path,
    issues: list[dict[str, str]],
) -> bool:
    hard_fail = False
    indices = select_sample_indices(len(pages))
    for idx in indices:
        page = pages[idx]
        url = str(page.get("url", ""))
        html_path = url_to_public_path(public_root, url)
        if not html_path.exists():
            issues.append({"url": url, "type": "missing_html", "detail": str(html_path)})
            hard_fail = True
            continue
        html = html_path.read_text(encoding="utf-8")
        main_html = extract_main_html(html)
        if main_html is None:
            issues.append({"url": url, "type": "missing_main_container", "detail": "<main id=\"main\"> not found"})
            hard_fail = True
            continue

        body_text = str(page.get("body_text", ""))
        if has_nav_like_fragments(body_text):
            issues.append({"url": url, "type": "nav_like_body_text", "detail": "navigation/footer tokens clustered"})
            hard_fail = True

        export_headings = {str(h).strip() for h in page.get("headings", []) if str(h).strip()}
        if export_headings:
            html_headings = extract_headings(main_html)
            if not (export_headings & html_headings):
                issues.append({
                    "url": url,
                    "type": "missing_headings_in_html",
                    "detail": f"export has {len(export_headings)} headings, none found in HTML main",
                })
    return hard_fail


def record_soft_issues(pages: list[dict], issues: list[dict[str, str]]) -> None:
    for page in pages:
        url = str(page.get("url", ""))
        description = str(page.get("description", "")).strip()
        body_text = str(page.get("body_text", "")).strip()
        if not description:
            issues.append({"url": url, "type": "missing_description", "detail": "description empty"})
        if len(body_text) < 400:
            issues.append({"url": url, "type": "very_short_body_text", "detail": f"length {len(body_text)}"})
        if page.get("is_placeholder") is True:
            issues.append({"url": url, "type": "is_placeholder", "detail": "is_placeholder true"})
        if page.get("indexable") is False:
            issues.append({"url": url, "type": "indexable_false", "detail": "indexable false"})


def verify_export(path: Path, lang: str, public_root: Path, issues: list[dict[str, str]]) -> VerificationResult:
    label = f"{lang.upper()} export"
    if not path.exists():
        raise AssertionError(f"{label}: file missing at {path}")
    payload = load_json(path)
    pages = ensure_export_shape(payload, label)
    ensure_sorted_unique(pages, label)
    ensure_language_urls(pages, lang, label)
    ensure_quality_minimum(pages, label)
    hard_fail = check_sample_pages(pages, public_root, issues)
    record_soft_issues(pages, issues)
    return VerificationResult(hard_fail=hard_fail, issues=issues)


def write_report(path: Path, hard_fail: bool, checked_pages_de: int, checked_pages_en: int, issues: list[dict[str, str]]) -> None:
    report = {
        "generated_at": iso_timestamp(),
        "summary": {
            "hard_fail": 1 if hard_fail else 0,
            "checked_pages_de": checked_pages_de,
            "checked_pages_en": checked_pages_en,
            "issue_count": len(issues),
        },
        "issues": issues,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_page_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        payload = load_json(path)
    except AssertionError:
        return 0
    pages = payload.get("pages")
    if isinstance(pages, list):
        return len(pages)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify retrieval export JSON against local HTML output.")
    ap.add_argument("--public-root", default=str(DEFAULT_PUBLIC_ROOT))
    ap.add_argument("--export-de", default=str(DEFAULT_EXPORT_DE))
    ap.add_argument("--export-en", default=str(DEFAULT_EXPORT_EN))
    ap.add_argument("--report", default=str(DEFAULT_REPORT_PATH))
    args = ap.parse_args()

    public_root = Path(args.public_root).resolve()
    export_de = Path(args.export_de).resolve()
    export_en = Path(args.export_en).resolve()
    report_path = Path(args.report).resolve()

    issues: list[dict[str, str]] = []
    hard_fail = False
    try:
        result_de = verify_export(export_de, "de", public_root, issues)
        result_en = verify_export(export_en, "en", public_root, issues)
    except AssertionError as exc:
        issues.append({"url": "", "type": "hard_fail", "detail": str(exc)})
        hard_fail = True
        result_de = VerificationResult(hard_fail=True, issues=issues)
        result_en = VerificationResult(hard_fail=True, issues=issues)
    else:
        hard_fail = result_de.hard_fail or result_en.hard_fail

    checked_pages_de = safe_page_count(export_de)
    checked_pages_en = safe_page_count(export_en)
    write_report(report_path, hard_fail, checked_pages_de, checked_pages_en, issues)

    if hard_fail:
        print("Retrieval export verification failed.", file=sys.stderr)
        for issue in issues:
            if issue.get("type") in {"hard_fail", "missing_html", "missing_main_container", "nav_like_body_text"}:
                print(f"- {issue.get('type')}: {issue.get('detail')} ({issue.get('url')})", file=sys.stderr)
        return 1

    print("Retrieval export verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
