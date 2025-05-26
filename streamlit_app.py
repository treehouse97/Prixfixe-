# streamlit_app.py
import os
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from streamlit_lottie import st_lottie

from scraper import fetch_website_text, detect_prix_fixe_detailed
from places_api import text_search_restaurants
from settings import GOOGLE_API_KEY

DB_FILE = "prix_fixe.db"

# ----- Streamlit Config -----
st.set_page_config(page_title="The Fixe", page_icon="🍽", layout="wide")

# ----- Database -----
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS restaurants")
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            website TEXT,
            has_prix_fixe INTEGER,
            label TEXT,
            raw_text TEXT,
            location TEXT,
            rating REAL,
            photo_ref TEXT,
            UNIQUE(name, address, location)
        )
        """
    )
    conn.commit()
    conn.close()


def store_restaurants(rows):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for r in rows:
        c.execute(
            """
            INSERT OR IGNORE INTO restaurants
            (name, address, website, has_prix_fixe, label, raw_text, location, rating, photo_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            r,
        )
    conn.commit()
    conn.close()


def load_restaurants(location):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        SELECT name, address, website, label, rating, photo_ref
        FROM restaurants
        WHERE has_prix_fixe = 1 AND location = ?
        ORDER BY rating DESC NULLS LAST, name
        """,
        (location,),
    )
    data = c.fetchall()
    conn.close()
    return data


# ----- Utilities -----
def load_lottie_local(fp):
    with open(fp, "r") as f:
        return json.load(f)


def prioritize_places(places):
    keywords = [
        "bistro",
        "brasserie",
        "trattoria",
        "tavern",
        "grill",
        "prix fixe",
        "pre fixe",
        "ristorante",
    ]
    return sorted(
        places, key=lambda p: -1 if any(k in p.get("name", "").lower() for k in keywords) else 0
    )


def process_place(place, location):
    name, address, website = place["name"], place["vicinity"], place["website"]
    rating, photo_ref = place.get("rating"), place.get("photo_ref")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT id FROM restaurants WHERE name=? AND address=? AND location=?",
        (name, address, location),
    )
    if c.fetchone():
        conn.close()
        return None
    conn.close()

    try:
        text = fetch_website_text(website)
        matched, label = detect_prix_fixe_detailed(text)
        if matched:
            return (name, address, website, 1, label, text, location, rating, photo_ref)
    except Exception:
        pass
    return None


def restaurant_card(name, address, website, label, rating, photo_ref):
    photo_url = (
        f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={photo_ref}&key={GOOGLE_API_KEY}"
        if photo_ref
        else None
    )
    stars = "⭐" * int(rating) if rating else ""
    badge = f"<span class='restaurant-card-label'>{label}</span>" if label else ""
    return f"""
    <div class="restaurant-card">
        {f'<img src="{photo_url}">' if photo_url else ''}
        <div class="restaurant-card-body">
            {badge}
            <div class="restaurant-card-title">{name}</div>
            <div class="restaurant-card-address">{address}</div>
            {'<div class="restaurant-card-rating">' + stars + '</div>' if stars else ''}
            <a href="{website}" target="_blank">Visit Site</a>
        </div>
    </div>
    """


# ----- CSS -----
st.markdown(
    """
<style>
.restaurant-card{border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.15);overflow:hidden;background:#fff;margin-bottom:24px}
.restaurant-card img{width:100%;height:180px;object-fit:cover}
.restaurant-card-body{padding:12px 16px}
.restaurant-card-title{font-size:1.05rem;font-weight:600;margin-bottom:4px}
.restaurant-card-address{font-size:.9rem;color:#555;margin-bottom:6px}
.restaurant-card-rating{font-size:.9rem;color:#f39c12;margin-bottom:8px}
.restaurant-card-label{display:inline-block;background:#e74c3c;color:#fff;border-radius:4px;padding:2px 6px;font-size:.75rem;margin-bottom:6px}
</style>
""",
    unsafe_allow_html=True,
)

# ----- Page -----
st.title("The Fixe")

if "db_init" not in st.session_state:
    init_db()
    st.session_state["db_init"] = True

if st.button("Reset Database"):
    init_db()
    st.experimental_rerun()

location_input = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

if st.button("Search"):
    st.session_state["current_location"] = location_input
    loc = st.session_state["current_location"]

    placeholder = st.empty()
    animation = st.empty()
    placeholder.markdown("### Scouting the kitchens…")
    cooking = load_lottie_local("Animation - 1748132250829.json")
    if cooking:
        with animation.container():
            st_lottie(cooking, height=300)

    try:
        raw_places = text_search_restaurants(loc)
        candidates = prioritize_places([p for p in raw_places if p.get("website")])[:25]

        with ThreadPoolExecutor(max_workers=10) as executor:
            processed = list(executor.map(lambda p: process_place(p, loc), candidates))

        new_rows = [r for r in processed if r]
        if new_rows:
            store_restaurants(new_rows)
    except Exception as e:
        st.error(f"Search failed: {e}")

    finished = load_lottie_local("Finished.json")
    placeholder.empty()
    if finished:
        with animation.container():
            st_lottie(finished, height=300)

loc_display = st.session_state.get("current_location", location_input)
records = load_restaurants(loc_display)

if records:
    st.subheader(f"Prix Fixe Matches for {loc_display}")
    cols = st.columns(3)
    for idx, (name, addr, site, label, rating, photo_ref) in enumerate(records):
        with cols[idx % 3]:
            st.markdown(
                restaurant_card(name, addr, site, label, rating, photo_ref),
                unsafe_allow_html=True,
            )
else:
    st.info("No prix fixe menus stored yet for this location.")