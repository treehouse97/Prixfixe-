import json, os, re, sqlite3, tempfile, time, uuid, logging
from concurrent.futures import ThreadPoolExecutor
from typing import List
from math import radians, cos, sin, sqrt, atan2

import streamlit as st
from streamlit_lottie import st_lottie

from scraper import (
    fetch_website_text,
    detect_prix_fixe_detailed,
    PATTERNS,
)
from settings import GOOGLE_API_KEY
from places_api import text_search_restaurants, place_details

logging.basicConfig(level=logging.INFO, format="Fixe DEBUG » %(message)s", force=True)
log = logging.getLogger("prix_fixe_debug")

DEAL_GROUPS = {
    "Prix Fixe": {"prix fixe", "pre fixe", "price fixed", "fixed menu", "set menu", "tasting menu", "multi-course", "3-course"},
    "Lunch Special": {"lunch special", "complete lunch"},
    "Specials": {"specials", "special menu", "weekly special"},
    "Deals": {"combo deal", "value menu", "deals"},
}
_DISPLAY_ORDER = ["Prix Fixe", "Lunch Special", "Specials", "Deals"]

def canonical_group(label: str) -> str:
    l = label.lower()
    for g, synonyms in DEAL_GROUPS.items():
        if any(s in l for s in synonyms):
            return g
    return label.title()

def group_rank(g: str) -> int:
    return _DISPLAY_ORDER.index(g) if g in _DISPLAY_ORDER else len(_DISPLAY_ORDER)

def clean_utf8(s: str) -> str:
    return s.encode("utf-8", "ignore").decode("utf-8", "ignore")

def load_lottie(path: str):
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None

def nice_types(tp: List[str]) -> List[str]:
    banned = {"restaurant", "food", "point_of_interest", "establishment", "store", "bar", "meal_takeaway", "meal_delivery"}
    return [t.replace("_", " ").title() for t in tp if t not in banned][:3]

def first_review(pid: str) -> str:
    try:
        revs = (place_details(pid).get("reviews") or [])
        txt = revs[0].get("text", "") if revs else ""
        txt = re.sub(r"\s+", " ", txt).strip()
        return (txt[:100] + "…") if len(txt) > 100 else txt
    except Exception:
        return ""

def review_link(pid: str) -> str:
    return f"https://search.google.com/local/reviews?placeid={pid}"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

if "db_file" not in st.session_state:
    st.session_state["db_file"] = os.path.join(tempfile.gettempdir(), f"prix_fixe_{uuid.uuid4().hex}.db")
    st.session_state["searched"] = False
    st.session_state["latlng"] = None

DB_FILE = st.session_state["db_file"]

SCHEMA = """
CREATE TABLE restaurants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, address TEXT, website TEXT,
  has_prix_fixe INTEGER, label TEXT,
  raw_text TEXT,
  snippet TEXT,
  review_link TEXT,
  types TEXT,
  location TEXT, rating REAL, photo_ref TEXT,
  user_contributed INTEGER DEFAULT 0,
  lat REAL, lng REAL,
  UNIQUE(name, address, location)
);
"""

def update_schema():
    with sqlite3.connect(DB_FILE) as c:
        try:
            c.executescript("""
                ALTER TABLE restaurants ADD COLUMN user_contributed INTEGER DEFAULT 0;
                ALTER TABLE restaurants ADD COLUMN lat REAL;
                ALTER TABLE restaurants ADD COLUMN lng REAL;
            """)
        except sqlite3.OperationalError:
            pass

def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)

def ensure_schema():
    if not os.path.exists(DB_FILE):
        init_db()
    else:
        update_schema()

