#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ssot_sync.py  v2025-10-19-2  (export_pfad_de / export_pfad_en aware)

Zweck
- Synchronisiert die SSOT (CSV) → Markdown-Page-Bundles (DE & EN) unterhalb der
  in der SSOT definierten Exportpfade (export_pfad_de / export_pfad_en).
- Legt pro Produkt ein LEAF-BUNDLE {code}-{slug}/ an (index.md + Bilder).
- Verschiebt/vereinheitlicht verstreute Bilder rekursiv (Altlasten aus Kategorien).
- Kopiert Bilder DE → EN (inhaltsgleich, getrennte Bundles).
- Pflegt aliases in index.md automatisch, wenn sich der Zielpfad (URL) ändert.
- Idempotent: wiederholbar, bewahrt vorhandene Bodies der index.md.

Konventionen / Annahmen
- Dieses Script wird mit CWD = <repo>/wissen ausgeführt (vgl. Workflow).
- Content-Wurzeln:
    DE_ROOT = "content/de"
    EN_ROOT = "content/en"
- SSOT liegt (Default) unter "ssot/SSOT.csv".
- In SSOT existieren Spalten (mindestens):
    code, slug_de, slug_en, export_pfad_de, export_pfad_en, bilder_liste
  Optional (werden in Frontmatter übernommen, typ-sicher):
    title_de/title_en, description_de/description_en, price_cents, in_stock
- bilder_liste enthält nur Dateinamen (keine Pfade), z. B. "p0009-01.jpg, p0009-02.png".

Hugo / SEO / Struktur
- Produkte werden als Leaf-Bundles unterhalb der Exportpfade geführt, z. B.:
    content/de/oeffentlich/produkte/halbhohe-vertaefelungen/p0009-<slug_de>/
    content/en/public/products/<export_pfad_en>/p0009-<slug_en>/
