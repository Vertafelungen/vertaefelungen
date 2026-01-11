# Legacy Redirects (Variant B)

## Kontext

Die aktive Wissens-`.htaccess` liegt unter `wissen/static/.htaccess` und wird im Deployment unter `/wissen/` ausgeliefert. Damit greift der Rewrite-Context auf `/wissen/` und die Regeln matchen auf `^de/…` bzw. `^en/…` (ohne `/wissen/`-Prefix).

## Regeln (neu ergänzt)

```apache
# DE: alte Prefixe -> neue
RewriteRule ^de/oeffentlich/produkte/?$ de/produkte/ [R=301,L]
RewriteRule ^de/oeffentlich/produkte/(.*)$ de/produkte/$1 [R=301,L]
RewriteRule ^de/produktinfo/public/(.*)$ de/produkte/$1 [R=301,L]
RewriteRule ^de/produktinfo/?$ de/produkte/ [R=301,L]
RewriteRule ^de/produktinfo/(.*)$ de/produkte/$1 [R=301,L]

# EN (falls relevant; sonst trotzdem ok)
RewriteRule ^en/public/products/?$ en/products/ [R=301,L]
RewriteRule ^en/public/products/(.*)$ en/products/$1 [R=301,L]
RewriteRule ^en/products/public/(.*)$ en/products/$1 [R=301,L]
```

## Test-URLs (alt → neu)

1. `/wissen/de/produktinfo/` → `/wissen/de/produkte/`
2. `/wissen/de/produktinfo/halbhohe-vertaefelungen/52-p0011/` → `/wissen/de/produkte/halbhohe-vertaefelungen/52-p0011/`
3. `/wissen/de/produktinfo/public/halbhohe-vertaefelungen/52-p0011/` → `/wissen/de/produkte/halbhohe-vertaefelungen/52-p0011/`
4. `/wissen/de/produktinfo/public/leisten/wandleisten/82-wl07/` → `/wissen/de/produkte/leisten/wandleisten/82-wl07/`
5. `/wissen/de/oeffentlich/produkte/` → `/wissen/de/produkte/`
6. `/wissen/de/oeffentlich/produkte/halbhohe-vertaefelungen/35-p0022/` → `/wissen/de/produkte/halbhohe-vertaefelungen/35-p0022/`
7. `/wissen/en/public/products/` → `/wissen/en/products/`
8. `/wissen/en/public/products/high-wainscoting/47-p0017/` → `/wissen/en/products/high-wainscoting/47-p0017/`
9. `/wissen/en/products/public/mouldings/wall/82-wl07/` → `/wissen/en/products/mouldings/wall/82-wl07/`
10. `/wissen/en/products/public/rosettes/71-blr1/` → `/wissen/en/products/rosettes/71-blr1/`
