<!--
File: wissen/docs/ssot-content-schema-spec.md
Version: 2026-02-14T13:10:00+01:00 (Europe/Berlin)
Scope: Normative Spezifikation für SSOT-basierte Content-Pipeline (Produkte + Kategorien + FAQ)
-->

# SSOT Content Schema Spec (Produkte + Kategorien + FAQ)

## 0) Ziel
Wir definieren einen **Pipeline-Contract**, der garantiert:
- **SSOT ist Quelle der Wahrheit** für SSOT-owned Seiten.
- Generatoren erstellen daraus deterministisch Markdown unter `wissen/content/**`.
- **Kein** manuell oder per Codex erstellter Text wird im Normalbetrieb „wegüberschrieben“, weil Codex künftig primär **CSV** authort.

---

## 1) Ownership (verbindlich)

### 1.1 SSOT-owned
- Produktseiten und Kategorien, die aus CSVs generiert werden.
- **Regel:** Änderungen direkt in `wissen/content/**` sind nicht dauerhaft.

### 1.2 Editorial-owned
- Redaktionelle Wissensseiten außerhalb SSOT-Erzeugung.
- **Regel:** SSOT-Writer und Post-Processor dürfen sie **niemals** anfassen.

### 1.3 Scoping-Enforcement (MUSS)
- Writer dürfen **nur** Pfade anfassen, die in CSVs referenziert sind.
- Post-Processor (Link-/Image-Fixes) darf nur:
  - a) Dateien anfassen, die in diesem Run geändert wurden, oder
  - b) Dateien mit `managed_by: ssot-sync`.

---

## 2) Layout vs. Inhalt
- **Layout (HTML-Struktur, Karten, Auto-Listen):** Hugo Layouts/Partials.
- **Inhalt (Texte, FAQ, interne Verweise, Metadaten, Bilderliste):** CSVs + Generator-Skripte.

Da Layout „freeze“ ist, erzeugen Generatoren den Markdown-Body im gewünschten Schema.

---

## 3) Quellen der Wahrheit (Repo)

### 3.1 Produkte
- `wissen/ssot/SSOT.csv`  
  → Produktdaten + Produkttext (ohne FAQ)

### 3.2 Kategorien
- `wissen/ssot/categories.csv`  
  → Kategoriepfade + Kategorietext (ohne FAQ)

### 3.3 FAQ (NEU)
- `wissen/ssot/faq.csv`  
  → Alle FAQs für Produkte und Kategorien, inkl. Routing/Zuordnung

**Wichtig:** FAQ-Content wird **nicht mehr** in `SSOT.csv`/`categories.csv` gepflegt, sondern in `faq.csv`.

---

## 4) Mapping- und Pfad-Invarianten (MUSS)

### 4.1 Eindeutigkeit
- Pro Sprache gilt:
  - `export_pfad_de` / `export_pfad_en` ist pro Seite eindeutig (keine Duplikate).
  - `translationKey` (falls genutzt) ist eindeutig.

### 4.2 Konsistenz
- `produkt.id` muss zum `export_pfad_*` passen (Validierung).
- Keine „Zusatzseiten“ ohne explizite Anweisung (z. B. `aliases_*`).

### 4.3 Pfad-Policy
- CSV enthält den kanonischen Exportpfad **ohne** `/wissen`.
- Writer darf Pfade nur erstellen/umbauen, wenn CSV das verlangt.

---

## 5) Content-Schema (Body) für Produkte und Kategorien

### 5.1 Gemeinsames 8-Abschnitt-Schema (Output)
1) Kurzantwort (3–6 Bullets)  
2) Praxis-Kontext  
3) Entscheidung/Varianten  
4) Ablauf/Planung  
5) Kostenlogik (ohne Preisversprechen)  
6) Häufige Fehler + Vermeidung  
7) Verweise (intern) (2–5)  
8) FAQ (aus `faq.csv`, siehe Abschnitt 6)

### 5.2 Textspalten in SSOT.csv / categories.csv (ohne FAQ)
Wir pflegen Abschnittsinhalte in separaten Spalten; Überschriften setzt der Generator.

**DE**
- `body_de_kurzantwort`
- `body_de_praxis`
- `body_de_varianten`
- `body_de_ablauf`
- `body_de_kosten`
- `body_de_fehler`
- `body_de_verweise`

**EN** analog (`body_en_*`).

> Legacy: Falls bisher `body_*_faq` existiert, gilt: **deprecated**. Generator soll künftig FAQ ausschließlich aus `faq.csv` ziehen.

