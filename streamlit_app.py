import streamlit as st
import sqlite3
import os
import requests
from scraper import fetch_website_text, detect_prix_fixe_detailed
from places_textsearch import text_search_restaurants
from settings import GOOGLE_API_KEY

DB_FILE = "prix_fixe.db"

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS restaurants")
    c.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            label TEXT,
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
            c.execute("INSERT OR REPLACE INTO restaurants (name, address, label) VALUES (?, ?, ?)", r)
        except Exception as e:
            print(f"Insert failed for {r}: {e}")
    conn.commit()
    conn.close()

def load_all_restaurants():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, address, label FROM restaurants ORDER BY name")
    results = c.fetchall()
    conn.close()
    return results

# ---------------- Geocoding ----------------
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

# ---------------- Streamlit UI ----------------
st.title("Prix Fixe Menu Finder")
ensure_db()

if st.button("Reset Database"):
    init_db()
    st.success("Database reset.")

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
            label = ""
            if website:
                text = fetch_website_text(website)
                match, found_label = detect_prix_fixe_detailed(text)
                if match:
                    label = found_label
            enriched.append((name, address, label))
        store_restaurants(enriched)
        st.success("Restaurants scraped and stored.")
    except Exception as e:
        st.error(f"Failed to store data: {e}")

# ---------------- Results ----------------
try:
    all_restaurants = load_all_restaurants()
    if all_restaurants:
        st.subheader("Matched Restaurants")
        for name, address, label in all_restaurants:
            if label:
                st.markdown(f"**{name}** - {address} ({label})")
    else:
        st.info("No matches found. Use the search above to start.")
except Exception as e:
    st.error(f"Failed to load data: {e}")