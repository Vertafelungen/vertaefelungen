#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reorg_wissen_products.py
Version: v2025-10-18-1 (Europe/Berlin)

Ziel
----
Ordnet die Produktbilder aus Kategorien (z. B. .../halbhohe-vertaefelungen/)
in ihre jeweiligen Produkt-Page-Bundles (z. B. .../p0015-berlin-alte-nationalgalerie/)
um – passend zur Hugo-Page-Bundle-Arbeitsweise.

Funktionen
----------
1) erkennt kanonische Produktordner am Muster: pNNNN-<slug>/
2) findet Kategorieordner (alles andere innerhalb von 'produkte/')
3) verschiebt Bilder: pNNNN-YY.(png|jpg|jpeg|webp|avif) → Ziel-Produktordner
4) optional: normalisiert YY auf zweistellig (01..09)
5) Datei-Kollisionen:
   - identische Dateien (SHA-256) → Quelle wird gelöscht (kein Duplikat)
   - unterschiedliche Dateien → WARN, Move SKIP
6) optional: löscht Duplikate in Kategorien (pNNNN.md & leere pNNNN/-Unterordner)
7) Report als Markdown (Dry-Run & Apply)

Aufruf (Beispiele)
------------------
# Dry-Run (nur Bericht):
python tools/reorg_wissen_products.py \
  --base "wissen/content/de/oeffentlich/produkte"

# Anwenden + Duplikate entfernen:
python tools/reorg_wissen_products.py \
  --base "wissen/content/de/oeffentlich/produkte" \
  --apply --delete-duplicates

Optionen
--------
--base (str)                    : Basisordner (DE: wissen/content/de/oeffentlich/produkte)
--apply                         : Änderungen ausführen (ohne: Dry-Run)
--normalize-two-digits          : 'pNNNN-1.jpg' -> 'pNNNN-01.jpg'
--delete-duplicates             : Kategorie-Duplikate entfernen (pNNNN.md, leere pNNNN/)
--report (str)                  : eigener Reportpfad (default: tools/reports/reorg-report-<ts>.md)

Autor: Vertäfelung & Lambris – ChatGPT
Lizenz: MIT
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

BERLIN = timezone(timedelta(hours=2))

PRODUCT_CANONICAL_RE = re.compile(r"^(p\d{4})-(.+)$", re.IGNORECASE)
RE_PRODUCT_CODE      = re.compile(r"^(p\d{4})", re.IGNORECASE)
IMG_RE               = re.compile(r"^(p\d{4})-(\d{1,2})(\.[A-Za-z0-9]+)$", re.IGNORECASE)
DUP_MD_RE            = re.compile(r"^(p\d{4})\.md$", re.IGNORECASE)
SUBDIR_RE            = re.compile(r"^p\d{4}$", re.IGNORECASE)
IMG_EXTS             = {".png", ".jpg", ".jpeg", ".webp", ".avif"}

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
    normalize_two_digits: bool
    delete_duplicates: bool
    moves: List[MoveOp] = field(default_factory=list)
    deletes: List[DeleteOp] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        ts = datetime.now(BERLIN).strftime("%Y-%m-%d %H:%M:%S %Z")
        lines = []
        lines.append(f"# Reorg-Report – {ts}")
        lines.append("")
        lines.append(f"- Basis: `{self.base}`")
        lines.append(f"- Dry Run: `{self.dry_run}`")
        lines.append(f"- Normalize two digits: `{self.normalize_two_digits}`")
        lines.append(f"- Delete duplicates: `{self.delete_duplicates}`")
        if self.notes:
            lines.append("")
            lines.append("## Hinweise")
            for n in self.notes:
                lines.append(f"- {n}")
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
            lines.append("## WARNUNGEN")
            for w in self.warnings:
                lines.append(f"- {w}")
        return "\n".join(lines)


def sha256sum(p: Path) -> Optional[str]:
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_canonical_map(base: Path) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    if not base.exists():
        return mapping
    for child in base.iterdir():
        if child.is_dir():
            m = PRODUCT_CANONICAL_RE.match(child.name)
            if m:
                code = m.group(1).lower()
                mapping[code] = child
    return mapping


def desired_filename(name: str, normalize_two_digits: bool) -> str:
    m = IMG_RE.match(name)
    if not m:
        return name
    code, yy, ext = m.groups()
    if normalize_two_digits:
        yy = yy.zfill(2)
    return f"{code.lower()}-{yy}{ext.lower()}"


