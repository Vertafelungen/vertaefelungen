# Wissen vs. Shop (Architektur & Rollen)

## Zielbild
- **Wissensbereich (/wissen/de/)** ist die primäre Ranking-URL für SEO und informiert, inspiriert und erklärt. Er führt Nutzer:innen über klar erkennbare Übergänge zum Shop, ohne selbst Transaktionen abzuwickeln.
- **Shop (/de/)** ist der transaktionale Bereich für Kauf, Preis, Verfügbarkeit, Konfiguration und Checkout.

## Rollen & Verantwortlichkeiten
- **Wissen (Hugo):**
  - Erklär- und Beratungsinhalte, Produktwissen, Projektbeispiele, FAQs.
  - Suchmaschinenrelevante Inhalte (Long-Tail, Glossar, Anwendung, Materialkunde).
  - Strukturierte Inhalte (Knowledge Graph, FAQ-Snippets), ohne Shop-Features.
- **Shop (PrestaShop):**
  - Produktkatalog mit Preisen, Varianten, Warenkorb, Checkout.
  - Rechtliche Inhalte (AGB, Zahlung, Lieferung) im Kontext des Kaufs.
  - Conversion-optimierte Templates und Tracking.

## Verlinkung & Übergänge
- **Wissen → Shop**
  - Jede Produkt- oder Kategorie-Seite im Wissen verweist auf die Shop-Entsprechung (CTA, Primärlink).
  - CTAs sind klar als „Zum Shop/Zum Produkt“ gekennzeichnet.
  - Parameter (UTM) sind erlaubt, aber sparsam einzusetzen.
- **Shop → Wissen**
  - Shop verlinkt auf passende Wissensartikel (Ratgeber, Montage, Pflege) zur Beratung.
  - Keine Rückverlinkung auf reine Shop-Aktionsseiten aus Wissensartikeln.

## Content-Regeln (kurz)
- **Keine Duplikate:** Wissensartikel dürfen keine Shop-Produkttexte 1:1 übernehmen.
- **Mehrwert:** Wissen liefert Kontext, Anwendung, Pflege, historische Einordnung.
- **Striktes Rollenverständnis:** Wissensbereich hat kein Pricing/Checkout/Bestand.
- **Primäre URL:** SEO-relevante Wissensinhalte leben unter `/wissen/de/`.

## Struktur- und Template-Hinweise
- **Layouts:** Wiedererkennbare Header/Footer, aber ohne Shop-Funktionen (Warenkorb, Preise).
- **Design:** „Shop-nahes Look&Feel“ für Markenstimmigkeit, jedoch inhaltlich getrennt.
- **Sitemaps/Robots:** Wissen bleibt indexierbar, Shop-Pfade bleiben transaktional.
