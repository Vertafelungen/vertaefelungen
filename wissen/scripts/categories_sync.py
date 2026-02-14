#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/scripts/categories_sync.py
Version: 2026-02-14 18:40 Europe/Berlin

Kategorien-Generator: categories.csv → Hugo Branch Bundles (_index.md)

Ziel
----
- Erzeugt/aktualisiert ausschließlich Kategorie-Seiten als Hugo Branch Bundles:
    wissen/content/de/<path_de>/_index.md
    wissen/content/en/<path_en>/_index.md
- Quelle der Wahrheit: wissen/ssot/categories.csv
- Schreibt ein einheitliches Frontmatter-Schema (translationKey, cascade, seo-Block),
  sodass Templates (Navigation, Breadcrumbs, ItemList/JSON-LD) deterministisch darauf aufbauen können.
- Der Body wird deterministisch aus den (optionalen) Abschnittsspalten body_{lang}_* gebaut.
  Legacy-Fallback: body_md_de / body_md_en (vollständiger Body als Markdown).

Sicherheitsregel
----------------
- Der Generator ist authoritative owner für die in categories.csv gelisteten _index.md:
  Er überschreibt diese Dateien deterministisch (Frontmatter + Body).
- Dateien außerhalb der in categories.csv gelisteten Pfade werden nicht verändert.
- Optionales Pruning (--prune): Entfernt _index.md, die managed_by == "categories.csv" haben,
  aber nicht mehr in categories.csv vorkommen (nur unter den übergebenen Roots).

CSV-Schema (Minimum, tolerant)
------------------------------
Erwartete Spalten (case-insensitiv; '-' und Leerzeichen werden toleriert):
- key                              (translationKey)
- path_de, path_en                 (Alias: export_pfad_de, export_pfad_en)
- title_de, title_en
- description_de, description_en
- meta_title_de, meta_title_en
- meta_description_de, meta_description_en
- weight
- parent_key
- type
- robots
- hero_image
- canonical_de, canonical_en
- is_public

Body-Optionen:
A) Abschnittsspalten (empfohlen; Schema-konform, ohne FAQ):
- body_de_kurzantwort
- body_de_praxis
- body_de_varianten
- body_de_ablauf
- body_de_kosten
- body_de_fehler
- body_de_verweise
- body_en_* analog

B) Legacy-Fallback:
- body_md_de, body_md_en (vollständiger Body)

FAQ:
- Wird NICHT hier generiert. FAQ wird nachgelagert durch faq_sync.py aus wissen/ssot/faq.csv injiziert.

Exit-Codes
----------
0 = OK
2 = CSV/IO/Validation error
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ruamel.yaml import YAML

MANAGED_BY = "categories.csv"

yaml = YAML()
yaml.default_flow_style = False
yaml.allow_unicode = True
yaml.width = 4096


def _normkey(k: str) -> str:
    s = (k or "").strip()
    s = s.replace("\ufeff", "")
    s = s.strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"_+", "_", s)
    return s


def clean(s: Optional[str]) -> str:
    return (s or "").strip()


def parse_bool(v: str) -> bool:
    s = clean(v).lower()
    return s in {"1", "true", "yes", "y", "ja", "wahr", "public", "published"}


