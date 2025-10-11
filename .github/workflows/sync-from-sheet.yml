#!/usr/bin/env python3
# Version: 2025-10-11
# Sync aus Google Sheet (CSV/Export) -> Markdown-Dateien
# - Sanitizing aller Textwerte: NBSP/Zero-Width/BOM/LSEP/PSEP entfernen/ersetzen
# - UTF-8 ohne BOM, LF
# - Variablen:
#     GSHEET_CSV_URL  (direkter CSV-Export-Link)  ODER
#     SHEET_ID + SHEET_GID (wird zu CSV-URL gebaut)
# - Erwartete Spalten (Beispiele; optional): title_de, title_en, slug,
#   beschreibung_md_de, beschreibung_md_en, kategorie (Komma-getrennt),
#   bilder (Komma-getrennt), varianten (Semikolon-getrennt; Name|Preis|Einheit|SKU)
from __future__ import annotations
from pathlib import Path
import os, io, re, sys, unicodedata, csv
import requests
import yaml

ROOT     = Path(__file__).resolve().parents[1]
CONTENT  = ROOT / "content"
DE_PROD  = CONTENT / "de" / "oeffentlich" / "produkte"
EN_PROD  = CONTENT / "en" / "public" / "products"

BOM = "\ufeff"
CTRL_RE  = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
SPACE_MAP = {
    **{ord(c): " " for c in " \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000"},
    ord("\u200B"): None, ord("\u200C"): None, ord("\u200D"): None, ord("\u2060"): None,
    ord("\u200E"): None, ord("\u200F"): None, ord("\u2028"): " ", ord("\u2029"): " ",
}

def norm(s: str | None) -> str:
    if s is None: return ""
    s = str(s).replace(BOM, "")
    s = unicodedata.normalize("NFKC", s).translate(SPACE_MAP).replace("\r\n", "\n")
    s = CTRL_RE.sub(" ", s)
    return s.strip()

def csv_from_env() -> str:
    url = os.getenv("GSHEET_CSV_URL", "").strip()
    if not url:
        sid = os.getenv("SHEET_ID", "").strip()
        gid = os.getenv("SHEET_GID", "").strip()
        if not sid or not gid:
            raise SystemExit("GSHEET_CSV_URL oder SHEET_ID+SHEET_GID müssen gesetzt sein.")
        url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text

def parse_list(cell: str) -> list[str]:
    cell = norm(cell)
    if not cell: return []
    parts = [norm(p) for p in cell.replace(";", ",").split(",")]
    return [p for p in parts if p]

def parse_varianten(cell: str):
    v = norm(cell)
    if not v: return []
    out = []
    for chunk in [s.strip() for s in v.split(";") if s.strip()]:
        bits = [b.strip() for b in chunk.split("|")]
        if not bits or not bits[0]: continue
        rec = {"name": bits[0]}
        if len(bits) > 1 and bits[1]:
            try: rec["preis"] = float(bits[1].replace(",", "."))
            except ValueError: rec["preis"] = bits[1]
        if len(bits) > 2 and bits[2]: rec["einheit"] = bits[2]
        if len(bits) > 3 and bits[3]: rec["sku"] = bits[3]
        out.append(rec)
    return out

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def write_utf8_nobom(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    p.write_bytes(data)

def build_frontmatter(row: dict, lang: str) -> dict:
    fm: dict = {}
    title = norm(row.get(f"title_{lang}", row.get("title", "")))
    fm["title"] = title
    fm["slug"]  = norm(row.get("slug", "")) or re.sub(r"[^a-z0-9\-]+","-", title.lower()).strip("-")
    fm["type"]  = "produkte"
    # Felder
    fm["kategorie"] = parse_list(row.get("kategorie", ""))
    fm["bilder"]    = parse_list(row.get("bilder", ""))
    fm[f"beschreibung_md_{lang}"] = norm(row.get(f"beschreibung_md_{lang}", ""))
    # Varianten
    var = parse_varianten(row.get("varianten",""))
    if var: fm["varianten"] = var
    # last_sync
    fm["last_sync"] = norm(row.get("last_sync", ""))
    return fm

def fm_to_text(fm: dict, body: str) -> str:
    order = [
        "title","slug","type","kategorie",
        "beschreibung_md_de","beschreibung_md_en",
        "bilder","varianten","sku","last_sync",
    ]
    rest = [k for k in fm.keys() if k not in order]
    lines = ["---"]
    for key in order + rest:
        if key not in fm: continue
        val = fm[key]
        if val in (None, "", [], {}): continue
        if key in ("beschreibung_md_de","beschreibung_md_en"):
            lines.append(f"{key}: |")
            for ln in str(val).splitlines(): lines.append(f"  {ln}")
        elif key in ("kategorie","bilder"):
            seq = val if isinstance(val, list) else [val]
            lines.append(f"{key}:")
            for el in seq: lines.append(f"  - {el}")
        elif key=="varianten" and isinstance(val, list):
            lines.append("varianten:")
            for item in val:
                if isinstance(item, dict):
                    lines.append("  -")
                    for kk,vv in item.items(): lines.append(f"    {kk}: {vv}")
                else:
                    lines.append(f"  - {item}")
        elif isinstance(val,(list,dict)):
            dumped = yaml.safe_dump(val, sort_keys=False, allow_unicode=True).rstrip("\n").splitlines()
            lines.append(f"{key}:")
            lines += [f"  {ln}" for ln in dumped]
        else:
            sval = str(val)
            if "\n" in sval:
                lines.append(f"{key}: |")
                for ln in sval.splitlines(): lines.append(f"  {ln}")
            else:
                lines.append(f"{key}: {sval}")
    lines.append("---")
    lines.append("")
    lines.append(body.lstrip())
    return "\n".join(lines)

def write_product_pages(row: dict):
    # deutsch
    fm_de  = build_frontmatter(row, "de")
    fm_en  = build_frontmatter(row, "en")
    slug   = fm_de["slug"]
    de_dir = DE_PROD / slug
    en_dir = EN_PROD / slug
    ensure_dir(de_dir); ensure_dir(en_dir)

    body_de = norm(row.get("body_md_de",""))
    body_en = norm(row.get("body_md_en",""))

    de_text = fm_to_text(fm_de, body_de)
    en_text = fm_to_text(fm_en, body_en)

    write_utf8_nobom(de_dir/"index.md", de_text)
    write_utf8_nobom(en_dir/"index.md", en_text)

def main():
    csv_text = csv_from_env()
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    for r in rows:
        write_product_pages(r)
    print(f"✓ synced {len(rows)} rows into Markdown (sanitized).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
