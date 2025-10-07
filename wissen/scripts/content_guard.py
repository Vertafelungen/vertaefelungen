#!/usr/bin/env python3
# Version: 2025-10-07
from __future__ import annotations
from pathlib import Path
import re, sys
import yaml  # pip install pyyaml

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

FM_RE = re.compile(r'^---\n(.*?\n)---\n(.*)$', re.S)

SCHEMAS = {
    "produkte": {
        "required": {"title","slug","type"},
        "recommended": {"kategorie","bilder","varianten","beschreibung_md_de","beschreibung_md_en","last_sync"},
    },
    "faq": {
        "required": {"title","slug","type"},
        "recommended": {"frage_md_de","antwort_md_de","frage_md_en","antwort_md_en","tags"},
    },
    "allgemeine-informationen": {
        "required": {"title","slug","type"},
        "recommended": set(),
    },
}

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="strict")

def parse_frontmatter(txt: str):
    m = FM_RE.match(txt)
    if not m:
        return None, None  # kein Frontmatter (zulässig für einfache Seiten)
    head, body = m.group(1), m.group(2)
    try:
        data = yaml.safe_load(head) or {}
        if not isinstance(data, dict):
            raise ValueError("Frontmatter ist kein Mapping (dict).")
        return data, body
    except Exception as e:
        raise RuntimeError(f"YAML-Fehler im Frontmatter: {e}")

def check_schema(p: Path, fm: dict):
    t = str(fm.get("type") or "").strip()
    if not t:
        raise RuntimeError("Frontmatter: Feld 'type' fehlt.")
    schema = SCHEMAS.get(t)
    if not schema:
        # unbekannter Typ ist ok, aber warnen
        return [f"Warnung: unbekannter type='{t}'"], []
    missing = [k for k in schema["required"] if k not in fm or fm[k] in ("", [], None)]
    warns   = []
    if missing:
        raise RuntimeError(f"Pflichtfelder fehlen: {', '.join(sorted(missing))}")
    # Leichte Zusatztchecks pro Typ
    if t == "produkte":
        if p.as_posix().startswith("wissen/content/de/oeffentlich/produkte/") and not fm.get("beschreibung_md_de"):
            warns.append("Empfehlung: 'beschreibung_md_de' fehlt für DE-Produkte.")
        if p.as_posix().startswith("wissen/content/en/public/products/") and not fm.get("beschreibung_md_en"):
            warns.append("Empfehlung: 'beschreibung_md_en' fehlt für EN-Produkte.")
        if "varianten" in fm and fm["varianten"] not in (None, "") and not isinstance(fm["varianten"], list):
            raise RuntimeError("'varianten' muss eine Liste sein.")
    return warns, []

def guard():
    errors, warns = [], []
    for p in CONTENT.rglob("*.md"):
        try:
            txt = read(p)
        except UnicodeDecodeError as e:
            errors.append(f"{p}: Datei ist nicht UTF-8: {e}")
            continue

        # Frontmatter vorhanden?
        m = FM_RE.match(txt)
        if not m:
            # Seiten ohne Frontmatter sind ok – aber nur warnen, wenn Datei im “Wissen”-Baum liegt
            continue

        # kein reiner Text im YAML-Kopf (fängt viele Fehler ab)
        for i, ln in enumerate(m.group(1).splitlines(), start=1):
            if ln.strip() and not re.match(r'^\s*[^:#\-\s][^:]*:\s*', ln) and not ln.strip().startswith("#"):
                errors.append(f"{p}:{i}: Textzeile im YAML-Head (kein 'key: value'): {ln[:50]!r}")
                break

        # YAML parse
        try:
            fm, body = parse_frontmatter(txt)
        except Exception as e:
            errors.append(f"{p}: {e}")
            continue
        if fm is None:
            continue

        # Schema
        w, _ = check_schema(p, fm)
        warns += [f"{p}: {msg}" for msg in w]

    return errors, warns

def main():
    strict = "--strict" in sys.argv
    errs, warns = guard()
    for w in warns: print(f"[WARN] {w}")
    if errs:
        for e in errs: print(f"[ERR] {e}", file=sys.stderr)
        return 2 if strict else 0
    print("Content-Guard: OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
