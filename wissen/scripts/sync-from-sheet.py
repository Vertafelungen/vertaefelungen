#!/usr/bin/env python3
# sync-from-sheet.py – zieht ein Google-Sheet (CSV) und schreibt Hugo-Content (DE/EN)
# Zielpfade:
#   DE: wissen/content/de/oeffentlich/produkte/<slug>/index.md
#   EN: wissen/content/en/public/products/<slug>/index.md
#
# KONFIG über Umgebungsvariablen (eines von beidem):
#   GSHEET_CSV_URL   -> kompletter CSV-Export-Link
#   ODER
#   SHEET_ID + SHEET_GID  (Google Sheet ID + Tabellenblatt GID)
#
# Minimal erforderliche Spalten im Sheet (Case-insensitive erkannt):
#   slug (alternativ wird aus deutschem Titel generiert)
#   titel_de, titel_en
#   beschreibung_md_de, beschreibung_md_en
# Optional:
#   kategorie / category       (Komma/Strichpunkt-getrennt)
#   bilder / images            (Komma/Strichpunkt-getrennt)
#   varianten_yaml (YAML-Liste) ODER varianten im Format name|preis|einheit|sku; ...
#   sku, preis, einheit        (für Single-Variante, falls varianten leer)
#
# Aufruf lokal (aus Repo-Root):   cd wissen && python scripts/sync-from-sheet.py
# Aufruf in CI (Workflow tut das für dich)

from __future__ import annotations
import os, re, sys, unicodedata
from datetime import datetime, timezone, timedelta
from io import StringIO
from pathlib import Path

import requests
import pandas as pd

# --------------------- Pfade ---------------------
ROOT = Path(__file__).resolve().parents[1]  # .../wissen
OUT_DE = ROOT / "content" / "de" / "oeffentlich" / "produkte"
OUT_EN = ROOT / "content" / "en" / "public" / "products"

# --------------------- Helpers -------------------
def now_iso():
    # Berlin-Zeit ohne externe Abhängigkeiten
    return (datetime.utcnow() + timedelta(hours=2)).replace(microsecond=0, tzinfo=timezone(timedelta(hours=2))).isoformat()

def try_fix(s: str | None) -> str:
    if s is None:
        return ""
    s = str(s)
    if "Ã" in s or "�" in s:
        try:
            return s.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        except Exception:
            return s
    return s

