import sqlite3
import streamlit as st
from scraper import fetch_website_text, detect_prix_fixe
from places_api import find_restaurants
from settings import DEFAULT_LOCATION, SEARCH_RADIUS_METERS

DB_PATH = "prix_fixe.db"

st.title("Prix Fixe Menu Finder")

# Initialize the database
def initialize_db():
    try:
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
        st.success("Database initialized.")
    except Exception as e:
        st.error(f"Database initialization failed: {e}")

# Show what tables exist in the database (debugging help)
def debug_tables():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        st.text(f"Tables in DB: {tables}")
        conn.close()
    except Exception as e:
        st.error(f"Failed to inspect DB: {e}")

# Load restaurants from DB with prix fixe menus
def load_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name, address FROM restaurants WHERE has_prix_fixe = 1")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return []

# Scrape and update the DB
def run_scraper():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        results = find_restaurants(location=DEFAULT_LOCATION, radius=SEARCH_RADIUS_METERS)

        st.write("Raw restaurant count from Google:", len(results))
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
        st.success("Scraping complete.")
    except Exception as e:
        st.error(f"Scraping failed: {e}")

# --- Run app ---
initialize_db()
debug_tables()

# Scraper button
if st.button("Scrape Restaurants"):
    run_scraper()

# Display found results
results = load_data()
if results:
    st.subheader(f"Found {len(results)} restaurants with Prix Fixe menus")
    for name, address in results:
        st.markdown(f"**{name}**  \n{address}")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")