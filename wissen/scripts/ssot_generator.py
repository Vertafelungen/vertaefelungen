#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SSOT → Markdown Generator (DE + EN)
- Liest 1 CSV-Export-URL (GSHEET_CSV_URL) für beide Sprachen.
- Normalisiert Text (CP-1252, NBSP, Zero-Width), erzwingt UTF-8 ohne BOM.
- Coerced Typen (price_cents:int, in_stock:bool, Listenfelder).
- Schreibt deterministisches YAML (ruamel.yaml) mit sicheren Quotes.
- Pfade: wissen/content/{de|en}/oeffentlich/produkte/<kategorie>/<slug>/index.md
  (kategorie darf Unterordner enthalten, z. B. "leisten/sockelleisten")
"""

import os
import re
import sys
import csv
import json
import math
import argparse
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
import pandas as pd
from slugify import slugify
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ
from unidecode import unidecode

# ---------- Konfiguration -----------------------------------------------------

# Kandidatenspalten pro Zielfeld (beliebig erweiterbar).
# -> Der Generator nimmt die erste nicht-leere Spalte.
CANDS = {
    "slug":              ["slug", "slug_id", "sku", "artikel", "id"],
    "reference":         ["reference", "referenz", "artikelnummer", "sku_ref"],
    "product_id":        ["product_id", "produkt_id", "pid"],
    "category_path":     ["kategorie", "category", "kategorie_path", "category_path", "pfad_kategorie"],
    "content_path":      ["content_path", "pfad", "path"],

    "title_de":          ["titel_de", "title_de", "titel", "title"],
    "title_en":          ["title_en", "titel_en", "en_title"],

    "description_de":    ["beschreibung_de", "beschreibung", "description_de"],
    "description_en":    ["description_en", "en_description"],

    "meta_title_de":     ["meta_title_de", "meta_titel_de", "meta_title", "meta_titel"],
    "meta_title_en":     ["meta_title_en", "en_meta_title"],

    "meta_desc_de":      ["meta_description_de", "meta_beschreibung_de", "meta_description", "meta_beschreibung"],
    "meta_desc_en":      ["meta_description_en", "en_meta_description"],

    "tags_de":           ["tags_de", "schlagworte_de", "tags"],
    "tags_en":           ["tags_en", "en_tags"],

    "images":            ["bilder", "images", "img", "fotos"],
    "images_alt_de":     ["bilder_alt_de", "alt_de"],
    "images_alt_en":     ["bilder_alt_en", "alt_en"],

    "price_cents":       ["price_cents", "preis_cents", "preis_cent"],
    "price_eur":         ["price_eur", "preis_eur", "preis", "price"],
    "in_stock":          ["in_stock", "verfuegbar", "verfügbar", "lagernd", "stock"],

    # Freitext-Body (optional)
    "body_de":           ["body_de", "text_de", "inhalt_de"],
    "body_en":           ["body_en", "text_en", "inhalt_en"],
}

# Bool-Erkennung
TRUE_SET  = {"1", "true", "yes", "ja", "wahr", "y", "x"}
FALSE_SET = {"0", "false", "no", "nein", "falsch", ""}

# Unerwünschte Zeichen (CP-1252 Range & Co.) -> Ersetzungen
SUBS = {
    "\u00a0": " ",   # NBSP
    "\u200b": "",    # ZERO WIDTH SPACE
    "\u200c": "",    # ZWNJ
    "\u200d": "",    # ZWJ
    "\ufeff": "",    # BOM im Text
    "\u2013": "-",   # – en dash
    "\u2014": "-",   # — em dash
    "\u2018": "'",   # ‘
    "\u2019": "'",   # ’
    "\u201c": '"',   # “
    "\u201d": '"',   # ”
    "\u2026": "...", # …
    "\u2212": "-",   # −
}

CP1252_MAP = {
    0x80: "€", 0x82: ",", 0x83: "f", 0x84: '"', 0x85: "...", 0x86: "+",
    0x87: "#", 0x88: "^", 0x89: "%", 0x8A: "S", 0x8B: "<", 0x8C: "OE",
    0x91: "'", 0x92: "'", 0x93: '"', 0x94: '"', 0x95: "-", 0x96: "-",
    0x97: "-", 0x98: "~", 0x99: "(TM)", 0x9A: "s", 0x9B: ">", 0x9C: "oe"
}

# ---------- Utilities ---------------------------------------------------------

def first_value(row: dict, keys: List[str]) -> Optional[str]:
    for k in keys:
        if k in row and pd.notna(row[k]):
            v = str(row[k]).strip()
            if v != "":
                return v
    return None

def normalize_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    # Replace CP-1252 control range explicitly if present
    s = ''.join(CP1252_MAP.get(ord(ch), ch) for ch in s)
    for a, b in SUBS.items():
        s = s.replace(a, b)
    # Normalize unicode (NFC) & trim trailing spaces per line
    s = unicodedata.normalize("NFC", s)
    s = "\n".join(line.rstrip() for line in s.splitlines())
    return s

def coerce_bool(val: Optional[str]) -> Optional[bool]:
    if val is None:
        return None
    v = normalize_text(val).lower()
    if v in TRUE_SET: return True
    if v in FALSE_SET: return False
    return None

def parse_price_cents(row: dict) -> Optional[int]:
    raw_cents = first_value(row, CANDS["price_cents"])
    if raw_cents and raw_cents.isdigit():
        return int(raw_cents)

    raw_eur = first_value(row, CANDS["price_eur"])
    if raw_eur:
        s = normalize_text(raw_eur)
        # z.B. "49,75 €" -> 4975
        s = s.replace("€", "").replace("EUR", "").strip()
        s = s.replace(".", "").replace(" ", "")
        s = s.replace(",", ".")
        try:
            eur = float(s)
            return int(round(eur * 100))
        except Exception:
            return None
    return None

def split_list(val: Optional[str]) -> Optional[List[str]]:
    if not val: return None
    s = normalize_text(val)
    if not s: return None
    parts = re.split(r"[;|,]", s)
    cleaned = [p.strip() for p in parts if p.strip()]
    return cleaned or None

def safe_slug(base: Optional[str]) -> Optional[str]:
    if not base: return None
    return slugify(base, lowercase=True)

def quoted(s: Optional[str]) -> Optional[DQ]:
    if s is None: return None
    return DQ(s)

def yaml_dump(data: dict) -> str:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.indent(sequence=2, offset=2)
    out = []
    from io import StringIO
    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()

def ensure_deterministic_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

def ensure_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

# ---------- Mapping / Extraktion ---------------------------------------------

def extract_for_lang(row: dict, lang: str) -> Dict:
    assert lang in ("de", "en")
    title = first_value(row, CANDS[f"title_{lang}"])
    desc  = first_value(row, CANDS[f"description_{lang}"])
    mtitle = first_value(row, CANDS[f"meta_title_{lang}"])
    mdesc  = first_value(row, CANDS[f"meta_desc_{lang}"])
    tags   = first_value(row, CANDS.get(f"tags_{lang}", []))
    images = first_value(row, CANDS["images"])
    images_alt = first_value(row, CANDS.get(f"images_alt_{lang}", []))
    body   = first_value(row, CANDS.get(f"body_{lang}", []))

    # Fallbacks: wenn sprachspez. leer, probiere generische
    if not title and lang == "de":
        title = first_value(row, ["title", "titel"])
    if not desc and lang == "de":
        desc = first_value(row, ["beschreibung", "description"])

    # Normalize all strings
    title = normalize_text(title)
    desc  = normalize_text(desc)
    mtitle = normalize_text(mtitle)
    mdesc  = normalize_text(mdesc)
    body  = normalize_text(body)

    tags_list = split_list(tags)
    imgs_list = split_list(images)
    alts_list = split_list(images_alt) or []

    # Paarweise alt-Texte an images hängen (wenn gleich viele Einträge)
    images_struct = []
    if imgs_list:
        for i, img in enumerate(imgs_list):
            item = {"src": img}
            if i < len(alts_list):
                item["alt"] = alts_list[i]
            images_struct.append(item)

    return {
        "title": title,
        "description": desc,
        "meta_title": mtitle,
        "meta_description": mdesc,
        "tags": tags_list,
        "images": images_struct,
        "body": body or "",
    }

def compute_paths(row: dict, lang: str, fallback_slug: Optional[str]) -> (str, Path):
    # Kategorie/Content-Pfad
    explicit = first_value(row, CANDS["content_path"])
    category = first_value(row, CANDS["category_path"])

    if explicit:
        explicit = explicit.strip("/ ")
        content_rel = f"wissen/content/{lang}/{explicit}/index.md"
        return explicit, Path(content_rel)

    # Sonst: standardisiertes Muster unter 'oeffentlich/produkte'
    category = category or "allgemein"
    # erlaubte Unterordner beibehalten (je Segment sluggen)
    safe_cat = "/".join(safe_slug(seg) for seg in category.split("/") if seg.strip())
    slug_val = first_value(row, CANDS["slug"]) or fallback_slug or "item"
    slug_val = safe_slug(slug_val)

    rel = f"oeffentlich/produkte/{safe_cat}/{slug_val}"
    content_rel = f"wissen/content/{lang}/{rel}/index.md"
    return rel, Path(content_rel)

# ---------- Hauptlogik --------------------------------------------------------

def generate_from_csv(csv_url: str, langs: List[str]) -> int:
    print(f"[ssot] Lade CSV: {csv_url}")
    r = requests.get(csv_url, timeout=60)
    r.raise_for_status()
    text = ensure_deterministic_newlines(r.text)

    # Pandas mit dtype=str, damit nichts implizit typisiert wird
    df = pd.read_csv(
        pd.compat.StringIO(text),
        dtype=str,
        keep_default_na=False,
        na_values=[],
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
        engine="python"
    )

    total_written = 0
    for idx, row in df.to_dict(orient="records"):
        pass  # dummy to check iterator type (will fix below)

    # Workaround: pandas 2.2.2 -> iterrows liefert (idx, Series)
    total_written = 0
    for _, s in df.iterrows():
        row = {k: (None if (v == "" or pd.isna(v)) else str(v)) for k, v in s.items()}

        # gemeinsame Felder
        fallback_slug = first_value(row, CANDS["slug"]) or first_value(row, CANDS["reference"])
        reference = first_value(row, CANDS["reference"])
        product_id = first_value(row, CANDS["product_id"])
        price_cents = parse_price_cents(row)
        in_stock = coerce_bool(first_value(row, CANDS["in_stock"]))

        for lang in langs:
            data = extract_for_lang(row, lang)

            # Slug bestimmen (Spaltenwert → sonst aus Titel)
            slug_val = first_value(row, CANDS["slug"])
            if not slug_val:
                slug_val = data["title"]
            slug_val = safe_slug(slug_val or "item")

            rel_path, out_path = compute_paths(row, lang, slug_val)

            # YAML-Frontmatter aufbauen (nur sinnvolle Keys schreiben)
            fm = {
                "title":           quoted(data["title"]) if data["title"] else DQ(""),
                "description":     quoted(data["description"]) if data["description"] else DQ(""),
                "slug":            quoted(slug_val),
                "type":            quoted("produkte"),
                "kategorie":       quoted(rel_path.split("oeffentlich/produkte/")[-1].rsplit("/", 1)[0]),  # nur Kategorie ohne slug
            }
            if data["meta_title"]:        fm["meta_title"] = quoted(data["meta_title"])
            if data["meta_description"]:  fm["meta_description"] = quoted(data["meta_description"])
            if product_id:                fm["product_id"] = quoted(product_id)
            if reference:                 fm["reference"] = quoted(reference)
            if price_cents is not None:   fm["price_cents"] = int(price_cents)
            if in_stock is not None:      fm["in_stock"] = bool(in_stock)
            if data["tags"]:              fm["tags"] = [DQ(t) for t in data["tags"]]

            if data["images"]:
                imgs = []
                for it in data["images"]:
                    di = {"src": DQ(it["src"])}
                    if "alt" in it and it["alt"]:
                        di["alt"] = DQ(normalize_text(it["alt"]))
                    imgs.append(di)
                fm["images"] = imgs

            # YAML serialisieren (mit Quotes)
            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.default_flow_style = False
            yaml.indent(sequence=2, offset=2)

            # Write
            ensure_dir(out_path)
            with open(out_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("---\n")
                yaml.dump(fm, f)
                f.write("---\n\n")
                if data["body"]:
                    f.write(ensure_deterministic_newlines(normalize_text(data["body"])))
                    f.write("\n")

            total_written += 1
            print(f"[ssot] wrote {out_path}")

    print(f"[ssot] fertig, {total_written} Dateien geschrieben.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="SSOT CSV → Markdown (DE+EN)")
    ap.add_argument("--csv-url", dest="csv_url", default=os.environ.get("GSHEET_CSV_URL", ""))
    ap.add_argument("--lang", action="append", default=None,
                    help="de / en (kann mehrfach verwendet werden). Standard: de & en")
    args = ap.parse_args()

    if not args.csv_url:
        print("ERROR: GSHEET_CSV_URL fehlt (Secret oder --csv-url).", file=sys.stderr)
        return 2

    langs = args.lang or ["de", "en"]
    return generate_from_csv(args.csv_url, langs)


if __name__ == "__main__":
    sys.exit(main())
