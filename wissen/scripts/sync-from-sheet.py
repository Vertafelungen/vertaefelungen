#!/usr/bin/env python3
# sync-from-sheet.py — schreibt Hugo-Content aus Google-Sheet (CSV)
# Version: 2025-10-07 07:20 Europe/Berlin
#
# Ein-/Ausgabe:
# - Liest CSV über GSHEET_CSV_URL ODER über GSHEET_ID + GSHEET_GID
# - Erwartet, in REPO/wissen/scripts/ zu liegen
# - Schreibt deterministisch nach:
#     DE: REPO/wissen/content/de/oeffentlich/produkte/<slug>/index.md
#     EN: REPO/wissen/content/en/public/products/<slug>/index.md
#
# Minimal erforderliche Spalten im Sheet (Case-insensitive erkannt):
#   slug ODER titel_de / title_de (für Fallback-Slug)
#   titel_de | titel_en
#   beschreibung_md_de | beschreibung_de
#   beschreibung_md_en | beschreibung_en
# Optional (wenn vorhanden, werden sie übernommen):
#   kategorie / category (Komma- oder Semikolon-getrennt)
#   bilder / images (Komma- oder Semikolon-getrennt absolute oder /wissen/…-Pfade)
#   varianten_yaml (YAML-Block als String) ODER varianten (name|preis|einheit|sku;…)
#   sku, preis, einheit
#
# Aufruf lokal (aus dem Ordner "wissen"):
#   python scripts/sync-from-sheet.py
#
# Aufruf in CI (siehe Workflow unten):
#   (cd wissen) && python scripts/sync-from-sheet.py
#
# Exitcode 0 = OK, >0 = Fehler

import os
import re
import sys
import json
import unicodedata
from pathlib import Path
from datetime import datetime
from io import StringIO

import requests
import pandas as pd

# --- Pfade --------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]       # …/wissen
OUT_DE = ROOT / "content" / "de" / "oeffentlich" / "produkte"
OUT_EN = ROOT / "content" / "en" / "public" / "products"

# --- Helpers ------------------------------------------------------------------
def now_iso():
    # ISO mit Zeitzone (Berlin) – stabil für Frontmatter
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Europe/Berlin")
    except Exception:
        from datetime import timezone, timedelta
        tz = timezone(timedelta(hours=2))
    return datetime.now(tz).isoformat(timespec="seconds")

