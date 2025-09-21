# sync-from-sheet.py
# Version: 2025-09-21 21:07 (Europe/Berlin)

import os, sys, requests, pandas as pd, io
from datetime import datetime

# Konfiguration aus Umgebungsvariablen
SHEET_ID = os.getenv("GSHEET_ID")           # Google Sheet ID
SHEET_GID = os.getenv("GSHEET_GID")         # Tab ID (für separates Sprach-Tab)
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "wissen/de")  # Zielverzeichnis (sprachspezifisch)

if not SHEET_ID:
    sys.stderr.write("Error: Google Sheet ID not provided.\n")
    sys.exit(1)

# CSV-Export-URL der Google-Tabelle zusammenbauen:contentReference[oaicite:3]{index=3}
csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
if SHEET_GID:
    csv_url += f"&gid={SHEET_GID}"

try:
    response = requests.get(csv_url, timeout=30)
    response.raise_for_status()
except Exception as e:
    sys.stderr.write(f"Error fetching Google Sheet CSV: {e}\n")
    sys.exit(1)

csv_data = response.content.decode('utf-8', errors='ignore')
df = pd.read_csv(io.StringIO(csv_data), dtype=str, keep_default_na=False)

# Optional: Nach Sprache filtern, falls ein Sheet beide Sprachen enthält
lang_code = OUTPUT_DIR.rstrip('/').split('/')[-1]  # z.B. "de" oder "en"
if 'Language' in df.columns:
    df = df[df['Language'].str.lower() == lang_code]

# Spaltennamen entsprechend der Tabelle
ID_COL = 'ID'        # eindeutiger Slug/Dateiname
TITLE_COL = 'Title'  # Titel der Seite/Kategorie
CONTENT_COL = 'Content'  # Seiteninhalt oder Kurzbeschreibung
PATH_COL = 'Path'    # Pfad (Kategorie-Hierarchie)
TYPE_COL = 'Type'    # "page" oder "category"

entries = []  # Zwischenspeicher aller Einträge für Index-Generierung

for _, row in df.iterrows():
    slug = str(row.get(ID_COL, "")).strip()        # z.B. "allgemein" oder "p0001"
    title = str(row.get(TITLE_COL, "")).strip()
    content = str(row.get(CONTENT_COL, "")).strip()
    path = str(row.get(PATH_COL, "")).strip()      # z.B. "" oder "produkte/halbhohe-vertaefelungen"
    entry_type = str(row.get(TYPE_COL, "page")).strip().lower() or "page"

    if not slug:
        continue  # überspringen, falls kein gültiger Slug vorhanden

    # Zielverzeichnis für diesen Eintrag bestimmen
    parent_dir = os.path.join(OUTPUT_DIR, path) if path else OUTPUT_DIR
    os.makedirs(parent_dir, exist_ok=True)

    if entry_type == "category":
        # Kategorie: nur Verzeichnis anlegen, Index-Seite später generieren
        os.makedirs(os.path.join(parent_dir, slug), exist_ok=True)
        # Kategorie-Eintrag zwischenspeichern (Inhalt als Beschreibung für Index)
        entries.append({
            "slug": slug,
            "title": title or slug,
            "content": content,
            "path": path,         # parent category path
            "type": "category"
        })
    else:
        # Seite: Markdown-Datei erzeugen
        file_path = os.path.join(parent_dir, f"{slug}.md")
        yaml_header = ["---", f'id: "{slug}"']
        if title:
            safe_title = title.replace('"', '\\"')
            yaml_header.append(f'title: "{safe_title}"')
        yaml_header.append("---")
        md_lines = []
        if title:
            md_lines.append(f"# {title}")        # Titel als Überschrift im Inhalt
            md_lines.append("")                 # Leerzeile nach Überschrift
        if content:
            # Inhalt (Zeilenumbrüche normalisieren)
            md_lines.append(content.replace("\r\n", "\n").strip())
        # Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(yaml_header) + "\n")
            f.write("\n".join(md_lines).rstrip() + "\n")
        # Eintrag für Indexe sammeln
        entries.append({
            "slug": slug,
            "title": title or slug,
            "content": content,
            "path": path,
            "type": "page"
        })

# Index-Seiten für alle Verzeichnisse erstellen
# children_map ordnet jedem Pfad (Elternverzeichnis) die direkten Kinder-Einträge zu
children_map = {}
for entry in entries:
    parent_key = entry["path"].strip()
    if parent_key not in children_map:
        children_map[parent_key] = []
    children_map[parent_key].append(entry)

# Durch alle Verzeichnisse iterieren und index.md erstellen
timestamp = "2025-09-21 20:41"  # aktueller Zeitstempel
for parent_path, children in children_map.items():
    # Zielverzeichnis (parent_path kann "" für Root sein)
    target_dir = os.path.join(OUTPUT_DIR, parent_path) if parent_path else OUTPUT_DIR
    index_md_path = os.path.join(target_dir, "index.md")
    # Titel und ggf. Einleitung bestimmen
    if parent_path == "": 
        # Hauptindex (Wurzel der Wissensdatenbank)
        index_title = "Wissensdatenbank – Vert\u00e4felung & Lambris"
        intro_text = "Diese Sammlung bietet umfangreiches Wissen zu historischen Wandvertäfelungen, Materialien, Oberflächen und Zubehör."
    else:
        # Index einer Unterkategorie (Wir suchen den Kategorie-Eintrag für parent_path)
        # Der Kategorie-Eintrag hat slug = letzter Ordnername, path = dessen parent
        cat_slug = parent_path.split("/")[-1]
        # Finde passenden Eintrag
        cat_entry = next((e for e in entries if e["type"] == "category" 
                           and e["slug"] == cat_slug 
                           and e["path"] == "/".join(parent_path.split("/")[:-1])), None)
        index_title = cat_entry["title"] if cat_entry else parent_path
        intro_text = cat_entry["content"] if cat_entry and cat_entry["content"] else ""
    # Index-Inhalt aufbauen
    index_lines = [f"# {index_title}", ""]
    if intro_text:
        index_lines.append(intro_text.strip())
        index_lines.append("")  # Leerzeile nach Einleitung
    # Kinder sortiert hinzufügen (Kategorien zuerst, dann Seiten – optional)
    for child in children:
        if child["type"] == "category":
            # Kategorie-Link (Verzeichnis)
            index_lines.append(f"- [{child['title']}]({child['slug']}/)")
            if child["content"]:
                # Beschreibung der Unterkategorie in nächster Zeile (eingerückt)
                desc = child["content"].replace("\r\n", " ").replace("\n", " ").strip()
                index_lines.append(f"  {desc}")
        else:
            # Seiten-Link (direkte Markdown-Seite)
            index_lines.append(f"- [{child['title']}]({child['slug']}.html)")
            if child["content"]:
                # Kurzer Auszug aus Content in nächster Zeile
                snippet = child["content"].replace("\r\n", " ").replace("\n", " ").strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                index_lines.append(f"  {snippet}")
    # Zeitstempel als Kommentar anhängen
    index_lines.append("")
    index_lines.append(f"<!-- Stand: {timestamp} -->")
    # Index-Datei schreiben/überschreiben
    with open(index_md_path, "w", encoding="utf-8") as idxf:
        idxf.write("\n".join(index_lines).rstrip() + "\n")

print(f"Sync completed for {OUTPUT_DIR} at {timestamp}")
