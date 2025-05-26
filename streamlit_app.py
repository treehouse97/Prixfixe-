# streamlit_app.py
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from streamlit_lottie import st_lottie

from scraper import fetch_website_text, detect_prix_fixe_detailed, PATTERNS
from places_api import text_search_restaurants
from settings import GOOGLE_API_KEY

DB_FILE = "prix_fixe.db"
LABEL_ORDER = list(PATTERNS.keys())            # canonical order for grouping


# ────────────────── database helpers ──────────────────────────────────────────
SCHEMA = """
CREATE TABLE restaurants (
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

def init_db() -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)
    conn.commit()
    conn.close()

def ensure_schema() -> None:
    """Auto‑migrate old DBs that lack the rating/photo_ref columns."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("SELECT rating, photo_ref FROM restaurants LIMIT 1")
    except sqlite3.OperationalError:          # old schema detected
        conn.close()
        init_db()                             # rebuild from scratch
    else:
        conn.close()

def store_rows(rows) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.executemany(
        """
        INSERT OR IGNORE INTO restaurants
        (name, address, website, has_prix_fixe, label, raw_text,
         location, rating, photo_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

def fetch_records(location):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        SELECT name, address, website, label, rating, photo_ref
        FROM restaurants
        WHERE has_prix_fixe = 1 AND location = ?
        """,
        (location,),
    )
    data = c.fetchall()
    conn.close()
    return data


# ────────────────── misc utilities ────────────────────────────────────────────
def load_lottie(path):
    with open(path, "r") as fh:
        return json.load(fh)

def prioritize(places):
    kws = {"bistro", "brasserie", "trattoria", "tavern",
           "grill", "prix fixe", "pre fixe", "ristorante"}
    return sorted(
        places,
        key=lambda p: -1 if any(k in p.get("name", "").lower() for k in kws) else 0,
    )

def process_place(place, location):
    name, addr, web = place["name"], place["vicinity"], place["website"]
    rating, photo = place.get("rating"), place.get("photo_ref")

    # skip if already cached
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM restaurants WHERE name=? AND address=? AND location=?",
        (name, addr, location),
    )
    if c.fetchone():
        conn.close()
        return None
    conn.close()

    try:
        text = fetch_website_text(web)
        matched, lbl = detect_prix_fixe_detailed(text)
        if matched:
            return (name, addr, web, 1, lbl, text, location, rating, photo)
    except Exception:
        pass
    return None

def build_card(name, addr, web, lbl, rating, photo):
    photo_tag = (
        f'<img src="https://maps.googleapis.com/maps/api/place/photo'
        f'?maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">'
        if photo
        else ""
    )
    stars = "⭐" * int(rating) if rating else ""
    return f"""
    <div class="card">
        {photo_tag}
        <div class="body">
            <span class="badge">{lbl}</span>
            <div class="title">{name}</div>
            <div class="addr">{addr}</div>
            {'<div class="rate">' + stars + '</div>' if stars else ''}
            <a href="{web}" target="_blank">Visit&nbsp;Site</a>
        </div>
    </div>
    """

def label_rank(lbl):
    lbl = lbl.lower()
    return LABEL_ORDER.index(lbl) if lbl in LABEL_ORDER else len(LABEL_ORDER)


# ────────────────── Streamlit page setup ──────────────────────────────────────
st.set_page_config(page_title="The Fixe", page_icon="🍽", layout="wide")
st.markdown(
    """
<style>
.card{border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.15);
      overflow:hidden;background:#fff;margin-bottom:24px}
.card img{width:100%;height:180px;object-fit:cover}
.body{padding:12px 16px}
.title{font-size:1.05rem;font-weight:600;margin-bottom:4px}
.addr{font-size:.9rem;color:#555;margin-bottom:6px}
.rate{font-size:.9rem;color:#f39c12;margin-bottom:8px}
.badge{display:inline-block;background:#e74c3c;color:#fff;border-radius:4px;
       padding:2px 6px;font-size:.75rem;margin-bottom:6px}
</style>
""",
    unsafe_allow_html=True,
)

# ────────────────── session initialisation ────────────────────────────────────
if "bootstrapped" not in st.session_state:
    ensure_schema()
    st.session_state["bootstrapped"] = True
if "expanded" not in st.session_state:
    st.session_state["expanded"] = False

# ────────────────── header ────────────────────────────────────────────────────
st.title("The Fixe")

if st.button("Reset Database"):
    init_db()
    st.experimental_rerun()

location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")


# ────────────────── search routines ───────────────────────────────────────────
def run_search(limit=25):
    status = st.empty()
    anim   = st.empty()

    status.markdown("### Please wait for The Fixe...<br/>(be patient, we’re cooking)",
                    unsafe_allow_html=True)
    cook = load_lottie("Animation - 1748132250829.json")
    if cook:
        with anim.container():
            st_lottie(cook, height=280, key=f"cook-{time.time()}")

    try:
        raw = text_search_restaurants(location)
        candidates = prioritize([p for p in raw if p.get("website")])
        if limit:
            candidates = candidates[:limit]

        with ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(lambda p: process_place(p, location), candidates))

        rows = [r for r in rows if r]
        if rows:
            store_rows(rows)
    except Exception as e:
        st.error(f"Search failed: {e}")

    status.markdown("### The Fixe is in. Scroll below to see the deals.",
                    unsafe_allow_html=True)
    done = load_lottie("Finished.json")
    if done:
        with anim.container():
            st_lottie(done, height=280, key=f"done-{time.time()}")


# ────────────────── user actions ──────────────────────────────────────────────
if st.button("Search"):
    st.session_state["expanded"] = False
    run_search(limit=25)

records = fetch_records(location)

# ────────────────── results display ───────────────────────────────────────────
if records:
    grouped = {}
    for rec in records:
        grouped.setdefault(rec[3].lower(), []).append(rec)

    for lbl in sorted(grouped, key=label_rank):
        st.subheader(lbl.title())
        cols = st.columns(3)
        for i, (name, addr, web, _, rating, photo) in enumerate(grouped[lbl]):
            with cols[i % 3]:
                st.markdown(
                    build_card(name, addr, web, lbl, rating, photo),
                    unsafe_allow_html=True
                )
else:
    st.info("No prix fixe menus stored yet for this location.")

# ────────────────── expand search option ──────────────────────────────────────
if records and not st.session_state["expanded"]:
    st.markdown("---")
    if st.button("Expand Search"):
        st.session_state["expanded"] = True
        run_search(limit=None)          # unlimited pass
        st.experimental_rerun()