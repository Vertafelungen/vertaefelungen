#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audit für Prune-Kandidaten unter wissen/content

Ziel:
- Die *gleichen* Kandidaten ermitteln wie prune_unmanaged.py
  (kein managed_by im Frontmatter; Section-Dateien geschützt; Präfix-Allowlist)
- Kandidaten klassifizieren:
    • section_protected         -> _index.md / README.md (werden eh nicht gepruned)
    • flat_duplicate_strong     -> z.B. wl01.md **und** wl01/index.md existiert
    • human_slug_alt_strong     -> z.B. .../p0002-hamburger-michel/index.md
                                   **und** es gibt .../<NN>-p0002/index.md
    • human_slug_alt_weak       -> z.B. .../klassikgruen-beeck-.../index.md
                                   **und** es gibt .../<NN>-...-klassikgruen/index.md
    • other                     -> unklassifiziert → manuell prüfen
- Ausgaben:
    • CSV:  wissen/scripts/reports/prune-audit-YYYYMMDD-HHMMSS.csv
    • MD:   wissen/scripts/reports/prune-audit-YYYYMMDD-HHMMSS.md
"""

from __future__ import annotations
import os, sys, re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

SECTION_FILES = {"_index.md", "readme.md"}  # niemals löschen
PRODUCT_DIR_RX = re.compile(r"^((?:\d{1,3})-(?:p|sl|wl|tr|l|s)\d{3,5})", re.IGNORECASE)
PCODE_RX = re.compile(r"(p\d{3,5})", re.IGNORECASE)

def repo_root_from_here() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]  # .../wissen/scripts -> .../wissen -> <repo>

def normalize_prefixes(prefixes: str) -> List[str]:
    if not prefixes:
        return []
    out = []
    for raw in prefixes.split(","):
        p = raw.strip().strip("/").replace("\\", "/")
        if p:
            out.append(p)
    return out

def read_text_smart(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="cp1252", errors="replace")

def read_frontmatter_block(p: Path) -> str:
    txt = read_text_smart(p)
    if not txt.startswith("---"):
        return ""
    end = txt.find("\n---", 3)
    if end == -1:
        return ""
    return txt[3:end]

def has_managed_by(frontmatter: str) -> bool:
    for line in frontmatter.splitlines():
        if re.match(r"^\s*managed_by\s*:", line, flags=re.IGNORECASE):
            return True
    return False

def get_lang_and_products_root(content_root: Path, p: Path) -> Tuple[str, Optional[Path]]:
    """Ermittelt Sprache und Produkte-Root je Sprache."""
    rel = p.relative_to(content_root)
    parts = rel.parts
    if len(parts) < 2:
        return "", None
    lang = parts[0].lower()  # 'de' | 'en'
    if lang == "de":
        root = content_root / "de" / "oeffentlich" / "produkte"
    elif lang == "en":
        root = content_root / "en" / "public" / "products"
    else:
        return "", None
    return lang, (root if root.exists() else None)

def is_section_file(path: Path) -> bool:
    return path.name.lower() in SECTION_FILES

def is_allowed_by_prefix(path: Path, content_root: Path, allow_prefixes: List[str]) -> bool:
    rel = path.relative_to(content_root).as_posix()
    return any(rel.startswith(pref) for pref in allow_prefixes)

def collect_candidates(content_root: Path, allow_prefixes: List[str]) -> List[Path]:
    """Gleiche Logik wie prune_unmanaged.py: nur .md ohne managed_by; Section & Allowlist werden übersprungen."""
    cands: List[Path] = []
    for p in content_root.rglob("*.md"):
        # Section-Dateien generell nicht als Kandidat (werden nie gepruned)
        if is_section_file(p):
            continue
        if is_allowed_by_prefix(p, content_root, allow_prefixes):
            continue
        fm = read_frontmatter_block(p)
        if not has_managed_by(fm):
            cands.append(p)
    return sorted(cands, key=lambda x: x.as_posix())

def has_flat_duplicate_strong(p: Path) -> Tuple[bool, Optional[Path]]:
    """
    flaches Duplikat: <parent>/<stem>.md existiert und <parent>/<stem>/index.md existiert
    """
    if p.name.lower() == "index.md":
        return (False, None)
    stem = p.stem
    bundle = p.parent / stem / "index.md"
    return (bundle.exists(), bundle if bundle.exists() else None)

def find_canonical_by_pcode(products_root: Path, pcode: str) -> Optional[Path]:
    """
    Suche ein Verzeichnis <NN>-<pcode>/index.md irgendwo unter products_root.
    """
    rx = re.compile(rf"^\d{{1,3}}-{re.escape(pcode)}$", re.IGNORECASE)
    for d in products_root.rglob("*"):
        if d.is_dir() and rx.match(d.name):
            idx = d / "index.md"
            if idx.exists():
                return idx
    return None

def human_slug_alt_candidates(p: Path, products_root: Path) -> Tuple[str, Optional[Path]]:
    """
    Versuche zwei Heuristiken:
    - STRONG: parent-dir enthält pCode (pNNNN). Finde <NN>-pNNNN/index.md.
    - WEAK:   parent-dir endet auf '-<token>' und es gibt irgendwo <NN>-*<token>/index.md.
    """
    if p.name.lower() != "index.md":
        return ("", None)
    parent_name = p.parent.name

    # STRONG: pCode im Namen
    m = PCODE_RX.search(parent_name)
    if m:
        pcode = m.group(1).lower()
        hit = find_canonical_by_pcode(products_root, pcode)
        if hit and hit.resolve() != p.resolve():
            return ("human_slug_alt_strong", hit)

    # WEAK: token am Ende (z.B. '...-klassikgruen')
    parts = parent_name.split("-")
    if len(parts) >= 2:
        token = parts[-1].lower()
        # Suche irgendein <NN>-<irgendwas>-<token>/index.md
        rx = re.compile(rf"^\d{{1,3}}-[a-z0-9-]*{re.escape(token)}$", re.IGNORECASE)
        for d in products_root.rglob("*"):
            if d.is_dir() and rx.match(d.name):
                idx = d / "index.md"
                if idx.exists() and idx.resolve() != p.resolve():
                    return ("human_slug_alt_weak", idx)

    return ("", None)

def classify_candidate(content_root: Path, p: Path, allow_prefixes: List[str]) -> Dict[str, str]:
    rel = p.relative_to(content_root).as_posix()
    lang, products_root = get_lang_and_products_root(content_root, p)
    info: Dict[str, str] = {
        "lang": lang,
        "candidate": rel,
        "type": "",
        "reason": "",
        "canonical_bundle": "",
        "recommendation": ""
    }

    # Section-Dateien (sollten durch collect() nie auftauchen)
    if is_section_file(p):
        info.update({
            "type": "section_protected",
            "reason": "Section-Datei (_index.md/README.md)",
            "recommendation": "keep (protected)"
        })
        return info

    # Flat duplicate?
    has_dup, dup_path = has_flat_duplicate_strong(p)
    if has_dup:
        info.update({
            "type": "flat_duplicate_strong",
            "reason": "Flache Datei neben Bundle (stem.md + stem/index.md)",
            "canonical_bundle": dup_path.relative_to(content_root).as_posix(),
            "recommendation": "delete (legacy duplicate)"
        })
        return info

    # Human-slug alt?
    if products_root and products_root.exists():
        kind, idx = human_slug_alt_candidates(p, products_root)
        if kind:
            info.update({
                "type": kind,
                "reason": "Legacy-Human-Slug; kanonisches Produkt-Bundle existiert",
                "canonical_bundle": idx.relative_to(content_root).as_posix() if idx else "",
                "recommendation": "delete (legacy alias; aliases liegen im Bundle)"
            })
            return info

    # Fallback
    info.update({
        "type": "other",
        "reason": "Nicht klassifizierbar (prüfen)",
        "recommendation": "review"
    })
    return info

def main() -> int:
    repo_root = repo_root_from_here()
    content_root = (repo_root / "wissen" / "content").resolve()
    if not content_root.exists():
        print(f"Content root not found: {content_root}", file=sys.stderr)
        return 2

    allow_env = os.environ.get("PRUNE_ALLOWLIST", "")
    allow_prefixes = normalize_prefixes(allow_env)

    # Kandidaten wie beim Prune ermitteln
    candidates = collect_candidates(content_root, allow_prefixes)

    # Klassifizieren
    rows: List[Dict[str, str]] = []
    for p in candidates:
        rows.append(classify_candidate(content_root, p, allow_prefixes))

    # Ausgabe-Dateien
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    reports_dir = repo_root / "wissen" / "scripts" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / f"prune-audit-{ts}.csv"
    md_path  = reports_dir / f"prune-audit-{ts}.md"

    # CSV schreiben
    import csv
    fields = ["lang","candidate","type","reason","canonical_bundle","recommendation"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # MD-Report schreiben
    from collections import Counter
    cnt = Counter([r["type"] for r in rows]) if rows else Counter()
    lines: List[str] = []
    lines.append(f"# Prune Audit Report ({ts})")
    lines.append("")
    lines.append(f"- Content root: `{content_root}`")
    lines.append(f"- Allowlist: `{', '.join(allow_prefixes) if allow_prefixes else '(none)'}`")
    lines.append(f"- Candidates total: **{len(rows)}**")
    if cnt:
        lines.append("- Breakdown:")
        for k,v in cnt.most_common():
            lines.append(f"  - {k}: **{v}**")
    lines.append("")
    # kleine Vorschau
    preview = rows[:50]
    if preview:
        lines.append("## Preview (erste 50)")
        lines.append("")
        lines.append("| lang | candidate | type | recommendation |")
        lines.append("|------|-----------|------|----------------|")
        for r in preview:
            lines.append(f"| {r['lang']} | `{r['candidate']}` | {r['type']} | {r['recommendation']} |")
        lines.append("")
    # vollständige Liste
    if rows:
        lines.append("## Vollständige Liste")
        lines.append("")
        for r in rows:
            canon = f" → `{r['canonical_bundle']}`" if r["canonical_bundle"] else ""
            lines.append(f"- `{r['candidate']}`  ⟶  **{r['type']}**  ({r['recommendation']}){canon}")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"CSV: {csv_path}")
    print(f"MD:  {md_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
