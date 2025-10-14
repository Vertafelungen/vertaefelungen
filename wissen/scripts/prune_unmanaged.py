#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prune unmanaged Markdown under wissen/content/**.

Definition "unmanaged":
  - Datei enthält KEIN 'managed_by:' im Frontmatter/Text.

Sicherheit:
  - Default ist DRY-RUN (ENV PRUNE_CONFIRM != 1/true/yes)
  - Bei Dry-Run: nur Bericht + Exit 0 (grün).
  - Bei Confirm: echte Löschung, jede Datei wird geloggt, Exit 0.

Allowlist:
  - Ordnerpräfixe, die NIE gelöscht werden (anpassbar via ENV PRUNE_ALLOWLIST,
    mit Komma getrennt, relativ zu wissen/content).

Exit-Codes:
  0 = OK (Dry-Run oder echte Löschung abgeschlossen)
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "wissen" / "content"

# Baseline-Allowlist; kann per ENV erweitert werden
BASE_ALLOWLIST = [
    "de/faq/themen",     # FAQ-Themen schützen (kannst du entfernen, wenn gewünscht)
    "de/_templates",
    "en/_templates",
]

def read_text_safely(p: Path) -> str:
    b = p.read_bytes()
    # BOM entfernen
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
    # in POSIX-Notation (/) vereinheitlichen
    return [a.replace("\\", "/") for a in allow]

def is_allowlisted(p: Path, allowlist: Iterable[str]) -> bool:
    rel = p.relative_to(CONTENT).as_posix()
    return any(rel.startswith(prefix) for prefix in allowlist)

def is_unmanaged(p: Path) -> bool:
    try:
        return "managed_by:" not in read_text_safely(p)
    except Exception:
        # Wenn unlesbar, lieber NICHT löschen
        return False

def main() -> int:
    allowlist = load_allowlist()
    confirm = os.environ.get("PRUNE_CONFIRM", "").lower() in {"1", "true", "yes"}

    candidates: list[Path] = []
    for md in CONTENT.rglob("*.md"):
        if is_allowlisted(md, allowlist):
            continue
        if is_unmanaged(md):
            candidates.append(md)

    # Zusammenfassung in Step Summary (wenn von GitHub Actions aufgerufen)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    summary_lines = []
    summary_lines.append(f"### Prune unmanaged content\n")
    summary_lines.append(f"- Mode: {'DELETE' if confirm else 'DRY-RUN'}")
    summary_lines.append(f"- Candidates: **{len(candidates)}**\n")
    if candidates:
        summary_lines.append("<details><summary>Dateien anzeigen</summary>\n\n")
        for c in sorted(candidates):
            summary_lines.append(f"- `{c.relative_to(REPO)}`")
        summary_lines.append("\n</details>\n")
    else:
        summary_lines.append("Keine Kandidaten gefunden.\n")
    if summary_path:
        Path(summary_path).write_text("\n".join(summary_lines), encoding="utf-8")

    # Log in STDOUT
    print("\n".join(summary_lines))

    if not confirm:
        # DRY-RUN: niemals fehlschlagen
        return 0

    # Echte Löschung
    deleted = 0
    for c in candidates:
        try:
            c.unlink()
            print(f"deleted: {c.relative_to(REPO)}")
            deleted += 1
        except FileNotFoundError:
            # bereits weg → ignorieren
            pass
        except Exception as e:
            # Nicht abbrechen; nur melden
            print(f"warn: could not delete {c.relative_to(REPO)}: {e}")

    print(f"Pruned {deleted} files.")
    # Erfolg (auch wenn 0 Dateien gelöscht)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
