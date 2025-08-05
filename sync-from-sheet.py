with open("umlauttest.md", "w", encoding="utf-8") as f:
    f.write("Test: ä ö ü Ä Ö Ü ß\n")
import pandas as pd
import os
import requests
from io import StringIO

# Sheet-URL hier einfügen!
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRTwKrnuK0ZOjW6BpQatLIFAmYpFD-qykuJFQvI21Ep9G_uCNu_jbwtxIGCeeqMGg5-S1eq823AvR7L/pub?output=csv"

response = requests.get(SHEET_CSV_URL)
response.raise_for_status()
df = pd.read_csv(StringIO(response.text), encoding="utf-8-sig")

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

def build_content(row, lang="de"):
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

    yaml = f"""---
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
            yaml += f"  - {b}\n"
    else:
        yaml += "  -\n"
    yaml += f"""price: {yaml_safe(price)}
verfuegbar: {yaml_safe(verfuegbar)}
varianten_yaml: |
{varianten_yaml if varianten_yaml else "  "}
tags: {tags if tags else "[]"}
sortierung: {yaml_safe(sortierung)}
langcode: {yaml_safe(langcode)}
---
"""

    # --- Markdown-Body ---
    content = yaml + f"""
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
    return content, titel, beschreibung, meta_title

def write_md_files(export_col, slug_col, lang):
    for _, row in df.iterrows():
        pfad = str(row[export_col]).strip() if not pd.isna(row[export_col]) else ''
        slug = str(row[slug_col]).strip() if not pd.isna(row[slug_col]) else ''
        if pfad and slug:
            full_dir = pfad.rstrip('/')
            os.makedirs(full_dir, exist_ok=True)
            full_path = f"{full_dir}/{slug}.md"
            content, titel, beschreibung, meta_title = build_content(row, lang)

            # DEBUG-Ausgaben
            print("-" * 40)
            print(f"File: {full_path}")
            print("Titel:", titel)
            print("Beschreibung (Ausschnitt):", beschreibung[:80])
            print("Meta-Title:", meta_title)
            print("-" * 40)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{full_path} geschrieben.")

write_md_files('export_pfad_de', 'slug_de', lang="de")
write_md_files('export_pfad_en', 'slug_en', lang="en")
