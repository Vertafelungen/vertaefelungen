#!/usr/bin/env python3
"""Generate a prioritized content backlog from retrieval exports and reports."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_DE = REPO_ROOT / "wissen" / "public" / "export" / "index.de.json"
EXPORT_EN = REPO_ROOT / "wissen" / "public" / "export" / "index.en.json"
REPORT_EXPORT = REPO_ROOT / "wissen" / "scripts" / "reports" / "retrieval_export_report.json"
REPORT_VERIFY = REPO_ROOT / "wissen" / "scripts" / "reports" / "retrieval_export_verification_report.json"
OUTPUT_DE_MD = REPO_ROOT / "wissen" / "scripts" / "reports" / "content_backlog.de.md"
OUTPUT_EN_MD = REPO_ROOT / "wissen" / "scripts" / "reports" / "content_backlog.en.md"
OUTPUT_JSON = REPO_ROOT / "wissen" / "scripts" / "reports" / "content_backlog.json"

STRATEGIC_AREAS = {"products", "faq"}
LEGAL_SEGMENTS_DE = {"impressum", "datenschutz", "agb", "widerruf", "kontakt"}
LEGAL_SEGMENTS_EN = {"imprint", "privacy", "terms", "withdrawal", "contact"}


@dataclass
class IssueMatch:
    issue_type: str
    detail: str


@dataclass
class BacklogEntry:
    url: str
    title: str
    area: str
    score: int
    reasons: list[str]


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc}"


def ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def derive_area(url: str) -> str:
    if "/wissen/de/produkte/" in url or "/wissen/en/products/" in url:
        return "products"
    if "/wissen/de/faq/" in url or "/wissen/en/faq/" in url:
        return "faq"
    if "/wissen/de/lookbook/" in url or "/wissen/en/lookbook/" in url:
        return "lookbook"
    if "/wissen/de/shop/" in url or "/wissen/en/shop/" in url:
        return "shop-bridge"
    if any(f"/wissen/de/{segment}/" in url for segment in LEGAL_SEGMENTS_DE):
        return "legal"
    if any(f"/wissen/en/{segment}/" in url for segment in LEGAL_SEGMENTS_EN):
        return "legal"
    return "other"


def add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def build_issue_map(report: dict[str, Any] | None) -> dict[str, list[IssueMatch]]:
    issue_map: dict[str, list[IssueMatch]] = {}
    if not report:
        return issue_map
    for issue in ensure_list(report.get("issues")):
        url = str(issue.get("url", ""))
        issue_type = str(issue.get("type", ""))
        detail = str(issue.get("detail", ""))
        if not url:
            continue
        issue_map.setdefault(url, []).append(IssueMatch(issue_type=issue_type, detail=detail))
    return issue_map


def score_page(page: dict[str, Any], area: str, issues: Iterable[IssueMatch]) -> BacklogEntry:
    url = str(page.get("url", ""))
    title = str(page.get("title", "")).strip() or "(untitled)"
    description = str(page.get("description", "")).strip()
    body_text = str(page.get("body_text", "")).strip()
    headings = [str(h).strip() for h in ensure_list(page.get("headings")) if str(h).strip()]

    score = 0
    reasons: list[str] = []

    if page.get("is_placeholder") is True:
        score += 6
        add_reason(reasons, "is_placeholder")

    if not description:
        score += 4
        add_reason(reasons, "missing_description")

    if len(body_text) < 400:
        score += 4
        add_reason(reasons, f"very_short_body_text:{len(body_text)}")

    if page.get("indexable") is True:
        score += 2
        add_reason(reasons, "indexable_true")
    elif page.get("indexable") is False:
        score -= 6
        add_reason(reasons, "indexable_false")

    if area in STRATEGIC_AREAS:
        score += 2
        add_reason(reasons, "strategic_area")

    if not headings:
        score += 1
        add_reason(reasons, "headings_empty")

    for issue in issues:
        if issue.issue_type == "nav_like_body_text":
            add_reason(reasons, "nav_like_body_text")
        elif issue.issue_type in {"missing_html_expected", "missing_html_unexpected"}:
            suffix = f": {issue.detail}" if issue.detail else ""
            add_reason(reasons, f"{issue.issue_type}{suffix}")

    return BacklogEntry(url=url, title=title, area=area, score=score, reasons=reasons)


def build_backlog(pages: list[dict[str, Any]], issues_by_url: dict[str, list[IssueMatch]]) -> list[BacklogEntry]:
    backlog: list[BacklogEntry] = []
    for page in pages:
        url = str(page.get("url", ""))
        if not url:
            continue
        area = derive_area(url)
        issues = issues_by_url.get(url, [])
        backlog.append(score_page(page, area, issues))
    backlog.sort(key=lambda item: (-item.score, item.url))
    return backlog


def format_markdown(
    lang: str,
    generated_at: str,
    inputs: dict[str, dict[str, Any]],
    backlog: list[BacklogEntry],
    unmatched_report_issues: list[str],
    export_note: str | None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Content Backlog ({lang.upper()})")
    lines.append("")
    lines.append(f"Generated at: {generated_at}")
    if export_note:
        lines.append(f"Note: {export_note}")
    lines.append("")
    lines.append("## Inputs")
    for label, info in inputs.items():
        status = "present" if info.get("present") else "missing"
        detail = info.get("detail")
        detail_suffix = f" ({detail})" if detail else ""
        lines.append(f"- {label}: {status}{detail_suffix}")
    lines.append("")
    lines.append("## Counts")
    lines.append(f"- total_pages: {len(backlog)}")
    lines.append(f"- top_25: {min(25, len(backlog))}")
    lines.append("")
    lines.append("## Top 25")
    top_entries = backlog[:25]
    if not top_entries:
        lines.append("- (none)")
    else:
        for entry in top_entries:
            lines.append(f"1. **Score {entry.score}** — {entry.title}")
            lines.append(f"   - URL: {entry.url}")
            if entry.reasons:
                lines.append("   - Reasons:")
                for reason in entry.reasons:
                    lines.append(f"     - {reason}")
            else:
                lines.append("   - Reasons: (none)")
    lines.append("")
    lines.append("## By area")
    areas = ["products", "faq", "lookbook", "shop-bridge", "legal", "other"]
    for area in areas:
        grouped = [entry for entry in backlog if entry.area == area]
        lines.append(f"### {area} ({len(grouped)})")
        if not grouped:
            lines.append("- (none)")
            continue
        for entry in grouped:
            lines.append(f"- [{entry.score}] {entry.title} — {entry.url}")
    lines.append("")
    lines.append("## Debug summary")
    lines.append(f"- unmatched_report_issue_count: {len(unmatched_report_issues)}")
    if unmatched_report_issues:
        lines.append("- unmatched_report_issue_urls:")
        for url in sorted(unmatched_report_issues):
            lines.append(f"  - {url}")
    return "\n".join(lines) + "\n"


def backlog_to_json(
    generated_at: str,
    inputs: dict[str, dict[str, Any]],
    backlog: list[BacklogEntry],
) -> dict[str, Any]:
    top = [
        {
            "score": entry.score,
            "title": entry.title,
            "url": entry.url,
            "area": entry.area,
            "reasons": entry.reasons,
        }
        for entry in backlog[:25]
    ]
    by_area: dict[str, list[dict[str, Any]]] = {}
    for entry in backlog:
        by_area.setdefault(entry.area, []).append(
            {
                "score": entry.score,
                "title": entry.title,
                "url": entry.url,
                "reasons": entry.reasons,
            }
        )
    return {
        "generated_at": generated_at,
        "inputs": inputs,
        "count": len(backlog),
        "top": top,
        "by_area": by_area,
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    generated_at = iso_timestamp()

    export_de, export_de_err = read_json(EXPORT_DE)
    export_en, export_en_err = read_json(EXPORT_EN)
    report_export, report_export_err = read_json(REPORT_EXPORT)
    report_verify, report_verify_err = read_json(REPORT_VERIFY)

    inputs = {
        "export_de": {"path": str(EXPORT_DE), "present": export_de is not None, "detail": export_de_err},
        "export_en": {"path": str(EXPORT_EN), "present": export_en is not None, "detail": export_en_err},
        "report_export": {
            "path": str(REPORT_EXPORT),
            "present": report_export is not None,
            "detail": report_export_err,
        },
        "report_verify": {
            "path": str(REPORT_VERIFY),
            "present": report_verify is not None,
            "detail": report_verify_err,
        },
    }

    issues_by_url = build_issue_map(report_verify)
    export_pages_de = ensure_list(export_de.get("pages")) if export_de else []
    export_pages_en = ensure_list(export_en.get("pages")) if export_en else []

    all_urls = {str(page.get("url", "")) for page in export_pages_de + export_pages_en if page.get("url")}
    unmatched_report_issues = [
        url for url in issues_by_url.keys() if url and url not in all_urls
    ]

    backlog_de = build_backlog(export_pages_de, issues_by_url) if export_de else []
    backlog_en = build_backlog(export_pages_en, issues_by_url) if export_en else []

    export_note_de = "Export missing" if export_de is None else None
    export_note_en = "Export missing" if export_en is None else None

    md_de = format_markdown("de", generated_at, inputs, backlog_de, unmatched_report_issues, export_note_de)
    md_en = format_markdown("en", generated_at, inputs, backlog_en, unmatched_report_issues, export_note_en)

    write_text(OUTPUT_DE_MD, md_de)
    write_text(OUTPUT_EN_MD, md_en)

    combined = {
        "generated_at": generated_at,
        "inputs": inputs,
        "de": backlog_to_json(generated_at, inputs, backlog_de),
        "en": backlog_to_json(generated_at, inputs, backlog_en),
    }
    write_text(OUTPUT_JSON, json.dumps(combined, ensure_ascii=False, indent=2) + "\n")

    print("Content backlog generated.")
    print(f"- DE pages: {len(backlog_de)}")
    print(f"- EN pages: {len(backlog_en)}")
    if backlog_de:
        print(f"- Top DE URL: {backlog_de[0].url}")
    if backlog_en:
        print(f"- Top EN URL: {backlog_en[0].url}")
    missing_inputs = [name for name, info in inputs.items() if not info.get("present")]
    if missing_inputs:
        print(f"- Missing inputs: {', '.join(sorted(missing_inputs))}")
    if unmatched_report_issues:
        print(f"- Unmatched report URLs: {len(unmatched_report_issues)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
