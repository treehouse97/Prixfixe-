import streamlit as st
from streamlit_lottie import st_lottie
import json, os, re, sqlite3, tempfile, time, uuid, logging
from concurrent.futures import ThreadPoolExecutor
from typing import List

import gspread
from google.oauth2.service_account import Credentials

from scraper import fetch_website_text, detect_prix_fixe_detailed, PATTERNS
from settings import GOOGLE_API_KEY
from places_api import text_search_restaurants, place_details

# ─────────────────── Google Sheets Setup ────────────────────
scope = ["https://www.googleapis.com/auth/spreadsheets"]
try:
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    client = gspread.authorize(credentials)
    SHEET_ID = "1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0"
    sheet = client.open_by_key(SHEET_ID).sheet1
except Exception as e:
    st.error("🚫 Failed to load Google credentials or access Google Sheet.")
    st.exception(e)
    st.stop()

# ─────────────────── Streamlit Setup ────────────────────────
st.set_page_config("The Fixe", "🍽", layout="wide")
st.title("The Fixe")

logging.basicConfig(level=logging.INFO, format="The Fixe DEBUG » %(message)s", force=True)
log = logging.getLogger("prix_fixe_debug")

DEAL_GROUPS = {
    "Prix Fixe": {"prix fixe", "pre fixe", "price fixed", "fixed menu", "set menu", "tasting menu", "multi-course", "3-course"},
    "Lunch Special": {"lunch special", "complete lunch"},
    "Specials": {"specials", "special menu", "weekly special"},
    "Deals": {"combo deal", "value menu", "deals"},
}
_DISPLAY_ORDER = ["Prix Fixe", "Lunch Special", "Specials", "Deals"]

def canonical_group(label): return next((g for g, s in DEAL_GROUPS.items() if any(k in label.lower() for k in s)), label.title())
def group_rank(g): return _DISPLAY_ORDER.index(g) if g in _DISPLAY_ORDER else len(_DISPLAY_ORDER)
def safe_rerun(): (st.rerun if hasattr(st, "rerun") else st.experimental_rerun)()
def clean_utf8(s): return s.encode("utf-8", "ignore").decode("utf-8", "ignore")
def load_lottie(path): 
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None
def nice_types(tp): return [t.replace("_", " ").title() for t in tp if t not in {"restaurant", "food", "point_of_interest", "establishment", "store", "bar", "meal_takeaway", "meal_delivery"}][:3]
def first_review(pid): return re.sub(r"\s+", " ", (place_details(pid).get("reviews") or [{}])[0].get("text", "")).strip()[:100] + "…"
def review_link(pid): return f"https://search.google.com/local/reviews?placeid={pid}"

if "db_file" not in st.session_state:
    st.session_state["db_file"] = os.path.join(tempfile.gettempdir(), f"prix_fixe_{uuid.uuid4().hex}.db")
    st.session_state["searched"] = False

if "places_cache" not in st.session_state:
    st.session_state["places_cache"] = {}

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
  UNIQUE(name, address, location)
);
"""

def init_db():
    with sqlite3.connect(DB_FILE) as c: c.executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)
def ensure_schema():
    if not os.path.exists(DB_FILE): init_db()
    else:
        try: sqlite3.connect(DB_FILE).execute("SELECT 1 FROM restaurants LIMIT 1")
        except sqlite3.OperationalError: init_db()
def store_rows(rows):
    with sqlite3.connect(DB_FILE) as c:
        c.executemany("""
            INSERT OR IGNORE INTO restaurants
            (name,address,website,has_prix_fixe,label,raw_text,
             snippet,review_link,types,location,rating,photo_ref)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
