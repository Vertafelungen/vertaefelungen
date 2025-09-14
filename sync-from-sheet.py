#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync-from-sheet.py
Version: 2025-09-14 14:10 (Europe/Berlin)

Zweck:
- CSV aus Google Sheets laden (via SHEET_CSV_URL ODER SHEET_ID + SHEET_GID)
- Aus jeder Zeile Markdown-Seiten (de/en) mit sauberem YAML-Frontmatter erzeugen
- Produkte-JSON (de/en) für Tools exportieren

Abhängigkeiten (siehe requirements.txt):
- pandas>=2.2
- requests>=2.32
- PyYAML>=6.0.1
"""

from __future__ import annotations

import os
import sys
import json
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yaml


# ------------------------------------------------------------
# Utils
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
SITE_DE = ROOT / "de"
SITE_EN = ROOT / "en"
TOOLS_DIR = ROOT / "tools"


def nfc(s: Any) -> str:
    """Unicode-NFC-Normalisierung + trim, robust gegen None."""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return unicodedata.normalize("NFC", s).strip()


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def read_csv_from_google() -> pd.DataFrame:
    """
    CSV laden:
      - bevorzugt SHEET_CSV_URL
      - sonst aus SHEET_ID + SHEET_GID zusammenbauen
    """
    csv_url = os.getenv("SHEET_CSV_URL", "").strip()
    sheet_id = os.getenv("SHEET_ID", "").strip()
    gid = os.getenv("SHEET_GID", "").strip()

    if not csv_url:
        if not sheet_id or not gid:
            print("❌ Weder SHEET_CSV_URL noch (SHEET_ID + SHEET_GID) gesetzt.", file=sys.stderr)
            sys.exit(1)
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

    print(f"📥 Lade CSV aus: {csv_url}")

    # Direkt mit pandas lesen (requests-Header sind normalerweise nicht notwendig)
    df = pd.read_csv(csv_url, dtype=str, keep_default_na=False, encoding="utf-8")
    # Alle Spalten und Werte nfc-normalisieren
    df.columns = [nfc(c) for c in df.columns]
    for c in df.columns:
        df[c] = df[c].map(nfc)
    print(f"✅ CSV geladen: {len(df):d} Zeilen, {len(df.columns):d} Spalten")
    return df


def first_nonempty(d: Dict[str, str], keys: List[str], default: str = "") -> str:
    for k in keys:
        v = d.get(k, "")
        if v:
            return v
    return default


def build_frontmatter(row: Dict[str, str], lang: str) -> Dict[str, Any]:
    """
    Erzeuge YAML-Frontmatter. Greift flexibel auf gängige Spalten zu.
    """
    if lang not in ("de", "en"):
        raise ValueError("lang must be 'de' or 'en'")

    title = first_nonempty(
        row,
        [f"meta_title_{lang}", f"title_{lang}", "title"],
        default=""
    )

    description = first_nonempty(
        row,
        [f"meta_description_{lang}", f"description_{lang}", "description"],
        default=""
    )

    fm: Dict[str, Any] = {
        "lang": lang,
        "title": title,
        "description": description,
    }

    # Optional: ein paar häufige Felder durchreichen, falls im Sheet vorhanden
    for key in ("kategorie_raw", "bilder_liste", "bilder_alt_de", "bilder_alt_en"):
        if key in row and row[key]:
            fm[key] = row[key]

    return fm


def write_markdown(lang: str, export_path: str, frontmatter: Dict[str, Any], body: str = "") -> Path:
    """
    Schreibt eine Datei <lang>/<export_path>/index.md mit YAML-Frontmatter.
    Achtung: export_path kommt sheet-seitig ohne führenden Slash (z. B. 'oeffentlich/produkte/...').
    """
    base = SITE_DE if lang == "de" else SITE_EN
    out_dir = base / export_path.strip("/")

    ensure_dir(out_dir)
    out_file = out_dir / "index.md"

    # YAML sicher erzeugen
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    content = f"---\n{yaml_text}\n---\n\n{body.strip()}\n"

    out_file.write_text(content, encoding="utf-8")
    return out_file


def add_to_catalog(catalog: List[Dict[str, Any]], lang: str, export_path: str, fm: Dict[str, Any]) -> None:
    """
    Fügt einen Katalogeintrag für die JSON-Exports hinzu.
    """
    catalog.append({
        "lang": lang,
        "path": f"{lang}/{export_path.strip('/')}/",
        "title": fm.get("title", ""),
        "description": fm.get("description", ""),
        "category": fm.get("kategorie_raw", ""),
    })


def write_catalogs_json(prod_de: List[Dict[str, Any]], prod_en: List[Dict[str, Any]]) -> None:
    ensure_dir(TOOLS_DIR)
    (TOOLS_DIR / "produkte.de.json").write_text(json.dumps(prod_de, ensure_ascii=False, indent=2), encoding="utf-8")
    (TOOLS_DIR / "produkte.en.json").write_text(json.dumps(prod_en, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main() -> None:
    df = read_csv_from_google()

    # records: Liste[Dict[str, str]]
    records: List[Dict[str, str]] = df.fillna("").to_dict(orient="records")

    products_de: List[Dict[str, Any]] = []
    products_en: List[Dict[str, Any]] = []

    for row in records:  # <-- WICHTIG: kein Unpacking mehr!
        # Export-Pfade aus dem Sheet (siehe Screenshots: export_pfad_de/export_pfad_en)
        path_de = first_nonempty(row, ["export_pfad_de", "exportpfad_de", "pfad_de"]).strip("/")
        path_en = first_nonempty(row, ["export_pfad_en", "exportpfad_en", "pfad_en"]).strip("/")

        # Wenn keine Export-Pfade vorhanden sind, überspringen
        if not path_de and not path_en:
            # Optional: Log
            # print("⚠️  Zeile ohne export_pfad_de/en – wird übersprungen.")
            continue

        # Frontmatter DE
        if path_de:
            fm_de = build_frontmatter(row, "de")
            md_de = write_markdown("de", path_de, fm_de, body="")
            add_to_catalog(products_de, "de", path_de, fm_de)
            # Optionales Log:
            # print(f"📝 de: {md_de}")

        # Frontmatter EN
        if path_en:
            fm_en = build_frontmatter(row, "en")
            md_en = write_markdown("en", path_en, fm_en, body="")
            add_to_catalog(products_en, "en", path_en, fm_en)
            # Optionales Log:
            # print(f"📝 en: {md_en}")

    write_catalogs_json(products_de, products_en)
    print(f"✅ Markdown & JSON erzeugt: {len(products_de)} (de), {len(products_en)} (en)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ Fehler: {exc}", file=sys.stderr)
        sys.exit(1)
