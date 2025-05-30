import gspread
import logging
import streamlit as st
from google.oauth2.service_account import Credentials

log = logging.getLogger("prix_fixe_debug")

# Settings
SHEET_URL = "https://docs.google.com/spreadsheets/d/1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0/edit"
CACHE_SHEET_NAME = "Cache"
MAX_CACHE_ROWS = 500

# Auth
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)
client = gspread.authorize(credentials)
spreadsheet = client.open_by_url(SHEET_URL)

def get_cache_sheet():
    try:
        return spreadsheet.worksheet(CACHE_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=CACHE_SHEET_NAME, rows="1000", cols="2")

def get_cached_text(place_id: str) -> str | None:
    try:
        sheet = get_cache_sheet()
        records = sheet.get_all_records()
        for row in records:
            if row.get("place_id") == place_id:
                log.info(f"[SHEET HIT] {place_id}")
                return row.get("text")
    except Exception as e:
        log.warning(f"[SHEET FAIL] {place_id}: {e}")
    return None

def set_cached_text(place_id: str, text: str):
    try:
        sheet = get_cache_sheet()
        sheet.append_row([place_id, text])
        _prune_cache(sheet)
        log.info(f"[SHEET SET] {place_id}")
    except Exception as e:
        log.error(f"Sheet write error: {e}")

def _prune_cache(sheet):
    try:
        rows = sheet.get_all_values()
        if len(rows) > MAX_CACHE_ROWS:
            sheet.delete_rows(2, len(rows) - MAX_CACHE_ROWS + 2)
            log.info("Pruned Google Sheets cache.")
    except Exception as e:
        log.warning(f"Failed to prune cache: {e}")