def parse_int(v: str, default: int = 100) -> int:
    s = clean(v)
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def read_csv_utf8_auto(path: Path) -> List[Dict[str, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;|\t")
        delim = dialect.delimiter
    except Exception:
        delim = ","
    rows = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    norm = [{_normkey(k): ("" if v is None else v) for k, v in r.items()} for r in rows]
    return norm


def read_frontmatter_and_body(p: Path) -> Tuple[Dict, str]:
    if not p.exists():
        return {}, ""
    txt = p.read_text(encoding="utf-8", errors="replace")
    if txt.startswith("---"):
        parts = txt.split("\n---", 1)
        if len(parts) == 2:
            fm_raw = parts[0][3:]
            body = parts[1].lstrip("\n")
            try:
                fm = yaml.load(fm_raw) or {}
                if not isinstance(fm, dict):
                    fm = {}
            except Exception:
                fm = {}
            return fm, body
    return {}, txt


def dump_frontmatter(fm: Dict) -> str:
    buf = io.StringIO()
    yaml.dump(fm, buf)
    return "---\n" + buf.getvalue().strip() + "\n---\n"


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def canonicalize_robots(robots: str, is_public: bool) -> str:
    if not is_public:
        return "noindex,follow"
    r = clean(robots) or "index,follow"
    r = ",".join([x.strip().lower() for x in r.split(",") if x.strip()])
    return r or "index,follow"


def rewrite_internal_links(text: str) -> str:
    """
    Enforce rule: no /wissen/... links inside Markdown content.
    - https://www.vertaefelungen.de/wissen/de/... -> /de/...
    - /wissen/de/... -> /de/...
    Same for EN.
    """
    if not text:
        return text
    t = text
    t = re.sub(r"https?://www\.vertaefelungen\.de/wissen/de/", "/de/", t, flags=re.IGNORECASE)
    t = re.sub(r"https?://www\.vertaefelungen\.de/wissen/en/", "/en/", t, flags=re.IGNORECASE)
    t = t.replace("](/wissen/de/", "](/de/").replace("](/wissen/en/", "](/en/")
    t = t.replace("(/wissen/de/", "(/de/").replace("(/wissen/en/", "(/en/")
    t = t.replace("/wissen/de/", "/de/").replace("/wissen/en/", "/en/")
    return t


def _coalesce(r: Dict[str, str], *keys: str) -> str:
    for k in keys:
        v = clean(r.get(k))
        if v:
            return v
    return ""


@dataclass
class CategoryRow:
    key: str
    path_de: str
    path_en: str
    title_de: str
    title_en: str
    description_de: str
    description_en: str

    # Legacy full body
    body_md_de: str
    body_md_en: str

    # New structured body fields (without FAQ)
    body_de_kurzantwort: str
    body_de_praxis: str
    body_de_varianten: str
    body_de_ablauf: str
    body_de_kosten: str
    body_de_fehler: str
    body_de_verweise: str

    body_en_kurzantwort: str
    body_en_praxis: str
    body_en_varianten: str
    body_en_ablauf: str
    body_en_kosten: str
    body_en_fehler: str
    body_en_verweise: str

    meta_title_de: str
    meta_title_en: str
    meta_description_de: str
    meta_description_en: str
    weight: int
    parent_key: str
    type_: str
    robots: str
    hero_image: str
    canonical_de: str
    canonical_en: str
    is_public: bool
    menu_main_name_de: str
    menu_main_name_en: str
    menu_main_weight: int
    menu_main_identifier: str


def row_to_category(r: Dict[str, str]) -> CategoryRow:
    path_de = _coalesce(r, "path_de", "export_pfad_de")
    path_en = _coalesce(r, "path_en", "export_pfad_en")
    weight = parse_int(r.get("weight"), default=100)

    return CategoryRow(
        key=clean(r.get("key")),
        path_de=path_de.strip("/"),
        path_en=path_en.strip("/"),
        title_de=clean(r.get("title_de")),
        title_en=clean(r.get("title_en")),
        description_de=clean(r.get("description_de")),
        description_en=clean(r.get("description_en")),

        body_md_de=(r.get("body_md_de") or "").rstrip(),
        body_md_en=(r.get("body_md_en") or "").rstrip(),

        body_de_kurzantwort=(r.get("body_de_kurzantwort") or "").rstrip(),
        body_de_praxis=(r.get("body_de_praxis") or "").rstrip(),
        body_de_varianten=(r.get("body_de_varianten") or "").rstrip(),
        body_de_ablauf=(r.get("body_de_ablauf") or "").rstrip(),
        body_de_kosten=(r.get("body_de_kosten") or "").rstrip(),
        body_de_fehler=(r.get("body_de_fehler") or "").rstrip(),
        body_de_verweise=(r.get("body_de_verweise") or "").rstrip(),

        body_en_kurzantwort=(r.get("body_en_kurzantwort") or "").rstrip(),
        body_en_praxis=(r.get("body_en_praxis") or "").rstrip(),
        body_en_varianten=(r.get("body_en_varianten") or "").rstrip(),
        body_en_ablauf=(r.get("body_en_ablauf") or "").rstrip(),
        body_en_kosten=(r.get("body_en_kosten") or "").rstrip(),
        body_en_fehler=(r.get("body_en_fehler") or "").rstrip(),
        body_en_verweise=(r.get("body_en_verweise") or "").rstrip(),

        meta_title_de=clean(r.get("meta_title_de")),
        meta_title_en=clean(r.get("meta_title_en")),
        meta_description_de=clean(r.get("meta_description_de")),
        meta_description_en=clean(r.get("meta_description_en")),
        weight=weight,
        parent_key=clean(r.get("parent_key")),
        type_=(clean(r.get("type")) or "products"),
        robots=clean(r.get("robots")),
        hero_image=clean(r.get("hero_image")),
        canonical_de=clean(r.get("canonical_de")),
        canonical_en=clean(r.get("canonical_en")),
        is_public=parse_bool(r.get("is_public")),
        menu_main_name_de=clean(r.get("menu_main_name_de")),
        menu_main_name_en=clean(r.get("menu_main_name_en")),
        menu_main_weight=parse_int(r.get("menu_main_weight"), default=weight),
        menu_main_identifier=clean(r.get("menu_main_identifier")),
    )


def validate_categories(rows: List[CategoryRow]) -> List[str]:
    errs: List[str] = []
    seen_keys = set()
    seen_paths_de = set()
    seen_paths_en = set()

    for i, c in enumerate(rows, start=2):  # header line = 1
        if not c.key:
            errs.append(f"Line {i}: missing key")
        else:
            if c.key in seen_keys:
                errs.append(f"Line {i}: duplicate key: {c.key}")
            seen_keys.add(c.key)

        if not c.path_de:
            errs.append(f"Line {i}: missing path_de/export_pfad_de for key={c.key}")
        else:
            if c.path_de in seen_paths_de:
                errs.append(f"Line {i}: duplicate path_de: {c.path_de}")
            seen_paths_de.add(c.path_de)

        if not c.path_en:
            errs.append(f"Line {i}: missing path_en/export_pfad_en for key={c.key}")
        else:
            if c.path_en in seen_paths_en:
                errs.append(f"Line {i}: duplicate path_en: {c.path_en}")
            seen_paths_en.add(c.path_en)

        if not c.title_de:
            errs.append(f"Line {i}: missing title_de for key={c.key}")
        if not c.title_en:
            errs.append(f"Line {i}: missing title_en for key={c.key}")

        if not c.description_de:
            errs.append(f"Line {i}: missing description_de for key={c.key}")
        if not c.description_en:
            errs.append(f"Line {i}: missing description_en for key={c.key}")

    keys = {c.key for c in rows if c.key}
    for c in rows:
        if c.parent_key and c.parent_key not in keys:
            errs.append(f"key={c.key}: parent_key not found: {c.parent_key}")

    return errs


def _build_structured_body(c: CategoryRow, lang: str) -> str:
    """
    Deterministically build body without FAQ section.
    If legacy body_md_* exists, it takes precedence.
    """
    if lang == "de":
        legacy = c.body_md_de
        parts = [
            ("## Kurzantwort", c.body_de_kurzantwort),
            ("## Praxis-Kontext", c.body_de_praxis),
            ("## Entscheidung & Varianten", c.body_de_varianten),
            ("## Ablauf & Planung", c.body_de_ablauf),
            ("## Kostenlogik", c.body_de_kosten),
            ("## Häufige Fehler & Vermeidung", c.body_de_fehler),
            ("## Verweise", c.body_de_verweise),
        ]
    else:
        legacy = c.body_md_en
        parts = [
            ("## Quick answer", c.body_en_kurzantwort),
            ("## Practical context", c.body_en_praxis),
            ("## Decisions & variants", c.body_en_varianten),
            ("## Process & planning", c.body_en_ablauf),
            ("## Cost logic", c.body_en_kosten),
            ("## Common mistakes & how to avoid them", c.body_en_fehler),
            ("## References", c.body_en_verweise),
        ]

    if legacy and legacy.strip():
        return rewrite_internal_links(legacy.strip()) + "\n"

    any_new = any((v or "").strip() for _, v in parts)
    if not any_new:
        return ""

    out: List[str] = []
    for h, txt in parts:
        t = (txt or "").strip()
        if not t:
            continue
        out.append(h)
        out.append("")
        out.append(rewrite_internal_links(t))
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def build_frontmatter(c: CategoryRow, lang: str, now_utc: datetime) -> Tuple[Dict, str]:
    if lang == "de":
        title = c.title_de
        description = c.description_de
        meta_title = c.meta_title_de or c.title_de
        meta_desc = c.meta_description_de or c.description_de
        canonical = c.canonical_de
        menu_main_name = c.menu_main_name_de
    else:
        title = c.title_en
        description = c.description_en
        meta_title = c.meta_title_en or c.title_en
        meta_desc = c.meta_description_en or c.description_en
        canonical = c.canonical_en
        menu_main_name = c.menu_main_name_en

    robots = canonicalize_robots(c.robots, c.is_public)
    ts_utc = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    fm = {
        "version": ts_utc,
        "managed_by": MANAGED_BY,
        "last_synced": ts_utc,
        "lastmod": ts_utc,

        "lang": lang,
        "translationKey": c.key,

        "title": title,
        "description": description,
        "weight": int(c.weight),
        "type": c.type_,

        "seo": {
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "robots": robots,
            "canonical": canonical or "",
            "og_image": c.hero_image or "",
            "is_public": bool(c.is_public),
        },

        "schema": {
            "breadcrumb": True,
            "itemlist": True,
            "organization": True,
        },

        "nav": {
            "show": bool(c.is_public),
            "parent_key": c.parent_key or "",
        },

        "cascade": {
            "category": {
                "key": c.key,
                "parent_key": c.parent_key or "",
                "is_public": bool(c.is_public),
            },
            "seo": {
                "robots": robots,
            },
        },
    }

    if menu_main_name:
        fm["menu"] = {
            "main": {
                "name": menu_main_name,
                "weight": int(c.menu_main_weight),
                "identifier": c.menu_main_identifier or c.key,
            }
        }

    body_out = _build_structured_body(c, lang)
    return fm, body_out


def write_index(target: Path, fm: Dict, body: str, apply: bool) -> str:
    new_txt = dump_frontmatter(fm) + body

    existed = target.exists()
    if existed:
        old_txt = target.read_text(encoding="utf-8", errors="replace")
        if old_txt == new_txt:
            return "unchanged"

    if apply:
        ensure_parent_dir(target)
        target.write_text(new_txt, encoding="utf-8")
        return "updated" if existed else "created"

    return "would-write"


def is_managed_by_categories_csv(p: Path) -> bool:
    fm, _ = read_frontmatter_and_body(p)
    return str(fm.get("managed_by", "")).strip() == MANAGED_BY


def write_report(path: Path, lines: List[str], apply: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "APPLY" if apply else "DRY-RUN"
    header = [f"# Categories Sync Report ({mode})", "", f"- Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ""]
    path.write_text("\n".join(header + lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/categories.csv")
    ap.add_argument("--de-root", default="content/de")
    ap.add_argument("--en-root", default="content/en")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--report", default=None, help="Report path (default: scripts/reports/categories-sync-<ts>.md)")
    args = ap.parse_args()

    repo_wissen = Path.cwd().resolve()
    csv_path = (repo_wissen / args.csv).resolve()
    de_root = (repo_wissen / args.de_root).resolve()
    en_root = (repo_wissen / args.en_root).resolve()

    if not csv_path.exists():
        print(f"[categories_sync] ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 2
    if not de_root.exists():
        print(f"[categories_sync] ERROR: DE root not found: {de_root}", file=sys.stderr)
        return 2
    if not en_root.exists():
        print(f"[categories_sync] ERROR: EN root not found: {en_root}", file=sys.stderr)
        return 2

    raw_rows = read_csv_utf8_auto(csv_path)
    rows = [row_to_category(r) for r in raw_rows]

    errs = validate_categories(rows)
    if errs:
        print("[categories_sync] VALIDATION FAILED:", file=sys.stderr)
        for e in errs:
            print(f"- {e}", file=sys.stderr)
        return 2

    now_utc = datetime.now(timezone.utc)

    statuses: List[str] = []
    changed_targets: set[Path] = set()

    created = updated = unchanged = would_write = 0

    for c in rows:
        # DE
        de_target = de_root / c.path_de / "_index.md"
        fm_de, body_de = build_frontmatter(c, "de", now_utc)
        st = write_index(de_target, fm_de, body_de, apply=args.apply)
        statuses.append(f"- DE `{de_target.as_posix()}`: {st}")
        if st == "created":
            created += 1
            changed_targets.add(de_target)
        elif st == "updated":
            updated += 1
            changed_targets.add(de_target)
        elif st == "unchanged":
            unchanged += 1
        else:
            would_write += 1

        # EN
        en_target = en_root / c.path_en / "_index.md"
        fm_en, body_en = build_frontmatter(c, "en", now_utc)
        st = write_index(en_target, fm_en, body_en, apply=args.apply)
        statuses.append(f"- EN `{en_target.as_posix()}`: {st}")
        if st == "created":
            created += 1
            changed_targets.add(en_target)
        elif st == "updated":
            updated += 1
            changed_targets.add(en_target)
        elif st == "unchanged":
            unchanged += 1
        else:
            would_write += 1

    pruned = 0
    prune_notes: List[str] = []
    if args.prune:
        csv_targets = {(de_root / c.path_de / "_index.md").resolve() for c in rows} | {(en_root / c.path_en / "_index.md").resolve() for c in rows}

        for root in (de_root, en_root):
            for p in root.rglob("_index.md"):
                try:
                    rp = p.resolve()
                except Exception:
                    continue
                if rp in csv_targets:
                    continue
                if not is_managed_by_categories_csv(p):
                    continue

                if args.apply:
                    try:
                        p.unlink()
                        pruned += 1
                        prune_notes.append(f"- PRUNED `{p.as_posix()}`")
                    except Exception as e:
                        prune_notes.append(f"- PRUNE FAILED `{p.as_posix()}`: {e}")
                else:
                    prune_notes.append(f"- WOULD PRUNE `{p.as_posix()}`")

    # Report
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = Path(args.report) if args.report else (repo_wissen / "scripts" / "reports" / f"categories-sync-{ts}.md")
    lines: List[str] = []
    lines.append(f"- CSV: `{csv_path.as_posix()}`")
    lines.append(f"- DE root: `{de_root.as_posix()}`")
    lines.append(f"- EN root: `{en_root.as_posix()}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- created: {created}")
    lines.append(f"- updated: {updated}")
    lines.append(f"- unchanged: {unchanged}")
    lines.append(f"- would-write: {would_write}")
    if args.prune:
        lines.append(f"- pruned: {pruned}")
    lines.append("")
    lines.append("## Details")
    lines.append("")
    lines.extend(statuses)
    if prune_notes:
        lines.append("")
        lines.append("## Prune")
        lines.append("")
        lines.extend(prune_notes)

    write_report(report_path, lines, apply=args.apply)
    print(f"[categories_sync] Report: {report_path.as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
