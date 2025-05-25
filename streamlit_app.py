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
from streamlit_js_eval import get_geolocation

DB_FILE = "prix_fixe.db"

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
            photo_ref TEXT,
            rating REAL,
            review_count INTEGER,
            UNIQUE(name, address, location)
        )
    """)
    conn.commit()
    conn.close()

def store_restaurants(restaurants):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for r in restaurants:
        try:
            c.execute("""
                INSERT OR IGNORE INTO restaurants 
                (name, address, website, has_prix_fixe, label, raw_text, location, photo_ref, rating, review_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, r)
        except Exception:
            pass
    conn.commit()
    conn.close()

def load_restaurants_for_location(location):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT name, address, website, label, photo_ref, rating, review_count
        FROM restaurants 
        WHERE has_prix_fixe = 1 AND location = ?
        ORDER BY name
    """, (location,))
    results = c.fetchall()
    conn.close()
    return results

def build_photo_url(photo_ref):
    if photo_ref:
        return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_ref}&key={GOOGLE_API_KEY}"
    return None

def star_rating(rating):
    if rating is None:
        return ""
    return "â" * int(round(rating)) + f" ({rating:.1f})"

def display_restaurant_card(name, address, website, label, photo_ref, rating, review_count):
    col1, col2 = st.columns([1, 3])
    with col1:
        image_url = build_photo_url(photo_ref)
        if image_url:
            st.image(image_url, width=120)
        else:
            st.image("https://via.placeholder.com/120x90?text=No+Image", width=120)
    with col2:
        st.markdown(f"### {name}")
        st.markdown(f"{address}")
        if rating:
            st.markdown(f"**Rating:** {star_rating(rating)} from {review_count or 0} reviews")
        st.markdown(f"_Detected_: **{label}**")
        st.markdown(f"[Visit Site]({website})")

st.title("The Fixe")

if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

if st.button("Reset Entire Database"):
    init_db()
    st.session_state["db_initialized"] = True
    st.success("Database was reset and rebuilt.")

st.subheader("Search Area")
col1, col2 = st.columns([2, 1])

with col1:
    user_location = st.text_input(
        "Enter a town, hamlet, or neighborhood",
        value=st.session_state.get("user_location", "Islip, NY")
    )

with col2:
    if st.button("Use My Location"):
        result = get_geolocation()
        if result and result.get("latitude") and result.get("longitude"):
            lat = result["latitude"]
            lon = result["longitude"]
            coords = f"{lat},{lon}"

            try:
                geo_url = "https://maps.googleapis.com/maps/api/geocode/json"
                params = {"latlng": coords, "key": GOOGLE_API_KEY}
                resp = requests.get(geo_url, params=params).json()
                if resp["status"] == "OK":
                    formatted = resp["results"][0]["formatted_address"]
                    st.session_state["user_location"] = formatted
                    st.success(f"Using location: {formatted}")
                else:
                    st.warning("Could not geocode location.")
            except Exception as e:
                st.error(f"Geocoding failed: {e}")
        else:
            st.warning("Unable to retrieve your location.")

if st.button("Click Here To Search"):
    st.session_state["current_location"] = user_location
    st.session_state["search_expanded"] = False

    status_placeholder = st.empty()
    subtext_placeholder = st.empty()
    animation_placeholder = st.empty()

    status_placeholder.markdown("### Please wait for The Fixe...")
    subtext_placeholder.markdown(
        "<p style='font-size: 0.9em; color: white;'>(be patient, weâre cooking)</p>", unsafe_allow_html=True
    )

    cooking_animation = "Animation - 1748132250829.json"
    if os.path.exists(cooking_animation):
        with open(cooking_animation, "r") as f:
            anim = json.load(f)
            st_lottie(anim, height=300, key="cooking")

    try:
        raw_places = text_search_restaurants(user_location)
        places_with_websites = [p for p in raw_places if p.get("website")]
        prioritized = places_with_websites[:25]

        def process_place(place):
            name = place.get("name", "")
            address = place.get("vicinity", "")
            website = place.get("website", "")
            photo_ref = place.get("photo_ref", "")
            rating = place.get("rating", None)
            review_count = place.get("user_ratings_total", None)

            if not website:
                return None

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT has_prix_fixe FROM restaurants WHERE name=? AND address=? AND location=?", (name, address, user_location))
            result = c.fetchone()
            conn.close()

            if result:
                return None

            try:
                text = fetch_website_text(website)
                matched, label = detect_prix_fixe_detailed(text)
                if matched:
                    return (name, address, website, 1, label, text, user_location, photo_ref, rating, review_count)
            except:
                return None

            return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(process_place, prioritized))
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

    finished_animation = "Finished.json"
    if os.path.exists(finished_animation):
        with open(finished_animation, "r") as f:
            anim = json.load(f)
            st_lottie(anim, height=300, key="finished")

location_to_display = st.session_state.get("current_location", user_location)
results = load_restaurants_for_location(location_to_display)

if results:
    st.subheader("Click on the websites to see the deals.")

    prix_fixe_terms = ["prix fixe", "pre fixe", "price fixe"]
    def is_prix_fixe(label):
        return any(term in label for term in prix_fixe_terms)

    sorted_results = sorted(results, key=lambda r: (0 if is_prix_fixe(r[3]) else 1, r[0]))

    for r in sorted_results:
        display_restaurant_card(*r)
else:
    st.info("No prix fixe menus stored yet for this location.")