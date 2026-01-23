#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kategorien-Generator: categories.csv → Hugo Branch Bundles (_index.md)
Version: 2025-12-27 18:59 Europe/Berlin

Ziel
----
- Erzeugt/aktualisiert ausschließlich Kategorie-Seiten als Hugo Branch Bundles:
    wissen/content/de/<path_de>/_index.md
    wissen/content/en/<path_en>/_index.md
- Quelle der Wahrheit: wissen/ssot/categories.csv
- Schreibt ein einheitliches Frontmatter-Schema (translationKey, cascade, seo-Block),
  sodass Templates (Navigation, Breadcrumbs, ItemList/JSON-LD) deterministisch darauf aufbauen können.

Sicherheitsregel
----------------
- Der Generator ist authoritative owner für die in categories.csv gelisteten _index.md:
  Er überschreibt diese Dateien deterministisch (Frontmatter + Body).
- Dateien außerhalb der in categories.csv gelisteten Pfade werden nicht verändert.
- Optionales Pruning (--prune): Entfernt _index.md, die managed_by == "categories.csv" haben,
  aber nicht mehr in categories.csv vorkommen (nur unter den übergebenen Roots).

CSV-Schema (Minimum)
--------------------
Erwartete Spalten (case-insensitiv; '-' und Leerzeichen werden toleriert):
- key
- path_de, path_en
- title_de, title_en
- description_de, description_en
- body_md_de, body_md_en
- meta_title_de, meta_title_en
- meta_description_de, meta_description_en
- weight
- parent_key
- type
- robots
- hero_image
- canonical_de, canonical_en
- is_public

Exit-Codes
----------
0 = OK
2 = CSV/IO/Validation error
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

from ruamel.yaml import YAML

MANAGED_BY = "categories.csv"

yaml = YAML()
yaml.default_flow_style = False
yaml.allow_unicode = True
yaml.width = 4096


def _normkey(k: str) -> str:
    s = (k or "").strip()
    s = s.replace("\ufeff", "")
    s = s.strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"_+", "_", s)
    return s


def clean(s: Optional[str]) -> str:
    return (s or "").strip()


def parse_bool(v: str) -> bool:
    s = clean(v).lower()
    return s in {"1", "true", "yes", "y", "ja", "wahr", "public", "published"}


