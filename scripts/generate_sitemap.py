
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generiert sitemap.xml (ggf. als Index) und robots.txt.
- Scannt Markdown-Dateien (konfigurierbar via INCLUDE_GLOBS / EXCLUDE_GLOBS)
- Pretty-URLs (README -> Ordner, sonst ohne .md)
- lastmod aus 'git log' (Fallback: Filesystem)
- hreflang-Alternates, wenn gleicher 'slug' in unterschiedlichen Sprachen existiert
- robots.txt mit Sitemap-Verweis
"""

import os
import glob
import pathlib
import subprocess
import datetime
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except Exception:
    yaml = None

BASE_URL     = os.environ.get("BASE_URL", "").rstrip("/")
PUBLISH_ROOT = os.environ.get("PUBLISH_ROOT", ".").rstrip("/").strip()
INCLUDE_GLOBS_STR = os.environ.get("INCLUDE_GLOBS", "**/*.md")
EXCLUDE_GLOBS_STR = os.environ.get("EXCLUDE_GLOBS", ".github/** **/README.md")

if not BASE_URL:
    raise SystemExit("ERROR: BASE_URL ist nicht gesetzt. Setze BASE_URL in der Action-Umgebung.")

INCLUDE_GLOBS = [g.strip() for g in INCLUDE_GLOBS_STR.split() if g.strip()]
EXCLUDE_GLOBS = [g.strip() for g in EXCLUDE_GLOBS_STR.split() if g.strip()]

MAX_URLS_PER_FILE = 50000
TODAY = datetime.date.today()

def is_excluded(path: str) -> bool:
    p = path.replace("\\", "/")
    for patt in EXCLUDE_GLOBS:
        if glob.fnmatch.fnmatch(p, patt):
            return True
    return False

def rel_web_path(absolute_path: pathlib.Path) -> str:
    root = pathlib.Path(PUBLISH_ROOT).resolve()
    ap   = absolute_path.resolve()
    try:
        rel = str(ap.relative_to(root)).replace("\\", "/")
    except Exception:
        rel = str(ap).replace("\\", "/")
    return rel

def parse_frontmatter(text: str) -> Tuple[Dict, str]:
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            head = parts[0].lstrip("-").strip()
            body = parts[1]
            if yaml:
                try:
                    meta = yaml.safe_load(head) or {}
                except Exception:
                    meta = {}
            else:
                meta = {}
            return meta, body
    return {}, text

def get_git_lastmod(path: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", path],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        if out:
            return out
    except Exception:
        pass
    try:
        ts = pathlib.Path(path).stat().st_mtime
        dt = datetime.datetime.utcfromtimestamp(ts).replace(tzinfo=datetime.timezone.utc)
        return dt.isoformat()
    except Exception:
        return None

def infer_lang_from_path(rel_path: str) -> Optional[str]:
    p = rel_path.lower()
    if "/de/" in p or p.startswith("de/"):
        return "de"
    if "/en/" in p or p.startswith("en/"):
        return "en"
    return None

def md_path_to_url(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/")
    if rel.endswith("/README.md") or rel.endswith("/readme.md"):
        rel = rel[: -len("/README.md")] if rel.endswith("/README.md") else rel[: -len("/readme.md")]
    elif rel.lower().endswith(".md"):
        rel = rel[: -3]
    if rel.startswith("./"):
        rel = rel[2:]
    return f"{BASE_URL}/{rel}".rstrip("/")

# Scan
root_globs = []
for patt in INCLUDE_GLOBS:
    root_globs.extend(glob.glob(patt, recursive=True))

candidates = []
for p in root_globs:
    if not p.lower().endswith(".md"):
        continue
    if is_excluded(p):
        continue
    if pathlib.Path(p).is_file():
        if PUBLISH_ROOT == "." or pathlib.Path(p).resolve().is_relative_to(pathlib.Path(PUBLISH_ROOT).resolve()):
            candidates.append(p)

entries = []
slug_groups: Dict[str, List[int]] = {}

for path in sorted(set(candidates)):
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except Exception:
        continue
    meta, _ = parse_frontmatter(raw)
    rel = rel_web_path(pathlib.Path(path))
    url = md_path_to_url(rel)

    lang = (meta.get("lang") or infer_lang_from_path(rel) or "x-default")
    slug = (meta.get("slug") or "").strip()
    lastmod = get_git_lastmod(path) or f"{TODAY.isoformat()}"

    idx = len(entries)
    entries.append({
        "path": path,
        "rel": rel,
        "url": url,
        "lang": lang,
        "slug": slug,
        "lastmod": lastmod,
    })
    if slug:
        slug_groups.setdefault(slug, []).append(idx)

# XML mit hreflang
NSMAP = { "xhtml": "http://www.w3.org/1999/xhtml" }
ET.register_namespace("xhtml", NSMAP["xhtml"])

def build_urlset(url_items: List[dict]) -> ET.Element:
    urlset = ET.Element("urlset", attrib={"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9",
                                          "xmlns:xhtml": NSMAP["xhtml"]})
    for e in url_items:
        url_el = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_el, "loc")
        loc.text = e["url"]
        lm  = ET.SubElement(url_el, "lastmod")
        lm.text = e["lastmod"]

        if e["slug"] and e["slug"] in slug_groups:
            for j in slug_groups[e["slug"]]:
                sib = entries[j]
                if sib is e:
                    continue
                link = ET.SubElement(url_el, f"{{{NSMAP['xhtml']}}}link")
                link.set("rel", "alternate")
                link.set("hreflang", sib["lang"])
                link.set("href", sib["url"])
    return urlset

def write_xml(tree: ET.Element, out_path: str):
    xml_bytes = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
    pathlib.Path(out_path).write_bytes(xml_bytes)

def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

lang_order = {"de": 0, "en": 1}
entries.sort(key=lambda e: (lang_order.get(e["lang"], 9), e["url"]))

if len(entries) <= MAX_URLS_PER_FILE:
    urlset = build_urlset(entries)
    out_file = pathlib.Path(PUBLISH_ROOT) / "sitemap.xml"
    write_xml(urlset, str(out_file))
    sitemap_files = [out_file.name]
else:
    sitemap_files = []
    for n, part in enumerate(chunk(entries, MAX_URLS_PER_FILE), start=1):
        urlset = build_urlset(part)
        name = f"sitemap-{n}.xml"
        out_file = pathlib.Path(PUBLISH_ROOT) / name
        write_xml(urlset, str(out_file))
        sitemap_files.append(name)

    idx_root = ET.Element("sitemapindex", attrib={"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for name in sitemap_files:
        sm = ET.SubElement(idx_root, "sitemap")
        loc = ET.SubElement(sm, "loc")
        loc.text = f"{BASE_URL}/{name}"
        lm = ET.SubElement(sm, "lastmod")
        lm.text = f"{TODAY.isoformat()}"
    write_xml(idx_root, str(pathlib.Path(PUBLISH_ROOT) / "sitemap-index.xml"))

# robots.txt
robots_lines = []
robots_lines.append("User-agent: *")
robots_lines.append("Allow: /")
robots_lines.append("Disallow: /drafts/")
robots_lines.append("Disallow: /tmp/")
robots_lines.append("Disallow: /private/")
robots_lines.append("")
if len(sitemap_files) == 1 and sitemap_files[0] == "sitemap.xml":
    robots_lines.append(f"Sitemap: {BASE_URL}/sitemap.xml")
else:
    robots_lines.append(f"Sitemap: {BASE_URL}/sitemap-index.xml")

robots_txt = "\n".join(robots_lines).strip() + "\n"
(pathlib.Path(PUBLISH_ROOT) / "robots.txt").write_text(robots_txt, encoding="utf-8")

print(f"OK: {len(entries)} URLs erfasst.")
if len(sitemap_files) == 1:
    print("Ausgabe:", f"{PUBLISH_ROOT}/sitemap.xml")
else:
    print("Ausgabe:", ", ".join(f"{PUBLISH_ROOT}/{n}" for n in sitemap_files), "und sitemap-index.xml")
print("robots.txt:", f"{PUBLISH_ROOT}/robots.txt")
