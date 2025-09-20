import os, sys, csv, json, requests, pandas as pd, io

SHEET_ID = os.getenv("GSHEET_ID")
SHEET_GID = os.getenv("GSHEET_GID")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "wissen/de")

if not SHEET_ID:
    sys.stderr.write("Error: Google Sheet ID not provided. Set GSHEET_ID env variable.\n")
    sys.exit(1)

csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
if SHEET_GID:
    csv_url += f"&gid={SHEET_GID}"

try:
    response = requests.get(csv_url, timeout=30)
    response.raise_for_status()
except Exception as e:
    sys.stderr.write(f"Error fetching Google Sheet CSV: {e}\n")
    sys.exit(1)

csv_data = response.content.decode('utf-8', errors='replace')
# ⬇️ pandas.compat.StringIO → io.StringIO
df = pd.read_csv(io.StringIO(csv_data), dtype=str, keep_default_na=False)

os.makedirs(OUTPUT_DIR, exist_ok=True)

entries = []

ID_COL = 'ID'
TITLE_COL = 'Title'
CONTENT_COL = 'Content'

for _, row in df.iterrows():
    id_val = str(row.get(ID_COL, "")).strip()
    title_val = str(row.get(TITLE_COL, "")).strip()
    content_val = str(row.get(CONTENT_COL, "")).strip()
    if not id_val:
        continue

    filename = f"{id_val}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    yaml_lines = ["---", f'id: "{id_val}"']
    if title_val:
        yaml_lines.append(f'title: "{title_val.replace("\"","\\\"")}"')
    yaml_lines.append("---")

    md_lines = []
    if title_val:
        md_lines += [f"# {title_val}", ""]
    if content_val:
        md_lines.append(content_val.replace("\r\n", "\n").strip())

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(yaml_lines) + "\n")
        f.write("\n".join(md_lines).rstrip() + "\n")

    snippet = (content_val or title_val).replace("\r\n", "\n").replace("\n", " ")
    snippet = snippet[:197] + "..." if len(snippet) > 200 else snippet
    entries.append({"id": id_val, "title": title_val or id_val, "excerpt": snippet})

json_path = os.path.join(OUTPUT_DIR, "search_index.json")
with open(json_path, "w", encoding="utf-8") as jf:
    json.dump(entries, jf, ensure_ascii=False, indent=2)

print(f"Sync completed: {len(entries)} entries written to {OUTPUT_DIR}/")
