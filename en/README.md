# Knowledge Base – English

This is the English section of the structured knowledge base for **Vertäfelungen & Lambris**.  
It contains all publicly accessible content and internal process documentation related to historical wood paneling, product variations, production techniques, and installation workflows.

The folder structure is designed to be:

- product-oriented (by category),
- process-oriented (by workflow),
- language-separated (de/en),
- machine-readable (Markdown, JSON, CSV)

---

## 🔹 Directory Overview

### 📁 `general-information/`  
General content for clients and project partners – such as customer FAQs, glossary, and historical background on wood paneling.  
**Examples:**
- `FAQ-Customer.md` – Answers to common client questions  
- `History-of-Wood-Paneling.md` – Background & origins  
- `Glossary.csv` – Technical terminology

---

### 📁 `internal-processes/`  
**Not public** – contains internal documentation on the complete project workflow: planning, visualization, production, and installation.  
Useful for staff training and GPT-based internal advisors.  
**Examples:**
- `Quotation.md` – Project quotation and pricing logic  
- `Production.md` – Production workflow  
- `Installation.md` – On-site installation  
- `Visualization.md` – 3D modeling and design approval

---

### 📁 `public/`  
All publicly available information for clients, architects, restorers, and third-party systems.

#### Subfolders:

- 📁 `products/`  
  Contains all product categories:  
  - `dado-panel/` (half-height paneling)  
  - `high-wainscoting/`  
  - `accessories/` (e.g., rosettes, oils, moldings)  

  Each folder includes `.md` files per product and matching `.png` visuals.  
  **Support files:**  
  - `README.md` – Overview of each category  
  - `productcatalog.json` – Structured product data (for API use)

- 📄 `materials.md` (optional): wood types, oils, surfaces  
- 📄 `historical-inspirations.md` (optional): historical sources and style references  
- 📁 `reference-projects/` (planned): detailed case studies

---

## 🔹 Maintenance Notes

- All `.md` files are written in kebab-case (lowercase with `-` separators).
- Image files are stored in the same folder as their product file.
- Structured data is stored as `.csv` or `.json` for easy automation and integration.
- The German counterpart is available under `/de/`.

---

## 🧩 Purpose of This Knowledge Base

This repository serves as the foundation for:

- AI-powered customer support (e.g., via CustomGPT)
- Internal training and process documentation
- Consistent and transparent product communication
- Automated publishing and data export (e.g., GitHub Pages, APIs)

---

> For the German version, please refer to [`../de/`](../de/)
