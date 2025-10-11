#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repariert Markdown-Dateien mit offenem oder fehlerhaft begonnenem YAML-Frontmatter.

Fälle:
- Zeile 1 ist exakt '---' (linksbuendig), aber es existiert kein schließender '---'.
- Zeile 1 beginnt mit '---' und enthaelt bereits Payload (z. B. '--- title: Wissen description: ...').
  -> Payload wird in einzelne YAML-Zeilen aufgesplittet.
- Existiert bereits ein schliessender '---', wird der vorhandene Header-Bereich korrekt neu
  aufgebaut (Payload gesplittet + bisherige Header-Zeilen bis zum End-Delimiter).

Idempotent: Mehrfachlauf ist unkritisch.
"""

from __future__ import annotations
from pathlib import Path
import re

CONTENT = Path(__file__).resolve().parents[1] / "content"

# Delimiter exakt in eigener Zeile
DELIM_RE = re.compile(r'^\s*---\s*$')

# Start mit Payload in Zeile 1: '--- <payload>'
START_WITH_PAYLOAD_RE = re.compile(r'^\s*---\s*(.+)$')

# YAML-Formen
KEY_LINE  = re.compile(r'^[A-Za-z0-9_\-]+\s*:\s*.*$')
LIST_ITEM = re.compile(r'^\s*-\s+.*$')
INDENTED  = re.compile(r'^\s{2,}\S.*$')  # eingerueckte Fortsetzungen / Blockcontent

# Key-Tokenizer: findet "key:" am Wortanfang (Start oder Whitespace davor)
KEY_TOKEN = re.compile(r'(?<!\S)([A-Za-z0-9_\-]+)\s*:\s*')

def normalize_nl(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

def find_end_delim(lines: list[str], start_idx: int = 1) -> int | None:
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

def split_payload_into_yaml_lines(payload: str) -> list[str]:
    """
    Zerlegt 'title: Wissen description: ... slug: x' in einzelne Zeilen:
    ['title: Wissen', 'description: ...', 'slug: x'].
    """
    res: list[str] = []
    if not payload.strip():
        return res
    matches = list(KEY_TOKEN.finditer(payload))
    if not matches:
        # kein 'key:' -> als Kommentar ablegen (damit Parser nicht scheitert)
        return [f"# auto-repaired: payload='{payload.strip()}'"]
    for idx, m in enumerate(matches):
        key = m.group(1)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(payload)
        value = payload[start:end].strip()
        # Falls value leer ist, trotzdem key anlegen
        res.append(f"{key}: {value}".rstrip())
    return res

def repair_text(t: str) -> tuple[str, bool]:
    t = normalize_nl(t)
    if not t:
        return t, False

    lines = t.splitlines()

    # Fall A: Start-Zeile ist exakt '---'
    if DELIM_RE.match(lines[0]):
        end = find_end_delim(lines, start_idx=1)
        if end is not None:
            # Header ist formal geschlossen → nichts tun
            return t, False
        # Kein Abschluss: Header aus "YAML-ähnlichen" Zeilen sammeln
        yaml_lines, body_idx = collect_yaml_block(lines, 1)
        if not yaml_lines:
            yaml_lines = ["# auto-repaired: missing end YAML frontmatter delimiter"]
        fixed = "---\n" + "\n".join(yaml_lines).rstrip() + "\n---\n"
        body = "\n".join(lines[body_idx:]).lstrip("\n")
        return fixed + (body + ("\n" if body and not body.endswith("\n") else "")), True

    # Fall B: Start-Zeile beginnt mit '---' + Payload
    m = START_WITH_PAYLOAD_RE.match(lines[0])
    if m:
        payload = m.group(1)
        end = find_end_delim(lines, start_idx=1)
        header_lines: list[str] = split_payload_into_yaml_lines(payload)

        if end is not None:
            # Existierender Abschluss: uebernehme existierende Header-Zeilen bis 'end'
            rest = lines[1:end]
            header_lines.extend(rest)
            body = "\n".join(lines[end+1:]).lstrip("\n")
        else:
            # Kein Abschluss: YAML-Block heuristisch sammeln
            rest, body_idx = collect_yaml_block(lines, 1)
            header_lines.extend(rest)
            body = "\n".join(lines[body_idx:]).lstrip("\n")

        if not header_lines:
            header_lines = ["# auto-repaired: malformed frontmatter start"]

        fixed = "---\n" + "\n".join(header_lines).rstrip() + "\n---\n"
        return fixed + (body + ("\n" if body and not body.endswith("\n") else "")), True

    # Kein Frontmatter-Start
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
