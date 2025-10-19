#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seed_en_from_de.py  v2025-10-19-2  (SSOT-aware)

Ziel
- EN-Bundles aus der DE-Struktur erzeugen; Bilder kopieren.
- EN-Slug bevorzugt aus SSOT (slug_en), Fallback: DE-Slug.
- index.md: standardmäßig NICHT schreiben (images-only) -> eure CSV→Markdown-Pipeline übernimmt.

Modi
- --mode images-only   (default): nur Ordner + Bilder, KEIN index.md
- --mode placeholders:  Ordner + Bilder + minimaler index.md
- --mode ssot:          Ordner + Bilder + index.md aus SSOT (Mapping unten)

Idempotent:
- Überschreibt keine bestehenden Dateien (außer mit --overwrite-index).
"""
from __future__ import annotations
import argparse, csv, re, shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

RE_CANON = re.compile(r"^(?P<code>[psw]\d{4})-(?P<slug>.+)$", re.I)
IMG_RE   = re.compile(r"^[psw]\d{4}-\d{2}\.(png|jpg|jpeg|webp|avif)$", re.I)

# ---------------- SSOT helpers ----------------
def load_ssot(path: Optional[Path], delimiter=",") -> Dict[str, dict]:
    data: Dict[str, dict] = {}
    if not path or not path.exists():
        return data
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            code = (row.get("code") or row.get("produkt_code") or "").strip().lower()
            if not code:
                continue
            data[code] = row
    return data

def ssot_slug_en(ssot: Dict[str, dict], code: str, fallback: str) -> str:
    row = ssot.get(code.lower())
    slug = (row or {}).get("slug_en") or ""
    return (slug or "").strip() or fallback

def ssot_title_en(ssot: Dict[str, dict], code: str, fallback: str) -> str:
    row = ssot.get(code.lower())
    title = (row or {}).get("title_en") or (row or {}).get("titel_en") or ""
    return (title or "").strip() or fallback

def ssot_frontmatter_en(ssot: Dict[str, dict], code: str, fallback_title: str) -> str:
    title = ssot_title_en(ssot, code, fallback_title)
    return f"""---
title: "{title}"
lang: en
translationKey: "{code}"
---
"""

# ---------------- seeding core ----------------
def ensure_bundle(base: Path, code: str, slug: str) -> Path:
    d = base / f"{code}-{slug}"
    d.mkdir(parents=True, exist_ok=True)
    return d

def write_placeholder_index(en_dir: Path, code: str, title_fallback: str):
    idx = en_dir / "index.md"
    if idx.exists():
        return
    idx.write_text(f"""---
title: "{title_fallback}"
lang: en
translationKey: "{code}"
---

> TODO: Translate content from German page for **{code.upper()}**.
""", encoding="utf-8")

def write_ssot_index(en_dir: Path, code: str, ssot: Dict[str, dict], de_title: str):
    idx = en_dir / "index.md"
    if idx.exists():
        return
    idx.write_text(ssot_frontmatter_en(ssot, code, de_title or f"{code.upper()} – TODO English title"), encoding="utf-8")

def read_de_title(de_index: Path) -> str:
    if not de_index.exists():
        return ""
    txt = de_index.read_text(encoding="utf-8", errors="replace")
    if not txt.startswith("---"):
        return ""
    try:
        fm = txt.split("\n---", 1)[0].splitlines()[1:]
        for line in fm:
            if line.strip().lower().startswith("title:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--de-root", default="wissen/content/de/oeffentlich/produkte")
    ap.add_argument("--en-root", default="wissen/content/en/public/products")
    ap.add_argument("--mode", choices=["images-only", "placeholders", "ssot"], default="images-only")
    ap.add_argument("--ssot-csv", default="wissen/ssot/SSOT.csv", help="Pfad zur SSOT-CSV (für slug_en/title_en)")
    ap.add_argument("--ssot-delimiter", default=",")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--overwrite-index", action="store_true", help="Bestehende index.md überschreiben (i.d.R. nicht setzen).")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    de_root = Path(args.de_root).resolve()
    en_root = Path(args.en_root).resolve()
    assert de_root.exists(), f"DE root not found: {de_root}"

    ssot = load_ssot(Path(args.ssot_csv)) if args.ssot_csv else {}

    created_dirs = []
    image_copies = []
    index_written = []

    for d in sorted([p for p in de_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        m = RE_CANON.match(d.name)
        if not m:
            continue  # Kategorieordner überspringen
        code = m.group("code").lower()
        slug_de = m.group("slug")
        # EN-Slug aus SSOT (slug_en) oder DE-Slug als Fallback
        slug_en = ssot_slug_en(ssot, code, slug_de)
        en_dir = ensure_bundle(en_root, code, slug_en)
        if en_dir not in created_dirs:
            created_dirs.append(en_dir)

        # Bilder kopieren
        for f in d.iterdir():
            if f.is_file() and IMG_RE.match(f.name):
                dst = en_dir / f.name
                if not dst.exists():
                    image_copies.append((f, dst))

        # index.md je nach Modus
        idx = en_dir / "index.md"
        if args.mode == "placeholders":
            if args.overwrite_index and idx.exists():
                idx.unlink()
            if not idx.exists():
                write_placeholder_index(en_dir, code, read_de_title(d / "index.md") or f"{code.upper()} – TODO English title")
                index_written.append(idx)
        elif args.mode == "ssot":
            if not ssot:
                raise SystemExit("Mode 'ssot' gewählt, aber --ssot-csv fehlt oder ist leer.")
            if args.overwrite_index and idx.exists():
                idx.unlink()
            if not idx.exists():
                write_ssot_index(en_dir, code, ssot, read_de_title(d / "index.md"))
                index_written.append(idx)
        else:
            # images-only: keine index.md schreiben
            pass

    # Report
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rep = Path(args.report) if args.report else Path("tools/reports") / f"seed-en-{ts}.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# EN Seed Report ({ts})", "",
             f"DE root: {de_root}", f"EN root: {en_root}", f"Mode: {args.mode}", ""]
    lines += [f"## Bundles ensured ({len(created_dirs)})"] + [f"- {p}" for p in created_dirs] + [""]
    lines += [f"## Images to copy ({len(image_copies)})"] + [f"- {src} -> {dst}" for src, dst in image_copies] + [""]
    lines += [f"## Index files to write ({len(index_written)})"] + [f"- {p}" for p in index_written]
    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {rep}")

    if args.apply:
        en_root.mkdir(parents=True, exist_ok=True)
        for src, dst in image_copies:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"COPY {src} -> {dst}")
        print("Done (apply).")
    else:
        print("Dry-run (no changes).")

if __name__ == "__main__":
    main()
