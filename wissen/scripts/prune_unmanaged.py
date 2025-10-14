#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prune: löscht Altbestände unter wissen/content/** ohne 'managed_by:'.

Sicherheit:
- Dry-Run per Default (nur Report)
- Echt löschen, wenn ENV PRUNE_CONFIRM=1
- Allowlist schützt Ordner, die bewusst ungemanagt bleiben sollen (bei Bedarf erweitern)

Exit 0: OK, Exit 1: es gäbe Löschkandidaten (im Dry-Run), Exit 2: Löschung ausgeführt.
"""
from __future__ import annotations
import os, re, sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "wissen" / "content"

# Ordner, die vorerst NIE gelöscht werden (kannst du anpassen)
ALLOWLIST = [
    "de/faq/themen",      # FAQ-Themen bleiben (werden zuvor repariert)
    "de/_templates",      # falls vorhanden
    "en/_templates",
]

def is_allowlisted(p: Path) -> bool:
    rel = p.relative_to(CONTENT).as_posix()
    return any(rel.startswith(x) for x in ALLOWLIST)

def has_managed_by(p: Path) -> bool:
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception:
        return False
    return "managed_by:" in txt

def main() -> int:
    dry = os.environ.get("PRUNE_CONFIRM", "") not in {"1", "true", "yes"}
    candidates = []
    for md in CONTENT.rglob("*.md"):
        if is_allowlisted(md):
            continue
        if not has_managed_by(md):
            candidates.append(md)

    if dry:
        if candidates:
            print("Dry-Run: unmanaged candidates:", file=sys.stderr)
            for c in sorted(candidates):
                print(" -", c.relative_to(REPO), file=sys.stderr)
            return 1
        print("Dry-Run: nothing to prune.")
        return 0

    # Echt löschen
    for c in candidates:
        try:
            c.unlink()
        except FileNotFoundError:
            pass

    print(f"Pruned {len(candidates)} files.")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
