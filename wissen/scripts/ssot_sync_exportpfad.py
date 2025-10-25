#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSOT → Markdown Page Bundles (export_pfad aware, no image renaming)
- Legt pro Produkt ein Leaf-Bundle unterhalb export_pfad_de/en an:
    DE: content/de/<export_pfad_de>/<code>-<slug_de>/
    EN: content/en/<export_pfad_en>/<code>-<slug_en>/
- Schreibt index.md (Frontmatter aus SSOT; translationKey=code; aliases für Alt-URLs).
- Verschiebt alle im SSOT (bilder_liste) aufgeführten Bilddateien in das DE-Produktbundle
  (SUCHE im gesamten DE-Produktbaum) – Dateinamen bleiben exakt wie gelistet.
- Kopiert diese Bilder 1:1 ins EN-Bundle (gleiche Dateinamen).
- Entfernt KEINE Kategorieordner; räumt leere alte Produkt-Bundles auf Wunsch.
- Idempotent; erzeugt Report (moved/copied/missing/aliases).
"""

from __future__ import annotations
import argparse, csv, io, os, re, shutil, sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from ruamel.yaml import YAML

# ---------- Helpers ----------

yaml = YAML()
yaml.default_flow_style = False
yaml.allow_unicode = True
yaml.width = 4096

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif"}

def read_csv_utf8_auto(path: Path) -> List[Dict[str,str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # Dialekt schnüffeln
    try:
        dialect = csv.Sniffer().sniff(raw[:2048], delimiters=",;|\t")
        delim = dialect.delimiter
    except Exception:
        delim = ","
    return list(csv.DictReader(io.StringIO(raw), delimiter=delim))

def clean(s: Optional[str]) -> str:
    return (s or "").strip()

def slugify(s: str) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"[ä]", "ae", t)
    t = re.sub(r"[ö]", "oe", t)
    t = re.sub(r"[ü]", "ue", t)
    t = re.sub(r"[ß]", "ss", t)
    t = re.sub(r"[^\w\s-]", "", t)
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    return t.strip("-") or "item"

def ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

def read_frontmatter_and_body(p: Path) -> Tuple[Dict, str]:
    if not p.exists(): return {}, ""
    txt = p.read_text(encoding="utf-8", errors="replace")
    if txt.startswith("---"):
        parts = txt.split("\n---", 1)
        if len(parts) == 2:
            fm_raw = parts[0][3:]
            body = parts[1].lstrip("\n")
            try:
                fm = yaml.load(fm_raw) or {}
                if not isinstance(fm, dict):
                    fm = {}
            except Exception:
                fm = {}
            return fm, body
    return {}, txt

def dump_frontmatter(fm: Dict) -> str:
    from io import StringIO
    s = StringIO()
    yaml.dump(fm, s)
    return "---\n" + s.getvalue().rstrip() + "\n---\n"

def write_index(bundle_dir: Path, fm_new: Dict, keep_body_from: Optional[Path]):
    ensure_dir(bundle_dir)
    idx = bundle_dir / "index.md"
    body = ""
    if keep_body_from and keep_body_from.exists():
        _, body = read_frontmatter_and_body(keep_body_from)
    elif idx.exists():
        _, body = read_frontmatter_and_body(idx)
    idx.write_text(dump_frontmatter(fm_new) + (body if body else ""), encoding="utf-8")

def bundle_url(content_lang_root: Path, bundle_dir: Path) -> str:
    rel = bundle_dir.relative_to(content_lang_root).as_posix().strip("/")
    lang = content_lang_root.name.lower()  # 'de' | 'en'
    return f"/wissen/{lang}/{rel}/"

def find_existing_bundles(content_lang_root: Path, code: str) -> List[Path]:
    # sehr großzügig: jede Dir, die mit "<code>-" beginnt, gilt als altes Bundle
    hits = []
    for p in content_lang_root.rglob(f"{code}-*"):
        if p.is_dir():
            hits.append(p)
    return hits

def list_all_images(root: Path) -> Dict[str, List[Path]]:
    # Map: basename.lower() -> [fullpath,...]
    from collections import defaultdict
    m = defaultdict(list)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            m[p.name.lower()].append(p)
    return m

# ---------- Core ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/SSOT.csv")
    ap.add_argument("--de-root", default="content/de")
    ap.add_argument("--en-root", default="content/en")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--remove-empty-old-bundles", action="store_true")
    args = ap.parse_args()

    repo_wissen = Path.cwd().resolve()   # erwartet: <repo>/wissen
    csv_path = (repo_wissen / args.csv).resolve()
    de_root  = (repo_wissen / args.de_root).resolve()
    en_root  = (repo_wissen / args.en_root).resolve()
    assert csv_path.exists(), f"CSV not found: {csv_path}"
    assert de_root.exists(),  f"DE root not found: {de_root}"
    assert en_root.exists(),  f"EN root not found: {en_root}"

    rows = read_csv_utf8_auto(csv_path)

    # Index aller vorhandenen Bilder im DE-Produkte-Baum (einmalig)
    de_products_root = de_root / "oeffentlich" / "produkte"
    assert de_products_root.exists(), f"DE products root missing: {de_products_root}"
    de_images_index = list_all_images(de_products_root)

    created, updated, moved, copied, aliases_set, errors = [], [], [], [], [], []

    for r in rows:
        code = clean(r.get("code") or r.get("produkt_code") or r.get("product_code"))
        if not code:
            errors.append("row without code")
            continue

        slug_de = clean(r.get("slug_de")) or slugify(clean(r.get("title_de") or r.get("titel_de") or code))
        slug_en = clean(r.get("slug_en")) or slugify(clean(r.get("title_en") or r.get("titel_en") or code))

        exp_de = clean(r.get("export_pfad_de"))
        exp_en = clean(r.get("export_pfad_en"))
        if not exp_de: errors.append(f"{code}: missing export_pfad_de")
        if not exp_en: errors.append(f"{code}: missing export_pfad_en")
        if not exp_de or not exp_en:
            continue

        bilder_raw = clean(r.get("bilder_liste") or r.get("bilder") or "")
        bilder = [b.strip() for b in re.split(r"[,\n;]", bilder_raw) if b.strip()]

        # Ziel-Bundles
        bundle_de = de_root / exp_de.strip("/") / f"{code}-{slug_de}"
        bundle_en = en_root / exp_en.strip("/") / f"{code}-{slug_en}"

        # Aliases aus alten Bundles sammeln (DE+EN)
        old_de = [p for p in find_existing_bundles(de_root, code) if p.resolve() != bundle_de.resolve()]
        old_en = [p for p in find_existing_bundles(en_root, code) if p.resolve() != bundle_en.resolve()]
        alias_de = [bundle_url(de_root, p) for p in old_de]
        alias_en = [bundle_url(en_root, p) for p in old_en]

        # Existierende Aliases mitnehmen
        fm_exist_de, _ = read_frontmatter_and_body(bundle_de / "index.md")
        fm_exist_en, _ = read_frontmatter_and_body(bundle_en / "index.md")
        if isinstance(fm_exist_de.get("aliases"), list):
            alias_de.extend([str(a) for a in fm_exist_de["aliases"]])
        if isinstance(fm_exist_en.get("aliases"), list):
            alias_en.extend([str(a) for a in fm_exist_en["aliases"]])

        # Frontmatter bauen (nur Kernfelder; übrige kommen aus SSOT – optional erweiterbar)
        fm_de = {"title": clean(r.get("title_de") or r.get("titel_de") or code),
                 "lang": "de", "translationKey": code}
        fm_en = {"title": clean(r.get("title_en") or r.get("titel_en") or code),
                 "lang": "en", "translationKey": code}
        if alias_de: fm_de["aliases"] = sorted(set(alias_de))
        if alias_en: fm_en["aliases"] = sorted(set(alias_en))

        # index.md schreiben/aktualisieren
        if args.apply:
            existed = (bundle_de / "index.md").exists()
            write_index(bundle_de, fm_de, keep_body_from=bundle_de / "index.md")
            (updated if existed else created).append(bundle_de.as_posix())

            existed = (bundle_en / "index.md").exists()
            write_index(bundle_en, fm_en, keep_body_from=bundle_en / "index.md")
            (updated if existed else created).append(bundle_en.as_posix())

        # Bilder einsammeln (DE): exakt die Namen aus bilder_liste – ohne Umbenennung
        for name in bilder:
            key = name.lower()
            # Falls bereits im Ziel-Bundle vorhanden, ok
            if (bundle_de / name).exists():
                continue
            # Sonst global im DE-Produkte-Baum nach Basename suchen
            candidates = de_images_index.get(key, [])
            if not candidates:
                errors.append(f"{code}: image missing in repo (DE): {name}")
                continue
            # Heuristik: bevorzuge Kandidaten, die unterhalb des export_pfad_de liegen
            chosen = None
            pref_root = de_root / exp_de.strip("/")
            for c in candidates:
                try:
                    c.relative_to(pref_root)
                    chosen = c; break
                except Exception:
                    continue
            if not chosen:
                chosen = candidates[0]
            # Verschieben
            if args.apply:
                ensure_dir((bundle_de).resolve())
                dst = bundle_de / chosen.name  # Name bleibt unverändert
                if not dst.exists():
                    shutil.move(str(chosen), str(dst))
                    moved.append(f"MOVE {chosen} -> {dst}")
                # Index neu aufbauen für den Fall mehrfacher Dateien mit gleichem Namen
            # (kein else: dry-run weglassen, um Log schlank zu halten)

        # Bilder nach EN spiegeln
        for name in bilder:
            src = bundle_de / name
            dst = bundle_en / name
            if src.exists():
                if args.apply:
                    ensure_dir(dst.parent)
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        copied.append(f"COPY {src} -> {dst}")
            else:
                errors.append(f"{code}: image not found in DE bundle for EN copy: {name}")

        if alias_de or alias_en:
            aliases_set.append(code)

        # Leere alte Bundle-Verzeichnisse optional löschen
        if args.apply and args.remove_empty_old_bundles:
            for ob in old_de + old_en:
                try:
                    # nur löschen, wenn wirklich leer
                    any_files = any(ob.rglob("*"))
                    if not any_files:
                        ob.rmdir()
                except Exception:
                    pass

    # Report schreiben
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rep = Path(args.report) if args.report else Path("scripts/reports")/f"ssot-sync-exportpfad-{ts}.md"
    ensure_dir(rep.parent)
    lines = [
        f"# SSOT Sync Report ({ts})",
        "",
        f"CSV: {csv_path}",
        f"DE root: {de_root}",
        f"EN root: {en_root}",
        ""
    ]
    if created: lines += ["## Created"] + [f"- {p}" for p in created] + [""]
    if updated: lines += ["## Updated"] + [f"- {p}" for p in updated] + [""]
    if moved:   lines += ["## Moved"]   + [f"- {p}" for p in moved]   + [""]
    if copied:  lines += ["## Copied"]  + [f"- {p}" for p in copied]  + [""]
    if aliases_set: lines += ["## Aliases set for codes"] + [f"- {c}" for c in sorted(set(aliases_set))] + [""]
    if errors:  lines += ["## Errors"]  + [f"- {e}" for e in errors]  + [""]

    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {rep}")

    # Exit-Code: Fehler sichtbar machen (Gate entscheidet im nachgelagerten Step)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
