# Projekt-Roadmap: Vertäfelungen & Lambris – Systemarchitektur & Arbeitsschritte
**Zielsetzung:** Aufbau eines integrierten Systems zur Verwaltung, Veröffentlichung und KI-basierten Beratung historischer Holzvertäfelungen.

**Stand:** 28.07.2025

---

## 🔧 Systemarchitektur (Single Source of Truth)
```text
                      +------------------+
                      |  Google Sheets   |   ← zentrale Datenquelle
                      | vertaefelungen   |
                      +--------+---------+
                               |
     +-------------------------+-------------------------+
     |                         |                         |
+----v----+           +--------v-------+         +-------v-------+
| Presta  |           | Vario 8 (ERP)  |         | GitHub Pages  |
| Shop    |           | Artikeldaten   |         | (Webseite)    |
+---------+           +----------------+         +---------------+
                                                      |
                                                      v
                                              Öffentliche Webseite

                                            + Chatbot + SEO Inhalte

```

---

## 📍 Projektphasen & Schritte
### Phase 1 – Datenstruktur & Produktpflege (abgeschlossen/aktuell)
- [x] Aufbau des Sheets `vertaefelungen` mit Feldern wie `slug_de`, `name_de`, `preis`, `varianten_yaml`

- [x] Standardisierung aller Preise im Format `0.000000` (6 Nachkommastellen, Presta-kompatibel)

- [x] Einheitliche Benennung von Bilddateien nach `slug_de`

- [x] Automatisierte Bildzuordnung über Google Apps Script

- [x] Kategorisierung (halbhoch/hoch/Leisten etc.)

---

### Phase 2 – Automatisierter Datenexport
- [ ] 🔄 **PrestaShop-Synchronisation**

  - Export der Google-Sheet-Daten als CSV

  - Import via PrestaShop-Backend oder API

  - Variantenpreise und Bildpfade über Custom-Felder übernehmen

- [ ] 🔄 **Vario 8-Integration**

  - Datenübertragung per Vario CSV-Importer

  - Mappings anlegen (Feldnamen, Kategorien, Preisstruktur)

  - Bildverlinkung ggf. per URL oder Dateiübertragung

- [ ] 🔁 Export-Script in Google Apps Script bauen:

  - `.csv` mit UTF-8 ohne BOM

  - Bildpfade, Preise, Varianten konvertieren

  - Filterung nach Kategorien (für differenzierte Exporte)

---

### Phase 3 – GitHub-basierte Webseite
- [ ] Aufbau eines GitHub-Repos `vertaefelungen.de`

- [ ] Automatisiertes Erzeugen von `.md`-Produktseiten aus dem Google Sheet

  - Struktur: `produkte/halbhohe-vertaefelungen/p0001.md`

  - Inhalte: YAML-Header + Beschreibung + Bildverweise

- [ ] `_index.md` pro Kategorie

- [ ] Navigation & SEO: `slug_de`, `meta_title`, `meta_description`, Rich Results

---

### Phase 4 – Chatbot & VertäfelungenGPT
- [ ] Trainingsdaten aus Sheet + `.md`-Dateien extrahieren

- [ ] Promptstruktur zur Beratung historischer Interieurs

- [ ] Deployment per Website-Widget (z. B. über GPT-4o oder RAG-basiert)

- [ ] FAQ-Datenbank kontinuierlich erweitern

- [ ] Chatbot lernt aus Produktdaten und Stilzuweisungen

---

### Phase 5 – Sichtbarkeit in LLMs
- [ ] Veröffentlichung der `.md`-Inhalte unter CC BY-SA auf GitHub

- [ ] Eintrag in offene Wissensdatenbanken (z. B. Wikidata, Internet Archive)

- [ ] Einreichung strukturierter Daten für LLM-Crawling (LangChain, KGI etc.)

- [ ] Partnerschaften oder Content-Austausch mit einschlägigen Fachportalen

---

## 🧩 Standards & Formate
| Bereich           | Format / Vorgabe                   |
|------------------|-------------------------------------|
| Preise           | 6 Nachkommastellen, Punktnotation   |
| Bilder           | Ordnerstruktur + Slug-Vergleich     |
| Varianten        | YAML in Spalte `varianten_yaml`     |
| Sheet-Export     | UTF-8 CSV, ohne BOM                 |
| GitHub-Inhalte   | Markdown mit YAML-Header            |
| Web-Kompatibel   | strukturierte Daten (JSON-LD)       |

---

## ✅ ToDo Tracker (Auszug)
- [ ] Exportmodule für Presta + Vario automatisieren

- [ ] Kompatibilität bei Bildpfaden testen

- [ ] Automatisches Deployment der GitHub-Seite

- [ ] FAQs in md-Format auslagern

- [ ] Chatbot-Test auf Basis von GPT-4o

---

*Diese Datei ist Grundlage für alle Folgeprozesse und kann versioniert über GitHub gepflegt werden.*