def store_rows(rows):
    with sqlite3.connect(DB_FILE) as c:
        c.executemany(
            """INSERT OR IGNORE INTO restaurants
            (name,address,website,has_prix_fixe,label,raw_text,snippet,
             review_link,types,location,rating,photo_ref,
             user_contributed, lat, lng)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )

def fetch_records(loc):
    with sqlite3.connect(DB_FILE) as c:
        return c.execute(
            """SELECT name,address,website,label,snippet,review_link,
                      types,rating,photo_ref,user_contributed,lat,lng
               FROM restaurants
               WHERE has_prix_fixe=1 AND location=?""",
            (loc,),
        ).fetchall()

def prioritize(places):
    hits = {"bistro", "brasserie", "trattoria", "tavern", "grill", "prix fixe", "pre fixe", "ristorante"}
    return sorted(places, key=lambda p: -1 if any(k in p.get("name", "").lower() for k in hits) else 0)

def process_place(place, loc):
    name, addr = place["name"], place["vicinity"]
    web = place.get("website") or place.get("menu_url")
    rating = place.get("rating")
    photo = place.get("photo_ref")
    pid = place.get("place_id")
    g_types = place.get("types", [])
    coords = place.get("geometry", {}).get("location", {})
    lat, lng = coords.get("lat"), coords.get("lng")

    with sqlite3.connect(DB_FILE) as c:
        if c.execute("SELECT 1 FROM restaurants WHERE name=? AND address=? AND location=?", (name, addr, loc)).fetchone():
            log.info(f"{name} • skipped (already processed)")
            return None

    try:
        text = fetch_website_text(web) if web else ""
        text = clean_utf8(text)
        matched, lbl = detect_prix_fixe_detailed(text)
        if matched:
            trigger = re.search(PATTERNS[lbl], text, re.IGNORECASE)
            log.info(f"{name} • triggered by “{trigger.group(0) if trigger else lbl}” → {lbl}")
            return (
                name, addr, web, 1, lbl, text,
                first_review(pid), review_link(pid),
                ", ".join(nice_types(g_types)), loc, rating, photo, 0, lat, lng
            )
    except Exception as e:
        log.info(f"{name} • error: {e}")
    return None

def build_card(name, addr, web, lbl, snippet, link, types_txt, rating, photo, user_tip):
    chips = "".join(f'<span class="chip">{t}</span>' for t in (types_txt.split(", ") if types_txt else []))
    badge = f'<span class="badge">{"User Tip" if user_tip else lbl}</span>'
    img = f'<img src="https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">' if photo else ""
    snippet = f'<p class="snippet">💬 {snippet} <a href="{link}" target="_blank">Read&nbsp;more</a></p>' if snippet else ""
    rating = f'<div class="rate">{rating:.1f} / 5</div>' if rating else ""
    return f'<div class="card">{img}<div class="body">{badge}<div class="title">{name}</div>{chips}<div class="addr">{addr}</div>{snippet}{rating}<a href="{web}" target="_blank">Visit&nbsp;Site</a></div></div>'

st.set_page_config("The Fixe", "🍽", layout="wide")
ensure_schema()

st.title("The Fixe")

if st.button("Reset Database"):
    init_db()
    st.session_state["searched"] = False
    st.rerun()

if st.button("Update schema (run once)"):
    update_schema()
    st.success("Schema updated.")

location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

coords_input = st.text_input("Optional: Restrict by lat,lng (e.g. 40.7,-73.2)")
if coords_input:
    try:
        lat_c, lng_c = map(float, coords_input.split(","))
        st.session_state["latlng"] = (lat_c, lng_c)
    except:
        st.error("Invalid format. Use: latitude,longitude")

with st.expander("Add a restaurant manually"):
    with st.form("manual_entry"):
        m_name = st.text_input("Name")
        m_addr = st.text_input("Address")
        m_web = st.text_input("Website")
        m_label = st.selectbox("Deal Type", ["None"] + list(PATTERNS.keys()))
        submitted = st.form_submit_button("Submit")
        if submitted and m_name and m_addr and m_web:
            store_rows([(m_name, m_addr, m_web, 1 if m_label != "None" else 0, m_label if m_label != "None" else "", "", "", "", "", location, None, None, 1, None, None)])
            st.success("Restaurant added.")

deal_options = ["Any deal"] + _DISPLAY_ORDER
selected_deals = st.multiselect("Deal type (optional)", deal_options, default=["Any deal"])

def want_group(g: str) -> bool:
    return "Any deal" in selected_deals or g in selected_deals

if st.button("Search"):
    st.session_state["searched"] = True
    raw = text_search_restaurants(location)
    cand = [p for p in raw if p.get("website") or p.get("menu_url")]
    cand = prioritize(cand)[:25]
    with ThreadPoolExecutor() as ex:
        rows = list(ex.map(lambda p: process_place(p, location), cand))
    store_rows([r for r in rows if r])

if st.session_state.get("searched"):
    recs = fetch_records(location)
    latlng = st.session_state.get("latlng")
    if latlng:
        recs = [r for r in recs if r[10] and r[11] and haversine(latlng[0], latlng[1], r[10], r[11]) <= 10]

    if recs:
        by_group = {}
        for r in recs:
            g = canonical_group(r[3])
            if not want_group(g):
                continue
            by_group.setdefault(g, []).append(r)

        for g in sorted(by_group.keys(), key=group_rank):
            st.subheader(g)
            cols = st.columns(3)
            for i, r in enumerate(by_group[g]):
                with cols[i % 3]:
                    st.markdown(build_card(*r[:9], r[9]), unsafe_allow_html=True)
    else:
        st.info("No prix fixe menus found.")