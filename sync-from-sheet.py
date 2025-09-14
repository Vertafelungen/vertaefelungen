#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync-from-sheet.py
Version: 2025-09-14 10:30 (Europe/Berlin)

Zweck
- Liest Content aus einem Google Sheet (CSV-Export) via requests/pandas
- Schreibt Markdown-Dateien in de/ und en/ (UTF-8) mit YAML-Frontmatter
- Normalisiert interne Links auf /wissen/<lang>/… (href/src & Markdown-Links)
- Erzeugt zwei Index-Dateien: produkte.de.json und produkte.en.json

Erwartete Umgebungsvariablen (über GitHub Actions gesetzt):
- SHEET_ID        : Google Sheet ID (Pflicht, wenn SHEET_CSV_URL fehlt)
- SHEET_GID       : Tabellen-GID (Pflicht, wenn SHEET_CSV_URL fehlt)
- SHEET_CSV_URL   : optional komplette CSV-URL (überschreibt SHEET_ID/GID)
- GOOGLE_SERVICE_ACCOUNT_JSON : optional (nicht benötigt für CSV)

Erwartete Spalten (robust; fehlende werden toleriert):
- slug                         (z. B. p0001)
- lang                         ("de" oder "en") – optional; siehe unten
- export_pfad_de, export_pfad_en
- titel_de, titel_en
- beschreibung_md_de, beschreibung_md_en
- description_de, description_en            (optional; Meta-Description)
- jsonld_de, jsonld_en                      (optional; JSON-String pro Seite)
- is_product / typ                          (optional: Kennzeichen für Produkte)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
import requests
import yaml


# -----------------------------------------------------------------------------
# Konfiguration & Hilfsfunktionen
# -----------------------------------------------------------------------------

CSV_TIMEOUT = 30  # Sekunden


def csv_url_from_env() -> str:
    """Ermittelt die CSV-Export-URL aus Umgebungsvariablen."""
    direct = os.environ.get("SHEET_CSV_URL", "").strip()
    if direct:
        return direct
    sheet_id = os.environ.get("SHEET_ID", "").strip()
    gid = os.environ.get("SHEET_GID", "").strip()
    if not sheet_id or not gid:
        raise SystemExit(
            "❌ SHEET_ID und/oder SHEET_GID fehlen. Setze entweder SHEET_CSV_URL "
            "oder beide Variablen SHEET_ID und SHEET_GID."
        )
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


# Links normalisieren: /wissen/ → /wissen/<lang>/ …
_HREF_SRC_QUOTED = re.compile(r'\b(href|src)\s*=\s*(["\'])/wissen/(?!de/|en/)', re.I)
_HREF_SRC_BARE = re.compile(r'\b(href|src)\s*=\s*/wissen/(?!de/|en/)', re.I)
_MD_WISSEN = re.compile(r'\]\(\s*/wissen/(?!de/|en/)', re.I)


def normalize_links(text: str, lang: str) -> str:
    """Korrigiert href/src + Markdown-Links auf /wissen/<lang>/…"""
    if not text:
        return text
    t = _HREF_SRC_QUOTED.sub(rf'\1=\2/wissen/{lang}/', text)
    t = _HREF_SRC_BARE.sub(rf'\1="/wissen/{lang}/', t)
    t = _MD_WISSEN.sub(f'](/wissen/{lang}/', t)
    return t


def ensure_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def safe_json_loads(s: str) -> Optional[Any]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        # Falls im Sheet versehentlich Single-Quotes verwendet wurden
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            return None


# -----------------------------------------------------------------------------
# Datenzugriff
# -----------------------------------------------------------------------------

def load_sheet_df() -> pd.DataFrame:
    url = csv_url_from_env()
    print(f"📥 Lade CSV aus: {url}")
    resp = requests.get(url, timeout=CSV_TIMEOUT)
    if resp.status_code != 200:
        raise SystemExit(f"❌ CSV-Download fehlgeschlagen (HTTP {resp.status_code})")
    content = resp.content  # bytes
    # pandas erkennt UTF-8 in der Regel automatisch; wir zwingen es explizit
    df = pd.read_csv(pd.io.common.BytesIO(content), dtype=str, keep_default_na=False, encoding="utf-8")
    print(f"✅ CSV geladen: {len(df)} Zeilen, {len(df.columns)} Spalten")
    return df


