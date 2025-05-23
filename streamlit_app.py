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

    st.info("Contacting Google Places API...")
    results = find_restaurants(location=DEFAULT_LOCATION, radius=SEARCH_RADIUS_METERS)

    st.subheader("Nearby Search Raw Response:")
    st.json(results)

    raw_places = results.get("results", [])
    st.text(f"Raw restaurant count from Google: {len(raw_places)}")

    for r in raw_places:
        name = r.get("name")
        address = r.get("vicinity", "")
        website = r.get("website", "")

        # Show all names regardless of website for debug
        st.text(f"Found: {name} - {website if website else 'No website'}")

        if website:
            cursor.execute("INSERT INTO restaurants (name, address, website) VALUES (?, ?, ?)",
                           (name, address, website))
            restaurant_id = cursor.lastrowid
            try:
                text = fetch_website_text(website)
                if detect_prix_fixe(text):
                    cursor.execute("UPDATE restaurants SET has_prix_fixe = 1 WHERE id = ?", (restaurant_id,))
            except Exception as e:
                st.warning(f"Scrape error for {name}: {e}")
    conn.commit()
    conn.close()

initialize_db()

if st.button("Scrape Restaurants"):
    run_scraper()
    st.success("Scraping complete. See below.")

results = load_data()
if results:
    st.subheader(f"Found {len(results)} restaurants with Prix Fixe menus")
    for name, address in results:
        st.markdown(f"**{name}**  \n{address}")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")