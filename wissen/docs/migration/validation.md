# Validation Report

- Datum/Uhrzeit (UTC): 2026-01-09 11:24 UTC
- Branch: migration-tree-klickdummy-2026-01-09

## Command Results (Kurzfassung)

- `python wissen/scripts/guard_validate.py`: Fehlgeschlagen – `ModuleNotFoundError: No module named 'ruamel'`.
- `python wissen/scripts/lint_content_frontmatter.py`: Erfolgreich (kein Output, Exit-Code 0).
- `cd wissen && hugo --minify`: Fehlgeschlagen – `bash: command not found: hugo`.

## Beispiel-URLs (sollen funktionieren)

1. `/de/faq/beratung/planung-bestellung/`
2. `/de/faq/beratung/angebotserstellung/`
3. `/de/faq/beratung/montage/`
4. `/de/faq/stilkunde/geschichtliches/`
5. `/de/faq/stilkunde/holzvertaefelungen-im-altbau/`
6. `/de/produkte/halbhohe-vertaefelungen/57-p0018/`
7. `/de/produkte/halbhohe-vertaefelungen/23-p0001/`
8. `/de/produkte/hohe-vertaefelungen/24-p0002/`
9. `/de/produkte/leisten/sockelleisten/40-sl0001/`
10. `/de/produkte/oele-farben/leinoel-tung/61-loen/`
