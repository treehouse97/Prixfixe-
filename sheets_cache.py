import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

def get_worksheet():
    # Define the scope
    scope = ["https://www.googleapis.com/auth/spreadsheets"]

    # Load credentials from Streamlit secrets
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )

    # Authorize the client
    client = gspread.authorize(credentials)

    # Open the Google Sheet by its key
    spreadsheet = client.open_by_key("10j8gkxcrBc8vCi3nWkLPnx9Bab4mhj-Gu91Pss3QLoQ")

    # Return the first worksheet
    return spreadsheet.sheet1