
def format_varianten_md(yaml_text):
    try:
        eintraege = yaml.safe_load(yaml_text)
        if not isinstance(eintraege, list):
            return "_Keine Varianten verfügbar._"
        lines = ["## Varianten", ""]
        for eintrag in eintraege:
            bez = eintrag.get("bezeichnung", "").strip()
            preis = eintrag.get("preis_aufschlag", "").strip()
            if bez or preis:
                lines.append(f"- **{bez}** (Aufschlag: {preis})")
        lines.append("")  # Leerzeile zum Abschluss
        return "\n".join(lines)
    except Exception:
        return "_Varianten konnten nicht geladen werden._"


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


# ===== FIXED METADATA =====
author = "Tobias Klaus"
author_url = "https://www.vertaefelungen.de/de/content/4-uber-uns"
license_info = "CC BY-SA 4.0"

# ===== CONFIG =====
SHEET_CSV_URL = os.getenv(
    "SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRTwKrnuK0ZOjW6BpQatLIFAmYpFD-qykuJFQvI21Ep9G_uCNu_jbwtxIGCeeqMGg5-S1eq823AvR7L/pub?output=csv"
)

# Optional output dir for JSON catalogs (defaults repo root)
OUTPUT_DIR = os.getenv("OUTPUT_DIR", ".").strip()

# Columns in the Google Sheet (keep existing, including Umlaut handling)
COL_EXPORT_DE = "export_pfad_de"
COL_EXPORT_EN = "export_pfad_en"
COL_SLUG_DE   = "slug_de"
COL_SLUG_EN   = "slug_en"

# Neue Felder für source + Aktualisierungsstand
COL_SOURCE_DE = "source_de"
COL_SOURCE_EN = "source_en"
COL_LAST_UPDATED = "last_updated"

# Alttext-Spalten (Q/R)
COL_ALT_DE = "bilder_alt_de"
COL_ALT_EN = "bilder_alt_en"

# ===== FETCH SHEET =====
resp = requests.get(SHEET_CSV_URL, timeout=60)
resp.raise_for_status()
csv_bytes = BytesIO(resp.content)
df = pd.read_csv(csv_bytes, encoding="utf-8")

# ===== HELPERS =====
def yaml_list(val):
    if pd.isna(val) or str(val).strip() == "":
        return []
    return [x.strip() for x in str(val).split(",") if x.strip()]

def bilder_liste(val):
    if pd.isna(val) or not str(val).strip():
        return []
    return [b.strip() for b in str(val).split(",") if b.strip()]

def alt_liste(val):
    """Comma-separated alt texts, keep order; empty cells become ''. """
    if pd.isna(val) or not str(val).strip():
        return []
    return [a.strip() for a in str(val).split(",")]

def yaml_safe(s):
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
    except Exception:
        return ""

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
            price = format_price(val)
            lines.append(f"    preis_aufschlag: {price}")
        elif stripped:
            lines.append('    ' + stripped)
    return "\n".join(lines)

def _short_summary(text, limit=240):
    if text is None or pd.isna(text):
        return ""
    s = " ".join(str(text).split())
    return s[:limit]

def build_content(row, lang="de"):
    # Extract raw fields
    if lang == "de":
        slug = row.get("slug_de", "")
        titel = row.get("titel_de", "")
        beschreibung = row.get("beschreibung_md_de", "")
        meta_title = row.get("meta_title_de", "")
        meta_description = row.get("meta_description_de", "")
        kategorie = row.get("kategorie_raw", "")
        verfuegbar = row.get("verfuegbar", "")
        bilder = bilder_liste(row.get("bilder_liste", ""))
        bilder_alt = alt_liste(row.get(COL_ALT_DE, ""))
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
        bilder_alt = alt_liste(row.get(COL_ALT_EN, ""))
        price = format_price(row.get("price", ""))
        varianten_yaml_raw = row.get("varianten_yaml", "")
        varianten_yaml = format_varianten_yaml(varianten_yaml_raw)
        tags = yaml_list(row.get("tags", ""))
        sortierung = row.get("sortierung", "")
        langcode = row.get("langcode_en", "")

    product_id = row.get("product_id", "")
    reference = row.get("reference", "")

    # PREP
    beschreibung_text = ""
    if pd.notna(beschreibung):
        beschreibung_text = str(beschreibung).replace("\n", " ")
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
    # Alttexte parallel ablegen
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
    yaml_lines.append("---")
    yaml_block = "\n".join(yaml_lines)

    # Markdown body
    body_parts = []
    body_parts.append(f"# {titel}")
    body_parts.append("")
    body_parts.append(str(beschreibung if pd.notna(beschreibung) else ""))
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
    content = yaml_block + "\n\n" + "\n".join(body_parts)

    json_item = {
        "path": "",  # will be set relative to repo root
        "slug": str(slug or "").strip(),
        "category": str(kategorie or "").strip(),
        "title": str(titel or "").strip(),
        "has_yaml": True,
        "summary": _short_summary(beschreibung),
        "images": bilder,
        "images_alt": bilder_alt
    }
    return content, titel, beschreibung, meta_title_text, json_item

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

# Write JSON catalogs
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