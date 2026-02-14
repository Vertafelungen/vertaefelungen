#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/scripts/faq_sync.py
Version: 2026-02-14T13:45:00+01:00 (Europe/Berlin)

Purpose:
  Inject/replace the "## FAQ" section in SSOT-managed Markdown pages based on wissen/ssot/faq.csv.

Scope:
  - Reads: wissen/ssot/faq.csv
  - Writes (only if --apply): files under content/** that are managed_by: ssot-sync
  - Does NOT touch layouts, config, or non-SSOT pages.

Key rules:
  - Only internal links /de/... or /en/... (rewrites /wissen/de/... -> /de/... and /wissen/en/... -> /en/...)
  - Deterministic output for FAQ block (sorted by order)
  - Leaves frontmatter byte-identical (frontmatter is preserved as-is)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional


H2_FAQ_RE = re.compile(r"(?m)^##\s+FAQ\s*$")
H2_ANY_RE = re.compile(r"(?m)^##\s+\S.*$")

# basic rewrites to avoid /wissen/... links
def rewrite_internal_links(text: str, lang: str) -> str:
    if not text:
        return text

    # absolute -> root-relative
    text = re.sub(r"https?://www\.vertaefelungen\.de/wissen/de/", "/de/", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://www\.vertaefelungen\.de/wissen/en/", "/en/", text, flags=re.IGNORECASE)

    # root-relative but with /wissen
    text = text.replace("](/wissen/de/", "](/de/")
    text = text.replace("](/wissen/en/", "](/en/")
    text = text.replace("(/wissen/de/", "(/de/")
    text = text.replace("(/wissen/en/", "(/en/")

    # defensive: any remaining "/wissen/" becomes a warning target; do not auto-rewrite blindly
    return text


def normalize_question(q: str) -> str:
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


@dataclass(frozen=True)
class FaqItem:
    faq_id: str
    scope_type: str
    scope_key: str
    lang: str
    question: str
    answer: str
    order: int
    status: str
    tags: str
    source: str


def split_frontmatter(md: str) -> Tuple[str, str]:
    """
    Returns (frontmatter_block_or_empty, body).
    Preserves frontmatter text exactly (no re-serialization).
    Supports YAML frontmatter with --- ... --- at file start.
    """
    if md.startswith("---\n"):
        end = md.find("\n---\n", 4)
        if end != -1:
            fm = md[: end + len("\n---\n")]
            body = md[end + len("\n---\n") :]
            return fm, body
    return "", md


def parse_managed_by(frontmatter: str) -> str:
    """
    Best-effort parse of managed_by from YAML frontmatter.
    We avoid rewriting; we only parse with regex to stay robust.
    """
    # match lines like: managed_by: ssot-sync  OR managed_by: "ssot-sync"
    m = re.search(r'(?m)^managed_by:\s*("?)([^"\n]+)\1\s*$', frontmatter)
    return (m.group(2).strip() if m else "")


def extract_translation_key(frontmatter: str) -> str:
    m = re.search(r'(?m)^translationKey:\s*("?)([^"\n]+)\1\s*$', frontmatter)
    return (m.group(2).strip() if m else "")


def extract_produkt_fields(frontmatter: str) -> Dict[str, str]:
    """
    Very lightweight extraction for:
      produkt:
        id: ...
        artikelnummer: ...
    Works even if YAML has quotes.
    """
    out: Dict[str, str] = {}
    # isolate produkt: block by indentation
    # find line "produkt:" then capture subsequent indented lines until next non-indented key
    m = re.search(r"(?ms)^produkt:\s*\n(.*?)(?=^[A-Za-z0-9_\-]+\s*:|\Z)", frontmatter)
    if not m:
        return out
    block = m.group(1)

    mid = re.search(r'(?m)^\s+id:\s*("?)([^"\n]+)\1\s*$', block)
    if mid:
        out["id"] = mid.group(2).strip()

    man = re.search(r'(?m)^\s+artikelnummer:\s*("?)([^"\n]+)\1\s*$', block)
    if man:
        out["artikelnummer"] = man.group(2).strip()

    return out


def normalize_artikelnummer_to_scope_keys(val: str) -> List[str]:
    """
    Accepts TR01-120, TR01/120, tr01-120 etc.
    Returns candidates, most canonical first.
    """
    v = (val or "").strip()
    if not v:
        return []
    v_up = v.upper()
    # canonicalize TRxx-yyy -> TRxx/yyy
    if re.fullmatch(r"TR\d{2}-\d{2,3}", v_up):
        return [v_up.replace("-", "/"), v_up]
    if re.fullmatch(r"TR\d{2}/\d{2,3}", v_up):
        return [v_up, v_up.replace("/", "-")]
    return [v_up]


def derive_product_keys_from_path(path: Path) -> List[str]:
    """
    From folder names like '117-tr01-120' derive:
      - TR01/120
      - TR01-120
      - 117
    """
    parts = path.parts
    # look for ".../<something>/index.md"
    parent = path.parent.name.lower()
    keys: List[str] = []

    m = re.search(r"(?i)(\d+)-?(tr\d{2})-(\d{2,3})", parent)
    if m:
        keys.append(f"{m.group(2).upper()}/{m.group(3)}")
        keys.append(f"{m.group(2).upper()}-{m.group(3)}")
        keys.append(m.group(1))
        return keys

    # fallback: try to find trXX-YYY anywhere in path
    m2 = re.search(r"(?i)(tr\d{2})-(\d{2,3})", str(path).lower())
    if m2:
        keys.append(f"{m2.group(1).upper()}/{m2.group(2)}")
        keys.append(f"{m2.group(1).upper()}-{m2.group(2)}")

    return keys


def upsert_faq_section(body: str, faq_block: str) -> Tuple[str, bool]:
    """
    Replace existing ## FAQ section content, or append if absent.
    Returns (new_body, changed).
    """
    m = H2_FAQ_RE.search(body)
    if not m:
        # append at end with spacing
        new_body = body.rstrip() + "\n\n" + faq_block.rstrip() + "\n"
        return new_body, (new_body != body)

    start = m.start()
    # find next H2 after the FAQ heading line
    # locate end of the "## FAQ" line
    line_end = body.find("\n", m.end())
    if line_end == -1:
        line_end = m.end()

    # search next H2 after line_end
    m2 = H2_ANY_RE.search(body, pos=line_end)
    end = m2.start() if m2 else len(body)

    # keep the "## FAQ" heading line, replace the rest of the section
    faq_heading = body[start:line_end].rstrip() + "\n\n"
    new_body = body[:start] + faq_heading + faq_block.split("\n", 2)[2] if faq_block.startswith("## FAQ") else (body[:start] + faq_block + body[end:])
    # The above can be tricky; simplest: we always generate full block starting with "## FAQ"
    # so we just replace [start:end] with faq_block.
    new_body = body[:start] + faq_block.rstrip() + "\n" + body[end:].lstrip("\n")
    return new_body, (new_body != body)


def build_faq_block(items: List[FaqItem], lang: str) -> str:
    out: List[str] = ["## FAQ", ""]
    for it in items:
        q = rewrite_internal_links(it.question.strip(), lang).strip()
        a = rewrite_internal_links(it.answer.strip(), lang).strip()
        out.append(f"### {q}")
        out.append("")
        out.append(a)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def load_faq_csv(csv_path: Path) -> List[FaqItem]:
    items: List[FaqItem] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                items.append(
                    FaqItem(
                        faq_id=(row.get("faq_id") or "").strip(),
                        scope_type=(row.get("scope_type") or "").strip().lower(),
                        scope_key=(row.get("scope_key") or "").strip().strip("/"),
                        lang=(row.get("lang") or "").strip().lower(),
                        question=(row.get("question") or "").strip(),
                        answer=(row.get("answer") or "").strip(),
                        order=int((row.get("order") or "0").strip() or "0"),
                        status=(row.get("status") or "").strip().lower(),
                        tags=(row.get("tags") or "").strip(),
                        source=(row.get("source") or "").strip(),
                    )
                )
            except Exception:
                # skip bad rows; report later
                continue
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to faq.csv (relative to working dir)")
    ap.add_argument("--root", required=True, help="Content root, e.g. content")
    ap.add_argument("--apply", action="store_true", help="Write changes (otherwise dry-run)")
    ap.add_argument("--managed-by", default="ssot-sync", help="Only touch files with managed_by matching this (default: ssot-sync)")
    ap.add_argument("--report", default="scripts/reports/faq_sync_report.md", help="Write a markdown report here")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    root = Path(args.root)
    managed_by_val = args.managed_by.strip()

    if not csv_path.exists():
        print(f"[faq_sync] faq.csv not found: {csv_path} (skip)")
        return 0
    if not root.exists():
        print(f"[faq_sync] content root not found: {root}")
        return 2

    all_items = load_faq_csv(csv_path)

    # Build map: (scope_type, scope_key, lang) -> items (active)
    faq_map: Dict[Tuple[str, str, str], List[FaqItem]] = {}
    for it in all_items:
        if it.status != "active":
            continue
        if it.scope_type not in ("product", "category"):
            continue
        if it.lang not in ("de", "en"):
            continue
        key = (it.scope_type, it.scope_key, it.lang)
        faq_map.setdefault(key, []).append(it)

    for k in list(faq_map.keys()):
        faq_map[k] = sorted(faq_map[k], key=lambda x: (x.order, x.faq_id))

    touched_files: List[str] = []
    skipped_files: List[str] = []
    warnings: List[str] = []

    # walk markdown files
    md_files = sorted(root.rglob("*.md"))

    for p in md_files:
        # derive lang from path: root/<lang>/...
        try:
            rel = p.relative_to(root)
        except Exception:
            continue
        if len(rel.parts) < 2:
            continue

        lang = rel.parts[0].lower()
        if lang not in ("de", "en"):
            continue

        md = p.read_text(encoding="utf-8")
        fm, body = split_frontmatter(md)

        if managed_by_val:
            mb = parse_managed_by(fm)
            if mb != managed_by_val:
                skipped_files.append(str(p))
                continue

        # Determine scope & key
        basename = p.name
        scope_type: Optional[str] = None
        scope_key: Optional[str] = None

        if basename == "_index.md":
            scope_type = "category"
            # category key relative to content/<lang>/ without filename
            scope_key = "/".join(rel.parts[1:-1]).strip("/")
            if not scope_key:
                skipped_files.append(str(p))
                continue
        elif basename == "index.md":
            # likely product page, but only if under produkte/
            rel_path_str = "/".join(rel.parts[1:])
            if "produkte/" not in rel_path_str:
                skipped_files.append(str(p))
                continue
            scope_type = "product_