def collect_category_items(cat_dir: Path) -> Tuple[List[Path], List[Path], List[Path]]:
    images: List[Path] = []
    dup_mds: List[Path] = []
    subdirs: List[Path] = []
    for child in sorted(cat_dir.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file():
            if child.suffix.lower() in IMG_EXTS and IMG_RE.match(child.name):
                images.append(child)
            elif DUP_MD_RE.match(child.name):
                dup_mds.append(child)
        elif child.is_dir():
            if SUBDIR_RE.match(child.name):
                subdirs.append(child)
    return images, dup_mds, subdirs


def ensure_target_dir(code: str, base: Path, canonical_map: Dict[str, Path], subdirs_for_code: Dict[str, Path], report: Report) -> Optional[Path]:
    code = code.lower()
    if code in canonical_map:
        return canonical_map[code]
    if code in subdirs_for_code:
        # Fallback: wenn es einen pNNNN-Unterordner in einer Kategorie gibt, spiegeln wir ihn an der Basis als pNNNN/
        fallback = base / code
        fallback.mkdir(parents=True, exist_ok=True)
        report.notes.append(f"Kein kanonischer Produktordner für {code} gefunden – Fallback '{fallback.name}' angelegt.")
        return fallback
    report.warnings.append(f"Kein Zielordner für {code} – Bild wird nicht verschoben.")
    return None


def plan_reorg(base: Path, normalize_two_digits: bool, delete_duplicates: bool) -> Report:
    report = Report(base=base, dry_run=True, normalize_two_digits=normalize_two_digits, delete_duplicates=delete_duplicates)

    canonical_map = find_canonical_map(base)

    # Kategorie-Verzeichnisse = alles, was KEIN kanonischer Produktordner ist
    category_dirs: List[Path] = []
    if base.exists():
        for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and not PRODUCT_CANONICAL_RE.match(child.name):
                category_dirs.append(child)

    # Hilfsmap: pro Kategorie Unterordner pNNNN zuordnen
    subdir_map: Dict[str, Path] = {}
    for cat in category_dirs:
        images, dup_mds, subdirs = collect_category_items(cat)
        for s in subdirs:
            code = s.name.lower()  # pNNNN
            subdir_map[code] = s

    # Durchlaufe je Kategorie und plane Moves/Deletes
    for cat in category_dirs:
        cat_images, dup_mds, subdirs = collect_category_items(cat)

        # Bilder verschieben
        for img in cat_images:
            m = IMG_RE.match(img.name)
            if not m:
                continue
            code, yy, ext = m.groups()
            target_dir = ensure_target_dir(code, base, canonical_map, subdir_map, report)
            if not target_dir:
                continue
            new_name = desired_filename(img.name, normalize_two_digits)
            dst = target_dir / new_name

            if dst.exists():
                src_hash = sha256sum(img)
                dst_hash = sha256sum(dst)
                if src_hash and dst_hash and src_hash == dst_hash:
                    # identisch -> Quelle kann weg
                    report.deletes.append(DeleteOp(path=img, reason=f"Duplikat (identisch zu {dst.name})"))
                else:
                    report.warnings.append(f"Konflikt: {dst} existiert und unterscheidet sich von {img}. Move SKIP.")
            else:
                report.moves.append(MoveOp(src=img, dst=dst, reason=f"Bild {img.name} → Bundle {target_dir.name}"))

        # Duplikat-Markdowns und Subdirs optional löschen
        if delete_duplicates:
            for md in dup_mds:
                report.deletes.append(DeleteOp(path=md, reason="Kategorie-Duplikat pNNNN.md"))
            for s in subdirs:
                entries = list(s.iterdir())
                # nur löschen, wenn leer oder nur index.md
                if len(entries) == 0 or (len(entries) == 1 and entries[0].is_file() and entries[0].name.lower() == "index.md"):
                    # index.md ggf. vorher löschen
                    for e in entries:
                        if e.is_file() and e.name.lower() == "index.md":
                            report.deletes.append(DeleteOp(path=e, reason="index.md in leerem pNNNN-Unterordner"))
                    report.deletes.append(DeleteOp(path=s, reason="Kategorie-Unterordner pNNNN/ (Duplikat)"))
                else:
                    report.warnings.append(f"Unterordner nicht leer: {s} – nicht automatisch löschen.")

    return report


def apply_report(report: Report):
    # Moves
    for m in report.moves:
        m.dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(m.src), str(m.dst))
        print(f"MOVED  {m.src}  ->  {m.dst}")
    # Deletes
    for d in report.deletes:
        p = d.path
        if p.is_dir():
            # im Zweifel leeren (nur index.md sollte schon im Report stehen)
            try:
                p.rmdir()
                print(f"RMDIR  {p}")
            except OSError:
                print(f"SKIP RMDIR (nicht leer): {p}")
        else:
            p.unlink(missing_ok=True)
            print(f"DELETE {p}")


def main():
    ap = argparse.ArgumentParser(description="Reorganisiere Produktbilder in Hugo-Page-Bundles (DE/EN).")
    ap.add_argument("--base", required=True, help="Basisordner, z. B. wissen/content/de/oeffentlich/produkte")
    ap.add_argument("--apply", action="store_true", help="Änderungen anwenden (ohne: Dry-Run).")
    ap.add_argument("--normalize-two-digits", action="store_true", help="Optional: YY auf zweistellig normalisieren.")
    ap.add_argument("--delete-duplicates", action="store_true", help="Optional: pNNNN.md & leere pNNNN/-Unterordner in Kategorien löschen.")
    ap.add_argument("--report", default=None, help="Pfad für Markdown-Report. Default: tools/reports/reorg-report-<timestamp>.md")
    args = ap.parse_args()

    base = Path(args.base).resolve()
    if not base.exists():
        raise SystemExit(f"Base does not exist: {base}")

    report = plan_reorg(base, normalize_two_digits=args.normalize_two_digits, delete_duplicates=args.delete_duplicates)
    report.dry_run = (not args.apply)

    ts = datetime.now(BERLIN).strftime("%Y%m%d-%H%M%S")
    default_report = Path("tools/reports") / f"reorg-report-{ts}.md"
    report_path = Path(args.report) if args.report else default_report
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
