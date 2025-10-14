#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAQ-Repair & Mark:
Repariert und markiert alle Markdown-Dateien unter wissen/content/**/faq/**.

Leistet:
- robustes Lesen (UTF-8 bevorzugt, Fallback CP-1252), BOM entfernen, CRLF->LF
- Frontmatter erkennen:
  * korrektes '---/---'
  * "Inline-Opener" wie:  --- title: ... slug: ...   (wird entflacht)
  * fehlender Header -> wird neu angelegt
- YAML sanitisieren:
  * unquotierte Werte mit ':' / '#' -> sicher single-quoten
  * Block-Scalar in derselben Zeile (z.B. "beschreibung: | TEXT") -> echter Literalblock
- Pflichtfelder setzen/ergänzen:
  * managed_by: 'faq'
  * type: 'faq'
  * lang: 'de' | 'en' (aus Pfad)
  * title: aus YAML oder erster H1 '# ...' oder Dateiname
  * slug: aus Titel (slugify) oder aus Pfad
- Body normalisieren:
  * '- - -' → '---'
  * nach Header genau eine Leerzeile
- Schreiben: UTF-8 (ohne BOM), LF

Nach der Reparatur sind die Dateien für Guard/Hugo valide und vor Prune geschützt.
"""
from __future__ import annotations
import re, unicodedata
from pathlib import Path
from typing import Optional, Tuple, Dict

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
from ruamel.yaml.scalarstring import LiteralScalarString as LSS
from slugify import slugify

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "wissen" / "content"

RE_FAQ_PATH = re.compile(r"(^|/)faq(/|/.*)")

RE_OPENER_INLINE = re.compile(r'^\s*\ufeff?\s*---\s*(.*)$', re.UNICODE)  # erfasst Rest der Zeile
RE_CLOSER_LINE   = re.compile(r'^\s*---\s*$', re.UNICODE)
KEY_RE = re.compile(r'(?<!\S)([A-Za-z0-9_-]{1,64})\s*:\s*')

REPLACEMENTS = {
    "\u00A0": " ",
    "\u202F": " ",
    "\u200B": "",
    "\u200C": "",
    "\u200D": "",
    "\u2018": "'",
    "\u2019": "'",
    "\u201C": '"',
    "\u201D": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
}

ORDER = ["title", "slug", "type", "lang", "managed_by"]

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

def split_frontmatter_allow_inline(t: str) -> Tuple[bool, str, str]:
    """returns (has_fm, header, body)."""
    t = t.lstrip("\ufeff")
    lines = t.split("\n")
    if not lines:
        return (False, "", t)
    m0 = RE_OPENER_INLINE.match(lines[0])
    if not m0:
        return (False, "", t)
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
        # fehlender closer -> wir behandeln als "kein FM" (neu schreiben)
        return (False, "", t)

    header = "\n".join(header_lines)
    body = "\n".join(lines[close_idx + 1 :])
    return (True, header, body)

def try_yaml_parse(header: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        d = y.load(header) or {}
        return dict(d) if isinstance(d, dict) else None
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

def tokenize_flat_header(header: str) -> Dict[str, str]:
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
        if s.startswith("|"):
            clean[k] = LSS(s[1:].strip())
            continue
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
    lines = body.split("\n")
    out = []
    for ln in lines:
        out.append("---" if ln.strip() == "- - -" else ln.rstrip())
    text = "\n".join(out).lstrip("\n")
    # exakt eine Leerzeile am Anfang des Bodys
    if text and not text.startswith("\n"):
        text = "\n" + text
    return text

def extract_lang_from_path(p: Path) -> str:
    # wissen/content/<lang>/...
    parts = p.relative_to(ROOT).parts
    return parts[0] if parts else "de"

def extract_title_from_body(body: str) -> str:
    for ln in body.split("\n"):
        s = ln.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("#\t") or s.startswith("#\u00A0"):
            return s[1:].strip()
    return ""

def ensure_core_fields(p: Path, data: dict, body: str) -> dict:
    # managed_by
    data.setdefault("managed_by", SQS("faq"))
    # type
    data.setdefault("type", SQS("faq"))
    # lang
    lang = data.get("lang")
    if not lang:
        data["lang"] = SQS(extract_lang_from_path(p))
    # title
    if not data.get("title"):
        t = extract_title_from_body(body)
        if not t:
            # Dateiname (ohne index.md)
            stem = p.parent.name if p.name == "index.md" else p.stem
            t = stem.replace("-", " ").replace("_", " ").strip()
        data["title"] = SQS(t)
    # slug
    if not data.get("slug"):
        data["slug"] = SQS(slugify(str(data.get("title", "")) or p.stem))
    return data

def repair_faq_file(p: Path) -> tuple[bool, bool]:
    raw = read_text_any(p)
    has_fm, header, body = split_frontmatter_allow_inline(raw)

    if not has_fm:
        # komplett neuer Header
        data: dict = {}
        data = ensure_core_fields(p, data, body)
        new_header = dump_yaml(order_mapping(data))
        new_body = normalize_body(body)
        write_text_utf8_lf(p, f"---\n{new_header}\n---{new_body}")
        return (True, True)

    # vorhandenes Frontmatter sanitisieren
    header_norm = normalize_text(header)
    parsed = try_yaml_parse(header_norm)

    if parsed is None:
        # flachen Header zerlegen & bauen
        kv = tokenize_flat_header(header_norm)
        data = sanitize_kv_map(kv) if kv else {}
    else:
        data = parsed

    data = ensure_core_fields(p, data, body)
    new_header = dump_yaml(order_mapping(data))
    if try_yaml_parse(new_header) is None:
        # Sollte praktisch nicht passieren – Minimalheader
        data = ensure_core_fields(p, {}, body)
        new_header = dump_yaml(order_mapping(data))

    new_body = normalize_body(body)
    new_text = f"---\n{new_header}\n---{new_body}"
    if new_text != raw:
        write_text_utf8_lf(p, new_text)
        return (True, True)
    return (False, True)

def main() -> int:
    changed = 0
    for md in ROOT.rglob("*.md"):
        rel = md.relative_to(ROOT).as_posix()
        if not RE_FAQ_PATH.search(rel):
            continue
        chg, ok = repair_faq_file(md)
        if chg:
            changed += 1
        if not ok:
            print(f"warn: could not fully repair {md.relative_to(REPO)}")
    print(f"FAQ repair & mark done. Files changed: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
