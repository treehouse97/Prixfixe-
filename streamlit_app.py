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
LABEL_ORDER = list(PATTERNS.keys())

# ─── Streamlit Config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="The Fixe", page_icon="🍽", layout="wide")

# ─── Database ──────────────────────────────────────────────────────────────────
def init_db() -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
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


def store_rows(rows) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for r in rows:
        c.execute(
            """
            INSERT OR IGNORE INTO restaurants
            (name, address, website, has_prix_fixe, label, raw_text,
             location, rating, photo_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            r,
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


# ─── Helpers ───────────────────────────────────────────────────────────────────
def load_lottie(path):
    with open(path, "r") as fh:
        return json.load(fh)


def prioritize(places):
    kws = [
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
        places,
        key=lambda p: -1 if any(k in p.get("name", "").lower() for k in kws) else 0,
    )


def process_place(place, location):
    name, addr, web = place["name"], place["vicinity"], place["website"]
    rating, photo = place.get("rating"), place.get("photo_ref")

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
        matched, label = detect_prix_fixe_detailed(text)
        if matched:
            return (
                name,
                addr,
                web,
                1,
                label,
                text,
                location,
                rating,
                photo,
            )
    except Exception:
        pass
    return None


def build_card(name, addr, web, label, rating, photo):
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
            <span class="badge">{label}</span>
            <div class="title">{name}</div>
            <div class="addr">{addr}</div>
            {'<div class="rate">' + stars + '</div>' if stars else ''}
            <a href="{web}" target="_blank">Visit Site</a>
        </div>
    </div>
    """


# ─── CSS ───────────────────────────────────────────────────────────────────────
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

# ─── Session Init ─────────────────────────────────────────────────────────────
if "db_init" not in st.session_state:
    init_db()
    st.session_state["db_init"] = True
if "expanded" not in st.session_state:
    st.session_state["expanded"] = False

# ─── UI ────────────────────────────────────────────────────────────────────────
st.title("The Fixe")

if st.button("Reset Database"):
    init_db()
    st.experimental_rerun()

location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

# ── Primary Search ────────────────────────────────────────────────────────────
def run_search(limit=25):
    msg = st.empty()
    anim = st.empty()

    msg.markdown("### Please wait for The Fixe...<br/>(be patient, we’re cooking)", unsafe_allow_html=True)
    cooking = load_lottie("Animation - 1748132250829.json")
    if cooking:
        with anim.container():
            st_lottie(cooking, height=280, key=str(time.time()))

    try:
        raw = text_search_restaurants(location)
        candidates = prioritize([p for p in raw if p.get("website")])
        if limit:
            candidates = candidates[:limit]

        with ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(lambda p: process_place(p, location), candidates))

        rows_to_store = [r for r in rows if r]
        if rows_to_store:
            store_rows(rows_to_store)
    except Exception as e:
        st.error(f"Search failed: {e}")

    finished = load_lottie("Finished.json")
    msg.markdown("### The Fixe is in. Scroll below to see the deals.", unsafe_allow_html=True)
    if finished:
        with anim.container():
            st_lottie(finished, height=280, key=str(time.time()))


if st.button("Search"):
    st.session_state["expanded"] = False
    run_search(limit=25)

# ── Results Display ───────────────────────────────────────────────────────────
records = fetch_records(location)

if records:
    grouped = {}
    for r in records:
        grouped.setdefault(r[3].lower(), []).append(r)

    def label_rank(lbl):
        lbl_lower = lbl.lower()
        return LABEL_ORDER.index(lbl_lower) if lbl_lower in LABEL_ORDER else len(LABEL_ORDER)

    sorted_labels = sorted(grouped.keys(), key=label_rank)

    for lbl in sorted_labels:
        st.subheader(lbl.title())
        cols = st.columns(3)
        for idx, (name, addr, web, _, rating, photo) in enumerate(grouped[lbl]):
            with cols[idx % 3]:
                st.markdown(build_card(name, addr, web, lbl, rating, photo), unsafe_allow_html=True)
else:
    st.info("No prix fixe menus stored yet for this location.")

# ── Expand Search ─────────────────────────────────────────────────────────────
if records and not st.session_state["expanded"]:
    st.markdown("---")
    if st.button("Expand Search"):
        st.session_state["expanded"] = True
        run_search(limit=None)
        st.experimental_rerun()