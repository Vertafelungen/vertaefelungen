#!/usr/bin/env python3
"""Detect common UTF-8 mojibake sequences in generated HTML."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Iterable, List


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
]


@dataclass
class Hit:
    file: str
    token: str
    line: int
    snippet: str


@dataclass
class Report:
    root: str
    files_scanned: int
    hits: List[Hit]
    warnings: List[str]
    truncated: bool


def _iter_html_files(root: str) -> List[str]:
    files: List[str] = []
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.lower().endswith(".html"):
                files.append(os.path.join(dirpath, filename))
    return sorted(files)


def _find_hits_in_line(line: str, token: str) -> Iterable[int]:
    start = 0
    while True:
        index = line.find(token, start)
        if index == -1:
            return
        yield index
        start = index + len(token)


def _check_meta_charset(text: str) -> bool:
    lowered = text.lower()
    return "<meta charset=\"utf-8\"" in lowered or "<meta charset='utf-8'" in lowered


def scan(root: str, max_files: int | None, max_hits: int | None) -> Report:
    files = _iter_html_files(root)
    if max_files is not None:
        files = files[:max_files]

    hits: List[Hit] = []
    warnings: List[str] = []
    truncated = False

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError as exc:
            warnings.append(f"WARN: Unable to read {file_path}: {exc}")
            continue

        if not _check_meta_charset(content):
            warnings.append(f"WARN: Missing <meta charset=\"utf-8\"> in {file_path}")

        for line_no, line in enumerate(content.splitlines(), start=1):
            for token in TOKENS:
                if token not in line:
                    continue
                for index in _find_hits_in_line(line, token):
                    snippet_start = max(0, index - 60)
                    snippet_end = min(len(line), index + len(token) + 60)
                    snippet = line[snippet_start:snippet_end]
                    hits.append(
                        Hit(
                            file=file_path,
                            token=token,
                            line=line_no,
                            snippet=snippet,
                        )
                    )
                    if max_hits is not None and len(hits) >= max_hits:
                        truncated = True
                        return Report(
                            root=root,
                            files_scanned=len(files),
                            hits=hits,
                            warnings=warnings,
                            truncated=truncated,
                        )

    return Report(
        root=root,
        files_scanned=len(files),
        hits=hits,
        warnings=warnings,
        truncated=truncated,
    )


def _write_report(report: Report, path: str) -> None:
    report_dir = os.path.dirname(path)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
    payload = {
        "root": report.root,
        "files_scanned": report.files_scanned,
        "hit_count": len(report.hits),
        "warnings": report.warnings,
        "truncated": report.truncated,
        "hits": [
            {
                "file": hit.file,
                "token": hit.token,
                "line": hit.line,
                "snippet": hit.snippet,
            }
            for hit in report.hits
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect mojibake sequences in HTML output.")
    parser.add_argument("--root", required=True, help="Root directory of generated site")
    parser.add_argument("--max-files", type=int, default=None, help="Limit number of files scanned")
    parser.add_argument("--max-hits", type=int, default=None, help="Limit number of hits reported")
    parser.add_argument("--report", default=None, help="Write JSON report to path")
    args = parser.parse_args()

    report = scan(args.root, args.max_files, args.max_hits)

    print("Mojibake scan")
    print(f"Root: {report.root}")
    print(f"Files scanned: {report.files_scanned}")
    if report.truncated:
        print("NOTE: hit list truncated due to --max-hits")

    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"  {warning}")

    if report.hits:
        print("Hits:")
        for hit in report.hits:
            print(f"  {hit.file}:{hit.line} [{hit.token}] {hit.snippet}")
    else:
        print("No mojibake tokens found.")

    if args.report:
        _write_report(report, args.report)
        print(f"Report written to {args.report}")

    return 2 if report.hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
