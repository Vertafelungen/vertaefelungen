#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

INCLUDE_PREFIX = "@include:"
INCLUDE_ROOT = Path(__file__).resolve().parents[1] / "ssot_texts"

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


def _validate_relpath(relpath: str, *, context: str) -> None:
    if not relpath:
        raise ValueError(f"{context}: include path is empty")
    if Path(relpath).is_absolute():
        raise ValueError(f"{context}: include path must be relative: {relpath}")
    if _DRIVE_RE.match(relpath) or _SCHEME_RE.match(relpath):
        raise ValueError(f"{context}: include path contains drive or URI scheme: {relpath}")

    parts = Path(relpath).parts
    if any(part == ".." for part in parts):
        raise ValueError(f"{context}: include path traversal is not allowed: {relpath}")


def resolve_include(value: str, *, context: str) -> str:
    raw = "" if value is None else str(value)
    stripped = raw.strip()
    if not stripped.startswith(INCLUDE_PREFIX):
        return value

    relpath = stripped[len(INCLUDE_PREFIX):].strip()
    _validate_relpath(relpath, context=context)

    include_root = INCLUDE_ROOT.resolve()
    target = (INCLUDE_ROOT / relpath).resolve()
    try:
        target.relative_to(include_root)
    except ValueError as exc:
        raise ValueError(f"{context}: include path escapes include root: {relpath}") from exc

    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"{context}: include file not found: {relpath}")

    content = target.read_text(encoding="utf-8")
    return content.rstrip() + "\n"


def resolve_many(row: Dict[str, str], keys: List[str], *, context_prefix: str) -> Dict[str, str]:
    for key in keys:
        row[key] = resolve_include(row.get(key, ""), context=f"{context_prefix}:{key}")
    return row
