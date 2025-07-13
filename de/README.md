# Wissensdatenbank (Deutsch)

Dies ist der deutschsprachige Bereich der strukturierten Wissensdatenbank von **Vertäfelungen & Lambris**.  
Er enthält alle öffentlich kommunizierten Inhalte sowie internes Fach- und Prozesswissen rund um historische Holzvertäfelungen, Produktvarianten, Herstellung und Montage.

Die Gliederung folgt einem praxisnahen Aufbau nach Zielgruppen und Verwendungszweck.

---

## 🔹 Verzeichnisse

### 📁 `allgemeine-informationen/`  
Allgemein zugängliche Informationen zur Unternehmensphilosophie, Begriffsdefinitionen, häufigen Kundenfragen und geschichtlichem Hintergrund.  
**Beispiele:**
- `faq-Kunden.md` – Kundenorientierte FAQ
- `geschichte-der-holzvertaefelung.md` – Hintergrund zur Entstehung und Entwicklung
- `glossar.csv` – Fachbegriffe & Definitionen

---

### 📁 `interne-prozesse/`  
Nicht öffentlich. Enthält Dokumentationen zu internen Abläufen von der Planung bis zur Montage.  
Diese Inhalte dienen der Einarbeitung, Qualitätssicherung und für KI-gestützte interne Beratungssysteme.  
**Beispiele:**
- `Angebotserstellung.md` – Angebotslogik inkl. Planungsphase
- `Fertigung.md` – Produktionsabläufe
- `Montage.md` – Montageprozess beim Kunden
- `Visualisierung.md` – Erstellung und Freigabe von 3D-Modellen

---

### 📁 `oeffentlich/`  
Alle für Kunden, Architekten und Restauratoren öffentlich sichtbaren Inhalte: Produktdaten, Varianten, Materialien, Projekte.

#### Unterverzeichnisse:

- 📁 `produkte/`  
  Enthält alle Produktkategorien, z. B.:  
  - `halbhohe-vertaefelungen/`  
  - `hohe-vertaefelungen/`  
  - `leisten/`  
  - `zubehoer/`  

  Jede Kategorie enthält `.md`-Dateien zu konkreten Modellen sowie passende `.png`-Bilder.  
  **Begleitdateien:**  
  - `README.md` – Beschreibung der Produktstruktur  
  - `produktkatalog.json` – strukturierter Überblick für KI- und Webanwendungen

- 📄 `materialien.md` (optional): Holzarten, Oberflächen, Öle  
- 📄 `historische-vorbilder.md` (optional): Gestaltungsgrundlagen aus verschiedenen Epochen  
- 📁 `referenzprojekte/` (zukünftig): Fallstudien und Kundenprojekte

---

## 🔹 Hinweise zur Pflege

- Alle Dateien im Markdown-Format (`.md`) sind in `kebap-case` benannt (klein, mit Bindestrichen).
- Bilder befinden sich im selben Ordner wie die zugehörige `.md`-Datei.
- CSV/JSON-Dateien werden für strukturierte Daten verwendet (z. B. Produktvarianten, Katalogexporte).
- Die englische Spiegelung erfolgt unter `/en/`.

---

## 🧩 Zielsetzung

Diese Wissensdatenbank dient als Basis für:

- KI-gestützte Kundenberatung (CustomGPT)
- Schulung und internes Onboarding
- transparente Produktkommunikation
- automatisierbare Dokumentation (z. B. GitHub Pages, API-Ausgabe)

---

> Für die englischsprachige Version siehe [`../en/`](../en/)
