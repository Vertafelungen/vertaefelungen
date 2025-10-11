#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repariert Markdown-Dateien mit *offenem* oder fehlerhaft begonnenem YAML-Frontmatter.

Fälle:
- Zeile 1 ist exakt '---' (Start), aber es existiert kein schließender '---' (linksbuendig).
- Zeile 1 beginnt mit '---' und enthält bereits Text auf derselben Zeile (z. B. '--- title: Wissen').
  => Der Rest nach '---' wird als erste YAML-Zeile gewertet.
- Danach werden zusammenhängende YAML-Zeilen (Key/Value, Listen, eingerückte Fortsetzungen)
  bis zur ersten Nicht-YAML-Zeile gesammelt und korrekt zwischen '---' ... '---' eingeschlossen.

Idempotent: Mehrfachlauf ist unkritisch.
"""

from __future__ import annotations
from pathlib import Path
import re

CONTENT = Path(__file__).resolve().parents[1] / "content"

# gültige Start-/End-Zeile: NUR '---' (evtl. Whitespace)
DELIM_RE = re.compile(r'^\s*---\s*$')
# erkennt Zeile 1, die mit '---' beginnt, aber Text dahinter hat
START_WITH_PAYLOAD_RE = re.compile(r'^\s*---\s*(.+)$')

# YAML-ähnliche Zeilen: key: value, listeneintrag, eingerückte Fortsetzung
KEY_LINE  = re.compile(r'^[A-Za-z0-9_\-]+\s*:\s*.*$')
LIST_ITEM = re.compile(r'^\s*-\s+.*$')
INDENTED  = re.compile(r'^\s{2,}\S.*$')  # eingerückt (z. B. Block-Content)

def normalize_nl(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

def find_end_delim(lines: list[str], start_idx: int = 1) -> int | None:
    """Suche echten Abschluss-Delimiter ab start_idx; None, wenn nicht vorhanden."""
    for i in range(start_idx, len(lines)):
        if DELIM_RE.match(lines[i]):
            return i
    return None

def collect_yaml_block(lines: list[str], start_idx: int) -> tuple[list[str], int]:
    """
    Sammle YAML-Zeilen ab start_idx (inklusive) bis zur ersten Nicht-YAML-Zeile.
    Liefert (yaml_lines, next_body_idx).
    """
    yaml_lines: list[str] = []
    i = start_idx
    while i < len(lines):
        ln = lines[i]
        if KEY_LINE.match(ln) or LIST_ITEM.match(ln) or INDENTED.match(ln) or ln.strip() == "":
            yaml_lines.append(ln)
            i += 1
            continue
        break
    return yaml_lines, i

def repair_text(t: str) -> tuple[str, bool]:
    """
    Repariert offene/fehlerhafte Header. Gibt (neuer_text, geändert?)
    """
    t = normalize_nl(t)
    if not t:
        return t, False

    lines = t.splitlines()

    # Fall A: Zeile 1 ist exakt '---'
    if DELIM_RE.match(lines[0]):
        end = find_end_delim(lines, start_idx=1)
        if end is not None:
            return t, False  # bereits korrekt geschlossen
        # kein Abschluss -> Header sammeln ab Zeile 1
        yaml_lines, body_idx = collect_yaml_block(lines, 1)
        if not yaml_lines:
            yaml_lines = ["# auto-repaired: missing end YAML frontmatter delimiter"]
        fixed = "---\n" + "\n".join(yaml_lines).rstrip() + "\n---\n"
        body = "\n".join(lines[body_idx:]).lstrip("\n")
        return fixed + (body + ("\n" if body and not body.endswith("\n") else "")), True

    # Fall B: Zeile 1 beginnt mit '---' + Text
    m = START_WITH_PAYLOAD_RE.match(lines[0])
    if m:
        first_payload = m.group(1).strip()  # z. B. "title: Wissen"
        # Collect weitere YAML-Zeilen ab Zeile 2
        yaml_lines, body_idx = collect_yaml_block(lines, 1)
        header = []
        if first_payload:
            header.append(first_payload)
        header.extend(yaml_lines)
        if not header:
            header = ["# auto-repaired: malformed frontmatter start"]
        fixed = "---\n" + "\n".join(header).rstrip() + "\n---\n"
        body = "\n".join(lines[body_idx:]).lstrip("\n")
        return fixed + (body + ("\n" if body and not body.endswith("\n") else "")), True

    # kein Frontmatter-Start vorhanden
    return t, False

def main() -> int:
    repaired = 0
    for p in CONTENT.rglob("*.md"):
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        new_t, changed = repair_text(t)
        if changed:
            p.write_text(new_t, encoding="utf-8")
            repaired += 1
    print(f"Repaired files (open/malformed frontmatter): {repaired}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
