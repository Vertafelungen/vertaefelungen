#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/scripts/faq_sync.py
Version: 2026-02-14T14:05:00+01:00 (Europe/Berlin)

Purpose:
  Inject/replace the "## FAQ" section in SSOT-managed Markdown pages based on wissen/ssot/faq.csv.

Scope:
  - Reads: wissen/ssot/faq.csv
  - Writes (only if --apply): files under content/** that are managed_by: ssot-sync
  - Does NOT touch layouts, config, or non-SSOT pages.

Key rules:
  - Only internal links /de/... or /en/... (rewrites /wissen/de/... -> /de/... and /wissen/en/... -> /en/...)
  - Deterministic output for FAQ block (sorted by order then faq_id; de-dupe by question)
  - Leaves frontmatter byte-identical (frontmatter is preserved as-is)
  - Replaces existing "## FAQ" section (until next H2) or appends it if absent
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Iterable, Set


H2_FAQ_RE = re.compile(r"(?m)^##\s+FAQ\s*$")
H2_ANY_RE = re.compile(r"(?m)^##\s+\S.*$")
H2_FAQ_ANYLANG_RE = re.compile(r"(?m)^##\s+(FAQ|Häufige Fragen)\s*$", re.IGNORECASE)

WISSEN_LINK_RE = re.compile(r"(\]\(/wissen/|https?://[^,\s)]+/wissen/|/wissen/)", re.IGNORECASE)


def rewrite_internal_links(text: str, lang: str) -> str:
    """
    Rewrite known internal /wissen/ links to language-root-relative /de/ or /en/.
    Does not blindly rewrite arbitrary /wissen/ occurrences beyond the known patterns.
    """
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

    # defensive: if markdown uses full path without brackets
    text = text.replace("/wissen/de/", "/de/")
    text = text.replace("/wissen/en/", "/en/")

    # language-specific cleanup (rare): /de/ links inside EN content are allowed, but we keep as authoring choice.
    # We do not force /de/ -> /en/ or vice versa here.
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
    Supports:
      - YAML frontmatter: --- ... ---
      - TOML frontmatter: +++ ... +++
    """
    if md.startswith("---"):
        m = re.match(r"(?s)\A---\s*\n.*?\n---\s*\n", md)
        if m:
            fm = md[: m.end()]
            body = md[m.end() :]
            return fm, body

    if md.startswith("+++"):
        m = re.match(r"(?s)\A\+\+\+\s*\n.*?\n\+\+\+\s*\n", md)
        if m:
            fm = md[: m.end()]
            body = md[m.end() :]
            return fm, body

    return "", md


def parse_managed_by(frontmatter: str) -> str:
    """
    Best-effort parse of managed_by from YAML/TOML-ish frontmatter via regex.
    We avoid rewriting; we only parse with regex to stay robust.
    """
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
    """
    out: Dict[str, str] = {}
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
    Returns candidates (canonical first).
    """
    v = (val or "").strip()
    if not v:
        return []
    v_up = v.upper()
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
    parent = path.parent.name.lower()
    keys: List[str] = []

    m = re.search(r"(?i)(\d+)-?(tr\d{2})-(\d{2,3})", parent)
    if m:
        keys.append(f"{m.group(2).upper()}/{m.group(3)}")
        keys.append(f"{m.group(2).upper()}-{m.group(3)}")
        keys.append(m.group(1))
        return keys

    m2 = re.search(r"(?i)(tr\d{2})-(\d{2,3})", str(path).lower())
    if m2:
        keys.append(f"{m2.group(1).upper()}/{m2.group(2)}")
        keys.append(f"{m2.group(1).upper()}-{m2.group(2)}")

    return keys


def product_key_variants(key: str) -> List[str]:
    """
    Return equivalent variants for TRxx/yyy <-> TRxx-yyy.
    """
    k = (key or "").strip()
    if not k:
        return []
    kup = k.upper()
    if re.fullmatch(r"TR\d{2}/\d{2,3}", kup):
        return [kup, kup.replace("/", "-")]
    if re.fullmatch(r"TR\d{2}-\d{2,3}", kup):
        return [kup.replace("-", "/"), kup]
    return [kup]


def uniq_preserve_order(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in items:
        x = (x or "").strip()
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def upsert_faq_section(body: str, faq_block: str) -> Tuple[str, bool]:
    """
    Replace existing ## FAQ (or ## Häufige Fragen) section content, or append if absent.
    Replaces from the FAQ H2 heading up to (but excluding) the next H2 heading.
    Returns (new_body, changed).
    """
    faq_block = faq_block.rstrip() + "\n"

    m = H2_FAQ_ANYLANG_RE.search(body)
    if not m:
        new_body = body.rstrip() + "\n\n" + faq_block
        return new_body, (new_body != body)

    start = m.start()
    # find end of the FAQ heading line
    line_end = body.find("\n", m.end())
    if line_end == -1:
        line_end = m.end()
    # search next H2 after line_end
    m2 = H2_ANY_RE.search(body, pos=line_end + 1)
    end = m2.start() if m2 else len(body)

    new_body = body[:start] + faq_block + body[end:].lstrip("\n")
    return new_body, (new_body != body)


def build_faq_block(items: List[FaqItem], lang: str) -> str:
    """
    Builds:
      ## FAQ
      ### Question
      Answer
    De-duplicates questions (normalized), keeps first occurrence in sorted order.
    """
    out: List[str] = ["## FAQ", ""]
    seen_q: Set[str] = set()

    for it in items:
        q_raw = rewrite_internal_links(it.question.strip(), lang).strip()
        a_raw = rewrite_internal_links(it.answer.strip(), lang).strip()

        nq = normalize_question(q_raw)
        if not nq or nq in seen_q:
            continue
        seen_q.add(nq)

        out.append(f"### {q_raw}")
        out.append("")
        out.append(a_raw)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def load_faq_csv(csv_path: Path) -> Tuple[List[FaqItem], List[str]]:
    """
    Loads faq.csv. Returns (items, warnings).
    Skips rows that cannot be parsed (but records warning).
    """
    items: List[FaqItem] = []
    warnings: List[str] = []

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"faq_id", "scope_type", "scope_key", "lang", "question", "answer", "order", "status"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            warnings.append(f"faq.csv missing required columns: {sorted(missing)}")
        for idx, row in enumerate(reader, start=2):
            try:
                order_raw = (row.get("order") or "0").strip() or "0"
                order_int = int(order_raw)

                items.append(
                    FaqItem(
                        faq_id=(row.get("faq_id") or "").strip(),
                        scope_type=(row.get("scope_type") or "").strip().lower(),
                        scope_key=(row.get("scope_key") or "").strip().strip("/"),
                        lang=(row.get("lang") or "").strip().lower(),
                        question=(row.get("question") or "").strip(),
                        answer=(row.get("answer") or "").strip(),
                        order=order_int,
                        status=(row.get("status") or "").strip().lower(),
                        tags=(row.get("tags") or "").strip(),
                        source=(row.get("source") or "").strip(),
                    )
                )
            except Exception as e:
                warnings.append(f"faq.csv line {idx}: could not parse row ({e}); skipping")
                continue

    return items, warnings


def write_report(path: Path, touched: List[str], skipped: List[str], warn: List[str], dry_run: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "DRY-RUN" if dry_run else "APPLY"
    lines: List[str] = []
    lines.append(f"# FAQ Sync Report ({mode})")
    lines.append("")
    lines.append(f"- Touched files: {len(touched)}")
    lines.append(f"- Skipped files: {len(skipped)}")
    lines.append(f"- Warnings: {len(warn)}")
    lines.append("")

    if warn:
        lines.append("## Warnings")
        lines.append("")
        for w in warn:
            lines.append(f"- {w}")
        lines.append("")

    if touched:
        lines.append("## Touched files")
        lines.append("")
        for f in touched:
            lines.append(f"- `{f}`")
        lines.append("")

    if skipped:
        lines.append("## Skipped files (managed_by mismatch or out of scope)")
        lines.append("")
        # keep report reasonably sized
        max_list = 200
        for f in skipped[:max_list]:
            lines.append(f"- `{f}`")
        if len(skipped) > max_list:
            lines.append(f"- … ({len(skipped) - max_list} more)")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to faq.csv (relative to working dir)")
    ap.add_argument("--root", required=True, help="Content root, e.g. content")
    ap.add_argument("--apply", action="store_true", help="Write changes (otherwise dry-run)")
    ap.add_argument("--managed-by", default="ssot-sync", help="Only touch files with managed_by matching this (default: ssot-sync)")
    ap.add_argument("--report", default="scripts/reports/faq_sync_report.md", help="Write a markdown report here (relative to root dir)")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging to stdout")
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

    all_items, csv_warnings = load_faq_csv(csv_path)

    # Build map: (scope_type, scope_key, lang) -> items (active)
    # For products, we index both TRxx/yyy and TRxx-yyy variants to be tolerant.
    faq_map: Dict[Tuple[str, str, str], List[FaqItem]] = {}

    for it in all_items:
        if it.status != "active":
            continue
        if it.lang not in ("de", "en"):
            continue
        if it.scope_type not in ("product", "category"):
            continue
        if not it.scope_key:
            continue

        if it.scope_type == "product":
            for v in product_key_variants(it.scope_key):
                key = ("product", v, it.lang)
                faq_map.setdefault(key, []).append(it)
        else:
            key = ("category", it.scope_key.strip("/"), it.lang)
            faq_map.setdefault(key, []).append(it)

    for k in list(faq_map.keys()):
        faq_map[k] = sorted(faq_map[k], key=lambda x: (x.order, x.faq_id))

    touched_files: List[str] = []
    skipped_files: List[str] = []
    warnings: List[str] = []
    warnings.extend(csv_warnings)

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

        try:
            md = p.read_text(encoding="utf-8")
        except Exception as e:
            warnings.append(f"could not read {p}: {e}")
            continue

        fm, body = split_frontmatter(md)

        if managed_by_val:
            mb = parse_managed_by(fm)
            if mb != managed_by_val:
                skipped_files.append(str(p))
                continue

        basename = p.name
        scope_type: Optional[str] = None
        scope_key: Optional[str] = None

        if basename == "_index.md":
            scope_type = "category"
            scope_key = "/".join(rel.parts[1:-1]).strip("/")
            if not scope_key:
                skipped_files.append(str(p))
                continue

            items = faq_map.get((scope_type, scope_key, lang), [])
            if not items:
                # no FAQ for this category in this language
                continue

        elif basename == "index.md":
            # Product pages: only apply under produkte/
            rel_path_str = "/".join(rel.parts[1:])
            if "produkte/" not in rel_path_str:
                skipped_files.append(str(p))
                continue

            scope_type = "product"

            produkt = extract_produkt_fields(fm)
            tkey = extract_translation_key(fm)

            candidates: List[str] = []
            if "id" in produkt:
                candidates.extend(normalize_artikelnummer_to_scope_keys(produkt["id"]))
            if "artikelnummer" in produkt:
                candidates.extend(normalize_artikelnummer_to_scope_keys(produkt["artikelnummer"]))
            if tkey:
                candidates.append(tkey.strip())
            candidates.extend(derive_product_keys_from_path(p))

            candidates = uniq_preserve_order(candidates)

            matched_items: List[FaqItem] = []
            matched_key: Optional[str] = None

            # Try candidates and their variants
            for cand in candidates:
                for v in product_key_variants(cand):
                    items = faq_map.get(("product", v, lang), [])
                    if items:
                        matched_items = items
                        matched_key = v
                        break
                if matched_items:
                    break

            if not matched_items:
                # No FAQ entry for this product/lang
                continue

            scope_key = matched_key or ""

            items = matched_items

        else:
            skipped_files.append(str(p))
            continue

        # Build FAQ block and upsert
        faq_block = build_faq_block(items, lang)

        # Defensive warning: any remaining /wissen/ after rewrite
        if WISSEN_LINK_RE.search(faq_block):
            warnings.append(f"{p}: FAQ block still contains '/wissen/' after rewrite (check faq.csv inputs)")

        new_body, changed = upsert_faq_section(body, faq_block)
        if not changed:
            continue

        new_md = fm + new_body

        if args.apply:
            try:
                p.write_text(new_md, encoding="utf-8")
            except Exception as e:
                warnings.append(f"could not write {p}: {e}")
                continue

        touched_files.append(str(p))

        if args.verbose:
            print(f"[faq_sync] {'UPDATED' if args.apply else 'WOULD UPDATE'}: {p} ({scope_type}:{scope_key}:{lang})")

    # Write report (always)
    report_path = Path(args.report)
    write_repor_
