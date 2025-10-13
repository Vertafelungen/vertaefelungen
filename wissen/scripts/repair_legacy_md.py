#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repair legacy Markdown front matter (wissen/content/**/*.md).

Fixes (inspired by cases like 'braun-beeck-standolinnenfarbe-pro/index.md'):
- Inline front matter after opener:  --- title: ... slug: ...  → normalized to proper multi-line keys
- Values with ':' / '#' / tabs / NBSP / smart quotes → safely single-quoted and normalized
- Block scalars like 'beschreibung_md_*: | <text on same line>' → converted to proper literal blocks
- Robust IO: UTF-8 preferred with BOM removal, CP-1252 fallback; line endings forced to LF
- Leaves generator-managed files (containing 'managed_by:') untouched
- Keeps body content; lightly normalizes obvious '- - -' separators to '---'

Exit codes:
  0 = success
  1 = some files remained unparsable (print list)
"""
from __future__ import annotations

import re, sys, unicodedata
from pathlib import Path
from typing import Dict, Optional, Tuple

# ruamel.yaml for safe YAML re-serialization
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
from ruamel.yaml.scalarstring import LiteralScalarString as LSS

REPO = Path(__file__).resolve().parents[2]
CONTENT_ROOT = REPO / "wissen" / "content"

# Accept both "clean" opener and inline opener with content after '---'
RE_OPENER_INLINE = re.compile(r'^\s*\ufeff?\s*---\s*(.*)$', re.UNICODE)  # captures rest of line
RE_CLOSER_LINE   = re.compile(r'^\s*---\s*$', re.UNICODE)

# key pattern anywhere (start or whitespace before), conservative to avoid catching URLs
KEY_RE = re.compile(r'(?<!\S)([A-Za-z0-9_-]{1,64})\s*:\s*')

# Normalizations for legacy text
REPLACEMENTS = {
    "\u00A0": " ",    # NBSP
    "\u202F": " ",    # NNBSP
    "\u200B": "",     # ZWSP
    "\u200C": "", "\u200D": "",
    "\u2018": "'",    # ‘
    "\u2019": "'",    # ’
    "\u201C": '"',    # “
    "\u201D": '"',    # ”
    "\u2013": "-",    # –
    "\u2014": "-",    # —
    "\u2026": "...",  # …
}

ORDER = ["title", "slug", "type", "beschreibung_md_de", "beschreibung_md_en", "last_sync"]

# ---------- IO helpers ----------
def read_text_any(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):  # strip UTF-8 BOM
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
    # rstrip each line to avoid YAML trailing spaces issues
    return "\n".join(ln.rstrip() for ln in s.split("\n"))

# ---------- front matter splitting (allows inline opener) ----------
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
        # no closing delimiter (should be fixed earlier, but bail out)
        return None

    header = "\n".join(header_lines)
    body = "\n".join(lines[close_idx + 1 :])
    return ("", header, body)

# ---------- YAML helpers ----------
def try_yaml_parse(header: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        data = y.load(header) or {}
        return dict(data) if isinstance(data, dict) else None
    except Exception:
        return None

def dump_yaml_clean(data: dict) -> str:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 100000
    y.indent(mapping=2, sequence=2, offset=2)
    from io import StringIO
    buf = StringIO()
    y.dump(data, buf)
    return buf.getvalue().rstrip("\n")

# ---------- core repairing ----------
def tokenize_flat_header(header: str) -> Dict[str, str]:
    """
    Split a 'flattened' header into key->raw_value by cutting at occurrences of 'key:'.
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

        # Block scalar handling: "key: | <text on same line>"
        if s.startswith("|"):
            blk = s[1:].strip()
            clean[k] = LSS(blk)
            continue

        # otherwise, treat as string and safely quote (avoid YAML implicit typing & colon/hash issues)
        val = s.strip()
        if val == "- - -":
            val = "---"
        clean[k] = SQS(val)
    return clean

def order_mapping(m: dict) -> dict:
    ordered = {k: m[k] for k in ORDER if k in m}
    for k in m:
        if k not in ordered:
            ordered[k] = m[k]
    return ordered

def normalize_body(body: str) -> str:
    # Clean up common artifact lines like "- - -" (convert to HR or remove)
    lines = body.split("\n")
    out = []
    for ln in lines:
        if ln.strip() == "- - -":
            out.append("---")
        else:
            out.append(ln.rstrip())
    return "\n".join(out).lstrip("\n")

def repair_file(p: Path) -> Tuple[bool, bool]:
    """
    Returns (changed, ok)
    """
    raw = read_text_any(p)
    parts = split_frontmatter_allow_inline(raw)
    if not parts:
        return (False, True)
    _, header, body = parts

    # skip generator-managed files
    if "managed_by:" in header:
        return (False, True)

    # Already valid? parse check on normalized version
    header_norm = normalize_text(header)
    if try_yaml_parse(header_norm) is not None:
        # even if parseable, ensure clean serialization & normalized body
        data = try_yaml_parse(header_norm) or {}
        new_header = dump_yaml_clean(order_mapping(data))
        new_body = normalize_body(body)
        new_text = f"---\n{new_header}\n---\n{new_body}"
        changed = (new_text != raw)
        if changed:
            write_text_utf8_lf(p, new_text)
        return (changed, True)

    # Not parseable → flatten & rebuild
    kv = tokenize_flat_header(header_norm)
    if not kv:
        # give up with minimal header; keep body
        min_header = dump_yaml_clean({})
        new_text = f"---\n{min_header}\n---\n{normalize_body(body)}"
        write_text_utf8_lf(p, new_text)
        # minimal header is parseable
        return (True, True)

    clean = sanitize_kv_map(kv)
    new_header = dump_yaml_clean(order_mapping(clean))
    new_body = normalize_body(body)
    new_text = f"---\n{new_header}\n---\n{new_body}"

    # final parse guard
    if try_yaml_parse(new_header) is None:
        return (False, False)

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

    print(f"Legacy repair OK. Files changed: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
