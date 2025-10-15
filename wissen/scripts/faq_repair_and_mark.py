#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Force-Repair für alle FAQ-Markdown-Dateien unter wissen/content/**/faq/**.

Leistet:
- BOM/CRLF entfernen, tolerant lesen (UTF-8/CP-1252)
- falsche/fehlende Frontmatter-Delimiter (***, ___, —, etc.) -> korrektes '---/---'
- Inline-Header (--- key: val ...) entflachen
- Header & Body normalisieren (Smart Quotes, NBSP, ZWSP, en-dash etc.)
- Pflichtfelder setzen: managed_by: faq, type: faq, lang, title, slug (kurz), url (kurz)
- Artefakte '- - -' -> '---'; exakt eine Leerzeile nach Header
- Schreiben: UTF-8 (ohne BOM), LF
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString as LSS
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
from slugify import slugify

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "wissen" / "content"

RE_FAQ_PATH = re.compile(r"(^|/)faq(/|/.*)")
RE_BAD_OPEN = re.compile(r'^\s*(\*\*\*|___|—|–––)\s*(.*)$')  # falscher Delimiter am Anfang
RE_OPEN = re.compile(r'^\s*\ufeff?\s*---\s*(.*)$')           # erlaubt Inline-Reste
RE_CLOSE = re.compile(r'^\s*---\s*$')
KEY_RE = re.compile(r'(?<!\S)([A-Za-z0-9_-]{1,64})\s*:\s*')

REPLACEMENTS = {
    "\u00A0": " ",  # NBSP
    "\u202F": " ",  # NNBSP
    "\u200B": "",   # ZWSP
    "\u200C": "",   # ZWNJ
    "\u200D": "",   # ZWJ
    "\u2018": "'",  # ‘
    "\u2019": "'",  # ’
    "\u201C": '"',  # “
    "\u201D": '"',  # ”
    "\u2013": "-",  # –
    "\u2014": "-",  # —
    "\u2026": "...",
}

ORDER = ["title", "slug", "type", "lang", "managed_by", "url"]

