#!/usr/bin/env python3
# Version: 2025-10-07 18:25 Europe/Berlin
#
# Zweck:
# - ALLE *.md unter wissen/content werden normalisiert
# - Frontmatter: NBSP/Zero-Width/LSEP/PSEP/BOM/Control entfernen/ersetzen
# - Tabs im YAML-Indent -> Spaces
# - YAML-Head robust parsen (Fallback, falls PyYAML meckert)
# - Produkte:
#     * in Pfaden .../de/oeffentlich/produkte/** und .../en/public/products/**
#     * _index.md: type="produkte" ergänzen (falls fehlt)
#     * index.md:  type="produkte" + slug aus Ordner ergänzen (falls fehlt)
#     * varianten: String -> Liste[Objekt]
# - Serialisiert Frontmatter stabil und menschenlesbar zurück
#
from __future__ import annotations
from pathlib import Path
import re, sys, unicodedata
import yaml

ROOT    = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

BOM = "\ufeff"
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
    return re.sub(r'^\t+', lambda m: "  " * len(m.group(0)), head, flags=re.M)

def sanitize_head(head: str) -> str:
    return detab_head(norm_unicode(head))

def strip_disallowed_yaml_chars(head: str) -> str:
    # „letztes Netz“: NBSP->Space; Zero-Width/Format (Cf) entfernen
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

def is_product_path(p: Path) -> bool:
    s = p.as_posix()
    return "/de/oeffentlich/produkte/" in s or "/en/public/products/" in s

def is_index(p: Path) -> bool:
    return p.name.lower() == "index.md"

def is_index_list(p: Path) -> bool:
    return p.name.lower() == "_index.md"

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

def yaml_parse_robust(head: str) -> dict:
    try:
        data = yaml.safe_load(head) or {}
    except Exception:
        data = yaml.safe_load(strip_disallowed_yaml_chars(head)) or {}
    if not isinstance(data, dict):
        raise RuntimeError("Frontmatter ist kein Mapping")
    return data

def dump_nested(val, indent: int = 0) -> list[str]:
    """Dump für unbekannte Strukturen als YAML-Block (ohne Header)."""
    dumped = yaml.safe_dump(val, sort_keys=False, allow_unicode=True)
    lines = dumped.rstrip("\n").splitlines()
    if indent:
        pad = " " * indent
        lines = [pad + ln if ln else ln for ln in lines]
    return lines

def serialize_head(data: dict) -> str:
    order = [
        "title", "slug", "type", "kategorie",
        "beschreibung_md_de", "beschreibung_md_en",
        "bilder", "varianten", "sku", "last_sync",
    ]
    # Rest-Schlüssel in stabiler Reihenfolge anhängen
    rest = [k for k in data.keys() if k not in order]
    lines: list[str] = []
    for key in order + rest:
        if key not in data:
            continue
        val = data[key]
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
        elif key == "varianten" and isinstance(val, list):
            lines.append("varianten:")
            for item in val:
                if isinstance(item, dict):
                    lines.append("  -")
                    for kk, vv in item.items():
                        lines.append(f"    {kk}: {vv}")
                else:
                    lines.append(f"  - {item}")
        elif isinstance(val, (list, dict)):
            lines.append(f"{key}:")
            lines.extend(dump_nested(val, indent=2))
        else:
            sval = str(val)
            if "\n" in sval:
                lines.append(f"{key}: |")
                for ln in sval.splitlines():
                    lines.append(f"  {ln}")
            else:
                lines.append(f"{key}: {sval}")
    return "\n".join(lines) + "\n"

def repair_file(p: Path) -> bool:
    raw = p.read_text(encoding="utf-8", errors="replace")
    txt = norm_unicode(raw)
    m = FM_RE.match(txt)
    if not m:
        return False
    head_raw, body_raw = m.group(1), m.group(2)
    head = sanitize_head(head_raw)
    body = norm_unicode(body_raw)

    data = yaml_parse_robust(head)

    # Produkt-Heuristiken
    if is_product_path(p):
        if is_index(p):
            data.setdefault("type", "produkte")
            data.setdefault("slug", p.parent.name)
            if "varianten" in data:
                newv = normalize_variants(data["varianten"])
                if newv:
                    data["varianten"] = newv
                else:
                    data.pop("varianten", None)
        elif is_index_list(p):
            data.setdefault("type", "produkte")
            # _index.md braucht keinen slug

    new_head = serialize_head(data)
    new_txt  = f"---\n{new_head}---\n{body.lstrip()}"

    if new_txt != raw:
        p.write_text(new_txt, encoding="utf-8")
        print(f"[FIX] {p}")
        return True
    return False

def main():
    changed = 0
    for p in CONTENT.rglob("*.md"):
        try:
            if repair_file(p):
                changed += 1
        except Exception as e:
            print(f"[WARN] {p}: {e}", file=sys.stderr)
    print(f"✓ normalized frontmatter in {changed} files")
    return 0

if __name__ == "__main__":
    sys.exit(main())
