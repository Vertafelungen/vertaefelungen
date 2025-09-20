import os, sys, csv, json, requests, pandas as pd

# Parameter aus Umgebungsvariablen
SHEET_ID = os.getenv("GSHEET_ID")
SHEET_GID = os.getenv("GSHEET_GID")  # optional: Tabellenblatt-ID
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "wissen")  # Zielverzeichnis für Markdown

if not SHEET_ID:
    sys.stderr.write("Error: Google Sheet ID not provided. Set GSHEET_ID env variable.\n")
    sys.exit(1)

# Konstruiere CSV-Export-URL für das Google Sheet
csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
if SHEET_GID:
    csv_url += f"&gid={SHEET_GID}"

try:
    # CSV-Daten abrufen
    response = requests.get(csv_url, timeout=30)
    response.raise_for_status()
except Exception as e:
    sys.stderr.write(f"Error fetching Google Sheet CSV: {e}\n")
    sys.exit(1)

# Daten mit pandas einlesen (alle Zellen als String, 'NA' nicht als NaN interpretieren)
csv_data = response.content.decode('utf-8')
df = pd.read_csv(pd.compat.StringIO(csv_data), dtype=str, keep_default_na=False)

# Sicherstellen, dass Ausgabeordner existiert
os.makedirs(OUTPUT_DIR, exist_ok=True)

entries = []  # Liste für JSON-Ausgabe

# Erwartete Spaltennamen (ggf. an Sheet anpassen)
ID_COL = 'ID'
TITLE_COL = 'Title'       # oder 'Titel'
CONTENT_COL = 'Content'   # oder 'Inhalt', falls der Sheet-Inhalt in einer Spalte steht

# Durch alle Zeilen iterieren und Markdown-Dateien erstellen
for idx, row in df.iterrows():
    # Werte aus dem DataFrame holen und Whitespaces trimmen
    id_val = str(row.get(ID_COL, "")).strip()
    title_val = str(row.get(TITLE_COL, "")).strip()
    content_val = str(row.get(CONTENT_COL, "")).strip()

    if not id_val:
        continue  # überspringe Zeilen ohne ID

    # Dateiname und -pfad für Markdown-Datei
    filename = f"{id_val}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    # YAML-Frontmatter vorbereiten
    yaml_lines = ["---"]
    yaml_lines.append(f'id: "{id_val}"')
    if title_val:
        # Doppelte Anführungszeichen im Titel escapen
        safe_title = title_val.replace('"', '\\"')
        yaml_lines.append(f'title: "{safe_title}"')
    # Hier können weitere Meta-Daten aus dem Sheet hinzugefügt werden, z.B. Kategorie:
    # if 'Category' in df.columns: yaml_lines.append(f'category: "{row["Category"].strip()}"')
    yaml_lines.append("---")

    # Markdown-Inhalt aufbereiten
    md_lines = []
    if title_val:
        # Füge als Überschrift den Titel hinzu, damit er auf der Seite sichtbar ist
        md_lines.append(f"# {title_val}")
        md_lines.append("")  # Leerzeile nach der Überschrift

    if content_val:
        # Linebreaks normalisieren und führende/leere Zeilen entfernen
        content_val = content_val.replace("\r\n", "\n").strip()
        md_lines.append(content_val)

    # Markdown-Datei schreiben (UTF-8)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(yaml_lines) + "\n")
        f.write("\n".join(md_lines).rstrip() + "\n")

    # Auszug für JSON erstellen (erster Absatz oder gekürzte Version)
    snippet_source = content_val if content_val else title_val
    # Markdown-Formatierungen entfernen für den Auszug
    snippet = snippet_source
    snippet = snippet.replace("\r\n", "\n").replace("\n", " ")
    # Links [Text](URL) auf Text reduzieren
    snippet = csv.re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", snippet) if hasattr(csv, 're') else snippet
    snippet = snippet.replace("**", "").replace("*", "").replace("_", "").replace("`", "")
    snippet = snippet.strip()
    # Auf ca. 200 Zeichen kürzen
    if len(snippet) > 200:
        cutoff = snippet.rfind(" ", 0, 200)
        if cutoff == -1:
            cutoff = 200
        snippet = snippet[:cutoff] + "..."
    # Datensatz für JSON sammeln
    entries.append({
        "id": id_val,
        "title": title_val if title_val else id_val,
        "excerpt": snippet
    })

# JSON-Indexdatei schreiben
json_path = os.path.join(OUTPUT_DIR, "search_index.json")
with open(json_path, "w", encoding="utf-8") as jf:
    json.dump(entries, jf, ensure_ascii=False, indent=2)

print(f"Sync completed: {len(entries)} entries written to {OUTPUT_DIR}/")
