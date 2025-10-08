#!/usr/bin/env python3
# One-off Repair: säubert Frontmatter in Produktverzeichnissen für
#  - .../produkte/**/index.md        (Detailseiten)
#  - .../produkte/**/_index.md       (Listen/Übersichtsseiten)
#  - .../products/**/index.md        (EN)
#  - .../products/**/_index.md       (EN)
#
# Behebt u.a.:
# - NBSP (#xA0), Zero-Width, LSEP/PSEP, BOM, Control-Chars
# - Tabs im YAML-Indent
# - unstrukturierte "varianten" -> Liste[Objekt]
# - fehlendes type/slug (slug nur auf Detailseiten)
# - saubere, stabile YAML-Serialisierung
from __future__ import annotations
from pathlib import Path
import re, sys, unicodedata
import yaml  # pip install pyyaml

ROOT    = Path(__file__).resolve().parents[1]
DE_BASE = ROOT / "content" / "de" / "oeffentlich" / "produkte"
EN_BASE = ROOT / "content" / "en" / "public" / "products"

BOM   = "\ufeff"
FM_RE = re.compile(r'^---\n(.*?\n)---\n(.*)$', re.S)
CTRL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')

SPACE_MAP = {
    # alle Space-Varianten -> Space
    **{ord(c): " " for c in " \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000"},
    # Zero-Width/Format entfernen
    ord("\u200B"): None, ord("\u200C"): None, ord("\u200D"): None, ord("\u2060"): None,
    ord("\u200E"): None, ord("\u200F"): None,
    # LSEP/PSEP -> Space
    ord("\u2028"): " ", ord("\u2029"): " ",
}

def norm_unicode(s: str) -> str:
    if s is None:
        return ""
    s = s.replace(BOM, "")
    s = unicodedata.normalize("NFKC", s).translate(SPACE_MAP).replace("\r\n", "\n")
    s = CTRL_RE.sub(" ", s)
    return s

def detab_head(head: str) -> str:
    # Tabs am Zeilenanfang sind im YAML-Indent unzulässig
    return re.sub(r'^\t+', lambda m: "  " * len(m.group(0)), head, flags=re.M)

def sanitize_head(head: str) -> str:
    return detab_head(norm_unicode(head))

def strip_disallowed_yaml_chars(head: str) -> str:
    # „letztes Netz“ vor YAML-Parse: NBSP -> Space, Zero-Width entfernen
    out = []
    for ch in head:
        if ch == "\u00A0":
            out.append(" ")
        elif unicodedata.category(ch) == "Cf":
            continue
        else:
            out.append(ch)
    return "".join(out)

def split_frontmatter(txt: str):
    m = FM_RE.match(txt)
    if not m:
        return None, None
    return m.group(1), m.group(2)

def is_index_like(p: Path) -> bool:
    n = p.name.lower()
    return n == "index.md" or n == "_index.md"

def is_detail_page(p: Path) -> bool:
    # Detailseite = index.md (nicht _index.md)
    return p.name.lower() == "index.md"

def serialize_yaml(head_dict: dict, body: str) -> str:
    """Schreibt das Frontmatter in stabiler, menschenlesbarer Form."""
    order = [
        "title", "slug", "type", "kategorie",
        "beschreibung_md_de", "beschreibung_md_en",
        "bilder", "varianten", "sku", "last_sync",
    ]
    lines = ["---"]
    for key in order:
        if key not in head_dict:
            continue
        val = head_dict[key]
        if val in (None, "", [], {}):
            continue
        if key in ("beschreibung_md_de", "beschreibung_md_en"):
            lines.append(f"{key}: |")
            for ln in str(val).splitlines():
                lines.append(f"  {ln}")
        elif key in ("kategorie", "bilder"):
            seq = val if isinstance(val, list) else [val]
            lines.append(f"{key}:")
            for el in seq:
                lines.append(f"  - {el}")
        elif key == "varianten":
            if isinstance(val, list) and val:
                lines.append("varianten:")
                for item in val:
                    lines.append("  -")
                    for kk, vv in item.items():
                        lines.append(f"    {kk}: {vv}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append("")
    lines.append((body or "").lstrip())
    return "\n".join(lines)

def parse_yaml_head(head: str) -> dict:
    try:
        return yaml.safe_load(head) or {}
    except Exception:
        head2 = strip_disallowed_yaml_chars(head)
        return yaml.safe_load(head2) or {}

def variants_from_string(txt: str):
    if not txt:
        return []
    out = []
    for chunk in [s.strip() for s in txt.split(";") if s.strip()]:
        bits = [b.strip() for b in chunk.split("|")]
        if not bits or not bits[0]:
            continue
        rec = {"name": bits[0]}
        if len(bits) > 1 and bits[1]:
            try:
                rec["preis"] = float(bits[1].replace(",", "."))
            except ValueError:
                rec["preis"] = bits[1]
        if len(bits) > 2 and bits[2]:
            rec["einheit"] = bits[2]
        if len(bits) > 3 and bits[3]:
            rec["sku"] = bits[3]
        out.append(rec)
    return out

def normalize_variants(v):
    if v in (None, "", []):
        return []
    if isinstance(v, str):
        return variants_from_string(v)
    if isinstance(v, list):
        out = []
        for el in v:
            if isinstance(el, str):
                out += variants_from_string(el)
            elif isinstance(el, dict):
                rec = {}
                for k, vv in el.items():
                    key = str(k).strip().lower()
                    val = norm_unicode(str(vv))
                    if key == "preis":
                        try:
                            val = float(str(vv).replace(",", "."))
                        except Exception:
                            pass
                    rec[key] = val
                if rec:
                    out.append(rec)
        return out
    return []

def repair_file(p: Path) -> bool:
    raw = p.read_text(encoding="utf-8", errors="replace")
    txt = norm_unicode(raw)
    fm = split_frontmatter(txt)
    if not fm:
        return False
    head_raw, body_raw = fm
    head = sanitize_head(head_raw)
    body = norm_unicode(body_raw)

    data = parse_yaml_head(head)
    if not isinstance(data, dict):
        raise RuntimeError(f"Frontmatter kein Mapping in {p}")

    is_detail = is_detail_page(p)

    # Pflichtfelder
    if not data.get("type"):
        data["type"] = "produkte"
    if is_detail and not data.get("slug"):
        data["slug"] = p.parent.name

    # Listenfelder vereinheitlichen
    for key in ("kategorie", "bilder"):
        if key in data and data[key] not in (None, "") and not isinstance(data[key], list):
            data[key] = [str(data[key]).strip()]

    # varianten normalisieren (nur Detailseiten relevant)
    if is_detail:
        if "varianten" in data:
            newv = normalize_variants(data["varianten"])
            if newv:
                data["varianten"] = newv
            else:
                data.pop("varianten", None)
    else:
        # auf _index.md sicherstellen, dass keine „varianten“ o. ä. rumliegt
        if "varianten" in data and not data["varianten"]:
            data.pop("varianten", None)

    fixed = serialize_yaml(data, body)

    if fixed != raw:
        p.write_text(fixed, encoding="utf-8")
        print(f"[FIX] {p}")
        return True
    return False

def main():
    changed = 0
    for base in (DE_BASE, EN_BASE):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and is_index_like(p):
                try:
                    if repair_file(p):
                        changed += 1
                except Exception as e:
                    print(f"[WARN] {p}: {e}", file=sys.stderr)
    print(f"✓ product index repaired: {changed} files")
    return 0

if __name__ == "__main__":
    sys.exit(main())
