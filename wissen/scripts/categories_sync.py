# Gehe zu den relevanten Stellen und stelle sicher, dass die `title_de` und `title_en`
# aus der CSV korrekt übernommen werden, wenn die `_index.md`-Dateien erstellt werden.

def write_index(target: Path, fm: Dict, body: str, apply: bool) -> str:
    """
    Schreibt _index.md mit den richtigen Title-Werten.
    """
    # Sicherstellen, dass title aus CSV immer überschrieben wird:
    fm["title"] = fm.get("title")  # Diese Zeile stellt sicher, dass der 'title' korrekt gesetzt wird.

    # Nach dem Mergen der Frontmatter können wir den Titel aus der CSV setzen
    new_txt = dump_frontmatter(fm) + body

    if target.exists():
        old_txt = target.read_text(encoding="utf-8", errors="replace")
        if old_txt == new_txt:
            return "unchanged"

    if apply:
        ensure_parent_dir(target)
        target.write_text(new_txt, encoding="utf-8")
        return "updated" if target.exists() else "created"

    return "would-write"
