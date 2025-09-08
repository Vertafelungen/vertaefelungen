#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync aus Google Sheet → Markdown (DE/EN) + produkte.<lang>.json
Version: 2025-09-08 16:45 (Europe/Berlin)

Wesentliche Änderung:
- Link-Normalisierung erzeugt konsequent SPRACHRELATIVE Links.
  Beispiele (für lang='de'):
    /wissen/de/foo/bar      -> foo/bar
    /de/foo/bar             -> foo/bar
    ../foo/bar              -> ../foo/bar (belassen)
    /wissen/foo/bar (ohne Sprachpräfix) -> foo/bar (Warnung im Log)
    Absolute externe Links (https, mailto, tel) bleiben unverändert.

Damit erhält der Builder genug Kontext, um nach /wissen/<lang>/... zu rewriten.
"""

from __future__ import annotations
import os
import re
import json
from datetime import datetime

LANG_ROOT = os.getcwd()  # wird im Repo-Kontext aufgerufen
OUTPUT_DIR = "."

EXTERNAL = ("http://", "https://", "mailto:", "tel:", "ftp://", "ftps://")

def to_lang_relative(u: str, lang: str) -> str:
    s = u.strip()
    low = s.lower()
    if not s or s.startswith("#") or low.startswith(EXTERNAL):
        return s

    # /wissen/<lang>/...
    pfx = f"/wissen/{lang}/"
    if low.startswith(pfx):
        return s[len(pfx):]

    # /de/... oder /en/...
    if low.startswith("/de/") or low.startswith("/en/"):
        return s.split("/", 2)[2] if s.count("/") >= 2 else ""

    # /wissen/... (ohne Sprachpräfix)
    if low.startswith("/wissen/"):
        rest = s.split("/wissen/", 1)[1].lstrip("/")
        print(f"[sync] WARN: Root-Link ohne Sprachpräfix gefunden: {u} -> {rest}")
        return rest

    # Root-absolute interne Pfade "/foo/bar"
    if s.startswith("/"):
        return s.lstrip("/")

    # Relativpfade belassen
    return s

_LINK_ATTR_RE = re.compile(r'''(?P<attr>\b(?:href|src)\s*=\s*)(?P<q>["']?)(?P<url>[^"'\s>]+)(?P=q)''', re.IGNORECASE)

def normalize_links_in_text(txt: str, lang: str) -> str:
    def repl(m: re.Match) -> str:
        attr, q, url = m.group("attr"), m.group("q") or '"', m.group("url")
        return f'{attr}{q}{to_lang_relative(url, lang)}{q}'
    return _LINK_ATTR_RE.sub(repl, txt)

# -------------------------------------------------------------------
# ... Hier folgt unveränderter Code deiner CSV/Sheets-Verarbeitung ...
# -------------------------------------------------------------------

# (DEIN BESTEHENDER CODE) – Platzhalter:
catalog_de = []
catalog_en = []

# Beispiel: Spracheinträge nachbearbeiten (Landing Pages)
for lang in ("de", "en"):
    for candidate in (f"{lang}/index.md", f"{lang}/_index.md"):
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                txt = f.read()
            new_txt = normalize_links_in_text(txt, lang)
            if new_txt != txt:
                with open(candidate, "w", encoding="utf-8") as f:
                    f.write(new_txt)
                print(f"[sync] {candidate}: Links normalisiert.")
            else:
                print(f"[sync] {candidate}: keine Anpassungen nötig.")

# JSON schreiben
os.makedirs(OUTPUT_DIR, exist_ok=True)
produkte_de = {"language": "de", "generated": datetime.now().isoformat(), "items": catalog_de}
produkte_en = {"language": "en", "generated": datetime.now().isoformat(), "items": catalog_en}
with open(os.path.join(OUTPUT_DIR, "produkte.de.json"), "w", encoding="utf-8") as f:
    json.dump(produkte_de, f, ensure_ascii=False, indent=2)
with open(os.path.join(OUTPUT_DIR, "produkte.en.json"), "w", encoding="utf-8") as f:
    json.dump(produkte_en, f, ensure_ascii=False, indent=2)
print("[sync] produkte.de.json und produkte.en.json geschrieben.")
