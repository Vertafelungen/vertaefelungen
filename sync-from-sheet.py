import pandas as pd
import os
import requests
from io import StringIO

# Sheet-URL: HIER DEINE CSV-URL EINFÜGEN!
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRTwKrnuK0ZOjW6BpQatLIFAmYpFD-qykuJFQvI21Ep9G_uCNu_jbwtxIGCeeqMGg5-S1eq823AvR7L/pub?output=csv"

response = requests.get(SHEET_CSV_URL)
response.raise_for_status()

df = pd.read_csv(StringIO(response.text))

def yaml_list(val):
    """Hilfsfunktion: Kommagetrennte Strings als YAML-Liste ausgeben"""
    if pd.isna(val) or str(val).strip() == "":
        return "[]"
    items = [x.strip() for x in str(val).split(",") if x.strip()]
    return "[" + ", ".join(f'"{item}"' for item in items) + "]"

def bilder_liste(val):
    if pd.isna(val) or not str(val).strip():
        return []
    # Kommagetrennte Liste
    return [b.strip() for b in str(val).split(",") if b.strip()]

def build_content(row, lang="de"):
    # Felder für YAML je nach Sprache
    prefix = "" if lang == "de" else "_en"
    # Felder aus Zeile holen
    slug = row.get(f"slug{prefix}", "")
    product_id = row.get("product_id", "")
    reference = row.get("reference", "")
    titel = row.get(f"titel{prefix}", "")
    beschreibung = row.get(f"beschreibung_md{prefix}", "")
    meta_title = row.get(f"meta_title{prefix}", "")
    meta_description = row.get(f"meta_description{prefix}", "")
    price = row.get("price", "")
    verfuegbar = row.get("verfuegbar", "")
    kategorie = row.get("kategorie_raw", "")
    bilder = bilder_liste(row.get("bilder_liste", ""))
    varianten_yaml = row.get("varianten_yaml", "")
    tags = yaml_list(row.get("tags", ""))
    sortierung = row.get("sortierung", "")
    langcode = row.get(f"langcode{prefix}", "")
    
    # YAML Frontmatter
    yaml = f"""---
slug: {slug}
product_id: {product_id}
reference: {reference}
titel: "{titel}"
kategorie: {kategorie}
beschreibung: >
  {beschreibung.replace('\n', ' ')}
meta_title: "{meta_title}"
meta_description: "{meta_description}"
bilder:
"""
    for b in bilder:
        yaml += f"  - {b}\n"
    yaml += f"""price: {price}
verfuegbar: {verfuegbar}
varianten_yaml: | 
{varianten_yaml if pd.notna(varianten_yaml) else ""}
tags: {tags}
sortierung: {sortierung}
langcode: {langcode}
---
"""

    # Markdown Body
    content = yaml + f"""
# {titel}

{beschreibung}

## Technische Daten

- Referenz: {reference}
- Preis: {price} €
- Verfügbar: {verfuegbar}
- Kategorie: {kategorie}
- Sortierung: {sortierung}

## Varianten

{varianten_yaml if pd.notna(varianten_yaml) else "_keine Varianten hinterlegt_"}

## Bilder

""" + "\n".join(f"![]({b})" for b in bilder) + """

## SEO-Metadaten

- meta_title: {meta_title}
- meta_description: {meta_description}

## Tags

{tags}
"""
    return content

def write_md_files(export_col, slug_col, lang):
    for _, row in df.iterrows():
        pfad = str(row[export_col]).strip() if not pd.isna(row[export_col]) else ''
        slug = str(row[slug_col]).strip() if not pd.isna(row[slug_col]) else ''
        if pfad and slug:
            full_dir = pfad.rstrip('/')
            os.makedirs(full_dir, exist_ok=True)
            full_path = f"{full_dir}/{slug}.md"
            content = build_content(row, lang)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{full_path} geschrieben.")

# Deutsch & Englisch synchronisieren
write_md_files('export_pfad_de', 'slug_de', lang="de")
write_md_files('export_pfad_en', 'slug_en', lang="en")
