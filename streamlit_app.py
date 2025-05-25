import streamlit as st
import sqlite3
import os
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from streamlit_lottie import st_lottie

DB_FILE = "prix_fixe.db"
YELP_API_KEY = "YOUR_YELP_API_KEY"  # Replace with your Yelp API Key
YELP_API_URL = "https://api.yelp.com/v3/businesses/search"

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

# --------- Yelp API Call ---------
def fetch_yelp_data(location):
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "location": location,
        "categories": "restaurants",
        "limit": 25,  # Fetch up to 25 restaurants
        "sort_by": "rating"
    }
    response = requests.get(YELP_API_URL, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get("businesses", [])
    else:
        st.error(f"Failed to fetch data from Yelp: {response.status_code}")
        return []

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
    address = ", ".join(place.get("location", {}).get("display_address", []))
    website = place.get("url", "")
    latitude = place.get("coordinates", {}).get("latitude")
    longitude = place.get("coordinates", {}).get("longitude")
    menu_images = place.get("image_url", "")
    ambiance_images = place.get("image_url", "")  # Using the same image for now
    reviews = place.get("review_count", 0)
    rating = place.get("rating", 0.0)
    
    # Mocking prix fixe detection here for simplicity
    has_prix_fixe = 1 if "prix fixe" in name.lower() else 0
    label = "Prix Fixe Menu" if has_prix_fixe else "Standard Menu"

    return (name, address, website, has_prix_fixe, label, None, location, menu_images, ambiance_images, f"{reviews} reviews", rating, latitude, longitude)

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
    status_placeholder = st.empty()
    animation_placeholder = st.empty()

    status_placeholder.markdown("### Please wait for The Fixe...")
    
    cooking_animation = load_lottie_local("Animation - 1748132250829.json")
    if cooking_animation:
        with animation_placeholder.container():
            st_lottie(cooking_animation, height=300, key="cooking")

    try:
        yelp_places = fetch_yelp_data(user_location)

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda p: process_place(p, user_location), yelp_places))

        enriched = [r for r in results if r]
        if enriched:
            store_restaurants(enriched)
            st.success("New results saved.")
        else:
            st.info("No new matches to store.")

    except Exception as e:
        st.error(f"Search failed: {e}")

    status_placeholder.markdown("### The Fixe is in. Scroll to the bottom.")
    animation_placeholder.empty()

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
        st.image([menu_images, ambiance_images], caption=["Menu", "Ambiance"], use_container_width=True)
        st.markdown(f"[Visit Website]({website})")
        if latitude and longitude:
            data.append({"Latitude": latitude, "Longitude": longitude})

    # Display map
    if data:
        map_data = pd.DataFrame(data)
        st.map(map_data)
else:
    st.info("No prix fixe menus stored yet for this location.")