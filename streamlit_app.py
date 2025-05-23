import streamlit as st
import sqlite3
import requests
import os

# Load API key from Streamlit secrets or hardcoded (as requested)
GOOGLE_PLACES_API_KEY = "AIzaSyApX2q-0DaM5xqJGGyiyFA6gkRe7rRxaeM"

DB_FILE = "prix_fixe.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
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

def delete_db():
    try:
        os.remove(DB_FILE)
        return True, "Database deleted. Please click 'Initialize Database' again."
    except FileNotFoundError:
        return False, "Database file not found."
    except Exception as e:
        return False, f"Failed to delete database: {e}"

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

def mock_scrape_restaurants():
    # Replace with actual scraping or API logic
    return [
        ("Le Gourmet", "123 Main St", 4.5, 1),
        ("Chez Nous", "789 Oak St", 4.8, 1),
        ("No Prix Fixe Place", "456 Elm St", 4.0, 0)
    ]

# Streamlit UI
st.title("Prix Fixe Menu Finder")

if st.button("Delete Database"):
    success, message = delete_db()
    if success:
        st.success(message)
    else:
        st.warning(message)

if st.button("Initialize Database"):
    init_db()
    st.success("Database initialized.")

if st.button("Scrape Restaurants"):
    try:
        data = mock_scrape_restaurants()
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