import pandas as pd
import os
import requests
from io import StringIO

# Sheet-URL hier einfügen!
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRTwKrnuK0ZOjW6BpQatLIFAmYpFD-qykuJFQvI21Ep9G_uCNu_jbwtxIGCeeqMGg5-S1eq823AvR7L/pub?output=csv"

response = requests.get(SHEET_CSV_URL)
response.raise_for_status()
df = pd.read_csv(StringIO(response.text))

def yaml_list(val):
    if pd.isna(val) or str(val).strip() == "":
        return []
    return [x.strip() for x in str(val).split(",") if x.strip()]

def bilder_liste(val):
    if pd.isna(val) or not str(val).strip():
        return []
    return [b.strip() for b in str(val).split(",") if b.strip()]

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
    except:
        return ""

def format_varianten_yaml(varianten_str):
    if not varianten_str or pd.isna(varianten_str):
        return ""
    lines = []
    last_line_was_dash = False
    for line in str(varianten_str).split("\n"):
        stripped = line.strip()
        if stripped.startswith('- '):
            lines.append('  ' + stripped)
            last_line_was_dash = True
        elif "preis_aufschlag:" in line:
            key, val = line.split(":", 1)
            val = val.strip()
            price = format_price(val)
            lines.append(f"    preis_aufschlag: {price}")
            last_line_was_dash = False
        elif stripped:
            # Weitere Felder auf zweiter Ebene korrekt einrücken
            lines.append('    ' + stripped)
            last_line_was_dash = False
    return "\n".join(lines)

def build_content(row, lang="de"):
    prefix = "" if lang == "de" else "_en"

    def safeval(key):
        v = row.get(key, "")
        return "" if pd.isna(v) else str(v).strip()

    slug = safeval(f"slug{prefix}")
    product_id = safeval("product_id")
    reference = safeval("reference")
    titel = safeval(f"titel{prefix}")
    beschreibung = safeval(f"beschreibung_md{prefix}")
    meta_title = safeval(f"meta_title{prefix}") or safeval(f"meta_titel{prefix}")
    meta_description = safeval(f"meta_description{prefix}")
    price = format_price(row.get("price", ""))
    preis_aufschlag = format_price(row.get("preis_aufschlag", ""))
    verfuegbar = safeval("verfuegbar")
    kategorie = safeval("kategorie_raw")
    bilder = bilder_liste(row.get("bilder_liste", ""))
    varianten_yaml_raw = safeval("varianten_yaml")
    varianten_yaml = format_varianten_yaml(varianten_yaml_raw)
    tags = yaml_list(row.get("tags", ""))
    sortierung = safeval("sortierung")
    langcode = safeval(f"langcode{prefix}")

    yaml = f"""---
slug: {yaml_safe(slug)}
product_id: {yaml_safe(product_id)}
reference: {yaml_safe(reference)}
titel: {yaml_safe(titel)}
kategorie: {yaml_safe(kategorie)}
beschreibung: >
  {beschreibung.replace('\n', ' ') if beschreibung else ''}
meta_title: {yaml_safe(meta_title)}
meta_description: {yaml_safe(meta_description)}
bilder:
"""
    if bilder:
        for b in bilder:
            yaml += f"  - {b}\n"
    else:
        yaml += "  -\n"
    yaml += f"""price: {yaml_safe(price)}
preis_aufschlag: {yaml_safe(preis_aufschlag)}
verfuegbar: {yaml_safe(verfuegbar)}
varianten_yaml: |
{varianten_yaml if varianten_yaml else "  "}
tags: {tags if tags else "[]"}
sortierung: {yaml_safe(sortierung)}
langcode: {yaml_safe(langcode)}
---
"""

    content = yaml + f"""
# {titel}

{beschreibung}

## Technische Daten

- Referenz: {reference}
- Preis: {price}
- Aufschlag: {preis_aufschlag}
- Verfügbar: {verfuegbar}
- Kategorie: {kategorie}
- Sortierung: {sortierung}

## Varianten

{varianten_yaml if varianten_yaml else "_keine Varianten hinterlegt_"}

## Bilder

""" + ("\n".join(f"![]({b})" for b in bilder) if bilder else "_keine Bilder hinterlegt_") + """

## SEO-Metadaten

- meta_title: {meta_title}
- meta_description: {meta_description}

## Tags

{', '.join(tags) if tags else "_keine Tags hinterlegt_"}
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

write_md_files('export_pfad_de', 'slug_de', lang="de")
write_md_files('export_pfad_en', 'slug_en', lang="en")
