# Duplicate-Policy (Wissen vs. Shop)

## Ziel
Duplicate/near-duplicate Inhalte zwischen `/wissen/de/` (Wissen) und `/de/` (Shop) werden vermieden, um klare Rankings, saubere Indexierung und eindeutige Nutzerpfade sicherzustellen.

## Praktische Regeln
1. **Kein Copy/Paste von Shop-Produkttexten in Wissensartikel.**
   - Wissensinhalte müssen eigenständig formuliert sein.
2. **Produktdaten bleiben im Shop.**
   - Preise, Varianten, Lieferzeiten, Bestand, SKU, CTAs für Kauf sind Shop-only.
3. **Wissen liefert Kontext statt Katalog.**
   - Einsatzbereiche, Pflege, Historie, Planung, Materialkunde, Montage.
4. **Canonical & Knowledge-URL**
   - Wissensseiten behalten ihre eigene Canonical URL.
   - Shop-seitige Canonicals zeigen auf Shop-URLs, nicht auf Wissen.
5. **Seitenzweck klar trennen.**
   - Kategorie-Seiten im Wissen erklären und kuratieren.
   - Kategorie-Seiten im Shop listen und verkaufen.

## Umsetzungshinweise (Hugo)
- **Content-Checkliste vor Veröffentlichung:**
  - Hat die Wissensseite eigene Einleitung, Kontext und Nutzen?
  - Keine identischen Absatzblöcke aus dem Shop.
  - CTA führt zum Shop, aber kein doppelter Produkttext.
- **Linking:**
  - Wissensseiten verlinken auf die passende Shop-URL mit UTM optional.
  - Shop-Seiten verlinken auf Wissensartikel, wenn diese Beratungsmehrwert bieten.
- **Structured Data:**
  - Wissensseiten: FAQ, Article, HowTo (falls passend).
  - Shop-Seiten: Product, Offer.

## Beispiele
- **Erlaubt:** „Wie wählt man historische Sockelleisten?“ + Link zur Shop-Kategorie.
- **Nicht erlaubt:** Vollständige Shop-Produktbeschreibung inkl. Maße/Preis im Wissen.
