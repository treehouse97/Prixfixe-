# places_api.py
import time
from typing import List, Dict

import requests
import streamlit as st
from settings import GOOGLE_API_KEY

TEXT_URL   = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"


# ────────────────── cache initialization ─────────────────────────────────────
def initialize_cache():
    if "sheet_cache" not in st.session_state:
        st.session_state["sheet_cache"] = load_cache_from_sheet()


def load_cache_from_sheet() -> Dict[str, Dict]:
    """
    Loads existing place data from a Google Sheet into memory.
    Assumes each row corresponds to a restaurant with a unique place_id.
    Returns a dict keyed by place_id.
    """
    import gspread
    gc = gspread.service_account()
    sh = gc.open("YourSheetName")  # replace with your actual sheet
    worksheet = sh.sheet1
    records = worksheet.get_all_records()

    cache = {}
    for row in records:
        pid = row.get("place_id")
        if pid:
            cache[pid] = {
                "place_id": pid,
                "name":     row.get("name", ""),
                "vicinity": row.get("vicinity", ""),
                "website":  row.get("website"),
                "rating":   row.get("rating"),
                "photo_ref": row.get("photo_ref"),
                "types":    row.get("types", "").split(",") if row.get("types") else [],
            }
    return cache


# ────────────────── public helpers ───────────────────────────────────────────
def text_search_restaurants(location_name: str) -> List[Dict]:
    """
    Google *Text Search* → returns a list of places that have a website.
    Each dict contains: place_id, name, vicinity, website, rating,
                        photo_ref, types
    Uses session cache to avoid redundant lookups.
    """
    initialize_cache()
    params = {"query": f"restaurants in {location_name}", "key": GOOGLE_API_KEY}
    seen, results = set(), []

    while True:
        data = _get_json(TEXT_URL, params)

        for item in data.get("results", []):
            pid = item.get("place_id")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            # Check if already cached
            if pid in st.session_state["sheet_cache"]:
                results.append(st.session_state["sheet_cache"][pid])
                continue

            # Fetch details from API
            det = _fetch_details(pid)
            website = det.get("website")
            if not website:
                continue

            photos = det.get("photos", [])
            entry = {
                "place_id": pid,
                "name":     det.get("name", ""),
                "vicinity": det.get("vicinity", ""),
                "website":  website,
                "rating":   det.get("rating"),
                "photo_ref": photos[0]["photo_reference"] if photos else None,
                "types":    item.get("types", []),
            }

            # Update both results and cache
            results.append(entry)
            st.session_state["sheet_cache"][pid] = entry

        nxt = data.get("next_page_token")
        if not nxt:
            break
        time.sleep(2)
        params = {"pagetoken": nxt, "key": GOOGLE_API_KEY}

    return results


def place_details(place_id: str) -> Dict:
    """
    Lightweight Google *Place Details* wrapper.
    Fetches only `reviews` and `types` – sufficient to build a promo snippet.
    """
    fields = "reviews,types"
    data = _get_json(
        DETAIL_URL,
        {"place_id": place_id, "fields": fields, "key": GOOGLE_API_KEY},
    )
    return data.get("result", {})


# ────────────────── internal helpers ─────────────────────────────────────────
def _fetch_details(pid: str) -> Dict:
    """Details call used internally by the Text‑Search routine."""
    fields = "name,vicinity,website,rating,photos"
    data = _get_json(
        DETAIL_URL,
        {"place_id": pid, "fields": fields, "key": GOOGLE_API_KEY},
    )
    return data.get("result", {})


def _get_json(url: str, params: Dict) -> Dict:
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}