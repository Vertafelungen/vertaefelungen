import pandas as pd
import os
import requests

# Sheet-URL: HIER DEINE CSV-URL EINFÜGEN!
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/DEINE_ID/pub?output=csv"

response = requests.get(SHEET_CSV_URL)
response.raise_for_status()

df = pd.read_csv(pd.compat.StringIO(response.text))

# Funktion für das Anlegen der Dateien
def write_md_files(export_col, slug_col):
    for _, row in df.iterrows():
        pfad = str(row[export_col]).strip() if not pd.isna(row[export_col]) else ''
        slug = str(row[slug_col]).strip() if not pd.isna(row[slug_col]) else ''
        if pfad and slug:
            full_dir = pfad.rstrip('/')
            os.makedirs(full_dir, exist_ok=True)
            full_path = f"{full_dir}/{slug}.md"
            # Hier kannst du definieren, was als Inhalt rein soll:
            content = f"# {slug}\n\nAutomatisch erzeugt aus Sheet.\n"
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{full_path} geschrieben.")

# Deutsch & Englisch synchronisieren (bei Bedarf eine oder beide Sprachen)
write_md_files('export_pfad_de', 'slug_de')
write_md_files('export_pfad_en', 'slug_en')
