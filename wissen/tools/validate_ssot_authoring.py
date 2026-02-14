#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/tools/validate_ssot_authoring.py
Version: 2026-02-14T13:10:00+01:00 (Europe/Berlin)

Purpose:
  Validiert SSOT Authoring-Stand in:
    - wissen/ssot/SSOT.csv
    - wissen/ssot/categories.csv
    - wissen/ssot/faq.csv

Checks:
  - Required body columns exist in SSOT/categories (FAQ columns are deprecated and ignored)
  - No /wissen/ links inside any authoring fields (SSOT/categories body + FAQ question/answer)
  - FAQ count constraints met:
      products: 5–8 per language (active)
      categories: 8–12 per language (active)
  - FAQ dedupe per (scope_type, scope_key, lang) on normalized question
  - Basic mapping sanity (product_id vs export_pfad heuristic)
  - Scope_key validity for categories (relative path form)

Exit codes:
  0 = OK
  1 = Issues found
  2 = File missing / parse error
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, DefaultDict
from collections import defaultdict


# Required body fields (FAQ is not here; FAQ lives in faq.csv)
REQ_BODY_FIELDS = [
    "body_de_kurzantwort",
    "body_de_praxis",
    "body_de_varianten",
    "body_de_ablauf",
    "body_de_kosten",
    "body_de_fehler",
    "body_de_verweise",
    "body_en_kurzantwort",
    "body_en_praxis",
    "body_en_varianten",
    "body_en_ablauf",
    "body_en_kosten",
    "body_en_fehler",
    "body_en_verweise",
]

WISSEN_LINK_RE = re.compile(r"(\]\(/wissen/|https?://[^,\s)]+/wissen/|/wissen/)", re.IGNORECASE)

def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)

def load_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = [row for row in reader]
    return headers, rows

def detect_key(headers: List[str], candidates: List[str]) -> str | None:
    hset = {h.strip() for h in headers}
    for c in candidates:
        if c in hset:
            return c
    return None

def is_row_inactive(row: Dict[str, str]) -> bool:
    # best-effort standard status flags
    for k in ["status", "active", "enabled", "publish", "published", "draft"]:
        if k in row:
            v = (row.get(k) or "").strip().lower()
            if k == "draft" and v in ["1", "true", "yes", "y"]:
                return True
            if k in ["active", "enabled", "publish", "published"]:
                if v in ["0", "false", "no", "n"]:
                    return True
            if k == "status" and v in ["inactive", "archived", "disabled", "draft"]:
                return True
    return False

def contains_wissen_links(text: str) -> bool:
    return bool(text and WISSEN_LINK_RE.search(text))

def normalize_question(q: str) -> str:
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q

