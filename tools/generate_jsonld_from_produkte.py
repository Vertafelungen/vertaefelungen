
import json
import os
import sys

# Sprachparameter prüfen
if len(sys.argv) < 2 or sys.argv[1] not in ["de", "en"]:
    print("❌ Bitte Sprache angeben: 'de' oder 'en'")
    sys.exit(1)

lang = sys.argv[1]
input_path = f"../produkte.{lang}.json"
output_path = f"../produkte-jsonld.{lang}.json"

# Basis-URL und Sprachpfad
BASE_URL = "https://www.vertaefelungen.de"
LANG_PATH = f"/{lang}"

# Sprachabhängige Felder
title_field = f"titel_{lang}"
desc_field = f"beschreibung_md_{lang}"

try:
    with open(input_path, "r", encoding="utf-8") as f:
        produkte = json.load(f)
except Exception as e:
    print(f"❌ Fehler beim Laden von {input_path}: {e}")
    sys.exit(1)

jsonld_list = []
valid_count = 0
error_count = 0

for index, produkt in enumerate(produkte):
    if not isinstance(produkt, dict):
        print(f"⚠️  Eintrag {index} ist kein gültiges Objekt: {produkt}")
        error_count += 1
        continue

    slug = produkt.get("slug")
    titel = produkt.get(title_field)
    beschreibung = produkt.get(desc_field, "")[:500]
    bilder = produkt.get("bilder_liste", [])
    preis = produkt.get("preis", "")
    verfuegbarkeit = produkt.get("verfuegbarkeit", "in_stock").lower()
    brand = produkt.get("marke", "Vertäfelung & Lambris")

    # Pflichtfelder prüfen
    if not all([slug, titel, preis]):
        print(f"⚠️  Eintrag {index} unvollständig: slug={slug}, titel={titel}, preis={preis}")
        error_count += 1
        continue

    bild_urls = [f"{BASE_URL}/{bild}" for bild in bilder]

    jsonld_obj = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "@id": f"{BASE_URL}{LANG_PATH}/{slug}",
        "name": titel,
        "description": beschreibung,
        "image": bild_urls,
        "brand": {
            "@type": "Organization",
            "name": brand
        },
        "offers": {
            "@type": "Offer",
            "priceCurrency": "EUR",
            "price": preis,
            "availability": f"https://schema.org/{'InStock' if verfuegbarkeit == 'in_stock' else 'OutOfStock'}",
            "url": f"{BASE_URL}{LANG_PATH}/{slug}"
        }
    }

    jsonld_list.append(jsonld_obj)
    valid_count += 1

# Ergebnis speichern
try:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(jsonld_list, f, ensure_ascii=False, indent=2)
    print(f"✅ Export abgeschlossen: {valid_count} gültig, {error_count} übersprungen → {output_path}")
except Exception as e:
    print(f"❌ Fehler beim Speichern der Datei: {e}")
    sys.exit(1)
