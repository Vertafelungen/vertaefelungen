#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Beautify/Normalize all FAQ Markdown in wissen/content/**/faq/**.

Neu:
- Entfernt Inline-Metazeilen im Body (z. B. '*** title: "…" slug: "…" … ***')
- H1 wird immer auf den Frontmatter-'title' gesetzt (wenn vorhanden)

Weiterhin:
- Clean/canonical title (Fallbacks, Kürzung ~80 Zeichen)
- Slug kurz (<=64) + passende url
- Body beginnt mit '# <Titel>' (ersetzen/insert)
- Inline ' ## ' -> echte Überschriften
- Smart Quotes / NBSP / ZWSP etc. normalisieren
- UTF-8 (ohne BOM), LF, genau eine Leerzeile nach Frontmatter
- Idempotent: schreibt nur bei echten Änderungen
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

def clamp_title(s: str, width: int = 80) -> str:
    s = s.strip()
    if len(s) <= width:
        return s
    cut = s[:width].rsplit(" ", 1)[0]
    return cut if cut else s[:width]

def derive_title(data_title: Optional[str], body: str) -> str:
    """
    Erzeuge einen brauchbaren Titel, falls Frontmatter 'title' fehlt.
    """
    h1 = first_h1(body)
    if h1:
        return clamp_title(h1)
    cand = (data_title or "").strip()
    if not cand:
        return ""
    cand = cand.split("##", 1)[0]
    cand = strip_inline_md(cand)
    return clamp_title(cand)

# ---------- body cleanup ----------
META_LINE_RE = re.compile(
    r"""^\s*
        \*{3}               # beginnt mit ***
        [^*]*               # irgendwas (keine weiteren *)
        (title:|slug:|kategorie:|tags:|erstellt_am:|sichtbar:|sprachversion:|beschreibung:)
        .*                  # Rest
        \*{3}\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

TRIPLE_META_START_RE = re.compile(r"^\s*\*{3}\s*(title:|slug:)", re.IGNORECASE)

def remove_inline_meta_lines(lines: List[str]) -> List[str]:
    """
    Entfernt Alt-Metazeilen, z. B.:
    *** title: "…" slug: "…" … ***
    oder Zeilen, die mit '*** title:' / '*** slug:' beginnen.
    """
    out: List[str] = []
    for ln in lines:
        s = ln.strip()
        if META_LINE_RE.match(s) or TRIPLE_META_START_RE.match(s):
            continue
        out.append(ln)
    return out

def beautify_body(body: str, final_title: str) -> str:
    """Normalize body, ensure H1(title), convert inline ' ## ' to headings."""
    b = norm(body)
    lines = b.split("\n")

    # 1) Inline-Metazeilen herausfiltern
    lines = remove_inline_meta_lines(lines)

    # 2) führende Leerzeilen entfernen
    while lines and not lines[0].strip():
        lines.pop(0)

    # 3) H1 setzen/ersetzen
    if lines and lines[0].strip().startswith("# "):
        lines[0] = f"# {final_title}"
    else:
        lines.insert(0, f"# {final_title}")

    b = "\n".join(lines)

    # 4) Inline ' ## ' -> echte Überschrift
    b = re.sub(r"\s+##\s+", "\n\n## ", b)

    # 5) Leerzeile vor Überschrift sicherstellen
    b = re.sub(r"\n(## )", r"\n\n\1", b)

    # 6) Max. 2 aufeinanderfolgende Leerzeilen
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
        # Wir erwarten in FAQ-Dateien Frontmatter (Repair/Seed sorgt dafür)
        return False

    data = yaml_parse(header) or {}

    # 1) effektiver Titel: wenn YAML 'title' vorhanden -> exakt diesen verwenden
    fm_title = data.get("title") if isinstance(data.get("title"), str) else ""
    if fm_title and fm_title.strip():
        title = clamp_title(strip_inline_md(fm_title))
    else:
        title = derive_title("", body)
        if not title:
            stem = p.parent.name if p.name == "index.md" else p.stem
            title = strip_inline_md(stem.replace("-", " ").replace("_", " ").strip())
        title = clamp_title(title)

    # 2) Body hübschen + H1 = title
    new_body = beautify_body(body, title)

    # 3) Pflichtfelder & Konsistenz
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
