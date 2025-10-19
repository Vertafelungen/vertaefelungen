#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ssot_sync.py  v2025-10-20-1  (export_pfad aware + Sanitizer)

Funktion
- Liest SSOT (CSV) und synchronisiert DE/EN-Produkt-Page-Bundles gemäß
  export_pfad_de / export_pfad_en:
    DE: wissen/content/de/<export_pfad_de>/<code>-<slug_de>/
    EN: wissen/content/en/<export_pfad_en>/<code>-<slug_en>/
- Schreibt sauber formatiertes Frontmatter mit ruamel.yaml (UTF-8, stabile Quotes).
- Säubert Texte konsequent (NFC, CP-1252 Smartquotes/Dashes/Ellipsis → ASCII,
  NBSP→Space, ZWSP/Steuerzeichen raus, CRLF→LF).
- Räumt Altlasten auf: sammelt verstreute Bilder rekursiv ein und verschiebt
  sie ins Ziel-Bundle (kollisionssicher, optional Duplikate löschen).
- Kopiert Bilder aus DE-Bundle 1:1 ins EN-Bundle.
- Setzt automatisch `aliases`, wenn sich der Bundle-Pfad (URL) geändert hat.
- Idempotent; vorhandene Body-Inhalte bleiben erhalten.

CLI
  Dry-Run:
    python scripts/ssot_sync.py
  Anwenden:
    python scripts/ssot_sync.py --apply
  Optionen:
    --csv pfad               (Default: ssot/SSOT.csv)
    --de-root pfad           (Default: content/de)
    --en-root pfad           (Default: content/en)
    --normalize-two-digits   (z.B. -1 → -01)
    --delete-duplicates      (identische Alt-Dateien nach Move löschen)
    --report pfad

Exit-Code
- 0: OK  (Report geschrieben)
- 1: Warn-/Fehlerliste vorhanden (Details im Report/STDERR)
"""

from __future__ import annotations
import argparse, csv, re, shutil, sys, hashlib, unicodedata
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from ruamel.yaml import YAML

# ---------- Konstanten ----------

RE_CODE   = re.compile(r"^[psw]\d{4}$", re.I)
RE_BUNDLE = re.compile(r"^[psw]\d{4}-.+$", re.I)
IMG_NAME  = re.compile(r"^[psw]\d{4}-(\d{1,2})\.(png|jpg|jpeg|webp|avif)$", re.I)
IMG_EXTS  = {".png", ".jpg", ".jpeg", ".webp", ".avif"}

ZWSP_CODES = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}  # ZWSP/ZWNJ/ZWJ/WORD JOINER/BOM
KEEP_CTRL  = {0x0009, 0x000A}  # Tab, LF ok

CP1252_MAP = {
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x2039: "<", 0x203A: ">",
    0x201C: '"', 0x201D: '"', 0x201E: '"',
    0x2013: "-",  0x2014: "-",  0x2212: "-",   # en/em dash, minus
    0x2026: "...",                            # ellipsis
    0x00A0: " ",                              # NBSP
}

# ---------- Utilities ----------

def yaml_emitter() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.explicit_start = False
    y.width = 4096
    return y

def clean_text(s: str) -> str:
    """Unicode-NFC, CP-1252-Fixes, ZWSP/Steuerzeichen raus, EOL vereinheitlichen, Trim."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s)).replace("\r\n", "\n").replace("\r", "\n")
    s = "".join(CP1252_MAP.get(ord(ch), ch) for ch in s)
    s = "".join(ch for ch in s if (ord(ch) not in ZWSP_CODES and (ord(ch) >= 32 or ord(ch) in KEEP_CTRL)))
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    return s.strip()

def slugify_ascii(s: str) -> str:
    s = clean_text(s).lower()
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
    t = clean_text(v).lower()
    if t in {"true","1","yes","ja","y"}: return True
    if t in {"false","0","no","nein","n"}: return False
    return None

def to_int(v: str) -> Optional[int]:
    try:
        return int(clean_text(v))
    except Exception:
        return None

def normalize_two_digits(name: str) -> str:
    m = IMG_NAME.match(name)
    if not m: return name
    num = m.group(1)
    if len(num) == 1:
        return re.sub(r"-(\d)\.", r"-0\1.", name)
    return name

def ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

