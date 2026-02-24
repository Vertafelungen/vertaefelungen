#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/scripts/qa_url_policy.py
Version: 2026-02-24 10:30 Europe/Berlin
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from ruamel.yaml import YAML

yaml = YAML(typ="safe")
ASCII_RE = re.compile(r"^[a-z0-9-]+$")


def read_frontmatter(path: Path) -> dict:
    txt = path.read_text(encoding="utf-8", errors="replace")
    if not txt.startswith("---\n"):
        return {}
    end = txt.find("\n---\n", 4)
    if end == -1:
        return {}
    raw = txt[4:end]
    data = yaml.load(raw) or {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    root = Path("content")
    errors: list[str] = []

    for p in sorted(root.rglob("index.md")):
        fm = read_frontmatter(p)
        if str(fm.get("managed_by", "")).strip() != "ssot-sync":
            continue
        parent = p.parent.name
        slug = str(fm.get("slug", "")).strip()
        if not slug or slug != parent:
            errors.append(f"{p}: slug missing or not equal parent-folder ({parent})")
        pk = str(fm.get("translationKey") or ((fm.get("produkt") or {}).get("id") if isinstance(fm.get("produkt"), dict) else "")).strip()
        if pk and not parent.startswith(f"{pk}-"):
            errors.append(f"{p}: folder does not start with <pk>- ({pk})")

    for p in sorted(root.rglob("_index.md")):
        fm = read_frontmatter(p)
        if str(fm.get("managed_by", "")).strip() != "categories.csv":
            continue
        slug = str(fm.get("slug", "")).strip()
        if not slug:
            errors.append(f"{p}: categories slug missing")
        elif not ASCII_RE.fullmatch(slug):
            errors.append(f"{p}: categories slug non-ascii: {slug}")

    for p in sorted(root.rglob("*.md")):
        fm = read_frontmatter(p)
        aliases = fm.get("aliases")
        if isinstance(aliases, list):
            for a in aliases:
                if str(a).startswith("/wissen/"):
                    errors.append(f"{p}: alias must not start with /wissen/: {a}")

    dirs = {p.parent for p in root.rglob("index.md")} & {p.parent for p in root.rglob("_index.md")}
    for d in sorted(dirs):
        errors.append(f"{d}: contains both index.md and _index.md")

    if errors:
        print("qa_url_policy failed:", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        return 1
    print("qa_url_policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
