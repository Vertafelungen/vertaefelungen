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

MD_GLOB = "**/products/**/index.md"

BOOL_TRUE = {"true", "wahr", "ja", "yes", "1", "y", "t"}
BOOL_FALSE = {"false", "falsch", "nein", "no", "0", "n", "f"}

PRICE_KEYS_FALLBACK = ["price_eur", "price", "preis", "price_euros"]

def parse_frontmatter(text: str) -> Tuple[Optional[dict], str, str]:
    """
    Splittet Frontmatter und Body. Gibt (data, frontmatter_raw, body) zurück.
    Wenn keine Frontmatter vorhanden ist, data=None.
    """
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            fm_raw = parts[0][4:]  # nach erstem '---\n'
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
    return None  # unklar -> nicht ändern

def euros_like_to_cents(value) -> Optional[int]:
    """
    Nimmt alles an, was wie Preis aussieht:
    - "12,99 €" / "12.99" / "12,99" / "1299" / "1.299,00 €" etc.
    - auch Strings mit Text; alle Ziffern extrahieren + letzte 2 als Cent
    """
    if value is None:
        return None
    if isinstance(value, (int,)):
        # Falls schon Cent ist und plausibel (>=0)
        return value if value >= 0 else None
    s = str(value).strip()
    # 1) Versuche klassische Schreibweisen 12,34 / 12.34
    m = re.match(r"^\s*([0-9]{1,6})([.,]([0-9]{1,2}))?\s*(€)?\s*$", s)
    if m:
        euros = int(m.group(1))
        cents = int((m.group(3) or "0").ljust(2, "0"))
        return euros * 100 + cents

    # 2) Entferne alles außer Ziffern (auch Tausenderpunkte/Leerzeichen/€)
    digits = re.sub(r"[^\d]", "", s)
    if digits == "":
        return None
    # Wenn nur eine Stelle, interpretiere als z. B. "5" -> 5 Cent
    if len(digits) == 1:
        return int(digits)
    # Sonst letzte zwei Ziffern = Cent
    euros_part = digits[:-2]
    cents_part = digits[-2:]
    try:
        return int(euros_part) * 100 + int(cents_part)
    except ValueError:
        return None

def normalize_doc(path: Path) -> Tuple[bool, str]:
    """
    Normalisiert price_cents (int) und in_stock (bool).
    Gibt (changed, reason) zurück.
    """
    raw = path.read_text(encoding="utf-8")
    data, fm_raw, body = parse_frontmatter(raw)
    if data is None:
        # Kein Frontmatter -> Guard meldet nur WARN, wir lassen es unangetastet.
        return False, "no-frontmatter"

    changed = False
    reasons = []

    # in_stock
    if "in_stock" in data:
        new_bool = to_bool(data["in_stock"])
        if new_bool is not None and new_bool != data["in_stock"]:
            data["in_stock"] = new_bool
            changed = True
            reasons.append("in_stock->bool")
    else:
        # nicht vorhanden: nicht erzwingen
        pass

    # price_cents
    if "price_cents" in data:
        new_cents = euros_like_to_cents(data["price_cents"])
        if new_cents is not None and new_cents != data["price_cents"]:
            data["price_cents"] = new_cents
            changed = True
            reasons.append("price_cents->int")
    else:
        # versuche aus Fallback-Feldern zu gewinnen
        for k in PRICE_KEYS_FALLBACK:
            if k in data and data[k] not in (None, ""):
                new_cents = euros_like_to_cents(data[k])
                if new_cents is not None:
                    data["price_cents"] = new_cents
                    changed = True
                    reasons.append(f"{k}->price_cents")
                    break

    if not changed:
        return False, ",".join(reasons) or "no-change"

    # Schreibe zurück (Frontmatter + Body)
    new_fm = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    new_text = f"---\n{new_fm}\n---\n{body}"
    path.write_text(new_text, encoding="utf-8")
    return True, ",".join(reasons)

def main():
    base = CONTENT_DIR
    files = sorted(base.glob(MD_GLOB))
    total = 0
    changed = 0
    for p in files:
        total += 1
        ch, why = normalize_doc(p)
        if ch:
            changed += 1
            print(f"[fix_yaml_types] FIXED {p} ({why})")
    print(f"[fix_yaml_types] Done. {changed}/{total} Dateien angepasst.")

if __name__ == "__main__":
    main()
