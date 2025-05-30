import time
import logging
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.DEBUG, format="The Fixe DEBUG » %(message)s")
log = logging.getLogger("TheFixe")

# Constants
SHEET_URL = "https://docs.google.com/spreadsheets/d/1SAMPLEKEY123456789/edit"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_SNIPPET_LENGTH = 200

# Initialize client once
def get_sheet():
    creds_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL).sheet1
    return sheet

# Write minimal metadata to avoid cell limits
def write_to_sheet(place_id: str, label: str, snippet: str):
    try:
        sheet = get_sheet()
        trimmed_snippet = snippet[:MAX_SNIPPET_LENGTH] if snippet else ""
        sheet.append_row([place_id, label, trimmed_snippet])
        log.debug(f"[SHEET SET] {place_id}")
        time.sleep(1)  # prevent quota flooding
    except Exception as e:
        log.debug(f"[SHEET FAIL] {place_id}: {e}")

# Optional: for cache checking (use sparingly)
def is_cached_in_sheet(place_id: str) -> bool:
    try:
        sheet = get_sheet()
        rows = sheet.get_all_values()[1:]  # skip header
        return any(row[0] == place_id for row in rows if row)
    except Exception as e:
        log.debug(f"[SHEET FAIL] {place_id}: {e}")
        return False