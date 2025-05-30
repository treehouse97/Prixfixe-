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

# ──────── Config
st.set_page_config("The Fixe", "🍽", layout="wide")

# ──────── Google Sheets Setup
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)
client = gspread.authorize(credentials)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0/edit"
spreadsheet = client.open_by_url(SHEET_URL)

# ──────── Cache Sheet (Remote)
CACHE_SHEET_NAME = "Cache"
MAX_CACHE_ENTRIES = 500

def get_cache_sheet():
    try:
        return spreadsheet.worksheet(CACHE_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=CACHE_SHEET_NAME, rows="1000", cols="2")

def get_cached_text(place_id: str) -> str | None:
    sheet = get_cache_sheet()
    try:
        records = sheet.get_all_records()
        for row in records:
            if row.get("place_id") == place_id:
                return row.get("text")
    except Exception as e:
        log.error(f"Error reading cache: {e}")
    return None

def set_cached_text(place_id: str, text: str):
    sheet = get_cache_sheet()
    try:
        sheet.append_row([place_id, text])
        prune_cache(sheet)
        log.info(f"[CACHE SET] {place_id}")
    except Exception as e:
        log.error(f"Failed to write to cache for {place_id}: {e}")

def prune_cache(sheet):
    try:
        rows = sheet.get_all_values()
        if len(rows) > MAX_CACHE_ENTRIES:
            sheet.delete_rows(2, len(rows) - MAX_CACHE_ENTRIES + 2)
            log.info(f"Pruned {len(rows) - MAX_CACHE_ENTRIES} rows from cache.")
    except Exception as e:
        log.error(f"Prune error: {e}")

# ──────── Logging
logging.basicConfig(level=logging.INFO, format="The Fixe DEBUG » %(message)s", force=True)
log = logging.getLogger("prix_fixe_debug")

# ──────── Constants
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

def nice_types(tp: List[str]) -> List[str]:
    banned = {"restaurant", "food", "point_of_interest", "establishment", "store", "bar", "meal_takeaway", "meal_delivery"}
    return [t.replace("_", " ").title() for t in tp if t not in banned][:3]

def first_review(pid: str) -> str:
    try:
        revs = (place_details(pid).get("reviews") or [])
        txt = revs[0].get("text", "") if revs else ""
        return (txt[:100] + "…") if len(txt) > 100 else txt.strip()
    except Exception:
        return ""

def review_link(pid: str) -> str:
    return f"https://search.google.com/local/reviews?placeid={pid}"

# ──────── DB Setup
if "db_file" not in st.session_state:
    st.session_state["db_file"] = os.path.join(tempfile.gettempdir(), f"prix_fixe_{uuid.uuid4().hex}.db")
    st.session_state["searched"] = False

DB_FILE = st.session_state["db_file"]
SCHEMA = """
CREATE TABLE restaurants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, address TEXT, website TEXT,
  has_prix_fixe INTEGER, label TEXT,
  raw_text TEXT, snippet TEXT, review_link TEXT,
  types TEXT, location TEXT, rating REAL, photo_ref TEXT,
  UNIQUE(name, address, location)
);
"""

def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)

def ensure_schema():
    if not os.path.exists(DB_FILE): init_db()
    try:
        with sqlite3.connect(DB_FILE) as c:
            c.execute("SELECT 1 FROM restaurants LIMIT 1")
    except sqlite3.OperationalError:
        init_db()

