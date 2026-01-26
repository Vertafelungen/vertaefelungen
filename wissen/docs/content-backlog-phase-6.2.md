# Content Backlog – Phase 6.2

Phase 6.2 erzeugt aus den Retrieval-Exports und Verifikations-Reports ein priorisiertes Content-Backlog
(Reporting-only, keine CI-Blocker). Das Backlog wird als Markdown und JSON geschrieben und in CI als
Artifact bereitgestellt.

## Zweck

- Systematische Priorisierung von Content-Arbeit (Placeholder ersetzen, Descriptions ergänzen, dünne Seiten).
- Deterministisches Scoring mit stabiler Sortierung (score desc, url asc).
- Reporting-Phase: fehlende Inputs werden dokumentiert, aber die CI bleibt grün.

## Inputs

- Exporte:
  - `wissen/public/export/index.de.json`
  - `wissen/public/export/index.en.json`
- Reports (optional):
  - `wissen/scripts/reports/retrieval_export_report.json`
  - `wissen/scripts/reports/retrieval_export_verification_report.json`

## Outputs

- `wissen/scripts/reports/content_backlog.de.md`
- `wissen/scripts/reports/content_backlog.en.md`
- `wissen/scripts/reports/content_backlog.json`

## Wichtige Felder

### Score-Regeln (fix)

- +6 `is_placeholder`
- +4 fehlende Beschreibung
- +4 `body_text` < 400
- +2 `indexable == true`
- +2 strategischer Bereich (`/produkte/` oder `/faq/`)
- +1 keine H2/H3-Headings
- -6 `indexable == false`

### Area-Ableitung (nur URL-Prefix)

- `products`: `/wissen/de/produkte/` oder `/wissen/en/products/`
- `faq`: `/wissen/de/faq/` oder `/wissen/en/faq/`
- `lookbook`: `/wissen/de/lookbook/` oder `/wissen/en/lookbook/`
- `shop-bridge`: `/wissen/de/shop/` oder `/wissen/en/shop/`
- `legal`: `/wissen/de/(impressum|datenschutz|agb|widerruf|kontakt)/` usw.
- `other`: alles andere

### Debug/Reporting

- `nav_like_body_text`, `missing_html_expected`, `missing_html_unexpected` werden nur als Hinweis
  geführt (kein Score-Einfluss).
- Report-URLs ohne Match zum Export werden im Debug-Block als `unmatched_report_issue` zusammengefasst.
