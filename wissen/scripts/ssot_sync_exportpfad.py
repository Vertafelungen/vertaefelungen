#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSOT → Markdown Page Bundles (export_pfad aware, no image renaming)

- Primärschlüssel: product_id (Fallback: reference; sonst aus slug_de/slug_en extrahiert)
- Zielstruktur:
    DE: content/de/<export_pfad_de>/<pk>-<slug_de>/
    EN: content/en/<export_pfad_en>/<pk>-<slug_en>/
- index.md: translationKey=pk; aliases bei Umzug
- Bilder aus `bilder_liste`:
    * Einmalig aus Kategorie-Bäumen MOVEN (Kategorien langfristig bildfrei)
    * Wenn Bild bereits verschoben/liegt in anderem Produkt-Bundle → COPY
    * Keine Umbenennung; Dateinamen bleiben exakt wie gelistet
- Zeilen ohne brauchbaren pk werden still SKIPPED (kein Abbruch)
- Nach jedem Move wird der Bildindex aktualisiert (keine „stale path“-Fehler)
"""

from __future__ import annotations
import argparse, csv, io, re, shutil, sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from ruamel.yaml import YAML

yaml = YAML()
yaml.default_flow_style = False
yaml.allow_unicode = True
yaml.width = 4096

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif"}

# ---------- CSV / Text Utils ----------

def _normkey(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
    return s

def read_csv_utf8_auto(path: Path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw[:2048], delimiters=",;|\t")
        delim = dialect.delimiter
    except Exception:
        delim = ","
    rows = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    norm = [{ _normkey(k): ("" if v is None else v) for k, v in r.items() } for r in rows]
    return norm

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

# ---------- Frontmatter / Markdown ----------

def read_frontmatter_and_body(p: Path):
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
    bundle_dir.mkdir(parents=True, exist_ok=True)
    idx = bundle_dir / "index.md"
    body = ""
    if keep_body_from and keep_body_from.exists():
        _, body = read_frontmatter_and_body(keep_body_from)
    elif idx.exists():
        _, body = read_frontmatter_and_body(idx)
    idx.write_text(dump_frontmatter(fm_new) + (body if body else ""), encoding="utf-8")

# ---------- Paths, URLs, Images ----------

PK_REGEX = re.compile(r"^(p\d{3,5}|sl\d{3,5}|wl\d{3,5}|tr\d{3,5}|l\d{3,5}|s\d{3,5})", re.IGNORECASE)
BUNDLE_DIRNAME_REGEX = re.compile(r"^(p|sl|wl|tr|l|s)\d{3,5}-", re.IGNORECASE)

def bundle_url(content_lang_root: Path, bundle_dir: Path) -> str:
    rel = bundle_dir.relative_to(content_lang_root).as_posix().strip("/")
    lang = content_lang_root.name.lower()
    return f"/wissen/{lang}/{rel}/"

def find_existing_bundles(content_lang_root: Path, pk: str) -> List[Path]:
    hits = []
    for p in content_lang_root.rglob(f"{pk}-*"):
        if p.is_dir():
            hits.append(p)
    return hits

def is_in_product_bundle(p: Path) -> bool:
    for parent in [p] + list(p.parents):
        if BUNDLE_DIRNAME_REGEX.match(parent.name):
            return True
    return False

def list_all_images(root: Path) -> Dict[str, List[Path]]:
    from collections import defaultdict
    m = defaultdict(list)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            m[p.name.lower()].append(p)
    return m

def refresh_index_entry(index: Dict[str, List[Path]], name: str, old: Optional[Path], new: Optional[Path]):
    key = name.lower()
    lst = index.get(key, [])
    if old is not None:
        lst = [p for p in lst if p.resolve() != old.resolve()]
    if new is not None:
        lst.append(new)
    index[key] = lst

# ---------- Produkt-Key ----------

def get_pk(row: Dict[str,str]) -> str:
    v = clean(row.get("product_id"))
    if v: return v.lower()
    v = clean(row.get("reference"))
    if v: return v.lower()
    for k in ("slug_de","slug_en","slug"):
        v = clean(row.get(k))
        if not v: 
            continue
        m = PK_REGEX.match(v)
        if m:
            return m.group(1).lower()
        t = v.split("-",1)[0].lower()
        if PK_REGEX.match(t):
            return t
    return ""

# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/SSOT.csv")
    ap.add_argument("--de-root", default="content/de")
    ap.add_argument("--en-root", default="content/en")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--remove-empty-old-bundles", action="store_true")
    args = ap.parse_args()

    repo_wissen = Path.cwd().resolve()
    csv_path = (repo_wissen / args.csv).resolve()
    de_root  = (repo_wissen / args.de_root).resolve()
    en_root  = (repo_wissen / args.en_root).resolve()
    assert csv_path.exists(), f"CSV not found: {csv_path}"
    assert de_root.exists(),  f"DE root not found: {de_root}"
    assert en_root.exists(),  f"EN root not found: {en_root}"

    rows = read_csv_utf8_auto(csv_path)

    de_products_root = de_root / "oeffentlich" / "produkte"
    assert de_products_root.exists(), f"DE products root missing: {de_products_root}"
    img_index = list_all_images(de_products_root)
    processed_sources: set[Path] = set()

    created, updated, moved, copied, aliases_set, errors, skipped = [], [], [], [], [], [], []

    for r in rows:
        pk = get_pk(r)
        if not pk:
            skipped.append("row without product_id/reference/slug")
            continue

        slug_de = clean(r.get("slug_de")) or slugify(clean(r.get("titel_de") or pk))
        slug_en = clean(r.get("slug_en")) or slugify(clean(r.get("titel_en") or pk))

        exp_de = clean(r.get("export_pfad_de"))
        exp_en = clean(r.get("export_pfad_en"))
        if not exp_de or not exp_en:
            skipped.append(f"{pk}: missing export path")
            continue

        bilder_raw = clean(r.get("bilder_liste") or "")
        bilder = [b.strip() for b in re.split(r"[,\n;]", bilder_raw) if b.strip()]

        bundle_de = de_root / exp_de.strip("/") / f"{pk}-{slug_de}"
        bundle_en = en_root / exp_en.strip("/") / f"{pk}-{slug_en}"

        # Aliases bei Umzug
        old_de = [p for p in find_existing_bundles(de_root, pk) if p.resolve() != bundle_de.resolve()]
        old_en = [p for p in find_existing_bundles(en_root, pk) if p.resolve() != bundle_en.resolve()]
        alias_de = [bundle_url(de_root, p) for p in old_de]
        alias_en = [bundle_url(en_root, p) for p in old_en]

        fm_exist_de, _ = read_frontmatter_and_body(bundle_de / "index.md")
        fm_exist_en, _ = read_frontmatter_and_body(bundle_en / "index.md")
        if isinstance(fm_exist_de.get("aliases"), list):
            alias_de.extend([str(a) for a in fm_exist_de["aliases"]])
        if isinstance(fm_exist_en.get("aliases"), list):
            alias_en.extend([str(a) for a in fm_exist_en["aliases"]])

        fm_de = {"title": clean(r.get("titel_de") or pk), "lang": "de", "translationKey": pk}
        fm_en = {"title": clean(r.get("titel_en") or pk), "lang": "en", "translationKey": pk}
        if alias_de: fm_de["aliases"] = sorted(set(alias_de))
        if alias_en: fm_en["aliases"] = sorted(set(alias_en))

        if args.apply:
            existed = (bundle_de / "index.md").exists()
            write_index(bundle_de, fm_de, keep_body_from=bundle_de / "index.md")
            (updated if existed else created).append(bundle_de.as_posix())

            existed = (bundle_en / "index.md").exists()
            write_index(bundle_en, fm_en, keep_body_from=bundle_en / "index.md")
            (updated if existed else created).append(bundle_en.as_posix())

        # Bilder → DE
        for name in bilder:
            dst_de = bundle_de / name
            if dst_de.exists():
                continue

            key = name.lower()
            # Liste existierender Quellen JETZT (Index wurde ggf. verändert)
            sources = [p for p in img_index.get(key, []) if p.exists()]
            # Wenn leer: versuchen im ganzen DE-Baum nochmal zu suchen (z. B. nach Moves)
            if not sources:
                for p in de_products_root.rglob(name):
                    if p.is_file():
                        sources.append(p)
                if sources:
                    img_index[key] = sources  # aktualisieren

            if not sources:
                errors.append(f"{pk}: image missing in repo (DE): {name}")
                continue

            # Bevorzugt Quelle unterhalb export_pfad_de
            chosen = None
            pref_root = de_root / exp_de.strip("/")
            for c in sources:
                try:
                    c.relative_to(pref_root)
                    chosen = c; break
                except Exception:
                    continue
            if not chosen:
                chosen = sources[0]

            # Move nur 1x aus Kategorie-Wurzel; sonst Copy
            do_move = False
            if chosen not in processed_sources:
                # Kategorie-Asset? (nicht in einem Produkt-Bundle)
                do_move = not is_in_product_bundle(chosen)

            if args.apply:
                dst_de.parent.mkdir(parents=True, exist_ok=True)
                if do_move:
                    # MOVE
                    shutil.move(str(chosen), str(dst_de))
                    moved.append(f"MOVE {chosen} -> {dst_de}")
                    processed_sources.add(chosen)
                    # Index aktualisieren
                    refresh_index_entry(img_index, name, old=chosen, new=dst_de)
                else:
                    # COPY
                    shutil.copy2(chosen, dst_de)
                    copied.append(f"COPY {chosen} -> {dst_de}")
                    refresh_index_entry(img_index, name, old=None, new=dst_de)

        # Bilder → EN spiegeln
        for name in bilder:
            src = bundle_de / name
            dst = bundle_en / name
            if src.exists():
                if args.apply:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        copied.append(f"COPY {src} -> {dst}")
            else:
                errors.append(f"{pk}: image not found in DE bundle for EN copy: {name}")

        if alias_de or alias_en:
            aliases_set.append(pk)

        if args.apply and args.remove_empty_old_bundles:
            for ob in old_de + old_en:
                try:
                    if not any(ob.rglob("*")):
                        ob.rmdir()
                except Exception:
                    pass

    # Report
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rep = Path(args.report) if args.report else Path("scripts/reports")/f"ssot-sync-exportpfad-{ts}.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# SSOT Sync Report ({ts})", "",
        f"CSV: {csv_path}", f"DE root: {de_root}", f"EN root: {en_root}", ""
    ]
    if created: lines += ["## Created"] + [f"- {p}" for p in created] + [""]
    if updated: lines += ["## Updated"] + [f"- {p}" for p in updated] + [""]
    if moved:   lines += ["## Moved"]   + [f"- {p}" for p in moved]   + [""]
    if copied:  lines += ["## Copied"]  + [f"- {p}" for p in copied]  + [""]
    if aliases_set: lines += ["## Aliases set for"] + [f"- {c}" for c in sorted(set(aliases_set))] + [""]
    if skipped: lines += ["## Skipped (info)"] + [f"- {s}" for s in skipped[:200]] + [""]
    if errors:  lines += ["## Errors"]  + [f"- {e}" for e in errors]  + [""]

    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {rep}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
