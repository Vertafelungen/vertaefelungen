#!/usr/bin/env python3
# Datei: wissen/scripts/sync-from-sheet.py
# Version: 2025-10-12 17:05 (Europe/Berlin)
# Zweck: CSV aus Google Sheets einlesen und HUGO-Markdown je Sprache erzeugen.
# Nutzt NUR Spalten, die WIRKLICH im CSV vorhanden sind (Stand geprüft).
# DE → content/de/oeffentlich/produkte/<path>/index.md
# EN → content/en/public/products/<path>/index.md

import os, re, unicodedata, requests, pandas as pd
from pathlib import Path
from datetime import datetime
from io import StringIO

ROOT = Path(__file__).resolve().parents[1]  # .../wissen
LANG = os.getenv("LANG", "de").lower()         # 'de' oder 'en'
CSV_URL = os.getenv("GSHEET_CSV_URL", "").strip()
TZ = os.getenv("TZ", "Europe/Berlin")

# ---- Sprache → Spaltenmapping (nur vorhandene Spalten aus deinem CSV) ----
FIELDS = {
    "de": {
        "title": "titel_de",
        "body": "beschreibung_md_de",
        "meta_title": "meta_title_de",
        "meta_desc": "meta_description_de",
        "slug": "slug_de",
        "export_path": "export_pfad_de",
        "langcode": "langcode_de",
        "source": "source_de",
    },
    "en": {
        "title": "titel_en",
        "body": "beschreibung_md_en",
        "meta_title": "meta_title_en",
        "meta_desc": "meta_description_en",
        "slug": "slug_en",
        "export_path": "export_pfad_en",
        "langcode": "langcode_en",
        "source": "source_en",
    },
}

COMMON = {
    "id": "product_id",
    "reference": "reference",
    "price": "price",
    "available": "verfuegbar",              # DE-Feld, dient für beide Sprachen → in_stock
    "images": "bilder_liste",
    "alt_de": "bilder_alt_de",
    "alt_en": "bilder_alt_en",
    "category_raw": "kategorie_raw",
    "tags": "tags",
    "sort_order": "sortierung",
    "variants_yaml": "varianten_yaml",
    "last_updated": "last_updated",
}

def out_dir():
    if LANG == "en":
        return ROOT / "content" / "en" / "public" / "products"
    return ROOT / "content" / "de" / "oeffentlich" / "produkte"

