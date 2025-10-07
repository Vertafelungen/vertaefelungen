#!/usr/bin/env python3
# Version: 2025-10-07
from __future__ import annotations
from pathlib import Path
import re, sys, unicodedata
import yaml  # pip install pyyaml

ROOT = Path(__file__).resolve().parents[1]
PROD_DE = ROOT / "content" / "de" / "oeffentlich" / "produkte"
PROD_EN = ROOT / "content" / "en" / "public" / "products"

FM_RE = re.compile(r'^---\n(.*?\n)---\n(.*)$', re.S)

# Control chars (tab lassen wir zu), BOM, Zero-Width, NBSP, LSEP/PSEP
CTRL_RE  = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
BOM      = "\ufeff"
SPACE_MAP = {
    **{ord(c): " " for c in " \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000"},
    ord("\u200B"): None,  # ZWSP
    ord("\u200C"): None,  # ZWNJ
    ord("\u200D"): None,  # ZWJ
    ord("\u2060"): None,  # WJ
    ord("\u200E"): None,  # LRM
    ord("\u200F"): None,  # RLM
    ord("\u2028"): " ",   # LSEP → Space
    ord("\u2029"): " ",   # PSEP → Space
}

def norm_spaces(s: str) -> str:
    return s.translate(SPACE_MAP)

def sanitize(s: str | None) -> str:
    if s is None:
        return ""
    s = str(s).replace(BOM, "")
    s = CTRL_RE.sub(" ", s)
    s = s.replace("\r\n", "\n")
    s = norm_spaces(s)
    return s

def parse_varianten_from_string(txt: str):
    """Parst z.B. 'Standard|12,5|lfm|SKU123; Premium|19.9|lfm|SKU9' → Liste von Dicts."""
    if not txt:
        return []
    out = []
    for chunk in re.split(r"[;,\n]\s*(?=[^\|]+(\|)|$)", txt):  # grob robust
        chunk = chunk.strip()
        if not chunk:
            continue
        bits = [b.strip() for b in chunk.split("|")]
        if not bits or not bits[0]:
            continue
        item = {"name": sanitize(bits[0])}
        if len(bits) > 1 and bits[1]:
            try:
                item["preis"] = float(str(bits[1]).replace(",", "."))
            except ValueError:
                item["preis"] = sanitize(bits[1])
        if len(bits) > 2 and bits[2]:
            item["einheit"] = sanitize(bits[2])
        if len(bits) > 3 and bits[3]:
            item["sku"] = sanitize(bits[3])
        out.append(item)
    return out

def ensure_list_varianten(v):
    """Akzeptiert String/Liste/Mischformen und gibt saubere Liste[Dict] zurück."""
    if v in (None, "", []):
        return []
    if isinstance(v, str):
        return parse_varianten_from_string(v)
    if isinstance(v, list):
        norm = []
        for el in v:
            if isinstance(el, str):
                norm += parse_varianten_from_string(el)
            elif isinstance(el, dict):
                item = {}
                for k, vv in el.items():
                    key = str(k).strip().lower()
                    val = sanitize(vv)
                    if key == "preis":
                        try:
                            val = float(str(val).replace(",", "."))
                        except ValueError:
                            pass
                    item[key] = val
                if item:
                    norm.append(item)
        return norm
    # irgendwas anderes → fallen lassen
    return []

def fm_to_str(fm: dict, body: str) -> str:
    """Baut eine stabile Frontmatter-Zeichenkette (YAML) + Body zusammen."""
    order = [
        "title", "slug", "type", "kategorie",
        "beschreibung_md_de", "beschreibung_md_en",
        "bilder", "varianten", "sku", "last_sync",
    ]
    out = ["---"]
    for k in order:
        if k not in fm or fm[k] in (None, "", [], {}):
            continue
        v = fm[k]
        if k in ("beschreibung_md_de", "beschreibung_md_en"):
            out.append(f"{k}: |")
            for ln in str(v).splitlines():
                out.append(f"  {ln}")
        elif k in ("kategorie", "bilder"):
            seq = v if isinstance(v, list) else [v]
            out.append(f"{k}:")
            for el in seq:
                out.append(f"  - {sanitize(el)}")
        elif k == "varianten":
            if isinstance(v, list) and v:
                out.append("varianten:")
                for el in v:
                    out.append("  -")
                    for kk, vv in el.items():
                        out.append(f"    {kk}: {vv}")
        else:
            out.append(f"{k}: {v}")
    out.append("---")
    out.append("")
    out.append(body.lstrip())
    return "\n".join(out)

def repair_file(p: Path) -> bool:
    raw = p.read_text(encoding="utf-8", errors="replace")
    txt = sanitize(raw)
    # Frontmatter finden
    m = FM_RE.match(txt)
    if not m:
        return False
    head, body = m.group(1), m.group(2)

    # Tabs am Zeilenanfang im Head → Spaces (YAML mag keine Tab-Indents)
    head = re.sub(r'^\t+', lambda m: "  " * len(m.group(0)), head, flags=re.M)
    head = sanitize(head)

    # YAML laden (nach Sanitizing)
    try:
        fm = yaml.safe_load(head) or {}
    except Exception as e:
        # Letzter Versuch: exotische Unicode-Normalisierung
        head2 = unicodedata.normalize("NFKC", head)
        fm = yaml.safe_load(head2) or {}

    changed = False

    # type: falls fehlt, aus Pfad ableiten
    if not fm.get("type"):
        fm["type"] = "produkte"; changed = True

    # slug: falls fehlt, aus Ordnername
    if not fm.get("slug"):
        fm["slug"] = p.parent.name; changed = True

    # kategorie/bilder → Listen erzwingen
    for key in ("kategorie", "bilder"):
        val = fm.get(key)
        if val and not isinstance(val, list):
            fm[key] = [sanitize(val)]
            changed = True

    # Beschreibung-Felder sanitisieren
    for key in ("beschreibung_md_de", "beschreibung_md_en"):
        if key in fm and fm[key] is not None:
            fm[key] = sanitize(str(fm[key]))

    # varianten normalisieren
    if "varianten" in fm:
        newv = ensure_list_varianten(fm["varianten"])
        if newv:
            fm["varianten"] = newv
        else:
            # leer → Feld entfernen
            fm.pop("varianten", None)
        changed = True

    # body sanitisieren (nur Soft-Normierung)
    body = sanitize(body)

    # Neu schreiben, wenn Änderungen
    new = fm_to_str(fm, body)
    if new != raw:
        p.write_text(new, encoding="utf-8")
        print(f"[FIX] {p}")
        return True
    return False

def main():
    changed = 0
    for base in (PROD_DE, PROD_EN):
        if not base.exists():
            continue
        for p in base.rglob("index.md"):
            try:
                if repair_file(p):
                    changed += 1
            except Exception as e:
                print(f"[WARN] {p}: {e}", file=sys.stderr)
    print(f"✓ repariert: {changed} Produktdateien")
    return 0

if __name__ == "__main__":
    sys.exit(main())
