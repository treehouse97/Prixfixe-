import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

def get_worksheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope,
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key("your_sheet_id_here")  # Replace with actual ID
    return sheet.sheet1