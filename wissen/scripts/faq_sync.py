#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/scripts/faq_sync.py
Version: 2026-02-14 18:40 Europe/Berlin

Purpose
-------
Inject/replace the "## FAQ" section in SSOT-managed Markdown pages based on wissen/ssot/faq.csv.

- Scope types:
  - category: Hugo branch bundles (_index.md) under content/<lang>/<path>/_index.md
             scope_key is the category path relative to content/<lang>/, e.g. "produkte/leisten/tuerbekleidungen"
  - product:  Hugo leaf bundles (index.md) under content/<lang>/.../index.md (only if under "produkte/")
             scope_key may be any of:
               - frontmatter translationKey
               - frontmatter produkt.id
               - frontmatter produkt.artikelnummer
               - a key derived from bundle folder name like "117-tr01-120-..." -> "TR01/120" or "TR01-120"

Safety / Ownership
------------------
- Only touches files whose frontmatter contains managed_by in an allowed set.
  Default allowed: "ssot-sync,categories.csv" (comma-separated).
- Only modifies the FAQ section in the body; frontmatter is preserved verbatim.
- Does not create or delete pages; only updates existing Markdown files.

CLI
---
python wissen/scripts/faq_sync.py --csv wissen/ssot/faq.csv --root wissen/content --apply

Exit codes
----------
0 = OK (including "nothing to do")
2 = input/validation error
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------- CSV ----------

def _normkey(k: str) -> str:
    s = (k or "").strip().replace("\ufeff", "").strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"_+", "_", s)
    return s


def clean(s: Optional[str]) -> str:
    return (s or "").strip()


