#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: wissen/scripts/faq_sync.py

faq.csv sync with two stages:
- Stage A: generate/update authoritative global FAQ pages under content/<lang>/faq/**
- Stage B: inject compact FAQ blocks into product/category pages
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------- CSV ----------

def _normkey(k: str) -> str:
    s = (k or "").strip().replace("\ufeff", "").strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    s = re.sub(r"_+", "_", s)
    return s


def clean(s: Optional[str]) -> str:
    return (s or "").strip()


def read_csv_utf8_auto(path: Path) -> List[Dict[str, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;|\t")
        delim = dialect.delimiter
    except Exception:
        delim = ","
    rows = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    return [{_normkey(k): ("" if v is None else v) for k, v in r.items()} for r in rows]


def _order_parseable(raw_order: str) -> bool:
    v = clean(raw_order)
    if not v:
        return True
    try:
        int(float(v))
        return True
    except Exception:
        return False


def normalize_links(text: str) -> str:
    if not text:
        return ""
    out = text
    out = re.sub(r"https://www\.vertaefelungen\.de/wissen/de/", "/wissen/de/", out, flags=re.IGNORECASE)
    out = re.sub(r"https://www\.vertaefelungen\.de/wissen/en/", "/wissen/en/", out, flags=re.IGNORECASE)
    out = re.sub(r"(?<!/wissen)/de/faq/", "/wissen/de/faq/", out)
    out = re.sub(r"(?<!/wissen)/en/faq/", "/wissen/en/faq/", out)
    return out


def strip_url_frontmatter_key(fm_block: str) -> Tuple[str, Optional[str], str]:
    if not fm_block:
        return fm_block, None, "none"

    def _dq(s: str) -> str:
        # Safe double-quoted YAML scalar (minimal escaping)
        return s.replace("\\", "\\\\").replace('"', '\\"')

    content = fm_block.strip()
    if content.startswith("---"):
        content = content[3:]
    if content.endswith("---"):
        content = content[:-3]
    lines = content.strip("\n").splitlines()

    old_url: Optional[str] = None
    kept_lines: List[str] = []
    for line in lines:
        m = re.match(r"^\s*url\s*:\s*(.*?)\s*$", line)
        if m and old_url is None:
            old_url = m.group(1).strip().strip('"').strip("'")
            continue
        kept_lines.append(line)

    if old_url is None:
        return fm_block, None, "none"

    alias_status = "merged"
    alias_line_idx = None
    alias_vals: List[str] = []

    # helper: detect a new top-level YAML key (no indent)
    def _is_top_level_key(line: str) -> bool:
        if not line:
            return False
        if line.startswith(" ") or line.startswith("\t"):
            return False
        return re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", line) is not None

    for idx, line in enumerate(kept_lines):
        m_alias = re.match(r"^(\s*)aliases\s*:\s*(.*?)\s*$", line)
        if not m_alias:
            continue

        alias_line_idx = idx
        header_indent = m_alias.group(1) or ""
        raw = (m_alias.group(2) or "").strip()

        # CASE 1: inline list: aliases: ["a", "b"]
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if inner:
                alias_vals = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
            else:
                alias_vals = []
            if old_url and old_url not in alias_vals:
                alias_vals.append(old_url)
            rendered = ", ".join([f'"{_dq(a)}"' for a in alias_vals])
            kept_lines[idx] = f"aliases: [{rendered}]"

        # CASE 2: empty inline list: aliases: []
        elif raw == "[]":
            kept_lines[idx] = f'aliases: ["{_dq(old_url)}"]'

        # CASE 3: block-style header: aliases:
        elif raw == "":
            # collect following block list items belonging to aliases
            j = idx + 1
            item_lines_idx: List[int] = []
            existing_vals: List[str] = []
            while j < len(kept_lines):
                nxt = kept_lines[j]
                if _is_top_level_key(nxt):
                    break
                # treat as list item if it's indented and starts with '-'
                m_item = re.match(r"^(\s*)-\s*(.*?)\s*$", nxt)
                if m_item:
                    indent = m_item.group(1) or ""
                    # ensure item is more indented than header (YAML block list)
                    if len(indent) >= len(header_indent) + 1:
                        item_lines_idx.append(j)
                        raw_val = (m_item.group(2) or "").strip()
                        # remove trailing comment for unquoted scalars
                        if raw_val and not (raw_val.startswith('"') or raw_val.startswith("'")) and "#" in raw_val:
                            raw_val = raw_val.split("#", 1)[0].strip()
                        val = raw_val.strip().strip('"').strip("'")
                        if val:
                            existing_vals.append(val)
                        j += 1
                        continue
                # if it's not a list item and not a top-level key, it's likely blank/comment; continue scan
                # but do not consume unrelated nested structures—still safe to continue
                if nxt.strip() == "" or nxt.lstrip().startswith("#"):
                    j += 1
                    continue
                # any other indented line ends our alias list block
                break

            if old_url and old_url not in existing_vals:
                # choose indent style: reuse first item indent if present, else default two spaces past header indent
                if item_lines_idx:
                    m_first = re.match(r"^(\s*)-\s*", kept_lines[item_lines_idx[0]])
                    item_indent = (m_first.group(1) if m_first else (header_indent + "  "))
                else:
                    item_indent = header_indent + "  "
                insert_at = (item_lines_idx[-1] + 1) if item_lines_idx else (idx + 1)
                kept_lines.insert(insert_at, f'{item_indent}- "{_dq(old_url)}"')
            # keep header line as-is; NEVER rewrite to inline list (prevents dangling "- ..." YAML)

        else:
            alias_status = "not_merged"

        break

    if alias_line_idx is None and old_url:
        # add aliases in block style to avoid YAML format surprises
        kept_lines.append("aliases:")
        kept_lines.append(f'  - "{_dq(old_url)}"')

    payload = "\n".join(kept_lines).rstrip()
    return f"---\n{payload}\n---\n", old_url, alias_status


@dataclass
class FaqItem:
    faq_id: str
    scope_type: str
    scope_key: str
    lang: str
    question: str
    answer: str
    order: int
    status: str
    source: str

    @staticmethod
    def from_row(r: Dict[str, str]) -> "FaqItem":
        def to_int(v: str, default: int = 100) -> int:
            v = clean(v)
            if not v:
                return default
            try:
                return int(float(v))
            except Exception:
                return default

        return FaqItem(
            faq_id=clean(r.get("faq_id") or r.get("id") or ""),
            scope_type=clean(r.get("scope_type") or "").lower(),
            scope_key=clean(r.get("scope_key") or ""),
            lang=clean(r.get("lang") or "").lower(),
            question=normalize_links(clean(r.get("question") or r.get("frage") or "")),
            answer=normalize_links((r.get("answer") or r.get("antwort") or "").rstrip()),
            order=to_int(r.get("order") or r.get("sort") or r.get("rank") or ""),
            status=clean(r.get("status") or "").lower(),
            source=clean(r.get("source") or ""),
        )


def load_faq_csv(csv_path: Path) -> List[FaqItem]:
    rows = read_csv_utf8_auto(csv_path)
    items = [FaqItem.from_row(r) for r in rows]

    bad: List[str] = []
    for i, (r, it) in enumerate(zip(rows, items), start=2):
        if not it.faq_id:
            bad.append(f"Line {i}: missing faq_id")
        if it.scope_type not in ("product", "category", "global"):
            bad.append(f"Line {i}: invalid scope_type: {it.scope_type}")
        if it.lang not in ("de", "en"):
            bad.append(f"Line {i}: invalid lang: {it.lang}")
        if not it.scope_key:
            bad.append(f"Line {i}: missing scope_key")
        if not it.question:
            bad.append(f"Line {i}: missing question")
        if not it.answer:
            bad.append(f"Line {i}: missing answer")
        if not clean(r.get("status") or ""):
            bad.append(f"Line {i}: missing status")
        raw_order = r.get("order") or r.get("sort") or r.get("rank") or ""
        if not _order_parseable(raw_order):
            bad.append(f"Line {i}: invalid order: {clean(raw_order)}")

    if bad:
        raise ValueError("faq.csv validation failed:\n" + "\n".join(bad))

    return items


# ---------- Markdown parsing ----------

FM_RE = re.compile(r"\A(?:\ufeff)?---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FAQ_MARKER_RE = re.compile(r"(?s)<!--\s*FAQ_SYNC:BEGIN\s*-->.*?<!--\s*FAQ_SYNC:END\s*-->")
FAQ_LEGACY_SECTION_RE = re.compile(
    r"(?ims)^##\s*(FAQ|Häufige\s+Fragen|Frequently\s+asked\s+questions|Info)\s*\n.*?(?=^##\s+|\Z)"
)


def split_frontmatter(md: str) -> Tuple[str, str]:
    m = FM_RE.match(md or "")
    if not m:
        return "", md or ""
    fm_block = m.group(0)
    body = (md or "")[len(fm_block):]
    return fm_block, body


def has_duplicate_frontmatter_start(md: str, max_lines: int = 80) -> bool:
    text = md or ""
    if not (text.startswith("---\n") or text.startswith("\ufeff---\n")):
        return False

    fm_block, body = split_frontmatter(text)
    if not fm_block:
        return False

    probe = "\n".join((body or "").splitlines()[:max_lines])
    return re.search(r"(?m)^(?:\ufeff)?---\s*$", probe) is not None


def parse_managed_by(frontmatter_block: str) -> str:
    if not frontmatter_block:
        return ""
    m = re.search(r"(?m)^\s*managed_by\s*:\s*(.+?)\s*$", frontmatter_block)
    if not m:
        return ""
    return m.group(1).strip().strip('"').strip("'")


def merge_frontmatter_preserving(fm_block: str, updates: Dict[str, str]) -> str:
    if fm_block:
        content = fm_block.strip()
        if content.startswith("---"):
            content = content[3:]
        if content.endswith("---"):
            content = content[:-3]
        lines = content.strip("\n").splitlines()
    else:
        lines = []

    for key, value in updates.items():
        rendered = f'{key}: "{value}"'
        replaced = False
        for i, line in enumerate(lines):
            if re.match(rf"^\s*{re.escape(key)}\s*:", line):
                lines[i] = rendered
                replaced = True
                break
        if not replaced:
            lines.append(rendered)

    payload = "\n".join(lines).rstrip()
    return f"---\n{payload}\n---\n"


def remove_marker_blocks(text: str) -> str:
    return FAQ_MARKER_RE.sub("", text or "")


def remove_legacy_faq_section(text: str) -> str:
    return FAQ_LEGACY_SECTION_RE.sub("", text or "")


def cleanup_body_text(text: str) -> str:
    out = remove_marker_blocks(text)
    out = remove_legacy_faq_section(out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def render_qa_markdown(items: List[FaqItem]) -> str:
    deduped: List[FaqItem] = []
    seen_questions = set()
    for it in items:
        q = re.sub(r"\s+", " ", it.question.strip()).casefold()
        if not q or q in seen_questions:
            continue
        seen_questions.add(q)
        deduped.append(it)

    if not deduped:
        return ""

    out: List[str] = ["## Info", ""]
    for it in deduped:
        out.extend([f"### {it.question}", "", it.answer.strip(), ""])
    return "\n".join(out).rstrip() + "\n"


def marker_wrap(block: str) -> str:
    return "\n".join([
        "<!-- FAQ_SYNC:BEGIN -->",
        block.strip(),
        "<!-- FAQ_SYNC:END -->",
    ]).rstrip() + "\n"


def inject_marker_block(body: str, block: str) -> Tuple[str, str]:
    marker_block = marker_wrap(block)
    has_marker = FAQ_MARKER_RE.search(body or "") is not None
    has_legacy = FAQ_LEGACY_SECTION_RE.search(body or "") is not None

    if has_marker:
        new_body = FAQ_MARKER_RE.sub(marker_block.strip(), body or "", count=1)
        if has_legacy:
            new_body = remove_legacy_faq_section(new_body)
        new_body = re.sub(r"\n{3,}", "\n\n", new_body).rstrip() + "\n"
        return (new_body, "replaced" if new_body != body else "unchanged")

    if has_legacy:
        new_body = FAQ_LEGACY_SECTION_RE.sub(marker_block.strip() + "\n", body or "", count=1)
        new_body = re.sub(r"\n{3,}", "\n\n", new_body).rstrip() + "\n"
        return (new_body, "migrated" if new_body != body else "unchanged")

    new_body = (body or "").rstrip() + "\n\n" + marker_block
    new_body = re.sub(r"\n{3,}", "\n\n", new_body).rstrip() + "\n"
    return new_body, "appended"


# ---------- Scope detection ----------

ARTICLE_RE = re.compile(r"(?i)\b([a-z]{2}\d{2})-(\d{2,3})\b")


def derive_product_keys_from_path(p: Path) -> List[str]:
    keys: List[str] = []
    try:
        bundle_dir = p.parent.name
    except Exception:
        return keys

    m_num = re.match(r"^(\d{2,})-", bundle_dir)
    if m_num:
        keys.append(m_num.group(1))

    m = ARTICLE_RE.search(bundle_dir)
    if m:
        a = m.group(1)
        n = m.group(2)
        keys += [f"{a.upper()}/{n}", f"{a.upper()}-{n}", f"{a.lower()}/{n}", f"{a.lower()}-{n}"]

    return list(dict.fromkeys([k for k in keys if k]))


def derive_product_keys_from_frontmatter(frontmatter_block: str) -> List[str]:
    keys: List[str] = []
    for field in ("translationKey", "id", "artikelnummer"):
        m = re.search(rf"(?m)^\s*{field}\s*:\s*(.+?)\s*$", frontmatter_block or "")
        if m:
            keys.append(m.group(1).strip().strip('"').strip("'"))
    return list(dict.fromkeys([k for k in keys if k]))


def global_scope_key_candidates(rel: Path) -> List[str]:
    rel_without_lang = rel.parts[1:]
    if not rel_without_lang:
        return []
    filename = rel.name
    if filename in ("_index.md", "index.md"):
        key = "/".join(rel_without_lang[:-1]).strip("/")
    else:
        key = "/".join(rel_without_lang).strip("/")
        if key.lower().endswith(".md"):
            key = key[:-3]
    if not key:
        return []
    candidates = [key]
    if key.startswith("faq/"):
        candidates.append(key[len("faq/"):])
    return list(dict.fromkeys([c for c in candidates if c]))


def pick_matching_faq_items(
    faq_map: Dict[Tuple[str, str, str], List[FaqItem]],
    scope_type: str,
    candidate_keys: List[str],
    lang: str,
) -> Tuple[Optional[str], List[FaqItem]]:
    for k in candidate_keys:
        items = faq_map.get((scope_type, k, lang))
        if items:
            return k, items
    return None, []


# ---------- Generator helpers ----------


def normalize_source_to_target(source: str, lang: str) -> Optional[Path]:
    src = clean(source).replace("\\", "/")
    if not src:
        return None
    src = src.lstrip("/")
    if src.startswith("wissen/"):
        src = src[len("wissen/"):]
    if src.startswith("content/"):
        target = src
    elif src.startswith(f"{lang}/"):
        target = f"content/{src}"
    else:
        target = src

    p = Path(target)
    expected_prefix = Path("content") / lang / "faq"
    try:
        p.relative_to(expected_prefix)
    except Exception:
        return None
    return p


def fallback_target_from_scope(scope_key: str, lang: str) -> Path:
    key = clean(scope_key).strip("/")
    if key.startswith("faq/"):
        key = key[len("faq/"):]
    if key in ("", "root"):
        return Path("content") / lang / "faq" / "_index.md"
    return Path("content") / lang / "faq" / key / "index.md"


def stable_translation_key_from_target(target: Path) -> str:
    rel = target.as_posix()
    if rel.startswith("content/"):
        rel = rel[len("content/"):]
    if rel.endswith("/_index.md"):
        rel = rel[:-10]
    elif rel.endswith("/index.md"):
        rel = rel[:-9]
    elif rel.endswith(".md"):
        rel = rel[:-3]
    return f"faq:{rel.strip('/')}"


# ---------- Report ----------

def write_report(path: Path, apply: bool, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "APPLY" if apply else "DRY-RUN"
    header = [
        f"# FAQ Sync Report ({mode})",
        "",
        f"- Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    path.write_text("\n".join(header + lines).rstrip() + "\n", encoding="utf-8")


# ---------- Main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ssot/faq.csv")
    ap.add_argument("--root", default="content")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--generate-global", action="store_true")
    ap.add_argument("--inject", action="store_true")
    ap.add_argument("--prune", action="store_true", help="Only with --generate-global --apply")
    ap.add_argument("--managed-by", default="ssot-sync,categories.csv")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    do_inject = args.inject or (not args.generate_global and not args.inject)
    do_generate = args.generate_global

    csv_path = Path(args.csv)
    root = Path(args.root)
    managed_by_vals = {v.strip() for v in clean(args.managed_by).split(",") if v.strip()}

    if not csv_path.exists():
        print(f"[faq_sync] faq.csv not found: {csv_path} (skip)")
        return 0
    if not root.exists():
        print(f"[faq_sync] content root not found: {root}", file=sys.stderr)
        return 2

    try:
        all_items = load_faq_csv(csv_path)
    except Exception as e:
        print(f"[faq_sync] ERROR: {e}", file=sys.stderr)
        return 2

    active_items = [it for it in all_items if it.status == "active"]
    faq_map: Dict[Tuple[str, str, str], List[FaqItem]] = {}
    for it in active_items:
        key = (it.scope_type, it.scope_key, it.lang)
        faq_map.setdefault(key, []).append(it)
    for k in list(faq_map.keys()):
        faq_map[k] = sorted(faq_map[k], key=lambda x: (x.order, x.faq_id))

    created = updated = unchanged = skipped_conflict = invalid_source = would_change = errors = pruned = 0
    touched_files: List[str] = []
    skipped_files: List[str] = []
    warnings: List[str] = []
    expected_targets: Set[Path] = set()

    if args.prune and not do_generate:
        errors += 1
        warnings.append("prune_aborted_generate_global_required")
        raise SystemExit(2)

    if do_generate:
        grouped: Dict[Tuple[str, str], List[FaqItem]] = {}
        for it in active_items:
            if it.scope_type != "global":
                continue
            group_key = (it.source or f"__scope__:{it.scope_key}", it.lang)
            grouped.setdefault(group_key, []).append(it)

        for (_, lang), items in sorted(grouped.items(), key=lambda x: (x[0][1], x[0][0])):
            first = items[0]
            if first.source:
                target_repo = normalize_source_to_target(first.source, lang)
                if target_repo is None:
                    invalid_source += 1
                    warnings.append(f"invalid_source_outside_faq: lang={lang} source={first.source}")
                    continue
            else:
                target_repo = fallback_target_from_scope(first.scope_key, lang)

            target_rel = Path(target_repo).relative_to("content")
            expected_targets.add(target_rel)
            p = root / target_rel

            items_sorted = sorted(items, key=lambda x: (x.order, x.faq_id))
            base_rows = [x for x in items_sorted if x.question in ("_index", "_body")]
            qa_rows = [x for x in items_sorted if x.question not in ("_index", "_body")]
            base_text = "\n\n".join([x.answer.strip() for x in base_rows if x.answer.strip()]).strip()
            base_clean = cleanup_body_text(base_text)
            qa_block = render_qa_markdown(qa_rows).strip()

            final_body = ""
            if base_clean and qa_block:
                final_body = f"{base_clean}\n\n{qa_block}\n"
            elif base_clean:
                final_body = base_clean.rstrip() + "\n"
            else:
                final_body = qa_block.rstrip() + "\n"

            fm_existing = ""
            body_existing = ""
            managed_by_existing = ""
            if p.exists():
                old_md = p.read_text(encoding="utf-8", errors="replace")
                if has_duplicate_frontmatter_start(old_md):
                    warnings.append(f"duplicate_frontmatter_suspected: {p.as_posix()}")
                fm_existing, body_existing = split_frontmatter(old_md)
                fm_existing, old_url, alias_status = strip_url_frontmatter_key(fm_existing)
                if old_url:
                    if alias_status == "not_merged":
                        warnings.append(
                            f"url_removed_alias_not_merged: {p.as_posix()} url={old_url}"
                        )
                    else:
                        warnings.append(f"url_removed_to_aliases: {p.as_posix()} url={old_url}")
                managed_by_existing = parse_managed_by(fm_existing)
                if managed_by_existing != "faq.csv":
                    skipped_conflict += 1
                    warnings.append(f"conflict_not_owned: {p.as_posix()} managed_by={managed_by_existing or '(none)'}")
                    continue

            fm_new = merge_frontmatter_preserving(
                fm_existing,
                {
                    "managed_by": "faq.csv",
                    "lang": lang,
                    "translationKey": stable_translation_key_from_target(target_repo),
                    "title": "Info",
                    "last_synced": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            new_md = fm_new + final_body

            if p.exists() and (fm_existing + body_existing) == new_md:
                unchanged += 1
                continue

            if p.exists():
                updated += 1
            else:
                created += 1
                p.parent.mkdir(parents=True, exist_ok=True)

            if not args.apply:
                would_change += 1
            else:
                p.write_text(new_md, encoding="utf-8")
            touched_files.append(f"generated: {p.as_posix()}")

        if args.prune and args.apply:
            if not expected_targets:
                errors += 1
                warnings.append("prune_aborted_expected_targets_empty")
                raise SystemExit(2)
            if invalid_source > 0 or errors > 0:
                warnings.append("prune_aborted_invalid_source_or_errors")
                raise SystemExit(2)

            for lang in ("de", "en"):
                faq_root = root / lang / "faq"
                if not faq_root.exists():
                    continue
                for file in sorted(faq_root.rglob("*.md")):
                    rel = file.relative_to(root)
                    if rel in expected_targets:
                        continue
                    md = file.read_text(encoding="utf-8", errors="replace")
                    fm, _ = split_frontmatter(md)
                    if parse_managed_by(fm) == "faq.csv":
                        file.unlink()
                        pruned += 1
                        touched_files.append(f"pruned: {file.as_posix()}")

    if do_inject:
        md_files = sorted(root.rglob("*.md"))
        for p in md_files:
            try:
                rel = p.relative_to(root)
            except Exception:
                continue
            if len(rel.parts) < 2:
                continue

            lang = rel.parts[0].lower()
            if lang not in ("de", "en"):
                continue

            rel_from_lang = rel.parts[1:]
            is_faq_tree = len(rel_from_lang) >= 1 and rel_from_lang[0] == "faq"
            if is_faq_tree:
                continue

            md = p.read_text(encoding="utf-8", errors="replace")
            if has_duplicate_frontmatter_start(md):
                warnings.append(f"duplicate_frontmatter_suspected: {p.as_posix()}")
            fm_block, body = split_frontmatter(md)
            managed_by = parse_managed_by(fm_block)
            if managed_by == "faq.csv":
                continue

            basename = p.name
            scope_type: Optional[str] = None
            scope_key_candidates: List[str] = []

            if basename == "_index.md":
                if managed_by != "categories.csv":
                    skipped_files.append(str(p))
                    continue
                scope_type = "category"
                scope_key = "/".join(rel.parts[1:-1]).strip("/")
                if not scope_key:
                    skipped_files.append(str(p))
                    continue
                scope_key_candidates = [scope_key]
            elif basename == "index.md":
                rel_path_str = "/".join(rel.parts[1:])
                if "produkte/" not in rel_path_str:
                    skipped_files.append(str(p))
                    continue
                if not managed_by.startswith("ssot-sync"):
                    skipped_files.append(str(p))
                    continue
                scope_type = "product"
                scope_key_candidates.extend(derive_product_keys_from_frontmatter(fm_block))
                scope_key_candidates.extend(derive_product_keys_from_path(p))
                scope_key_candidates.extend([p.parent.name, p.parent.name.lower(), p.parent.name.upper()])
                scope_key_candidates = [k for k in scope_key_candidates if k and k.lower() != "none"]
                scope_key_candidates = list(dict.fromkeys(scope_key_candidates))
            else:
                skipped_files.append(str(p))
                continue

            # explicit backwards-compatible guard for allowed values
            if managed_by_vals and not any(
                managed_by == mv or (mv == "ssot-sync" and managed_by.startswith("ssot-sync")) for mv in managed_by_vals
            ):
                skipped_files.append(str(p))
                continue

            matched_key, items = pick_matching_faq_items(faq_map, scope_type, scope_key_candidates, lang)
            if not items:
                continue

            faq_block = render_qa_markdown(items)
            new_body, action = inject_marker_block(body, faq_block)
            if action == "unchanged":
                unchanged += 1
                continue

            new_md = (fm_block or "") + (new_body or "")
            if new_md == md:
                unchanged += 1
                continue

            if not args.apply:
                would_change += 1
            else:
                p.write_text(new_md, encoding="utf-8")
            touched_files.append(f"inject_{action}: {p} (scope={scope_type} key={matched_key})")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = Path(args.report) if args.report else Path(f"scripts/reports/faq-sync-{ts}.md")

    lines: List[str] = []
    lines.append(f"- CSV: `{csv_path.as_posix()}`")
    lines.append(f"- Root: `{root.as_posix()}`")
    lines.append(f"- stages: generate_global={do_generate} inject={do_inject} prune={args.prune and args.apply}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- created: {created}")
    lines.append(f"- updated: {updated}")
    lines.append(f"- unchanged: {unchanged}")
    lines.append(f"- skipped_conflict: {skipped_conflict}")
    lines.append(f"- invalid_source: {invalid_source}")
    lines.append(f"- pruned: {pruned}")
    lines.append(f"- would_change: {would_change}")
    lines.append(f"- errors: {errors}")
    lines.append("")
    lines.append("## Touched")
    lines.append("")
    lines.extend([f"- {t}" for t in touched_files] if touched_files else ["- (none)"])
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    lines.extend([f"- {w}" for w in warnings] if warnings else ["- (none)"])

    write_report(report_path, args.apply, lines)
    print(f"[faq_sync] Report: {report_path}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