- Kategorien sind Branch-Bundles (nur _index.md/README.md); Produkt-Assets liegen NICHT
  im Kategorie-Root. Das Script räumt ggf. Altlasten (p0009/*) rekursiv dorthin weg.
- Bei Pfadwechseln werden alte URLs automatisch als aliases erfasst.

CLI
  Dry-Run:
    python scripts/ssot_sync.py
  Anwenden:
    python scripts/ssot_sync.py --apply
  Weitere Optionen:
    --csv pfad             (Default: ssot/SSOT.csv)
    --de-root pfad         (Default: content/de)
    --en-root pfad         (Default: content/en)
    --report pfad
    --delete-duplicates    (Duplikate am Alt-Ort nach Move löschen, wenn gleich)
    --normalize-two-digits (Bildsuffix -1 → -01, -2 → -02, ... sofern vorhanden)

Exit-Codes
- 0: OK (dry-run/real) – Report erzeugt.
- 1: Report mit Fehlern (z. B. invalid code, fehlende Bildernamen-Formate);
     der Workflow zeigt das im PR an.

"""

from __future__ import annotations
import argparse, csv, re, shutil, sys, hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
import yaml

# ----------------------------- Konfiguration -----------------------------

RE_CODE = re.compile(r"^[psw]\d{4}$", re.I)
RE_BUNDLE = re.compile(r"^[psw]\d{4}-.+$", re.I)
IMG_NAME = re.compile(r"^[psw]\d{4}-(\d{1,2})\.(png|jpg|jpeg|webp|avif)$", re.I)
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif"}

# ----------------------------- Hilfsfunktionen ---------------------------

def slugify_basic(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[ä]", "ae", s)
    s = re.sub(r"[ö]", "oe", s)
    s = re.sub(r"[ü]", "ue", s)
    s = re.sub(r"[ß]", "ss", s)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-") or "item"

def to_bool(v: str) -> Optional[bool]:
    if v is None: return None
    t = str(v).strip().lower()
    if t in {"true","1","yes","ja","y"}: return True
    if t in {"false","0","no","nein","n"}: return False
    return None

def to_int(v: str) -> Optional[int]:
    try:
        return int(str(v).strip())
    except Exception:
        return None

def read_csv_rows(path: Path) -> List[Dict[str,str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def normalize_two_digits(name: str) -> str:
    """
    p0009-1.jpg -> p0009-01.jpg  (nur wenn genau -\d{1} vorkommt)
    """
    m = IMG_NAME.match(name)
    if not m: return name
    num = m.group(1)
    if len(num) == 1:
        return re.sub(r"-(\d)\.", r"-0\1.", name)
    return name

def file_sha1(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

def split_frontmatter(md_text: str) -> Tuple[Dict, str]:
    if md_text.startswith("---"):
        parts = md_text.split("\n---", 1)
        if len(parts) == 2:
            fm_raw = parts[0][3:]  # cut first '---'
            body = parts[1].lstrip("\n")
            try:
                fm = yaml.safe_load(fm_raw) or {}
                if not isinstance(fm, dict):
                    fm = {}
            except Exception:
                fm = {}
            return fm, body
    return {}, md_text

def dump_frontmatter(fm: Dict) -> str:
    return "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip() + "\n---\n"

def read_md(path: Path) -> Tuple[Dict, str]:
    if not path.exists():
        return {}, ""
    txt = path.read_text(encoding="utf-8", errors="replace")
    return split_frontmatter(txt)

def write_index(bundle_dir: Path, fm_new: Dict, keep_body_from: Optional[Path]):
    ensure_dir(bundle_dir)
    idx = bundle_dir / "index.md"
    body = ""
    if keep_body_from and keep_body_from.exists():
        fm_old, body = read_md(keep_body_from)
    elif idx.exists():
        fm_old, body = read_md(idx)
    idx.write_text(dump_frontmatter(fm_new) + (body if body else ""), encoding="utf-8")

def path_to_url(content_lang_root: Path, bundle_dir: Path) -> str:
    """
    content_lang_root = <repo>/wissen/content/de  oder .../en
    bundle_dir = .../wissen/content/de/<export_path>/<code>-<slug>/
    -> /wissen/de/<export_path>/<code>-<slug>/
    """
    # <repo>/wissen is cwd; we add /wissen prefix explicitly
    rel = bundle_dir.relative_to(content_lang_root).as_posix().strip("/")
    lang = content_lang_root.name.lower()  # 'de' | 'en'
    return f"/wissen/{lang}/{rel}/"

def find_existing_bundles(content_lang_root: Path, code: str) -> List[Path]:
    """
    Suche nach Ordnern <irgendwo>/<code>-<irgendwas> unterhalb content_lang_root.
    """
    hits = []
    for p in content_lang_root.rglob(f"{code}-*"):
        if p.is_dir() and RE_BUNDLE.match(p.name):
            hits.append(p)
    return hits

def move_or_delete_duplicate(src: Path, dst: Path, delete_duplicates: bool, log: List[str]):
    if not src.exists():
        return
    if dst.exists():
        try:
            if file_sha1(src) == file_sha1(dst):
                if delete_duplicates:
                    src.unlink()
                    log.append(f"DELETE duplicate {src}")
                else:
                    log.append(f"SKIP duplicate (keep both) {src} ~ {dst}")
                return
            else:
                # Name-Kollision mit unterschiedlichem Inhalt -> umbenennen
                stem, ext = dst.stem, dst.suffix
                i = 2
                while True:
                    cand = dst.with_name(f"{stem}-{i}{ext}")
                    if not cand.exists():
                        shutil.move(str(src), str(cand))
                        log.append(f"RENAME-MOVE {src} -> {cand} (collision content)")
                        return
                    i += 1
        except Exception:
            # Fallback: nicht vergleichen -> nicht löschen
            log.append(f"SKIP collision (no hash) {src} vs {dst}")
            return
    # normaler Move
    ensure_dir(dst.parent)
    shutil.move(str(src), str(dst))
    log.append(f"MOVE {src} -> {dst}")

def sweep_recursively_for_code_images(content_lang_root: Path, code: str, target_bundle: Path,
                                      normalize_two_digit: bool, delete_duplicates: bool,
                                      log: List[str]):
    """
    Sammelt verstreute Bilder (Altlasten) rekursiv ein:
    - .../<kategorie>/**/p0009-*.{ext}
    - .../<kategorie>/p0009/p0009-*.{ext}
    und verschiebt sie ins target_bundle.
    """
    for p in content_lang_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS and p.name.lower().startswith(f"{code}-"):
            # schon am Ziel?
            try:
                p.relative_to(target_bundle)
                # liegt bereits im Bundle
                continue
            except ValueError:
                pass
            name = p.name
            if normalize_two_digit:
                name = normalize_two_digits(name)
            dst = target_bundle / name
            move_or_delete_duplicate(p, dst, delete_duplicates, log)

# ----------------------------- SSOT Parsing ------------------------------

def parse_row(row: Dict[str,str]) -> Tuple[Dict[str,object], List[str]]:
    errs: List[str] = []

    code = (row.get("code") or row.get("produkt_code") or "").strip().lower()
    if not RE_CODE.match(code):
        errs.append(f"invalid code '{code}'")

    # Slugs
    slug_de = (row.get("slug_de") or "").strip()
    slug_en = (row.get("slug_en") or "").strip()
    if not slug_de:
        slug_de = slugify_basic(row.get("title_de") or row.get("titel_de") or "")
    if not slug_en:
        slug_en = slugify_basic(row.get("title_en") or row.get("titel_en") or "")

    # Exportpfade
    exp_de = (row.get("export_pfad_de") or "").strip().strip("/")
    exp_en = (row.get("export_pfad_en") or "").strip().strip("/")
    if not exp_de:
        errs.append("missing export_pfad_de")
    if not exp_en:
        errs.append("missing export_pfad_en")

    # Bilderliste
    bilder_raw = (row.get("bilder_liste") or row.get("bilder") or "").strip()
    bilder = [b.strip() for b in bilder_raw.split(",") if b.strip()]
    invalid_imgs = [b for b in bilder if not IMG_NAME.match(b)]
    # wir normalisieren später, daher nur harte Fehler bei komplett falschem Muster
    really_bad = [b for b in invalid_imgs if not re.match(r"^[psw]\d{4}-\d+\.", b, re.I)]
    if really_bad:
        errs.append(f"invalid image names: {', '.join(really_bad)}")

    # Frontmatter-Felder
    title_de = (row.get("title_de") or row.get("titel_de") or "").strip() or code.upper()
    title_en = (row.get("title_en") or row.get("titel_en") or "").strip() or f"{code.upper()} – TODO English title"
    desc_de  = (row.get("description_de") or row.get("beschreibung_de") or "").strip()
    desc_en  = (row.get("description_en") or "").strip()
    price_cents_raw = row.get("price_cents")
    price_cents = to_int(price_cents_raw)
    if price_cents is None and price_cents_raw not in (None, ""):
        errs.append(f"price_cents not int: '{price_cents_raw}'")
    in_stock_raw = row.get("in_stock")
    in_stock = to_bool(in_stock_raw)
    if in_stock is None and in_stock_raw not in (None, ""):
        errs.append(f"in_stock not bool: '{in_stock_raw}'")

    return ({
        "code": code,
        "slug_de": slug_de,
        "slug_en": slug_en,
        "export_pfad_de": exp_de,
        "export_pfad_en": exp_en,
        "bilder": bilder,
        "title_de": title_de,
        "title_en": title_en,
        "description_de": desc_de,
        "description_en": desc_en,
        "price_cents": price_cents,
        "in_stock": in_stock,
    }, errs)

def build_frontmatter(data: Dict[str,object], lang: str, aliases: List[str]) -> Dict:
    fm = {
        "title": data["title_de"] if lang=="de" else data["title_en"],
        "lang": lang,
        "translationKey": data["code"]
    }
    if data["price_cents"] is not None:
        fm["price_cents"] = int(data["price_cents"])
    if data["in_stock"] is not None:
        fm["in_stock"] = bool(data["in_stock"])
    if data["description_de"] and lang=="de":
        fm["description"] = data["description_de"]
    if data["description_en"] and lang=="en":
        fm["description"] = data["description_en"]
    if data["bilder"]:
        fm["bilder"] = [normalize_two_digits(b) for b in data["bilder"]]
    if aliases:
        fm["aliases"] = sorted(set(aliases))
    return fm

# ----------------------------- Hauptlogik --------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/SSOT.csv")
    ap.add_argument("--de-root", default="content/de")
    ap.add_argument("--en-root", default="content/en")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--delete-duplicates", action="store_true")
    ap.add_argument("--normalize-two-digits", action="store_true")
    args = ap.parse_args()

    cwd = Path.cwd().resolve()  # erwartet: <repo>/wissen
    csv_path = (cwd / args.csv).resolve()
    de_root  = (cwd / args.de_root).resolve()
    en_root  = (cwd / args.en_root).resolve()

    assert csv_path.exists(), f"CSV not found: {csv_path}"
    assert de_root.exists(), f"DE root not found: {de_root}"
    assert en_root.exists(), f"EN root not found: {en_root}"

    rows = read_csv_rows(csv_path)

    actions: List[str] = []
    errors:  List[str] = []
    created: List[str] = []
    updated: List[str] = []
    moved:   List[str] = []
    copied:  List[str] = []

    for row in rows:
        data, errs = parse_row(row)
        if errs:
            errors.append(f"{data.get('code','?')}: " + "; ".join(errs))

        code = data["code"]
        if not RE_CODE.match(code):
            continue

        # Ziel-Bundles (DE/EN)
        bundle_de = de_root / data["export_pfad_de"].strip("/") / f"{code}-{data['slug_de']}"
        bundle_en = en_root / data["export_pfad_en"].strip("/") / f"{code}-{data['slug_en']}"

        # Alte Bundles finden (DE/EN) – für aliases & Body-Übernahme
        old_bundles_de = [p for p in find_existing_bundles(de_root, code) if p.resolve() != bundle_de.resolve()]
        old_bundles_en = [p for p in find_existing_bundles(en_root, code) if p.resolve() != bundle_en.resolve()]

        # Aliases aus alten Orten ermitteln
        aliases_de: List[str] = []
        for ob in old_bundles_de:
            aliases_de.append(path_to_url(de_root, ob))
        aliases_en: List[str] = []
        for ob in old_bundles_en:
            aliases_en.append(path_to_url(en_root, ob))

        # Bestehende Aliases im Ziel übernehmen
        fm_existing_de, _ = read_md(bundle_de / "index.md")
        if isinstance(fm_existing_de.get("aliases"), list):
            aliases_de.extend([str(a) for a in fm_existing_de["aliases"]])

        fm_existing_en, _ = read_md(bundle_en / "index.md")
        if isinstance(fm_existing_en.get("aliases"), list):
            aliases_en.extend([str(a) for a in fm_existing_en["aliases"]])

        # Frontmatter bauen
        fm_de = build_frontmatter(data, "de", aliases_de)
        fm_en = build_frontmatter(data, "en", aliases_en)

        # index.md schreiben (Body erhalten – bevorzugt vom Zielort)
        if args.apply:
            existed = (bundle_de / "index.md").exists()
            write_index(bundle_de, fm_de, keep_body_from=bundle_de / "index.md")
            (updated if existed else created).append(bundle_de.as_posix())

            existed = (bundle_en / "index.md").exists()
            write_index(bundle_en, fm_en, keep_body_from=bundle_en / "index.md")
            (updated if existed else created).append(bundle_en.as_posix())

        actions.append(f"ENSURE bundle: {bundle_de}")
        actions.append(f"ENSURE bundle: {bundle_en}")

        # Rekursives Einsammeln alter Bilder in DE
        sweep_recursively_for_code_images(
            de_root, code, bundle_de,
            normalize_two_digit=args.normalize_two_digits,
            delete_duplicates=args.delete_duplicates,
            log=moved
        )

        # Bilder aus liste in DE-Bundle sicherstellen (umbenennen falls nötig)
        for b in data["bilder"]:
            name = normalize_two_digits(b) if args.normalize_two_digits else b
            # Quelle: überall unter DE (falls Altlasten), ansonsten bereits im Bundle
            # Wir prüfen zuerst im Bundle selbst:
            src = None
            candidate = bundle_de / name
            if candidate.exists():
                src = candidate
            else:
                # sonst global suchen (langsamer, aber zuverlässig)
                for p in de_root.rglob(name):
                    if p.is_file():
                        src = p
                        break
            if src and (bundle_de / name).resolve() != src.resolve():
                # verschieben ins Bundle
                if args.apply:
                    move_or_delete_duplicate(src, bundle_de / name, args.delete_duplicates, moved)
                else:
                    moved.append(f"Would MOVE {src} -> {bundle_de / name}")
            else:
                # wenn gar nicht gefunden, als Fehler notieren
                if not candidate.exists():
                    errors.append(f"{code}: image missing in DE: {name}")

        # EN: Bilder 1:1 aus DE-Bundle kopieren
        for b in data["bilder"]:
            name = normalize_two_digits(b) if args.normalize_two_digits else b
            src = bundle_de / name
            dst = bundle_en / name
            if src.exists():
                if not dst.exists():
                    if args.apply:
                        ensure_dir(dst.parent)
                        shutil.copy2(src, dst)
                        copied.append(f"COPY {src} -> {dst}")
                    else:
                        copied.append(f"Would COPY {src} -> {dst}")
                else:
                    # Optional: Hash vergleichen, ansonsten belassen
                    pass
            else:
                errors.append(f"{code}: image not found in DE bundle for EN copy: {name}")

        # Alte leere Bundle-Ordner entfernen (optional)
        if args.apply:
            for ob in old_bundles_de:
                try:
                    if not any(ob.rglob("*")):
                        ob.rmdir()
                        actions.append(f"RMDIR empty old bundle: {ob}")
                except Exception:
                    pass
            for ob in old_bundles_en:
                try:
                    if not any(ob.rglob("*")):
                        ob.rmdir()
                        actions.append(f"RMDIR empty old bundle: {ob}")
                except Exception:
                    pass

    # Report schreiben
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rep = Path(args.report) if args.report else Path("scripts/reports")/f"ssot-sync-exportpfade-{ts}.md"
    ensure_dir(rep.parent)
    lines: List[str] = [
        f"# SSOT Sync Report ({ts})",
        "",
        f"CSV: {csv_path}",
        f"DE root: {de_root}",
        f"EN root: {en_root}",
        ""
    ]
    if created:
        lines += [f"## Created ({len(created)})"] + [f"- {p}" for p in created] + [""]
    if updated:
        lines += [f"## Updated ({len(updated)})"] + [f"- {p}" for p in updated] + [""]
    if moved:
        lines += [f"## Moved ({len(moved)})"] + [f"- {p}" for p in moved[:1000]] + [""]
    if copied:
        lines += [f"## Copied ({len(copied)})"] + [f"- {p}" for p in copied[:1000]] + [""]
    if actions:
        lines += [f"## Actions ({len(actions)})"] + [f"- {p}" for p in actions[:1000]] + [""]
    if errors:
        lines += [f"## Errors ({len(errors)})"] + [f"- {e}" for e in errors] + [""]

    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {rep}")

    # Exit-Code – zeige Fehler im Workflow an (PR bleibt trotzdem möglich)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
