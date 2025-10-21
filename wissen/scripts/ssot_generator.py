#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSOT -> Markdown Generator (deterministic)
Repo layout target: wissen/content/{de|en}/.../<slug>/index.md

- Liest CSV aus SSOT_CSV_PATH (lokal) oder GSHEET_CSV_URL (Secret) oder GSHEET_ID+GSHEET_GID
- Normalisiert Text (UTF-8, NFC, entfernt ZWSP/NBSP, ersetzt Smart Quotes, --)
- Mappt DE/EN aus einer CSV-Zeile auf je eine Markdown-Datei (index.md)
- YAML: strikt mit ---/---, UTF-8 LF, korrekt gequotet, stabile Feldreihenfolge
- Datentypen: price_cents:int, in_stock:bool, Listen korrekt, Variants normalisiert
- Entfernt "public" aus Pfaden, schreibt nur, wenn Content sich geändert hat (idempotent)
- Pruning: löscht verwaltete Seiten, die nicht mehr in CSV vorkommen

Abhängigkeiten: pandas, requests, python-slugify, ruamel.yaml, Unidecode
"""
from __future__ import annotations

import os
import sys
import re
import io
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

import unicodedata
from unidecode import unidecode
import requests
import pandas as pd
from slugify import slugify as slugify_util

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS

VERSION = "ssot_generator/2025-10-13T12:45:00+02:00"
REPO_ROOT = Path(__file__).resolve().parents[2]  # <repo>/
CONTENT_ROOT = REPO_ROOT / "wissen" / "content"

REQUIRED_COLS = [
    "product_id",
    "slug_de", "slug_en",
    "titel_de", "titel_en",
    "beschreibung_md_de", "beschreibung_md_en",
    "meta_title_de", "meta_title_en",
    "meta_description_de", "meta_description_en",
    "price", "verfuegbar",
    "bilder_liste", "bilder_alt_de", "bilder_alt_en",
    "kategorie_raw",
    "export_pfad_de", "export_pfad_en",
    "tags",
    "langcode_de", "langcode_en",
    "sortierung",
    "varianten_yaml",
    "source_de", "source_en",
    "last_updated",
]

REPLACEMENTS = {
    "\u00A0": " ",   # NBSP
    "\u202F": " ",   # NARROW NBSP
    "\u200B": "",    # ZWSP
    "\u200C": "",    # ZWNJ
    "\u200D": "",    # ZWJ
    "\u2018": "'",   # ‘
    "\u2019": "'",   # ’
    "\u201C": '"',   # “
    "\u201D": '"',   # ”
    "\u2013": "-",   # –
    "\u2014": "-",   # —
    "\u2026": "...", # …
}

PROBLEM_CLASS = {
    "NBSP": "\u00A0",
    "NARROW_NBSP": "\u202F",
    "ZWSP": "\u200B",
    "ZWNJ": "\u200C",
    "ZWJ": "\u200D",
    "SMART_APOSTROPHE": "\u2019",
    "SMART_QUOTE_L": "\u201C",
    "SMART_QUOTE_R": "\u201D",
    "EN_DASH": "\u2013",
    "EM_DASH": "\u2014",
    "ELLIPSIS": "\u2026",
}

YAML_FIELD_ORDER = [
    "managed_by", "id", "slug", "lang",
    "title", "reference",
    "meta_title", "meta_description",
    "price_cents", "in_stock",
    "categories", "tags",
    "images",
    "variants",
    "sort",
    "source_url", "last_updated",
]

def normalize_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFC", s)
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    return s

def has_problem_chars(s: str) -> bool:
    return any(ch in s for ch in PROBLEM_CLASS.values())

def quote_if_needed(s: str) -> SQS:
    if any(x in s for x in [":", "#", "\n", '"', "'", "„", "“", "’"]):
        return SQS(s)
    return SQS(s)

def parse_bool(x: str) -> bool:
    if x is None:
        return False
    s = normalize_text(str(x)).strip().lower()
    return s in {"1", "true", "yes", "ja", "y", "wahr"}

def parse_price_cents(raw: str) -> Optional[int]:
    if raw is None:
        return None
    s = normalize_text(str(raw))
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    if digits.endswith("0000"):
        return int(digits) // 10000
    s2 = s.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        val = float(s2)
        return int(round(val * 100))
    except Exception:
        try:
            val = int(digits)
            return val if val < 10_000_000 else None
        except Exception:
            return None

def split_list_field(s: str) -> List[str]:
    if not s:
        return []
    s = normalize_text(s)
    parts = re.split(r"[,\|]", s)
    return [p.strip() for p in parts if p.strip()]

def sanitize_export_path(lang: str, raw_path: str) -> Path:
    if not raw_path:
        return Path()
    raw = normalize_text(raw_path).strip().strip("/")
    parts = [p for p in raw.split("/") if p]
    if parts and parts[0] in ("de", "en"):
        parts = parts[1:]
    if parts and parts[0] == "public":
        parts = parts[1:]
    return Path(*parts)

def build_images(file_list: List[str], alt_list: List[str]) -> List[Dict[str, Any]]:
    out = []
    for idx, fn in enumerate(file_list):
        fn = normalize_text(fn)
        if not fn:
            continue
        entry: Dict[str, Any] = {"src": f"bilder/{fn}"}
        if idx < len(alt_list):
            alt = normalize_text(alt_list[idx])
            if alt:
                entry["alt"] = alt
        out.append(entry)
    return out

# ---------------------------
# Google Sheets URL handling
# ---------------------------

DOCS_EXPORT_TMPL = "https://docs.google.com/spreadsheets/d/{doc}/export?format=csv&gid={gid}"

def canonicalize_gsheet_url(url: str) -> str:
    u = url.strip()
    if re.match(r"^https://docs\.google\.com/spreadsheets/d/[^/]+/export\?[^ ]*format=csv", u):
        return u
    m = re.search(r"https://docs\.google\.com/spreadsheets/d/([^/]+)/", u)
    if m:
        doc = m.group(1)
        q_gid = re.search(r"(?:[?&]gid=)(\d+)", u)
        f_gid = re.search(r"(?:#gid=)(\d+)", u)
        gid = q_gid.group(1) if q_gid else (f_gid.group(1) if f_gid else "0")
        return DOCS_EXPORT_TMPL.format(doc=doc, gid=gid)
    if "output=csv" in u and "docs.google.com" in u:
        return u
    if "googleusercontent.com/export" in u:
        raise ValueError(
            "Die URL zeigt auf googleusercontent.com/export (session-gebunden). "
            "Bitte eine docs.google.com Export-URL verwenden."
        )
    return u

def resolve_gsheet_source_env() -> Optional[str]:
    url = os.environ.get("GSHEET_CSV_URL", "").strip()
    if not url:
        doc = os.environ.get("GSHEET_ID", "").strip()
        gid = os.environ.get("GSHEET_GID", "").strip() or "0"
        if doc:
            url = DOCS_EXPORT_TMPL.format(doc=doc, gid=gid)
    return url or None

def load_csv() -> pd.DataFrame:
    local = os.environ.get("SSOT_CSV_PATH")
    if local:
        csv_bytes = Path(local).read_bytes()
        data = csv_bytes.decode("utf-8")
    else:
        url = resolve_gsheet_source_env()
        if not url:
            print("ERROR: Neither SSOT_CSV_PATH nor GSHEET_CSV_URL/GSHEET_ID provided.", file=sys.stderr)
            sys.exit(2)
        try:
            url_canon = canonicalize_gsheet_url(url)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(2)
        headers = {
            "User-Agent": "vertaefelungen-ssot-generator/1.0",
            "Accept": "text/csv, text/plain;q=0.9, */*;q=0.1",
        }
        r = requests.get(url_canon, timeout=60, headers=headers)
        try:
            r.raise_for_status()
        except requests.HTTPError:
            print("ERROR: HTTP error for Google Sheets CSV.", file=sys.stderr)
            raise
        data = r.content.decode("utf-8", errors="strict")
        if "<html" in data.lower():
            print("ERROR: Received HTML instead of CSV (vermutlich keine öffentliche Freigabe).", file=sys.stderr)
            sys.exit(2)

    from io import StringIO
    df = pd.read_csv(StringIO(data), dtype=str, keep_default_na=False, na_values=[])
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        print("ERROR: CSV missing required columns: " + ", ".join(missing), file=sys.stderr)
        sys.exit(3)
    return df

# ---------------------------

def parse_variants(yaml_text: str) -> Optional[List[Dict[str, Any]]]:
    yaml_text = normalize_text(yaml_text)
    if not yaml_text.strip():
        return None
    yaml = YAML(typ="safe")
    try:
        data = yaml.load(yaml_text)
        if not isinstance(data, list):
            return None
        out = []
        for item in data:
            if not isinstance(item, dict):
                continue
            new = dict(item)
            if "preis_aufschlag" in new:
                raw = str(new.pop("preis_aufschlag"))
                digits = re.sub(r"[^\d]", "", raw)
                if digits.endswith("0000"):
                    new["preis_aufschlag_cents"] = int(digits) // 10000
                else:
                    rr = raw.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
                    try:
                        val = float(rr)
                        new["preis_aufschlag_cents"] = int(round(val * 100))
                    except Exception:
                        pass
            out.append(new)
        return out or None
    except Exception:
        return None

def make_header(lang: str, row: pd.Series) -> CommentedMap:
    cm = CommentedMap()
    cm["managed_by"] = SQS(VERSION)
    cm["id"] = SQS(normalize_text(row.get("product_id")))
    cm["slug"] = SQS(normalize_text(row.get(f"slug_{lang}")))
    cm["lang"] = SQS(normalize_text(row.get(f"langcode_{lang}") or lang))

    title = normalize_text(row.get(f"titel_{lang}"))
    cm["title"] = quote_if_needed(title)

    ref = normalize_text(row.get("reference"))
    if ref:
        cm["reference"] = quote_if_needed(ref)

    mt = normalize_text(row.get(f"meta_title_{lang}"))
    if mt:
        cm["meta_title"] = quote_if_needed(mt)

    md = normalize_text(row.get(f"meta_description_{lang}"))
    if md:
        cm["meta_description"] = quote_if_needed(md)

    price_cents = parse_price_cents(row.get("price"))
    if price_cents is not None:
        cm["price_cents"] = int(price_cents)

    cm["in_stock"] = bool(parse_bool(row.get("verfuegbar")))

    cats = [normalize_text(x) for x in split_list_field(row.get("kategorie_raw"))]
    if cats:
        cm["categories"] = cats

    tags = [normalize_text(x) for x in split_list_field(row.get("tags"))]
    if tags:
        cm["tags"] = tags

    imgs = split_list_field(row.get("bilder_liste"))
    alts = split_list_field(row.get(f"bilder_alt_{lang}"))
    images = build_images(imgs, alts)
    if images:
        cm["images"] = images

    variants = parse_variants(row.get("varianten_yaml"))
    if variants:
        cm["variants"] = variants

    sort_raw = normalize_text(row.get("sortierung")).strip()
    if sort_raw.isdigit():
        cm["sort"] = int(sort_raw)

    src = normalize_text(row.get(f"source_{lang}"))
    if src:
        cm["source_url"] = src

    lu = normalize_text(row.get("last_updated"))
    if lu:
        cm["last_updated"] = SQS(lu)

    ordered = CommentedMap()
    for k in YAML_FIELD_ORDER:
        if k in cm:
            ordered[k] = cm[k]
    for k in cm:
        if k not in ordered:
            ordered[k] = cm[k]
    return ordered

def write_markdown(lang: str, row: pd.Series, out_dir: Path) -> Path:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 100000
    yaml.indent(mapping=2, sequence=2, offset=2)

    header = make_header(lang, row)
    body = normalize_text(row.get(f"beschreibung_md_{lang}")) or ""

    buf = io.StringIO()
    buf.write("---\n")
    yaml.dump(header, buf)
    buf.write("---\n\n")
    buf.write(body.rstrip() + "\n")

    content
