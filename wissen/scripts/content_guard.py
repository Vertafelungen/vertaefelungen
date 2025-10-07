#!/usr/bin/env python3
# Version: 2025-10-07 16:30 Europe/Berlin
# Strikter Content-Guard mit Unicode-Normalisierung des YAML-Frontmatters
from __future__ import annotations
from pathlib import Path
import re, sys, unicodedata
import yaml  # pip install pyyaml

ROOT    = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

FM_RE = re.compile(r'^---\n(.*?\n)---\n(.*)$', re.S)

# Unicode-Normalisierung (wie im Fixer)
SPACE_MAP = {
    **{ord(c): " " for c in " \u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000"},
    ord("\u200B"): None, ord("\u200C"): None, ord("\u200D"): None, ord("\u2060"): None,
    ord("\u200E"): None, ord("\u200F"): None, ord("\u2028"): " ", ord("\u2029"): " ",
}
def normalize_unicode(s: str) -> str:
    return unicodedata.normalize("NFKC", s).translate(SPACE_MAP)

# Pfad-Helfer
def is_product_path(p: Path) -> bool:
    s = p.as_posix()
    return "/de/oeffentlich/produkte/" in s or "/en/public/products/" in s
def is_faq_path(p: Path) -> bool:
    return "/faq/" in p.as_posix()
def is_index_file(p: Path) -> bool:
    return p.name == "_index.md"
def guess_type_by_path(p: Path) -> str | None:
    if is_product_path(p): return "produkte"
    if is_faq_path(p):     return "faq"
    if "/allgemeine-informationen/" in p.as_posix(): return "allgemeine-informationen"
    return None

# Struktur-Prüfung (erlaubt Blocks & Listen)
KEY_LINE   = re.compile(r'^\s*[^:#\-\s][^:]*:\s*(\|[+-]?|\>|[^\#].*)?$')
LIST_ITEM  = re.compile(r'^\s*-\s+.*$')
INDENTED   = re.compile(r'^\s+')

def head_structure_error(head_raw: str) -> str | None:
    head = normalize_unicode(head_raw)
    lines = head.splitlines()
    in_block = False
    for i, ln in enumerate(lines, start=1):
        if in_block:
            if ln.strip() == "" or INDENTED.match(ln):  # Folgezeilen eines Blocks
                continue
            in_block = False  # Block beendet, aktuelle Zeile weiterprüfen

        if ln.strip() == "" or ln.lstrip().startswith("#"):
            continue
        if KEY_LINE.match(ln):
            if ln.rstrip().endswith(("|", "|-", "|+", ">")):
                in_block = True
            continue
        if LIST_ITEM.match(ln):
            continue
        return f"Textzeile im YAML-Head (kein 'key: value' / Block / Liste): Zeile {i}: {ln[:60]!r}"
    return None

def parse_frontmatter(txt_raw: str):
    m = FM_RE.match(txt_raw)
    if not m:
        return None, None
    head_raw, body_raw = m.group(1), m.group(2)
    head = normalize_unicode(head_raw)
    body = normalize_unicode(body_raw)
    data = yaml.safe_load(head) or {}
    if not isinstance(data, dict):
        raise RuntimeError("YAML-Frontmatter ist kein Mapping (dict).")
    return head, data, body

# Schemas
SCHEMAS = {
    "produkte": {
        "required": {"title", "slug"},
        "recommended": {"kategorie","bilder","varianten","beschreibung_md_de","beschreibung_md_en","last_sync"},
    },
    "faq": {
        "required": {"title", "slug"},
        "recommended": {"frage_md_de","antwort_md_de","frage_md_en","antwort_md_en","tags"},
    },
    "allgemeine-informationen": {
        "required": {"title","slug"},
        "recommended": set(),
    },
}

def check_schema(p: Path, fm: dict, strict: bool):
    warns, errs = [], []

    implied = guess_type_by_path(p)
    fm_type = (fm.get("type") or "").strip().lower()
    t = fm_type or (implied or "")

    # _index.md nie strikt behandeln
    if is_index_file(p):
        if strict and implied in ("produkte","faq") and not fm_type:
            warns.append("Empfehlung: 'type' für _index.md optional setzen (z. B. 'produkte').")
        return warns, errs

    if implied in ("produkte","faq") and fm_type != implied:
        if strict:
            errs.append(f"Erwarte type='{implied}' (oder setze ihn explizit) für Datei im {implied}-Pfad.")
        else:
            warns.append(f"Empfehlung: type='{implied}' setzen.")
        t = implied or t

    schema = SCHEMAS.get(t) if t else None

    if schema:
        missing = [k for k in schema["required"] if not fm.get(k)]
        if missing:
            if strict and t in ("produkte","faq"):
                errs.append(f"Pflichtfelder fehlen: {', '.join(sorted(missing))}")
            else:
                warns.append(f"Empfehlung: fehlende Felder: {', '.join(sorted(missing))}")
        if t == "produkte":
            var = fm.get("varianten")
            if var is not None and var != "" and not isinstance(var, list):
                errs.append("'varianten' muss eine Liste sein (oder Feld ganz weglassen).")
    else:
        if strict and implied in ("produkte","faq"):
            errs.append("Frontmatter: Feld 'type' fehlt.")
        elif not t:
            warns.append("Frontmatter: Feld 'type' fehlt (allgemeine Seite/unklarer Bereich).")

    return warns, errs

def guard(strict: bool):
    errors, warns = [], []
    for p in CONTENT.rglob("*.md"):
        try:
            txt = p.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError as e:
            errors.append(f"{p}: Datei ist nicht UTF-8: {e}")
            continue

        m = FM_RE.match(txt)
        if not m:
            continue

        # Strukturcheck (robust gegen NBSP/Zero-Width)
        err = head_structure_error(m.group(1))
        if err:
            errors.append(f"{p}: {err}")
            continue

        try:
            _, fm, _ = parse_frontmatter(txt)
        except Exception as e:
            errors.append(f"{p}: YAML-Fehler: {e}")
            continue

        w, e = check_schema(p, fm, strict)
        warns += [f"{p}: {x}" for x in w]
        errors += [f"{p}: {x}" for x in e]

    return errors, warns

def main():
    strict = "--strict" in sys.argv
    errs, warns = guard(strict)
    for w in warns:
        print(f"[WARN] {w}")
    if errs:
        for e in errs:
            print(f"[ERR] {e}", file=sys.stderr)
        sys.exit(2)
    print("Content-Guard: OK")
    sys.exit(0)

if __name__ == "__main__":
    main()
