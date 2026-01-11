# EN Redirects: consulting/style-guide -> faq

## Rewrite-Context

Die aktive Wissens-`.htaccess` wird unter `/wissen/` ausgeliefert, daher matchen die Regeln im Kontext von `/wissen/` auf `^en/…` (ohne `/wissen/`-Prefix).

## Regeln

```apache
RewriteRule ^en/consulting/?$ en/faq/consulting/ [R=301,L]
RewriteRule ^en/consulting/(.*)$ en/faq/consulting/$1 [R=301,L]
RewriteRule ^en/style-guide/?$ en/faq/style-guide/ [R=301,L]
RewriteRule ^en/style-guide/(.*)$ en/faq/style-guide/$1 [R=301,L]
```

## Testfälle (alt → neu)

1. `/wissen/en/consulting/` → `/wissen/en/faq/consulting/`
2. `/wissen/en/consulting/process/` → `/wissen/en/faq/consulting/process/`
3. `/wissen/en/consulting/services/briefing/` → `/wissen/en/faq/consulting/services/briefing/`
4. `/wissen/en/style-guide/` → `/wissen/en/faq/style-guide/`
5. `/wissen/en/style-guide/typography/weights/` → `/wissen/en/faq/style-guide/typography/weights/`
