import streamlit as st
import sqlite3
from scraper import fetch_website_text, detect_prix_fixe
from places_textsearch import text_search_restaurants
from settings import GOOGLE_API_KEY, DEFAULT_LOCATION, SEARCH_RADIUS_METERS
import requests
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

def load_all_restaurants():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, address, has_prix_fixe FROM restaurants ORDER BY name")
    results = c.fetchall()
    conn.close()
    return results

# --- Geocoding ---
def geocode_location(place_name):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": place_name, "key": GOOGLE_API_KEY}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["status"] == "OK":
            location = data["results"][0]["geometry"]["location"]
            return f"{location['lat']},{location['lng']}"
        else:
            st.error(f"Geocoding failed: {data['status']}")
    except Exception as e:
        st.error(f"Error geocoding location: {e}")
    return None

# --- App UI ---
st.title("Prix Fixe Menu Finder")

ensure_db()

if st.button("Reset Database"):
    init_db()
    st.success("Database reset.")

if st.button("Initialize Database"):
    init_db()
    st.success("Database initialized.")

st.subheader("Search Area")
user_location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")
if st.button("Scrape Restaurants in Area"):
    try:
        raw_places = text_search_restaurants(user_location)
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

# Display results
try:
    all_restaurants = load_all_restaurants()
    if all_restaurants:
        st.subheader("All Detected Restaurants")
        for name, address, has_pf in all_restaurants:
            st.markdown(f"**{name}** - {address}, Prix Fixe: {'Yes' if has_pf else 'No'}")
    else:
        st.info("No restaurants found. Use the search above to start.")
except Exception as e:
    st.error(f"Failed to load data: {e}")
