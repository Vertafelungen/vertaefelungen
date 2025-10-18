#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reorg_wissen_products.py
Version: v2025-10-18-1
Generated: 2025-10-18 12:00 (Europe/Berlin)

Ziel
----
Verschiebt Produktbilder aus Kategorieordnern in die kanonischen Produkt-Page-Bundles
unter wissen/content/<lang>/<sektion>/produkte/pNNNN-<slug>/.

Sicher:
- Default ist Dry-Run (nur Report). --apply wendet an.
- Keine Überschreibung vorhandener Dateien ohne Warnung.
- Optional: Duplikate (pNNNN.md, leere pNNNN/-Unterordner) in Kategorien löschen.

Aufruf (Beispiele)
------------------
# DE Dry-Run
python tools/reorg_wissen_products.py --base "wissen/content/de/oeffentlich/produkte"

# DE Apply + Duplikate löschen
python tools/reorg_wissen_products.py --base "wissen/content/de/oeffentlich/produkte" --apply --delete-duplicates

# EN Dry-Run (falls Spiegel vorhanden)
python tools/reorg_wissen_products.py --base "wissen/content/en/public/products"

Autor: ChatGPT (Vertäfelung & Lambris)
Lizenz: MIT
"""
from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime, timezone, timedelta

BERLIN = timezone(timedelta(hours=2))

PRODUCT_CANONICAL_RE = re.compile(r"^(p\d{4})-(.+)$")
IMG_RE = re.compile(r"^(p\d{4})-(\d{1,2})(\.[A-Za-z0-9]+)$", re.IGNORECASE)
DUP_MD_RE = re.compile(r"^(p\d{4})\.md$", re.IGNORECASE)
SUBDIR_RE = re.compile(r"^p\d{4}$")  # Unterordner pNNNN (nur index.md erwartet)

@dataclass
class MoveOp:
    src: Path
    dst: Path
    reason: str

@dataclass
class DeleteOp:
    path: Path
    reason: str

@dataclass
class Report:
    base: Path
    dry_run: bool
    delete_duplicates: bool
    moves: List[MoveOp] = field(default_factory=list)
    deletes: List[DeleteOp] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        ts = datetime.now(BERLIN).strftime("%Y-%m-%d %H:%M:%S %Z")
        lines = []
        lines.append(f"# Reorg-Report – {ts}")
        lines.append("")
        lines.append(f"- Basis: `{self.base}`")
        lines.append(f"- Dry Run: `{self.dry_run}`")
        lines.append(f"- Delete duplicates: `{self.delete_duplicates}`")
        lines.append("")
        lines.append(f"## Geplante Verschiebungen ({len(self.moves)})")
        for m in self.moves:
            lines.append(f"- MOVE: `{m.src}` → `{m.dst}`  — {m.reason}")
        lines.append("")
        lines.append(f"## Geplante Löschungen ({len(self.deletes)})")
        for d in self.deletes:
            lines.append(f"- DELETE: `{d.path}`  — {d.reason}")
        if self.warnings:
            lines.append("")
            lines.append("## Hinweise/Warnungen")
            for w in self.warnings:
                lines.append(f"- {w}")
        return "\n".join(lines)


def find_canonical_map(base: Path) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for child in base.iterdir():
        if child.is_dir():
            m = PRODUCT_CANONICAL_RE.match(child.name)
            if m:
                code = m.group(1)  # pNNNN
                mapping[code] = child
    return mapping


def collect_category_items(cat_dir: Path) -> Tuple[List[Path], List[Path], List[Path]]:
    images: List[Path] = []
    dup_mds: List[Path] = []
    subdirs: List[Path] = []
    for child in cat_dir.iterdir():
        if child.is_file():
            if IMG_RE.match(child.name):
                images.append(child)
            elif DUP_MD_RE.match(child.name):
                dup_mds.append(child)
        elif child.is_dir():
            if SUBDIR_RE.match(child.name):
                subdirs.append(child)
    return images, dup_mds, subdirs


def plan_reorg(base: Path, delete_duplicates: bool) -> Report:
    report = Report(base=base, dry_run=True, delete_duplicates=delete_duplicates)
    canonical_map = find_canonical_map(base)

    # Kategorie-Verzeichnisse: alles, was KEIN kanonischer Produktordner ist
    category_dirs: List[Path] = []
    for child in base.iterdir():
        if child.is_dir() and not PRODUCT_CANONICAL_RE.match(child.name):
            category_dirs.append(child)

    # Map der pNNNN-Unterordner pro Kategorie (für Fallback)
    subdir_map: Dict[str, Path] = {}
    for cat in category_dirs:
        _, _, subdirs = collect_category_items(cat)
        for s in subdirs:
            subdir_map[s.name] = s  # key: pNNNN

    # Plan Moves/Deletes
    for cat in category_dirs:
        images, dup_mds, subdirs = collect_category_items(cat)

        for img in images:
            m = IMG_RE.match(img.name)
            if not m:
                continue
            code, yy, ext = m.groups()
            # Ziel ermitteln
            if code in canonical_map:
                target_dir = canonical_map[code]
            elif code in subdir_map:
                # Fallback: falls noch kein kanonischer Ordner existiert
                target_dir = base / f"{code}"
                target_dir.mkdir(parents=True, exist_ok=True)
            else:
                # Letzter Fallback: lege /pNNNN an
                target_dir = base / f"{code}"
                target_dir.mkdir(parents=True, exist_ok=True)

            dst = target_dir / f"{code}-{yy.zfill(2)}{ext.lower()}"
            if dst.exists():
                report.warnings.append(f"Zieldatei existiert bereits: {dst} — SKIP (prüfen)")
            else:
                report.moves.append(MoveOp(src=img, dst=dst, reason=f"Bild in Bundle {target_dir.name}"))

        if delete_duplicates:
            for md in dup_mds:
                report.deletes.append(DeleteOp(path=md, reason="Kategorie-Duplikat pNNNN.md"))
            for s in subdirs:
                try:
                    entries = list(s.iterdir())
                except Exception:
                    entries = []
                if len(entries) == 0 or (len(entries) == 1 and entries[0].is_file() and entries[0].name.lower() == "index.md"):
                    report.deletes.append(DeleteOp(path=s, reason="Kategorie-Unterordner pNNNN/ (leer oder nur index.md)"))
                else:
                    report.warnings.append(f"Unterordner nicht leer: {s} — nicht automatisch löschen.")

    return report


def apply_report(report: Report):
    for m in report.moves:
        m.dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(m.src), str(m.dst))
        print(f"MOVED  {m.src}  ->  {m.dst}")
    for d in report.deletes:
        p = d.path
        if p.is_dir():
            entries = list(p.iterdir())
            if len(entries) == 1 and entries[0].is_file() and entries[0].name.lower() == 'index.md':
                entries[0].unlink(missing_ok=True)
            try:
                p.rmdir()
                print(f"RMDIR  {p}")
            except OSError:
                print(f"SKIP RMDIR (nicht leer): {p}")
        else:
            p.unlink(missing_ok=True)
            print(f"DELETE {p}")


def main():
    ap = argparse.ArgumentParser(description="Reorganisiere Produktbilder in Hugo-Page-Bundles.")
    ap.add_argument("--base", required=True, help="z. B. wissen/content/de/oeffentlich/produkte")
    ap.add_argument("--apply", action="store_true", help="Ohne diese Option nur Dry-Run (Report).")
    ap.add_argument("--delete-duplicates", action="store_true", help="pNNNN.md & pNNNN/ in Kategorien löschen (wenn sicher).")
    ap.add_argument("--report", default=None, help="Pfad für Markdown-Report; Default: tools/reports/reorg-report-<timestamp>.md")
    args = ap.parse_args()

    base = Path(args.base).resolve()
    if not base.exists():
        raise SystemExit(f"Base not found: {base}")

    report = plan_reorg(base, delete_duplicates=args.delete_duplicates)
    report.dry_run = not args.apply

    ts = datetime.now(BERLIN).strftime("%Y%m%d-%H%M%S")
    report_path = Path(args.report) if args.report else Path("tools/reports") / f"reorg-report-{ts}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.to_markdown(), encoding="utf-8")
    print(f"Report: {report_path}")

    if args.apply:
        apply_report(report)
        print("Änderungen angewendet.")
    else:
        print("Dry-Run beendet. (Keine Dateien verändert.)")


if __name__ == "__main__":
    main()