# ---------- IO ----------
def read_any(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252")
    return t.replace("\r\n", "\n").replace("\r", "\n")

def write_utf8_lf(p: Path, t: str) -> None:
    if not t.endswith("\n"):
        t += "\n"
    p.write_text(t, encoding="utf-8", newline="\n")

def norm(s: str) -> str:
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    s = s.expandtabs(2)
    s = unicodedata.normalize("NFC", s)
    return "\n".join(ln.rstrip() for ln in s.split("\n"))

# ---------- Frontmatter split (tolerant) ----------
def split_fm_allow_inline(t: str) -> Tuple[bool, str, str]:
    lines = t.lstrip("\ufeff").split("\n")

    if not lines:
        return False, "", t

    # 1) falscher Delimiter am Anfang -> so behandeln, als gäbe es KEIN FM
    if RE_BAD_OPEN.match(lines[0] or ""):
        return False, "", t

    m0 = RE_OPEN.match(lines[0] or "")
    if not m0:
        return False, "", t

    header_lines: List[str] = []
    rest = m0.group(1) or ""
    if rest.strip():
        header_lines.append(rest.strip())

    close_idx = -1
    for i in range(1, len(lines)):
        if RE_CLOSE.match(lines[i] or ""):
            close_idx = i
            break
        header_lines.append(lines[i])

    if close_idx == -1:
        # kein schließendes '---' -> behandeln als "kein FM"
        return False, "", t

    header = "\n".join(header_lines)
    body = "\n".join(lines[close_idx + 1 :])
    return True, header, body

# ---------- YAML helpers ----------
def yaml_parse(header: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        data = y.load(header) or {}
        return dict(data) if isinstance(data, dict) else None
    except Exception:
        return None

def yaml_dump(obj: dict) -> str:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 100000
    y.indent(mapping=2, sequence=2, offset=2)
    from io import StringIO
    buf = StringIO()
    y.dump(obj, buf)
    return buf.getvalue().rstrip("\n")

def tokenize_flat(header: str) -> Dict[str, str]:
    items = list(KEY_RE.finditer(header))
    out: Dict[str, str] = {}
    for i, m in enumerate(items):
        k = m.group(1)
        start = m.end()
        end = items[i + 1].start() if i + 1 < len(items) else len(header)
        out[k] = header[start:end].strip()
    return out

def sanitize_kv(kv: Dict[str, str]) -> dict:
    clean = {}
    for k, raw in kv.items():
        v = norm(raw).strip()
        if v.startswith("|"):
            clean[k] = LSS(v[1:].strip())
        else:
            if v == "- - -":
                v = "---"
            clean[k] = SQS(v)
    return clean

# ---------- Slug/URL ----------
def short_slug(s: str, maxlen: int = 64) -> str:
    base = slugify(s) if s else ""
    if len(base) <= maxlen:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:6]
    keep = maxlen - 7
    return f"{base[:keep].rstrip('-')}-{digest}"

def faq_url_for(p: Path, short: str) -> str:
    parts = list(p.relative_to(ROOT).parts)     # z. B. ['de','faq','themen','file.md'] oder ['de','faq','group','long','index.md']
    after_lang = parts[1:]
    if after_lang and after_lang[-1].lower() == "index.md":
        after_lang = after_lang[:-1]
    if after_lang:
        after_lang[-1] = short
    else:
        after_lang = [short]
    if not after_lang or after_lang[0] != "faq":
        after_lang.insert(0, "faq")
    return "/" + "/".join(after_lang) + "/"

# ---------- Header/Body ----------
def first_h1(body: str) -> str:
    b = norm(body)
    for ln in b.split("\n"):
        s = ln.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("#\t") or s.startswith("#\u00A0"):
            return s[1:].strip()
    return ""

def normalize_body(body: str) -> str:
    body = norm(body)
    out = []
    for ln in body.split("\n"):
        out.append("---" if ln.strip() == "- - -" else ln.rstrip())
    text = "\n".join(out).lstrip("\n")
    if text and not text.startswith("\n"):
        text = "\n" + text
    return text

def order_mapping(m: dict) -> dict:
    ordered = {k: m[k] for k in ORDER if k in m}
    for k in m:
        if k not in ordered:
            ordered[k] = m[k]
    return ordered

def ensure_core_fields(p: Path, data: dict, body: str) -> dict:
    data.setdefault("managed_by", SQS("faq"))
    data.setdefault("type", SQS("faq"))

    # lang
    parts = p.relative_to(ROOT).parts
    data.setdefault("lang", SQS(parts[0] if parts else "de"))

    # title
    if not data.get("title"):
        t = first_h1(body)
        if not t:
            stem = p.parent.name if p.name == "index.md" else p.stem
            t = stem.replace("-", " ").replace("_", " ").strip()
        data["title"] = SQS(t)

    # slug/url kurz
    short = short_slug(str(data.get("title", "")) or p.stem, 64)
    data["slug"] = SQS(short)
    data["url"] = SQS(faq_url_for(p, short))
    return data

# ---------- Repair ----------
def repair_file(p: Path) -> tuple[bool, bool]:
    raw = read_any(p)

    # Falls die Datei mit falschem Delimiter beginnt (***, ___, …), schreib neuen Header.
    lines = raw.split("\n")
    if lines and RE_BAD_OPEN.match(lines[0] or ""):
        has_fm = False
        header = ""
        body = "\n".join(lines[1:])
    else:
        has_fm, header, body = split_fm_allow_inline(raw)

    if not has_fm:
        new_body = normalize_body(body)
        data: dict = {}
        data = ensure_core_fields(p, data, new_body)
        new_header = yaml_dump(order_mapping(data))
        new = f"---\n{new_header}\n---{new_body}"
        if new != raw:
            write_utf8_lf(p, new)
            return True, True
        return False, True

    header_n = norm(header)
    parsed = yaml_parse(header_n)
    data = sanitize_kv(tokenize_flat(header_n)) if parsed is None else parsed

    new_body = normalize_body(body)
    data = ensure_core_fields(p, data, new_body)
    new_header = yaml_dump(order_mapping(data))
    if yaml_parse(new_header) is None:
        data = ensure_core_fields(p, {}, new_body)
        new_header = yaml_dump(order_mapping(data))

    new = f"---\n{new_header}\n---{new_body}"
    if new != raw:
        write_utf8_lf(p, new)
        return True, True
    return False, True

def main() -> int:
    changed = 0
    for md in ROOT.rglob("*.md"):
        rel = md.relative_to(ROOT).as_posix()
        if not RE_FAQ_PATH.search(rel):
            continue
        chg, ok = repair_file(md)
        if chg:
            changed += 1
        if not ok:
            print(f"warn: could not fully repair {md.relative_to(REPO)}")
    print(f"FAQ repair & mark done. Files changed: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
