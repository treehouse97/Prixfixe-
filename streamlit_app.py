import streamlit as st
import sqlite3
import os
import json
import requests

from scraper import fetch_website_text, detect_prix_fixe_detailed
from places_textsearch import text_search_restaurants
from settings import GOOGLE_API_KEY

from streamlit_lottie import st_lottie  # Animation support

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

# --------- Load Local Lottie Animation ---------
def load_lottie_local(filepath):
    with open(filepath, "r") as f:
        return json.load(f)

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

if st.button("Click Here To Reset"):
    init_db()
    st.success("Database reset.")

st.subheader("Search Area")
user_location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

if st.button("Click Here To Search"):
    # Show status and animation in order
    status_placeholder = st.empty()
    animation_placeholder = st.empty()

    with status_placeholder.container():
        st.markdown("### Please wait for The Fixe...")

    lottie_animation = load_lottie_local("Animation - 1748132250829.json")
    if lottie_animation:
        with animation_placeholder.container():
            st_lottie(lottie_animation, height=300, key="cooking")

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
                    st.warning(f"{name}: No deal found.")

        if enriched:
            store_restaurants(enriched)
            st.success("New results saved.")
        else:
            st.info("No new matches to store.")

    except Exception as e:
        st.error(f"Scrape failed: {e}")

    # Update message once scraping is done
    status_placeholder.markdown("### The Fixe is complete. Scroll to the bottom.")

# --------- Display Results ---------
try:
    all_restaurants = load_all_restaurants()
    if all_restaurants:
        st.subheader("Detected Prix Fixe Menus")

        # Group results by label
        grouped = {}
        for name, address, website, label in all_restaurants:
            grouped.setdefault(label.lower(), []).append((name, address, website, label))

        # Prioritize prix fixe–style labels
        prix_fixe_terms = ["prix fixe", "pre fixe", "price fixe"]
        def is_prix_fixe(label):
            return any(term in label for term in prix_fixe_terms)

        sorted_labels = sorted(grouped.keys(), key=lambda k: (0 if is_prix_fixe(k) else 1, k))

        # Display grouped results
        for key in sorted_labels:
            readable_label = grouped[key][0][3]  # Use original casing from first match
            st.markdown(f"#### {readable_label}")
            for name, address, website, _ in grouped[key]:
                st.markdown(f"**{name}** - {address}  \n[Visit Site]({website})")
    else:
        st.info("No prix fixe menus stored yet.")
except Exception as e:
    st.error(f"Failed to load results: {e}")