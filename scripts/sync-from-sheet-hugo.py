#!/usr/bin/env python3
# sync-from-sheet-hugo.py — v2025-09-24 18:30 (Europe/Berlin)

import os, re, unicodedata, requests, pandas as pd
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]

LANG = os.getenv("LANG", "de").lower()          # de | en
CSV_URL = os.getenv("GSHEET_CSV_URL", "").strip()

if not CSV_URL:
    SHEET_ID  = os.getenv("GSHEET_ID", "")
    SHEET_GID = os.getenv("GSHEET_GID", "")
    if SHEET_ID:
        CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"
    else:
        raise SystemExit("Missing GSHEET_CSV_URL (or GSHEET_ID/GID).")

# Spaltennamen (anpassen an dein Sheet)
COL_ID     = "id"
COL_TITLE  = "title"
COL_DESC   = "description"
COL_PATH   = "path"       # z. B. "grundlagen" oder "dokumentation/halbhohe"
COL_TYPE   = "type"       # "wissen"|"knowledge" optional
COL_LANG   = "lang"       # optional

def try_fix_mojibake(text: str) -> str:
    if not isinstance(text, str):
        return ""
    try:
        if any(s in text for s in ("Ã", "�", "¤")):
            fixed = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            return fixed if fixed.count("�") < text.count("�") else text
    except Exception:
        pass
    return text

def slugify(s: str) -> str:
    s = try_fix_mojibake(str(s)).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s or "eintrag"

def fetch_df() -> pd.DataFrame:
    r = requests.get(CSV_URL, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(pd.compat.StringIO(r.text))
    # Falls Großbuchstaben:
    df.columns = [c.strip().lower() for c in df.columns]
    # UTF-8 reparieren
    for c in df.columns:
        df[c] = df[c].map(try_fix_mojibake)
    return df

def out_dir_for_lang() -> Path:
    if LANG == "de":
        return ROOT / "content" / "de" / "wissen"
    return ROOT / "content" / "en" / "knowledge"

def write_md(row: dict):
    title = row.get(COL_TITLE, "").strip() or row.get(COL_ID, "")
    desc  = row.get(COL_DESC, "").strip()
    path  = (row.get(COL_PATH, "") or "").strip().strip("/")
    slug  = slugify(title)
    sect  = out_dir_for_lang()
    target_dir = sect / Path(path)
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{slug}.md"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    fm = {
        "title": title,
        "description": desc,
        "slug": slug,
        "date": now,
        "draft": False
    }

    # YAML Frontmatter schreiben
    lines = ["---"]
    for k, v in fm.items():
        v = str(v).replace("\n", " ").strip()
        lines.append(f"{k}: {v}")
    lines.append("---\n")

    body = row.get("content", "")
    md = "\n".join(lines) + (body or "")

    out.write_text(md, encoding="utf-8")
    return out

def main():
    df = fetch_df()
    # Optional: nach Sprache filtern
    if COL_LANG in df.columns:
        df = df[(df[COL_LANG].str.lower() == LANG) | (df[COL_LANG].isna())]
    written = 0
    for _, r in df.iterrows():
        write_md(r.to_dict())
        written += 1
    print(f"✓ {written} Dateien nach {out_dir_for_lang()} geschrieben.")

if __name__ == "__main__":
    main()
