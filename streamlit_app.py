import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Set Streamlit page config early
st.set_page_config(page_title="Google Sheets Write Test", layout="centered")

# Connect to Google Sheets via service account
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)
client = gspread.authorize(credentials)

# Sheet URL from your message
SHEET_URL = "https://docs.google.com/spreadsheets/d/1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0/edit"

# Try write operation
try:
    spreadsheet = client.open_by_url(SHEET_URL)
    sheet = spreadsheet.sheet1  # Use first sheet
    sheet.update("A1", "Test successful")
    st.success("✅ Successfully wrote to the spreadsheet (A1 = 'Test successful')")
except Exception as e:
    st.error("❌ Failed to write to the spreadsheet.")
    st.exception(e)