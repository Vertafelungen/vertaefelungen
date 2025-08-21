#!/usr/bin/env python3
# coding: utf-8

"""
Auto-fixer für Markdown-Dateien:
- YAML-Frontmatter sauber einfassen und genau eine Leerzeile danach
- Leerzeile vor Listenblöcken
- Tabs -> Spaces in Listen
- Heading-Spacing normalisieren
- trailing spaces trimmen (erhält 2-Spaces-Markdown-Umbruch)
- finale Leerzeile erzwingen
- arbeitet rekursiv über das Repo, ignoriert node_modules/.git/.venv usw.
"""

from __future__ import annotations
import re
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_EXT = {".md", ".markdown"}

IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", ".github", ".idea", ".vscode", "dist", "build", "out"
}

DRY_RUN = "--dry-run" in sys.argv

# -------- Helpers --------

def is_markdown(p: Path) -> bool:
    return p.suffix.lower() in INCLUDE_EXT

def iter_md_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # Verzeichnisfilter
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".pytest_cache")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if is_markdown(p):
                yield p

_HEADING_RE = re.compile(r"^(#{1,6})(\s*)(.*\S.*)$")
_LIST_START_RE = re.compile(r"^(\s*)([-*+]|(\d+)[.)])\s+")
_YAML_FENCE_RE = re.compile(r"^---\s*$")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+$")

def normalize_headings(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            hashes, ws, rest = m.groups()
            # genau ein Space zwischen #..# und Titel
            line = f"{hashes} {rest.strip()}"
        out.append(line)
    return out

def ensure_blank_line_after_yaml(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    if _YAML_FENCE_RE.match(lines[0]):
        for i in range(1, len(lines)):
            if _YAML_FENCE_RE.match(lines[i]):
                end_yaml = i
                break
        else:
            return lines
        j = end_yaml + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        new_lines = lines[:end_yaml+1] + ["\n"] + lines[j:]
        return new_lines
    return lines

def add_blank_line_before_lists(lines: list[str]) -> list[str]:
    out = []
    for idx, line in enumerate(lines):
        if idx > 0:
            prev = out[-1]
            if prev.strip() != "" and _LIST_START_RE.match(line):
                out.append("\n")
        out.append(line)
    return out

def normalize_list_indentation(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if _LIST_START_RE.match(line) or line.startswith("\t"):
            leading = len(line) - len(line.lstrip("\t"))
            if leading > 0:
                line = ("  " * leading) + line.lstrip("\t")
        out.append(line)
    return out

def trim_trailing_spaces_preserve_md_break(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if line.endswith("  \n"):
            core = line[:-3]
            core = _TRAILING_SPACE_RE.sub("", core)
            line = core + "  \n"
        else:
            if line.endswith("\n"):
                core = line[:-1]
                core = _TRAILING_SPACE_RE.sub("", core)
                line = core + "\n"
            else:
                line = _TRAILING_SPACE_RE.sub("", line)
        out.append(line)
    return out

def ensure_final_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"

def normalize_eols(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")

def process_markdown(text: str) -> str:
    text = normalize_eols(text)
    lines = text.splitlines(keepends=True)
    lines = ensure_blank_line_after_yaml(lines)
    lines = normalize_headings(lines)
    lines = add_blank_line_before_lists(lines)
    lines = normalize_list_indentation(lines)
    lines = trim_trailing_spaces_preserve_md_break(lines)
    new_text = "".join(lines)
    new_text = ensure_final_newline(new_text)
    return new_text

def main():
    changed_files = []
    for p in iter_md_files(ROOT):
        original = p.read_text(encoding="utf-8", errors="ignore")
        fixed = process_markdown(original)
        if fixed != original:
            changed_files.append(p)
            if not DRY_RUN:
                p.write_text(fixed, encoding="utf-8")
    if DRY_RUN:
        if changed_files:
            print("Würde ändern:", len(changed_files), "Dateien")
            for p in changed_files:
                print(" -", p.relative_to(ROOT))
        else:
            print("Keine Änderungen nötig.")
    else:
        if changed_files:
            print("Geändert:", len(changed_files), "Dateien")
        else:
            print("Alles schon sauber.")

if __name__ == "__main__":
    main()
