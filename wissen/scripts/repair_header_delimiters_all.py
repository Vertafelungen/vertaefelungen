#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repariert Frontmatter-Header in allen Markdown-Dateien unter wissen/content:
- Entfernt UTF-8 BOM / Zero-Width/NO-BREAK (U+FEFF, U+200B etc.) am Anfang
- Ersetzt führendes '***' durch '---'
- Ergänzt fehlende schließende '---' für YAML-Frontmatter
- Sorgt für eine Leerzeile nach geschlossenem Header
- Lässt Body-'---' (Horizontallinie) in Ruhe
Idempotent: mehrfach ausführbar ohne Doppeländerungen.
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]  # .../wissen
CONTENT_DIR = ROOT / "content"

# Zero-width / BOM am Anfang entfernen
LEADING_JUNK = re.compile(r"^\ufeff|\u200b|\u200c|\u200d|\u2060", re.UNICODE)

def sanitize_start(text: str) -> str:
    # Nur am Anfang störende Zeichen weg
    return LEADING_JUNK.sub("", text, count=1)

def fix_frontmatter(text: str):
    """
    Gibt (fixed_text, changed_bool) zurück.
    """
    changed = False
    original = text

    text = sanitize_start(text)

    # Falls Datei gar keinen potentiellen Header enthält, raus
    if not text.lstrip().startswith(("---", "***")):
        return original, False

    # Nur ganz am Anfang arbeiten
    # Ersetze evtl. führende *** durch ---
    if text.startswith("***"):
        text = "---" + text[3:]
        changed = True

    # Jetzt versuchen wir, den Header bis zur schließenden --- zu finden
    lines = text.splitlines(keepends=True)

    if not lines:
        return original, False

    if not lines[0].strip() == "---":
        # Es stand evtl. Whitespace davor; korrigieren
        # Wir normalisieren: erste nicht-leere Zeile muss '---' sein
        # Andernfalls: nicht unser Fall.
        first_nonempty = 0
        while first_nonempty < len(lines) and lines[first_nonempty].strip() == "":
            first_nonempty += 1
        if first_nonempty < len(lines) and lines[first_nonempty].strip() in ("---", "***"):
            if lines[first_nonempty].strip() == "***":
                lines[first_nonempty] = lines[first_nonempty].replace("***", "---")
            # Header an den Anfang ziehen
            header_line = lines.pop(first_nonempty)
            lines.insert(0, header_line)
            changed = True
        else:
            return original, changed

    # Suche nach abschließender ---
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break

    if close_idx is None:
        # Kein Abschluss gefunden → einfügen nach Headerblockende
        # Headerblockende heuristisch: bis erste Leerzeile oder bis eine Zeile nicht "key: value" wirkt.
        # Zur Sicherheit: Wir setzen den Abschluss direkt hinter der letzten Kopfzeile,
        # oder, falls Datei sehr kurz ist, auf Position 1.
        # Minimal robust: schließe nach max. 200 Kopfzeilen ab.
        max_scan = min(200, len(lines)-1)
        insert_pos = 1
        keylike = re.compile(r"^[A-Za-z0-9_\-\"']+\s*:\s*.*$")
        for i in range(1, max_scan):
            s = lines[i].strip()
            if s == "":  # leere Zeile signalisiert meist Ende
                insert_pos = i
                break
            if not keylike.match(s):
                insert_pos = i
                break
            insert_pos = i + 1
        lines.insert(insert_pos, "---\n")
        changed = True
        close_idx = insert_pos

    # Sicherstellen: Leerzeile nach schließender ---
    if close_idx + 1 < len(lines):
        if lines[close_idx + 1].strip() != "":
            lines.insert(close_idx + 1, "\n")
            changed = True

    fixed = "".join(lines)
    return (fixed, changed)

def main() -> int:
    changed_files = 0
    checked = 0
    for md in CONTENT_DIR.rglob("*.md"):
        try:
            txt = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Versuche mit 'utf-8-sig'
            txt = md.read_text(encoding="utf-8-sig")

        fixed, changed = fix_frontmatter(txt)
        checked += 1
        if changed:
            md.write_text(fixed, encoding="utf-8", newline="\n")
            changed_files += 1
            print(f"[FIX] {md}")

    print(f"\nChecked: {checked} files, fixed: {changed_files}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