def parse_int(v: str, default: int = 100) -> int:
    s = clean(v)
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def read_csv_utf8_auto(path: Path) -> List[Dict[str, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;|\t")
        delim = dialect.delimiter
    except Exception:
        delim = ","
    rows = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    norm = [{_normkey(k): ("" if v is None else v) for k, v in r.items()} for r in rows]
    return norm


def read_frontmatter_and_body(p: Path) -> Tuple[Dict, str]:
    if not p.exists():
        return {}, ""
    txt = p.read_text(encoding="utf-8", errors="replace")
    if txt.startswith("---"):
        parts = txt.split("\n---", 1)
        if len(parts) == 2:
            fm_raw = parts[0][3:]
            body = parts[1].lstrip("\n")
            try:
                fm = yaml.load(fm_raw) or {}
                if not isinstance(fm, dict):
                    fm = {}
            except Exception:
                fm = {}
            return fm, body
    return {}, txt


def dump_frontmatter(fm: Dict) -> str:
    buf = io.StringIO()
    yaml.dump(fm, buf)
    return "---\n" + buf.getvalue().strip() + "\n---\n"


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def canonicalize_robots(robots: str, is_public: bool) -> str:
    if not is_public:
        return "noindex,follow"
    r = clean(robots) or "index,follow"
    r = ",".join([x.strip().lower() for x in r.split(",") if x.strip()])
    return r or "index,follow"


@dataclass
class CategoryRow:
    key: str
    path_de: str
    path_en: str
    title_de: str
    title_en: str
    description_de: str
    description_en: str
    body_md_de: str
    body_md_en: str
    meta_title_de: str
    meta_title_en: str
    meta_description_de: str
    meta_description_en: str
    weight: int
    parent_key: str
    type_: str
    robots: str
    hero_image: str
    canonical_de: str
    canonical_en: str
    is_public: bool


def row_to_category(r: Dict[str, str]) -> CategoryRow:
    return CategoryRow(
        key=clean(r.get("key")),
        path_de=clean(r.get("path_de")),
        path_en=clean(r.get("path_en")),
        title_de=clean(r.get("title_de")),
        title_en=clean(r.get("title_en")),
        description_de=clean(r.get("description_de")),
        description_en=clean(r.get("description_en")),
        body_md_de=(r.get("body_md_de") or "").rstrip(),
        body_md_en=(r.get("body_md_en") or "").rstrip(),
        meta_title_de=clean(r.get("meta_title_de")),
        meta_title_en=clean(r.get("meta_title_en")),
        meta_description_de=clean(r.get("meta_description_de")),
        meta_description_en=clean(r.get("meta_description_en")),
        weight=parse_int(r.get("weight"), default=100),
        parent_key=clean(r.get("parent_key")),
        type_=(clean(r.get("type")) or "products"),
        robots=clean(r.get("robots")),
        hero_image=clean(r.get("hero_image")),
        canonical_de=clean(r.get("canonical_de")),
        canonical_en=clean(r.get("canonical_en")),
        is_public=parse_bool(r.get("is_public")),
    )


def validate_categories(rows: List[CategoryRow]) -> List[str]:
    errs: List[str] = []
    seen_keys = set()
    seen_paths_de = set()
    seen_paths_en = set()

    for i, c in enumerate(rows, start=2):  # header line = 1
        if not c.key:
            errs.append(f"Line {i}: missing key")
        else:
            if c.key in seen_keys:
                errs.append(f"Line {i}: duplicate key: {c.key}")
            seen_keys.add(c.key)

        if not c.path_de:
            errs.append(f"Line {i}: missing path_de")
        else:
            if c.path_de in seen_paths_de:
                errs.append(f"Line {i}: duplicate path_de: {c.path_de}")
            seen_paths_de.add(c.path_de)

        if not c.path_en:
            errs.append(f"Line {i}: missing path_en")
        else:
            if c.path_en in seen_paths_en:
                errs.append(f"Line {i}: duplicate path_en: {c.path_en}")
            seen_paths_en.add(c.path_en)

        if not c.title_de:
            errs.append(f"Line {i}: missing title_de for key={c.key}")
        if not c.title_en:
            errs.append(f"Line {i}: missing title_en for key={c.key}")

        if not c.description_de:
            errs.append(f"Line {i}: missing description_de for key={c.key}")
        if not c.description_en:
            errs.append(f"Line {i}: missing description_en for key={c.key}")

    keys = {c.key for c in rows if c.key}
    for c in rows:
        if c.parent_key and c.parent_key not in keys:
            errs.append(f"key={c.key}: parent_key not found: {c.parent_key}")

    return errs


def build_frontmatter(c: CategoryRow, lang: str, now_utc: datetime) -> Tuple[Dict, str]:
    if lang == "de":
        title = c.title_de
        description = c.description_de
        meta_title = c.meta_title_de or c.title_de
        meta_desc = c.meta_description_de or c.description_de
        canonical = c.canonical_de
        body = c.body_md_de
    else:
        title = c.title_en
        description = c.description_en
        meta_title = c.meta_title_en or c.title_en
        meta_desc = c.meta_description_en or c.description_en
        canonical = c.canonical_en
        body = c.body_md_en

    robots = canonicalize_robots(c.robots, c.is_public)
    ts_utc = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    fm = {
        "version": ts_utc,
        "managed_by": MANAGED_BY,
        "last_synced": ts_utc,

        "lang": lang,
        "translationKey": c.key,

        "title": title,
        "description": description,
        "weight": int(c.weight),
        "type": c.type_,

        "seo": {
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "robots": robots,
            "canonical": canonical or "",
            "og_image": c.hero_image or "",
            "is_public": bool(c.is_public),
        },

        "schema": {
            "breadcrumb": True,
            "itemlist": True,
            "organization": True,
        },

        "nav": {
            "show": bool(c.is_public),
            "parent_key": c.parent_key or "",
        },

        "cascade": {
            "category": {
                "key": c.key,
                "parent_key": c.parent_key or "",
                "is_public": bool(c.is_public),
            },
            "seo": {
                "robots": robots,
            },
        },
    }

    body_out = (body.strip() + "\n") if body and body.strip() else ""
    return fm, body_out


def write_index(target: Path, fm: Dict, body: str, apply: bool) -> str:
    new_txt = dump_frontmatter(fm) + body

    if target.exists():
        old_txt = target.read_text(encoding="utf-8", errors="replace")
        if old_txt == new_txt:
            return "unchanged"

    if apply:
        ensure_parent_dir(target)
        target.write_text(new_txt, encoding="utf-8")
        return "updated" if target.exists() else "created"

    return "would-write"
