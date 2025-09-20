#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py
Version: 2025-09-20 08:01 (Europe/Berlin)

import os, re, io
import markdown, yaml

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wissen")

# Markdown-Converter initialisieren (mit ein paar Extra-Extensions für erweitertes MD)
md_converter = markdown.Markdown(extensions=['extra'])

for root, dirs, files in os.walk(BASE_DIR):
    for filename in files:
        if not filename.lower().endswith(".md"):
            continue
        filepath = os.path.join(root, filename)
        # Markdown-Datei einlesen
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        # YAML-Frontmatter parsen (falls vorhanden)
        meta = {}
        content_md = text
        if text.strip().startswith("---"):
            parts = text.split("---", 2)
            # parts[0] = '' (vor erstem ---), parts[1] = YAML, parts[2] = rest nach zweitem ---
            if len(parts) >= 3:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except Exception as e:
                    meta = {}
                content_md = parts[2]
        content_md = content_md.lstrip("\r\n")  # führende Zeilenumbrüche entfernen

        # Markdown → HTML konvertieren
        html_body = md_converter.reset().convert(content_md)

        # HTML-Entities deutscher Umlaute in echte Zeichen umwandeln
        entity_map = {
            "&auml;": "ä", "&Auml;": "Ä",
            "&ouml;": "ö", "&Ouml;": "Ö",
            "&uuml;": "ü", "&Uuml;": "Ü",
            "&szlig;": "ß"
        }
        for entity, char in entity_map.items():
            html_body = html_body.replace(entity, char)

        # Häufige UTF-8-Mojibake-Sequenzen reparieren (Ã¶ -> ö usw.)
        mojibake_map = {
            "Ã¤": "ä", "Ã„": "Ä",
            "Ã¶": "ö", "Ã–": "Ö",
            "Ã¼": "ü", "Ãœ": "Ü"
        }
        for bad, good in mojibake_map.items():
            html_body = html_body.replace(bad, good)
        if "Ã" in html_body:
            try:
                # Allgemeiner Fix: als Latin-1 Bytes interpretieren und in UTF-8 dekodieren
                html_body = html_body.encode("latin-1").decode("utf-8")
            except Exception:
                pass

        # Interne Links von *.md auf *.html ändern
        html_body = re.sub(r'href="(?!https?://)([^"]+)\.md(#[^"]*)?"',
                           r'href="\1.html\2"', html_body)

        # Sprache für <html>-Tag bestimmen (aus Pfad: 'de' oder 'en')
        rel_path = os.path.relpath(root, BASE_DIR)
        first_dir = rel_path.split(os.sep)[0] if rel_path != "." else ""
        lang = "de" if first_dir.lower() == "de" else ("en" if first_dir.lower() == "en" else "de")

        # HTML <title> setzen (Titel aus YAML oder aus erster Überschrift)
        title_text = ""
        if isinstance(meta.get("title"), str):
            title_text = meta["title"]
        if not title_text:
            # Falls im Markdown eine H1-Überschrift vorhanden ist, deren Text nehmen
            match = re.search(r'<h1[^>]*>(.*?)</h1>', html_body, flags=re.IGNORECASE)
            if match:
                # HTML-Tags aus dem Heading-Text entfernen
                title_text = re.sub(r'<[^>]+>', '', match.group(1))
        if not title_text:
            # Fallback: Dateiname ohne Extension
            title_text = os.path.splitext(filename)[0]

        # HTML-Grundgerüst zusammenbauen
        html_content = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <title>{title_text}</title>
</head>
<body>
{html_body}
</body>
</html>
"""

        # Ausgabedateinamen bestimmen (.html, README.md -> index.html)
        output_name = filename[:-3] + ".html"
        if filename.lower() == "readme.md":
            output_name = "index.html"
        output_path = os.path.join(root, output_name)

        # HTML-Datei speichern (UTF-8)
        with open(output_path, "w", encoding="utf-8") as f_out:
            f_out.write(html_content)
        # Optional: Logging
        print(f"Converted {filepath} -> {output_path}")
