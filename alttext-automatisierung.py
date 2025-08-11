import os, io, re, json, base64, time
from typing import List, Dict, Tuple
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from googleapiclient.errors import HttpError

# === Konfiguration via ENV ===
OPENAI_API_KEY   = os.getenv("8398e2703b3b33e8411223fd7151a90ce98eaa80", "").strip()
DRIVE_FOLDER_ID  = os.getenv("1x2GgjjCsiIxJtzynJyCIg6mYY914OHQa?dmr", "").strip()
SPREADSHEET_ID   = os.getenv("17PINnHHTErdkmb0H4j9lyXyMt_O4D9jgsGLG1qusULI", "").strip()
SHEET_TAB_NAME   = os.getenv("vertaefelungen", "").strip() or None  # None = 1. Blatt
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "alttext-automatisierung-8398e2703b3b.json")

# Spalten-Header im Sheet (GENAU so benannt)
COL_BILDER_LISTE = "bilder_liste"
COL_ALT_DE       = "bilder_alt_de"
COL_ALT_EN       = "bilder_alt_en"
# Optional: Kontextfelder (falls vorhanden, verbessern die Alttexte)
COL_TITEL_DE     = "titel_de"
COL_TITLE_EN     = "title_en"
COL_KATEGORIE_DE = "kategorie_de"
COL_CATEGORY_EN  = "category_en"
COL_MATERIAL     = "material"
COL_FARBE        = "farbe"
COL_COLOR        = "color"
COL_SKU          = "sku"

# === Google Auth (Drive + Sheets) ===
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]
creds = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
drive = build("drive", "v3", credentials=creds)
sheets = build("sheets", "v4", credentials=creds)

# === OpenAI (Vision) – Responses API mit Bild-Bytes (Base64) ===
# Tipp: Bytes senden, damit Bilder NICHT öffentlich geteilt werden müssen.
import openai
openai.api_key = OPENAI_API_KEY

# Caching (spart Tokens/Kosten bei wiederholtem Lauf)
CACHE_PATH = ".alt_cache.json"
try:
    ALT_CACHE = json.loads(open(CACHE_PATH, "r", encoding="utf-8").read())
except Exception:
    ALT_CACHE = {}

def save_cache():
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(ALT_CACHE, f, ensure_ascii=False, indent=2)

# ---------- Hilfsfunktionen ----------
def list_drive_images(folder_id: str) -> Dict[str, Dict]:
    """Liest alle Bilder im Ordner. Rückgabe: name_lower -> {id, name, mimeType}"""
    files = {}
    page_token = None
    while True:
        res = drive.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false",
            fields="nextPageToken, files(id,name,mimeType)",
            pageToken=page_token
        ).execute()
        for f in res.get("files", []):
            files[f["name"].lower()] = f
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return files

def download_file_bytes(file_id: str) -> Tuple[bytes, str]:
    """Lädt Datei-Bytes aus Drive und gibt (bytes, mimeType) zurück."""
    meta = drive.files().get(fileId=file_id, fields="mimeType").execute()
    request = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return buf.getvalue(), meta["mimeType"]

def parse_list(cell: str) -> List[str]:
    if not cell:
        return []
    return [x.strip() for x in str(cell).split(",") if x.strip()]

def join_list(values: List[str]) -> str:
    return ", ".join(v.strip() for v in values if str(v).strip())

def normalize_ext(filename: str) -> str:
    # Du arbeitest mit .png: ersetze .jpg/.jpeg → .png für Matching
    return re.sub(r"\.jpe?g$", ".png", filename.strip(), flags=re.IGNORECASE)

def build_context(row_map: Dict[str, int], header: List[str], row: List[str]) -> Dict[str, str]:
    def get(col):
        if col in row_map:
            v = row[row_map[col]]
            return "" if v is None else str(v).strip()
        return ""
    return {
        "titel_de": get(COL_TITEL_DE),
        "title_en": get(COL_TITLE_EN),
        "kategorie_de": get(COL_KATEGORIE_DE),
        "category_en": get(COL_CATEGORY_EN),
        "material": get(COL_MATERIAL),
        "farbe": get(COL_FARBE),
        "color": get(COL_COLOR),
        "sku": get(COL_SKU),
    }

def vision_alttexts(image_bytes: bytes, mime_type: str, ctx: Dict[str, str]) -> Tuple[str, str]:
    """Erzeugt (alt_de, alt_en) via Vision. Cached nach Hash der Bytes."""
    import hashlib
    h = hashlib.sha256(image_bytes).hexdigest()
    if h in ALT_CACHE:
        return ALT_CACHE[h]["de"], ALT_CACHE[h]["en"]

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64}"

    # Prompt knapp & deterministisch halten
    system = (
        "You generate concise, accessible image alt texts in German and English for product catalogs. "
        "Return ONLY two lines: 'DE: ...' and 'EN: ...'. 90–120 characters each. "
        "No file names, no quotes, no marketing fluff."
    )

    # Kontext hilft Qualität
    de_hint = f"{ctx.get('titel_de','')}, {ctx.get('kategorie_de','')}, {ctx.get('material','')}, Farbton {ctx.get('farbe','')}, SKU {ctx.get('sku','')}".strip(", ").replace(" ,", ",")
    en_hint = f"{ctx.get('title_en','')}, {ctx.get('category_en','')}, {ctx.get('material','')}, color {ctx.get('color','')}, SKU {ctx.get('sku','')}".strip(", ").replace(" ,", ",")

    user_text = (
        "Bildbeschreibung für Leinöl-Farbe. "
        f"Kontext (DE): {de_hint or '—'} | Context (EN): {en_hint or '—'}.\n"
        "Formatiere nur:\nDE: <deutscher Alttext>\nEN: <english alt text>"
    )

    # Responses API (oder chat.completions – je nach Account). Hier: Chat Completions kompatibel.
    completion = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":[
                {"type":"text","text": user_text},
                {"type":"image_url","image_url":{"url": data_url}}
            ]}
        ],
        temperature=0.2,
    )
    txt = completion.choices[0].message["content"].strip()
    de = en = ""
    mde = re.search(r"DE:\s*(.+)", txt)
    men = re.search(r"EN:\s*(.+)", txt)
    if mde: de = mde.group(1).strip()
    if men: en = men.group(1).strip()
    if not de: de = txt
    if not en: en = txt

    ALT_CACHE[h] = {"de": de, "en": en}
    save_cache()
    return de, en