def looks_like_relative_category_key(key: str) -> bool:
    # Must be relative path: no leading slash, no "content/de", no protocol, no ".."
    if not key:
        return False
    k = key.strip()
    if k.startswith("/") or k.startswith("\\"):
        return False
    if "content/de" in k.lower() or "content\\de" in k.lower():
        return False
    if "://" in k:
        return False
    if ".." in k:
        return False
    # allow a-z0-9-_/
    return bool(re.fullmatch(r"[a-z0-9_\-\/]+", k.lower()))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="Repo root")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    ssot = repo / "wissen" / "ssot" / "SSOT.csv"
    cats = repo / "wissen" / "ssot" / "categories.csv"
    faq = repo / "wissen" / "ssot" / "faq.csv"

    for p in [ssot, cats, faq]:
        if not p.exists():
            eprint(f"ERROR: missing file: {p}")
            return 2

    try:
        ssot_h, ssot_rows = load_csv(ssot)
        cats_h, cats_rows = load_csv(cats)
        faq_h, faq_rows = load_csv(faq)
    except Exception as e:
        eprint(f"ERROR: CSV parse failed: {e}")
        return 2

    issues: List[str] = []

    # Schema checks
    missing_ssot = [f for f in REQ_BODY_FIELDS if f not in ssot_h]
    missing_cats = [f for f in REQ_BODY_FIELDS if f not in cats_h]
    if missing_ssot:
        issues.append(f"SSOT.csv: missing required body columns: {', '.join(missing_ssot)}")
    if missing_cats:
        issues.append(f"categories.csv: missing required body columns: {', '.join(missing_cats)}")

    # FAQ header minimum
    faq_required = ["faq_id", "scope_type", "scope_key", "lang", "question", "answer", "order", "status"]
    faq_missing = [f for f in faq_required if f not in faq_h]
    if faq_missing:
        issues.append(f"faq.csv: missing required columns: {', '.join(faq_missing)}")

    # Keys for diagnostics
    ssot_pid_key = detect_key(ssot_h, ["product_id", "produkt.id", "produkt_id", "id"])
    ssot_path_key = detect_key(ssot_h, ["export_pfad_de", "path_de", "de_path", "content_path_de"])
    cats_path_key = detect_key(cats_h, ["export_pfad_de", "path_de", "de_path", "content_path_de"])

    # Build sets for expected scopes
    product_ids: set[str] = set()
    category_keys: set[str] = set()

    if ssot_pid_key:
        for r in ssot_rows:
            if is_row_inactive(r):
                continue
            pid = (r.get(ssot_pid_key) or "").strip()
            if pid:
                product_ids.add(pid)

    if cats_path_key:
        for r in cats_rows:
            if is_row_inactive(r):
                continue
            p = (r.get(cats_path_key) or "").strip().strip("/")
            if p:
                category_keys.add(p)

    # Link checks in body fields (only enforce on filled rows)
    def check_body_links(name: str, headers: List[str], rows: List[Dict[str, str]]) -> None:
        for i, r in enumerate(rows, start=2):
            if is_row_inactive(r):
                continue
            touched = any((r.get(f, "") or "").strip() for f in REQ_BODY_FIELDS if f in headers)
            if not touched:
                continue
            bad = []
            for f in REQ_BODY_FIELDS:
                if f in headers and contains_wissen_links(r.get(f, "") or ""):
                    bad.append(f)
            if bad:
                issues.append(f"{name} line {i}: contains /wissen/ links in fields: {bad}")

    check_body_links("SSOT.csv", ssot_h, ssot_rows)
    check_body_links("categories.csv", cats_h, cats_rows)

    # Basic product id / path mismatch heuristic
    if ssot_pid_key and ssot_path_key:
        for i, r in enumerate(ssot_rows, start=2):
            if is_row_inactive(r):
                continue
            pid_raw = (r.get(ssot_pid_key) or "").strip()
            pth = (r.get(ssot_path_key) or "").strip().lower()
            if not pid_raw or not pth:
                continue
            pid = pid_raw.lower().replace("/", "-")
            # heuristic: "tr01" should appear in path when applicable
            if pid.startswith("tr") and pid.split("-")[0] not in pth:
                # not always guaranteed, so treat as warning-level issue
                issues.append(f"SSOT.csv line {i}: possible id/path mismatch: {ssot_pid_key}={pid_raw} vs {ssot_path_key}={r.get(ssot_path_key)}")

    # FAQ validation
    # Group counts by (scope_type, scope_key, lang) for active
    counts: DefaultDict[Tuple[str, str, str], int] = defaultdict(int)
    questions_seen: DefaultDict[Tuple[str, str, str], set[str]] = defaultdict(set)

    for i, r in enumerate(faq_rows, start=2):
        faq_id = (r.get("faq_id") or "").strip()
        scope_type = (r.get("scope_type") or "").strip().lower()
        scope_key = (r.get("scope_key") or "").strip().strip("/")
        lang = (r.get("lang") or "").strip().lower()
        q = (r.get("question") or "").strip()
        a = (r.get("answer") or "").strip()
        status = (r.get("status") or "").strip().lower()
        order = (r.get("order") or "").strip()

        # Required fields present
        if not faq_id or not scope_type or not scope_key or not lang or not q or not a or not order or not status:
            issues.append(f"faq.csv line {i}: missing required values (faq_id/scope_type/scope_key/lang/question/answer/order/status)")
            continue

        if scope_type not in ["product", "category", "global"]:
            issues.append(f"faq.csv line {i}: invalid scope_type '{scope_type}'")
        if lang not in ["de", "en"]:
            issues.append(f"faq.csv line {i}: invalid lang '{lang}'")
        try:
            int(order)
        except Exception:
            issues.append(f"faq.csv line {i}: order is not an integer: '{order}'")

        if contains_wissen_links(q) or contains_wissen_links(a):
            issues.append(f"faq.csv line {i}: contains /wissen/ link in question/answer")

        # scope_key validation
        if scope_type == "category" and not looks_like_relative_category_key(scope_key):
            issues.append(f"faq.csv line {i}: category scope_key not a clean relative path: '{scope_key}'")

        if status == "active":
            key = (scope_type, scope_key, lang)
            counts[key] += 1

            nq = normalize_question(q)
            if nq in questions_seen[key]:
                issues.append(f"faq.csv line {i}: duplicate question in scope/lang: '{q}'")
            else:
                questions_seen[key].add(nq)

    # Enforce counts for scopes we know (only if there is at least some FAQ content for that scope)
    # Products
    for pid in sorted(product_ids):
        for lang in ["de", "en"]:
            key = ("product", pid, lang)
            c = counts.get(key, 0)
            if c == 0:
                continue  # allow incomplete authoring without failing on untouched products
            if not (5 <= c <= 8):
                issues.append(f"faq.csv: product {pid} lang {lang} active FAQ count {c} (expected 5–8)")

    # Categories
    for ck in sorted(category_keys):
        for lang in ["de", "en"]:
            key = ("category", ck, lang)
            c = counts.get(key, 0)
            if c == 0:
                continue
            if not (8 <= c <= 12):
                issues.append(f"faq.csv: category {ck} lang {lang} active FAQ count {c} (expected 8–12)")

    if issues:
        print("SSOT AUTHORING VALIDATION: FAIL\n")
        for msg in issues:
            print("-", msg)
        return 1

    print("SSOT AUTHORING VALIDATION: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