def store_rows(rows):
    with sqlite3.connect(DB_FILE) as c:
        c.executemany(
            """INSERT OR IGNORE INTO restaurants
               (name,address,website,has_prix_fixe,label,raw_text,snippet,review_link,
                types,location,rating,photo_ref)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)

def fetch_records(loc):
    with sqlite3.connect(DB_FILE) as c:
        return c.execute(
            """SELECT name,address,website,label,snippet,review_link,types,rating,photo_ref
               FROM restaurants WHERE has_prix_fixe=1 AND location=?""", (loc,)
        ).fetchall()

# ──────── Logic
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

    with sqlite3.connect(DB_FILE) as c:
        if c.execute("SELECT 1 FROM restaurants WHERE name=? AND address=? AND location=?", (name, addr, loc)).fetchone():
            log.info(f"{name} • skipped (already processed)")
            return None

    if not web:
        return None

    text = get_cached_text(pid)
    if text:
        log.info(f"[CACHE HIT] {pid}")
    else:
        log.info(f"[CACHE MISS] {pid}")
        text = fetch_website_text(web)
        set_cached_text(pid, text)

    text = clean_utf8(text)
    matched, lbl = detect_prix_fixe_detailed(text)
    if matched:
        m = re.search(PATTERNS[lbl], text, re.IGNORECASE)
        trigger = m.group(0) if m else lbl
        log.info(f"{name} • triggered by “{trigger}” → {lbl}")
        snippet = first_review(pid)
        types = ", ".join(nice_types(g_types))
        link = review_link(pid)
        return (name, addr, web, 1, lbl, text, snippet, link, types, loc, rating, photo)
    else:
        log.info(f"{name} • skipped (no qualifying phrases found)")
    return None

# ──────── UI
def build_card(name, addr, web, lbl, snippet, link, types_txt, rating, photo):
    chips = "".join(f'<span class="chip">{t}</span>' for t in types_txt.split(", ") if types_txt)
    photo_tag = f'<img src="https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">' if photo else ""
    snippet_ht = f'<p class="snippet">💬 {snippet} <a href="{link}" target="_blank">Read&nbsp;more</a></p>' if snippet else ""
    rating_ht = f'<div class="rate">{rating:.1f} / 5</div>' if rating else ""
    return f'''
    <div class="card">{photo_tag}<div class="body">
    <span class="badge">{lbl}</span>
    <div class="chips">{chips}</div>
    <div class="title">{name}</div>
    {snippet_ht}
    <div class="addr">{addr}</div>
    {rating_ht}
    <a href="{web}" target="_blank">Visit&nbsp;Site</a></div></div>
    '''

st.markdown("""<style>
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
.chip{display:inline-block;background:#e1e5ea;color:#111;border-radius:999px;padding:2px 8px;font-size:.72rem;margin-right:4px;margin-bottom:4px}
.addr{font-size:.9rem;color:#555;margin-bottom:6px}
.rate{font-size:.9rem;color:#f39c12;margin-bottom:8px}
.badge{display:inline-block;background:#e74c3c;color:#fff;border-radius:4px;padding:2px 6px;font-size:.75rem;margin-bottom:6px;margin-right:6px}
</style>""", unsafe_allow_html=True)

# ──────── App
ensure_schema()
st.title("The Fixe")

if st.button("Reset Database"):
    init_db()
    st.session_state["searched"] = False
    st.rerun()

location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")
deal_options = ["Any deal"] + _DISPLAY_ORDER
selected_deals = st.multiselect("Deal type (optional)", deal_options, default=["Any deal"])

def want_group(g: str) -> bool:
    return "Any deal" in selected_deals or g in selected_deals

def run_search(limit):
    status = st.empty()
    anim = st.empty()
    status.markdown("### Please wait for The Fixe… *(we’re cooking)*", unsafe_allow_html=True)
    cook = load_lottie("Animation - 1748132250829.json")
    if cook:
        with anim.container():
            st_lottie(cook, height=260, key=f"cook-{time.time()}")
    try:
        raw = text_search_restaurants(location)
        cand = [p for p in raw if p.get("website") or p.get("menu_url")]
        cand = prioritize(cand)[:limit] if limit else cand
        with ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(lambda p: process_place(p, location), cand))
        store_rows([r for r in rows if r])
    except Exception as e:
        st.error(f"Search failed: {e}")
    status.markdown("### The Fixe is in. Scroll below to see the deals.", unsafe_allow_html=True)

if st.button("Search"):
    st.session_state.update(searched=True, expanded=False)
    run_search(limit=25)

if st.session_state.get("searched"):
    recs = fetch_records(location)
    if recs:
        grouped = {}
        for r in recs:
            g = canonical_group(r[3])
            if want_group(g): grouped.setdefault(g, []).append(r)
        for g in sorted(grouped, key=group_rank):
            st.subheader(g)
            cols = st.columns(3)
            for i, r in enumerate(grouped[g]):
                with cols[i % 3]:
                    st.markdown(build_card(*r, g), unsafe_allow_html=True)
        if not st.session_state.get("expanded"):
            st.markdown("---")
            if st.button("Expand Search"):
                st.session_state["expanded"] = True
                run_search(limit=None)
                st.rerun()
    else:
        st.info("No prix fixe menus stored yet for this location.")