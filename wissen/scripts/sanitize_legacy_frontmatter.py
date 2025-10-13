#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sanitize legacy YAML frontmatter in wissen/content/**/*.md

- Greift NUR Dateien ohne 'managed_by:' (Generator-Outputs bleiben unberührt)
- Liest robust (UTF-8 bevorzugt, Fallback CP-1252), entfernt BOM, normalisiert CRLF→LF
- Räumt Steuer-/Typografiezeichen auf (NBSP/ZWSP/Smart Quotes/Tabs)
- Quoted problematische Werte (':', '#', multiple spaces etc.)
- Prüft/serialisiert YAML mit ruamel.yaml (wird notfalls on-the-fly installiert)
- Schreibt IMMER UTF-8 (ohne BOM) und LF

ENV:
  SANITIZE_APPLY=1  -> Änderungen schreiben (sonst nur Analyse)
"""

from __future__ import annotations
import os, sys, re, unicodedata
from pathlib import Path
from typing import Optional

# --- ruamel.yaml sicherstellen (lazy install, falls im Build-Job nicht vorinstalliert)
try:
    from ruamel.yaml import YAML
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
except Exception:  # pragma: no cover
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "ruamel.yaml"])
    from ruamel.yaml import YAML
    from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "wissen" / "content"

RE_OPEN = re.compile(r"(?m)^\s*---\s*$")
RE_CLOSE = re.compile(r"(?m)^\s*---\s*$")

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

def _read_text_any(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM
        b = b[3:]
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252")
    return t.replace("\r\n", "\n").replace("\r", "\n")

def _normalize_text(s: str) -> str:
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    s = s.expandtabs(2)
    s = unicodedata.normalize("NFC", s)
    return "\n".join(ln.rstrip() for ln in s.split("\n"))

def _split_frontmatter(t: str) -> Optional[tuple[str, str, str]]:
    m1 = RE_OPEN.search(t)
    if not m1 or m1.start() != 0:
        return None
    m2 = RE_CLOSE.search(t, m1.end())
    if not m2:
        return None
    header = t[m1.end():m2.start()]
    body = t[m2.end():]
    return ("", header, body)

def _quote_problem_lines(header: str) -> str:
    out = []
    for ln in header.split("\n"):
        raw = ln
        s = ln.strip()
        if not s or s.startswith(("#", "- ", "|", ">", "{", "[")):
            out.append(raw)
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", s)
        if not m:
            out.append(raw)
            continue
        key, val = m.group(1), m.group(2)
        if val == "":
            out.append(f"{key}: ''")
            continue
        if val.startswith(("'", '"', "{", "[", "|", ">", "*", "&")) or val.isdigit():
            out.append(raw)
            continue
        # Problemzeichen? -> sicher single-quoten
        if (":" in val) or ("#" in val) or ("\t" in val) or ("  " in val):
            val2 = val.strip().replace("'", "''")
            out.append(f"{key}: '{val2}'")
        else:
            out.append(raw)
    return "\n".join(out)

def _dump_yaml_clean(data: dict) -> str:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 100000
    y.indent(mapping=2, sequence=2, offset=2)
    from io import StringIO
    buf = StringIO()
    y.dump(data, buf)
    return buf.getvalue().rstrip("\n")

def _try_parse(header: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        d = y.load(header) or {}
        return dict(d) if isinstance(d, dict) else None
    except Exception:
        return None

def sanitize_file(p: Path, apply: bool) -> tuple[bool, bool]:
    raw = _read_text_any(p)
    parts = _split_frontmatter(raw)
    if not parts:
        return (False, True)
    _, header, body = parts

    # Generator-Outputs ausnehmen
    if "managed_by:" in header:
        return (False, True)

    # Normalize & heuristisch quoten
    h1 = _normalize_text(header)
    if _try_parse(h1) is None:
        h2 = _quote_problem_lines(h1)
    else:
        h2 = h1

    data = _try_parse(h2)
    if data is None:
        # Notfall: minimaler Header (title extrahieren, Rest ignorieren)
        title = ""
        m = re.search(r"(?mi)^\s*title\s*:\s*(.+)$", h2)
        if m:
            title = m.group(1).strip().strip("'").strip('"')
        data = {}
        if title:
            data["title"] = SQS(title)

    new_header = _dump_yaml_clean(data)
    new_text = f"---\n{new_header}\n---\n{body.lstrip()}"
    changed = (new_text != raw)

    if apply and changed:
        p.write_text(new_text, encoding="utf-8", newline="\n")

    # finaler Parse-Check
    ok = _try_parse(new_header) is not None
    return (changed, ok)

def main() -> int:
    apply = os.environ.get("SANITIZE_APPLY", "").lower() in {"1", "true", "yes"}
    changed = 0
    bad = []

    for p in ROOT.rglob("*.md"):
        chg, ok = sanitize_file(p, apply)
        if chg:
            changed += 1
        if not ok:
            bad.append(p)

    if bad:
        print("Sanitizer: YAML weiterhin ungültig in:", file=sys.stderr)
        for pp in bad:
            print(" -", pp.relative_to(REPO), file=sys.stderr)
        print(f"Geänderte Dateien: {changed}", file=sys.stderr)
        return 1

    print(f"Sanitizer OK. Dateien geändert: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
