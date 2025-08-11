#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generates Markdown files (DE/EN) from a Google Sheet CSV (SSOT) and produces
produkte.de.json / produkte.en.json with RELATIVE paths (repo-root relative).
Designed to run locally and in GitHub Actions (daily).

Dependencies: pandas, requests
"""

import os
import json
import pandas as pd
import requests
from datetime import datetime
from io import BytesIO

# ===== CONFIG =====
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL", "https://docs.google.com/spreadsheets/d/e/2PACX-1vRTwKrnuK0ZOjW6BpQatLIFAmYpFD-qykuJFQvI21Ep9G_uCNu_jbwtxIGCeeqMGg5-S1eq823AvR7L/pub?output=csv")

# Columns in the Google Sheet (keep existing, including Umlaut handling)
COL_EXPORT_DE = "export_pfad_de"
COL_EXPORT_EN = "export_pfad_en"
COL_SLUG_DE   = "slug_de"
COL_SLUG_EN   = "slug_en"

# ===== FETCH SHEET =====
resp = requests.get(SHEET_CSV_URL, timeout=60)
resp.raise_for_status()
csv_bytes = BytesIO(resp.content)
df = pd.read_csv(csv_bytes, encoding="utf-8")

# ===== HELPERS (unchanged behaviour) =====
def yaml_list(val):
    import pandas as pd
    if pd.isna(val) or str(val).strip() == "":
        return []
    return [x.strip() for x in str(val).split(",") if x.strip()]

def bilder_liste(val):
    import pandas as pd
    if pd.isna(val) or not str(val).strip():
        return []
    return [b.strip() for b in str(val).split(",") if b.strip()]

def yaml_safe(s):
    import pandas as pd
    if s is None or pd.isna(s):
        return '""'
    s = str(s)
    s = s.replace('"', "'")
    return f'"{s}"'

def format_price(val):
    try:
        num = int(val)
        euro = num / 1_000_000
        return f"{euro:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return ""

def format_varianten_yaml(varianten_str):
    import pandas as pd
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
            price = format_price(val)
            lines.append(f"    preis_aufschlag: {price}")
        elif stripped:
            lines.append('    ' + stripped)
    return "\n".join(lines)

def _short_summary(text, limit=240):
    import pandas as pd
    if text is None or pd.isna(text):
        return ""
    s = " ".join(str(text).split())
    return s[:limit]

def build_content(row, lang="de"):
    import pandas as pd
    if lang == "de":
        slug = row.get("slug_de", "")
        titel = row.get("titel_de", "")
        beschreibung = row.get("beschreibung_md_de", "")
        meta_title = row.get("meta_title_de", "")
        meta_description = row.get("meta_description_de", "")
        kategorie = row.get("kategorie_raw", "")
        verfuegbar = row.get("verfuegbar", "")
        bilder = bilder_liste(row.get("bilder_liste", ""))
        price = format_price(row.get("price", ""))
        varianten_yaml_raw = row.get("varianten_yaml", "")
        varianten_yaml = format_varianten_yaml(varianten_yaml_raw)
        tags = yaml_list(row.get("tags", ""))
        sortierung = row.get("sortierung", "")
        langcode = row.get("langcode_de", "")
    else:
        slug = row.get("slug_en", "")
        titel = row.get("titel_en", "")
        beschreibung = row.get("beschreibung_md_en", "")
        meta_title = row.get("meta_title_en", "")
        meta_description = row.get("meta_description_en", "")
        kategorie = row.get("kategorie_raw", "")
        verfuegbar = row.get("verfuegbar", "")
        bilder = bilder_liste(row.get("bilder_liste", ""))
        price = format_price(row.get("price", ""))
        varianten_yaml_raw = row.get("varianten_yaml", "")
        varianten_yaml = format_varianten_yaml(varianten_yaml_raw)
        tags = yaml_list(row.get("tags", ""))
        sortierung = row.get("sortierung", "")
        langcode = row.get("langcode_en", "")

    product_id = row.get("product_id", "")
    reference = row.get("reference", "")

    yaml_block = f"""---
slug: {yaml_safe(slug)}
product_id: {yaml_safe(product_id)}
reference: {yaml_safe(reference)}
titel: {yaml_safe(titel)}
kategorie: {yaml_safe(kategorie)}
beschreibung: >
  {beschreibung.replace('\n', ' ') if pd.notna(beschreibung) else ''}
meta_title: {yaml_safe(meta_title)}
meta_description: {yaml_safe(meta_description)}
bilder:
"""
    if bilder:
        for b in bilder:
            yaml_block += f"  - {b}\n"
    else:
        yaml_block += "  -\n"
    yaml_block += f"""price: {yaml_safe(price)}
verfuegbar: {yaml_safe(verfuegbar)}
varianten_yaml: |
{varianten_yaml if varianten_yaml else "  "}
tags: {tags if tags else "[]"}
sortierung: {yaml_safe(sortierung)}
langcode: {yaml_safe(langcode)}
---
"""

    # Markdown body
    content = yaml_block + f"""
# {titel}

{beschreibung}

## Technische Daten

- Referenz: {reference}
- Preis: {price}
- Verfügbar: {verfuegbar}
- Kategorie: {kategorie}
- Sortierung: {sortierung}

## Varianten

{varianten_yaml if varianten_yaml else "_keine Varianten hinterlegt_"}

## Bilder

""" + ("\n".join(f"![]({b})" for b in bilder) if bilder else "_keine Bilder hinterlegt_") + f"""

## SEO-Metadaten

- meta_title: {meta_title}
- meta_description: {meta_description}

## Tags

{', '.join(tags) if tags else "_keine Tags hinterlegt_"}
"""

    json_item = {
        "path": "",  # will be set relative to repo root
        "slug": str(slug or "").strip(),
        "category": str(kategorie or "").strip(),
        "title": str(titel or "").strip(),
        "has_yaml": True,
        "summary": _short_summary(beschreibung),
        "images": bilder
    }
    return content, titel, beschreibung, meta_title, json_item

catalog_de = []
catalog_en = []

def write_md_files(export_col, slug_col, lang):
    for _, row in df.iterrows():
        pfad = str(row.get(export_col, "")).strip() if not pd.isna(row.get(export_col, "")) else ''
        slug = str(row.get(slug_col, "")).strip() if not pd.isna(row.get(slug_col, "")) else ''
        if pfad and slug:
            # ensure relative paths for GH Action; repo root is current working dir
            full_dir = pfad.strip().strip('/').replace("\\", "/")
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

            # relative path for JSON (no leading ./)
            rel = full_path.replace("\\", "/")
            if rel.startswith("./"):
                rel = rel[2:]
            json_item["path"] = rel
            if lang == "de":
                catalog_de.append(json_item)
            else:
                catalog_en.append(json_item)

# Generate .md and collect items
write_md_files(COL_EXPORT_DE, COL_SLUG_DE, lang="de")
write_md_files(COL_EXPORT_EN, COL_SLUG_EN, lang="en")

# Write JSON catalogs at repo root
produkte_de = {"language": "de", "generated": datetime.now().isoformat(), "items": catalog_de}
produkte_en = {"language": "en", "generated": datetime.now().isoformat(), "items": catalog_en}

with open("produkte.de.json", "w", encoding="utf-8") as f:
    json.dump(produkte_de, f, ensure_ascii=False, indent=2)
with open("produkte.en.json", "w", encoding="utf-8") as f:
    json.dump(produkte_en, f, ensure_ascii=False, indent=2)

print("produkte.de.json und produkte.en.json geschrieben.")
