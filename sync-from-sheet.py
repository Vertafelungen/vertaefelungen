# sync-from-sheet.py
# Version: 2025-09-22 13:46 (Europe/Berlin)

import os, sys, requests, pandas as pd, io
from pathlib import Path

# --- ENV: sowohl GSHEET_* als auch SHEET_* akzeptieren ---
SHEET_ID        = os.getenv("GSHEET_ID")        or os.getenv("SHEET_ID")
SHEET_GID       = os.getenv("GSHEET_GID")       or os.getenv("SHEET_GID")
SHEET_CSV_URL   = os.getenv("GSHEET_CSV_URL")   or os.getenv("SHEET_CSV_URL")
OUTPUT_DIR      = os.getenv("OUTPUT_DIR", "wissen/de")  # z.B. "wissen/de" oder "wissen/en"

# ---- CSV-URL bestimmen ----
if SHEET_CSV_URL:
    csv_url = SHEET_CSV_URL.strip()
else:
    if not SHEET_ID:
        sys.stderr.write("Error: Google Sheet ID not provided. Set GSHEET_ID/SHEET_ID or GSHEET_CSV_URL/SHEET_CSV_URL.\n")
        sys.exit(1)
    csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
    if SHEET_GID:
        csv_url += f"&gid={SHEET_GID}"

# ---- CSV holen ----
try:
    r = requests.get(csv_url, timeout=30)
    r.raise_for_status()
except Exception as e:
    sys.stderr.write(f"Error fetching Google Sheet CSV from {csv_url}: {e}\n")
    sys.exit(1)

csv_data = r.content.decode("utf-8", errors="replace")
df = pd.read_csv(io.StringIO(csv_data), dtype=str, keep_default_na=False)

# Sprache aus OUTPUT_DIR ableiten (z. B. "de" / "en").
lang = OUTPUT_DIR.rstrip("/").split("/")[-1].lower()

# Falls ein gemeinsames Sheet beide Sprachen enthält, nach Sprache filtern
if "Language" in df.columns:
    df = df[df["Language"].str.lower() == lang]

# Erwartete Spalten (ggf. anpassen)
ID_COL      = next((c for c in df.columns if c.lower() == "id"), "ID")
TITLE_COL   = next((c for c in df.columns if c.lower() == "title"), "Title")
CONTENT_COL = next((c for c in df.columns if c.lower() == "content"), "Content")
PATH_COL    = next((c for c in df.columns if c.lower() == "path"), "Path")
TYPE_COL    = next((c for c in df.columns if c.lower() == "type"), "Type")  # "page" | "category"

out_root = Path(OUTPUT_DIR)
out_root.mkdir(parents=True, exist_ok=True)

entries = []

for _, row in df.iterrows():
    slug    = str(row.get(ID_COL, "")).strip()
    title   = str(row.get(TITLE_COL, "")).strip()
    content = str(row.get(CONTENT_COL, "")).strip()
    relpath = str(row.get(PATH_COL, "")).strip()
    etype   = (str(row.get(TYPE_COL, "page")).strip() or "page").lower()

    if not slug:
        continue

    parent_dir = out_root / relpath if relpath else out_root
    parent_dir.mkdir(parents=True, exist_ok=True)

    if etype == "category":
        (parent_dir / slug).mkdir(parents=True, exist_ok=True)
        entries.append({"type": "category", "slug": slug, "title": title or slug, "content": content, "path": relpath})
    else:
        md_path = parent_dir / f"{slug}.md"

        yaml = ["---", f'id: "{slug}"']
        if title:
            safe_title = title.replace('"', '\\"')
            yaml.append(f'title: "{safe_title}"')
        yaml.append("---")

        body_lines = []
        if title:
            body_lines += [f"# {title}", ""]
        if content:
            # Inhalt sollte UTF-8 sein; ggf. in Google Sheet bereinigen (Umlaute etc.)
            body_lines.append(content.replace("\r\n", "\n").strip())

        md_path.write_text(
            "\n".join(yaml) + "\n" + "\n".join(body_lines).rstrip() + "\n",
            encoding="utf-8"
        )
        entries.append({"type": "page", "slug": slug, "title": title or slug, "content": content, "path": relpath})

# Indexseiten generieren (index.md)
children_map = {}
for e in entries:
    parent_key = e["path"] or ""
    children_map.setdefault(parent_key, []).append(e)

timestamp = "2025-09-22 11:02"

for parent_path, children in children_map.items():
    target_dir = out_root / parent_path if parent_path else out_root
    index_md = target_dir / "index.md"

    if not parent_path:
        # Top-Level Index
        if lang == "de":
            index_title = "Wissensdatenbank – Vertäfelung & Lambris"
            intro = "Diese Sammlung bietet umfangreiches Wissen zu historischen Wandvertäfelungen, Materialien, Oberflächen und Zubehör."
        else:
            index_title = "Knowledge Base – Panelling & Wainscoting"
            intro = "A curated knowledge base about historical wood panelling, materials, finishes and accessories."
    else:
        # Kategorietitel und Intro aus Eintrag holen
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

    cats  = [c for c in children if c["type"] == "category"]
    pages = [p for p in children if p["type"] == "page"]

    for c in sorted(cats, key=lambda x: x["title"].lower()):
        lines.append(f"- [{c['title']}]({c['slug']}/)")
        if c["content"]:
            lines.append("  " + " ".join(c["content"].split()))

    # >>> FIX: hier war das Mischzitat ("title'") und verursachte den SyntaxError
    for p in sorted(pages, key=lambda x: x["title"].lower()):
        lines.append(f"- [{p['title']}]({p['slug']}.html)")
        if p["content"]:
            snip = " ".join(p["content"].split())
            lines.append("  " + (snip[:197] + "..." if len(snip) > 200 else snip))

    lines += ["", f"<!-- Stand: {timestamp} -->"]
    index_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

print(f"✅ Sync completed for {OUTPUT_DIR} at {timestamp}")
