# scripts/sync-from-sheet-hugo.py
# Version: 2025-09-23 15:10 (Europe/Berlin)

import os, io, re, unicodedata, requests, pandas as pd
from pathlib import Path
from datetime import datetime

LANG        = os.getenv("LANG", "de").lower()          # de | en
CONTENT_DIR = Path(os.getenv("CONTENT_DIR", f"wissen/content/{LANG}"))
CSV_URL     = os.getenv("GSHEET_CSV_URL")              # z.B. https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>
if not CSV_URL:
    SHEET_ID = os.getenv("GSHEET_ID")
    SHEET_GID = os.getenv("GSHEET_GID")
    if not SHEET_ID:
        raise SystemExit("Missing GSHEET_CSV_URL or GSHEET_ID(+GID).")
    CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
    if SHEET_GID:
        CSV_URL += f"&gid={SHEET_GID}"

# erwartete Spalten
COL_ID      = "ID"         # slug/id, z.B. p0001
COL_TITLE   = "Title"      # sichtbarer Titel
COL_CONTENT = "Content"    # Markdown
COL_PATH    = "Path"       # z.B. "grundlagen" oder "dokumentation/halbhohe"
COL_TYPE    = "Type"       # "category" | "page"
COL_LANG    = "Language"   # de|en (optional)

def try_fix_mojibake(text: str) -> str:
    if text is None:
        return ""
    if any(s in text for s in ("Ã", "â", "Â")):
        try:
            fixed = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            if fixed.count("Ã") < text.count("Ã"):
                return fixed
        except Exception:
            pass
    return text

def slugify(s: str) -> str:
    s = try_fix_mojibake(str(s)).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9/_-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s

def fm(title: str, desc: str = "") -> str:
    t = (title or "").replace('"', '\\"')
    d = (desc or "").replace('"', '\\"')
    return f'---\ntitle: "{t}"\ndescription: "{d}"\ndraft: false\n---\n'

def fetch_df() -> pd.DataFrame:
    r = requests.get(CSV_URL, timeout=30)
    r.raise_for_status()
    data = r.content.decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(data), dtype=str, keep_default_na=False)
    if COL_LANG in df.columns:
        df = df[df[COL_LANG].str.lower() == LANG]
    return df

def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def main():
    df = fetch_df()
    # → Gruppen nach Pfad/Sektion
    groups = {}
    for _, row in df.iterrows():
        etype   = (row.get(COL_TYPE) or "page").strip().lower()
        title   = try_fix_mojibake(row.get(COL_TITLE, "")).strip()
        content = try_fix_mojibake(row.get(COL_CONTENT, "")).replace("\r\n","\n").strip()
        path    = slugify(row.get(COL_PATH, ""))
        sid     = slugify(row.get(COL_ID, ""))
        if not sid:
            continue
        g = groups.setdefault(path, {"cat": None, "pages": []})
        if etype == "category":
            g["cat"] = {"id": (path.split("/")[-1] or "index"), "title": title or path, "content": content}
        else:
            g["pages"].append({"id": sid, "title": title or sid, "content": content})

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Top-Level _index.md (Home der Sprache)
    top_fm = fm(
        "Wissensdatenbank – Vertäfelung & Lambris" if LANG=="de" else "Knowledge Base – Panelling & Wainscoting",
        "Kuratierte Inhalte zu Vertäfelungen, Materialien, Oberflächen." if LANG=="de"
        else "Curated knowledge about panelling, materials, finishes."
    )
    write(CONTENT_DIR / "_index.md", top_fm + f"\n<!-- Stand: {now} -->\n")

    for path, bucket in groups.items():
        base = CONTENT_DIR / path if path else CONTENT_DIR
        # Kategorie-Index
        if path:
            title = bucket["cat"]["title"] if bucket["cat"] else path
            desc  = bucket["cat"]["content"] if bucket["cat"] else ""
            body  = []
            if bucket["pages"]:
                body.append("## Inhalte\n")
                for p in sorted(bucket["pages"], key=lambda x: x["title"].lower()):
                    body.append(f"- [{p['title']}]({p['id']}/)")
            write(base / "_index.md", fm(title, "") + "\n".join(body) + f"\n\n<!-- Stand: {now} -->\n")

        # Seiten (Leaf Bundles)
        for p in bucket["pages"]:
            leaf = base / p["id"] / "index.md"
            write(leaf, fm(p["title"]) + "\n" + (p["content"] or "") + f"\n\n<!-- Stand: {now} -->\n")

    print(f"✅ Sync done for {LANG} → {CONTENT_DIR}")

if __name__ == "__main__":
    main()
