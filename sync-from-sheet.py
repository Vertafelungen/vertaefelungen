#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync-from-sheet.py
Version: 2025-09-11 06:25 (Europe/Berlin)

Sync aus Google Sheet → Markdown-Dateien (de/, en/).
Normalisiert alle internen Links auf /wissen/<lang>/…,
sodass keine sprachlosen /wissen/-Links mehr entstehen.
"""

import re
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path
import yaml

# ----------------------------------------------------------
# Google Sheets Zugriff
# ----------------------------------------------------------
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")
SHEET_KEY = os.environ.get("SHEET_KEY")

if not SHEET_KEY:
    raise SystemExit("❌ Bitte die Umgebungsvariable SHEET_KEY setzen.")

creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_KEY).sheet1

# ----------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------
def to_lang_relative(url: str, lang: str) -> str:
    """Macht aus /wissen/... → pfad relativ mit Sprachcode."""
    if not url:
        return url
    u = url.strip()
    if u.startswith("http://") or u.startswith("https://") or u.startswith("mailto:"):
        return u
    # /wissen/de/... → strip /wissen/de/
    if u.startswith(f"/wissen/{lang}/"):
        return u.split(f"/wissen/{lang}/", 1)[1]
    # /de/... oder /en/... → strip
    if u.startswith(f"/{lang}/"):
        return u.split(f"/{lang}/", 1)[1]
    # /wissen/... ohne Sprachpräfix → strip /wissen/
    if u.startswith("/wissen/"):
        return u.split("/wissen/", 1)[1]
    return u.lstrip("/")

def normalize_links(text: str, lang: str) -> str:
    """Korrigiert href/src und Markdown-Links auf /wissen/<lang>/…"""
    if not text:
        return text
    # href/src mit oder ohne Quotes
    text = re.sub(
        r'\b(href|src)\s*=\s*(["\'])/wissen/(?!de/|en/)',
        rf'\1=\2/wissen/{lang}/',
        text,
        flags=re.I,
    )
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

# ----------------------------------------------------------
# Hauptlogik
# ----------------------------------------------------------
def main():
    rows = sheet.get_all_records()
    for row in rows:
        slug = row.get("slug")
        lang = row.get("lang")  # "de" oder "en"
        export_pfad = row.get(f"export_pfad_{lang}")
        titel = row.get(f"titel_{lang}")
        beschreibung = row.get(f"beschreibung_md_{lang}")

        if not slug or not export_pfad:
            continue

        rel_path = Path(lang) / export_pfad / f"{slug}.md"
        rel_path.parent.mkdir(parents=True, exist_ok=True)

        # Body vorbereiten
        body = normalize_links(beschreibung, lang)

        content = {
            "titel": titel,
            "slug": slug,
            "export_pfad": export_pfad,
        }

        md_text = "---\n" + yaml.dump(content, allow_unicode=True) + "---\n\n" + (body or "")
        rel_path.write_text(md_text, encoding="utf-8")
        print(f"✅ geschrieben: {rel_path}")

if __name__ == "__main__":
    main()
