# sync-from-sheet.py
# Version: 2025-09-21 22:06 (Europe/Berlin)

import os, sys, requests, pandas as pd, io
from pathlib import Path

# --- ENV: sowohl GSHEET_* als auch SHEET_* akzeptieren ---
SHEET_ID  = os.getenv("GSHEET_ID")  or os.getenv("SHEET_ID")
SHEET_GID = os.getenv("GSHEET_GID") or os.getenv("SHEET_GID")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "wissen/de")  # z.B. "wissen/de" oder "wissen/en"

if not SHEET_ID:
    sys.stderr.write("Error: Google Sheet ID not provided. Set GSHEET_ID or SHEET_ID.\n")
    sys.exit(1)

# CSV-Export-URL der Google-Tabelle
csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
if SHEET_GID:
    csv_url += f"&gid={SHEET_GID}"

try:
    r = requests.get(csv_url, timeout=30)
    r.raise_for_status()
except Exception as e:
    sys.stderr.write(f"Error fetching Google Sheet CSV: {e}\n")
    sys.exit(1)

csv_data = r.content.decode("utf-8", errors="replace")
df = pd.read_csv(io.StringIO(csv_data), dtype=str, keep_default_na=False)

# Sprache aus OUTPUT_DIR ableiten (z. B. "de" / "en").
lang = OUTPUT_DIR.rstrip("/").split("/")[-1].lower()

# Wenn ein gemeinsames Sheet genutzt wird, kann optional nach Language gefiltert werden.
if "Language" in df.columns:
    df = df[df["Language"].str.lower() == lang]

# Erwartete Spalten (Namen ggf. an dein Sheet anpassen)
ID_COL      = next((c for c in df.columns if c.lower() == "id"), "ID")             # slug/Dateiname
TITLE_COL   = next((c for c in df.columns if c.lower() == "title"), "Title")
CONTENT_COL = next((c for c in df.columns if c.lower() == "content"), "Content")
PATH_COL    = next((c for c in df.columns if c.lower() == "path"), "Path")         # z. B. "oeffentlich/produkte/..."
TYPE_COL    = next((c for c in df.columns if c.lower() == "type"), "Type")         # "page" | "category"

out_root = Path(OUTPUT_DIR)
out_root.mkdir(parents=True, exist_ok=True)

# Alle Einträge einsammeln (für Index-Generierung)
entries = []

for _, row in df.iterrows():
    slug    = str(row.get(ID_COL, "")).strip()
    title   = str(row.get(TITLE_COL, "")).strip()
    content = str(row.get(CONTENT_COL, "")).strip()
    relpath = str(row.get(PATH_COL, "")).strip()    # Elternpfad (kann leer sein)
    etype   = (str(row.get(TYPE_COL, "page")).strip() or "page").lower()

    if not slug:
        continue

    parent_dir = out_root / relpath if relpath else out_root
    parent_dir.mkdir(parents=True, exist_ok=True)

    if etype == "category":
        # Kategorieordner anlegen; eigentliche index.md generieren wir später gesammelt
        (parent_dir / slug).mkdir(parents=True, exist_ok=True)
        entries.append({
            "type": "category",
            "slug": slug,
            "title": title or slug,
            "content": content,
            "path": relpath  # Elternpfad
        })
    else:
        # Inhaltsseite als Markdown
        md_path = parent_dir / f"{slug}.md"
        yaml = ["---", f'id: "{slug}"']
        if title:
            yaml.append(f'title: "{title.replace("\"","\\\"")}"')
        yaml.append("---")

        body_lines = []
        if title:
            body_lines += [f"# {title}", ""]
        if content:
            body_lines.append(content.replace("\r\n", "\n").strip())

        with md_path.open("w", encoding="utf-8") as f:
            f.write("\n".join(yaml) + "\n")
            f.write("\n".join(body_lines).rstrip() + "\n")

        entries.append({
            "type": "page",
            "slug": slug,
            "title": title or slug,
            "content": content,
            "path": relpath
        })

# Indexseiten pro Verzeichnis erstellen (index.md statt README.md)
# children_map ordnet jedem Elternpfad seine direkten Kinder zu
children_map = {}
for e in entries:
    parent_key = e["path"] or ""
    children_map.setdefault(parent_key, []).append(e)

timestamp = "2025-09-21 20:41"

for parent_path, children in children_map.items():
    target_dir = out_root / parent_path if parent_path else out_root
    index_md = target_dir / "index.md"

    # Titel/Einleitung für diese Ebene ermitteln
    if not parent_path:
        # Wurzelebene der Sprache
        if lang == "de":
            index_title = "Wissensdatenbank – Vertäfelung & Lambris"
            intro = "Diese Sammlung bietet umfangreiches Wissen zu historischen Wandvertäfelungen, Materialien, Oberflächen und Zubehör."
        else:
            index_title = "Knowledge Base – Panelling & Wainscoting"
            intro = "A curated knowledge base about historical wood panelling, materials, finishes and accessories."
    else:
        # Den passenden Kategorie-Eintrag zu diesem Ordner suchen:
        # parent_path = "oeffentlich/produkte" → slug wäre letzter Ordnername der KIND-Ebene,
        # aber wir brauchen den Kategorieeintrag, dessen path == parent_path.rsplit("/",1)[0]
        # und dessen slug == letzter Name von parent_path
        cat_slug   = parent_path.split("/")[-1]
        cat_parent = "/".join(parent_path.split("/")[:-1])
        cat_entry = next(
            (e for e in entries if e["type"] == "category" and e["slug"] == cat_slug and (e["path"] or "") == cat_parent),
            None
        )
        index_title = cat_entry["title"] if cat_entry else parent_path
        intro = (cat_entry["content"] or "") if cat_entry else ""

    lines = [f"# {index_title}", ""]
    if intro:
        lines += [intro.strip(), ""]

    # Erst Kategorien, dann Seiten ausgeben (optional: alphabetisch)
    cats  = [c for c in children if c["type"] == "category"]
    pages = [p for p in children if p["type"] == "page"]

    # Kategorien verlinken auf Unterordner (→ index.html)
    for c in sorted(cats, key=lambda x: x["title"].lower()):
        lines.append(f"- [{c['title']}]({c['slug']}/)")
        if c["content"]:
            desc = " ".join(c["content"].split())
            lines.append(f"  {desc}")

    # Seiten verlinken mit .html (keine .md in Links)
    for p in sorted(pages, key=lambda x: x["title"].lower()):
        lines.append(f"- [{p['title']}]({p['slug']}.html)")
        if p["content"]:
            snip = " ".join(p["content"].split())
            if len(snip) > 200:
                snip = snip[:197] + "..."
            lines.append(f"  {snip}")

    lines += ["", f"<!-- Stand: {timestamp} -->"]

    index_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

print(f"✅ Sync completed for {OUTPUT_DIR} at {timestamp}")
