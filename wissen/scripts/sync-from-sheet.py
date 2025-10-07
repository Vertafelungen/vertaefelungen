#!/usr/bin/env python3
# Version: 2025-10-07 14:05 Europe/Berlin
# Sync Google Sheet → Hugo Content (DE/EN) mit Sanitizing + sauberem last_sync in der Frontmatter

from __future__ import annotations
import os, re, sys, unicodedata
from datetime import datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import pandas as pd

ROOT   = Path(__file__).resolve().parents[1]  # .../wissen
OUT_DE = ROOT / "content" / "de" / "oeffentlich" / "produkte"
OUT_EN = ROOT / "content" / "en" / "public" / "products"

DRY_RUN = os.getenv("DRY_RUN", "") not in ("", "0", "false", "False")

CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
BOM = "\ufeff"

def now_iso_berlin() -> str:
    return datetime.now(ZoneInfo("Europe/Berlin")).replace(microsecond=0).isoformat()

def sanitize(s: str | None) -> str:
    if s is None:
        return ""
    s = str(s)
    # Repariere mögliche Fehldekodierungen (Latin1→UTF8 Artefakte vermeiden)
    if "Ã" in s or "�" in s:
        try:
            s = s.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        except Exception:
            pass
    s = s.replace(BOM, "")
    s = CTRL_RE.sub(" ", s)
    s = s.replace("\r\n", "\n")
    return s

def slugify(s: str) -> str:
    s = sanitize(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\-]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s or "item"

def split_list(val: str):
    if not val:
        return []
    parts = re.split(r"[;,]\s*", sanitize(val).replace("\n", ","))
    return [p.strip() for p in parts if p.strip()]

