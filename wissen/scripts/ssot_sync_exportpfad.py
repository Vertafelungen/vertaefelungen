#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSOT → Hugo Page Bundles (mit Produktdaten, Varianten, Bildern, SEO)
Version: 2025-10-27 06:00 Europe/Berlin

Dieses Skript baut/aktualisiert alle Produktseiten unter:
  wissen/content/de/…  und  wissen/content/en/…

Es macht konkret:
- Liest wissen/ssot/SSOT.csv (Single Source of Truth)
- Baut für jedes Produkt den Zielordner anhand von export_pfad_de / export_pfad_en
- Kopiert Bilder AUSSCHLIESSLICH aus wissen/ssot/bilder in die jeweiligen Bundles
  (Dateinamen bleiben UNVERÄNDERT, Mehrfachverwendung wie vsfp.png ist erlaubt)
- Schreibt alle Produktinfos strukturiert in die Frontmatter:
    title, lang, translationKey, managed_by, last_synced
    produkt: { id, artikelnummer, verfuegbar, preis_basis, varianten[], bilder[] }
    seo:     { title, description, tags }
    refs:    { source_shop }
    aliases: (alte URLs, falls Bundle verschoben)
- Schreibt die Produktbeschreibung aus der SSOT als Markdown-Body
- Erzeugt/aktualisiert Kategorie-_index.md für jede export_pfad_* (Landingpages)

Preis-Handling für Varianten:
- alte Schreibweise in SSOT: preis_aufschlag: 102350000   → bedeutet 102,35 €
- neue gewünschte Schreibweise: preis_aufschlag: 102.35   → direkt in €
Das Skript erkennt beides und schreibt immer float mit 2 Nachkommastellen.

Wichtig:
- Body wird nur überschrieben, wenn er leer ist ODER managed_by mit "ssot-sync" beginnt.
- Wir überschreiben keine manuell gepflegten Texte von Hand.
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
    except ValueError:
        return None


# ---------- Varianten / Preis-Normalisierung ----------

def parse_varianten_yaml(txt: str):
    """
    Liest das YAML aus der Spalte varianten_yaml.
    Rückgabe ist eine Liste von Dicts (eine Variante pro Dict).
    """
    txt = clean(txt)
    if not txt:
        return []
    try:
        data = yaml.load(txt)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Fallback: einzelne Variante als Dict
            return [data]
        return []
    except Exception:
        return []

def normalize_preis_value(raw_val):
    """
    Macht aus preis_aufschlag einen float in Euro.
    Fälle:
      - "102.35"      → 102.35
      - "102,35"      → 102.35
      - 102350000     → 102.35 (alte SSOT-Logik: Mikro-Euro / *1e6)
      - 365780000     → 365.78
    Heuristik:
      - Wenn der Wert sehr groß ist (>= 100000), interpretieren wir ihn als mikro-€ (divide by 1_000_000).
      - Sonst normal float().
    """
    if raw_val is None:
        return None

    # Wenn's schon ein echter number-Typ ist:
    if isinstance(raw_val, (int, float)):
        num = float(raw_val)
        if num >= 100000:
            return round(num / 1_000_000.0, 2)
        return round(num, 2)

    # Falls String:
    s = str(raw_val).strip()
    if not s:
        return None

    # Währungsreste und Komma → Punkt
    s_clean = (
        s.replace("€","")
         .replace("eur","")
         .replace("EUR","")
         .replace(",", ".")
         .strip()
    )

    # Versuchen, erst als int → dann ggf. teilen
    try:
        as_int = int(s_clean)
        if as_int >= 100000:
            return round(as_int / 1_000_000.0, 2)
        return round(float(as_int), 2)
    except ValueError:
        pass

    # Dann als float
    try:
        as_float = float(s_clean)
        if as_float >= 100000:
            return round(as_float / 1_000_000.0, 2)
        return round(as_float, 2)
    except ValueError:
        return None

