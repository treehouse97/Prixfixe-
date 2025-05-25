import streamlit as st
import sqlite3
import os
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# --------- Scraping Logic with Status ---------
def process_place_verbose(place):
    name = place.get("name", "")
    address = place.get("vicinity", "")
    website = place.get("website", "")

    if not website:
        return {"name": name, "status": "skipped (no website)", "data": None}

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT has_prix_fixe FROM restaurants WHERE name=? AND address=?", (name, address))
    result = c.fetchone()
    conn.close()

    if result:
        return {"name": name, "status": "cached", "data": None}

    try:
        text = fetch_website_text(website)
        matched, label = detect_prix_fixe_detailed(text)
        if matched:
            return {"name": name, "status": f"match found ({label})", "data": (name, address, website, 1, label, text)}
        else:
            return {"name": name, "status": "no deal found", "data": None}
    except:
        return {"name": name, "status": "error", "data": None}

# --------- Streamlit Interface ---------
st.title("The Fixe")
ensure_db()

if st.button("Click Here To Reset"):
    init_db()
    st.success("Database reset.")

st.subheader("Search Area")
user_location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

if st.button("Click Here To Search"):
    status_placeholder = st.empty()
    animation_placeholder = st.empty()

    with status_placeholder.container():
        st.markdown("### Please wait for The Fixe...")

    cooking_animation = load_lottie_local("Animation - 1748132250829.json")
    if cooking_animation:
        with animation_placeholder.container():
            st_lottie(cooking_animation, height=300, key="cooking")

    try:
        raw_places = text_search_restaurants(user_location)

        # --------- Filter and prioritize ---------
        places_with_websites = [p for p in raw_places if p.get("website")]
        prioritized = prioritize_places(places_with_websites)

        # --------- Scraping with live progress ---------
        enriched = []
        progress_area = st.container()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_place_verbose, p): p for p in prioritized}
            for future in as_completed(futures):
                result = future.result()
                name = result["name"]
                status = result["status"]

                with progress_area:
                    if "match found" in status:
                        st.success(f"{name}: {status}")
                    elif "no deal" in status:
                        st.warning(f"{name}: {status}")
                    else:
                        st.info(f"{name}: {status}")

                if result["data"]:
                    enriched.append(result["data"])

        # --------- Store results ---------
        if enriched:
            store_restaurants(enriched)
            st.success("New results saved.")
        else:
            st.info("No new matches to store.")

    except Exception as e:
        st.error(f"Scrape failed: {e}")

    with status_placeholder.container():
        st.markdown("### The Fixe is complete. Scroll to the bottom.")

    finished_animation = load_lottie_local("Finished.json")
    if finished_animation:
        with animation_placeholder.container():
            st_lottie(finished_animation, height=300, key="finished")

# --------- Display Results ---------
try:
    all_restaurants = load_all_restaurants()
    if all_restaurants:
        st.subheader("Detected Prix Fixe Menus")

        grouped = {}
        for name, address, website, label in all_restaurants:
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
        st.info("No prix fixe menus stored yet.")
except Exception as e:
    st.error(f"Failed to load results: {e}")