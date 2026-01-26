# Structured Data – Phase 5.1 (Wissen)

## Einsatzregeln (kontextabhängig)
- **Product**: Nur auf Wissensseiten mit eindeutigem Produktbezug **und** eindeutigem Shop-Link.
  - Pflichtfelder: `name`, `description`, `image`.
  - Optional: `brand` (nur wenn vorhanden).
  - **Nicht gesetzt**: `offers`, `price`, `availability`, `aggregateRating`.
- **FAQPage**: Nur auf Seiten mit echten, sichtbaren Frage/Antwort-Paaren (aus dem Markdown).
  - Keine automatisch generierten Fragen.
  - Keine Kombination mit Product.
- **Article / WebPage**: Leichtgewichtig für redaktionelle Seiten, Lookbook-Übersichten und Hintergrundseiten.
  - Felder: `headline`, `description`, `inLanguage`, `mainEntityOfPage`.

## Bewusste Nicht-Nutzung
- Keine Preis-, Angebots- oder Verfügbarkeitsdaten im Wissensbereich.
- Kein Product-Markup auf Platzhalter- oder Übersichtsseiten ohne eindeutiges Einzelprodukt.
- Kein „Schema-Over-Markup“: pro Seite maximal ein Haupttyp.

## Manuelle Prüfung
- **Google Rich Results Test**: Prüfen, ob gewünschte Typen erkannt werden.
- **Search Console – URL Inspection**: Validierung der erkannten strukturierten Daten je URL.
