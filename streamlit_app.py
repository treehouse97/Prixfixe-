import json, os, re, sqlite3, tempfile, time, uuid, logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import streamlit as st
from streamlit_lottie import st_lottie

from scraper import (
    fetch_website_text,
    detect_prix_fixe_detailed,
    PATTERNS,
)
from settings import GOOGLE_API_KEY
from places_api import text_search_restaurants, place_details

# ─────────────── Setup ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="The Fixe DEBUG » %(message)s",
    force=True,
)
log = logging.getLogger("prix_fixe_debug")

DEAL_GROUPS = {
    "Prix Fixe": {
        "prix fixe", "pre fixe", "price fixed",
        "fixed menu", "set menu", "tasting menu",
        "multi-course", "3-course",
    },
    "Lunch Special": {"lunch special", "complete lunch"},
    "Specials":      {"specials", "special menu", "weekly special"},
    "Deals":         {"combo deal", "value menu", "deals"},
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

# ─────────────── DB and State ─────────────────
if "db_file" not in st.session_state:
    st.session_state["db_file"] = os.path.join(
        tempfile.gettempdir(), f"prix_fixe_{uuid.uuid4().hex}.db"
    )
    st.session_state["searched"] = False

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

USER_SUBMIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_suggestions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  address TEXT,
  website TEXT,
  deal_type TEXT,
  notes TEXT,
  submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)

def ensure_schema():
    if not os.path.exists(DB_FILE):
        init_db()
        return
    try:
        with sqlite3.connect(DB_FILE) as c:
            c.execute("SELECT 1 FROM restaurants LIMIT 1")
    except sqlite3.OperationalError:
        init_db()

def ensure_user_schema():
    with sqlite3.connect(DB_FILE) as c:
        c.executescript(USER_SUBMIT_SCHEMA)

ensure_schema()
ensure_user_schema()

def insert_user_suggestion(name, address, website, deal_type, notes):
    with sqlite3.connect(DB_FILE) as c:
        c.execute(
            "INSERT INTO user_suggestions (name, address, website, deal_type, notes) VALUES (?, ?, ?, ?, ?)",
            (name, address, website, deal_type, notes)
        )

# ─────────────── Streamlit UI ─────────────────
st.set_page_config("The Fixe", "🍽", layout="wide")

st.markdown(
    \"\"\"<style>
html,body,[data-testid="stAppViewContainer"]{background:#f8f9fa!important;color:#111!important;}
.stButton>button{background:#212529!important;color:#fff!important;border-radius:4px!important;font-weight:600!important;}
.stButton>button:hover{background:#343a40!important;}
.stTextInput input{background:#fff!important;color:#111!important;border:1px solid #ced4da!important;}

.card{border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.1);overflow:hidden;background:#fff;margin-bottom:24px}
.card img{width:100%;height:180px;object-fit:cover}
.body{padding:12px 16px}
.title{font-size:1.05rem;font-weight:600;margin-bottom:2px;color:#111;}
.snippet{font-size:.83rem;color:#444;margin:.35rem 0 .5rem}
.snippet a{color:#0d6efd;text-decoration:none}
.chips{margin-bottom:4px}
.chip{display:inline-block;background:#e1e5ea;color:#111;border-radius:999px;
      padding:2px 8px;font-size:.72rem;margin-right:4px;margin-bottom:4px}
.addr{font-size:.9rem;color:#555;margin-bottom:6px}
.rate{font-size:.9rem;color:#f39c12;margin-bottom:8px}
.badge{display:inline-block;background:#e74c3c;color:#fff;border-radius:4px;
       padding:2px 6px;font-size:.75rem;margin-bottom:6px;margin-right:6px}
</style>\"\"\", unsafe_allow_html=True)

st.title("The Fixe")

# ─────────────── Suggestion Form ─────────────────
st.markdown("## Suggest a Restaurant or Tag a Deal")
with st.form("user_suggestion_form"):
    name = st.text_input("Restaurant Name", "")
    address = st.text_input("Address (optional)", "")
    website = st.text_input("Website URL (optional)", "")
    deal_type = st.selectbox(
        "Deal Type (optional)",
        ["", "Prix Fixe", "Lunch Special", "Specials", "Combo Deal", "Other"]
    )
    notes = st.text_area("Additional Notes (optional)")
    submitted = st.form_submit_button("Submit Suggestion")

if submitted and name.strip():
    insert_user_suggestion(name.strip(), address.strip(), website.strip(), deal_type.strip(), notes.strip())
    st.success("Thank you! Your suggestion has been recorded.")

# (continued below: admin panel and original search logic)