import streamlit as st
import sqlite3
import requests
import os

# Constants
GOOGLE_PLACES_API_KEY = "AIzaSyApX2q-0DaM5xqJGGyiyFA6gkRe7rRxaeM"
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

# --- Google Places API Integration ---
def scrape_restaurants_real_world(location="Garden City, NY", radius=3000):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "key": GOOGLE_PLACES_API_KEY,
        "location": "40.7268,-73.6343",  # Garden City coordinates
        "radius": radius,
        "type": "restaurant"
    }
    response = requests.get(url, params=params)
    data = response.json()

    results = []
    for place in data.get("results", []):
        name = place.get("name")
        address = place.get("vicinity")
        rating = place.get("rating", 0.0)
        # Simulated condition: if 'prix fixe' is in name or address (refine as needed)
        has_prix_fixe = int("prix fixe" in name.lower() or "prix fixe" in address.lower())
        results.append((name, address, rating, has_prix_fixe))
    return results

# --- UI ---
st.title("Prix Fixe Menu Finder")

if st.button("Reset Database"):
    init_db()
    st.success("Database reset.")

if st.button("Initialize Database"):
    init_db()
    st.success("Database initialized.")

if st.button("Scrape Restaurants"):
    try:
        data = scrape_restaurants_real_world()
        store_restaurants(data)
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