#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync-from-sheet.py
Version: 2025-09-11 10:00 (Europe/Berlin)

Sync aus Google Sheet → Markdown-Dateien (de/, en/).
Normalisiert interne Links auf /wissen/<lang>/…,
sodass keine sprachlosen /wissen/-Links mehr entstehen.
"""

import os
import re
from pathlib import Path
import yaml

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")
SHEET_KEY = os.environ.get("SHEET_KEY")

if not SHEET_KEY:
    raise SystemExit("❌ SHEET_KEY ist nicht gesetzt (Repo-Secret). Bitte in den Actions-Secrets hinterlegen.")

if not os.path.exists(CREDS_FILE):
    raise SystemExit(f"❌ Service-Account-Datei '{CREDS_FILE}' nicht gefunden. "
                     "Lege das JSON in ein Secret (GOOGLE_SERVICE_ACCOUNT_JSON) und schreibe es im Workflow in eine Datei.")

def _authorize():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
    return gspread.authorize(creds)

def to_lang_relative(url: str, lang: str) -> str:
    """Macht aus /wissen/... → pfad relativ mit Sprachcode (für Quellen)."""
    if not url:
        return url
    u = url.strip()
    low = u.lower()
    if low.startswith(("http://", "https://", "mailto:", "tel:")):
        return u
    if low.startswith(f"/wissen/{lang}/"):
        return u.split(f"/wissen/{lang}/", 1)[1]
    if low.startswith(f"/{lang}/"):
        return u.split(f"/{lang}/", 1)[1]
    if low.startswith("/wissen/"):
        # sprachlos → /wissen/ entfernen
        return u.split("/wissen/", 1)[1]
    return u.lstrip("/")

def normalize_links(text: str, lang: str) -> str:
    """Korrigiert href/src und Markdown-Links auf /wissen/<lang>/…"""
    if not text:
        return text
    # href/src mit Quotes
    text = re.sub(
        r'\b(href|src)\s*=\s*(["\'])/wissen/(?!de/|en/)',
        rf'\1=\2/wissen/{lang}/',
        text,
        flags=re.I,
    )
    # href/src ohne Quotes
    text = re.sub(
        r'\b(href|src)\s*=\s*/wissen/(?!de/|en/)',
        rf'\1="/wissen/{lang}/',
        text,
        flags=re.I,
    )
    # Markdown-Links [text](/wissen/…)
    text = re.sub(
        r'\]\(\s*/wissen/(?!de/|en/)',
        f'](/wissen/{lang}/',
        text,
        flags=re.I,
    )
    return text

def main():
    gc = _authorize()
    sheet = gc.open_by_key(SHEET_KEY).sheet1

    rows = sheet.get_all_records()
    for row in rows:
        slug = row.get("slug")
        lang = (row.get("lang") or "").strip().lower()  # "de" oder "en"
        export_pfad = row.get(f"export_pfad_{lang}")
        titel = row.get(f"titel_{lang}")
        beschreibung = row.get(f"beschreibung_md_{lang}")

        if not slug or not lang or not export_pfad:
            # unvollständige Zeilen überspringen
            continue

        rel_path = Path(lang) / export_pfad / f"{slug}.md"
        rel_path.parent.mkdir(parents=True, exist_ok=True)

        body = normalize_links(beschreibung or "", lang)

        frontmatter = {
            "titel": titel,
            "slug": slug,
            "export_pfad": export_pfad,
        }

        md_text = "---\n" + yaml.dump(frontmatter, allow_unicode=True) + "---\n\n" + body
        rel_path.write_text(md_text, encoding="utf-8")
        print(f"✅ geschrieben: {rel_path}")

if __name__ == "__main__":
    main()
