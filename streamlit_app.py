import streamlit as st
import sqlite3
import requests
from typing import List, Tuple

# WARNING: This is insecure for production environments.
GOOGLE_PLACES_API_KEY = "AIzaSyApX2q-0DaM5xqJGGyiyFA6gkRe7rRxaeM"
DB_NAME = "prix_fixe.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            rating REAL,
            has_prix_fixe BOOLEAN
        )
    """)
    conn.commit()
    conn.close()
    st.success("Database initialized.")

def scrape_restaurants() -> List[Tuple[str, str, float, bool]]:
    location = "40.745,-73.994"  # Example: Midtown Manhattan
    radius = 1500
    type_ = "restaurant"
    url = (
        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        f"?location={location}&radius={radius}&type={type_}&key={GOOGLE_PLACES_API_KEY}"
    )

    response = requests.get(url)
    if response.status_code != 200:
        st.error("Failed to fetch data from Google Places API.")
        return []

    data = response.json()
    results = []
    for r in data.get("results", []):
        name = r.get("name", "Unknown")
        address = r.get("vicinity", "Unknown")
        rating = r.get("rating", 0.0)
        # Simulate logic to identify prix fixe (e.g., keyword in name or types)
        has_prix_fixe = "prix" in name.lower() or "gourmet" in name.lower()
        results.append((name, address, rating, has_prix_fixe))

    return results

def store_restaurants(restaurants: List[Tuple[str, str, float, bool]]):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.executemany("""
        INSERT INTO restaurants (name, address, rating, has_prix_fixe)
        VALUES (?, ?, ?, ?)
    """, restaurants)
    conn.commit()
    conn.close()

def load_prix_fixe_restaurants() -> List[Tuple[str, str, float]]:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT name, address, rating FROM restaurants
        WHERE has_prix_fixe = 1
        ORDER BY rating DESC
    """)
    results = c.fetchall()
    conn.close()
    return results

# Streamlit UI
st.title("Prix Fixe Menu Finder")

if st.button("Initialize Database"):
    init_db()

if st.button("Scrape Restaurants"):
    data = scrape_restaurants()
    if data:
        store_restaurants(data)
        st.success(f"{len(data)} restaurants scraped and stored.")
    else:
        st.warning("No data was scraped.")

restaurants = load_prix_fixe_restaurants()
if restaurants:
    for name, address, rating in restaurants:
        st.markdown(f"**{name}** - {address}, Rating: {rating}, Prix Fixe: Yes")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")