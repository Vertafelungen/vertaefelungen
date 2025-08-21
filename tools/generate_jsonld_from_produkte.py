
import json
import os
from datetime import datetime

# Eingabe- und Ausgabe-Datei definieren
input_path = "produkte.de.json"
output_path = "produkte-jsonld.de.json"

# Basis-URL deiner Website
BASE_URL = "https://www.vertaefelungen.de"

# JSON-Datei laden
with open(input_path, "r", encoding="utf-8") as f:
    produkte = json.load(f)

# JSON-LD Liste vorbereiten
jsonld_list = []

for produkt in produkte:
    slug = produkt.get("slug")
    titel = produkt.get("titel_de")
    beschreibung = produkt.get("beschreibung_md_de", "")[:500]  # ggf. kürzen
    bilder = produkt.get("bilder_liste", [])
    bild_urls = [f"{BASE_URL}/{bild}" for bild in bilder]

    preis = produkt.get("preis", "")
    verfuegbarkeit = produkt.get("verfuegbarkeit", "in_stock").lower()
    brand = produkt.get("marke", "Vertäfelung & Lambris")

    jsonld_obj = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "@id": f"{BASE_URL}/de/{slug}",
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
            "url": f"{BASE_URL}/de/{slug}"
        }
    }

    jsonld_list.append(jsonld_obj)

# JSON-LD speichern
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(jsonld_list, f, ensure_ascii=False, indent=2)

print(f"✅ JSON-LD erfolgreich exportiert: {output_path}")