def first_col(df: pd.DataFrame, *cands):
    lm = {c.lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in lm:
            return lm[c.lower()]
    return None

def parse_varianten(row: dict):
    vy = row.get("varianten_yaml") or row.get("VARIANTEN_YAML") or ""
    if vy and str(vy).strip():
        try:
            import yaml  # optional
            v = yaml.safe_load(sanitize(str(vy)))
            if isinstance(v, list):
                # Felder in Varianten ebenfalls sanitisieren
                nn = []
                for it in v:
                    if not isinstance(it, dict):
                        continue
                    nn.append({k: sanitize(vv) for k, vv in it.items()})
                return nn
        except Exception:
            pass
    txt = sanitize(row.get("varianten") or row.get("VARIANTEN") or "")
    items = []
    for chunk in split_list(txt):
        bits = [sanitize(b) for b in chunk.split("|")]
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

def fm_to_str(fm: dict, title: str, beschr_de: str, beschr_en: str, last_sync: str | None = None) -> str:
    # deterministische Reihenfolge
    order = [
        "title", "title_en",
        "slug", "type", "kategorie",
        "beschreibung_md_de", "beschreibung_md_en",
        "bilder", "varianten", "sku", "last_sync",
    ]
    data = dict(fm)
    data["title"] = sanitize(title)
    out = ["---"]
    for k in order:
        if k == "beschreibung_md_de":
            out.append(yaml_block(k, sanitize(beschr_de)))
            continue
        if k == "beschreibung_md_en":
            out.append(yaml_block(k, sanitize(beschr_en)))
            continue
        if k == "last_sync":
            if last_sync:
                out.append(f'last_sync: "{last_sync}"')
            continue
        if k not in data:
            continue
        v = data[k]
        if v in (None, "", []):
            continue
        if k in ("kategorie", "bilder"):
            seq = v if isinstance(v, list) else split_list(v)
            out.append(f"{k}:")
            for el in seq:
                out.append(f"  - {sanitize(el)}")
        elif k == "varianten":
            out.append("varianten:")
            for el in (v if isinstance(v, list) else []):
                out.append("  -")
                for kk, vv in el.items():
                    out.append(f"    {kk}: {sanitize(vv)}")
        else:
            out.append(f"{k}: {sanitize(v)}")
    out.append("---")
    out.append("")  # Leerzeile
    return "\n".join(out)

LAST_SYNC_RE = re.compile(r'^\s*last_sync:\s*".*?"\s*$', flags=re.M)

def strip_last_sync(txt: str) -> str:
    return LAST_SYNC_RE.sub("", txt or "")

def write_product(de: dict, en: dict):
    out_de = OUT_DE / de["slug"] / "index.md"
    out_en = OUT_EN / de["slug"] / "index.md"
    out_de.parent.mkdir(parents=True, exist_ok=True)
    out_en.parent.mkdir(parents=True, exist_ok=True)

    base_fm = {
        "type": "produkte",
        "slug": de["slug"],
        "kategorie": de.get("kategorie", []),
        "bilder": de.get("bilder", []),
        "varianten": de.get("varianten", []),
        "sku": de.get("sku") or en.get("sku") or "",
        "title_en": en["title"],  # optionaler Zusatzschlüssel
    }

    core_de = fm_to_str(base_fm, title=de["title"], beschr_de=de.get("beschreibung",""), beschr_en=en.get("beschreibung",""))
    core_en = fm_to_str(base_fm, title=en["title"], beschr_de=de.get("beschreibung",""), beschr_en=en.get("beschreibung",""))

    old_de = out_de.read_text(encoding="utf-8") if out_de.exists() else ""
    old_en = out_en.read_text(encoding="utf-8") if out_en.exists() else ""
    changed_de = strip_last_sync(old_de) != strip_last_sync(core_de)
    changed_en = strip_last_sync(old_en) != strip_last_sync(core_en)

    wrote = False
    ts = now_iso_berlin()

    if changed_de:
        new_de = fm_to_str(base_fm, title=de["title"], beschr_de=de.get("beschreibung",""), beschr_en=en.get("beschreibung",""), last_sync=ts)
        new_de = new_de.replace("\r\n", "\n")
        if not DRY_RUN:
            out_de.write_text(new_de, encoding="utf-8")
        print(f"[SYNC] DE {de['slug']}: CHANGED")
        wrote = True
    else:
        print(f"[SYNC] DE {de['slug']}: UNCHANGED")

    if changed_en:
        new_en = fm_to_str(base_fm, title=en["title"], beschr_de=de.get("beschreibung",""), beschr_en=en.get("beschreibung",""), last_sync=ts)
        new_en = new_en.replace("\r\n", "\n")
        if not DRY_RUN:
            out_en.write_text(new_en, encoding="utf-8")
        print(f"[SYNC] EN {de['slug']}: CHANGED")
        wrote = True
    else:
        print(f"[SYNC] EN {de['slug']}: UNCHANGED")

    return wrote

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
    d = {k: sanitize(v) for k, v in row.items()}
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

    if not varianten:
        preis = d.get("preis") or ""
        einheit = d.get("einheit") or ""
        if preis or einheit or sku:
            item = {"name": "Standard"}
            if preis:
                try:
                    item["preis"] = float(str(preis).replace(",", "."))
                except ValueError:
                    item["preis"] = sanitize(preis)
            if einheit:
                item["einheit"] = sanitize(einheit)
            if sku:
                item["sku"] = sanitize(sku)
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

    pub = first_col(df, "publish", "veröffentlichen")
    if pub:
        df = df[df[pub].astype(str).str.lower().isin(["1", "true", "ja", "yes", "y", ""])]

    OUT_DE.mkdir(parents=True, exist_ok=True)
    OUT_EN.mkdir(parents=True, exist_ok=True)

    written = 0
    for _, row in df.iterrows():
        row = {k: row[k] for k in df.columns}
        de = row_to_lang(row, "de")
        en = row_to_lang(row, "en")
        if write_product(de, en):
            written += 1

    print(f"✓ {written} Produkte geändert (idempotent).")
    print(f"DE → {OUT_DE}")
    print(f"EN → {OUT_EN}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        sys.exit(1)