# -----------------------------------------------------------------------------
# Hauptlogik
# -----------------------------------------------------------------------------

def row_to_page_payload(row: Dict[str, str], lang: str) -> Optional[Dict[str, Any]]:
    """
    Baut den Payload für eine Sprach-Seite aus einer Zeile.
    Funktioniert sowohl mit Zeilen pro Item (ohne "lang"-Spalte) als auch mit
    Zeilen pro Sprache (mit "lang").
    """
    lang = lang.lower()
    slug = (row.get("slug") or "").strip()
    if not slug:
        return None

    # Wenn die Zeile explizit eine Sprache trägt, nur diese akzeptieren
    row_lang = (row.get("lang") or "").strip().lower()
    if row_lang in ("de", "en") and row_lang != lang:
        return None

    titel = (row.get(f"titel_{lang}") or "").strip()
    export_pfad = (row.get(f"export_pfad_{lang}") or "").strip()
    beschreibung_md = (row.get(f"beschreibung_md_{lang}") or "").strip()
    meta_desc = (row.get(f"description_{lang}") or "").strip()
    jsonld_str = row.get(f"jsonld_{lang}") or ""

    if not export_pfad:
        # ohne Zielordner keine Seite
        return None

    body = normalize_links(beschreibung_md, lang)
    jsonld = safe_json_loads(jsonld_str)

    fm = {
        "titel": titel or slug,
        "slug": slug,
        "export_pfad": export_pfad,
    }
    if meta_desc:
        fm["description"] = meta_desc
    if jsonld is not None:
        fm["jsonld"] = jsonld

    return {"frontmatter": fm, "body": body, "lang": lang}


def write_markdown(payload: Dict[str, Any]) -> Path:
    lang = payload["lang"]
    fm = payload["frontmatter"]
    body = payload["body"] or ""
    export_pfad = fm["export_pfad"]
    slug = fm["slug"]

    out_md = Path(lang) / export_pfad / f"{slug}.md"
    ensure_dir(out_md)

    front = yaml.dump(fm, allow_unicode=True, sort_keys=False).strip()
    md_text = f"---\n{front}\n---\n\n{body.strip()}\n"
    out_md.write_text(md_text, encoding="utf-8")
    print(f"📝 geschrieben: {out_md}")
    return out_md


def main() -> None:
    df = load_sheet_df()

    # Sammeln für Index-JSONs
    index_by_lang: Dict[str, List[Dict[str, Any]]] = {"de": [], "en": []}

    # Pro Zeile ggf. für beide Sprachen generieren
    for _, r in df.fillna("").to_dict(orient="records"):
        # erst DE
        de_payload = row_to_page_payload(r, "de")
        if de_payload:
            write_markdown(de_payload)
            index_by_lang["de"].append({
                "slug": de_payload["frontmatter"]["slug"],
                "titel": de_payload["frontmatter"].get("titel"),
                "export_pfad": de_payload["frontmatter"]["export_pfad"],
                "description": de_payload["frontmatter"].get("description", ""),
            })
        # dann EN
        en_payload = row_to_page_payload(r, "en")
        if en_payload:
            write_markdown(en_payload)
            index_by_lang["en"].append({
                "slug": en_payload["frontmatter"]["slug"],
                "titel": en_payload["frontmatter"].get("titel"),
                "export_pfad": en_payload["frontmatter"]["export_pfad"],
                "description": en_payload["frontmatter"].get("description", ""),
            })

    # Index-JSONs schreiben (für nachgelagerte Prozesse/Analysen)
    for lang in ("de", "en"):
        out_json = Path(f"produkte.{lang}.json")
        out_json.write_text(json.dumps(index_by_lang[lang], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📦 Index geschrieben: {out_json} ({len(index_by_lang[lang])} Einträge)")

    print("✅ Sync abgeschlossen.")


if __name__ == "__main__":
    main()