def try_fix_mojibake(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    if any(x in s for x in ("Ã", "�", "¤")):
        try:
            fixed = s.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            return fixed if fixed.count("�") < s.count("�") else s
        except Exception:
            return s
    return s

def slugify(s: str) -> str:
    s = try_fix_mojibake(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s or "item"

def col(df: pd.DataFrame, *names):
    # Liefert die erste existierende Spalte (case-insensitive)
    lower_map = {c.lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None

def split_list(val: str):
    if val is None or str(val).strip() == "":
        return []
    s = str(val).replace("\n", ",")
    parts = re.split(r"[;,]\s*", s)
    return [p.strip() for p in parts if p.strip()]

def parse_varianten(row: dict):
    # 1) bevorzugt: YAML-Block in 'varianten_yaml'
    vy = row.get("varianten_yaml") or row.get("Varianten_Yaml") or row.get("VARIANTEN_YAML")
    if vy and str(vy).strip():
        try:
            import yaml  # optional
        except Exception:
            yaml = None
        if yaml:
            try:
                v = yaml.safe_load(str(vy))
                if isinstance(v, list):
                    return v
            except Exception:
                pass
    # 2) Fallback: "varianten" im Format name|preis|einheit|sku; name|…
    vtxt = row.get("varianten") or row.get("Varianten") or row.get("VARIANTEN") or ""
    items = []
    for chunk in split_list(vtxt):
        bits = [b.strip() for b in chunk.split("|")]
        if not bits or bits[0] == "":
            continue
        item = {"name": bits[0]}
        if len(bits) > 1 and bits[1] != "":
            try:
                item["preis"] = float(str(bits[1]).replace(",", "."))
            except ValueError:
                item["preis"] = bits[1]
        if len(bits) > 2 and bits[2] != "":
            item["einheit"] = bits[2]
        if len(bits) > 3 and bits[3] != "":
            item["sku"] = bits[3]
        items.append(item)
    return items

def yaml_escape(s: str) -> str:
    s = "" if s is None else str(s)
    if any(ch in s for ch in [":", "-", "{", "}", "[", "]", "#", "&", "*", "!", "|", ">", "'", "\"", "%", "@"]):
        # Wir nutzen Block-Scalar für längere Texte
        return s
    return s

def build_frontmatter(row_de: dict, row_en: dict):
    # gemeinsame Felder
    fm = {
        "type": "produkte",
        "slug": row_de["slug"],
        "kategorie": row_de.get("kategorie", []),
        "bilder": row_de.get("bilder", []),
        "varianten": row_de.get("varianten", []),
        "sku": row_de.get("sku") or row_en.get("sku"),
        "last_sync": now_iso(),
    }
    return fm

def dump_yaml(fm: dict, de_title: str, en_title: str, de_desc: str, en_desc: str) -> str:
    # deterministische YAML-Ausgabe (Key-Reihenfolge fix)
    lines = ["---"]
    order = [
        "title", "title_en",
        "slug", "type", "kategorie",
        "beschreibung_md_de", "beschreibung_md_en",
        "bilder", "varianten", "sku", "last_sync"
    ]
    # Wir geben title (DE) und title_en aus
    kv = dict(fm)
    kv["title"] = de_title
    kv["title_en"] = en_title
    kv["beschreibung_md_de"] = de_desc
    kv["beschreibung_md_en"] = en_desc

    def write_list(key, arr):
        lines.append(f"{key}:")
        for el in arr:
            if isinstance(el, dict):
                # einrücken
                lines.append(f"  -")
                for k, v in el.items():
                    lines.append(f"    {k}: {v!s}")
            else:
                lines.append(f"  - {el}")

    for k in order:
        if k not in kv:
            continue
        v = kv[k]
        if v is None or v == "" or v == []:
            continue
        if k in ("kategorie", "bilder"):
            arr = v if isinstance(v, list) else split_list(v)
            write_list(k, arr)
        elif k == "varianten":
            arr = v if isinstance(v, list) else []
            write_list(k, arr)
        elif k in ("beschreibung_md_de", "beschreibung_md_en"):
            # Block-Scalar für Markdown
            txt = yaml_escape(str(v))
            lines.append(f"{k}: |")
            for line in txt.splitlines():
                lines.append(f"  {line}")
        else:
            lines.append(f"{k}: {v!s}")
    lines.append("---")
    return "\n".join(lines) + "\n"

def write_markdown(de: dict, en: dict):
    # Dateien erstellen
    out_de = OUT_DE / de["slug"] / "index.md"
    out_en = OUT_EN / de["slug"] / "index.md"
    out_de.parent.mkdir(parents=True, exist_ok=True)
    out_en.parent.mkdir(parents=True, exist_ok=True)

    fm = build_frontmatter(de, en)
    fm_str = dump_yaml(fm,
                       de_title=de["title"],
                       en_title=en["title"],
                       de_desc=de.get("beschreibung", ""),
                       en_desc=en.get("beschreibung", ""))

    # Body: deutsch → deutsch, englisch → englisch (falls kein Body, bleibt es nur bei Frontmatter)
    body_de = ""
    body_en = ""

    # Interne .md-Links → Ordner-URLs (…/index.md → …/)
    def fix_links(md: str) -> str:
        return re.sub(r"\((/[^)]+?)\.md\)", r"(\1/)", md)

    body_de = fix_links(body_de)
    body_en = fix_links(body_en)

    content_de = fm_str + body_de
    content_en = fm_str + body_en

    existed_de = out_de.exists()
    existed_en = out_en.exists()
    old_de = out_de.read_text(encoding="utf-8") if existed_de else ""
    old_en = out_en.read_text(encoding="utf-8") if existed_en else ""

    if content_de != old_de:
        out_de.write_text(content_de, encoding="utf-8")
    if content_en != old_en:
        out_en.write_text(content_en, encoding="utf-8")

def fetch_csv_text():
    url = os.getenv("GSHEET_CSV_URL", "").strip()
    if not url:
        sheet_id = os.getenv("GSHEET_ID", "").strip()
        gid = os.getenv("GSHEET_GID", "").strip()
        if not (sheet_id and gid):
            print("Fehlende Variablen: setze GSHEET_CSV_URL ODER GSHEET_ID + GSHEET_GID", file=sys.stderr)
            sys.exit(2)
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.text

def fetch_df() -> pd.DataFrame:
    csv_text = fetch_csv_text()
    df = pd.read_csv(StringIO(csv_text))
    # Spalten-Namen harmonisieren
    df.columns = [c.strip() for c in df.columns]
    return df.fillna("")

def row_to_lang_dict(row: pd.Series, lang: str) -> dict:
    data = {k: try_fix_mojibake(v) for k, v in row.to_dict().items()}

    # Titel
    if lang == "de":
        title = data.get("titel_de") or data.get("title_de") or data.get("Titel_DE") or data.get("Title (DE)") or ""
    else:
        title = data.get("titel_en") or data.get("title_en") or data.get("Titel_EN") or data.get("Title (EN)") or ""

    # Slug (fallback aus deutschem Titel)
    slug = data.get("slug") or data.get("Slug")
    if not slug:
        base = data.get("titel_de") or data.get("title_de") or title or "produkt"
        slug = slugify(base)

    # Beschreibung
    if lang == "de":
        beschr = data.get("beschreibung_md_de") or data.get("beschreibung_de") or data.get("Beschreibung_MD_DE") or ""
    else:
        beschr = data.get("beschreibung_md_en") or data.get("beschreibung_en") or data.get("Beschreibung_MD_EN") or ""

    # Kategorien / Bilder
    kat = split_list(data.get("kategorie") or data.get("category"))
    bilder = split_list(data.get("bilder") or data.get("images"))

    # Varianten
    varianten = parse_varianten(data)

    # Einzelfelder
    sku = data.get("sku") or data.get("SKU") or ""
    preis = data.get("preis") or data.get("Preis") or ""
    einheit = data.get("einheit") or data.get("Einheit") or ""

    # ggf. Single-Variante aus Einzelwerten zusammensetzen (wenn Variants fehlen)
    if not varianten and (preis or sku or einheit):
        item = {}
        if preis != "":
            try:
                item["preis"] = float(str(preis).replace(",", "."))
            except ValueError:
                item["preis"] = preis
        if einheit:
            item["einheit"] = einheit
        if sku:
            item["sku"] = sku
        if item:
            item["name"] = "Standard"
            varianten = [item]

    return {
        "slug": slug,
        "title": title,
        "beschreibung": beschr,
        "kategorie": kat,
        "bilder": bilder,
        "varianten": varianten,
        "sku": sku,
    }

def main():
    print("Lade CSV …")
    df = fetch_df()

    # Optional: nur Zeilen mit 'publish'==true oder leer
    pub_col = col(df, "publish", "veröffentlichen", "publizieren")
    if pub_col:
        df = df[df[pub_col].astype(str).str.lower().isin(["1", "true", "ja", "yes", "y", ""])]

    # Slug-Quelle sicherstellen (damit map de/en klappt)
    slug_c = col(df, "slug", "Slug")
    if not slug_c:
        # wir generieren später aus dem deutschen Titel
        pass

    written = 0
    for _, row in df.iterrows():
        de = row_to_lang_dict(row, "de")
        en = row_to_lang_dict(row, "en")
        write_markdown(de, en)
        written += 1

    print(f"✓ {written} Produkt-Seiten geschrieben nach:")
    print(f"  - {OUT_DE}")
    print(f"  - {OUT_EN}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        sys.exit(1)