def slugify(s: str) -> str:
    s = try_fix(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s or "item"

def split_list(val: str):
    if not val:
        return []
    parts = re.split(r"[;,]\s*", str(val).replace("\n", ","))
    return [p.strip() for p in parts if p.strip()]

def first_col(df: pd.DataFrame, *cands):
    lm = {c.lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in lm:
            return lm[c.lower()]
    return None

def parse_varianten(row: dict):
    # Variante A: YAML-Liste in 'varianten_yaml' (optional)
    vy = row.get("varianten_yaml") or row.get("VARIANTEN_YAML") or ""
    if vy and str(vy).strip():
        try:
            import yaml  # optional
            v = yaml.safe_load(str(vy))
            if isinstance(v, list):
                return v
        except Exception:
            pass
    # Variante B: kompakt "name|preis|einheit|sku; name|…"
    txt = row.get("varianten") or row.get("VARIANTEN") or ""
    items = []
    for chunk in split_list(txt):
        bits = [b.strip() for b in chunk.split("|")]
        if not bits or not bits[0]:
            continue
        item = {"name": bits[0]}
        if len(bits) > 1 and bits[1]:
            try:
                item["preis"] = float(str(bits[1]).replace(",", "."))
            except ValueError:
                item["preis"] = bits[1]
        if len(bits) > 2 and bits[2]:
            item["einheit"] = bits[2]
        if len(bits) > 3 and bits[3]:
            item["sku"] = bits[3]
        items.append(item)
    return items

def yaml_block(key: str, text: str) -> str:
    lines = [f"{key}: |"]
    for ln in (text or "").splitlines():
        lines.append(f"  {ln}")
    return "\n".join(lines)

def fm_to_str(fm: dict, de_title: str, en_title: str, de_desc: str, en_desc: str) -> str:
    # deterministische Reihenfolge
    order = [
        "title", "title_en",
        "slug", "type", "kategorie",
        "beschreibung_md_de", "beschreibung_md_en",
        "bilder", "varianten", "sku", "last_sync",
    ]
    # zusammenführen
    data = dict(fm)
    data["title"] = de_title
    data["title_en"] = en_title
    data["beschreibung_md_de"] = de_desc or ""
    data["beschreibung_md_en"] = en_desc or ""

    out = ["---"]
    for k in order:
        if k not in data:
            continue
        v = data[k]
        if v in (None, "", []):
            continue
        if k in ("kategorie", "bilder"):
            out.append(f"{k}:")
            for el in (v if isinstance(v, list) else split_list(v)):
                out.append(f"  - {el}")
        elif k == "varianten":
            out.append("varianten:")
            for el in (v if isinstance(v, list) else []):
                out.append("  -")
                for kk, vv in el.items():
                    out.append(f"    {kk}: {vv}")
        elif k in ("beschreibung_md_de", "beschreibung_md_en"):
            out.append(yaml_block(k, str(v)))
        else:
            out.append(f"{k}: {v}")
    out.append("---")
    out.append("")  # Leerzeile hinter Frontmatter
    return "\n".join(out)

def write_product(de: dict, en: dict):
    out_de = OUT_DE / de["slug"] / "index.md"
    out_en = OUT_EN / de["slug"] / "index.md"
    out_de.parent.mkdir(parents=True, exist_ok=True)
    out_en.parent.mkdir(parents=True, exist_ok=True)

    fm = {
        "type": "produkte",
        "slug": de["slug"],
        "kategorie": de.get("kategorie", []),
        "bilder": de.get("bilder", []),
        "varianten": de.get("varianten", []),
        "sku": de.get("sku") or en.get("sku") or "",
        "last_sync": now_iso(),
    }
    fm_txt = fm_to_str(
        fm,
        de_title=de["title"],
        en_title=en["title"],
        de_desc=de.get("beschreibung", ""),
        en_desc=en.get("beschreibung", ""),
    )
    # Body lassen wir leer (Inhalt kommt aus Frontmatter-Feldern)
    new_de = fm_txt
    new_en = fm_txt

    old_de = out_de.read_text(encoding="utf-8") if out_de.exists() else ""
    old_en = out_en.read_text(encoding="utf-8") if out_en.exists() else ""
    if new_de != old_de:
        out_de.write_text(new_de, encoding="utf-8")
    if new_en != old_en:
        out_en.write_text(new_en, encoding="utf-8")

def fetch_csv_text() -> str:
    url = (os.getenv("GSHEET_CSV_URL") or "").strip()
    if not url:
        sheet_id = (os.getenv("SHEET_ID") or os.getenv("GSHEET_ID") or "").strip()
        gid = (os.getenv("SHEET_GID") or os.getenv("GSHEET_GID") or "").strip()
        if not (sheet_id and gid):
            print("FEHLER: Setze GSHEET_CSV_URL ODER SHEET_ID+SHEET_GID.", file=sys.stderr)
            sys.exit(2)
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text

def row_to_lang(row: dict, lang: str) -> dict:
    d = {k: try_fix(v) for k, v in row.items()}
    if lang == "de":
        title = d.get("titel_de") or d.get("title_de") or ""
        beschr = d.get("beschreibung_md_de") or d.get("beschreibung_de") or ""
    else:
        title = d.get("titel_en") or d.get("title_en") or ""
        beschr = d.get("beschreibung_md_en") or d.get("beschreibung_en") or ""

    slug = d.get("slug") or slugify(d.get("titel_de") or d.get("title_de") or title or "produkt")
    kat = split_list(d.get("kategorie") or d.get("category"))
    bilder = split_list(d.get("bilder") or d.get("images"))
    varianten = parse_varianten(d)
    sku = d.get("sku") or ""

    # Single-Variante aus preis/einheit/sku, wenn keine Liste vorhanden
    if not varianten:
        preis = d.get("preis") or ""
        einheit = d.get("einheit") or ""
        if preis or einheit or sku:
            item = {"name": "Standard"}
            if preis:
                try:
                    item["preis"] = float(str(preis).replace(",", "."))
                except ValueError:
                    item["preis"] = preis
            if einheit:
                item["einheit"] = einheit
            if sku:
                item["sku"] = sku
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
    csv_text = fetch_csv_text()
    df = pd.read_csv(StringIO(csv_text))
    df = df.fillna("")
    df.columns = [c.strip() for c in df.columns]

    # Optional: nur freigegebene Zeilen
    pub = first_col(df, "publish", "veröffentlichen")
    if pub:
        df = df[df[pub].astype(str).str.lower().isin(["1", "true", "ja", "yes", "y", ""])]

    written = 0
    OUT_DE.mkdir(parents=True, exist_ok=True)
    OUT_EN.mkdir(parents=True, exist_ok=True)

    for _, row in df.iterrows():
        row = {k: row[k] for k in df.columns}
        de = row_to_lang(row, "de")
        en = row_to_lang(row, "en")
        write_product(de, en)
        written += 1

    print(f"✓ {written} Produkte aktualisiert.")
    print(f"DE → {OUT_DE}")
    print(f"EN → {OUT_EN}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        sys.exit(1)
