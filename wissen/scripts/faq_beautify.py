#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Beautify/Normalize all FAQ Markdown in wissen/content/**/faq/**.

- Clean/canonical title (from first H1 if present, else derived from YAML title)
- Strip markdown artifacts from title, clamp ~80 chars
- Ensure body starts with "# <title>" (replace or insert)
- Turn inline " ## " into real headings on new lines
- Short slug (<=64) + matching url (stable)
- Normalize smart quotes / NBSP / ZWSP etc. (header + body)
- UTF-8 (no BOM), LF, exactly one blank line after frontmatter
- Idempotent: writes only on real change
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
from slugify import slugify

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "wissen" / "content"

RE_FAQ_PATH = re.compile(r"(^|/)faq(/|/.*)")

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

# ---------- IO & helpers ----------
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

def norm(s: str) -> str:
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    s = s.expandtabs(2)
    s = unicodedata.normalize("NFC", s)
    return "\n".join(ln.rstrip() for ln in s.split("\n"))

def strip_inline_md(text: str) -> str:
    """remove simple inline markdown from a one-line title candidate"""
    s = re.sub(r"[#*_`~]+", "", text)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def short_slug(s: str, maxlen: int = 64) -> str:
    base = slugify(s) if s else ""
    if len(base) <= maxlen:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:6]
    keep = maxlen - 7
    return f"{base[:keep].rstrip('-')}-{digest}"

def after_faq_parts(p: Path) -> List[str]:
    """return path parts after 'faq' segment"""
    parts = list(p.relative_to(ROOT).parts)
    if "faq" in parts:
        i = parts.index("faq")
        return parts[i+1:]
    return parts

def faq_url_for(p: Path, slug: str) -> str:
    parts = after_faq_parts(p)
    if parts and parts[-1].lower() == "index.md":
        parts = parts[:-1]
    if parts:
        parts[-1] = slug
    else:
        parts = [slug]
    return "/faq/" + "/".join(parts) + "/"

# ---------- frontmatter ----------
def split_frontmatter(t: str) -> Tuple[bool, str, str]:
    t = t.lstrip("\ufeff")
    lines = t.split("\n")
    if not lines or not lines[0].strip().startswith("---"):
        return False, "", t
    head: List[str] = []
    close = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
        head.append(lines[i])
    if close == -1:
        return False, "", t
    header = "\n".join(head)
    body = "\n".join(lines[close+1:])
    return True, header, body

def yaml_parse(h: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        d = y.load(h) or {}
        return dict(d) if isinstance(d, dict) else None
    except Exception:
        return None

def yaml_dump(d: dict) -> str:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 100000
    y.indent(mapping=2, sequence=2, offset=2)
    from io import StringIO
    buf = StringIO()
    y.dump(d, buf)
    return buf.getvalue().rstrip("\n")

def first_h1(body: str) -> str:
    b = norm(body)
    for ln in b.split("\n"):
        s = ln.strip()
        if s.startswith("# "):
            return strip_inline_md(s[2:])
    return ""

def derive_title(data_title: Optional[str], body: str) -> str:
    h1 = first_h1(body)
    if h1:
        return h1
    cand = (data_title or "").strip()
    if not cand:
        return ""
    # cut at inline headings like "## ..."
    cand = cand.split("##", 1)[0]
    cand = strip_inline_md(cand)
    # clamp ~80 chars on word boundary
    if len(cand) > 80:
        cut = cand[:80].rsplit(" ", 1)[0]
        cand = cut if cut else cand[:80]
    return cand

def beautify_body(body: str, title: str) -> str:
    """Normalize body, ensure H1(title), convert inline ' ## ' to headings."""
    b = norm(body)

    lines = b.split("\n")
    # remove leading empty lines
    while lines and not lines[0].strip():
        lines.pop(0)

    # replace or insert H1
    if lines and lines[0].strip().startswith("# "):
        lines[0] = f"# {title}"
    else:
        lines.insert(0, f"# {title}")

    b = "\n".join(lines)

    # turn inline ' ## ' or '  ## ' into proper heading breaks
    b = re.sub(r"\s+##\s+", "\n\n## ", b)

    # ensure blank line before headings
    b = re.sub(r"\n(## )", r"\n\n\1", b)

    # clean stray duplicate empty lines (max 2)
    b = re.sub(r"\n{3,}", "\n\n", b)

    return b.lstrip("\n")

def order_mapping(m: dict) -> dict:
    order = ["title", "slug", "type", "lang", "managed_by", "url", "translationKey"]
    res = {k: m[k] for k in order if k in m}
    for k in m:
        if k not in res:
            res[k] = m[k]
    return res

# ---------- main normalize ----------
def normalize_file(p: Path) -> bool:
    raw = read_text_any(p)
    has, header, body = split_frontmatter(raw)
    if not has:
        # nothing to do: we assume FAQ files already carry FM (created by our other scripts)
        return False

    data = yaml_parse(header) or {}
    # derive canonical title
    data_title = data.get("title") if isinstance(data.get("title"), str) else ""
    title = derive_title(data_title, body)
    if not title:
        # fallback from filename
        stem = p.parent.name if p.name == "index.md" else p.stem
        title = strip_inline_md(stem.replace("-", " ").replace("_", " ").strip())

    # new body with proper H1 and headings
    new_body = beautify_body(body, title)

    # adjust slug/url if title changed or slug missing
    lang = data.get("lang") or ("de" if "content/de/" in str(p) else "en")
    data["lang"] = SQS(str(lang))
    data["type"] = SQS("faq")
    data["managed_by"] = SQS("faq")

    data["title"] = SQS(title)
    new_slug = short_slug(title, 64)
    data["slug"] = SQS(new_slug)
    data["url"] = SQS(faq_url_for(p, new_slug))

    new_header = yaml_dump(order_mapping(data))
    new = f"---\n{new_header}\n---\n\n{new_body}"
    if new != raw:
        write_text_utf8_lf(p, new)
        return True
    return False

def main() -> int:
    changed = 0
    for md in ROOT.rglob("*.md"):
        rel = md.relative_to(ROOT).as_posix()
        if not RE_FAQ_PATH.search(rel):
            continue
        if normalize_file(md):
            changed += 1
    print(f"FAQ beautify complete. Files changed: {changed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
