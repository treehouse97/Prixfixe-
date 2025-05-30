import streamlit as st
from streamlit_lottie import st_lottie
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
import json
import requests
import time
import sqlite3
import logging

# Setup
st.set_page_config(page_title="The Fixe", layout="wide")
st.title("The Fixe")
st.caption("What’s the deal?")

# Logging
logging.basicConfig(level=logging.DEBUG, format="The Fixe DEBUG » %(message)s")

# Google Sheets config
SHEET_URL = "https://docs.google.com/spreadsheets/d/1SAMPLEKEY123456789/edit#gid=0"

# Load credentials from secrets
creds_dict = st.secrets["gcp_service_account"]
creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).sheet1

# Local cache (sqlite)
conn = sqlite3.connect("cache.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS cache (
        place_id TEXT PRIMARY KEY,
        text TEXT,
        label TEXT,
        snippet TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

def fetch_from_local_cache(place_id):
    cursor.execute("SELECT text, label, snippet FROM cache WHERE place_id=?", (place_id,))
    return cursor.fetchone()

def set_local_cache(place_id, text, label, snippet):
    cursor.execute("""
        INSERT OR REPLACE INTO cache (place_id, text, label, snippet)
        VALUES (?, ?, ?, ?)
    """, (place_id, text, label, snippet))
    conn.commit()

def fetch_from_sheet(place_id):
    try:
        all_ids = [row[0] for row in sheet.get_all_values()[1:]]
        return place_id in all_ids
    except Exception as e:
        logging.debug(f"[SHEET FAIL] {place_id}: {e}")
        return False

def set_sheet_cache(place_id, label, snippet):
    try:
        snippet_short = snippet[:200]
        sheet.append_row([place_id, label, snippet_short])
        logging.debug(f"[SHEET SET] {place_id}")
        time.sleep(1)  # Prevent rate limit breach
    except Exception as e:
        logging.debug(f"Sheet write error: {e}")

def load_lottie(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception:
        return None

# Demo text classifier
def classify_deal(text):
    text = text.lower()
    if "prix fixe" in text:
        return "prix fixe", "prix fixe"
    if "lunch special" in text:
        return "lunch", "lunch special"
    if "special" in text:
        return "special", "specials"
    return None, None

# Fake function to simulate crawling
def crawl_website(place_id):
    # Simulated site crawl
    return f"This is a fake crawl result for place {place_id} with lots of deals like lunch special and prix fixe."

# Search execution
def run_search(limit=10):
    # Simulated Places IDs
    place_ids = [f"ChIJ{str(i).zfill(3)}" for i in range(limit)]

    for place_id in place_ids:
        logging.debug(f"[CACHE MISS] {place_id}")

        local = fetch_from_local_cache(place_id)
        if local:
            logging.debug(f"[LOCAL HIT] {place_id}")
            continue

        if fetch_from_sheet(place_id):
            logging.debug(f"[SHEET HIT] {place_id}")
            continue

        text = crawl_website(place_id)
        label, snippet = classify_deal(text)
        if not label:
            logging.debug(f"{place_id} • skipped (no qualifying phrases found)")
            continue

        set_local_cache(place_id, text, label, snippet)
        set_sheet_cache(place_id, label, snippet)
        logging.debug(f"{place_id} • triggered by “{snippet}” → {label}")

# UI
if st.button("Search"):
    run_search()