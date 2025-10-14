#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prune unmanaged Markdown unter wissen/content/**.

"Unmanaged" = Datei enthält KEIN 'managed_by:'.

Sicherheit:
- Default: DRY-RUN (PRUNE_CONFIRM != true) -> Exit 0 (grün) + Bericht
- Confirm: echte Löschung + Commit (vom Workflow), Exit 0

Allowlist (nie löschen), relativ zu wissen/content/:
- BASIS: de/faq, en/faq, de/_templates, en/_templates
- + optionale Präfixe via ENV PRUNE_ALLOWLIST (kommagetrennt)

Löscht ausschließlich *.md (keine Verzeichnisse/Assets).
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "wissen" / "content"

BASE_ALLOWLIST = [
    "de/faq",          # komplette FAQ-Struktur schützen
    "en/faq",
    "de/_templates",
    "en/_templates",
]

def read_text_safely(p: Path) -> str:
    b = p.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252", errors="ignore")

def load_allowlist() -> list[str]:
    allow = list(BASE_ALLOWLIST)
    extra = os.environ.get("PRUNE_ALLOWLIST", "").strip()
    if extra:
        allow.extend(x.strip().strip("/") for x in extra.split(",") if x.strip())
    return [a.replace("\\", "/") for a in allow]

def is_allowlisted(p: Path, allowlist: Iterable[str]) -> bool:
    rel = p.relative_to(CONTENT).as_posix()
    return any(rel.startswith(prefix) for prefix in allowlist)

def is_unmanaged(p: Path) -> bool:
    try:
        return "managed_by:" not in read_text_safely(p)
    except Exception:
        return False

def main() -> int:
    allowlist = load_allowlist()
    confirm = os.environ.get("PRUNE_CONFIRM", "").lower() in {"1", "true", "yes"}

    candidates = []
    for md in CONTENT.rglob("*.md"):
        if is_allowlisted(md, allowlist):
            continue
        if is_unmanaged(md):
            candidates.append(md)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = []
    lines.append("### Prune unmanaged content\n")
    lines.append(f"- Mode: {'DELETE' if confirm else 'DRY-RUN'}")
    lines.append(f"- Candidates: **{len(candidates)}**\n")
    if candidates:
        lines.append("<details><summary>Dateien anzeigen</summary>\n")
        for c in sorted(candidates):
            lines.append(f"- `{c.relative_to(REPO)}`")
        lines.append("\n</details>\n")
    else:
        lines.append("Keine Kandidaten gefunden.\n")

    print("\n".join(lines))
    if summary_path:
        Path(summary_path).write_text("\n".join(lines), encoding="utf-8")

    if not confirm:
        return 0

    deleted = 0
    for c in candidates:
        try:
            c.unlink()
            print(f"deleted: {c.relative_to(REPO)}")
            deleted += 1
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"warn: could not delete {c.relative_to(REPO)}: {e}")

    print(f"Pruned {deleted} files.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
