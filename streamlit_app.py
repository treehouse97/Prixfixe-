import streamlit as st
import sqlite3
from scraper import fetch_website_text, detect_prix_fixe
from places_api import find_restaurants
from settings import DEFAULT_LOCATION, SEARCH_RADIUS_METERS
import os

DB_FILE = "prix_fixe.db"

# --- Database Operations ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS restaurants")
    c.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            has_prix_fixe INTEGER,
            UNIQUE(name, address)
        )
    """)
    conn.commit()
    conn.close()

def ensure_db():
    if not os.path.exists(DB_FILE):
        init_db()

def store_restaurants(restaurants):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for r in restaurants:
        try:
            c.execute("INSERT OR IGNORE INTO restaurants (name, address, has_prix_fixe) VALUES (?, ?, ?)", r)
        except Exception as e:
            print(f"Insert failed for {r}: {e}")
    conn.commit()
    conn.close()

def load_prix_fixe_restaurants():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, address FROM restaurants WHERE has_prix_fixe = 1 ORDER BY name")
    results = c.fetchall()
    conn.close()
    return results

# --- App UI ---
st.title("Prix Fixe Menu Finder")

ensure_db()

if st.button("Reset Database"):
    init_db()
    st.success("Database reset.")

if st.button("Initialize Database"):
    init_db()
    st.success("Database initialized.")

if st.button("Scrape Restaurants"):
    try:
        raw_places = find_restaurants(DEFAULT_LOCATION, SEARCH_RADIUS_METERS)
        enriched = []
        for place in raw_places:
            name = place.get("name", "")
            address = place.get("vicinity", "")
            website = place.get("website", "")
            has_prix_fixe = 0
            if website:
                text = fetch_website_text(website)
                if detect_prix_fixe(text):
                    has_prix_fixe = 1
            enriched.append((name, address, has_prix_fixe))
        store_restaurants(enriched)
        st.success("Restaurants scraped and stored.")
    except Exception as e:
        st.error(f"Failed to store data: {e}")

# Manual Entry Form
st.subheader("Add a Restaurant Manually")
with st.form("manual_entry"):
    manual_name = st.text_input("Restaurant Name")
    manual_address = st.text_input("Address")
    manual_url = st.text_input("Website URL")
    submitted = st.form_submit_button("Add Restaurant")
    if submitted:
        try:
            text = fetch_website_text(manual_url)
            has_prix_fixe = int(detect_prix_fixe(text))
            store_restaurants([(manual_name, manual_address, has_prix_fixe)])
            st.success(f"Manually added {manual_name} (Prix Fixe: {'Yes' if has_prix_fixe else 'No'})")
        except Exception as e:
            st.error(f"Failed to add manually: {e}")

# Output Results
try:
    restaurants = load_prix_fixe_restaurants()
    if restaurants:
        for name, address in restaurants:
            st.markdown(f"**{name}** - {address}, Prix Fixe: Yes")
    else:
        st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' or use manual entry.")
except Exception as e:
    st.error(f"Failed to load data: {e}")
