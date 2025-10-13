#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix legacy YAML formatting in wissen/content/**/*.md

Behebt typische Altbestands-Fehler (wie bei braun-beeck-standolinnenfarbe-pro):
- "Inline"-Frontmatter nach dem Opener:  --- title: ... slug: ...  → korrektes Mehrzeilen-Frontmatter
- Mehrere key: value in einer Zeile → echte Key-Zeilen
- Werte mit ':' / '#' / Tabs / NBSP / Smart Quotes → sicher single-quoted & normalisiert
- Block-Scalar in derselben Zeile (z. B. "beschreibung_md_*: | TEXT") → echter Literal-Block
- Zeilenenden: immer LF, Encoding: UTF-8 ohne BOM
- Body bleibt erhalten; offensichtliche Artefakte "- - -" → '---'
- Dateien mit 'managed_by:' (Generator) werden NICHT verändert

Exit 0: alles ok/behoben
Exit 1: einige Dateien blieben unparsbar (werden gelistet)
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, Optional, Tuple

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
from ruamel.yaml.scalarstring import LiteralScalarString as LSS

REPO = Path(__file__).resolve().parents[2]
CONTENT_ROOT = REPO / "wissen" / "content"

# Opener erlaubt Inline-Inhalt hinter '---'
RE_OPENER_INLINE = re.compile(r'^\s*\ufeff?\s*---\s*(.*)$', re.UNICODE)
RE_CLOSER_LINE   = re.compile(r'^\s*---\s*$', re.UNICODE)

# konservativ: 'key:' am Wortanfang oder nach Whitespace
KEY_RE = re.compile(r'(?<!\S)([A-Za-z0-9_-]{1,64})\s*:\s*')

REPLACEMENTS = {
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

ORDER = ["title", "slug", "type", "beschreibung_md_de", "beschreibung_md_en", "last_sync"]

# ---------------- IO ----------------
def read_text_any(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252")
    return t.replace("\r\n", "\n").replace("\r", "\n")

def write_text_utf8_lf(p: Path, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    p.write_text(text, encoding="utf-8", newline="\n")

def normalize_text(s: str) -> str:
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    s = s.expandtabs(2)
    s = unicodedata.normalize("NFC", s)
    return "\n".join(ln.rstrip() for ln in s.split("\n"))

# -------- Frontmatter split (mit Inline-Opener) --------
def split_frontmatter_allow_inline(t: str) -> Optional[Tuple[str, str, str]]:
    t = t.lstrip("\ufeff")
    lines = t.split("\n")
    if not lines:
        return None
    m0 = RE_OPENER_INLINE.match(lines[0])
    if not m0:
        return None
    first_rest = m0.group(1) or ""
    header_lines = []
    if first_rest.strip():
        header_lines.append(first_rest.strip())

    close_idx = -1
    for i in range(1, len(lines)):
        if RE_CLOSER_LINE.match(lines[i]):
            close_idx = i
            break
        header_lines.append(lines[i])
    if close_idx == -1:
        return None

    header = "\n".join(header_lines)
    body = "\n".join(lines[close_idx + 1 :])
    return ("", header, body)

# ---------------- YAML helpers ----------------
def try_yaml_parse(header: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        data = y.load(header) or {}
        return dict(data) if isinstance(data, dict) else None
    except Exception:
        return None

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

# --------------- Core Repair ---------------
def tokenize_flat_header(header: str) -> Dict[str, str]:
    """
    Schneidet 'flache' Header anhand der key:-Marker in key->raw_value auf.
    """
    items = list(KEY_RE.finditer(header))
    out: Dict[str, str] = {}
    for i, m in enumerate(items):
        key = m.group(1)
        start = m.end()
        end = items[i + 1].start() if i + 1 < len(items) else len(header)
        raw_val = header[start:end].strip()
        out[key] = raw_val
    return out

def sanitize_kv_map(kv: Dict[str, str]) -> dict:
    clean = {}
    for k, raw in kv.items():
        s = normalize_text(raw)

        # Block-Scalar direkt in der Zeile:  key: | TEXT
        if s.startswith("|"):
            block = s[1:].strip()
            clean[k] = LSS(block)
            continue

        val = s.strip()
        if val == "- - -":
            val = "---"
        # Immer sicher quoten (Doppelpunkt/Hash etc.)
        clean[k] = SQS(val)
    return clean

def order_mapping(m: dict) -> dict:
    ordered = {k: m[k] for k in ORDER if k in m}
    for k in m:
        if k not in ordered:
            ordered[k] = m[k]
    return ordered

def normalize_body(body: str) -> str:
    lines = body.split("\n")
    out = []
    for ln in lines:
        if ln.strip() == "- - -":
            out.append("---")
        else:
            out.append(ln.rstrip())
    return "\n".join(out).lstrip("\n")

def repair_file(p: Path) -> tuple[bool, bool]:
    """
    returns (changed, ok)
    """
    raw = read_text_any(p)
    parts = split_frontmatter_allow_inline(raw)
    if not parts:
        return (False, True)
    _, header, body = parts

    # Generator-Output nicht anfassen
    if "managed_by:" in header:
        return (False, True)

    header_norm = normalize_text(header)

    # Falls bereits parsebar: nur sauber serialisieren + Body normalisieren
    parsed = try_yaml_parse(header_norm)
    if parsed is not None:
        new_header = dump_yaml(order_mapping(parsed))
        new_body = normalize_body(body)
        new_text = f"---\n{new_header}\n---\n{new_body}"
        changed = (new_text != raw)
        if changed:
            write_text_utf8_lf(p, new_text)
        return (changed, True)

    # Nicht parsebar → flach zerlegen und neu bauen
    kv = tokenize_flat_header(header_norm)
    if not kv:
        # Minimaler Header, damit Hugo bauen kann
        new_header = dump_yaml({})
        new_body = normalize_body(body)
        write_text_utf8_lf(p, f"---\n{new_header}\n---\n{new_body}")
        return (True, True)

    clean_map = sanitize_kv_map(kv)
    new_header = dump_yaml(order_mapping(clean_map))
    if try_yaml_parse(new_header) is None:
        return (False, False)

    new_body = normalize_body(body)
    new_text = f"---\n{new_header}\n---\n{new_body}"
    if new_text != raw:
        write_text_utf8_lf(p, new_text)
        return (True, True)
    return (False, True)

def main() -> int:
    changed = 0
    bad = []
    for p in CONTENT_ROOT.rglob("*.md"):
        chg, ok = repair_file(p)
        if chg:
            changed += 1
        if not ok:
            bad.append(p)

    if bad:
        print("Unreparable legacy front matter in:", file=sys.stderr)
        for f in bad:
            print(" -", f.relative_to(REPO), file=sys.stderr)
        print(f"Files changed: {changed}", file=sys.stderr)
        return 1

    print(f"Legacy YAML formatting fixed. Files changed: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
