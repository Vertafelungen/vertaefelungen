#!/usr/bin/env python3
"""Non-destructive post-migration audit for FAQ content."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
FAQ_DIRS = [ROOT / "content" / "de" / "faq", ROOT / "content" / "en" / "faq"]
BEGIN_MARKER = "<!-- FAQ_SYNC:BEGIN -->"
END_MARKER = "<!-- FAQ_SYNC:END -->"


def read_text_and_bytes(path: Path) -> Tuple[str, bytes]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return text, raw


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], int, int] | Tuple[None, None, None]:
    lines = text.splitlines()
    if not lines:
        return None, None, None

    first = lines[0].lstrip("\ufeff").strip()
    if first != "---":
        return None, None, None

    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break

    if end_idx is None:
        return None, None, None

    fm: Dict[str, str] = {}
    for line in lines[1:end_idx]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$", line)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2).strip().strip('"').strip("'")
        fm[key] = value

    return fm, 0, end_idx


def find_second_frontmatter_start(text: str) -> int | None:
    lines = text.splitlines()
    if not lines:
        return None

    if lines[0].lstrip("\ufeff").strip() != "---":
        return None

    first_end = None
    for idx in range(1, min(len(lines), 120)):
        if lines[idx].strip() == "---":
            first_end = idx
            break

    if first_end is None:
        return None

    for idx in range(first_end + 1, min(len(lines), 120)):
        if lines[idx].lstrip("\ufeff").strip() == "---":
            return idx + 1

    return None


def collect_files() -> List[Path]:
    files: List[Path] = []
    for faq_dir in FAQ_DIRS:
        if faq_dir.exists():
            files.extend(sorted(p for p in faq_dir.rglob("*.md") if p.is_file()))
    return files


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def audit() -> Tuple[List[str], int, int]:
    files = collect_files()
    failures: List[str] = []
    key_index: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    marker_begin_count = 0
    marker_end_count = 0

    for path in files:
        text, raw = read_text_and_bytes(path)
        rpath = rel(path)

        if raw.startswith(b"\xef\xbb\xbf"):
            failures.append(f"{rpath}: UTF-8 BOM detected at file start")

        fm_data = parse_frontmatter(text)
        if fm_data[0] is None:
            failures.append(f"{rpath}: missing or invalid frontmatter block")
        else:
            fm, _, _ = fm_data
            managed_by = fm.get("managed_by", "")
            translation_key = fm.get("translationKey", "")

            if managed_by != "faq.csv":
                failures.append(
                    f"{rpath}: managed_by must be 'faq.csv' (found: {managed_by!r})"
                )

            if not translation_key:
                failures.append(f"{rpath}: missing frontmatter translationKey")
            else:
                lang = "de" if "/content/de/faq/" in f"/{rpath}/" else "en"
                key_index[lang][translation_key].append(rpath)

        second_fm_line = find_second_frontmatter_start(text)
        if second_fm_line is not None:
            failures.append(
                f"{rpath}: second frontmatter start found within first 120 lines at line {second_fm_line}"
            )

        if BEGIN_MARKER in text:
            marker_begin_count += text.count(BEGIN_MARKER)
            failures.append(f"{rpath}: contains forbidden marker {BEGIN_MARKER}")

        if END_MARKER in text:
            marker_end_count += text.count(END_MARKER)
            failures.append(f"{rpath}: contains forbidden marker {END_MARKER}")

    if marker_begin_count != marker_end_count:
        failures.append(
            f"global: marker count mismatch BEGIN={marker_begin_count}, END={marker_end_count}"
        )

    for lang, by_key in key_index.items():
        for key, paths in sorted(by_key.items()):
            if len(paths) > 1:
                failures.append(
                    f"{lang}: duplicate translationKey {key!r} in files: {', '.join(sorted(paths))}"
                )

    return failures, len(files), len(key_index)


def main() -> int:
    failures, files_count, langs_with_keys = audit()

    if failures:
        print("AUDIT FAIL: FAQ migration issues detected")
        for item in failures:
            print(f" - {item}")
        return 2

    print(
        "AUDIT OK: no FAQ migration issues found "
        f"(files={files_count}, langs_with_translation_keys={langs_with_keys})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
