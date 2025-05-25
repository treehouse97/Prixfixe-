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

# Layout display logic
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

