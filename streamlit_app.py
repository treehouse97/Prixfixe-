import streamlit as st
import sqlite3
from typing import List, Tuple

# Secure API key retrieval
GOOGLE_PLACES_API_KEY = st.secrets["api"]["GOOGLE_PLACES_API_KEY"]

# DB setup
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

def scrape_mock_restaurants() -> List[Tuple[str, str, float, bool]]:
    # Mock data for demonstration
    return [
        ("Le Gourmet", "123 Main St", 4.5, True),
        ("Chez Nous", "789 Oak St", 4.8, True),
        ("Taco Spot", "456 Elm St", 4.2, False),
    ]

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
    data = scrape_mock_restaurants()
    store_restaurants(data)
    st.success("Restaurants scraped and stored.")

restaurants = load_prix_fixe_restaurants()
if restaurants:
    for name, address, rating in restaurants:
        st.markdown(f"**{name}** - {address}, Rating: {rating}, Prix Fixe: Yes")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")