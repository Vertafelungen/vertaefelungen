# Redirect-Validierung (301 Canonicalisierung)

Diese Liste dient als schnelle Prüfung für historische Dupe-URLs der Wissensseite.
Alle Aufrufe sollen **direkt** (ohne Ketten) auf die kanonische URL mit **301** zeigen.

## Beispiel-Checks (5 Alt-URLs)

> Ersetze bei Bedarf den Host. Beispiel nutzt die Produktiv-Domain.

1. `https://www.vertaefelungen.de/wissen/de/de/produkte/`
   - Erwartet: `https://www.vertaefelungen.de/wissen/de/produkte/`
2. `https://www.vertaefelungen.de/wissen/en/en/products/`
   - Erwartet: `https://www.vertaefelungen.de/wissen/en/products/`
3. `https://www.vertaefelungen.de/wissen/de/de/faq/`
   - Erwartet: `https://www.vertaefelungen.de/wissen/de/faq/`
4. `https://www.vertaefelungen.de/wissen/de/produkte/produkte/`
   - Erwartet: `https://www.vertaefelungen.de/wissen/de/produkte/`
5. `https://www.vertaefelungen.de/wissen/en/products/products/`
   - Erwartet: `https://www.vertaefelungen.de/wissen/en/products/`

## Beispiel mit curl

```bash
curl -I https://www.vertaefelungen.de/wissen/de/de/produkte/
```

Prüfen:
- `HTTP/1.1 301` oder `HTTP/2 301`
- `Location` zeigt direkt auf die kanonische URL (kein weiterer Redirect).
