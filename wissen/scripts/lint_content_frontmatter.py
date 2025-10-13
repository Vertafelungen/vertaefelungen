#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lint & (optional) Auto-Fix für ungeschlossenes YAML-Frontmatter in Markdown-Dateien.

- Prüft alle wissen/content/**/*.md
- Wenn Datei mit '---' startet, muss ein zweites '---' folgen.
- Auto-Fix (AUTOFIX_FRONTMATTER=1): schließt das Frontmatter an der plausiblen Stelle,
  konvertiert Zeilenenden zu LF und schreibt UTF-8 (ohne BOM).

Exit:
  0 = OK (oder alle Probleme automatisch behoben)
  1 = Probleme gefunden (ohne Auto-Fix)
"""
from __future__ import annotations
from pathlib import Path
import os, sys, re

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIR = REPO_ROOT / "wissen" / "content"

YAML_KEY_RE = re.compile(r'^\s*[A-Za-z0-9_-]+\s*:\s*')   # title: '...'
YAML_LIST_RE = re.compile(r'^\s*-\s+')                   # - item
FENCE_RE = re.compile(r'^\s*```')                        # Code-Fence -> sicher Content

def is_yamlish(line: str) -> bool:
    s = line.rstrip("\n")
    if s.strip() == "":                 # leer erlaubt
        return True
    if s.strip().startswith("#"):       # YAML-Kommentar
        return True
    if YAML_KEY_RE.match(s):
        return True
    if YAML_LIST_RE.match(s):
        return True
    return False

def detect_insert_index(lines: list[str]) -> int:
    """
    Annahme: lines[0] == '---' (ohne CR).
    Rückgabe: Index, NACH dem das schließende '---' eingefügt werden soll.
    """
    # starte bei Zeile 1, sammle YAML-ähnliche Zeilen
    for i in range(1, len(lines)):
        L = lines[i]
        if L.strip() == "---":
            # Falls doch vorhanden -> wäre eigentlich kein Fix nötig,
            # wird aber an anderer Stelle abgefangen.
            return i
        if is_yamlish(L):
            continue
        # erste Content-Zeile -> schließe Frontmatter VOR dieser Zeile
        return i - 1
    # nur YAML-ähnliche Zeilen bis EOF -> schließe am Dateiende
    return len(lines) - 1

def normalize_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")

def needs_fix(text: str) -> bool:
    if not text.startswith("---"):
        return False
    # existiert bereits ein schließendes '---'?
    pos = text.find("\n---\n", 3)
    return pos == -1

def fix_text(text: str) -> str:
    t = normalize_lf(text)
    lines = t.split("\n")
    if not lines or lines[0].strip() != "---":
        return t
    insert_after = detect_insert_index(lines)
    # baue neu: Zeile0 '---', dann bis insert_after inkl., dann '---', dann Rest
    new_lines = []
    new_lines.append("---")
    new_lines.extend(lines[1:insert_after+1])
    new_lines.append("---")
    new_lines.extend(lines[insert_after+1:])
    # trailing newline sicherstellen
    out = "\n".join(l.rstrip("\n") for l in new_lines)
    if not out.endswith("\n"):
        out += "\n"
    return out

def main() -> int:
    autofix = os.environ.get("AUTOFIX_FRONTMATTER", "").strip().lower() in {"1","true","yes"}
    bad: list[Path] = []

    for p in CONTENT_DIR.rglob("*.md"):
        try:
            raw = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # wir lassen Hugo später stolpern; hier nicht blockieren
            continue

        if needs_fix(raw):
            if autofix:
                fixed = fix_text(raw)
                # Wenn sich wirklich etwas ändert, schreiben
                if fixed != raw:
                    p.write_text(fixed, encoding="utf-8", newline="\n")
            else:
                bad.append(p)

    if bad:
        print("Frontmatter-Lint: ungeschlossenes '---' in folgenden Dateien:", file=sys.stderr)
        for f in sorted(bad):
            print(" -", f.relative_to(REPO_ROOT), file=sys.stderr)
        print("Tipp: Setze AUTOFIX_FRONTMATTER=1, um automatisch zu reparieren.", file=sys.stderr)
        return 1

    print("Frontmatter-Lint OK.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