def normalize_variant_prices(variants):
    """
    Läuft über die Varianten-Liste und wandelt preis_aufschlag ins neue Schema.
    Beispiel in der SSOT:
      - bezeichnung: "Eiche, Bausatz"
        preis_aufschlag: 365780000   # => 365.78
    Ziel:
      preis_aufschlag: 365.78
    """
    out = []
    for v in variants:
        if isinstance(v, dict):
            vv = dict(v)
            if "preis_aufschlag" in vv:
                vv["preis_aufschlag"] = normalize_preis_value(vv.get("preis_aufschlag"))
            out.append(vv)
        else:
            # Falls irgendein Altformat kein Dict ist
            out.append(v)
    return out


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
    from io import StringIO
    s = StringIO()
    yaml.dump(fm, s)
    return "---\n" + s.getvalue().rstrip() + "\n---\n"

def merge_frontmatter(existing: Dict, updates: Dict) -> Dict:
    """
    - 'aliases' wird vereinigt.
    - Alle anderen Keys aus updates überschreiben existing komplett.
    Das gilt auch für verschachtelte Dicts wie 'produkt', 'seo', 'refs'.
    """
    out = dict(existing or {})

    # aliases mergen (ohne Duplikate)
    if "aliases" in updates:
        new_aliases = list(dict.fromkeys([str(a) for a in (updates.get("aliases") or [])]))
        old_aliases = out.get("aliases") or []
        if isinstance(old_aliases, list):
            combo = list(dict.fromkeys([str(a) for a in (old_aliases + new_aliases)]))
        else:
            combo = new_aliases
        out["aliases"] = combo

    for k, v in updates.items():
        if k == "aliases":
            continue
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
    lang = content_lang_root.name.lower()
    return f"/wissen/{lang}/{rel}/"

def find_existing_bundles(content_lang_root: Path, pk: str) -> List[Path]:
    hits = []
    for p in content_lang_root.rglob(f"{pk}-*"):
        if p.is_dir():
            hits.append(p)
    return hits

def list_all_images(root: Path) -> Dict[str, List[Path]]:
    from collections import defaultdict
    m = defaultdict(list)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            m[p.name.lower()].append(p)
    return m

def candidate_names(original: str) -> List[str]:
    """
    Bild-Namensvarianten:
    - exakt
    - 1-stellig ↔ 2-stellig (p0018-1.png ↔ p0018-01.png)
    - '-' ↔ '_' vor der Nummer
    - alternative Extensions
    Wichtig: wir BENENNEN NIE UM. Wir suchen nur flexibler.
    """
    name = original
    stem, dot, ext = name.rpartition(".")
    ext = ext or ""
    base_noext = stem if dot else name
    out = set()

    out.add(original.lower())

    m = re.search(r"([_-])(\d{1,2})$", base_noext)
    if m:
        sep, num = m.group(1), m.group(2)
        # 1-stellig → 2-stellig
        if len(num) == 1:
            out.add((base_noext[:-1] + "0" + num + (("." + ext) if ext else "")).lower())
        # 2-stellig mit führender 0 → 1-stellig
        if len(num) == 2 and num.startswith("0"):
            out.add((base_noext[:-2] + num[1:] + (("." + ext) if ext else "")).lower())
        # '-' ↔ '_'
        other_sep = "_" if sep == "-" else "-"
        alt_name2 = base_noext[:m.start(1)] + other_sep + num + (("." + ext) if ext else "")
        out.add(alt_name2.lower())

    # alternative Extensions
    for e in ["png","jpg","jpeg","webp","avif","gif"]:
        if ext.lower() != e:
            out.add((base_noext + "." + e).lower())

    return list(out)

def find_source_by_candidates(index: Dict[str, List[Path]], root: Path, name: str) -> Optional[Path]:
    # zuerst versuchen wir die index-Hits
    for cand in [name.lower()] + candidate_names(name):
        for p in index.get(cand, []):
            if p.exists():
                return p
    # fallback globale Suche
    for cand in [name] + candidate_names(name):
        hits = list(root.rglob(cand))
        if hits:
            return hits[0]
    return None

def existing_variant_in_bundle(bundle: Path, name: str) -> Optional[str]:
    # exakt?
    if (bundle / name).exists():
        return name
    # Kandidatenvarianten?
    for cand in candidate_names(name):
        if (bundle / cand).exists():
            return cand
    return None


