import streamlit as st
import sqlite3
import requests
import time

DB_PATH = "prix_fixe.db"

def initialize_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check for 'has_prix_fixe' column and recreate table if missing
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='restaurants'")
    table_exists = cursor.fetchone()

    if table_exists:
        cursor.execute("PRAGMA table_info(restaurants)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'has_prix_fixe' not in columns:
            st.warning("Updating database schema...")
            cursor.execute("DROP TABLE IF EXISTS restaurants")

    # Create table with correct schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            price_level INTEGER,
            rating REAL,
            has_prix_fixe BOOLEAN
        )
    """)
    conn.commit()
    conn.close()
    st.success("Database initialized.")

def insert_restaurant(data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO restaurants (name, address, price_level, rating, has_prix_fixe)
        VALUES (?, ?, ?, ?, ?)
    """, data)
    conn.commit()
    conn.close()

def fetch_restaurants():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM restaurants WHERE has_prix_fixe = 1")
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        st.error(f"Failed to load data: {e}")
        rows = []
    conn.close()
    return rows

def simulate_scrape():
    sample_data = [
        ("Le Gourmet", "123 Main St", 2, 4.5, True),
        ("Bistro du Coin", "456 Elm St", 1, 4.0, False),
        ("Chez Nous", "789 Oak St", 3, 4.8, True),
    ]
    for restaurant in sample_data:
        insert_restaurant(restaurant)
        time.sleep(0.5)

st.title("Prix Fixe Menu Finder")

initialize_db()

if st.button("Scrape Restaurants"):
    simulate_scrape()

restaurants = fetch_restaurants()
if restaurants:
    for r in restaurants:
        st.write(f"**{r[1]}** - {r[2]}, Rating: {r[4]}, Prix Fixe: {'Yes' if r[5] else 'No'}")
else:
    st.info("No prix fixe menus found yet. Tap 'Scrape Restaurants' to begin.")