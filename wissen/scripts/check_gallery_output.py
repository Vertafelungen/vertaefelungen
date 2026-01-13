#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    public_dir = repo_root / "public"
    target_html = public_dir / "de/produkte/halbhohe-vertaefelungen/21-p0009/index.html"

    if not target_html.exists():
        print(f"Expected HTML not found: {target_html}")
        return 1

    html = target_html.read_text(encoding="utf-8")
    images = re.findall(r'<img\s+[^>]*src="([^"]+)"', html)
    if not images:
        print(f"No <img> tags found in {target_html}")
        return 1

    for src in images:
        if src.startswith("http://") or src.startswith("https://"):
            continue
        candidate = public_dir / src.lstrip("/")
        if candidate.exists():
            print(f"Found gallery image: {candidate}")
            return 0

    print("No referenced gallery images found in public/ output.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