# ---------- Produkt-Key / Kategorie ----------

def get_pk(row: Dict[str,str]) -> str:
    """
    Liefert den Schlüssel (z. B. "23"), der als translationKey dient
    und den ersten Teil des Bundle-Ordners bildet.
    """
    v = clean(row.get("product_id"))
    if v:
        return v.lower()
    v = clean(row.get("reference"))
    if v:
        return v.lower()

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

def derive_category_title(raw_label: str, path_segment: str) -> str:
    """
    raw_label z. B. "Artikel, Halbhohe Vertäfelungen"
    Wir nehmen den Teil nach dem ersten Komma.
    Fallback: hübsch formatierter Ordnername.
    """
    label = clean(raw_label)
    if label:
        parts = [p.strip() for p in label.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            return parts[1]
        if parts[0]:
            return parts[0]

    seg = path_segment.replace("-", " ").replace("_", " ").strip()
    seg = " ".join([w.capitalize() for w in seg.split()])
    return seg or path_segment


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/SSOT.csv")
    ap.add_argument("--de-root", default="content/de")
    ap.add_argument("--en-root", default="content/en")
    ap.add_argument("--img-root", default="ssot/bilder")  # zentrale Bildquelle (Dateinamen bleiben unverändert)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--remove-empty-old-bundles", action="store_true")
    args = ap.parse_args()

    repo_wissen = Path.cwd().resolve()
    csv_path = (repo_wissen / args.csv).resolve()
    de_root  = (repo_wissen / args.de_root).resolve()
    en_root  = (repo_wissen / args.en_root).resolve()
    img_root = (repo_wissen / args.img_root).resolve()

    assert csv_path.exists(), f"CSV not found: {csv_path}"
    assert de_root.exists(),  f"DE root not found: {de_root}"
    assert en_root.exists(),  f"EN root not found: {en_root}"
    assert img_root.exists(), f"Image root not found: {img_root}"

    rows = read_csv_utf8_auto(csv_path)

    # zentrale Bildquelle indexieren
    img_index = list_all_images(img_root)

    created, updated, moved, copied, aliases_set, errors, skipped = [], [], [], [], [], [], []

    last_synced_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Kategorie-Infos sammeln (für spätere _index.md)
    category_de_info: Dict[str, Dict] = {}
    category_en_info: Dict[str, Dict] = {}

    for r in rows:
        pk = get_pk(r)
        if not pk:
            skipped.append("row without product_id/reference/slug")
            continue

        slug_de = clean(r.get("slug_de")) or slugify(clean(r.get("titel_de") or pk))
        slug_en = clean(r.get("slug_en")) or slugify(clean(r.get("titel_en") or pk))

        titel_de = clean(r.get("titel_de") or pk)
        titel_en = clean(r.get("titel_en") or pk)

        beschr_de = clean(r.get("beschreibung_md_de"))
        beschr_en = clean(r.get("beschreibung_md_en"))

        meta_title_de = clean(r.get("meta_title_de"))
        meta_desc_de  = clean(r.get("meta_description_de"))
        meta_title_en = clean(r.get("meta_title_en"))
        meta_desc_en  = clean(r.get("meta_description_en"))

        verfuegbar_raw = clean(r.get("verfuegbar"))
        price_raw      = clean(r.get("price"))

        verf_bool = parse_bool(verfuegbar_raw)
        preis_val = parse_float(price_raw)

        # Varianten aus YAML lesen und Preise normalisieren
        varianten_raw_list = parse_varianten_yaml(r.get("varianten_yaml"))
        varianten_list = normalize_variant_prices(varianten_raw_list)

        # Bilder + Alttexte (gleiche Reihenfolge)
        bilder_raw      = clean(r.get("bilder_liste") or "")
        bilder_names    = [b.strip() for b in re.split(r"[,\n;]", bilder_raw) if b.strip()]

        bilder_alt_de_l = split_multi_list(r.get("bilder_alt_de"))
        bilder_alt_en_l = split_multi_list(r.get("bilder_alt_en"))

        src_shop_de = clean(r.get("source_de") or r.get("link_shop_de"))
        src_shop_en = clean(r.get("source_en") or r.get("link_shop_en"))

        exp_de = clean(r.get("export_pfad_de"))
        exp_en = clean(r.get("export_pfad_en"))
        if not exp_de or not exp_en:
            skipped.append(f"{pk}: missing export path")
            continue

        # Kategorie-Infos merken (für _index.md)
        exp_de_norm = exp_de.strip("/")
        exp_en_norm = exp_en.strip("/")
        cat_segment_de = Path(exp_de_norm).name
        cat_segment_en = Path(exp_en_norm).name
        cat_title_de = derive_category_title(r.get("kategorie_raw"), cat_segment_de)
        cat_title_en = derive_category_title(r.get("kategorie_raw_en"), cat_segment_en)
        cat_body_de  = clean(r.get("kategorie_beschreibung_de"))
        cat_body_en  = clean(r.get("kategorie_beschreibung_en"))
        category_de_info[exp_de_norm] = {
            "lang": "de",
            "title": cat_title_de,
            "slug": cat_segment_de,
            "body": cat_body_de,
        }
        category_en_info[exp_en_norm] = {
            "lang": "en",
            "title": cat_title_en,
            "slug": cat_segment_en,
            "body": cat_body_en,
        }

        # Ziel-Bundles bestimmen
        bundle_de = de_root / exp_de_norm / f"{pk}-{slug_de}"
        bundle_en = en_root / exp_en_norm / f"{pk}-{slug_en}"

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

        # --- Bilder kopieren ---
        # Wichtig: Dateinamen bleiben exakt wie in ssot/bilder, wir benennen NICHT um.
        resolved_name_for_copy: Dict[str, str] = {}

        if args.apply:
            bundle_de.mkdir(parents=True, exist_ok=True)
            bundle_en.mkdir(parents=True, exist_ok=True)

        # zuerst DE-Bundle bestücken
        for name in bilder_names:
            # existiert Datei schon im Bundle (ggf. leicht andere Schreibweise wie -01 vs -1)?
            existing = existing_variant_in_bundle(bundle_de, name)
            if existing:
                resolved_name_for_copy[name] = existing
            else:
                chosen = find_source_by_candidates(img_index, img_root, name)
                if not chosen:
                    errors.append(f"{pk}: image missing in ssot/bilder: {name}")
                    continue
                dst_de = bundle_de / chosen.name  # KEINE Umbenennung
                if args.apply:
                    dst_de.parent.mkdir(parents=True, exist_ok=True)
                    if not dst_de.exists():
                        shutil.copy2(chosen, dst_de)
                        copied.append(f"COPY {chosen} -> {dst_de}")
                resolved_name_for_copy[name] = chosen.name

        # dann EN-Bundle spiegeln (1:1 dieselben Dateinamen)
        for name in bilder_names:
            eff = (
                resolved_name_for_copy.get(name)
                or existing_variant_in_bundle(bundle_de, name)
                or name
            )
            src = bundle_de / eff
            dst = bundle_en / eff
            if src.exists():
                if args.apply:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        copied.append(f"COPY {src} -> {dst}")
            else:
                errors.append(f"{pk}: image not found in DE bundle for EN copy: {name}")

        # finalisierte Bildnamen (tatsächlich im Bundle vorhandene Namen, in Reihenfolge)
        final_img_names = [
            resolved_name_for_copy.get(n)
            or existing_variant_in_bundle(bundle_de, n)
            or n
            for n in bilder_names
        ]

        # Bilder-Blocks mit Alttexten
        bilder_block_de = []
        for i, fname in enumerate(final_img_names):
            alt_de = bilder_alt_de_l[i] if i < len(bilder_alt_de_l) else ""
            bilder_block_de.append({
                "datei": fname,
                "alt_de": alt_de
            })

        bilder_block_en = []
        for i, fname in enumerate(final_img_names):
            alt_en = bilder_alt_en_l[i] if i < len(bilder_alt_en_l) else ""
            bilder_block_en.append({
                "datei": fname,
                "alt_en": alt_en
            })

        # Artikelnummer ableiten (einfacher Identifier fürs Frontend)
        artikelnummer = (slug_de or slug_en or pk).upper()

        # Produkt-Block (technische Infos)
        produkt_common = {
            "id": pk,
            "artikelnummer": artikelnummer,
            "verfuegbar": verf_bool,
            "preis_basis": preis_val,
            "varianten": varianten_list or [],
        }

        produkt_de = dict(produkt_common)
        produkt_de["bilder"] = bilder_block_de

        produkt_en = dict(produkt_common)
        produkt_en["bilder"] = bilder_block_en

        # SEO-Blöcke
        seo_de = {
            "title": meta_title_de,
            "description": meta_desc_de,
            "tags": split_multi_list(r.get("tags_de")),
        }

        seo_en = {
            "title": meta_title_en,
            "description": meta_desc_en,
            "tags": split_multi_list(r.get("tags_en")),
        }

        # Referenz-URL (Shop / Herkunft)
        refs_de = {
            "source_shop": src_shop_de,
        }
        refs_en = {
            "source_shop": src_shop_en,
        }

        # Frontmatter-updates vorbereiten
        fm_de_updates = {
            "title": titel_de,
            "lang": "de",
            "translationKey": pk,
            "managed_by": "ssot-sync",
            "last_synced": last_synced_str,
            "produkt": produkt_de,
            "seo": seo_de,
            "refs": refs_de,
        }
        if alias_de:
            fm_de_updates["aliases"] = sorted(set(alias_de))

        fm_en_updates = {
            "title": titel_en,
            "lang": "en",
            "translationKey": pk,
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
                beschr_de,
                managed_prefix_check="ssot-sync",
            )
            (updated if existed else created).append(bundle_de.as_posix())

            existed = (bundle_en / "index.md").exists()
            write_page(
                bundle_en,
                "index.md",
                fm_en_updates,
                beschr_en,
                managed_prefix_check="ssot-sync",
            )
            (updated if existed else created).append(bundle_en.as_posix())

        # Alias-Statistik
        if alias_de or alias_en:
            aliases_set.append(pk)

        # alte leere Bundles ggf. wegräumen
        if args.apply and args.remove_empty_old_bundles:
            for ob in old_de + old_en:
                try:
                    if not any(ob.rglob("*")):
                        ob.rmdir()
                except Exception:
                    pass

    # Kategorie-_index.md erzeugen/aktualisieren
    if args.apply:
        for exp_de_norm, info in category_de_info.items():
            section_dir = de_root / exp_de_norm
            cat_title = info["title"] or info["slug"]
            cat_slug  = info["slug"]
            cat_body  = info.get("body") or f"{cat_title} – Übersicht der Produkte."
            fm_cat_de = {
                "title": cat_title,
                "lang": "de",
                "managed_by": "ssot-sync",
                "last_synced": last_synced_str,
                "kategorie_slug": cat_slug,
            }
            write_page(
                section_dir,
                "_index.md",
                fm_cat_de,
                cat_body,
                managed_prefix_check="ssot-sync",
            )

        for exp_en_norm, info in category_en_info.items():
            section_dir = en_root / exp_en_norm
            cat_title = info["title"] or info["slug"]
            cat_slug  = info["slug"]
            cat_body  = info.get("body") or f"{cat_title} – Product overview."
            fm_cat_en = {
                "title": cat_title,
                "lang": "en",
                "managed_by": "ssot-sync",
                "last_synced": last_synced_str,
                "kategorie_slug": cat_slug,
            }
            write_page(
                section_dir,
                "_index.md",
                fm_cat_en,
                cat_body,
                managed_prefix_check="ssot-sync",
            )

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
    if moved:      lines += ["## Moved"]   + [f"- {p}" for p in moved]   + [""]
    if copied:     lines += ["## Copied"]  + [f"- {p}" for p in copied]  + [""]
    if aliases_set:lines += ["## Aliases set for"] + [f"- {c}" for c in sorted(set(aliases_set))] + [""]
    if skipped:    lines += ["## Skipped (info)"] + [f"- {s}" for s in skipped[:200]] + [""]
    if errors:     lines += ["## Errors"]  + [f"- {e}" for e in errors]  + [""]

    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {rep}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
