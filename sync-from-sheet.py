# sync-from-sheet.py
# Version: 2025-09-21 18:56 (Europe/Berlin)
#
# Änderungen ggü. deiner laufenden Version:
# - NEU: README-Link-Normalisierung am Ende:
#     * .../allgemein.md   → .../index.html
#     * p0001.md           → p0001.html
#     * generisch: *.md    → *.html
# - Rest (CSV-Download, Pandas-Parse, Markdown/JSON-Schreiben) unverändert belassen.

import os, sys, csv, json, requests, pandas as pd, io, re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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
# pandas.compat.StringIO → io.StringIO
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

    # --- YAML-Frontmatter vorbereiten ---
    yaml_lines = ["---", f'id: "{id_val}"']
    if title_val:
        # erst escapen, dann im f-String verwenden (keine Backslashes im Ausdruck)
        safe_title = title_val.replace('"', '\\"')
        yaml_lines.append(f'title: "{safe_title}"')
    yaml_lines.append("---")

    # --- Markdown-Inhalt ---
    md_lines = []
    if title_val:
        md_lines += [f"# {title_val}", ""]
    if content_val:
        md_lines.append(content_val.replace("\r\n", "\n").strip())

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(yaml_lines) + "\n")
        f.write("\n".join(md_lines).rstrip() + "\n")

    # kurzer Auszug für Index
    snippet = (content_val or title_val).replace("\r\n", "\n").replace("\n", " ")
    snippet = snippet[:197] + "..." if len(snippet) > 200 else snippet
    entries.append({"id": id_val, "title": title_val or id_val, "excerpt": snippet})

json_path = os.path.join(OUTPUT_DIR, "search_index.json")
with open(json_path, "w", encoding="utf-8") as jf:
    json.dump(entries, jf, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# README-Link-Normalisierung (NEU)
#   - Korrigiert NUR Link-Ziele in README.md unterhalb von OUTPUT_DIR
#   - Externe Links (http/https/mailto/data/#) bleiben unangetastet
# ---------------------------------------------------------------------------

MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

def _is_external(href: str) -> bool:
    href = (href or "").strip().lower()
    return href.startswith(("http://", "https://", "mailto:", "data:", "#"))

def _normalize_href(href: str) -> str:
    if _is_external(href):
        return href

    # Query/Fragment erhalten
    parts = urlsplit(href)
    path  = parts.path or ""

    # 1) 'allgemein.md' / 'allgemein.html' → 'index.html'
    if path.endswith(("allgemein.md", "allgemein.html")):
        # ersetze letzten Pfadteil durch index.html
        parent = str(Path(path).parent)
        path = (parent + "/" if parent and not parent.endswith("/") else parent) + "index.html"

    # 2) generisch: *.md → *.html
    elif path.lower().endswith(".md"):
        path = str(Path(path).with_suffix(".html"))

    # wieder zusammensetzen
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

def _rewrite_readme_links(readme_path: Path) -> bool:
    txt = readme_path.read_text(encoding="utf-8", errors="replace")

    def _repl(m):
        label, href = m.group(1), m.group(2)
        return f"[{label}]({_normalize_href(href)})"

    new_txt = MD_LINK_RE.sub(_repl, txt)
    if new_txt != txt:
        readme_path.write_text(new_txt, encoding="utf-8")
        return True
    return False

fixed_count = 0
for readme in Path(OUTPUT_DIR).rglob("README.md"):
    if _rewrite_readme_links(readme):
        fixed_count += 1

print(f"README-Link-Normalisierung: {fixed_count} Datei(en) angepasst unter {OUTPUT_DIR}")

print(f"Sync completed: {len(entries)} entries written to {OUTPUT_DIR}/")
