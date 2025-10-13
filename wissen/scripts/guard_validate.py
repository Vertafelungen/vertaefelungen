#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hart prüfender Guard:
- Alle *.md unter wissen/content/{de,en}/**/*.md
- Frontmatter mit ---/---; KEIN ***
- YAML parsebar; Feldtypen geprüft (price_cents:int, in_stock:bool, images:list[dict], lang in {de,en})
- Keine verbotenen Unicode-Zeichen (NBSP, ZWSP, Smart Quotes) im Header ODER Body
- Zeilenenden LF (keine CRLF)
- Keine '/public' Segmente in Pfad oder Werten
- Optional: Plausibilitätswarnung zu price_cents
Exit 1 bei Fehler.
"""
from __future__ import annotations

import sys, re
from pathlib import Path
from typing import Any, Dict, List

import unicodedata
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = REPO_ROOT / "wissen" / "content"
PROBLEM = {
    "\u00A0": "NBSP",
    "\u202F": "NARROW_NBSP",
    "\u200B": "ZWSP",
    "\u200C": "ZWNJ",
    "\u200D": "ZWJ",
    "\u2018": "SMART_QUOTE_L",
    "\u2019": "SMART_APOSTROPHE",
    "\u201C": "SMART_QUOTE_L",
    "\u201D": "SMART_QUOTE_R",
    "\u2013": "EN_DASH",
    "\u2014": "EM_DASH",
    "\u2026": "ELLIPSIS",
}
FORBIDDEN_SEGMENT = "/public/"

def find_frontmatter(txt: str):
    if not txt.startswith("---\n"):
        return None, None, "missing leading ---"
    end = txt.find("\n---", 4)
    if end == -1:
        return None, None, "missing closing ---"
    header = txt[4:end]
    body = txt[end+4:]
    if txt.startswith("***"):
        return None, None, "invalid delimiter ***"
    return header, body, None

def has_problem_chars(s: str) -> List[str]:
    found = []
    for ch, label in PROBLEM.items():
        if ch in s:
            found.append(label)
    return found

def check_types(y: Dict[str, Any], rel: str, errs: List[str]):
    def ensure_type(key, t):
        if key in y and not isinstance(y[key], t):
            errs.append(f"{rel}: field '{key}' must be {t.__name__}")

    # required-ish
    for k in ("slug", "lang", "title"):
        if k not in y or not y[k]:
            errs.append(f"{rel}: missing '{k}'")

    if "lang" in y and y["lang"] not in ("de", "en"):
        errs.append(f"{rel}: lang must be 'de' or 'en'")

    if "price_cents" in y:
        if not isinstance(y["price_cents"], int):
            errs.append(f"{rel}: price_cents must be int")
        elif y["price_cents"] < 0:
            errs.append(f"{rel}: price_cents must be >= 0")
        elif y["price_cents"] > 5000000:  # 50.000 €
            errs.append(f"{rel}: price_cents suspiciously high (>5,000,000)")

    ensure_type("in_stock", bool)

    if "images" in y:
        if not isinstance(y["images"], list):
            errs.append(f"{rel}: images must be a list")
        else:
            for i, it in enumerate(y["images"]):
                if not isinstance(it, dict):
                    errs.append(f"{rel}: images[{i}] must be map")
                    continue
                if "src" not in it or not isinstance(it["src"], str):
                    errs.append(f"{rel}: images[{i}].src must be string")
                if "alt" in it and not isinstance(it["alt"], str):
                    errs.append(f"{rel}: images[{i}].alt must be string")

    if "variants" in y and y["variants"] is not None:
        if not isinstance(y["variants"], list):
            errs.append(f"{rel}: variants must be a list")
        else:
            for i, it in enumerate(y["variants"]):
                if not isinstance(it, dict):
                    errs.append(f"{rel}: variants[{i}] must be map")
                if "preis_aufschlag_cents" in it and not isinstance(it["preis_aufschlag_cents"], int):
                    errs.append(f"{rel}: variants[{i}].preis_aufschlag_cents must be int")

def main():
    yaml = YAML(typ="safe")
    md_files = list((CONTENT_ROOT / "de").rglob("index.md")) + list((CONTENT_ROOT / "en").rglob("index.md"))
    errs: List[str] = []

    for f in md_files:
        rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
        b = f.read_bytes()
        if b.count(b"\r\n") > 0:
            errs.append(f"{rel}: CRLF found, must be LF only")

        try:
            txt = b.decode("utf-8")
        except UnicodeDecodeError:
            errs.append(f"{rel}: not UTF-8 decodable")
            continue

        if FORBIDDEN_SEGMENT in rel:
            errs.append(f"{rel}: path contains forbidden '/public'")
        if rel.count("/de/") + rel.count("/en/") != 1:
            errs.append(f"{rel}: unexpected language segment")

        header_txt, body_txt, err = find_frontmatter(txt)
        if err:
            errs.append(f"{rel}: {err}")
            continue

        # Problemzeichen suchen
        probs_h = has_problem_chars(header_txt or "")
        probs_b = has_problem_chars(body_txt or "")
        if probs_h:
            errs.append(f"{rel}: header contains forbidden chars: {', '.join(sorted(set(probs_h)))}")
        if probs_b:
            errs.append(f"{rel}: body contains forbidden chars: {', '.join(sorted(set(probs_b)))}")

        # YAML parsen
        try:
            y = yaml.load(header_txt) or {}
        except Exception as e:
            errs.append(f"{rel}: YAML parse error: {e}")
            continue

        # Typen prüfen
        if isinstance(y, dict):
            check_types(y, rel, errs)
            # Werte auf '/public' prüfen
            as_text = json.dumps(y, ensure_ascii=False)
            if "/public/" in as_text:
                errs.append(f"{rel}: YAML values must not contain '/public'")
        else:
            errs.append(f"{rel}: YAML must be mapping at top level")

    if errs:
        print("Guard found issues:\n", file=sys.stderr)
        for e in errs:
            print(" -", e, file=sys.stderr)
        sys.exit(1)

    print(f"Guard OK: {len(md_files)} files validated.")

if __name__ == "__main__":
    main()
