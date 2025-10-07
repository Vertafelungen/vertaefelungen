#!/usr/bin/env python3
# Version: 2025-10-07 (tolerant für allgemeine Seiten, strikt für Produkte/FAQ)
from __future__ import annotations
from pathlib import Path
import re, sys
import yaml  # pip install pyyaml

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

FM_RE = re.compile(r'^---\n(.*?\n)---\n(.*)$', re.S)

# bekannte Schemas
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
        "required": {"title","slug"},   # 'type' wird nicht erzwungen
        "recommended": set(),
    },
}

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="strict")

def parse_frontmatter(txt: str):
    m = FM_RE.match(txt)
    if not m:
        return None, None  # kein Frontmatter
    head, body = m.group(1), m.group(2)
    data = yaml.safe_load(head) or {}
    if not isinstance(data, dict):
        raise RuntimeError("YAML-Frontmatter ist kein Mapping (dict).")
    return data, body

def guess_type_by_path(p: Path) -> str | None:
    s = p.as_posix()
    if "/de/oeffentlich/produkte/" in s or "/en/public/products/" in s:
        return "produkte"
    if "/faq/" in s:
        return "faq"
    if "/allgemeine-informationen/" in s:
        return "allgemeine-informationen"
    return None

def keyline_errors(front_head: str) -> list[str]:
    # „Text im YAML-Kopf“ (kein "key:") früh erkennen
    errs = []
    for i, ln in enumerate(front_head.splitlines(), start=1):
        if ln.strip() == "" or ln.strip().startswith("#"):
            continue
        if re.match(r'^\s*[^:#\-\s][^:]*:\s*(\|[+-]?|\>|\s*[^#].*)?$', ln):
            continue
        errs.append(f"Textzeile im Frontmatter (kein 'key: value'): Zeile {i}: {ln[:60]!r}")
        break
    return errs

def check_schema(p: Path, fm: dict, strict: bool):
    # type lesen/normalisieren/erraten
    t = (fm.get("type") or fm.get("Type") or "").strip()
    t = t.lower() if t else ""
    if not t:
        t = guess_type_by_path(p) or ""

    warns, errs = [], []

    # Regeln:
    # - Produkte/FAQ: **immer strikt** (müssen Pflichtfelder haben; wenn Pfade danach aussehen,
    #   ist fehlender 'type' ebenfalls ein Fehler).
    # - allgemeine-informationen: nur warnen, wenn 'type' fehlt; Pflicht: title+slug.
    # - andere Seiten: nie Fehler wegen fehlendem 'type' (nur Warnung).

    implied = guess_type_by_path(p)
    if implied in ("produkte", "faq") and (fm.get("type","").lower() != implied):
        if strict:
            errs.append(f"Erwarte type='{implied}' (oder setze ihn explizit) für Datei im {implied}-Pfad.")
        else:
            warns.append(f"Empfehlung: type='{implied}' setzen.")
        # für die weitere Prüfung nehmen wir implied
        t = implied or t

    schema = SCHEMAS.get(t) if t else None
    if schema:
        # Pflichtfelder prüfen (bei allgemeine-informationen ohne 'type' trotzdem nur warnend)
        missing = [k for k in schema["required"] if not fm.get(k)]
        if missing:
            if strict and t in ("produkte","faq"):
                errs.append(f"Pflichtfelder fehlen: {', '.join(sorted(missing))}")
            else:
                warns.append(f"Empfehlung: fehlende Felder: {', '.join(sorted(missing))}")
        # Typ-spezifische Checks
        if t == "produkte":
            var = fm.get("varianten")
            if var not in (None, "") and not isinstance(var, list):
                errs.append("'varianten' muss eine Liste sein.")
    else:
        # unbekannter Typ oder keiner gesetzt
        if strict and implied in ("produkte","faq"):
            errs.append("Frontmatter: Feld 'type' fehlt.")
        elif not t:
            warns.append("Frontmatter: Feld 'type' fehlt (allgemeine Seite oder unbekannter Bereich).")

    return warns, errs

def guard(strict: bool):
    errors, warns = [], []
    for p in CONTENT.rglob("*.md"):
        txt = read(p)

        # Frontmatter vorhanden?
        m = FM_RE.match(txt)
        if not m:
            continue

        # Keine reinen Textzeilen im YAML-Kopf
        kerrs = keyline_errors(m.group(1))
        if kerrs:
            errors.append(f"{p}: {kerrs[0]}")
            continue

        try:
            fm, body = parse_frontmatter(txt)
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
