import streamlit as st
import sqlite3
from scraper import fetch_website_text, detect_prix_fixe
from places_api import find_restaurants
from settings import DEFAULT_LOCATION, SEARCH_RADIUS_METERS

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
            rating REAL,
            has_prix_fixe INTEGER
        )
    """)
    conn.commit()
    conn.close()

def store_restaurants(restaurants):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.executemany("""
        INSERT INTO restaurants (name, address, rating, has_prix_fixe)
        VALUES (?, ?, ?, ?)
    """, restaurants)
    conn.commit()
    conn.close()

def load_prix_fixe_restaurants():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT name, address, rating FROM restaurants
        WHERE has_prix_fixe = 1
        ORDER BY rating DESC
    """)
    results = c.fetchall()
    conn.close()
    return results

# --- App UI ---
st.title("Prix Fixe Menu Finder")

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
            rating = 0.0  # Rating not retrieved in this version, default to 0
            website = place.get("website", "")
            has_prix_fixe = 0
            if website:
                text = fetch_website_text(website)
                if detect_prix_fixe(text):
                    has_prix_fixe = 1
            enriched.append((name, address, rating, has_prix_fixe))

        store_restaurants(enriched)
        st.success("Restaurants scraped and stored.")
    except Exception as e:
        st.error(f"Failed to store data: {e}")

try:
    restaurants = load_prix_fixe_restaurants()
    if restaurants:
        for name, address, rating in restaurants:
            st.markdown(f"**{name}** - {address}, Rating: {rating}, Prix Fixe: Yes")
    else:
        st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")
except Exception as e:
    st.error(f"Failed to load data: {e}")