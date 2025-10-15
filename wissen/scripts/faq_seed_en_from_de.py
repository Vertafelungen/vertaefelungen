#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seed English FAQ pages from German FAQ sources.

Scans:   wissen/content/de/faq/**/*.md
Creates: wissen/content/en/faq/** (mirrors DE structure) with clean front matter.

Goals
- Idempotent: skip existing EN files unless --force
- Clean front matter: ---/---, UTF-8 LF, ASCII-safe quotes
- Fields set: title (TODO: Translate …), slug (short), type=faq, lang=en,
              managed_by=faq, url (short), translationKey (stable)
- Short slugs: max 64 chars with 6-char hash suffix if truncated
- Safe defaults; never touches DE files

CLI
  --apply      actually write files (otherwise dry-run)
  --force      overwrite existing EN files
  --limit N    stop after creating N files (for testing)
  --verbose    print details

Exit codes
  0 success
  1 unexpected error
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import SingleQuotedScalarString as SQS
from slugify import slugify

# ----- repo paths -----
REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "wissen" / "content"
DE_FAQ = ROOT / "de" / "faq"
EN_FAQ = ROOT / "en" / "faq"

# ----- text normalization (ASCII-safe for quotes/dashes etc.) -----
REPLACEMENTS = {
    "\u00A0": " ",   # NBSP
    "\u202F": " ",   # NNBSP
    "\u200B": "",    # ZWSP
    "\u200C": "",    # ZWNJ
    "\u200D": "",    # ZWJ
    "\u2018": "'",   # ‘
    "\u2019": "'",   # ’
    "\u201C": '"',   # “
    "\u201D": '"',   # ”
    "\u2013": "-",   # –
    "\u2014": "-",   # —
    "\u2026": "...", # …
}

def norm(s: str) -> str:
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    s = s.expandtabs(2)
    s = unicodedata.normalize("NFC", s)
    return "\n".join(ln.rstrip() for ln in s.split("\n"))

# ----- io helpers -----
def read_any(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):  # strip UTF-8 BOM
        b = b[3:]
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252")
    return t.replace("\r\n", "\n").replace("\r", "\n")

def write_utf8_lf(p: Path, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")

# ----- front matter parsing (tolerant) -----
def split_fm(text: str) -> Tuple[bool, str, str]:
    """
    Returns (has_frontmatter, header_text, body_text).
    Accepts '---' opener on first line and '---' closer later.
    If not found, returns (False, "", fulltext as body).
    """
    t = text.lstrip("\ufeff")
    lines = t.split("\n")
    if not lines:
        return False, "", text
    if not lines[0].strip().startswith("---"):
        return False, "", text
    # collect header until next '---' line
    header_lines: List[str] = []
    close_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
        header_lines.append(lines[i])
    if close_idx == -1:
        return False, "", text
    header = "\n".join(header_lines)
    body = "\n".join(lines[close_idx + 1 :])
    return True, header, body

def yaml_load(header: str) -> Optional[dict]:
    y = YAML(typ="safe")
    try:
        data = y.load(header) or {}
        return dict(data) if isinstance(data, dict) else None
    except Exception:
        return None

def yaml_dump(data: dict) -> str:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 100000
    y.indent(mapping=2, sequence=2, offset=2)
    from io import StringIO
    buf = StringIO()
    y.dump(data, buf)
    return buf.getvalue().rstrip("\n")

# ----- content helpers -----
def first_h1(body: str) -> str:
    b = norm(body)
    for ln in b.split("\n"):
        s = ln.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("#\t") or s.startswith("#\u00A0"):
            return s[1:].strip()
    return ""

def short_slug(s: str, maxlen: int = 64) -> str:
    base = slugify(s) if s else ""
    if len(base) <= maxlen:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:6]
    keep = maxlen - 7
    return f"{base[:keep].rstrip('-')}-{digest}"

def en_target_path_for(de_file: Path) -> Path:
    rel = de_file.relative_to(DE_FAQ)  # e.g., themen/abc/index.md  OR themen/abc.md
    return EN_FAQ / rel

def build_url_from_rel(rel: Path, slug: str) -> str:
    """
    Build /faq/<subdirs>/<slug>/
    rel is a path relative to .../faq (may include subdirs and either index.md or a file.md)
    """
    parts = list(rel.parts)
    if parts and parts[-1].lower() == "index.md":
        parts = parts[:-1]
    elif parts:
        parts[-1] = slug
    else:
        parts = [slug]
    if not parts or parts[0] != "faq":  # ensure first segment is 'faq'
        parts.insert(0, "faq")
    return "/" + "/".join(parts) + "/"

def stable_translation_key(de_rel: Path) -> str:
    """
    Build a stable translation key from the DE relative path.
    Keeps it short but deterministic.
    """
    base = de_rel.as_posix()
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"faq:{digest}"

@dataclass
class SeedResult:
    created: int = 0
    skipped: int = 0
    overwritten: int = 0

# ----- main seeding logic -----
def seed_one(de_file: Path, apply: bool, force: bool, verbose: bool) -> Tuple[bool, str]:
    # read DE
    src = read_any(de_file)
    has_fm, header, body = split_fm(src)
    title_de = ""
    if has_fm:
        data = yaml_load(header) or {}
        if isinstance(data.get("title"), str) and data["title"].strip():
            title_de = data["title"].strip()
    if not title_de:
        title_de = first_h1(body)
    if not title_de:
        # filename-based fallback
        stem = de_file.parent.name if de_file.name == "index.md" else de_file.stem
        title_de = stem.replace("-", " ").replace("_", " ").strip()

    rel_de = de_file.relative_to(DE_FAQ)
    target = en_target_path_for(de_file)
    rel_en = target.relative_to(EN_FAQ)

    # derive slug/url/translationKey
    slug = short_slug(title_de, 64)
    url = build_url_from_rel(rel_en, slug)  # same structure under EN
    tkey = stable_translation_key(rel_de)

    # build clean FM
    fm = {
        "title": SQS(f"TODO: Translate: {title_de}"),
        "slug": SQS(slug),
        "type": SQS("faq"),
        "lang": SQS("en"),
        "managed_by": SQS("faq"),
        "url": SQS(url),
        "translationKey": SQS(tkey),
    }

    # seed body
    body_out = "\n".join([
        f"# TODO: Translate: {title_de}",
        "",
        "_This page was seeded from the German FAQ. Please translate the content below and keep the front matter as-is._",
        "",
    ])
    text = f"---\n{yaml_dump(fm)}\n---\n\n{body_out}\n"

    # write
    if target.exists() and not force:
        return False, f"skip (exists): {target.relative_to(REPO)}"
    if apply:
        write_utf8_lf(target, text)
    return True, f"{'write' if apply else 'would write'}: {target.relative_to(REPO)}"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write files (default is dry-run).")
    ap.add_argument("--force", action="store_true", help="Overwrite existing EN files.")
    ap.add_argument("--limit", type=int, default=0, help="Max number of files to create (0 = no limit).")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not DE_FAQ.exists():
        print(f"Nothing to do: {DE_FAQ} not found.")
        return 0

    created = 0
    skipped = 0
    msgs: List[str] = []

    for de_md in sorted(DE_FAQ.rglob("*.md")):
        # mirror only files under faq; ignore hidden/underscore templates
        rel = de_md.relative_to(DE_FAQ).as_posix()
        if "/_templates" in rel or rel.startswith("_"):
            continue

        ok, msg = seed_one(de_md, args.apply, args.force, args.verbose)
        msgs.append(msg)
        if ok:
            created += 1
        else:
            skipped += 1

        if args.limit and created >= args.limit:
            break

    # Step summary (if in GitHub Actions)
    summary = []
    summary.append("### EN FAQ seeding\n")
    summary.append(f"- Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    summary.append(f"- Created: **{created}**, Skipped: **{skipped}**\n")
    summary.append("<details><summary>Details</summary>\n\n")
    summary.extend(f"- {m}" for m in msgs)
    summary.append("\n</details>\n")

    print("\n".join(summary))
    step_summary = Path(os.environ.get("GITHUB_STEP_SUMMARY", "")) if "GITHUB_STEP_SUMMARY" in os.environ else None
    try:
        if step_summary:
            step_summary.write_text("\n".join(summary), encoding="utf-8")
    except Exception:
        pass

    return 0

if __name__ == "__main__":
    import os
    sys.exit(main())