def file_sha1(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def read_csv_rows(path: Path) -> List[Dict[str,str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def split_frontmatter(md_text: str) -> Tuple[Dict, str]:
    if md_text.startswith("---"):
        parts = md_text.split("\n---", 1)
        if len(parts) == 2:
            fm_raw = parts[0][3:]
            body = parts[1].lstrip("\n")
            y = yaml_emitter()
            try:
                fm = y.load(fm_raw) or {}
                if not isinstance(fm, dict): fm = {}
            except Exception:
                fm = {}
            return fm, body
    return {}, md_text

def read_md(path: Path) -> Tuple[Dict, str]:
    if not path.exists(): return {}, ""
    txt = path.read_text(encoding="utf-8", errors="replace")
    return split_frontmatter(txt)

def write_index(bundle_dir: Path, fm_new: Dict, keep_body_from: Optional[Path]):
    ensure_dir(bundle_dir)
    idx = bundle_dir / "index.md"
    body = ""
    if keep_body_from and keep_body_from.exists():
        _, body = read_md(keep_body_from)
        body = clean_text(body)
    elif idx.exists():
        _, body = read_md(idx)
        body = clean_text(body)
    y = yaml_emitter()
    from io import StringIO
    sio = StringIO()
    y.dump(fm_new, sio)
    fm_text = "---\n" + sio.getvalue().rstrip() + "\n---\n"
    idx.write_text(fm_text + (body if body else ""), encoding="utf-8")

def path_to_url(content_lang_root: Path, bundle_dir: Path) -> str:
    rel = bundle_dir.relative_to(content_lang_root).as_posix().strip("/")
    lang = content_lang_root.name.lower()
    return f"/wissen/{lang}/{rel}/"

def find_existing_bundles(content_lang_root: Path, code: str) -> List[Path]:
    hits = []
    for p in content_lang_root.rglob(f"{code}-*"):
        if p.is_dir() and RE_BUNDLE.match(p.name):
            hits.append(p)
    return hits

def move_or_delete_duplicate(src: Path, dst: Path, delete_duplicates: bool, log: List[str]):
    if not src.exists(): return
    if dst.exists():
        try:
            if file_sha1(src) == file_sha1(dst):
                if delete_duplicates:
                    src.unlink()
                    log.append(f"DELETE duplicate {src}")
                else:
                    log.append(f"SKIP duplicate {src} ~ {dst}")
                return
            else:
                stem, ext = dst.stem, dst.suffix
                i = 2
                while True:
                    cand = dst.with_name(f"{stem}-{i}{ext}")
                    if not cand.exists():
                        shutil.move(str(src), str(cand))
                        log.append(f"RENAME-MOVE {src} -> {cand}")
                        return
                    i += 1
        except Exception:
            log.append(f"SKIP collision (no hash) {src} ~ {dst}")
            return
    ensure_dir(dst.parent)
    shutil.move(str(src), str(dst))
    log.append(f"MOVE {src} -> {dst}")

def sweep_recursively_for_code_images(content_lang_root: Path, code: str, target_bundle: Path,
                                      normalize_two_digit: bool, delete_duplicates: bool,
                                      log: List[str]):
    for p in content_lang_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS and p.name.lower().startswith(f"{code}-"):
            try:
                p.relative_to(target_bundle)
                continue
            except ValueError:
                pass
            name = p.name
            if normalize_two_digit:
                name = normalize_two_digits(name)
            dst = target_bundle / name
            move_or_delete_duplicate(p, dst, delete_duplicates, log)

# ---------- SSOT-Parsing ----------

def parse_row(row: Dict[str,str]) -> Tuple[Dict[str,object], List[str]]:
    errs: List[str] = []
    code = clean_text((row.get("code") or row.get("produkt_code") or "")).lower()
    if not RE_CODE.match(code):
        errs.append(f"invalid code '{code}'")

    slug_de = clean_text(row.get("slug_de") or "")
    slug_en = clean_text(row.get("slug_en") or "")
    if not slug_de: slug_de = slugify_ascii(row.get("title_de") or row.get("titel_de") or "")
    if not slug_en: slug_en = slugify_ascii(row.get("title_en") or row.get("titel_en") or "")

    exp_de = clean_text(row.get("export_pfad_de") or "").strip().strip("/")
    exp_en = clean_text(row.get("export_pfad_en") or "").strip().strip("/")
    if not exp_de: errs.append("missing export_pfad_de")
    if not exp_en: errs.append("missing export_pfad_en")

    bilder_raw = clean_text(row.get("bilder_liste") or row.get("bilder") or "")
    bilder = [b.strip() for b in bilder_raw.split(",") if b.strip()]
    really_bad = [b for b in bilder if not re.match(r"^[psw]\d{4}-\d+\.", b, re.I)]
    if really_bad:
        errs.append(f"invalid image names: {', '.join(really_bad)}")

    title_de = clean_text(row.get("title_de") or row.get("titel_de") or "") or code.upper()
    title_en = clean_text(row.get("title_en") or row.get("titel_en") or "") or f"{code.upper()} – TODO English title"
    desc_de  = clean_text(row.get("description_de") or row.get("beschreibung_de") or "")
    desc_en  = clean_text(row.get("description_en") or "")

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
    desc = data["description_de"] if lang=="de" else data["description_en"]
    if desc:
        fm["description"] = desc
    if data["bilder"]:
        fm["bilder"] = [normalize_two_digits(b) for b in data["bilder"]]
    if aliases:
        fm["aliases"] = sorted(set(aliases))
    return fm

# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/SSOT.csv")
    ap.add_argument("--de-root", default="content/de")
    ap.add_argument("--en-root", default="content/en")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--normalize-two-digits", action="store_true")
    ap.add_argument("--delete-duplicates", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    cwd = Path.cwd().resolve()  # erwartet: <repo>/wissen
    csv_path = (cwd / args.csv).resolve()
    de_root  = (cwd / args.de_root).resolve()
    en_root  = (cwd / args.en_root).resolve()

    assert csv_path.exists(), f"CSV not found: {csv_path}"
    assert de_root.exists(),  f"DE root not found: {de_root}"
    assert en_root.exists(),  f"EN root not found: {en_root}"

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

        bundle_de = de_root / data["export_pfad_de"] / f"{code}-{data['slug_de']}"
        bundle_en = en_root / data["export_pfad_en"] / f"{code}-{data['slug_en']}"

        old_bundles_de = [p for p in find_existing_bundles(de_root, code) if p.resolve() != bundle_de.resolve()]
        old_bundles_en = [p for p in find_existing_bundles(en_root, code) if p.resolve() != bundle_en.resolve()]

        aliases_de = [path_to_url(de_root, ob) for ob in old_bundles_de]
        aliases_en = [path_to_url(en_root, ob) for ob in old_bundles_en]

        fm_existing_de, _ = read_md(bundle_de / "index.md")
        if isinstance(fm_existing_de.get("aliases"), list):
            aliases_de.extend([clean_text(a) for a in fm_existing_de["aliases"]])

        fm_existing_en, _ = read_md(bundle_en / "index.md")
        if isinstance(fm_existing_en.get("aliases"), list):
            aliases_en.extend([clean_text(a) for a in fm_existing_en["aliases"]])

        fm_de = build_frontmatter(data, "de", aliases_de)
        fm_en = build_frontmatter(data, "en", aliases_en)

        if args.apply:
            existed = (bundle_de / "index.md").exists()
            write_index(bundle_de, fm_de, keep_body_from=bundle_de / "index.md")
            (updated if existed else created).append(bundle_de.as_posix())

            existed = (bundle_en / "index.md").exists()
            write_index(bundle_en, fm_en, keep_body_from=bundle_en / "index.md")
            (updated if existed else created).append(bundle_en.as_posix())

        actions.append(f"ENSURE bundle: {bundle_de}")
        actions.append(f"ENSURE bundle: {bundle_en}")

        # Bilder (DE) – Altlasten einsammeln
        sweep_recursively_for_code_images(
            de_root, code, bundle_de,
            normalize_two_digit=args.normalize_two_digits,
            delete_duplicates=args.delete_duplicates,
            log=moved
        )

        # Bilder laut Liste (DE) ins Bundle sicherstellen
        for b in data["bilder"]:
            name = normalize_two_digits(b) if args.normalize_two_digits else b
            target = bundle_de / name
            if target.exists():
                continue
            # Quelle suchen (Bundle zuerst, dann global)
            src = None
            for p in [bundle_de] + list(de_root.rglob("")):
                cand = p / name if p == bundle_de else None
                if cand and cand.exists():
                    src = cand; break
            if not src:
                for p in de_root.rglob(name):
                    if p.is_file(): src = p; break
            if src:
                if args.apply:
                    move_or_delete_duplicate(src, target, args.delete_duplicates, moved)
                else:
                    moved.append(f"Would MOVE {src} -> {target}")
            else:
                errors.append(f"{code}: image missing in DE: {name}")

        # EN: Bilder 1:1 aus DE kopieren
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
                errors.append(f"{code}: image not found in DE bundle for EN copy: {name}")

        # Alte leere Bundles wegräumen
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

    # Report
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rep = Path(args.report) if args.report else Path("scripts/reports")/f"ssot-sync-exportpfade-{ts}.md"
    ensure_dir(rep.parent)
    lines: List[str] = [
        f"# SSOT Sync Report ({ts})",
        "", f"CSV: {csv_path}",
        f"DE root: {de_root}", f"EN root: {en_root}", ""
    ]
    if created: lines += [f"## Created ({len(created)})"] + [f"- {p}" for p in created] + [""]
    if updated: lines += [f"## Updated ({len(updated)})"] + [f"- {p}" for p in updated] + [""]
    if moved:   lines += [f"## Moved ({len(moved)})"] + [f"- {p}" for p in moved[:1000]] + [""]
    if copied:  lines += [f"## Copied ({len(copied)})"] + [f"- {p}" for p in copied[:1000]] + [""]
    if actions: lines += [f"## Actions ({len(actions)})"] + [f"- {p}" for p in actions[:1000]] + [""]
    if errors:  lines += [f"## Errors ({len(errors)})"] + [f"- {e}" for e in errors] + [""]

    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {rep}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
