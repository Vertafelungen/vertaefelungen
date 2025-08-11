import os
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import openai
from PIL import Image
import requests

# ==== KONFIGURATION ====
CREDENTIALS_FILE = "credentials.json"  # Pfad zur Service-Account-JSON
DRIVE_FOLDER_ID = "DEINE_DRIVE_ORDNER_ID"
SPREADSHEET_ID = "DEINE_SPREADSHEET_ID"
BILDER_SPALTE = "bilder_liste"   # Name der Spalte im Sheet
ALTTEXT_DE_SPALTE = "alttext_de" # Zielspalte für DE
ALTTEXT_EN_SPALTE = "alttext_en" # Zielspalte für EN
OPENAI_API_KEY = "DEIN_OPENAI_KEY"

# ==== AUTH ====
creds = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=["https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets"]
)

drive_service = build('drive', 'v3', credentials=creds)
sheets_service = build('sheets', 'v4', credentials=creds)
openai.api_key = OPENAI_API_KEY

# ==== SCHRITT 1: Bilder aus Drive holen ====
def get_images_from_folder(folder_id):
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'image/'",
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get('files', [])

# ==== SCHRITT 2: Bildbeschreibung mit GPT ====
def generate_alttexts(image_url):
    prompt = f"Beschreibe dieses Produktbild in einem prägnanten Alttext auf Deutsch und Englisch. Kein Dateiname, nur Inhalt. Bild: {image_url}"
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    text = resp.choices[0].message.content.strip()
    # Erwartet Format: "DE: ..., EN: ..."
    if "EN:" in text:
        de_text = text.split("EN:")[0].replace("DE:", "").strip()
        en_text = text.split("EN:")[1].strip()
        return de_text, en_text
    return text, text

# ==== SCHRITT 3: Alttexte ins Sheet schreiben ====
def update_sheet_alttexts(data):
    # Annahme: data ist Liste mit [bildname, alt_de, alt_en]
    values = []
    for row in data:
        values.append(row[1:])  # nur Alttexte
    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ALTTEXT_DE_SPALTE}:{ALTTEXT_EN_SPALTE}",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

# ==== AUSFÜHRUNG ====
if __name__ == "__main__":
    bilder = get_images_from_folder(DRIVE_FOLDER_ID)
    results = []
    for b in bilder:
        # Direktlink erstellen
        url = f"https://drive.google.com/uc?export=view&id={b['id']}"
        alt_de, alt_en = generate_alttexts(url)
        results.append([b['name'], alt_de, alt_en])
        print(f"{b['name']} → DE: {alt_de} | EN: {alt_en}")

    update_sheet_alttexts(results)
    print("✅ Alttexte ins Sheet geschrieben.")
