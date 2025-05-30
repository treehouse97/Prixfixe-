import os
import re
import json
import time
import uuid
import sqlite3
import tempfile
import logging
import requests
import streamlit as st
from typing import List
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from PyPDF2 import PdfReader
from playwright.sync_api import sync_playwright

# Constants
DATA_DIR = Path(".data")
DB_FILE = DATA_DIR / "places.db"
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

# Debug mode toggle
DEBUG_MODE = st.checkbox("Enable Debug Logging")

def log(message: str):
    if DEBUG_MODE:
        st.write("The Fixe DEBUG » ", message)
    def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    with get_db_connection() as conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS restaurants (
    place_id TEXT PRIMARY KEY,
    name TEXT,
    address TEXT,
    website TEXT,
    summary TEXT,
    data JSON
);
""")
        conn.commit()

def ensure_schema():
    if not os.path.exists(DB_FILE):
        init_db()
        return
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1 FROM restaurants LIMIT 1")
    except sqlite3.DatabaseError:
        init_db()
def cache_place(place_id: str, data: dict):
    with get_db_connection() as conn:
        conn.execute(
            "REPLACE INTO restaurants (place_id, name, address, website, summary, data) VALUES (?, ?, ?, ?, ?, ?)",
            (
                place_id,
                data.get("name"),
                data.get("formatted_address"),
                data.get("website"),
                data.get("summary"),
                json.dumps(data),
            ),
        )
        conn.commit()

def lookup_cached_place(place_id: str):
    with get_db_connection() as conn:
        cur = conn.execute("SELECT data FROM restaurants WHERE place_id = ?", (place_id,))
        row = cur.fetchone()
        return json.loads(row["data"]) if row else None
def extract_text_from_url(url: str) -> str:
    domain = urlparse(url).netloc
    if url.lower().endswith(".pdf"):
        response = requests.get(url)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(response.content)
            reader = PdfReader(tmp_pdf.name)
            return "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=15000)
            content = page.content()
            browser.close()
            soup = BeautifulSoup(content, "html.parser")
            return soup.get_text(separator="\n", strip=True)
def find_qualifying_phrase(text: str, phrases: List[str]) -> str:
    for phrase in phrases:
        if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
            return phrase
    return ""

def process_place(place: dict, phrases: List[str]) -> dict:
    website = place.get("website")
    name = place.get("name", "")
    place_id = place.get("place_id")
    if not website:
        log(f"{name} • skipped (no website)")
        return {}

    try:
        text = extract_text_from_url(website)
        matched_phrase = find_qualifying_phrase(text, phrases)
        if matched_phrase:
            summary = f"Triggered by “{matched_phrase}” → {matched_phrase}"
            place["summary"] = summary
            log(f"{name} • triggered by “{matched_phrase}” → {matched_phrase}")
            log(f"{name} • card rendered")  # Added log line for clarity
            return place
        else:
            log(f"{name} • skipped (no qualifying phrases found)")
            return {}
    except Exception as e:
        log(f"{name} • error: {e}")
        return {}
def fetch_places_from_google(query: str, location: str, radius: int = 5000) -> List[dict]:
    base_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "location": location,
        "radius": radius,
        "key": GOOGLE_API_KEY,
    }
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    return response.json().get("results", [])

# Streamlit UI
ensure_schema()
st.title("The Fixe")

if st.button("Reset Database"):
    with get_db_connection() as conn:
        conn.executescript("DROP TABLE IF EXISTS restaurants;")
    init_db()
    st.success("Database reset.")

search_query = st.text_input("Search for Restaurants", "steakhouse East Islip NY")
phrases = ["prix fixe", "fixed price", "specials", "special menu", "special offer", "three course", "3-course", "steak deal"]

if st.button("Run Search"):
    latlng = "40.732253,-73.210338"
    places = fetch_places_from_google(search_query, latlng)
    for place in places:
        place_id = place.get("place_id")
        cached = lookup_cached_place(place_id)
        if cached:
            log(f"[CACHE HIT] place_id={place_id}")
            if cached.get("summary"):
                st.write(cached["name"], "-", cached["summary"])
        else:
            log(f"[CACHE MISS] Fetched from Google API: {place_id}")
            enriched = process_place(place, phrases)
            if enriched:
                cache_place(place_id, enriched)
                st.write(enriched["name"], "-", enriched["summary"])