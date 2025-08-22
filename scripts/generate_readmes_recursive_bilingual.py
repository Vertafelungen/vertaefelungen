import os
import yaml

BASE_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', 'vertaefelungen')
LANG_DIRS = ['de', 'en']

def extract_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if content.startswith('---'):
        parts = content.split('---')
        if len(parts) >= 3:
            return yaml.safe_load(parts[1])
    return {}

def generate_product_readme(path, lang='de'):
    entries = []
    for filename in sorted(os.listdir(path)):
        if filename.endswith('.md') and not filename.startswith('README'):
            filepath = os.path.join(path, filename)
            data = extract_yaml(filepath)
            titel_key = 'titel_de' if lang == 'de' else 'titel_en'
            beschr_key = 'beschreibung_md_de' if lang == 'de' else 'beschreibung_md_en'
            titel = data.get(titel_key, filename.replace('.md', ''))
            beschreibung = data.get(beschr_key, '')
            slug = filename.replace('.md', '')
            entries.append(f"- [{titel}](./{slug}.md): {beschreibung}")

    if entries:
        content = f"""# {os.path.basename(path).replace('-', ' ').title()}

Diese Übersicht listet alle enthaltenen Produkte mit Beschreibung:

{chr(10).join(entries)}

---

Diese Inhalte stammen von [vertaefelungen.de](https://www.vertaefelungen.de) und unterliegen der CC BY-NC-ND 4.0 Lizenz. Autor: Vertäfelung & Lambris
"""
        with open(os.path.join(path, 'README.md'), 'w', encoding='utf-8') as f:
            f.write(content)

def generate_folder_readme(path):
    subdirs = [d for d in sorted(os.listdir(path)) if os.path.isdir(os.path.join(path, d))]
    entries = []
    for sub in subdirs:
        subpath = os.path.join(path, sub)
        if os.path.isdir(subpath):
            entries.append(f"- [{sub}](./{sub}/README.md)")

    if entries:
        content = f"""# {os.path.basename(path).title()}

Dieser Ordner enthält folgende Unterverzeichnisse:

{chr(10).join(entries)}

---

Diese Inhalte stammen von [vertaefelungen.de](https://www.vertaefelungen.de) und unterliegen der CC BY-NC-ND 4.0 Lizenz. Autor: Vertäfelung & Lambris
"""
        with open(os.path.join(path, 'README.md'), 'w', encoding='utf-8') as f:
            f.write(content)

def process_path(path, lang='de'):
    has_md = any(f.endswith('.md') and not f.startswith('README') for f in os.listdir(path))
    has_dirs = any(os.path.isdir(os.path.join(path, f)) for f in os.listdir(path))

    if has_md:
        generate_product_readme(path, lang)
    elif has_dirs:
        generate_folder_readme(path)

    for f in os.listdir(path):
        sub = os.path.join(path, f)
        if os.path.isdir(sub):
            process_path(sub, lang)

for lang in LANG_DIRS:
    lang_path = os.path.join(BASE_ROOT, lang)
    if os.path.exists(lang_path):
        process_path(lang_path, lang)
