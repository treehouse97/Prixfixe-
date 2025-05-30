import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# === CONSTANTS ===
SHEET_ID = "1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0"

# === AUTH ===
def get_gsheet_client():
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"])
    return gspread.authorize(credentials)

# === FETCH ALL DATA FROM SHEET ===
def get_sheet_data():
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# === LOOKUP PLACE_ID IN SHEET CACHE ===
def cache_lookup(place_id):
    try:
        df = get_sheet_data()
        result = df[df["place_id"] == place_id]
        if not result.empty:
            return result.iloc[0]["text"]
    except Exception as e:
        st.warning(f"Cache lookup failed: {e}")
    return None

# === STORE NEW RESULT INTO SHEET CACHE ===
def cache_store(place_id, text):
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).sheet1
        all_rows = sheet.get_all_values()

        for i, row in enumerate(all_rows):
            if len(row) > 0 and row[0] == place_id:
                sheet.update_cell(i + 1, 2, text[:49999])  # Cell limit safeguard
                return

        sheet.append_row([place_id, text[:49999]])
    except Exception as e:
        st.warning(f"Cache store failed: {e}")