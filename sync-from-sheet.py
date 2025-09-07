#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generates Markdown files (DE/EN) from a Google Sheet CSV (SSOT) and produces
produkte.de.json / produkte.en.json with RELATIVE paths (repo-root relative).
Designed to run locally and in GitHub Actions (daily).

Updates (2025-09-07):
- Normalize *internal* root-absolute links to RELATIVE links (Markdown + HTML).
- Patch language landing pages (de/index.md, de/_index.md, en/index.md, en/_index.md)
  after generation to ensure links are relative.
"""

import os
import json
import re
import pandas as pd
import requests
from datetime import datetime
import time
from urllib.parse import quote
from io import StringIO

# ============================================================
# Link normalization
# ============================================================

MD_LINK_RE = re.compile(r'(\[([^\]]+)\]\(([^)]+)\))')
HTML_HREF_RE = re.compile(r'href="([^"]+)"')

def _is_external(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith(('http://','https://','mailto:','tel:','data:','#'))

def _to_relative_from_lang_root(url: str, lang: str) -> str:
    u = (url or "").strip()
    if not u.startswith('/'):
        return u
    low = u.lower()
    if low.startswith('/wissen/de/') or low.startswith('/wissen/en/'):
        parts = u.split('/', 4)
        return parts[4] if len(parts) >= 5 else ''
    if low.startswith('/wissen/'):
        return u.split('/wissen/', 1)[1].lstrip('/')
    if low.startswith('/de/') or low.startswith('/en/'):
        parts = u.split('/', 2)
        return parts[2] if len(parts) >= 3 else ''
    return u.lstrip('/')

def normalize_links_in_text(txt: str, lang: str) -> str:
    if not txt:
        return txt
    def md_repl(m):
        full, text, url = m.group(0), m.group(2), m.group(3).strip()
        if _is_external(url):
            return full
        return f'[{text}]({_to_relative_from_lang_root(url, lang)})'
    out = MD_LINK_RE.sub(md_repl, txt)
    def href_repl(m):
        url = m.group(1).strip()
        if _is_external(url):
            return f'href="{url}"'
        return f'href="{_to_relative_from_lang_root(url, lang)}"'
    out = HTML_HREF_RE.sub(href_repl, out)
    return out

# ============================================================
# Robust CSV fetch
# ============================================================

def fetch_sheet_csv(spreadsheet_id=None, sheet_name=None, gid=None, direct_url=None) -> str:
    headers = {"User-Agent": "curl/8.0 (+GitHub Actions sync-from-sheet)"}
    if direct_url:
        candidates = [direct_url]
    else:
        if not spreadsheet_id:
            raise RuntimeError("SHEET_ID fehlt und keine direkte URL übergeben.")
        candidates = []
        if gid:
            candidates.append(f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}")
        if sheet_name:
            candidates.append(f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}")
        candidates.append(f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv")
    last_err = None
    for url in candidates:
        for attempt in (1,2,3):
            try:
                r = requests.get(url, headers=headers, allow_redirects=True, timeout=60)
                ct = r.headers.get("content-type", "")
                if r.status_code == 200 and ("text/csv" in ct or r.text.count(",") > 3):
                    return r.text
                last_err = f"HTTP {r.status_code}, ct={ct}, url={url}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e} (url={url})"
            time.sleep(1.2 * attempt)
    raise RuntimeError(f"CSV-Download fehlgeschlagen: {last_err}")

# ============================================================
# Config
# ============================================================

CONTENT_ROOT = os.getenv("CONTENT_ROOT", ".").strip()
OUTPUT_DIR = os.getenv("OUTPUT_DIR", ".").strip()

COL_EXPORT_DE = "export_pfad_de"
COL_EXPORT_EN = "export_pfad_en"
COL_SLUG_DE   = "slug_de"
COL_SLUG_EN   = "slug_en"
COL_SOURCE_DE = "source_de"
COL_SOURCE_EN = "source_en"
COL_LAST_UPDATED = "last_updated"
COL_ALT_DE = "bilder_alt_de"
COL_ALT_EN = "bilder_alt_en"

# ============================================================
# Fetch sheet
# ============================================================

SHEET_ID   = os.getenv("SHEET_ID", "").strip()
SHEET_GID  = os.getenv("SHEET_GID", "").strip()
SHEET_NAME = os.getenv("SHEET_NAME", "").strip()
DIRECT_URL = os.getenv("SHEET_CSV_URL", "").strip()

csv_text = fetch_sheet_csv(
    spreadsheet_id=SHEET_ID or None,
    sheet_name=SHEET_NAME or None,
    gid=SHEET_GID or None,
    direct_url=DIRECT_URL or None
)
csv_bytes = StringIO(csv_text)
df = pd.read_csv(csv_bytes)
df = df.fillna("")

# ============================================================
# Helpers
# ============================================================

def yaml_list(val):
    if pd.isna(val) or str(val).strip() == "":
        return []
    return [x.strip() for x in str(val).split(",") if x.strip()]

def bilder_liste(val):
    if pd.isna(val) or not str(val).strip():
        return []
    return [b.strip() for b in str(val).split(",") if b.strip()]

def alt_liste(val):
    if pd.isna(val) or not str(val).strip():
        return []
    return [a.strip() for a in str(val).split(",")]

def yaml_safe(s):
    if s is None or pd.isna(s):
        return '""'
    s = str(s).replace('"', "'")
    return f'"{s}"'

def format_price(val):
    try:
        num = int(val)
        euro = num / 1_000_000
        return f"{euro:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return ""

# ============================================================
# Patch Landingpages
# ============================================================

def patch_language_index(lang: str):
    candidates = [
        os.path.join(CONTENT_ROOT, lang, "index.md"),
        os.path.join(CONTENT_ROOT, lang, "_index.md"),
        os.path.join(CONTENT_ROOT, "vertaefelungen", lang, "index.md"),
        os.path.join(CONTENT_ROOT, "vertaefelungen", lang, "_index.md"),
    ]
    for idx_path in candidates:
        if not os.path.isfile(idx_path):
            continue
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                txt = f.read()
            new_txt = normalize_links_in_text(txt, lang=lang)
            if new_txt != txt:
                with open(idx_path, "w", encoding="utf-8") as f:
                    f.write(new_txt)
                print(f"{idx_path}: Links normalisiert (Markdown + HTML).")
            else:
                print(f"{idx_path}: keine Link-Anpassungen nötig.")
        except Exception as e:
            print(f"Warnung: konnte {idx_path} nicht patchen: {e}")

patch_language_index("de")
patch_language_index("en")

# ============================================================
# (Produktdateien schreiben – hier unverändert aus deiner Version)
# ============================================================

# …
# (hier dein bestehender build_content, write_md_files usw. – unverändert)
