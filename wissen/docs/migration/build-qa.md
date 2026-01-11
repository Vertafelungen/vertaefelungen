# Build QA (Variante B Quickcheck)

## Build
- Status: Skipped (hugo not available in this environment)
- Hinweis: Build/Deploy-Prüfung über GitHub Actions ist maßgeblich.

## Geprüfte Einstiegs-URLs (strukturell)
### DE
- `/wissen/de/faq/`
- `/wissen/de/produkte/`
- `/wissen/de/lookbook/`
- `/wissen/de/shop/`

### EN
- `/wissen/en/faq/`
- `/wissen/en/products/`
- `/wissen/en/lookbook/`
- `/wissen/en/shop/`

## Struktur-Minimalcheck (Dateisystem)
### DE
- OK: `wissen/content/de/faq/_index.md`
- OK: `wissen/content/de/produkte/_index.md`
- OK: `wissen/content/de/lookbook/_index.md`
- OK: `wissen/content/de/shop/_index.md`
- OK: `wissen/content/de/produkte/halbhohe-vertaefelungen/_index.md`
- OK: `wissen/content/de/produkte/hohe-vertaefelungen/_index.md`
- OK: `wissen/content/de/produkte/leisten/_index.md`
- OK: `wissen/content/de/produkte/oele-farben/_index.md`
- OK: `wissen/content/de/produkte/oele-farben/beeck/_index.md`
- Missing: `wissen/content/de/produkte/oele-farben/beeck/sip-m/_index.md`
- Missing: `wissen/content/de/produkte/oele-farben/beeck/sip-v/_index.md`
- Missing: `wissen/content/de/produkte/oele-farben/beeck/vstp/_index.md`
- OK: `wissen/content/de/produkte/oele-farben/leinoel-tung/_index.md`

### EN
- OK: `wissen/content/en/faq/_index.md`
- OK: `wissen/content/en/products/_index.md`
- OK: `wissen/content/en/lookbook/_index.md`
- OK: `wissen/content/en/shop/_index.md`
- OK: `wissen/content/en/products/dado-panel/_index.md`
- OK: `wissen/content/en/products/high-wainscoting/_index.md`
- OK: `wissen/content/en/products/mouldings/_index.md`
- OK: `wissen/content/en/products/oil-paint/_index.md`
- OK: `wissen/content/en/products/rosettes/_index.md`

## Merge-Hinweis
- Struktur-Minimalcheck enthält Missing-Einträge → Merge NICHT empfohlen.
