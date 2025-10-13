#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fixer für *legacy* Markdown-Dateien in wissen/content/**:
- Repariert Inline-Frontmatter wie:  --- title: ... slug: ... beschreibung_md_de: | TEXT last_sync: ... ---
- Zerlegt den Header in echte Zeilen (ein key: pro Zeile)
- Behandelt Block-Scalar korrekt (beschreibung_md_*: |  … als Literal-Block)
- Quoted problematische Werte (':', '#', Leerzeichen etc.)
- Entfernt NBSP/ZWSP/Smart Quotes, normalisiert Tabs→Spaces, CRLF→LF, BOM
- Säubert Body (ersetzt „- - -“ durch „---“, entfernt stray-„---“ am Ende)
- Überspringt Dateien mit 'managed_by:' (Generator-Output)
- Schreibt IMMER UTF-8 (ohne BOM) und LF

Exit 0: alles ok/repariert
Exit 1: mindestens eine Datei blieb unparsebar (bitte manuell prüfen)
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple, Optional
import re, os, sys, unicodedata

# ruamel.yaml laden (bei Bedarf nachinstallieren)
try:
    from ruamel.yaml import YAML
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
    from ruamel.yaml.scalarstring import LiteralScalarString as LSS
except Exception:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "ruamel.yaml"])
    from ruamel.yaml import YAML
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
    from ruamel.yaml.scalarstring import LiteralScalarString as LSS

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "wissen" / "content"

# Normalisierungen von Problemzeichen
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

# Erster '---' (evtl. inline mit weiterem Text dahinter)
RE_OPENER_INLINE = re.compile(r'^\s*\ufeff?\s*---\s*(.*)$', re.UNICODE)
# Schließender '---' (Zeile nur mit ---)
RE_CLOSER_LINE   = re.compile(r'^\s*---\s*$', re.UNICODE)

# key: value Marker
KEY_RE = re.compile(r'([A-Za-z0-9_-]+)\s*:\s*', re.MULTILINE)

DESC_KEYS = {"beschreibung_md_de", "beschreibung_md_en"}

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

def split_frontmatter_allow_inline(t: str) -> Optional[Tuple[str, str, str]]:
    """
    Teilt Dokument in (before, header, body).
    Erlaubt erste Zeile:  '---'  ODER  '--- irgendwas' (Inline-Header).
    """
    t = t.lstrip("\ufeff")
    lines = t.split("\n")
    if not lines:
        return None
    m0 = RE_OPENER_INLINE.match(lines[0])
    if not m0:
        return None

    header_lines = []
    inline_rest = (m0.group(1) or "").strip()
    if inline_rest:
        header_lines.append(inline_rest)

    close_idx = -1
    for i in range(1, len(lines)):
        if RE_CLOSER_LINE.match(lines[i]):
            close_idx = i
            break
        header_lines.append(lines[i])

    if close_idx == -1:
        # Kein schließender Delimiter → kein valider Header
        return None

    header = "\n".join(header_lines)
    body = "\n".join(lines[close_idx + 1 :])
    return ("", header, body)

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
    Baut eine saubere YAML-Map:
    - Strings werden sicher single-quoted (SQS)
    - beschreibung_md_* werden als Literal-Block (LSS) abgelegt
    """
    clean = {}
    for k, raw in kv.items():
        s = normalize_text(raw)

        # Block-Scalar?
        # Fälle: "| TEXT", "|   TEXT", "|", dann Text …
        if k in DESC_KEYS:
            if s.startswith("|"):
                block = s[1:].strip()
            else:
                block = s
            clean[k] = LSS(block)
            continue

        # sonst normaler String → sicher quoten
        val = s.strip()
        if val == "- - -":
            val = "---"
        # viele Problemfälle (Doppelpunkt, Hash, Plus, Leerzeichen) → immer SQS
        clean[k] = SQS(val)
    return clean

def dump_yaml(obj:
