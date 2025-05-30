import gspread
import logging
from google.oauth2.service_account import Credentials
import streamlit as st

# ─────────────── Logger ───────────────
log = logging.getLogger("prix_fixe_debug")

# ─────────────── Google Sheets Config ───────────────
SHEET_URL = "https://docs.google.com/spreadsheets/d/1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0/edit"
CACHE_SHEET_NAME = "Cache"
MAX_CACHE_ENTRIES = 500

# ─────────────── Auth + Client Init ───────────────
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)
client = gspread.authorize(credentials)
spreadsheet = client.open_by_url(SHEET_URL)

# ─────────────── Cache Ops ───────────────
def get_cache_sheet():
    try:
        return spreadsheet.worksheet(CACHE_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=CACHE_SHEET_NAME, rows="1000", cols="2")

def get_cached_text(place_id: str) -> str | None:
    sheet = get_cache_sheet()
    try:
        records = sheet.get_all_records()
        for row in records:
            if row.get("place_id") == place_id:
                return row.get("text")
    except Exception as e:
        log.error(f"Cache read error: {e}")
    return None

def set_cached_text(place_id: str, text: str):
    sheet = get_cache_sheet()
    try:
        sheet.append_row([place_id, text])
        prune_cache(sheet)
        log.info(f"[CACHE SET] {place_id}")
    except Exception as e:
        log.error(f"Cache write error for {place_id}: {e}")

def prune_cache(sheet):
    try:
        rows = sheet.get_all_values()
        if len(rows) > MAX_CACHE_ENTRIES:
            sheet.delete_rows(2, len(rows) - MAX_CACHE_ENTRIES + 2)
            log.info(f"Pruned {len(rows) - MAX_CACHE_ENTRIES} rows from cache.")
    except Exception as e:
        log.error(f"Cache prune error: {e}")