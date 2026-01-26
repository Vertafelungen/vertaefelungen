# Phase 4.3 – Indexierungssteuerung (Redundante URLs)

## Historische redundante URL-Muster
- `/wissen/de/de/*`
- `/wissen/en/en/*`
- `/wissen/de/produkte/produkte/*`
- `/wissen/en/products/products/*`

## Aktive Maßnahmen
**Primärstrategie:** Serverseitige 301-Redirects über `wissen/static/.htaccess`.
- Querystrings werden beibehalten.
- Ziel ist immer die saubere, kanonische URL.
- Redundante Seiten sollen im Output nicht mehr existieren.

**Fallback (nur wenn Redirects nicht möglich sind):**
- `noindex,follow` + canonical auf die saubere URL.

## GSC-Prüfanleitung (URL-Inspection)
1. Saubere URL prüfen (z. B. `/wissen/de/...`).
   - **User-declared canonical:** saubere URL.
   - **Google-selected canonical:** identisch.
   - **Indexierungsstatus:** „Indexiert“ (sofern Seite indexierbar ist).
2. Redundante URL prüfen (z. B. `/wissen/de/de/...`).
   - Bei Redirects: 301 auf die saubere URL.
   - Bei noindex-Variante: „Excluded by ‘noindex’“ + canonical auf die saubere URL.

## Beispiel-URLs
- DE clean: `https://www.vertaefelungen.de/wissen/de/produkte/`
- DE redundant: `https://www.vertaefelungen.de/wissen/de/de/produkte/`
- EN clean: `https://www.vertaefelungen.de/wissen/en/products/`
- EN redundant: `https://www.vertaefelungen.de/wissen/en/en/products/`
- DE redundant products: `https://www.vertaefelungen.de/wissen/de/produkte/produkte/`
