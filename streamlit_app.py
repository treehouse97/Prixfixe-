import streamlit as st
import sqlite3
import os
import requests

from scraper import fetch_website_text, detect_prix_fixe_detailed
from places_textsearch import text_search_restaurants
from settings import GOOGLE_API_KEY
from streamlit_lottie import st_lottie

# --------- Style Injection ---------
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Inter', sans-serif;
        background-color: #f9f8f4;
    }

    .main > div {
        padding-top: 1rem;
    }

    h1, h2, h3, h4 {
        color: #402E32;
    }

    .block-container {
        padding: 2rem 2rem;
    }

    </style>
""", unsafe_allow_html=True)

# --------- Constants ---------
DB_FILE = "prix_fixe.db"
LOTTIE_URL = "https://lottie.host/da46d4dd-2c65-4f4a-a4c2-2cb8c8e4caa6/iMqqqAh7wI.json"

# --------- Lottie Helper ---------
def load_lottie_url(url):
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()

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

# --------- Streamlit App ---------
st.title("The Fixe")
ensure_db()

if st.button("Click Here To Reset"):
    init_db()
    st.success("Database reset.")

st.subheader("Search Area")
user_location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

status_placeholder = st.empty()

if st.button("Click Here To Search"):
    with status_placeholder.container():
        st.markdown("### Please wait for The Fixe...")
        lottie_animation = load_lottie_url(LOTTIE_URL)
        if lottie_animation:
            st_lottie(lottie_animation, height=300, key="cooking")

    try:
        raw_places = text_search_restaurants(user_location)
        enriched = []

        for place in raw_places:
            name = place.get("name", "")
            address = place.get("vicinity", "")
            website = place.get("website", "")

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

    with status_placeholder.container():
        st.markdown("### The Fixe is complete. Scroll to the bottom.")

# --------- Display Results ---------
try:
    all_restaurants = load_all_restaurants()
    if all_restaurants:
        st.markdown("## Detected Prix Fixe Menus")

        grouped = {}
        for name, address, website, label in all_restaurants:
            grouped.setdefault(label.lower(), []).append((name, address, website, label))

        # Prioritize prix fixe–style labels
        prix_fixe_labels = [k for k in grouped if any(term in k for term in ["prix fixe", "pre fixe", "price fixe"])]
        other_labels = sorted([k for k in grouped if k not in prix_fixe_labels])

        ordered_labels = prix_fixe_labels + other_labels

        for key in ordered_labels:
            readable_label = grouped[key][0][3]  # Original casing from first item
            st.markdown(f"### {readable_label}")
            for name, address, website, _ in grouped[key]:
                st.markdown(f"**{name}**  \n{address}  \n[Visit Site]({website})", unsafe_allow_html=True)
                st.markdown("---")
    else:
        st.info("No prix fixe menus stored yet.")
except Exception as e:
    st.error(f"Failed to load results: {e}")