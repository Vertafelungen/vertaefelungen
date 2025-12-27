#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSOT → Hugo Page Bundles (mit Produktdaten, Varianten, Bildern, SEO)
Version: 2025-12-27 16:00 Europe/Berlin

Dieses Skript baut/aktualisiert alle Produktseiten unter:
  wissen/content/de/…  und  wissen/content/en/…

Es macht konkret:
- Liest wissen/ssot/SSOT.csv (Single Source of Truth)
- Baut für jedes Produkt den Zielordner anhand von export_pfad_de / export_pfad_en
- Kopiert Bilder AUSSCHLIESSLICH aus wissen/ssot/bilder in die jeweiligen Bundles
  (Dateinamen bleiben UNVERÄNDERT, Mehrfachverwendung wie vsfp.png ist erlaubt)
- Schreibt alle Produktinfos strukturiert in die Frontmatter:
    title, lang, translationKey, managed_by, last_synced
    produkt:  { id, slug, verfuegbar, preis_basis, varianten[], bilder[] }
    seo:      { meta_title, meta_description, robots, canonical, og_image, is_public }
    refs:     { source_shop }
    aliases: (alte URLs, falls Bundle verschoben)
- Schreibt die Produktbeschreibung aus der SSOT als Markdown-Body
- Erzeugt/aktualisiert Kategorie-_index.md NUR, wenn managed_by != "categories.csv" (Schutz vor Überschreiben durch Kategorien-Generator)

Preis-Handling für Varianten:
- alte Schreibweise in SSOT: preis_aufschlag: 102350000   → bedeutet 102,35 €
- neue gewünschte Schreibweise: preis_aufschlag: 102.35   → bedeutet 102,35 €
Beides wird unterstützt.