def fetch_df() -> pd.DataFrame:
    if not CSV_URL:
        raise SystemExit("GSHEET_CSV_URL ist leer. Bitte Secret setzen.")
    r = requests.get(CSV_URL, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    # Nur Spalten behalten, die wirklich existieren
    keep = set(FIELDS[LANG].values()) | set(COMMON.values())
    keep = [c for c in df.columns if c in keep]
    df = df[keep].copy()
    return df

def try_fix_mojibake(text: str) -> str:
    if not isinstance(text, str):
        return text
    if any(s in text for s in ("Ã", "�", "¤")):
        try:
            fixed = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            return fixed if fixed.count("�") < text.count("�") else text
        except Exception:
            return text
    return text

def slugify(s: str) -> str:
    s = try_fix_mojibake(str(s)).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s or "item"

def parse_bool(val):
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    truthy = {"true","wahr","ja","yes","y","1","verfügbar","verfuegbar","vorrätig","lagernd","available","in stock","instock"}
    falsy  = {"false","falsch","nein","no","n","0","ausverkauft","unavailable","out of stock","outofstock"}
    if s in truthy: return True
    if s in falsy:  return False
    if "nicht" in s or s.startswith("no"): return False
    if "verfügbar" in s or "verfuegbar" in s or "available" in s: return True
    return None

def split_list(s):
    if pd.isna(s) or s is None: return []
    # Trenner: | ; , Zeilenumbruch
    parts = re.split(r"[|;\n,]+", str(s))
    return [p.strip() for p in parts if p.strip()]

def out_path(row: dict) -> Path:
    # bevorzugt export_pfad_*, sonst slug_*
    export_key = FIELDS[LANG]["export_path"]
    slug_key   = FIELDS[LANG]["slug"]
    base = row.get(export_key) or row.get(slug_key) or ""
    base = str(base).strip()
    if not base:
        # fallback: titel → slug
        base = slugify(row.get(FIELDS[LANG]["title"], "item"))
    return out_dir() / base / "index.md"

def yaml_escape(v):
    if v is None: return ""
    s = str(v)
    if any(ch in s for ch in [":","-","{","}","[","]","#","&","*","!",">","|","'",'"',"@",",","?","%"]):
        return '"' + s.replace('"','\\"') + '"'
    return s

def write_md(r: dict) -> Path:
    path = out_path(r)
    path.parent.mkdir(parents=True, exist_ok=True)

    title = r.get(FIELDS[LANG]["title"], "")
    body  = r.get(FIELDS[LANG]["body"], "")
    meta_title = r.get(FIELDS[LANG]["meta_title"], "")
    meta_desc  = r.get(FIELDS[LANG]["meta_desc"], "")
    slug_val   = r.get(FIELDS[LANG]["slug"], "")
    langcode   = r.get(FIELDS[LANG]["langcode"], "")
    source     = r.get(FIELDS[LANG]["source"], "")

    # Gemeinsame Felder
    product_id = r.get(COMMON["id"], "")
    reference  = r.get(COMMON["reference"], "")
    price      = r.get(COMMON["price"], "")
    available  = r.get(COMMON["available"], "")
    in_stock   = parse_bool(available)
    category   = r.get(COMMON["category_raw"], "")
    tags       = split_list(r.get(COMMON["tags"], ""))
    sort_order = r.get(COMMON["sort_order"], "")
    variants_yaml = r.get(COMMON["variants_yaml"], "")
    last_upd   = r.get(COMMON["last_updated"], "")
    # Bilder
    images     = split_list(r.get(COMMON["images"], ""))
    alt_de     = split_list(r.get(COMMON["alt_de"], ""))
    alt_en     = split_list(r.get(COMMON["alt_en"], ""))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Frontmatter bauen – nur vorhandene Felder befüllen
    fm = []
    fm.append("---")
    if title:       fm.append(f'title: {yaml_escape(title)}')
    if meta_title:  fm.append(f'meta_title: {yaml_escape(meta_title)}')
    if meta_desc:   fm.append(f'meta_description: {yaml_escape(meta_desc)}')
    if slug_val:    fm.append(f'slug: {yaml_escape(slug_val)}')
    if langcode:    fm.append(f'lang: {yaml_escape(langcode)}')
    if product_id:  fm.append(f'product_id: {yaml_escape(product_id)}')
    if reference:   fm.append(f'reference: {yaml_escape(reference)}')
    if price != "": fm.append(f'price: {yaml_escape(price)}')  # fixer wandelt später in price_cents
    if in_stock is not None: fm.append(f'in_stock: {"true" if in_stock else "false"}')
    if category:    fm.append(f'category_raw: {yaml_escape(category)}')
    if sort_order != "": fm.append(f'sort: {yaml_escape(sort_order)}')
    if tags:        fm.append("tags: [" + ", ".join(yaml_escape(t) for t in tags) + "]")
    # Varianten (falls schon YAML im Feld):
    if isinstance(variants_yaml, str) and variants_yaml.strip():
        fm.append("varianten:")
        for line in variants_yaml.splitlines():
            fm.append(str(line))
    # Bildergruppen schlicht übernehmen
    if images:
        fm.append("bilder:")
        for p in images:
            fm.append(f"  - {yaml_escape(p)}")
    if LANG == "de" and alt_de:
        fm.append("bilder_alt:")
        for a in alt_de:
            fm.append(f"  - {yaml_escape(a)}")
    if LANG == "en" and alt_en:
        fm.append("images_alt:")
        for a in alt_en:
            fm.append(f"  - {yaml_escape(a)}")
    if source:      fm.append(f'source: {yaml_escape(source)}')
    if last_upd:    fm.append(f'last_updated: {yaml_escape(last_upd)}')
    fm.append(f'generated_at: "{now} {TZ}"')
    fm.append("---")

    # Body (kleine Link-Korrektur: (...).md → (...)/ )
    body = str(body or "")
    body = re.sub(r'\((/[^)]+?)\.md\)', r'(\1/)', body)

    path.write_text("\n".join(fm) + "\n" + body, encoding="utf-8")
    return path

def main():
    df = fetch_df()
    n = 0
    for _, row in df.iterrows():
        write_md(row.to_dict())
        n += 1
    print(f"✓ {n} Seiten → {out_dir()}")

if __name__ == "__main__":
    main()
