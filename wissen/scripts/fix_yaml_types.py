# Datei: wissen/scripts/fix_yaml_types.py
# Version: 2025-10-12 16:00 (Europe/Berlin)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from pathlib import Path
from typing import Tuple, Optional

import sys
try:
    import yaml
except ImportError:
    print("[fix_yaml_types] PyYAML nicht installiert. Bitte 'pip install pyyaml' ausführen.", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]  # .../wissen
CONTENT_DIR = ROOT / "content"

# Wir bearbeiten nur Produkt-Seiten (DE: produkte, EN: products) mit index.md
def iter_product_index_files(base: Path):
    for p in base.glob("**/index.md"):
        s = str(p).replace("\\", "/")
        if "/produkte/" in s or "/products/" in s:
            yield p

BOOL_TRUE = {
    "true", "wahr", "ja", "yes", "y", "t", "1",
    "verfügbar", "verfuegbar", "vorrätig", "vorraetig", "lagernd", "available", "in stock", "instock"
}
BOOL_FALSE = {
    "false", "falsch", "nein", "no", "n", "f", "0",
    "nicht verfügbar", "nicht verfuegbar", "nicht vorrätig", "ausverkauft", "unavailable", "out of stock", "outofstock"
}

PRICE_KEYS_FALLBACK = ["price_eur", "price", "preis", "price_euros"]

def parse_frontmatter(text: str) -> Tuple[Optional[dict], str, str]:
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            fm_raw = parts[0][4:]
            body = parts[1]
            try:
                data = yaml.safe_load(fm_raw) or {}
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
            return data, fm_raw, body
    return None, "", text

def to_bool(val):
    if isinstance(val, bool):
        return val
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in BOOL_TRUE:
        return True
    if s in BOOL_FALSE:
        return False
    # einfache Heuristiken
    if "nicht" in s or "no " in s or s.startswith("no"):
        return False
    if "verfügbar" in s or "verfuegbar" in s or "available" in s:
        return True
    return None

def euros_like_to_cents(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    s = str(value).strip()

    # Normale Schreibweisen: 12,34 / 12.34 / 12 / 12 € / 12,3 €
    m = re.match(r"^\s*([0-9]{1,7})([.,]([0-9]{1,2}))?\s*(€)?\s*$", s)
    if m:
        euros = int(m.group(1))
        cents = int((m.group(3) or "0").ljust(2, "0"))
        return euros * 100 + cents

    # Alles Nicht-Ziffern weg – deckt "1.299,00 €" / "EUR 12.50" / "12-50" etc. ab
    digits = re.sub(r"[^\d]", "", s)
    if digits == "":
        return None
    if len(digits) == 1:
        return int(digits)  # „5“ -> 5 Cent
    euros_part, cents_part = digits[:-2], digits[-2:]
    try:
        return int(euros_part) * 100 + int(cents_part)
    except ValueError:
        return None

def normalize_doc(path: Path) -> Tuple[bool, str]:
    raw = path.read_text(encoding="utf-8")
    data, fm_raw, body = parse_frontmatter(raw)
    if data is None:
        return False, "no-frontmatter"

    changed = False
    reasons = []

    # in_stock → Boolean
    if "in_stock" in data:
        new_bool = to_bool(data["in_stock"])
        if new_bool is not None and new_bool != data["in_stock"]:
            data["in_stock"] = new_bool
            changed = True
            reasons.append("in_stock->bool")

    # price_cents → Integer (Cent), ggf. aus Fallback-Feldern
    def set_price_from(val, src_key):
        nonlocal changed
        cents = euros_like_to_cents(val)
        if cents is not None:
            prev = data.get("price_cents")
            if prev != cents:
                data["price_cents"] = cents
                changed = True
                reasons.append(f"{src_key}->price_cents")
            return True
        return False

    if "price_cents" in data:
        if not set_price_from(data["price_cents"], "price_cents"):
            # wenn vorhandener Wert unparseable ist, probiere Fallbacks
            for k in PRICE_KEYS_FALLBACK:
                if k in data and data[k] not in (None, ""):
                    if set_price_from(data[k], k):
                        break
    else:
        for k in PRICE_KEYS_FALLBACK:
            if k in data and data[k] not in (None, ""):
                if set_price_from(data[k], k):
                    break

    if not changed:
        return False, ",".join(reasons) or "no-change"

    new_fm = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    new_text = f"---\n{new_fm}\n---\n{body}"
    path.write_text(new_text, encoding="utf-8")
    return True, ",".join(reasons)

def main():
    base = CONTENT_DIR
    files = list(iter_product_index_files(base))
    total = len(files)
    changed = 0
    for p in sorted(files):
        ch, why = normalize_doc(p)
        if ch:
            changed += 1
            print(f"[fix_yaml_types] FIXED {p} ({why})")
    print(f"[fix_yaml_types] Done. {changed}/{total} Dateien angepasst.")

if __name__ == "__main__":
    main()
