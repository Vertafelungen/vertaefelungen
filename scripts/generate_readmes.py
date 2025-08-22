import os
import yaml

BASE_DIR = 'vertaefelungen/de/oeffentlich/produkte'

def extract_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if content.startswith('---'):
        parts = content.split('---')
        if len(parts) >= 3:
            return yaml.safe_load(parts[1])
    return {}

def generate_readme_for_category(category_path):
    entries = []
    for filename in sorted(os.listdir(category_path)):
        if filename.endswith('.md') and not filename.startswith('README'):
            filepath = os.path.join(category_path, filename)
            data = extract_yaml(filepath)
            titel = data.get('titel_de', filename.replace('.md', ''))
            beschreibung = data.get('beschreibung_md_de', '')
            slug = filename.replace('.md', '')
            entries.append(f"- [{titel}](./{slug}.md): {beschreibung}")

    readme_content = f"""# {os.path.basename(category_path).replace('-', ' ').title()}

Diese Übersicht listet alle enthaltenen Produkte mit Beschreibung:

{chr(10).join(entries)}

---

Diese Inhalte stammen von [vertaefelungen.de](https://www.vertaefelungen.de) und unterliegen der CC BY-NC-ND 4.0 Lizenz. Autor: Vertäfelung & Lambris
"""
    with open(os.path.join(category_path, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme_content)

# Alle Unterordner durchgehen
for root, dirs, files in os.walk(BASE_DIR):
    if any(f.endswith('.md') and not f.startswith('README') for f in files):
        generate_readme_for_category(root)
