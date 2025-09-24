#!/usr/bin/env python3
# sync-from-sheet-hugo.py — v2025-09-24 19:55 (Europe/Berlin)
# Liest Produktdaten aus Google Sheets (CSV-Export) und erzeugt Hugo-Markdown.
# Schreibt NUR in:
#   DE: content/de/oeffentlich/produkte/
#   EN: content/en/public/products/
# Manuell gepflegte FAQ/Themen bleiben unberührt.

import os, re, unicodedata, requests, pandas as pd
from pathlib import Path
from datetime import datetime
from io import StringIO

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

# Erwartete Spaltennamen (in Kleinbuchstaben). Bei Bedarf anpassen:
COL_ID     = "id"            # z. B. p0003
COL_TITLE  = "title"         # sichtbarer Titel
COL_DESC   = "description"   # Kurzbeschreibung
COL_BODY   = "content"       # Markdown-Inhalt
COL_SLUG   = "slug"          # optional; sonst aus title erzeugt
COL_PATH   = "path"          # optional Unterordner (z. B. "leisten")
COL_LANG   = "lang"          # optional Sprachfilter

def try_fix_mojibake(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if any(s in text for s in ("Ã", "�", "¤")):
        try:
            fixed = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            return fixed if fixed.count("�") < text.count("�") else text
        except Exception:
            return text
    return text

def slugify(s: str) -> str:
    s = try_fix_mojibake(str(s)).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s or "eintrag"

def yq(value: str) -> str:
    """
    YAML-quoting: single-quoted Scalar.
    Einzelne ' werden als '' verdoppelt (YAML-Regel), Zeilenumbrüche entfernt.
    """
    if value is None:
        value = ""
    s = str(value).replace("\r", " ").replace("\n", " ").strip()
    return "'" + s.replace("'", "''") + "'"

def fetch_df() -> pd.DataFrame:
    r = requests.get(CSV_URL, timeout=40)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    df.columns = [c.strip().lower() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].map(try_fix_mojibake)
    # ggf. nach Sprache filtern
    if COL_LANG in df.columns:
        df = df[(df[COL_LANG].str.lower() == LANG) | (df[COL_LANG].isna())]
    return df

def out_dir() -> Path:
    if LANG == "de":
        return ROOT / "content" / "de" / "oeffentlich" / "produkte"
    else:
        return ROOT / "content" / "en" / "public" / "products"

def write_md(row: dict) -> Path:
    title = (row.get(COL_TITLE) or row.get(COL_ID) or "").strip()
    desc  = (row.get(COL_DESC)  or "").strip()
    body  = (row.get(COL_BODY)  or "").rstrip() + "\n"
    slug  = (row.get(COL_SLUG)  or "").strip() or slugify(title)
    sub   = (row.get(COL_PATH)  or "").strip().strip("/")

    target_dir = out_dir() / sub if sub else out_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{slug}.md"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # YAML Frontmatter – robust mit yq()
    fm_lines = [
        "---",
        f"title: {yq(title)}",
        f"description: {yq(desc)}",
        f"slug: {slug}",
        f'date: "{now}"',
        "draft: false",
        "---",
        ""
    ]

    out.write_text("\n".join(fm_lines) + body, encoding="utf-8")
    return out

def main():
    df = fetch_df()
    count = 0
    for _, r in df.iterrows():
        write_md(r.to_dict())
        count += 1
    print(f"✓ {count} Produkt-Seiten geschrieben nach {out_dir()}")

if __name__ == "__main__":
    main()
