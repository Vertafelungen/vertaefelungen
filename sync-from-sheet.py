
import os
import pandas as pd
import re

def format_markdown_lint_safe(text):
    """Lint-konforme Formatierung: max. 80 Zeichen pro Zeile, korrekte Einrückung"""
    lines = text.strip().splitlines()
    fixed_lines = []
    for line in lines:
        # Kommentare und Listen nicht umbrechen
        if line.lstrip().startswith("- ") or line.startswith("#"):
            fixed_lines.append(line)
        else:
            while len(line) > 80:
                cut = line[:80].rfind(" ")
                if cut == -1: break
                fixed_lines.append(line[:cut])
                line = line[cut+1:]
            fixed_lines.append(line)
    return "\n".join(fixed_lines) + "\n"

def build_content(row, lang):
    yaml_block = f"""---
title: {row['title_' + lang]}
slug: {row['slug']}
source: {row.get('source_' + lang, '')}
last_updated: {row.get('last_updated', '')}
author: Vertäfelung & Lambris
licence: CC BY-SA 4.0
---
""".strip()

    body_parts = []
    if 'beschreibung_' + lang in row and row['beschreibung_' + lang]:
        body_parts.append(row['beschreibung_' + lang])
    if 'varianten_yaml' in row and isinstance(row['varianten_yaml'], str):
        variants = row['varianten_yaml'].strip().split("\n")
        if variants:
            body_parts.append("## Varianten\n")
            for variant in variants:
                if variant.strip():
                    body_parts.append(f"- {variant.strip()}")

    content = format_markdown_lint_safe(yaml_block + "\n\n" + "\n".join(body_parts))
    return content

def write_md_files(df, lang):
    path_col = 'export_pfad_' + lang
    slug_col = 'slug'
    for _, row in df.iterrows():
        if not pd.notnull(row[slug_col]): continue
        md_path = os.path.join(row[path_col], row[slug_col] + ".md")
        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(build_content(row, lang))

if __name__ == "__main__":
    df = pd.read_excel("vertaefelungen.xlsx")
    write_md_files(df, "de")
    write_md_files(df, "en")
