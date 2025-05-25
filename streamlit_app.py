import streamlit as st
import sqlite3
import os
import json
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import fitz
import re
from concurrent.futures import ThreadPoolExecutor
from streamlit_lottie import st_lottie
from settings import GOOGLE_API_KEY
from places_textsearch import text_search_restaurants

DB_FILE = "prix_fixe.db"

# ---------- PATTERNS ----------
def get_detection_patterns():
    return {
        "prix fixe": r"prix[\s\-]*fixe",
        "pre fixe": r"pre[\s\-]*fixe",
        "price fixed": r"price[\s\-]*fixed",
        "3-course": r"(three|3)[\s\-]*(course|courses)",
        "multi-course": r"\d+\s*course\s*meal",
        "fixed menu": r"(fixed|set)[\s\-]*(menu|meal)",
        "tasting menu": r"tasting\s*menu",
        "special menu": r"special\s*(menu|offer|deal)",
        "complete lunch": r"complete\s*(lunch|dinner)\s*special",
        "lunch special": r"(lunch|dinner)\s*special\s*(menu|offer)?",
        "specials": r"(today'?s|weekday|weekend)?\s*specials",
        "weekly special": r"(weekly|weeknight|weekend)\s*(specials?|menu)",
        "combo deal": r"(combo|combination)\s*(deal|meal|menu)",
        "value menu": r"value\s*(menu|deal|offer)",
        "deals": r"\\bdeals?\\b"
    }

def detect_prix_fixe_detailed(text, patterns):
    for label, pattern in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""

# ---------- SCRAPER ----------
def fetch_website_text(url, patterns):
    def extract_text_from_response(resp):
        content_type = resp.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or resp.url.lower().endswith(".pdf"):
            doc = fitz.open(stream=resp.content, filetype="pdf")
            return " ".join(page.get_text() for page in doc).lower()
        else:
            soup = BeautifulSoup(resp.text, "html.parser")
            return " ".join(
                s.get_text(" ", strip=True).lower()
                for s in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
            )

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        visited = set()
        all_text = ""

        queue = [(url, requests.get(url, headers=headers, timeout=10))]
        for current_url, resp in queue:
            visited.add(current_url)
            resp.raise_for_status()
            text = extract_text_from_response(resp)
            all_text += " " + text

            for label, pattern in patterns.items():
                if re.search(pattern, text, re.IGNORECASE):
                    return all_text.strip(), current_url

            if "text/html" in resp.headers.get("Content-Type", ""):
                soup = BeautifulSoup(resp.text, "html.parser")
                base_domain = urlparse(url).netloc
                for a in soup.find_all("a", href=True):
                    full_url = urljoin(url, a["href"])
                    if urlparse(full_url).netloc == base_domain and full_url not in visited:
                        try:
                            sub_resp = requests.get(full_url, headers=headers, timeout=10)
                            queue.append((full_url, sub_resp))
                        except Exception:
                            continue
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return "", url

# ---------- DATABASE ----------
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
            match_url TEXT,
            has_prix_fixe INTEGER,
            label TEXT,
            raw_text TEXT,
            location TEXT,
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
                (name, address, website, match_url, has_prix_fixe, label, raw_text, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, r)
        except Exception:
            pass
    conn.commit()
    conn.close()

def load_restaurants_for_location(location):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT name, address, match_url, label 
        FROM restaurants 
        WHERE has_prix_fixe = 1 AND location = ?
        ORDER BY name
    """, (location,))
    results = c.fetchall()
    conn.close()
    return results

# ---------- MATCH LOGIC ----------
def process_place(place, location):
    name = place.get("name", "")
    address = place.get("vicinity", "")
    website = place.get("website", "")
    if not website:
        return None

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT has_prix_fixe FROM restaurants WHERE name=? AND address=? AND location=?", (name, address, location))
    if c.fetchone():
        conn.close()
        return None
    conn.close()

    try:
        patterns = get_detection_patterns()
        text, match_url = fetch_website_text(website, patterns)
        matched, label = detect_prix_fixe_detailed(text, patterns)
        if matched:
            return (name, address, website, match_url, 1, label, text, location)
    except:
        return None
    return None

# ---------- UI ----------
st.title("The Fixe")
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

if st.button("Reset Entire Database"):
    init_db()
    st.session_state["db_initialized"] = True
    st.success("Database was reset and rebuilt.")

st.subheader("Search Area")
user_location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

if st.button("Click Here To Search"):
    st.session_state["current_location"] = user_location
    st.session_state["search_expanded"] = False
    status = st.empty()
    subtext = st.empty()
    animation = st.empty()

    status.markdown("### Please wait for The Fixe...")
    subtext.markdown("<p style='font-size: 0.9em; color: white;'>(be patient, we’re cooking)</p>", unsafe_allow_html=True)

    with open("Animation - 1748132250829.json", "r") as f:
        st_lottie(json.load(f), height=300, key="loading")

    raw_places = text_search_restaurants(user_location)
    with_websites = [p for p in raw_places if p.get("website")]

    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        scanned = ex.map(lambda p: process_place(p, user_location), with_websites[:25])
        results = [r for r in scanned if r]

    if results:
        store_restaurants(results)
        st.success("New results saved.")
    else:
        st.info("No new matches to store.")

    status.markdown("### The Fixe is in. Scroll to the bottom.")
    subtext.empty()
    with open("Finished.json", "r") as f:
        st_lottie(json.load(f), height=300, key="done")

# ---------- RESULTS ----------
location = st.session_state.get("current_location", user_location)
records = load_restaurants_for_location(location)

if records:
    st.subheader("Click on the websites to see the deals.")
    grouped = {}
    for name, addr, url, label in records:
        grouped.setdefault(label.lower(), []).append((name, addr, url, label))

    prix_terms = ["prix fixe", "pre fixe", "price fixe"]
    def priority(lbl): return 0 if any(t in lbl for t in prix_terms) else 1
    for k in sorted(grouped, key=priority):
        readable = grouped[k][0][3]
        st.markdown(f"#### {readable}")
        for name, addr, url, _ in grouped[k]:
            st.markdown(f"**{name}** - {addr}  \n[Visit Site]({url})")
else:
    st.info("No prix fixe menus stored yet for this location.")