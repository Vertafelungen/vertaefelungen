#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA-Struktur-Check für Wissen-Content.

- Prüft Allowlist-Pfade relativ zu wissen/content/{lang}
- Schreibt Report nach wissen/docs/migration/build-qa.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

REPO = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO / "wissen" / "docs" / "migration"
ALLOW_DE = DOCS_DIR / "allowlist_de.txt"
ALLOW_EN = DOCS_DIR / "allowlist_en.txt"
REPORT = DOCS_DIR / "build-qa.md"

BASE_DIR_DE = REPO / "wissen" / "content" / "de"
BASE_DIR_EN = REPO / "wissen" / "content" / "en"


def _clean_line(raw: str) -> str:
    line = raw.strip()
    if line.startswith("\"") and line.endswith("\"") and len(line) >= 2:
        line = line[1:-1].strip()
    if line.startswith("'") and line.endswith("'") and len(line) >= 2:
        line = line[1:-1].strip()
    return line


def _iter_allowlist(path: Path) -> Iterable[str]:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        if line.startswith("#"):
            continue
        yield line


def _check_entries(base_dir: Path, allowlist: Iterable[str]) -> Tuple[list[str], list[str]]:
    entries = list(allowlist)
    missing = []
    for entry in entries:
        is_dir = entry.endswith("/")
        normalized = entry[:-1] if is_dir else entry
        target = base_dir / normalized
        if is_dir:
            if not (target.exists() and target.is_dir()):
                missing.append(entry)
        else:
            if not (target.exists() and target.is_file()):
                missing.append(entry)
    return entries, missing


def _rel_base(base_dir: Path) -> str:
    try:
        return str(base_dir.relative_to(REPO))
    except ValueError:
        return str(base_dir)


def _format_list(label: str, items: list[str]) -> list[str]:
    lines = [f"### {label}"]
    if not items:
        lines.append("- (none)")
        return lines
    for item in items:
        lines.append(f"- `{item}`")
    return lines


def main() -> int:
    allow_de, missing_de = _check_entries(BASE_DIR_DE, _iter_allowlist(ALLOW_DE))
    allow_en, missing_en = _check_entries(BASE_DIR_EN, _iter_allowlist(ALLOW_EN))

    lines = [
        "# Build QA",
        "",
        "## Struktur-Allowlist-Check",
        "",
        "### Base directories",
        f"- de: `{_rel_base(BASE_DIR_DE)}`",
        f"- en: `{_rel_base(BASE_DIR_EN)}`",
        "",
        "### Allowlist counts",
        f"- de: {len(allow_de)}",
        f"- en: {len(allow_en)}",
        "",
        "### Missing counts",
        f"- de: {len(missing_de)}",
        f"- en: {len(missing_en)}",
        "",
        *(_format_list("Missing (de)", missing_de)),
        "",
        *(_format_list("Missing (en)", missing_en)),
        "",
    ]

    REPORT.write_text("\n".join(lines), encoding="utf-8")

    if missing_de or missing_en:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
