#!/usr/bin/env python3
# Version: 2025-10-07 (robust: block scalars, lists, _index.md-Ausnahme)
from __future__ import annotations
from pathlib import Path
import re, sys
import yaml  # pip install pyyaml

ROOT    = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

FM_RE = re.compile(r'^---\n(.*?\n)---\n(.*)$', re.S)

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

def is_product_path(p: Path) -> bool:
    s = p.as_posix()
    return "/de/oeffentlich/produkte/" in s or "/en/public/products/" in s

def is_faq_path(p: Path) -> bool:
    s = p.as_posix()
    return "/faq/" in s

def is_index_file(p: Path) -> bool:
    return p.name == "_index.md"

def guess_type_by_path(p: Path) -> str | None:
    if is_product_path(p): return "produkte"
    if is_faq_path(p):     return "faq"
    if "/allgemeine-informationen/" in p.as_posix(): return "allgemeine-informationen"
    return None

def read_utf8(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="strict")

def parse_frontmatter(txt: str):
    m = FM_RE.match(txt)
    if not m:
        return None, None
    head, body = m.group(1), m.group(2)
    data = yaml.safe_load(head) or {}
    if not isinstance(data, dict):
        raise RuntimeError("YAML-Frontmatter ist kein Mapping (dict).")
    return head, data, body

# -------- Struktur-Check für YAML-Head (erlaubt Block- und Listenzeilen)
KEY_LINE   = re.compile(r'^\s*[^:#\-\s][^:]*:\s*(\|[+-]?|\>|[^\#].*)?$')
LIST_ITEM  = re.compile(r'^\s*-\s+.*$')
INDENTED   = re.compile(r'^\s+')

def head_structure_error(head: str) -> str | None:
    """Erkennt fälschlich hineingeratene Freitext-Zeilen im YAML-Head.

    Erlaubt:
      - key: value
      - key: | / >  (Block), danach eingerückte Folgezeilen
      - Listenzeilen: '  - item'
      - leere Zeilen & Kommentare
    """
    lines = head.splitlines()
    in_block = False
    for i, ln in enumerate(lines, start=1):
        if in_block:
            if ln.strip() == "" or INDENTED.match(ln):
                continue
            # Block endet, aktuelle Zeile erneut normal prüfen
            in_block = False
            # kein "continue" – wir prüfen ln direkt unten

        if ln.strip() == "" or ln.lstrip().startswith("#"):
            continue

        if KEY_LINE.match(ln):
            if ln.rstrip().endswith(("|", "|-", "|+", ">")):
                in_block = True
            continue

        if LIST_ITEM.match(ln):
            continue

        # alles andere ist verdächtiger Freitext
        return f"Textzeile im YAML-Head (kein 'key: value' / Block / Liste): Zeile {i}: {ln[:60]!r}"
    return None

# -------- Schema-Prüfung
def check_schema(p: Path, fm: dict, strict: bool):
    warns, errs = [], []

    implied = guess_type_by_path(p)
    fm_type = (fm.get("type") or "").strip().lower()
    t = fm_type or (implied or "")

    # _index.md: nie strikt behandeln (Aggregationsseiten)
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
            # nur Fehler, wenn Feld existiert und KEINE Liste ist
            if var is not None and var != "" and not isinstance(var, list):
                errs.append("'varianten' muss eine Liste sein (oder Feld ganz weglassen).")
    else:
        if strict and implied in ("produkte","faq"):
            errs.append("Frontmatter: Feld 'type' fehlt.")
        elif not t:
            warns.append("Frontmatter: Feld 'type' fehlt (allgemeine Seite/unklarer Bereich).")

    return warns, errs

# -------- Lauf
def guard(strict: bool):
    errors, warns = [], []
    for p in CONTENT.rglob("*.md"):
        try:
            txt = read_utf8(p)
        except UnicodeDecodeError as e:
            errors.append(f"{p}: Datei ist nicht UTF-8: {e}")
            continue

        m = FM_RE.match(txt)
        if not m:
            continue

        head = m.group(1)
        err = head_structure_error(head)
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