def read_sheet():
    # ganze Tabelle holen
    meta = sheets.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    if SHEET_TAB_NAME:
        sheet_title = SHEET_TAB_NAME
    else:
        sheet_title = meta["sheets"][0]["properties"]["title"]
    res = sheets.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"{sheet_title}!A:ZZ"
    ).execute()
    values = res.get("values", [])
    if not values or len(values) < 2:
        raise RuntimeError("Sheet hat keine Datenzeilen.")
    header = [h.strip() for h in values[0]]
    # Map Header → Index
    idx = {h: i for i, h in enumerate(header)}
    rows = values[1:]
    return sheet_title, header, idx, rows

def write_sheet(sheet_title: str, header: List[str], row_idx_map: Dict[str,int], rows_out: Dict[int, Tuple[str,str]]):
    # Wir schreiben nur die Alt-Spalten zurück (bulk update)
    if COL_ALT_DE not in row_idx_map or COL_ALT_EN not in row_idx_map:
        raise RuntimeError(f"Sheet braucht Spalten {COL_ALT_DE} und {COL_ALT_EN}.")
    col_de = row_idx_map[COL_ALT_DE] + 1
    col_en = row_idx_map[COL_ALT_EN] + 1

    updates_de = []
    updates_en = []
    row_indices = sorted(rows_out.keys())
    for r in row_indices:
        de_val, en_val = rows_out[r]
        updates_de.append([de_val])
        updates_en.append([en_val])

    # Zielbereiche (1‑basiert, plus Headerzeile)
    start_row = min(row_indices) + 2
    end_row   = max(row_indices) + 2
    rng_de = f"{sheet_title}!{col_to_letter(col_de)}{start_row}:{col_to_letter(col_de)}{end_row}"
    rng_en = f"{sheet_title}!{col_to_letter(col_en)}{start_row}:{col_to_letter(col_en)}{end_row}"

    body = {"valueInputOption": "RAW", "data": [
        {"range": rng_de, "values": updates_de},
        {"range": rng_en, "values": updates_en},
    ]}
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body=body
    ).execute()

def col_to_letter(col: int) -> str:
    s = ""
    while col:
        col, rem = divmod(col-1, 26)
        s = chr(65+rem) + s
    return s

# ---------- Hauptlogik ----------
def main():
    if not OPENAI_API_KEY or not DRIVE_FOLDER_ID or not SPREADSHEET_ID:
        raise SystemExit("Bitte OPENAI_API_KEY, DRIVE_FOLDER_ID und SPREADSHEET_ID als Umgebungsvariablen setzen.")

    # 1) Drive-Index (name_lower -> file)
    drive_index = list_drive_images(DRIVE_FOLDER_ID)

    # 2) Sheet lesen
    sheet_title, header, hmap, rows = read_sheet()
    if COL_BILDER_LISTE not in hmap:
        raise RuntimeError(f"Spalte {COL_BILDER_LISTE} fehlt im Sheet.")

    out_updates: Dict[int, Tuple[str,str]] = {}  # row_idx -> (alt_de_csv, alt_en_csv)

    for i, row in enumerate(rows):
        bilder_cell = row[hmap[COL_BILDER_LISTE]] if hmap[COL_BILDER_LISTE] < len(row) else ""
        files_in_row = [normalize_ext(x) for x in parse_list(bilder_cell)]
        if not files_in_row:
            continue

        ctx = build_context(hmap, header, row)
        alt_de_list, alt_en_list = [], []

        for name in files_in_row:
            # exakte Suche (case-insensitive)
            f = drive_index.get(name.lower())
            if not f:
                # versuche tolerant: nur basename matchen
                base = os.path.basename(name).lower()
                f = drive_index.get(base) or next((v for k,v in drive_index.items() if os.path.basename(k)==base), None)
            if not f:
                # kein Treffer → neutraler Fallback
                alt_de_list.append("Produktabbildung – Leinölfarbe, Detail/Ansicht")
                alt_en_list.append("Product image – linseed oil paint, detail/view")
                continue

            # Bytes holen → Vision
            try:
                data, mime = download_file_bytes(f["id"])
            except HttpError:
                alt_de_list.append("Produktabbildung – Leinölfarbe, Detail/Ansicht")
                alt_en_list.append("Product image – linseed oil paint, detail/view")
                continue

            de, en = vision_alttexts(data, mime, ctx)
            alt_de_list.append(de)
            alt_en_list.append(en)
            time.sleep(0.2)  # sanft drosseln

        out_updates[i] = (join_list(alt_de_list), join_list(alt_en_list))

    # 3) zurück ins Sheet schreiben
    if out_updates:
        write_sheet(sheet_title, header, hmap, out_updates)
        print(f"✅ {len(out_updates)} Zeilen aktualisiert.")
    else:
        print("Nichts zu aktualisieren.")

if __name__ == "__main__":
    main()
