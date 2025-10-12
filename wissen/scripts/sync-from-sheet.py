#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync from Sheet → Markdown (DE/EN) für Produkte (+ optional FAQ).

- Einzeln konfigurierbare Spaltennamen im COLUMNS-Block unten.
- Unicode-Sanitizing: NBSP/Zero-Width raus, CRLF→LF, Tabs→Spaces.
- Tolerantes Matching Bilder/Alt-Texte (fehlende Alt-Texte -> Titel).
- Varianten: übernimmt YAML aus 'varianten_yaml' (oder parse-tolerant).
- Pfadbildung: <export_pfad_de>/<slug_de>/index.md (analog EN).
- Optional: FAQ-Sheet (wenn SECRET 'FAQ_SHEET_CSV' gesetzt ist).

ENV:
  - PRODUCTS_SHEET_CSV (Pflicht)
  - FAQ_SHEET_CSV      (optional)
"""

from __future__ import annotations
from pathlib import Path
import csv, os, re, sys, unicodedata, textwrap
import requests
import yaml

# ---------- Konfiguration: Spaltennamen aus deinem Sheet ----------
COLUMNS = {
    # Generische Produktfelder
    "id":                   "product_id",
    "sku":                  "reference",
    "slug_de":              "slug_de",
    "slug_en":              "slug_en",
    "title_de":             "titel_de",
    "title_en":             "titel_en",
    "desc_md_de":           "beschreibung_md_de",
    "desc_md_en":           "beschreibung_md_en",
    "meta_title_de":        "meta_title_de",
    "meta_title_en":        "meta_title_en",
    "meta_desc_de":         "meta_description_de",
    "meta_desc_en":         "meta_description_en",
    "price":                "price",            # Integer: Cent (oder wie im Sheet definiert)
    "in_stock":             "verfuegbar",       # 1 oder 0
    "variant_name":         "variante_kurz_bez",# optional (nicht zwingend)
    "variants_yaml":        "varianten_yaml",
    "images":               "bilder_liste",     # Kommasepariert
    "images_alt_de":        "bilder_alt_de",    # Kommasepariert
    "images_alt_en":        "bilder_alt_en",    # Kommasepariert
    "category_raw":         "kategorie_raw",    # Kommasepariert
    "export_path_de":       "export_pfad_de",   # z.B. de/oeffentlich/produkte/leisten/wandleisten
    "export_path_en":       "export_pfad_en",   # z.B. en/public/products/mouldings/wall-mouldings
    "tags":                 "tags",             # Komma/Semikolon
    "source_de":            "source_de",
    "source_en":            "source_en",
    "last_updated":         "last_updated",
}

# Optionales FAQ-Sheet (wenn vorhanden) – Spaltennamen:
FAQ_COLUMNS = {
    "slug_de":    "slug_de",
    "slug_en":    "slug_en",
    "title_de":   "frage_de",
    "title_en":   "frage_en",
    "answer_de":  "antwort_md_de",
    "answer_en":  "antwort_md_en",
    "tags":       "tags",
}

# ---------- Pfade ----------
ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
DE_PROD = CONTENT / "de"
EN_PROD = CONTENT / "en"

# ---------- Unicode/Whitespace Normalisierung ----------
BOM = "\ufeff"
CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
SPACE_MAP = {
    **{ord(c): " " for c in " \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000"},
    ord("\u200B"): None, ord("\u200C"): None, ord("\u200D"): None, ord("\u2060"): None,
    ord("\u200E"): None, ord("\u200F"): None, ord("\u2028"): " ", ord("\u2029"): " ",
}
def norm(s: str) -> str:
    if s is None:
        return ""
    s = str(s).replace(BOM, "")
    s = unicodedata.normalize("NFKC", s).translate(SPACE_MAP).replace("\r\n","\n")
    s = CTRL_RE.sub(" ", s)
    return s

def detab(s: str) -> str:
    return re.sub(r'^\t+', lambda m:"  "*len(m.group(0)), s, flags=re.M)

def nstrip(s: str) -> str:
    return norm(s).strip()

# ---------- Helpers ----------
def fetch_csv(url: str) -> list[dict]:
    if not url:
        return []
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("CSV-URL muss mit http(s) beginnen")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    txt = norm(r.text)
    return list(csv.DictReader(txt.splitlines()))

def split_any(s: str) -> list[str]:
    s = norm(s)
    if ";" in s and "," in s:
        # Trenne zuerst Semikolon grob, dann Komma innerhalb
        items = []
        for chunk in s.split(";"):
            items += [x.strip() for x in chunk.split(",")]
        return [x for x in items if x]
    # sonst: Komma oder Semikolon
    parts = re.split(r"[;,]", s)
    return [p.strip() for p in parts if p.strip()]

def as_int(s: str, default: int = 0) -> int:
    s = nstrip(s)
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def write_text(p: Path, content: str):
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-8")

def literal_block(key: str, value: str) -> list[str]:
    lines = [f"{key}: |"]
    for ln in norm(value).splitlines():
        lines.append(f"  {ln}")
    return lines

def yaml_list(key: str, seq: list[str]) -> list[str]:
    out = [f"{key}:"]
    for el in seq:
        out.append(f"  - {norm(el)}")
    return out

def yaml_variants(key: str, variants) -> list[str]:
    """Accept YAML list, stringified YAML, or []"""
    if isinstance(variants, str):
        v = nstrip(variants)
        if not v:
            return []
        try:
            parsed = yaml.safe_load(v)
        except Exception:
            parsed = []
        variants = parsed
    if not variants:
        return []
    out = [f"{key}:"]
    if isinstance(variants, list):
        for item in variants:
            if isinstance(item, dict):
                out.append("  -")
                for kk, vv in item.items():
                    out.append(f"    {kk}: {vv}")
            else:
                out.append(f"  - {item}")
    else:
        # fallback: dump as nested yaml
        dumped = yaml.safe_dump(variants, allow_unicode=True, sort_keys=False).splitlines()
        out.append("  # WARNING: variants had non-list structure")
        out += [("  " + ln) for ln in dumped]
    return out

def align_images_and_alts(images: list[str], alts: list[str], fallback_title: str) -> tuple[list[str], list[str]]:
    imgs = [img for img in images if img]
    alts = [a for a in alts if a]
    if not imgs:
        return [], []
    if len(alts) < len(imgs):
        alts = alts + [fallback_title] * (len(imgs) - len(alts))
    if len(alts) > len(imgs):
        alts = alts[:len(imgs)]
    return imgs, alts

def sanitize_path(path_str: str) -> str:
    # verhindert //, führende oder trailing slashes
    s = path_str.strip().strip("/").replace("//","/")
    return s

def build_frontmatter_product(rec: dict, lang: str) -> tuple[str, str]:
    get = lambda k: rec.get(COLUMNS[k], "") if COLUMNS.get(k) in rec else rec.get(k, "")

    title   = nstrip(get("title_de") if lang=="de" else get("title_en"))
    slug    = nstrip(get("slug_de")  if lang=="de" else get("slug_en"))
    sku     = nstrip(get("sku"))
    price_cents = as_int(get("price"), 0)
    in_stock = 1 if nstrip(get("in_stock")) in ("1","true","True","yes","ja") else 0

    export_path = nstrip(get("export_path_de") if lang=="de" else get("export_path_en"))
    export_path = sanitize_path(export_path)
    if not export_path:
        # sinnvolle Defaults
        export_path = "de/oeffentlich/produkte" if lang=="de" else "en/public/products"

    images = split_any(get("images"))
    alts   = split_any(get("images_alt_de") if lang=="de" else get("images_alt_en"))
    images, alts = align_images_and_alts(images, alts, fallback_title=title)

    cats = [c for c in split_any(get("category_raw")) if c.lower() != "artikel"]
    tags = split_any(get("tags"))

    desc  = nstrip(get("desc_md_de") if lang=="de" else get("desc_md_en"))
    mtitle = nstrip(get("meta_title_de") if lang=="de" else get("meta_title_en"))
    mdesc  = nstrip(get("meta_desc_de")  if lang=="de" else get("meta_desc_en"))
    source = nstrip(get("source_de") if lang=="de" else get("source_en"))
    last_updated = nstrip(get("last_updated"))

    variants = rec.get(COLUMNS["variants_yaml"], rec.get("variants_yaml", ""))

    # --- YAML Frontmatter zusammenbauen ---
    lines: list[str] = ["---"]
    # Pflichtfelder
    lines.append(f'title: "{title}"')
    lines.append(f"slug: {slug}")
    lines.append('type: "produkte"')
    if sku: lines.append(f"sku: {sku}")
    lines.append(f"price_cents: {price_cents}")
    if in_stock in (0,1): lines.append(f"in_stock: {bool(in_stock)}")

    if cats: lines += yaml_list("kategorie", cats)
    if tags: lines += yaml_list("tags", tags)

    if images:
        lines += yaml_list("bilder", images)
        lines += yaml_list("bilder_alt", alts)

    if variants:
        lines += yaml_variants("varianten", variants)

    if mtitle: lines.append(f'meta_title: "{mtitle}"')
    if mdesc:  lines.append(f'meta_description: "{mdesc}"')
    if source: lines.append(f'source: "{source}"')
    if last_updated: lines.append(f'last_updated: "{last_updated}"')

    # sprachspezifische Beschreibungen als Literal-Block
    if desc:
        lines += literal_block("beschreibung_md", desc)

    lines.append("---")
    lines.append("")  # Leerzeile vor Body

    # Pfad zu index.md
    dest_rel = f"{export_path}/{slug}/index.md"
    return "\n".join(lines), dest_rel

def build_frontmatter_faq(rec: dict, lang: str) -> tuple[str, str]:
    get = lambda k: rec.get(FAQ_COLUMNS[k], "")
    title = nstrip(get("title_de") if lang=="de" else get("title_en"))
    slug  = nstrip(get("slug_de") if lang=="de" else get("slug_en"))
    answer= nstrip(get("answer_de") if lang=="de" else get("answer_en"))
    tags  = split_any(nstrip(get("tags")))

    lines = ["---"]
    lines.append(f'title: "{title}"')
    lines.append(f"slug: {slug}")
    lines.append('type: "faq"')
    if tags: lines += yaml_list("tags", tags)
    if answer: lines += literal_block("antwort_md", answer)
    lines.append("---")
    lines.append("")

    dest_rel = ("de/faq" if lang=="de" else "en/faq") + f"/{slug}/index.md"
    return "\n".join(lines), dest_rel

def process_products(rows: list[dict]):
    for rec in rows:
        # Normalize record keys/values
        rec = {k: norm(v) for k,v in rec.items()}

        # DE
        fm_de, dest_de = build_frontmatter_product(rec, "de")
        write_text(CONTENT / dest_de, fm_de)

        # EN (nur wenn slug_en+title_en vorhanden; sonst überspringen)
        if nstrip(rec.get(COLUMNS["slug_en"], "")) and nstrip(rec.get(COLUMNS["title_en"], "")):
            fm_en, dest_en = build_frontmatter_product(rec, "en")
            write_text(CONTENT / dest_en, fm_en)

def process_faq(rows: list[dict]):
    for rec in rows:
        rec = {k: norm(v) for k,v in rec.items()}
        if nstrip(rec.get(FAQ_COLUMNS["slug_de"], "")) and nstrip(rec.get(FAQ_COLUMNS["title_de"], "")):
            fm_de, dest_de = build_frontmatter_faq(rec, "de")
            write_text(CONTENT / dest_de, fm_de)
        if nstrip(rec.get(FAQ_COLUMNS["slug_en"], "")) and nstrip(rec.get(FAQ_COLUMNS["title_en"], "")):
            fm_en, dest_en = build_frontmatter_faq(rec, "en")
            write_text(CONTENT / dest_en, fm_en)

def main():
    products_url = os.getenv("PRODUCTS_SHEET_CSV", "")
    faq_url      = os.getenv("FAQ_SHEET_CSV", "")

    if not products_url:
        print("ERROR: PRODUCTS_SHEET_CSV Secret/Env fehlt.", file=sys.stderr)
        sys.exit(2)

    prod_rows = fetch_csv(products_url)
    if not prod_rows:
        print("WARN: Keine Produktzeilen im Sheet gefunden.")
    else:
        process_products(prod_rows)
        print(f"✓ Produkte verarbeitet: {len(prod_rows)}")

    if faq_url:
        faq_rows = fetch_csv(faq_url)
        if faq_rows:
            process_faq(faq_rows)
            print(f"✓ FAQs verarbeitet: {len(faq_rows)}")

    print("SSOT → Markdown: done.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
