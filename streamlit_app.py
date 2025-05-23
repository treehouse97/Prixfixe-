import sqlite3
import streamlit as st
from scraper import fetch_website_text, detect_prix_fixe
from places_api import find_restaurants
from settings import DEFAULT_LOCATION, SEARCH_RADIUS_METERS

DB_PATH = "prix_fixe.db"

st.title("Prix Fixe Menu Finder")

def initialize_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS restaurants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        address TEXT,
        website TEXT,
        scraped INTEGER DEFAULT 0,
        has_prix_fixe INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, address FROM restaurants WHERE has_prix_fixe = 1")
    rows = cursor.fetchall()
    conn.close()
    return rows

def run_scraper():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    results = find_restaurants(location=DEFAULT_LOCATION, radius=SEARCH_RADIUS_METERS)
    for r in results:
        name = r['name']
        address = r.get('vicinity', '')
        website = r.get('website', '')

        if website:
            cursor.execute("INSERT INTO restaurants (name, address, website) VALUES (?, ?, ?)",
                           (name, address, website))
            restaurant_id = cursor.lastrowid
            text = fetch_website_text(website)
            if detect_prix_fixe(text):
                cursor.execute("UPDATE restaurants SET has_prix_fixe = 1 WHERE id = ?", (restaurant_id,))
    conn.commit()
    conn.close()

# Always initialize the DB on first load
initialize_db()

# Scrape button
if st.button("Scrape Restaurants"):
    initialize_db()  # Ensure table exists
    run_scraper()
    st.success("Scraping complete. Reloading results...")
    st.rerun()

# Load and display results
results = load_data()
if results:
    st.subheader(f"Found {len(results)} restaurants with Prix Fixe menus")
    for name, address in results:
        st.markdown(f"**{name}**  \n{address}")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")