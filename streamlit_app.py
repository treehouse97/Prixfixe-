import streamlit as st
import sqlite3
import requests

# Constants
GOOGLE_PLACES_API_KEY = "AIzaSyApX2q-0DaM5xqJGGyiyFA6gkRe7rRxaeM"
LOCATION = "Westbury, NY"
SEARCH_RADIUS = 5000  # in meters
KEYWORD = "prix fixe"

# Initialize DB
def init_db():
    conn = sqlite3.connect("prix_fixe.db")
    c = conn.cursor()
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

# Clear DB (optional utility)
def clear_db():
    conn = sqlite3.connect("prix_fixe.db")
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS restaurants")
    conn.commit()
    conn.close()

# Store data in DB
def store_restaurants(restaurants):
    try:
        conn = sqlite3.connect("prix_fixe.db")
        c = conn.cursor()
        c.executemany("""
            INSERT INTO restaurants (name, address, rating, has_prix_fixe)
            VALUES (?, ?, ?, ?)
        """, restaurants)
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Failed to store data: {e}")

# Load restaurants with prix fixe
def load_prix_fixe_restaurants():
    try:
        conn = sqlite3.connect("prix_fixe.db")
        c = conn.cursor()
        c.execute("""
            SELECT name, address, rating FROM restaurants
            WHERE has_prix_fixe = 1
            ORDER BY rating DESC
        """)
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return []

# Fetch from Google Places
def fetch_restaurants():
    url = (
        f"https://maps.googleapis.com/maps/api/place/textsearch/json?"
        f"query=restaurants+in+{LOCATION}&key={GOOGLE_PLACES_API_KEY}"
    )
    response = requests.get(url)
    data = response.json()
    return data.get("results", [])

# Check for prix fixe keyword
def detect_prix_fixe(restaurant):
    name = restaurant.get("name", "").lower()
    types = restaurant.get("types", [])
    return int("prix" in name or "prix" in " ".join(types).lower())

# Streamlit UI
st.title("Prix Fixe Menu Finder")

if st.button("Initialize Database"):
    init_db()
    st.success("Database initialized.")

if st.button("Scrape Restaurants"):
    api_results = fetch_restaurants()
    parsed = []
    for r in api_results:
        name = r.get("name", "N/A")
        address = r.get("formatted_address", "N/A")
        rating = r.get("rating", 0.0)
        prix = detect_prix_fixe(r)
        parsed.append((name, address, rating, prix))
    store_restaurants(parsed)

# Display results
restaurants = load_prix_fixe_restaurants()
if restaurants:
    for r in restaurants:
        st.markdown(f"**{r[0]}** - {r[1]}, Rating: {r[2]}, Prix Fixe: Yes")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")