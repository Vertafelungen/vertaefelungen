#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prune unmanaged Markdown files under wissen/content

- Löscht nur .md-Dateien, die KEIN 'managed_by:' im Frontmatter besitzen.
- _index.md und README.md werden NIE gelöscht (Section-/Kategorieseiten-Schutz).
- Zusätzliche Schutzpfade (Präfixe relativ zu wissen/content) via Env: PRUNE_ALLOWLIST="de/docs,de/faq,en/faq"
- Dry-Run per Default; erst bei PRUNE_CONFIRM=true werden Dateien wirklich entfernt.
"""

from __future__ import annotations
import os, sys, re
from pathlib import Path
from typing import Iterable, List

SECTION_FILES = {"_index.md", "readme.md"}  # nie löschen

def repo_root_from_here() -> Path:
    # <repo>/wissen/scripts/prune_unmanaged.py  -> <repo>
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

def is_allowed(path: Path, content_root: Path, allow_prefixes: List[str]) -> bool:
    rel = path.relative_to(content_root).as_posix()
    for pref in allow_prefixes:
        if rel.startswith(pref):
            return True
    return False

def read_frontmatter_block(p: Path) -> str:
    try:
        txt = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Fallback für alte Dateien
        txt = p.read_text(encoding="cp1252", errors="replace")
    if not txt.startswith("---"):
        return ""
    # Frontmatter bis zur nächsten Zeile mit '---'
    end = txt.find("\n---", 3)
    if end == -1:
        return ""
    return txt[3:end]  # ohne die erste '---'

def has_managed_by(frontmatter: str) -> bool:
    # Nur im Frontmatter prüfen, nicht im Body.
    # Zeilenweise tolerant gegen Whitespaces/Case.
    for line in frontmatter.splitlines():
        if re.match(r"^\s*managed_by\s*:", line, flags=re.IGNORECASE):
            return True
    return False

def collect_candidates(content_root: Path, allow_prefixes: List[str]) -> List[Path]:
    cands: List[Path] = []
    for p in content_root.rglob("*.md"):
        # Section-/Kategorieseiten nie löschen
        if p.name.lower() in SECTION_FILES:
            continue
        # Allowlist (Präfix relativ zu content-root)
        if is_allowed(p, content_root, allow_prefixes):
            continue
        fm = read_frontmatter_block(p)
        if not has_managed_by(fm):
            cands.append(p)
    return sorted(cands, key=lambda x: x.as_posix())

def main() -> int:
    repo_root = repo_root_from_here()
    content_root = (repo_root / "wissen" / "content").resolve()
    if not content_root.exists():
        print(f"Content root not found: {content_root}", file=sys.stderr)
        return 2

    confirm = (os.environ.get("PRUNE_CONFIRM", "false").strip().lower() == "true")
    allow_env = os.environ.get("PRUNE_ALLOWLIST", "")  # z. B. "de/docs,de/faq,en/faq"
    allow_prefixes = normalize_prefixes(allow_env)

    cands = collect_candidates(content_root, allow_prefixes)

    mode = "REAL" if confirm else "DRY-RUN"
    print(f"Prune unmanaged content\n\n    Mode: {mode}\n    Candidates: {len(cands)}\n")

    # Übersicht zeigen
    if cands:
        print("Dateien anzeigen\n")
        for p in cands:
            rel = p.relative_to(content_root).as_posix()
            print(f"    wissen/content/{rel}")

    if not confirm:
        return 0

    # Real löschen
    deleted = 0
    for p in cands:
        try:
            p.unlink()
            deleted += 1
        except Exception as e:
            print(f"[WARN] Could not delete {p}: {e}", file=sys.stderr)

    print(f"\nDeleted: {deleted}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
