# places_api.py
import time
from typing import List, Dict

import requests
from settings import GOOGLE_API_KEY

TEXT_URL   = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"


# ────────────────── public helpers ───────────────────────────────────────────
def text_search_restaurants(location_name: str) -> List[Dict]:
    """
    Google *Text Search* → returns a list of places that have a website.
    Each dict contains: place_id, name, vicinity, website, rating,
                        photo_ref, types
    """
    params = {"query": f"restaurants in {location_name}", "key": GOOGLE_API_KEY}
    seen, results = set(), []

    while True:
        data = _get_json(TEXT_URL, params)

        for item in data.get("results", []):
            pid = item.get("place_id")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            # need a Details call to get the website
            det = _fetch_details(pid)
            website = det.get("website")
            if not website:                       # skip places without site
                continue

            photos = det.get("photos", [])
            results.append(
                {
                    "place_id": pid,
                    "name":     det.get("name", ""),
                    "vicinity": det.get("vicinity", ""),
                    "website":  website,
                    "rating":   det.get("rating"),
                    "photo_ref": photos[0]["photo_reference"] if photos else None,
                    "types":    item.get("types", []),      # cuisine / venue tags
                }
            )

        nxt = data.get("next_page_token")
        if not nxt:
            break
        # Google requires a brief pause before the next‑page token becomes valid
        time.sleep(2)
        params = {"pagetoken": nxt, "key": GOOGLE_API_KEY}

    return results


def place_details(place_id: str) -> Dict:
    """
    Lightweight Google *Place Details* wrapper.
    Fetches only `reviews` and `types` – sufficient to build a promo snippet.
    Costs one Places Details quota unit per call.
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