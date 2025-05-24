import streamlit as st
import sqlite3
import os
import requests

from scraper import fetch_website_text, detect_prix_fixe_detailed
from places_textsearch import text_search_restaurants
from settings import GOOGLE_API_KEY

DB_FILE = "prix_fixe.db"

# --------- Database setup ---------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS restaurants")
    c.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            website TEXT,
            has_prix_fixe INTEGER,
            label TEXT,
            raw_text TEXT,
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
            c.execute("""
                INSERT OR IGNORE INTO restaurants (name, address, website, has_prix_fixe, label, raw_text)
                VALUES (?, ?, ?, ?, ?, ?)
            """, r)
        except Exception as e:
            print(f"Insert failed for {r}: {e}")
    conn.commit()
    conn.close()

def load_all_restaurants():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, address, website, label FROM restaurants WHERE has_prix_fixe = 1 ORDER BY name")
    results = c.fetchall()
    conn.close()
    return results

# --------- Geocoding ---------
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

# --------- Streamlit Interface ---------
st.title("The Fixe")
ensure_db()

if st.button("Reset Database"):
    init_db()
    st.success("Database reset.")

st.subheader("Search Area")
user_location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

if st.button("Click Here To Search"):
    try:
        raw_places = text_search_restaurants(user_location)
        enriched = []

        for place in raw_places:
            name = place.get("name", "")
            address = place.get("vicinity", "")
            website = place.get("website", "")

            # Check cache
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT has_prix_fixe FROM restaurants WHERE name=? AND address=?", (name, address))
            result = c.fetchone()
            conn.close()

            if result:
                st.info(f"Cached: {name} - {'Yes' if result[0] else 'No'}")
                continue

            if website:
                text = fetch_website_text(website)
                matched, label = detect_prix_fixe_detailed(text)
                if matched:
                    enriched.append((name, address, website, 1, label, text))
                    st.success(f"{name}: Match found ({label})")
                else:
                    st.warning(f"{name}: No prix fixe found.")

        if enriched:
            store_restaurants(enriched)
            st.success("New results saved.")
        else:
            st.info("No new matches to store.")

    except Exception as e:
        st.error(f"Scrape failed: {e}")

# --------- Display Results ---------
try:
    all_restaurants = load_all_restaurants()
    if all_restaurants:
        st.subheader("Detected Prix Fixe Menus")
        for name, address, website, label in all_restaurants:
            st.markdown(f"**{name}** - {address}  \n[Visit Site]({website})  \n_Detected: {label}_")
    else:
        st.info("No prix fixe menus stored yet.")
except Exception as e:
    st.error(f"Failed to load results: {e}")