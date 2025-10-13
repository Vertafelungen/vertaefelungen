#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fixer für *legacy* Frontmatter:
- Repariert 'flache' Header wie:  --- title: ... slug: ... type: ... beschreibung_md_de: |  TEXT last_sync: ...
- Quoted problematische Werte (':' / '#'), normalisiert Steuerzeichen, baut Block-Scalar korrekt
- Überspringt Dateien mit 'managed_by:' (Generator-Output)
- Schreibt UTF-8 (ohne BOM), LF

Exit 0: alles ok/repariert, Exit 1: Dateien bleiben unparsebar (manuell prüfen)
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple, Optional
import re, os, sys, unicodedata

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
from ruamel.yaml.scalarstring import LiteralScalarString as LSS

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "wissen" / "content"

# Problemzeichen -> Normalisierung
REPL = {
    "\u00A0": " ",   # NBSP
    "\u202F": " ",   # NNBSP
    "\u200B": "",    # ZWSP
    "\u200C": "",
    "\u200D": "",
    "\u2018": "'",   # ‘
    "\u2019": "'",   # ’
    "\u201C": '"',   # “
    "\u201D": '"',   # ”
    "\u2013": "-",   # –
    "\u2014": "-",   # —
    "\u2026": "...", # …
}

KEY_RE = re.compile(r'([A-Za-z0-9_-]+)\s*:\s*', re.MULTILINE)
CLOSE_RE = re.compile(r'^\s*---\s*$', re.MULTILINE)

def read_text_any(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM
        b = b[3:]
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252")
    return t.replace("\r\n", "\n").replace("\r", "\n")

def normalize_text(s: str) -> str:
    for k, v in REPL.items():
        s = s.replace(k, v)
    s = s.expandtabs(2)
    s = unicodedata.normalize("NFC", s)
    return "\n".join(line.rstrip() for line in s.split("\n"))

def split_frontmatter(txt: str) -> Optional[Tuple[str, str, str]]:
    # erwartet öffnendes --- am Anfang
    if not txt.lstrip().startswith("---"):
        return None
    first_line_end = txt.find("\n")
    if first_line_end == -1:
        return None
    # suche schließendes '---' nach Zeile 1
    m = CLOSE_RE.search(txt, first_line_end + 1)
    if not m:
        return None
    header = txt[first_line_end+1:m.start()]
    body = txt[m.end():]
    before = txt[:0]
    return before, header, body

def try_parse_yaml(header: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        data = y.load(header) or {}
        return dict(data) if isinstance(data, dict) else None
    except Exception:
        return None

def tokenize_flat_header(header: str) -> Dict[str, str]:
    """
    Zerlegt eine 'flache' Header-Zeichenkette in key->value,
    indem zwischen aufeinanderfolgenden 'key:'-Vorkommen geschnitten wird.
    """
    items = list(KEY_RE.finditer(header))
    out: Dict[str, str] = {}
    for i, m in enumerate(items):
        key = m.group(1)
        start = m.end()
        end = items[i+1].start() if i+1 < len(items) else len(header)
        raw_val = header[start:end].strip()
        out[key] = raw_val
    return out

def sanitize_kv_map(kv: Dict[str, str]) -> dict:
    """
    Baut eine saubere YAML-Map mit SQS/LSS aus den rohen Werten.
    """
    clean = {}
    for k, raw in kv.items():
        s = normalize_text(raw)
        # Block-Scalar?
        if s.startswith("|"):
            # Alles nach dem ersten '|' wird als literal block übernommen
            block = s[1:].strip()
            clean[k] = LSS(block)
            continue

        # Standard-String -> sicher single-quoten
        val = s.strip()
        # häufige Trennfehler im Body in Header geraten: "- - -" -> zu '---' normalisieren
        if val == "- - -":
            val = "---"
        # zur Sicherheit immer quoten (vereinfacht Regeln ':' / '#'/ etc.)
        clean[k] = SQS(val)
    return clean

def dump_yaml(obj: dict) -> str:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 100000
    y.indent(mapping=2, sequence=2, offset=2)
    from io import StringIO
    buf = StringIO()
    y.dump(obj, buf)
    return buf.getvalue().rstrip("\n")

def fix_file(p: Path) -> Tuple[bool, bool]:
    """
    returns (changed, ok)
    """
    txt = read_text_any(p)
    parts = split_frontmatter(txt)
    if not parts:
        return (False, True)
    _, header, body = parts

    # Generator-Outputs nicht anfassen
    if "managed_by:" in header:
        return (False, True)

    header_norm = normalize_text(header)
    if try_parse_yaml(header_norm) is not None:
        # parsebar -> nichts zu tun
        return (False, True)

    # flachen Header zerlegen
    kv = tokenize_flat_header(header_norm)
    if not kv:
        # Keine Schlüssel erkennbar -> minimaler Header
        new_header = "title: ''"
    else:
        clean = sanitize_kv_map(kv)
        # einzelne bekannte Felder optional sortieren
        order = ["title", "slug", "type", "last_sync", "beschreibung_md_de", "beschreibung_md_en"]
        ordered = {k: clean[k] for k in order if k in clean}
        for k in clean:
            if k not in ordered:
                ordered[k] = clean[k]
        new_header = dump_yaml(ordered)

    new_txt = f"---\n{new_header}\n---\n{body.lstrip()}"
    ok = try_parse_yaml(new_header) is not None
    if ok and new_txt != txt:
        p.write_text(new_txt, encoding="utf-8", newline="\n")
        return (True, True)
    return (False, ok)

def main() -> int:
    changed = 0
    bad = []
    for p in CONTENT.rglob("*.md"):
        chg, ok = fix_file(p)
        if chg:
            changed += 1
        if not ok:
            bad.append(p)

    if bad:
        print("Nicht reparierbar (bitte manuell prüfen):", file=sys.stderr)
        for b in bad:
            print(" -", b.relative_to(REPO), file=sys.stderr)
        print(f"Geänderte Dateien: {changed}", file=sys.stderr)
        return 1

    print(f"Legacy-Header repariert. Geänderte Dateien: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
