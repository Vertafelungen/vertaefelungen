#!/usr/bin/env python3
"""Scan source or build output files for common UTF-8 mojibake sequences."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


TOKENS = [
    "Ã¤",
    "Ã¶",
    "Ã¼",
    "Ã„",
    "Ã–",
    "Ãœ",
    "ÃŸ",
    "â€“",
    "â€”",
    "â€ž",
    "â€œ",
    "â€˜",
    "â€™",
    "Â",
]

PRE_EXTENSIONS = (".md", ".toml", ".yaml", ".yml", ".json", ".csv")
POST_EXTENSIONS = (".html", ".xml")


@dataclass
class Hit:
    file: str
    token: str
    snippet: str
    count: int
    encoding: str
    classification: str


@dataclass
class Report:
    root: str
    mode: str
    files_scanned: int
    hits: List[Hit]
    warnings: List[str]
    truncated: bool


def _iter_files(root: str, extensions: Sequence[str]) -> Iterable[str]:
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            lowered = filename.lower()
            if any(lowered.endswith(ext) for ext in extensions):
                yield os.path.join(dirpath, filename)


def _decode_bytes(raw: bytes, file_path: str, warnings: List[str]) -> Tuple[Optional[str], Optional[str]]:
    if b"\x00" in raw:
        warnings.append(f"WARN: Skipping binary-like file {file_path}")
        return None, None
    try:
        return raw.decode("utf-8", errors="strict"), "utf-8"
    except UnicodeDecodeError:
        try:
            return raw.decode("latin-1", errors="strict"), "latin-1"
        except UnicodeDecodeError as exc:
            warnings.append(f"WARN: Unable to decode {file_path}: {exc}")
            return None, None


def _find_token_hits(text: str, token: str) -> Iterable[int]:
    start = 0
    while True:
        index = text.find(token, start)
        if index == -1:
            return
        yield index
        start = index + len(token)


def _classify_hit(token: str, text: str, index: int) -> str:
    if token != "Â":
        return "hit"
    if index + 1 < len(text) and text[index + 1] == "&":
        return "warn"
    return "hit"


def _snippet(text: str, index: int, token: str, padding: int = 40) -> str:
    start = max(0, index - padding)
    end = min(len(text), index + len(token) + padding)
    return text[start:end]


def scan(root: str, mode: str, max_hits: Optional[int]) -> Report:
    extensions = PRE_EXTENSIONS if mode == "pre" else POST_EXTENSIONS
    files = sorted(_iter_files(root, extensions))

    hits: List[Hit] = []
    warnings: List[str] = []
    truncated = False
    total_matches = 0

    for file_path in files:
        try:
            with open(file_path, "rb") as handle:
                raw = handle.read()
        except OSError as exc:
            warnings.append(f"WARN: Unable to read {file_path}: {exc}")
            continue

        decoded, encoding = _decode_bytes(raw, file_path, warnings)
        if decoded is None or encoding is None:
            continue

        token_counts: Dict[Tuple[str, str], int] = {}
        token_snippets: Dict[Tuple[str, str], str] = {}

        for token in TOKENS:
            for index in _find_token_hits(decoded, token):
                classification = _classify_hit(token, decoded, index)
                key = (token, classification)
                token_counts[key] = token_counts.get(key, 0) + 1
                token_snippets.setdefault(key, _snippet(decoded, index, token))
                total_matches += 1
                if max_hits is not None and total_matches >= max_hits:
                    truncated = True
                    break
            if truncated:
                break
        for (token, classification), count in token_counts.items():
            hits.append(
                Hit(
                    file=file_path,
                    token=token,
                    snippet=token_snippets[(token, classification)],
                    count=count,
                    encoding=encoding,
                    classification=classification,
                )
            )
        if truncated:
            break

    return Report(
        root=root,
        mode=mode,
        files_scanned=len(files),
        hits=hits,
        warnings=warnings,
        truncated=truncated,
    )


def _summary_lines(report: Report, limit: int = 50) -> List[str]:
    lines = [
        "Mojibake source scan summary",
        f"Root: {report.root}",
        f"Mode: {report.mode}",
        f"Files scanned: {report.files_scanned}",
        f"Hit entries: {len([hit for hit in report.hits if hit.classification == 'hit'])}",
        f"Warning entries: {len([hit for hit in report.hits if hit.classification == 'warn'])}",
    ]
    if report.truncated:
        lines.append("NOTE: hit list truncated due to --max-hits")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  {warning}" for warning in report.warnings)

    def _sort_key(item: Hit) -> Tuple[int, str, str]:
        return (-item.count, item.file, item.token)

    hits = sorted((hit for hit in report.hits if hit.classification == "hit"), key=_sort_key)
    warns = sorted((hit for hit in report.hits if hit.classification == "warn"), key=_sort_key)

    lines.append("")
    lines.append("Top hits:")
    if hits:
        for hit in hits[:limit]:
            lines.append(
                f"  {hit.count}x [{hit.token}] {hit.file} ({hit.encoding}) :: {hit.snippet}"
            )
    else:
        lines.append("  (none)")

    if warns:
        lines.append("")
        lines.append("Warnings (token-only):")
        for hit in warns[:limit]:
            lines.append(
                f"  {hit.count}x [{hit.token}] {hit.file} ({hit.encoding}) :: {hit.snippet}"
            )

    return lines


def _write_report(report: Report, path: str) -> str:
    report_dir = os.path.dirname(path)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
    payload = {
        "root": report.root,
        "mode": report.mode,
        "files_scanned": report.files_scanned,
        "hit_entries": len([hit for hit in report.hits if hit.classification == "hit"]),
        "warning_entries": len([hit for hit in report.hits if hit.classification == "warn"]),
        "warnings": report.warnings,
        "truncated": report.truncated,
        "hits": [
            {
                "file": hit.file,
                "token": hit.token,
                "snippet": hit.snippet,
                "count": hit.count,
                "encoding": hit.encoding,
                "classification": hit.classification,
            }
            for hit in report.hits
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    summary_path = path[:-5] + "_summary.txt" if path.lower().endswith(".json") else path + "_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_summary_lines(report)))
        handle.write("\n")
    return summary_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan sources or build output for common mojibake sequences."
    )
    parser.add_argument("--root", required=True, help="Root directory to scan")
    parser.add_argument("--mode", required=True, choices=["pre", "post"], help="Scan mode")
    parser.add_argument("--report", required=True, help="Write JSON report to path")
    parser.add_argument("--max-hits", type=int, default=None, help="Limit number of hits reported")
    args = parser.parse_args()

    report = scan(args.root, args.mode, args.max_hits)

    print("Mojibake source scan")
    print(f"Root: {report.root}")
    print(f"Mode: {report.mode}")
    print(f"Files scanned: {report.files_scanned}")
    if report.truncated:
        print("NOTE: hit list truncated due to --max-hits")
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"  {warning}")
    if report.hits:
        for hit in report.hits:
            print(
                f"{hit.file} [{hit.token}] ({hit.classification}) ({hit.encoding}) "
                f"{hit.count}x :: {hit.snippet}"
            )
    else:
        print("No mojibake tokens found.")

    summary_path = _write_report(report, args.report)
    print(f"Report written to {args.report}")
    print(f"Summary written to {summary_path}")

    has_hits = any(hit for hit in report.hits if hit.classification == "hit")
    return 2 if has_hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
