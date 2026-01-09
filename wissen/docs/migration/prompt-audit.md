# Prompt Audit (Prompts 1–6)

## Umfeld/Grundlage

`origin/main` ist in diesem Repository nicht vorhanden (keine Remote-Refs konfiguriert). Dadurch schlagen alle Prüfungen gegen `origin/main` fehl und ein belastbarer Merge-Nachweis ist nicht möglich.

**Verifikation:**

```bash
git rev-parse --verify origin/main
```

**Ergebnis:**

```
fatal: Needed a single revision
```

## Statusübersicht

| Prompt-Nr. | Status   | Evidenz | Prüfkriterien |
| --- | --- | --- | --- |
| 1 | NOT DONE | `origin/main` nicht auflösbar (siehe oben). | Existiert in `origin/main`: `wissen/docs/migration/migration-report.md` |
| 2 | NOT DONE | `origin/main` nicht auflösbar (siehe oben). | `categories.csv` enthält Pfade mit `produkte/` statt `oeffentlich/produkte/`; `SSOT.csv` `export_pfad_de` beginnt mit `produkte/` statt `produktinfo/public/` |
| 3 | NOT DONE | `origin/main` nicht auflösbar (siehe oben). | Existiert `wissen/content/de/produkte/_index.md`; mehrere Bundles unter `wissen/content/de/produkte/**/index.md` |
| 4 | NOT DONE | `origin/main` nicht auflösbar (siehe oben). | Existiert `wissen/content/de/faq/beratung/_index.md`; existiert `wissen/content/de/faq/stilkunde/_index.md`; mind. 2 Dateien von `planning-bestellung` nach `faq/beratung` umgehängt |
| 5 | NOT DONE | `origin/main` nicht auflösbar (siehe oben). | Existiert `wissen/docs/migration/validation.md`; Frontmatter `aliases:` vorhanden (grep); ggf. `wissen/static/.htaccess` mit Redirect-Regeln |
| 6 | NOT DONE | `origin/main` nicht auflösbar (siehe oben). | `wissen/content/de/oeffentlich/produkte/` existiert **nicht**; `wissen/content/de/produktinfo/public/` existiert **nicht** |

## Detailprüfungen & Kommandos

### Prompt 1 (Report)

```bash
git cat-file -e origin/main:wissen/docs/migration/migration-report.md
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

### Prompt 2 (CSV rewrites)

```bash
git show origin/main:wissen/ssot/categories.csv | rg -n "produkte/"
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

```bash
git show origin/main:wissen/ssot/SSOT.csv | rg -n "^export_pfad_de"
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

### Prompt 3 (Generator outputs)

```bash
git cat-file -e origin/main:wissen/content/de/produkte/_index.md
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

```bash
git ls-tree -r --name-only origin/main -- wissen/content/de/produkte | rg -n "/index.md$"
```

**Ergebnis:**

```
fatal: Not a valid object name origin/main
```

### Prompt 4 (manuelle Moves FAQ/Stilkunde/Beratung)

```bash
git cat-file -e origin/main:wissen/content/de/faq/beratung/_index.md
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

```bash
git cat-file -e origin/main:wissen/content/de/faq/stilkunde/_index.md
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

```bash
git log --name-status --diff-filter=R origin/main -- wissen/content/de/faq/beratung
```

**Ergebnis:**

```
fatal: bad revision 'origin/main'
```

### Prompt 5 (aliases/links/validation)

```bash
git cat-file -e origin/main:wissen/docs/migration/validation.md
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

```bash
git grep -n "aliases:" origin/main --
```

**Ergebnis:**

```
fatal: unable to resolve revision: origin/main
```

```bash
git cat-file -e origin/main:wissen/static/.htaccess
```

**Ergebnis:**

```
fatal: invalid object name 'origin/main'.
```

### Prompt 6 (prune)

```bash
git ls-tree -d origin/main -- wissen/content/de/oeffentlich/produkte
```

**Ergebnis:**

```
fatal: Not a valid object name origin/main
```

```bash
git ls-tree -d origin/main -- wissen/content/de/produktinfo/public
```

**Ergebnis:**

```
fatal: Not a valid object name origin/main
```

## Empfehlung

Als nächstes **Prompt 1 ausführen**, **nachdem** eine Remote-Referenz `origin/main` verfügbar ist (oder ein Remote hinzugefügt wurde). Ohne `origin/main` können die Merge-Checks für alle Prompts nicht automatisiert verifiziert werden.
