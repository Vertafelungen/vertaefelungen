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
# Link normalization (Markdown + HTML) → internal root paths → RELATIVE
# ============================================================

MD_LINK_RE = re.compile(r'(\[([^\]]+)\]\(([^)]+)\))')
HTML_HREF_RE = re.compile(r'href="([^"]+)"')

def _is_external(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith(('http://','https://','mailto:','tel:','data:','#'))

def _to_relative_from_lang_root(url: str, lang: str) -> str:
    """
    Convert internal root-absolute URLs into relative paths from <lang>/... context.
    """
    u = (url or "").strip()
    if not u.startswith('/'):
        return u
    low = u.lower()

    if low.startswith('/wissen/de/') or low.startswith('/wissen/en/'):
        parts = u.split('/', 4)      # ['', 'wissen', '<lang>', '...']
        return parts[4] if len(parts) >= 5 else ''

    if low.startswith('/wissen/'):   # missing language
        return u.split('/wissen/', 1)[1].lstrip('/')

    if low.startswith('/de/') or low.startswith('/en/'):
        parts = u.split('/', 2)      # ['', 'de', '...']
        return parts[2] if len(parts) >= 3 else ''

    # any other root path
    return u.lstrip('/')

def normalize_links_in_text(txt: str, lang: str) -> str:
    """
    Normalize internal root-absolute links to RELATIVE in Markdown + HTML.
    """
    if not txt:
        return txt

    # Markdown links
    def md_repl(m):
        full, text, url = m.group(0), m.group(2), m.group(3).strip()
        if _is_external(url):
            return full
        return f'[{text}]({_to_relative_from_lang_root(url, lang)})'
    out = MD_LINK_RE.sub(md_repl, txt)

    # HTML href="..."
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
    """
    Liefert CSV-Text stabil zurück. Reihenfolge:
    1) direct_url, 2) export?format=csv&gid=..., 3) gviz tqx=out:csv&sheet=..., 4) export?format=csv
    """
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

CONTENT_ROOT = os.getenv("CONTENT_ROOT", ".").strip()   # i.d.R. '.' (Repo-Root)
OUTPUT_DIR   = os.getenv("OUTPUT_DIR", ".").strip()

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

def _short_summary(text, limit=240):
    if text is None or pd.isna(text):
        return ""
    s = " ".join(str(text).split())
    return s[:limit]

# ============================================================
# Build single product page (DE/EN)
# ============================================================

def format_varianten_yaml(varianten_str):
    if not varianten_str or pd.isna(varianten_str):
        return ""
    lines = []
    for line in str(varianten_str).split("\n"):
        stripped = line.strip()
        if stripped.startswith('- '):
            lines.append('  ' + stripped)
        elif "preis_aufschlag:" in line:
            key, val = line.split(":", 1)
            val = val.strip()
            # preis_aufschlag ist im Sheet in Mikro-Euro; umformatieren:
            try:
                num = int(val)
                euro = num / 1_000_000
                price = f"{euro:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
            except Exception:
                price = val
            lines.append(f"    preis_aufschlag: {price}")
        elif stripped:
            lines.append('    ' + stripped)
    return "\n".join(lines)

def bilder_aus_sheet(row, lang):
    bilder = bilder_liste(row.get("bilder_liste", ""))
    if lang == "de":
        bilder_alt = [a.strip() for a in str(row.get(COL_ALT_DE, "")).split(",")] if row.get(COL_ALT_DE, "") else []
    else:
        bilder_alt = [a.strip() for a in str(row.get(COL_ALT_EN, "")).split(",")] if row.get(COL_ALT_EN, "") else []
    return bilder, bilder_alt

def build_content(row, lang="de"):
    if lang == "de":
        slug = row.get("slug_de", "")
        titel = row.get("titel_de", "")
        beschreibung = row.get("beschreibung_md_de", "")
        meta_title = row.get("meta_title_de", "")
        meta_description = row.get("meta_description_de", "")
        kategorie = row.get("kategorie_raw", "")
        verfuegbar = row.get("verfuegbar", "")
        price_raw = row.get("price", "")
        varianten_yaml_raw = row.get("varianten_yaml", "")
        tags = [x.strip() for x in str(row.get("tags", "")).split(",") if x.strip()]
        sortierung = row.get("sortierung", "")
        langcode = row.get("langcode_de", "")
        source_url = str(row.get(COL_SOURCE_DE, "") or "").strip()
    else:
        slug = row.get("slug_en", "")
        titel = row.get("titel_en", "")
        beschreibung = row.get("beschreibung_md_en", "")
        meta_title = row.get("meta_title_en", "")
        meta_description = row.get("meta_description_en", "")
        kategorie = row.get("kategorie_raw", "")
        verfuegbar = row.get("verfuegbar", "")
        price_raw = row.get("price", "")
        varianten_yaml_raw = row.get("varianten_yaml", "")
        tags = [x.strip() for x in str(row.get("tags", "")).split(",") if x.strip()]
        sortierung = row.get("sortierung", "")
        langcode = row.get("langcode_en", "")
        source_url = str(row.get(COL_SOURCE_EN, "") or "").strip()

    product_id = row.get("product_id", "")
    reference  = row.get("reference", "")
    last_updated = str(row.get(COL_LAST_UPDATED, "") or "").strip()

    price = format_price(price_raw)
    varianten_yaml = format_varianten_yaml(varianten_yaml_raw)
    bilder, bilder_alt = bilder_aus_sheet(row, lang)

    beschreibung_text = ""
    if pd.notna(beschreibung):
        beschreibung_text = normalize_links_in_text(str(beschreibung).replace("\n", " "), lang)

    meta_title_text = "" if pd.isna(meta_title) else str(meta_title)
    meta_description_text = "" if pd.isna(meta_description) else str(meta_description)

    # YAML
    yaml_lines = []
    yaml_lines.append("---")
    yaml_lines.append(f"slug: {yaml_safe(slug)}")
    yaml_lines.append(f"product_id: {yaml_safe(product_id)}")
    yaml_lines.append(f"reference: {yaml_safe(reference)}")
    yaml_lines.append(f"titel: {yaml_safe(titel)}")
    yaml_lines.append(f"kategorie: {yaml_safe(kategorie)}")
    yaml_lines.append("beschreibung: >")
    yaml_lines.append(f"  {beschreibung_text}")
    yaml_lines.append(f"meta_title: {yaml_safe(meta_title_text)}")
    yaml_lines.append(f"meta_description: {yaml_safe(meta_description_text)}")
    yaml_lines.append("bilder:")
    if bilder:
        for b in bilder:
            yaml_lines.append(f"  - {b}")
    else:
        yaml_lines.append("  -")
    yaml_lines.append("bilder_alt:")
    if bilder:
        for i in range(len(bilder)):
            alt = bilder_alt[i] if i < len(bilder_alt) else ""
            yaml_lines.append(f"  - {yaml_safe(alt)}")
    else:
        yaml_lines.append("  -")
    yaml_lines.append(f"price: {yaml_safe(price)}")
    yaml_lines.append(f"verfuegbar: {yaml_safe(verfuegbar)}")
    yaml_lines.append("varianten_yaml: |")
    yaml_lines.append(varianten_yaml if varianten_yaml else "  ")
    yaml_lines.append(f"tags: {tags if tags else '[]'}")
    yaml_lines.append(f"sortierung: {yaml_safe(sortierung)}")
    yaml_lines.append(f"langcode: {yaml_safe(langcode)}")
    yaml_lines.append(f"author: {yaml_safe('Tobias Klaus')}")
    yaml_lines.append(f"author_url: {yaml_safe('https://www.vertaefelungen.de/de/content/4-uber-uns')}")
    yaml_lines.append(f"license: {yaml_safe('CC BY-SA 4.0')}")
    yaml_lines.append(f"source: {yaml_safe(source_url)}")
    yaml_lines.append(f"last_updated: {yaml_safe(last_updated)}")
    yaml_lines.append("---")
    yaml_block = "\n".join(yaml_lines)

    # Markdown body
    body_parts = []
    body_parts.append(f"# {titel}")
    body_parts.append("")
    body_parts.append(beschreibung_text)
    body_parts.append("")
    body_parts.append("## Technische Daten")
    body_parts.append("")
    body_parts.append(f"- Referenz: {reference}")
    body_parts.append(f"- Preis: {price}")
    body_parts.append(f"- Verfügbar: {verfuegbar}")
    body_parts.append(f"- Kategorie: {kategorie}")
    body_parts.append(f"- Sortierung: {sortierung}")
    body_parts.append("")
    body_parts.append("## Varianten")
    body_parts.append("")
    body_parts.append(varianten_yaml if varianten_yaml else "_keine Varianten hinterlegt_")
    body_parts.append("")
    body_parts.append("## Bilder")
    body_parts.append("")
    if bilder:
        for i, b in enumerate(bilder):
            alt = bilder_alt[i] if i < len(bilder_alt) else ""
            body_parts.append(f"![{alt}]({b})")
    else:
        body_parts.append("_keine Bilder hinterlegt_")
    body_parts.append("")
    body_parts.append("## SEO-Metadaten")
    body_parts.append("")
    body_parts.append(f"- meta_title: {meta_title_text}")
    body_parts.append(f"- meta_description: {meta_description_text}")
    body_parts.append("")
    body_parts.append("## Tags")
    body_parts.append("")
    body_parts.append(", ".join(tags) if tags else "_keine Tags hinterlegt_")
    body_parts.append("")

    body_md = "\n".join(body_parts)
    body_md = normalize_links_in_text(body_md, lang)

    content = yaml_block + "\n\n" + body_md

    json_item = {
        "path": "",
        "slug": str(slug or "").strip(),
        "category": str(kategorie or "").strip(),
        "title": str(titel or "").strip(),
        "has_yaml": True,
        "summary": _short_summary(beschreibung_text),
        "images": bilder,
        "images_alt": bilder_alt,
        "author": "Tobias Klaus",
        "author_url": "https://www.vertaefelungen.de/de/content/4-uber-uns",
        "license": "CC BY-SA 4.0",
        "source": source_url,
        "last_updated": last_updated
    }
    return content, titel, beschreibung_text, meta_title_text, json_item

catalog_de = []
catalog_en = []

def write_md_files(export_col, slug_col, lang):
    for _, row in df.iterrows():
        pfad = str(row.get(export_col, "")).strip() if not pd.isna(row.get(export_col, "")) else ''
        slug = str(row.get(slug_col, "")).strip() if not pd.isna(row.get(slug_col, "")) else ''
        if pfad and slug:
            full_dir = os.path.join(CONTENT_ROOT, pfad.strip().strip('/')).replace("\\", "/")
            os.makedirs(full_dir, exist_ok=True)
            full_path = f"{full_dir}/{slug}.md"
            content, titel, beschreibung, meta_title, json_item = build_content(row, lang)

            print("-" * 40)
            print(f"File: {full_path}")
            print("Titel:", titel)
            print("Beschreibung (Ausschnitt):", (beschreibung[:80] if isinstance(beschreibung, str) else ""))
            print("Meta-Title:", meta_title)
            print("-" * 40)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{full_path} geschrieben.")

            rel = os.path.relpath(full_path, CONTENT_ROOT).replace("\\", "/") if CONTENT_ROOT else full_path.replace("\\", "/")
            if rel.startswith("./"):
                rel = rel[2:]
            json_item["path"] = rel
            if lang == "de":
                catalog_de.append(json_item)
            else:
                catalog_en.append(json_item)

# Produktseiten erzeugen
write_md_files(COL_EXPORT_DE, COL_SLUG_DE, lang="de")
write_md_files(COL_EXPORT_EN, COL_SLUG_EN, lang="en")

# ============================================================
# Patch landing pages (de/en): make links relative in index files
# ============================================================

def patch_language_index(lang: str):
    candidates = [
        os.path.join(CONTENT_ROOT, lang, "index.md"),
        os.path.join(CONTENT_ROOT, lang, "_index.md"),
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
# Write JSON catalogs
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)
de_path = os.path.join(OUTPUT_DIR, "produkte.de.json")
en_path = os.path.join(OUTPUT_DIR, "produkte.en.json")

produkte_de = {"language": "de", "generated": datetime.now().isoformat(), "items": catalog_de}
produkte_en = {"language": "en", "generated": datetime.now().isoformat(), "items": catalog_en}

with open(de_path, "w", encoding="utf-8") as f:
    json.dump(produkte_de, f, ensure_ascii=False, indent=2)
with open(en_path, "w", encoding="utf-8") as f:
    json.dump(produkte_en, f, ensure_ascii=False, indent=2)

print(f"{de_path} und {en_path} geschrieben.")
