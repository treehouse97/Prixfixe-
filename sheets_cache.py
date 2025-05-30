import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# === CONSTANTS ===
SHEET_ID = "1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0"

# === CLIENT SETUP ===
def get_gsheet_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    return gspread.authorize(creds)

# === DATA FETCH ===
def get_sheet_data():
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# === CACHE LOOKUP ===
def cache_lookup(place_id):
    try:
        df = get_sheet_data()
        result = df[df["place_id"] == place_id]
        if not result.empty:
            return result.iloc[0]["text"]
    except Exception as e:
        print(f"Cache lookup failed: {e}")
    return None

# === CACHE STORE ===
def cache_store(place_id, text):
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).sheet1
        data = sheet.get_all_values()

        for i, row in enumerate(data):
            if len(row) > 0 and row[0] == place_id:
                sheet.update_cell(i + 1, 2, text[:49999])  # Google Sheets max cell length
                return

        sheet.append_row([place_id, text[:49999]])
    except Exception as e:
        print(f"Cache store failed: {e}")