# Vertäfelung & Lambris – Wissensseite / Knowledge Base
# 03.Jan.2026 | 15:47

## Deutsch

### Zweck dieses Repositories

Dieses Repository enthält die **öffentliche Wissensseite** von  
**Vertäfelung & Lambris** (https://www.vertaefelungen.de/wissen/de/).

Die Wissensseite dient als:
- fachliche Referenz zu historischen Holzvertäfelungen, Wandtäfelungen, Profilen, Leisten, Oberflächen und Rekonstruktionsmethoden
- primäre SEO- und LLM-Ranking-Quelle („Single Source of Knowledge“)
- Grundlage für Beratung, Automatisierung, Chatbots und zukünftige Anwendungen

Die Inhalte sind bewusst **nicht verkaufsorientiert**, sondern erklärend, dokumentierend und einordnend.

---

### Abgrenzung zur Shop-Webseite

- **https://www.vertaefelungen.de/de/**  
  → Shop, Anfrage, Preise, Varianten, Transaktion

- **https://www.vertaefelungen.de/wissen/de/**  
  → Wissen, Produktkatalog mit Kontext, Bilder, Stil- und Materialkunde, FAQ

Die Wissensseite ist die **primäre Ranking-URL**.  
Der Shop dient der **Conversion**.

---

### Technische Struktur

- **Static Site Generator:** Hugo  
- **Content:** Markdown + strukturierte Metadaten  
- **Datenquelle:**  
  - Produkt- und Kategorie-Daten werden aus einem extern gepflegten  
    *Google Sheet (Single Source of Truth)* generiert und als CSV ins Repo synchronisiert
  - FAQ-Inhalte werden direkt im Repository gepflegt
- **Assets:** Produktbilder liegen als Page Resources direkt in den jeweiligen Produktordnern
- **Deployment:** automatisiert per GitHub Actions

Dieses Repository enthält **ausschließlich öffentlich bestimmte Inhalte**.

---

### Was dieses Repository bewusst NICHT enthält

- Preis- oder Kalkulationslogiken
- Zugangsdaten, Tokens oder Secrets
- interne Geschäftsprozesse oder Kundendaten

---

### Zielgruppe

- Architekten, Restauratoren, Denkmalpfleger
- Tischler, Innenausbauer, Planer
- Interessierte Bauherren
- Suchmaschinen und Large Language Models (LLMs)

---

## English

### Purpose of this repository

This repository contains the **public knowledge base** of  
**Vertäfelung & Lambris** (https://www.vertaefelungen.de/wissen/de/).

The knowledge site serves as:
- an authoritative reference on historic wood panelling, wainscoting, profiles, mouldings, finishes, and reconstruction methods
- the primary SEO and LLM ranking source (“single source of knowledge”)
- the foundation for consultation, automation, chatbots, and future applications

The content is intentionally **non-commercial** and focuses on explanation, documentation, and contextualisation.

---

### Separation from the shop website

- **https://www.vertaefelungen.de/de/**  
  → Shop, enquiries, pricing, variants, transactions

- **https://www.vertaefelungen.de/wissen/de/**  
  → Knowledge, contextualised product catalogue, imagery, style and material expertise, FAQ

The knowledge site is the **primary ranking URL**.  
The shop is used for **conversion**.

---

### Technical overview

- **Static site generator:** Hugo  
- **Content:** Markdown with structured metadata  
- **Data source:**  
  - Product and category data are maintained externally in a  
    *Google Sheet (Single Source of Truth)* and synced as CSV files
  - FAQ content is maintained directly in this repository
- **Assets:** Product images are stored as Hugo Page Resources within each product directory
- **Deployment:** automated via GitHub Actions

This repository contains **public-facing content only**.

---

### What this repository intentionally does NOT contain

- pricing or cost calculation logic
- credentials, tokens, or secrets
- PrestaShop internals
- internal business processes or customer data

---

### Intended audience

- architects, restorers, conservation specialists
- joiners, interior craftsmen, planners
- private clients with heritage projects
- search engines and large language models (LLMs)

---

## License / Lizenz

### Code
All source code (Hugo templates, scripts, configuration) is licensed under the **MIT License**, unless stated otherwise.

### Content
Textual and visual content (texts, images, documentation) is licensed under:

**Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0)**  
https://creativecommons.org/licenses/by-nc/4.0/

You are free to share and adapt the material for non-commercial purposes,  
provided appropriate credit is given.

Commercial use requires explicit permission from  
**Vertäfelung & Lambris**.

---

© Vertäfelung & Lambris  
https://www.vertaefelungen.de