def read_csv_utf8_auto(path: Path) -> List[Dict[str, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;|\t")
        delim = dialect.delimiter
    except Exception:
        delim = ","
    rows = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    return [{_normkey(k): ("" if v is None else v) for k, v in r.items()} for r in rows]


@dataclass
class FaqItem:
    faq_id: str
    scope_type: str  # product|category
    scope_key: str
    lang: str        # de|en
    question: str
    answer: str
    order: int
    status: str      # active|disabled|draft|...

    @staticmethod
    def from_row(r: Dict[str, str]) -> "FaqItem":
        def to_int(v: str, default: int = 100) -> int:
            v = clean(v)
            if not v:
                return default
            try:
                return int(float(v))
            except Exception:
                return default

        return FaqItem(
            faq_id=clean(r.get("faq_id") or r.get("id") or ""),
            scope_type=clean(r.get("scope_type") or ""),
            scope_key=clean(r.get("scope_key") or ""),
            lang=clean(r.get("lang") or "").lower(),
            question=clean(r.get("question") or r.get("frage") or ""),
            answer=(r.get("answer") or r.get("antwort") or "").rstrip(),
            order=to_int(r.get("order") or r.get("sort") or r.get("rank") or ""),
            status=clean(r.get("status") or "active").lower(),
        )


def load_faq_csv(csv_path: Path) -> List[FaqItem]:
    rows = read_csv_utf8_auto(csv_path)
    items = [FaqItem.from_row(r) for r in rows]

    # Minimal validation
    bad: List[str] = []
    for i, it in enumerate(items, start=2):
        if not it.faq_id:
            bad.append(f"Line {i}: missing faq_id")
        if it.scope_type not in ("product", "category"):
            bad.append(f"Line {i}: invalid scope_type: {it.scope_type}")
        if it.lang not in ("de", "en"):
            bad.append(f"Line {i}: invalid lang: {it.lang}")
        if not it.scope_key:
            bad.append(f"Line {i}: missing scope_key")
        if not it.question:
            bad.append(f"Line {i}: missing question")
        if not it.answer:
            bad.append(f"Line {i}: missing answer")

    if bad:
        raise ValueError("faq.csv validation failed:\n" + "\n".join(bad))

    return items


# ---------- Markdown parsing ----------

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def split_frontmatter(md: str) -> Tuple[str, str]:
    """
    Return (frontmatter_block_including_delimiters_or_empty, body).
    Preserves the exact frontmatter string as found.
    """
    m = FM_RE.match(md or "")
    if not m:
        return "", md or ""
    fm_block = m.group(0)
    body = (md or "")[len(fm_block):]
    return fm_block, body


def parse_managed_by(frontmatter_block: str) -> str:
    """
    Quick YAML-ish extraction without a YAML parser (robust enough for managed_by: value).
    """
    if not frontmatter_block:
        return ""
    m = re.search(r"(?m)^\s*managed_by\s*:\s*(.+?)\s*$", frontmatter_block)
    if not m:
        return ""
    v = m.group(1).strip().strip('"').strip("'")
    return v


FAQ_HEADING_RE = re.compile(
    r"(?im)^(##\s*(FAQ|Häufige\s+Fragen|Frequently\s+asked\s+questions)\s*)$"
)

def replace_or_append_faq(body: str, faq_block: str) -> Tuple[str, str]:
    """
    Returns (new_body, action) where action in {"replaced","appended","unchanged"}.
    Replaces from FAQ heading to next '## ' heading (or end).
    """
    if not faq_block.strip():
        return body, "unchanged"

    # find an existing FAQ heading
    m = FAQ_HEADING_RE.search(body or "")
    if not m:
        # append
        b = (body or "").rstrip() + "\n\n" + faq_block.strip() + "\n"
        return b, "appended"

    start = m.start()
    # find next H2 after start (skip the heading itself)
    m2 = re.search(r"(?m)^(##\s+.+)$", body[m.end():])
    if m2:
        end = m.end() + m2.start()
        new_body = (body[:start].rstrip() + "\n\n" + faq_block.strip() + "\n\n" + body[end:].lstrip())
    else:
        new_body = (body[:start].rstrip() + "\n\n" + faq_block.strip() + "\n")

    if new_body == body:
        return body, "unchanged"
    return new_body, "replaced"


def render_faq_block(lang: str, items: List[FaqItem]) -> str:
    if not items:
        return ""
    out: List[str] = []
    out.append("## FAQ")
    out.append("")
    for it in items:
        out.append(f"### {it.question}")
        out.append("")
        out.append(it.answer.strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------- Scope detection ----------

ARTICLE_RE = re.compile(r"(?i)\b([a-z]{2}\d{2})-(\d{2,3})\b")

def derive_product_keys_from_path(p: Path) -> List[str]:
    """
    From bundle folder name like '117-tr01-120-tuerbekleidung' derive:
    - 'TR01/120'
    - 'TR01-120'
    - 'tr01/120'
    - 'tr01-120'
    Also returns numeric prefix like '117' if present.
    """
    keys: List[str] = []
    try:
        bundle_dir = p.parent.name
    except Exception:
        return keys

    # numeric translation key prefix
    m_num = re.match(r"^(\d{2,})-", bundle_dir)
    if m_num:
        keys.append(m_num.group(1))

    # article number
    m = ARTICLE_RE.search(bundle_dir)
    if m:
        a = m.group(1)
        n = m.group(2)
        keys += [
            f"{a.upper()}/{n}",
            f"{a.upper()}-{n}",
            f"{a.lower()}/{n}",
            f"{a.lower()}-{n}",
        ]

    return list(dict.fromkeys([k for k in keys if k]))


def derive_product_keys_from_frontmatter(frontmatter_block: str) -> List[str]:
    """
    Cheap extraction of common fields without YAML parser.
    """
    keys: List[str] = []

    # translationKey: ...
    m = re.search(r"(?m)^\s*translationKey\s*:\s*(.+?)\s*$", frontmatter_block or "")
    if m:
        keys.append(m.group(1).strip().strip('"').strip("'"))

    # produkt.id and produkt.artikelnummer (indented YAML)
    m = re.search(r"(?m)^\s*id\s*:\s*(.+?)\s*$", frontmatter_block or "")
    # NOTE: this can false-match other ids; we accept because we only use it as candidate key
    if m:
        keys.append(m.group(1).strip().strip('"').strip("'"))

    m = re.search(r"(?m)^\s*artikelnummer\s*:\s*(.+?)\s*$", frontmatter_block or "")
    if m:
        keys.append(m.group(1).strip().strip('"').strip("'"))

    # normalize duplicates
    keys = [k for k in keys if k]
    return list(dict.fromkeys(keys))


def pick_matching_faq_items(
    faq_map: Dict[Tuple[str, str, str], List[FaqItem]],
    scope_type: str,
    candidate_keys: List[str],
    lang: str,
) -> Tuple[Optional[str], List[FaqItem]]:
    for k in candidate_keys:
        items = faq_map.get((scope_type, k, lang))
        if items:
            return k, items
    return None, []


# ---------- Report ----------

def write_report(path: Path, apply: bool, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "APPLY" if apply else "DRY-RUN"
    header = [
        f"# FAQ Sync Report ({mode})",
        "",
        f"- Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    path.write_text("\n".join(header + lines).rstrip() + "\n", encoding="utf-8")


# ---------- Main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/faq.csv")
    ap.add_argument("--root", default="content")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--managed-by",
        default="ssot-sync,categories.csv",
        help="Only touch files with managed_by matching any of these (comma-separated). Default: ssot-sync,categories.csv",
    )
    ap.add_argument("--report", default="scripts/reports/faq_sync_report.md")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    root = Path(args.root)
    managed_by_vals = {v.strip() for v in clean(args.managed_by).split(",") if v.strip()}

    if not csv_path.exists():
        print(f"[faq_sync] faq.csv not found: {csv_path} (skip)")
        return 0
    if not root.exists():
        print(f"[faq_sync] content root not found: {root}", file=sys.stderr)
        return 2

    try:
        all_items = load_faq_csv(csv_path)
    except Exception as e:
        print(f"[faq_sync] ERROR: {e}", file=sys.stderr)
        return 2

    # Build map: (scope_type, scope_key, lang) -> items (active)
    faq_map: Dict[Tuple[str, str, str], List[FaqItem]] = {}
    for it in all_items:
        if it.status != "active":
            continue
        key = (it.scope_type, it.scope_key, it.lang)
        faq_map.setdefault(key, []).append(it)

    for k in list(faq_map.keys()):
        faq_map[k] = sorted(faq_map[k], key=lambda x: (x.order, x.faq_id))

    touched_files: List[str] = []
    skipped_files: List[str] = []
    warnings: List[str] = []

    md_files = sorted(root.rglob("*.md"))

    for p in md_files:
        try:
            rel = p.relative_to(root)
        except Exception:
            continue
        if len(rel.parts) < 2:
            continue

        lang = rel.parts[0].lower()
        if lang not in ("de", "en"):
            continue

        md = p.read_text(encoding="utf-8", errors="replace")
        fm_block, body = split_frontmatter(md)
        managed_by = parse_managed_by(fm_block)

        if managed_by_vals and managed_by not in managed_by_vals:
            skipped_files.append(str(p))
            continue

        basename = p.name
        scope_type: Optional[str] = None
        scope_key_candidates: List[str] = []

        if basename == "_index.md":
            scope_type = "category"
            # category path relative to content/<lang>/
            scope_key = "/".join(rel.parts[1:-1]).strip("/")
            if not scope_key:
                skipped_files.append(str(p))
                continue
            scope_key_candidates = [scope_key]
        elif basename == "index.md":
            # product page, only if path includes produkte/
            rel_path_str = "/".join(rel.parts[1:])
            if "produkte/" not in rel_path_str:
                skipped_files.append(str(p))
                continue
            scope_type = "product"

            # candidates: frontmatter + path-derived
            scope_key_candidates.extend(derive_product_keys_from_frontmatter(fm_block))
            scope_key_candidates.extend(derive_product_keys_from_path(p))

            # also allow raw folder prefix (slug) as-is
            scope_key_candidates.extend([p.parent.name, p.parent.name.lower(), p.parent.name.upper()])

            # normalize & de-dup
            scope_key_candidates = [k for k in scope_key_candidates if k and k.lower() != "none"]
            scope_key_candidates = list(dict.fromkeys(scope_key_candidates))
        else:
            skipped_files.append(str(p))
            continue

        matched_key, items = pick_matching_faq_items(faq_map, scope_type, scope_key_candidates, lang)
        if not items:
            # No FAQ rows for this page: do nothing
            continue

        faq_block = render_faq_block(lang, items)
        new_body, action = replace_or_append_faq(body, faq_block)

        if action == "unchanged":
            continue

        new_md = (fm_block or "") + (new_body or "")

        if args.apply:
            p.write_text(new_md, encoding="utf-8")
        touched_files.append(f"{action}: {p} (key={matched_key})")

    # report
    lines: List[str] = []
    lines.append(f"- CSV: `{csv_path.as_posix()}`")
    lines.append(f"- Root: `{root.as_posix()}`")
    lines.append(f"- managed_by allowlist: {', '.join(sorted(managed_by_vals)) if managed_by_vals else '(none)'}")
    lines.append("")
    lines.append("## Touched")
    lines.append("")
    if touched_files:
        lines.extend([f"- {t}" for t in touched_files])
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    if warnings:
        lines.extend([f"- {w}" for w in warnings])
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append("## Skipped (managed_by mismatch or not a target page)")
    lines.append("")
    if skipped_files:
        lines.extend([f"- {s}" for s in skipped_files[:200]])
        if len(skipped_files) > 200:
            lines.append(f"- ... ({len(skipped_files) - 200} more)")
    else:
        lines.append("- (none)")

    write_report(Path(args.report), args.apply, lines)
    print(f"[faq_sync] Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
