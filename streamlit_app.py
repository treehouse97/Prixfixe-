import streamlit as st
import sqlite3
import requests

# Constants
DB_PATH = "prix_fixe.db"
GOOGLE_PLACES_API_KEY = st.secrets"AIzaSyApX2q-0DaM5xqJGGyiyFA6gkRe7rRxaeM"  # Set this in .streamlit/secrets.toml

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY,
            name TEXT,
            address TEXT,
            rating REAL,
            has_prix_fixe INTEGER
        )
    """)
    conn.commit()
    conn.close()

def insert_restaurant(name, address, rating, has_prix_fixe):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO restaurants (name, address, rating, has_prix_fixe)
        VALUES (?, ?, ?, ?)
    """, (name, address, rating, int(has_prix_fixe)))
    conn.commit()
    conn.close()

def fetch_restaurants_from_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, address, rating, has_prix_fixe FROM restaurants")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- Google Places API Fetch ---
def fetch_from_google_places(location, radius=2000, keyword="restaurant"):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": location,
        "radius": radius,
        "type": "restaurant",
        "keyword": keyword,
        "key": GOOGLE_PLACES_API_KEY
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        st.error("Failed to fetch data from Google Places.")
        return []
    return response.json().get("results", [])

# --- Heuristic Filtering ---
def is_prix_fixe_candidate(name, types, vicinity):
    name_l = name.lower()
    return "prix fixe" in name_l or "tasting" in name_l or "course" in name_l

# --- UI & Logic ---
st.title("Prix Fixe Menu Finder")
init_db()
st.success("Database initialized.")

if "lat" not in st.session_state:
    st.session_state["lat"] = "40.743990"
    st.session_state["lng"] = "-73.605881"

with st.sidebar:
    st.subheader("Search Settings")
    st.session_state["lat"] = st.text_input("Latitude", st.session_state["lat"])
    st.session_state["lng"] = st.text_input("Longitude", st.session_state["lng"])
    radius = st.slider("Search Radius (meters)", 500, 5000, 2000)

if st.button("Scrape Restaurants"):
    location = f"{st.session_state['lat']},{st.session_state['lng']}"
    results = fetch_from_google_places(location, radius)
    for res in results:
        name = res.get("name", "Unknown")
        address = res.get("vicinity", "N/A")
        rating = res.get("rating", 0.0)
        types = res.get("types", [])
        has_prix_fixe = is_prix_fixe_candidate(name, types, address)
        insert_restaurant(name, address, rating, has_prix_fixe)

restaurants = fetch_restaurants_from_db()
if restaurants:
    for name, address, rating, prix_fixe in restaurants:
        st.markdown(f"**{name}** - {address}, Rating: {rating}, Prix Fixe: {'Yes' if prix_fixe else 'No'}")
else:
    st.info("No restaurants found yet. Tap 'Scrape Restaurants' to begin.")