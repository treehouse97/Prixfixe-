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
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name, address FROM restaurants WHERE has_prix_fixe = 1")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except sqlite3.OperationalError:
        return []

def run_scraper():
    initialize_db()
    st.info("Contacting Google Places API...")
    results = find_restaurants(location=DEFAULT_LOCATION, radius=SEARCH_RADIUS_METERS)

    st.markdown(f"**Raw restaurant count from Google: {len(results)}**")

    if not results:
        st.error("No places returned from Google. API key may be invalid or location is unreachable.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    added = 0
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
                added += 1
    conn.commit()
    conn.close()

    if added:
        st.markdown(f"**{added} restaurants with prix fixe menus added.**")
    else:
        st.markdown("Scraping completed but no prix fixe menus were found.")

# Always initialize DB
initialize_db()

# Scrape Button
if st.button("Scrape Restaurants"):
    run_scraper()
    st.rerun()

# Display Data
results = load_data()
if results:
    st.subheader(f"Found {len(results)} restaurants with Prix Fixe menus")
    for name, address in results:
        st.markdown(f"**{name}**  \n{address}")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")