# UPDATED STREAMLIT FILE with deduplication, reduced API usage, and persistent Google Sheet storage

import streamlit as st
from streamlit_lottie import st_lottie
import json, os, re, time, logging
from concurrent.futures import ThreadPoolExecutor
from typing import List

import gspread
from google.oauth2.service_account import Credentials

from scraper import fetch_website_text, detect_prix_fixe_detailed, PATTERNS
from settings import GOOGLE_API_KEY
from places_api import text_search_restaurants, place_details

# ─────────────────── Google Sheets Setup ────────────────────
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)
client = gspread.authorize(credentials)
SHEET_ID = "1mZymnpQ1l-lEqiwDnursBKN0Mh69L5GziXFyyM5nUI0"
sheet = client.open_by_key(SHEET_ID).sheet1

# ─────────────────── Streamlit Setup ────────────────────────
st.set_page_config("The Fixe", "🍽", layout="wide")
st.title("The Fixe")

logging.basicConfig(level=logging.INFO, format="The Fixe DEBUG » %(message)s", force=True)
log = logging.getLogger("prix_fixe_debug")

DEAL_GROUPS = {
    "Prix Fixe": {"prix fixe", "pre fixe", "price fixed", "fixed menu", "set menu", "tasting menu", "multi-course", "3-course"},
    "Lunch Special": {"lunch special", "complete lunch"},
    "Specials": {"specials", "special menu", "weekly special"},
    "Deals": {"combo deal", "value menu", "deals"},
}
_DISPLAY_ORDER = ["Prix Fixe", "Lunch Special", "Specials", "Deals"]

def canonical_group(label): return next((g for g, s in DEAL_GROUPS.items() if any(k in label.lower() for k in s)), label.title())
def group_rank(g): return _DISPLAY_ORDER.index(g) if g in _DISPLAY_ORDER else len(_DISPLAY_ORDER)
def clean_utf8(s): return s.encode("utf-8", "ignore").decode("utf-8", "ignore")
def load_lottie(path): return json.load(open(path)) if os.path.exists(path) else None
def nice_types(tp): return [t.replace("_", " ").title() for t in tp if t not in {"restaurant", "food", "point_of_interest", "establishment", "store", "bar", "meal_takeaway", "meal_delivery"}][:3]
def first_review(pid): return re.sub(r"\s+", " ", (place_details(pid).get("reviews") or [{}])[0].get("text", "")).strip()[:100] + "…"
def review_link(pid): return f"https://search.google.com/local/reviews?placeid={pid}"

def write_to_sheet(rows):
    if not rows:
        return
    try:
        existing = sheet.get_all_values()[1:]  # Skip header
        existing_keys = set((r[0], r[1], r[8]) for r in existing)  # (name, address, location)

        for r in rows:
            key = (r[0], r[1], r[9])  # (name, address, location)
            if key in existing_keys:
                log.info(f"{r[0]} • skipped (already in Google Sheet)")
                continue

            summary = " ".join(dict.fromkeys(r[5].split()))[:49000]  # deduplicated summary
            sheet.append_row([
                r[0], r[1], r[2], r[4], summary,
                r[6], r[7], r[8], r[9], str(r[10])
            ], value_input_option="USER_ENTERED")
            log.info(f"[SHEET SET] {r[0]}")
    except Exception as e:
        log.error(f"Sheet write error: {e}")

def clear_sheet_except_header():
    try:
        sheet.resize(rows=1)
        log.info("Sheet cleared (except header row).")
        st.success("Google Sheet cleared (except header).")
    except Exception as e:
        st.error(f"Failed to clear sheet: {e}")

def prioritize(places):
    return sorted(places, key=lambda p: -1 if any(k in p.get("name", "").lower() for k in {"bistro", "brasserie", "trattoria", "tavern", "grill", "prix fixe", "pre fixe", "ristorante"}) else 0)

def process_place(place, loc):
    name, addr = place["name"], place["vicinity"]
    web = place.get("website") or place.get("menu_url")
    rating, photo = place.get("rating"), place.get("photo_ref")
    pid, g_types = place.get("place_id"), place.get("types", [])

    try:
        text = clean_utf8(fetch_website_text(web)) if web else ""
        matched, lbl = detect_prix_fixe_detailed(text)
        if matched:
            snippet, link = first_review(pid), review_link(pid)
            types = ", ".join(nice_types(g_types))
            return (name, addr, web, 1, lbl, text, snippet, link, types, loc, rating, photo)
        else:
            log.info(f"{name} • skipped (no qualifying phrases found)")
    except Exception as e:
        log.info(f"{name} • skipped (error: {e})")
    return None

def build_card(name, addr, web, lbl, snippet, link, types_txt, rating, photo):
    chips = "".join(f'<span class="chip">{t}</span>' for t in (types_txt.split(", ") if types_txt else []))
    photo_tag = f'<img src="https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">' if photo else ""
    snippet_ht = f'<p class="snippet">💬 {snippet} <a href="{link}" target="_blank">Read&nbsp;more</a></p>' if snippet else ""
    rating_ht = f'<div class="rate">{rating:.1f} / 5</div>' if rating else ""
    return (
        '<div class="card">' + photo_tag + '<div class="body">'
        f'<span class="badge">{lbl}</span><div class="chips">{chips}</div>'
        f'<div class="title">{name}</div>{snippet_ht}<div class="addr">{addr}</div>'
        f'{rating_ht}<a href="{web}" target="_blank">Visit&nbsp;Site</a></div></div>'
    )

st.markdown("<style>html,body{background:#f8f9fa!important;}</style>", unsafe_allow_html=True)

if st.button("Clear Google Sheet (except header)"):
    clear_sheet_except_header()

location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")
selected_deals = st.multiselect("Deal type (optional)", ["Any deal"] + _DISPLAY_ORDER, default=["Any deal"])
def want_group(g): return ("Any deal" in selected_deals) or (g in selected_deals)

def run_search(limit):
    status, anim = st.empty(), st.empty()
    status.markdown("### Please wait for The Fixe… *(we’re cooking)*", unsafe_allow_html=True)
    cook = load_lottie("Animation - 1748132250829.json")
    if cook:
        with anim.container():
            st_lottie(cook, height=260, key=f"cook-{time.time()}")

    try:
        raw = text_search_restaurants(location)
        cand = prioritize([p for p in raw if p.get("website") or p.get("menu_url")])
        if limit: cand = cand[:limit]
        with ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(lambda p: process_place(p, location), cand))
        valid = [r for r in rows if r]
        write_to_sheet(valid)
    except Exception as e:
        st.error(f"Search failed: {e}")

    status.markdown("### The Fixe is in. Scroll below to see the deals.", unsafe_allow_html=True)
    done = load_lottie("Finished.json")
    if done:
        with anim.container():
            st_lottie(done, height=260, key=f"done-{time.time()}")

if st.button("Search"):
    run_search(limit=25)