---

## 6) FAQ-Policy (NEU) – `faq.csv` ist alleinige Quelle

### 6.1 Zuordnung (Scope)
Jede FAQ-Zeile gehört zu genau einem Scope:

- `scope_type = product` → Zuordnung über `scope_key = product_id` (z. B. `TR01/160`)
- `scope_type = category` → Zuordnung über `scope_key = export_pfad_de` (oder kanonischer Kategorie-Key, siehe 6.2)
- optional (später): `scope_type = global` → allgemeine FAQs, die gezielt eingeblendet werden dürfen (standardmäßig deaktiviert)

### 6.2 Kategorie-Key (verbindlich)
Für Kategorien ist `scope_key` der kanonische Kategoriepfad **relativ** zu `wissen/content/<lang>/`, ohne führenden Slash.
Beispiel:
- Kategorie-Content liegt unter `wissen/content/de/produkte/leisten/tuerbekleidungen/_index.md`
- Dann ist `scope_key = produkte/leisten/tuerbekleidungen`

### 6.3 Sprachmodell
`lang` ist `de` oder `en`.

### 6.4 Reihenfolge
`order` ist eine Ganzzahl (1..n). Generator sortiert nach `order` aufsteigend.

### 6.5 Aktiv/Deaktiv
`status` ist `active` oder `inactive`. Nur `active` wird gerendert.

### 6.6 Counts (MUSS)
- Produktseite: pro Sprache **5–8** FAQs (active)
- Kategorie-Seite: pro Sprache **8–12** FAQs (active)

### 6.7 Formatregeln
- Keine `/wissen/...` Links. Nur `/de/...` bzw. `/en/...`.
- Keine erfundenen technischen Werte.
- Fragen kurz und klar; Antworten sachlich, keine Preiszusagen.

### 6.8 Dedupe
Innerhalb einer Seite und Sprache:
- gleiche Frage (case-insensitive, whitespace-normalized) darf nicht doppelt vorkommen.

---

## 7) Canonical Fields & Header-Aliases (robust)

### 7.1 `SSOT.csv` Mindestfelder (canonical)
- `export_pfad_de`, `export_pfad_en`
- `product_id` (Alias: `produkt.id`, `produkt_id`, `id`)
- optional: `translationKey`
- `title_de`, `description_de`, `title_en`, `description_en`
- `body_de_*` / `body_en_*` (ohne FAQ)

### 7.2 `categories.csv` Mindestfelder
- `export_pfad_de`, `export_pfad_en`
- `title_de`, `description_de`, `title_en`, `description_en`
- optional: `weight`, `menu`, `parent`
- `body_de_*` / `body_en_*` (ohne FAQ)

### 7.3 `faq.csv` Mindestfelder (canonical)
- `faq_id` (eindeutig)
- `scope_type` (`product` | `category` | optional `global`)
- `scope_key` (siehe 6.1/6.2)
- `lang` (`de` | `en`)
- `question`
- `answer`
- `order` (int)
- `status` (`active` | `inactive`)

Optional:
- `tags` (kommagetrennt)
- `source` (intern, falls ihr Quellen referenzieren wollt)

---

## 8) Link-Policy (hart)
- Interne Links nur:
  - DE: `/de/...`
  - EN: `/en/...`
- Keine `(/wissen/...)`, keine absoluten `https://.../wissen/...` Links als interne Links.
- Verweise nur auf Ziele, die existieren (Export-Index oder Content-Tree).

---

## 9) Determinismus
- Sortierte Ausgabe (Verweise, FAQs, Bilder).
- Zeilenenden LF.
- Keine zufällige Reihenfolge.
- Keine zeitbasierte Änderung außer `lastmod` (und `version` falls vorhanden).
- `lastmod`-Format pro Datei beibehalten (Datum-only vs datetime).

---

## 10) Merge-/Release-Policy (SSOT-PRs)
Ein SSOT-PR ist mergebar nur wenn:
- Validator OK (inkl. FAQ counts)
- Build & Deploy OK
- Guards OK
- Keine Änderungen außerhalb:
  - `wissen/ssot/**`
  - und SSOT-owned `wissen/content/**` (scoped)

---

## 11) Nächster Implementierungsschritt (separat, aber zwingend)
Generatoren müssen:
1) Body-Felder aus `SSOT.csv`/`categories.csv` lesen,
2) FAQ aus `faq.csv` je Seite + Sprache sammeln,
3) deterministisch den Markdown-Body bauen,
4) strikt scoped schreiben (SSOT-owned only).
