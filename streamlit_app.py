# streamlit_app.py  – only st.rerun() fixes applied
import json
import os
import sqlite3
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from streamlit_lottie import st_lottie

from scraper import fetch_website_text, detect_prix_fixe_detailed, PATTERNS
from places_api import text_search_restaurants
from settings import GOOGLE_API_KEY

# ────────────────── per‑session database ──────────────────────────────────────
if "db_file" not in st.session_state:
    st.session_state["db_file"] = os.path.join(
        tempfile.gettempdir(), f"prix_fixe_{uuid.uuid4().hex}.db"
    )
    st.session_state["searched"] = False
    st.session_state["expanded"] = False

DB_FILE      = st.session_state["db_file"]
LABEL_ORDER  = list(PATTERNS.keys())

SCHEMA = """
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

def init_db():
    sqlite3.connect(DB_FILE).executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)

def ensure_schema():
    if not os.path.exists(DB_FILE):
        init_db(); return
    cur = sqlite3.connect(DB_FILE).cursor()
    try:    cur.execute("SELECT rating FROM restaurants LIMIT 1")
    except sqlite3.OperationalError:
        init_db()
    finally:
        cur.connection.close()

def store_rows(rows):
    sqlite3.connect(DB_FILE).executemany(
        "INSERT OR IGNORE INTO restaurants "
        "(name,address,website,has_prix_fixe,label,raw_text,location,rating,photo_ref) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )

def fetch_records(loc):
    return sqlite3.connect(DB_FILE).execute(
        "SELECT name,address,website,label,rating,photo_ref "
        "FROM restaurants WHERE has_prix_fixe=1 AND location=?",
        (loc,),
    ).fetchall()

# ────────────────── helpers ───────────────────────────────────────────────────
def load_lottie(path):
    with open(path) as f: return json.load(f)

def prioritize(places):
    kws = {"bistro","brasserie","trattoria","tavern","grill",
           "prix fixe","pre fixe","ristorante"}
    return sorted(
        places,
        key=lambda p: -1 if any(k in p.get("name","").lower() for k in kws) else 0
    )

def process_place(place, loc):
    name, addr, web  = place["name"], place["vicinity"], place["website"]
    rating, photo    = place.get("rating"), place.get("photo_ref")

    cur = sqlite3.connect(DB_FILE).cursor()
    cur.execute("SELECT 1 FROM restaurants WHERE name=? AND address=? AND location=?",
                (name, addr, loc))
    if cur.fetchone():
        cur.connection.close()
        return None
    cur.connection.close()

    try:
        text = fetch_website_text(web)
        matched, lbl = detect_prix_fixe_detailed(text)
        if matched:
            return (name, addr, web, 1, lbl, text, loc, rating, photo)
    except Exception:
        pass
    return None

def build_card(name, addr, web, lbl, rating, photo):
    img = (f'<img src="https://maps.googleapis.com/maps/api/place/photo?'
           f'maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">'
           if photo else "")
    stars = f'<div class="rate">{rating:.1f} / 5</div>' if rating else ""
    return f"""
    <div class="card">
      {img}
      <div class="body">
        <span class="badge">{lbl}</span>
        <div class="title">{name}</div>
        <div class="addr">{addr}</div>
        {stars}
        <a href="{web}" target="_blank">Visit&nbsp;Site</a>
      </div>
    </div>"""

def label_rank(lbl):
    low = lbl.lower()
    return LABEL_ORDER.index(low) if low in LABEL_ORDER else len(LABEL_ORDER)

# ────────────────── style & layout ────────────────────────────────────────────
st.set_page_config("The Fixe","🍽",layout="wide")
st.markdown(
"""
<style>
.card{border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.15);
      background:#fff;margin-bottom:24px;overflow:hidden}
.card img{width:100%;height:180px;object-fit:cover}
.body{padding:12px 16px}
.title{font-size:1.05rem;font-weight:600;margin-bottom:4px;color:#111}
.addr{font-size:.9rem;color:#444;margin-bottom:6px}
.rate{font-size:.85rem;color:#f39c12;margin-bottom:6px}
.badge{background:#e74c3c;color:#fff;border-radius:4px;padding:2px 6px;
       font-size:.75rem;margin-bottom:8px;display:inline-block}
</style>
""",
unsafe_allow_html=True)

ensure_schema()

# ────────────────── header ────────────────────────────────────────────────────
st.title("The Fixe")

if st.button("Reset Database"):
    init_db()
    st.session_state["searched"] = False
    st.rerun()                           # <── updated

location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

# ────────────────── search routine ────────────────────────────────────────────
def run_search(limit):
    status = st.empty(); anim = st.empty()
    status.markdown("### Please wait for The Fixe...<br/>(be patient, we’re cooking)",
                    unsafe_allow_html=True)
    cook = load_lottie("Animation - 1748132250829.json")
    if cook:
        with anim.container(): st_lottie(cook,height=260)

    try:
        raw  = text_search_restaurants(location)
        cand = prioritize([p for p in raw if p.get("website")])
        if limit: cand = cand[:limit]
        with ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(lambda p: process_place(p,location), cand))
        rows = [r for r in rows if r]
        if rows: store_rows(rows)
    except Exception as e:
        st.error(f"Search failed: {e}")

    status.markdown("### The Fixe is in. Scroll below to see the deals.",
                    unsafe_allow_html=True)
    done = load_lottie("Finished.json")
    if done:
        with anim.container(): st_lottie(done,height=260)

# ────────────────── actions ───────────────────────────────────────────────────
if st.button("Search"):
    st.session_state["searched"]  = True
    st.session_state["expanded"]  = False
    run_search(limit=25)

# ────────────────── results display ───────────────────────────────────────────
if st.session_state.get("searched"):
    records = fetch_records(location)
    if not records:
        st.info("No prix fixe menus stored yet for this location.")
    else:
        grouped={}
        for rec in records: grouped.setdefault(rec[3].lower(),[]).append(rec)

        for lbl in sorted(grouped,key=label_rank):
            st.subheader(lbl.title())
            cols=st.columns(3)
            for i,(n,a,w,_l,r,ph) in enumerate(grouped[lbl]):
                with cols[i%3]:
                    st.markdown(build_card(n,a,w,lbl,r,ph),unsafe_allow_html=True)

        # ─ expand search ──────────────────────────────────────────────────────
        if not st.session_state["expanded"]:
            st.markdown("---")
            if st.button("Expand Search"):
                st.session_state["expanded"] = True
                run_search(limit=None)
                st.rerun()               # <── updated