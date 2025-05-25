import streamlit as st
import sqlite3
import os
import json
import requests
from concurrent.futures import ThreadPoolExecutor

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
                (name, address, website, has_prix_fixe, label, raw_text, location)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, r)
        except Exception:
            pass
    conn.commit()
    conn.close()

def load_restaurants_for_location(location):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT name, address, website, label 
        FROM restaurants 
        WHERE has_prix_fixe = 1 AND location = ?
        ORDER BY name
    """, (location,))
    results = c.fetchall()
    conn.close()
    return results

# --------- Lottie Loader ---------
def load_lottie_local(filepath):
    with open(filepath, "r") as f:
        return json.load(f)

# --------- Target Prioritization ---------
def prioritize_places(places):
    keywords = ["bistro", "brasserie", "trattoria", "tavern", "grill", "prix fixe", "pre fixe", "ristorante"]
    def score(place):
        name = place.get("name", "").lower()
        return -1 if any(k in name for k in keywords) else 0
    return sorted(places, key=score)

# --------- Scraping Logic ---------
def process_place(place, location):
    name = place.get("name", "")
    address = place.get("vicinity", "")
    website = place.get("website", "")

    if not website:
        return None

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT has_prix_fixe FROM restaurants WHERE name=? AND address=? AND location=?", (name, address, location))
    result = c.fetchone()
    conn.close()

    if result:
        return None

    try:
        text = fetch_website_text(website)
        matched, label = detect_prix_fixe_detailed(text)
        if matched:
            return (name, address, website, 1, label, text, location)
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
    animation_placeholder = st.empty()

    with status_placeholder.container():
        st.markdown("### Please wait for The Fixe...")
        st.markdown("<p style='font-size: 0.9em; color: white;'>(be patient, we’re cooking)</p>", unsafe_allow_html=True)

    cooking_animation = load_lottie_local("Animation - 1748132250829.json")
    if cooking_animation:
        with animation_placeholder.container():
            st_lottie(cooking_animation, height=300, key="cooking")

    try:
        raw_places = text_search_restaurants(user_location)
        places_with_websites = [p for p in raw_places if p.get("website")]
        prioritized = prioritize_places(places_with_websites)[:25]

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

    with status_placeholder.container():
        st.markdown("### The Fixe is in. Scroll to the bottom.")

    finished_animation = load_lottie_local("Finished.json")
    if finished_animation:
        with animation_placeholder.container():
            st_lottie(finished_animation, height=300, key="finished")

# --------- Display Results ---------
location_to_display = st.session_state.get("current_location", user_location)
results = load_restaurants_for_location(location_to_display)

if results:
    st.subheader("Click on the websites to see the deals.")

    grouped = {}
    for name, address, website, label in results:
        grouped.setdefault(label.lower(), []).append((name, address, website, label))

    prix_fixe_terms = ["prix fixe", "pre fixe", "price fixe"]
    def is_prix_fixe(label):
        return any(term in label for term in prix_fixe_terms)

    sorted_labels = sorted(grouped.keys(), key=lambda k: (0 if is_prix_fixe(k) else 1, k))

    for key in sorted_labels:
        readable_label = grouped[key][0][3]
        st.markdown(f"#### {readable_label}")
        for name, address, website, _ in grouped[key]:
            st.markdown(f"**{name}** - {address}  \n[Visit Site]({website})")
else:
    st.info("No prix fixe menus stored yet for this location.")

# --------- Expand Search Option ---------
if "search_expanded" not in st.session_state:
    st.session_state["search_expanded"] = False

if results and not st.session_state["search_expanded"]:
    st.markdown("---")
    st.markdown("### Not enough deals?")
    if st.button("Expand Search"):
        st.session_state["search_expanded"] = True

        exp_status = st.empty()
        exp_animation = st.empty()

        with exp_status.container():
            st.markdown("### We’re cooking a big meal—have patience for The Fixe...")

        cooking_animation = load_lottie_local("Animation - 1748132250829.json")
        if cooking_animation:
            with exp_animation.container():
                st_lottie(cooking_animation, height=300, key="cooking_expand")

        try:
            raw_places = text_search_restaurants(location_to_display)
            places_with_websites = [p for p in raw_places if p.get("website")]
            prioritized = prioritize_places(places_with_websites)

            enriched = []
            with ThreadPoolExecutor(max_workers=10) as executor:
                expanded_results = list(executor.map(lambda p: process_place(p, location_to_display), prioritized))
            enriched = [r for r in expanded_results if r]

            if enriched:
                store_restaurants(enriched)
                st.success("Expanded results saved.")
            else:
                st.info("No additional matches found.")

        except Exception as e:
            st.error(f"Expanded scrape failed: {e}")

        with exp_status.container():
            st.markdown("### The Fixe is here. Scroll up.")

        finished_animation = load_lottie_local("Finished.json")
        if finished_animation:
            with exp_animation.container():
                st_lottie(finished_animation, height=300, key="finished_expand")