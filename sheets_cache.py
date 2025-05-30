import logging
import gspread
from google.oauth2.service_account import Credentials

# Logging setup
log = logging.getLogger("prix_fixe_debug")

# Google Sheets config
SHEET_ID = "1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0"
SHEET_NAME = "Sheet1"  # change if using a different sheet

def _get_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    return gspread.authorize(credentials)

def get_cached_text(place_id: str) -> str | None:
    try:
        sheet = _get_client().open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        records = sheet.get_all_records()
        for row in records:
            if row["place_id"] == place_id:
                log.info(f"[CACHE HIT] {place_id}")
                return row["text"]
        log.info(f"[CACHE MISS] {place_id}")
    except Exception as e:
        log.error(f"[CACHE FAIL] {place_id}: {e}")
    return None

def set_cached_text(place_id: str, text: str):
    try:
        sheet = _get_client().open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        sheet.append_row([place_id, text], value_input_option="USER_ENTERED")
        log.info(f"[SHEET SET] {place_id}")
        _prune_sheet(sheet)
    except Exception as e:
        log.error(f"[SHEET FAIL] {place_id}: {e}")

def _prune_sheet(sheet):
    try:
        records = sheet.get_all_values()
        header, rows = records[0], records[1:]
        if len(rows) > 500:
            excess = len(rows) - 500
            sheet.delete_rows(2, 2 + excess - 1)
            log.info(f"Pruned {excess} rows from cache")
    except Exception as e:
        log.error(f"Failed to prune cache: {e}")