Hinweise:
- Das Skript überschreibt den Body nur, wenn der Body aktuell leer ist oder managed_by mit "ssot-sync" beginnt.
- Für Kategorie-_index.md gilt zusätzlich ein harter Guard: wenn managed_by == "categories.csv", wird NICHT geschrieben.
"""

from __future__ import annotations
import argparse, csv, io, re, shutil, sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from ruamel.yaml import YAML

yaml = YAML()
yaml.default_flow_style = False
yaml.allow_unicode = True
yaml.width = 4096

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif"}


# Wenn eine _index.md bereits durch den Kategorien-Generator verwaltet wird,
# darf dieses Produkt-Sync-Skript sie NICHT überschreiben.
CATEGORY_INDEX_MANAGED_BY = "categories.csv"

# ---------- CSV / Text Utils ----------

def _normkey(k: str) -> str:
    s = (k or "").strip()
    s = s.replace("\ufeff","")
    s = s.strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = s.replace("__","_")
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

def split_multi_list(val: str) -> List[str]:
    parts = re.split(r"[,\n;|]", val or "")
    return [p.strip() for p in parts if p.strip()]

def parse_bool(val: str) -> bool:
    v = (val or "").strip().lower()
    return v in {"1","true","yes","ja","y","available","verfügbar","verfuegbar","lieferbar"}

def parse_float(val: str) -> Optional[float]:
    v = clean(val)
    if not v:
        return None
    v = v.replace(",", ".")
    try:
        return float(v)
    except Exception:
        return None

def parse_price_aufschlag_value(raw_val: str) -> Optional[float]:
    """
    Macht aus preis_aufschlag einen float in Euro.
    Unterstützt:
      - "102350000" (alt, Cent*1e6)  -> 102.35
      - "102.35" oder "102,35"       -> 102.35
    """
    v = clean(raw_val)
    if not v:
        return None

    # wenn nur Ziffern (altformat)
    if re.fullmatch(r"\d+", v):
        try:
            i = int(v)
            return (i / 1000000.0) / 100.0 * 100.0  # i / 1e6 = Euro? -> historisch: 102350000 -> 102.35
        except Exception:
            return None

    # normal float
    f = parse_float(v)
    return f

# ---------- Frontmatter / Markdown ----------

def read_frontmatter_and_body(p: Path) -> Tuple[Dict, str]:
    if not p.exists():
        return {}, ""
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
    buf = io.StringIO()
    yaml.dump(fm, buf)
    return "---\n" + buf.getvalue().strip() + "\n---\n"

def merge_frontmatter(existing: Dict, updates: Dict) -> Dict:
    out = dict(existing or {})
    for k, v in (updates or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_frontmatter(out.get(k, {}), v)
        else:
            out[k] = v
    return out

def write_page(
    bundle_dir: Path,
    filename: str,
    fm_updates: Dict,
    body_new: Optional[str],
    managed_prefix_check: str = "ssot-sync",
) -> None:
    """
    Schreibt bundle_dir/filename (index.md oder _index.md):
    - Frontmatter wird gemergt.
    - Body wird überschrieben, falls
        a) leer ODER
        b) managed_by beginnt mit "ssot-sync".
      Sonst bleibt der Body unangetastet.
    """
    bundle_dir.mkdir(parents=True, exist_ok=True)
    target = bundle_dir / filename

    fm_exist, body_exist = read_frontmatter_and_body(target)

    # Guard: Kategorie-_index.md wird ausschließlich aus categories.csv generiert.
    # Regel: nur schreiben, wenn managed_by != "categories.csv".
    if filename == "_index.md" and str(fm_exist.get("managed_by", "")).strip() == CATEGORY_INDEX_MANAGED_BY:
        return

    # Body-Entscheidung
    if body_new is not None:
        overwrite_allowed = (not body_exist.strip()) or str(fm_exist.get("managed_by","")).startswith(managed_prefix_check)
        if overwrite_allowed:
            body_final = (body_new.strip() + "\n") if body_new.strip() else ""
        else:
            body_final = body_exist
    else:
        body_final = body_exist

    # Frontmatter mergen
    fm_merged = merge_frontmatter(fm_exist, fm_updates)
    target.write_text(dump_frontmatter(fm_merged) + body_final, encoding="utf-8")


# ---------- Paths, URLs, Images ----------

PK_REGEX = re.compile(r"^(p\d{3,5}|sl\d{3,5}|wl\d{3,5}|tr\d{3,5}|l\d{3,5}|s\d{3,5})", re.IGNORECASE)

def bundle_url(content_lang_root: Path, bundle_dir: Path) -> str:
    rel = bundle_dir.relative_to(content_lang_root).as_posix().strip("/")
    return "/" + rel + "/"

def ensure_copy_image(img_root: Path, src_name: str, dest_dir: Path) -> Optional[str]:
    src_name = clean(src_name)
    if not src_name:
        return None
    src = img_root / src_name
    if not src.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src_name
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return dest.name
    shutil.copy2(src, dest)
    return dest.name

def guess_key_from_slug(slug: str) -> str:
    m = PK_REGEX.match(slug or "")
    if m:
        return m.group(1).lower()
    return (slug or "").lower().strip()

def parse_variants_yaml(val: str) -> List[Dict]:
    v = clean(val)
    if not v:
        return []
    try:
        data = yaml.load(v)
        if isinstance(data, list):
            out = []
            for it in data:
                if isinstance(it, dict):
                    out.append(it)
            return out
    except Exception:
        pass
    return []

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="SSOT.csv → Hugo Product Bundles (export_pfad)")
    ap.add_argument("--csv", default="wissen/ssot/SSOT.csv", help="Pfad zur SSOT.csv")
    ap.add_argument("--de-root", default="wissen/content/de", help="DE Content Root")
    ap.add_argument("--en-root", default="wissen/content/en", help="EN Content Root")
    ap.add_argument("--img-root", default="wissen/ssot/bilder", help="Bilderquelle (SSOT)")
    ap.add_argument("--apply", action="store_true", help="Schreiben/Ändern aktivieren (sonst Dry-Run)")
    ap.add_argument("--report", default="", help="Pfad für Report.md")
    args = ap.parse_args(argv)

    csv_path = Path(args.csv)
    de_root = Path(args.de_root)
    en_root = Path(args.en_root)
    img_root = Path(args.img_root)

    if not csv_path.exists():
        print(f"[ERROR] CSV not found: {csv_path}", file=sys.stderr)
        return 2

    rows = read_csv_utf8_auto(csv_path)
    now = datetime.utcnow()
    last_synced_str = now.strftime("%Y-%m-%d %H:%M UTC")

    created, updated, moved = [], [], []

    # Tracks which category sections exist (derived from products)
    seen_sections_de: Dict[str, Path] = {}
    seen_sections_en: Dict[str, Path] = {}

    for r in rows:
        # Minimalfelder
        pid = clean(r.get("product_id") or r.get("id") or "")
        slug_de = clean(r.get("slug_de") or "")
        slug_en = clean(r.get("slug_en") or "")
        export_de = clean(r.get("export_pfad_de") or "")
        export_en = clean(r.get("export_pfad_en") or "")

        if not slug_de or not export_de:
            # kein DE = kein Produkt
            continue
        if not slug_en or not export_en:
            # EN darf fehlen, aber wir erwarten i.d.R. beide
            slug_en = slug_de
            export_en = export_de

        # Zielordner
        bundle_de = de_root / export_de.strip("/") / slug_de
        bundle_en = en_root / export_en.strip("/") / slug_en

        # Basisdaten
        key = guess_key_from_slug(slug_de)
        title_de = clean(r.get("titel_de") or r.get("title_de") or "")
        title_en = clean(r.get("titel_en") or r.get("title_en") or "")
        desc_md_de = r.get("beschreibung_md_de") or r.get("body_md_de") or ""
        desc_md_en = r.get("beschreibung_md_en") or r.get("body_md_en") or ""
        meta_title_de = clean(r.get("meta_title_de") or "")
        meta_title_en = clean(r.get("meta_title_en") or "")
        meta_desc_de  = clean(r.get("meta_description_de") or "")
        meta_desc_en  = clean(r.get("meta_description_en") or "")
        verf = parse_bool(r.get("verfuegbar") or r.get("verfügbar") or r.get("available") or "")

        # Preis Basis (optional)
        preis_basis = parse_float(r.get("price") or r.get("preis") or "")
        currency = clean(r.get("currency") or "EUR") or "EUR"

        # Varianten
        variants = parse_variants_yaml(r.get("varianten_yaml") or r.get("variants_yaml") or "")
        # ggf. preis_aufschlag normalisieren
        for v in variants:
            pa = v.get("preis_aufschlag", None)
            if pa is not None:
                norm = parse_price_aufschlag_value(str(pa))
                if norm is not None:
                    v["preis_aufschlag"] = float(norm)

        # Bilder (aus SSOT)
        bilder = []
        bilder_liste = split_multi_list(r.get("bilder_liste") or r.get("bilder") or "")
        alt_de_list = split_multi_list(r.get("bilder_alt_de") or "")
        alt_en_list = split_multi_list(r.get("bilder_alt_en") or "")

        # Bilder kopieren: Name muss exakt stimmen
        copied_de = []
        copied_en = []
        for i, b in enumerate(bilder_liste):
            copied_name_de = ensure_copy_image(img_root, b, bundle_de) if args.apply else b
            copied_name_en = ensure_copy_image(img_root, b, bundle_en) if args.apply else b
            if copied_name_de:
                copied_de.append(copied_name_de)
            if copied_name_en:
                copied_en.append(copied_name_en)

            # Alttexte mappen, best effort
            alt_de = alt_de_list[i] if i < len(alt_de_list) else ""
            alt_en = alt_en_list[i] if i < len(alt_en_list) else ""
            bilder.append({
                "datei": b,
                "alt_de": alt_de,
                "alt_en": alt_en,
            })

        # Aliases (alte URLs)
        alias_de = split_multi_list(r.get("aliases_de") or r.get("alias_de") or "")
        alias_en = split_multi_list(r.get("aliases_en") or r.get("alias_en") or "")

        # Referenzen
        refs_de = {"source_shop": clean(r.get("ref_shop_de") or r.get("ref_shop") or "")}
        refs_en = {"source_shop": clean(r.get("ref_shop_en") or r.get("ref_shop") or "")}

        # SEO objects
        seo_de = {
            "meta_title": meta_title_de or title_de,
            "meta_description": meta_desc_de or "",
            "robots": clean(r.get("robots") or "index,follow"),
            "canonical": clean(r.get("canonical_de") or ""),
            "og_image": clean(r.get("og_image") or ""),
            "is_public": True,
        }
        seo_en = {
            "meta_title": meta_title_en or title_en,
            "meta_description": meta_desc_en or "",
            "robots": clean(r.get("robots") or "index,follow"),
            "canonical": clean(r.get("canonical_en") or ""),
            "og_image": clean(r.get("og_image") or ""),
            "is_public": True,
        }

        produkt_de = {
            "id": pid or key,
            "slug": slug_de,
            "verfuegbar": verf,
            "preis_basis": preis_basis,
            "currency": currency,
            "varianten": variants,
            "bilder": bilder,
        }
        produkt_en = {
            "id": pid or key,
            "slug": slug_en,
            "verfuegbar": verf,
            "preis_basis": preis_basis,
            "currency": currency,
            "varianten": variants,
            "bilder": bilder,
        }

        # Frontmatter updates
        fm_de_updates = {
            "title": title_de or slug_de,
            "lang": "de",
            "translationKey": key,
            "managed_by": "ssot-sync",
            "last_synced": last_synced_str,
            "produkt": produkt_de,
            "seo": seo_de,
            "refs": refs_de,
        }
        if alias_de:
            fm_de_updates["aliases"] = sorted(set(alias_de))

        fm_en_updates = {
            "title": title_en or slug_en,
            "lang": "en",
            "translationKey": key,
            "managed_by": "ssot-sync",
            "last_synced": last_synced_str,
            "produkt": produkt_en,
            "seo": seo_en,
            "refs": refs_en,
        }
        if alias_en:
            fm_en_updates["aliases"] = sorted(set(alias_en))

        # index.md schreiben (inkl. Body aus beschreibung_md_de / _en)
        if args.apply:
            existed = (bundle_de / "index.md").exists()
            write_page(
                bundle_de,
                "index.md",
                fm_de_updates,
                desc_md_de,
                managed_prefix_check="ssot-sync",
            )
            if existed:
                updated.append(str(bundle_de / "index.md"))
            else:
                created.append(str(bundle_de / "index.md"))

            existed = (bundle_en / "index.md").exists()
            write_page(
                bundle_en,
                "index.md",
                fm_en_updates,
                desc_md_en,
                managed_prefix_check="ssot-sync",
            )
            if existed:
                updated.append(str(bundle_en / "index.md"))
            else:
                created.append(str(bundle_en / "index.md"))

        # Kategorie-Seiten (abgeleitet aus export_pfad_*) tracken
        section_dir_de = de_root / export_de.strip("/")
        section_dir_en = en_root / export_en.strip("/")
        seen_sections_de[export_de.strip("/")] = section_dir_de
        seen_sections_en[export_en.strip("/")] = section_dir_en

    # Kategorie-_index.md erzeugen/aktualisieren (Landingpages) – mit Guard (managed_by != categories.csv)
    # Hinweis: Wenn categories.csv der Owner ist, werden diese _index.md dort bereits generiert
    for rel, section_dir in sorted(seen_sections_de.items()):
        cat_slug = rel.split("/")[-1] if rel else "produkte"
        fm_cat_de = {
            "title": cat_slug.replace("-", " ").title(),
            "lang": "de",
            "managed_by": "ssot-sync",
            "last_synced": last_synced_str,
            "kategorie_slug": cat_slug,
        }
        cat_body = ""
        if args.apply:
            existed = (section_dir / "_index.md").exists()
            write_page(
                section_dir,
                "_index.md",
                fm_cat_de,
                cat_body,
                managed_prefix_check="ssot-sync",
            )
            if existed:
                updated.append(str(section_dir / "_index.md"))
            else:
                created.append(str(section_dir / "_index.md"))

    for rel, section_dir in sorted(seen_sections_en.items()):
        cat_slug = rel.split("/")[-1] if rel else "products"
        fm_cat_en = {
            "title": cat_slug.replace("-", " ").title(),
            "lang": "en",
            "managed_by": "ssot-sync",
            "last_synced": last_synced_str,
            "kategorie_slug": cat_slug,
        }
        cat_body = ""
        if args.apply:
            existed = (section_dir / "_index.md").exists()
            write_page(
                section_dir,
                "_index.md",
                fm_cat_en,
                cat_body,
                managed_prefix_check="ssot-sync",
            )
            if existed:
                updated.append(str(section_dir / "_index.md"))
            else:
                created.append(str(section_dir / "_index.md"))

    # Report schreiben
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    rep = Path(args.report) if args.report else Path("scripts/reports")/f"ssot-sync-exportpfad-{ts}.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# SSOT Sync Report ({ts})", "",
        f"CSV: {csv_path}", f"DE root: {de_root}", f"EN root: {en_root}", f"IMG root: {img_root}", ""
    ]
    if created:    lines += ["## Created"] + [f"- {p}" for p in created] + [""]
    if updated:    lines += ["## Updated"] + [f"- {p}" for p in updated] + [""]
    if moved:      lines += ["## Moved"] + [f"- {p}" for p in moved] + [""]

    rep.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"[OK] Report: {rep}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
