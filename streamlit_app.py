import streamlit as st
import sqlite3
import os
import json
import requests
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from scraper import fetch_website_text, detect_prix_fixe_detailed
from places_textsearch import text_search_restaurants
from settings import GOOGLE_API_KEY
from streamlit_lottie import st_lottie

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
            location TEXT,
            menu_images TEXT,
            ambiance_images TEXT,
            reviews TEXT,
            rating REAL,
            latitude REAL,
            longitude REAL,
            UNIQUE(name, address, location)
        )
    """)
    conn.commit()
    conn.close()

# --------- Data Handling ---------
def store_restaurants(restaurants):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for r in restaurants:
        try:
            c.execute("""
                INSERT OR IGNORE INTO restaurants 
                (name, address, website, has_prix_fixe, label, raw_text, location, menu_images, ambiance_images, reviews, rating, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, r)
        except Exception:
            pass
    conn.commit()
    conn.close()

def load_restaurants_for_location(location):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT name, address, website, label, menu_images, ambiance_images, reviews, rating, latitude, longitude 
        FROM restaurants 
        WHERE has_prix_fixe = 1 AND location = ?
        ORDER BY rating DESC
    """, (location,))
    results = c.fetchall()
    conn.close()
    return results

# --------- Lottie Loader ---------
def load_lottie_local(filepath):
    with open(filepath, "r") as f:
        return json.load(f)

# --------- Scraping Logic ---------
def process_place(place, location):
    name = place.get("name", "")
    address = place.get("vicinity", "")
    website = place.get("website", "")
    latitude = place.get("geometry", {}).get("location", {}).get("lat")
    longitude = place.get("geometry", {}).get("location", {}).get("lng")

    if not website:
        return None

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT has_prix_fixe FROM restaurants WHERE name=? AND address=? AND location=?", (name, address, location))
    result = c.fetchone()
    conn.close()

    if result:
        return None

    # Fetch additional data
    menu_images = f"https://source.unsplash.com/600x400/?menu,{name}"
    ambiance_images = f"https://source.unsplash.com/600x400/?restaurant,{name}"
    reviews = "Great ambiance and delicious prix fixe menu!"  # Placeholder
    rating = 4.5  # Placeholder

    try:
        text = fetch_website_text(website)
        matched, label = detect_prix_fixe_detailed(text)
        if matched:
            return (name, address, website, 1, label, text, location, menu_images, ambiance_images, reviews, rating, latitude, longitude)
    except:
        return None

    return None

# --------- Streamlit UI ---------
st.title("The Fixe")

# Initialize DB only once per session
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

if st.button("Reset Entire Database"):
    init_db()
    st.session_state["db_initialized"] = True
    st.success("Database was reset and rebuilt.")

st.subheader("Search Area")
user_location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

# Run search
if st.button("Click Here To Search"):
    st.session_state["current_location"] = user_location
    st.session_state["search_expanded"] = False

    status_placeholder = st.empty()
    subtext_placeholder = st.empty()
    animation_placeholder = st.empty()

    status_placeholder.markdown("### Please wait for The Fixe...")
    subtext_placeholder.markdown(
        "<p style='font-size: 0.9em; color: white;'>(be patient, we’re cooking)</p>", unsafe_allow_html=True
    )

    cooking_animation = load_lottie_local("Animation - 1748132250829.json")
    if cooking_animation:
        with animation_placeholder.container():
            st_lottie(cooking_animation, height=300, key="cooking")

    try:
        raw_places = text_search_restaurants(user_location)
        places_with_websites = [p for p in raw_places if p.get("website")]
        prioritized = places_with_websites[:25]

        enriched = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda p: process_place(p, user_location), prioritized))
        enriched = [r for r in results if r]

        if enriched:
            store_restaurants(enriched)
            st.success("New results saved.")
        else:
            st.info("No new matches to store.")

    except Exception as e:
        st.error(f"Scrape failed: {e}")

    status_placeholder.markdown("### The Fixe is in. Scroll to the bottom.")
    subtext_placeholder.empty()

    finished_animation = load_lottie_local("Finished.json")
    if finished_animation:
        with animation_placeholder.container():
            st_lottie(finished_animation, height=300, key="finished")

# --------- Display Results ---------
location_to_display = st.session_state.get("current_location", user_location)
results = load_restaurants_for_location(location_to_display)

if results:
    st.subheader("Click on the websites to see the deals.")

    data = []
    for name, address, website, label, menu_images, ambiance_images, reviews, rating, latitude, longitude in results:
        st.markdown(f"### {name}")
        st.markdown(f"**Address:** {address}")
        st.markdown(f"**Rating:** {rating} ⭐")
        st.markdown(f"**Reviews:** {reviews}")
        st.image([menu_images, ambiance_images], caption=["Menu", "Ambiance"], use_column_width=True)
        st.markdown(f"[Visit Website]({website})")
        data.append({"Latitude": latitude, "Longitude": longitude})

    # Display map
    if data:
        map_data = pd.DataFrame(data)
        st.map(map_data)
else:
    st.info("No prix fixe menus stored yet for this location.")