import time, json, sqlite3
from typing import List, Dict
import requests

from settings import GOOGLE_API_KEY

TEXT_URL   = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# ────────────────── PUBLIC API ───────────────────────────────────────────────
def text_search_restaurants(location_name: str, db_file: str) -> List[Dict]:
    params = {"query": f"restaurants in {location_name}", "key": GOOGLE_API_KEY}
    seen, results = set(), []

    while True:
        data = _get_json(TEXT_URL, params)

        for item in data.get("results", []):
            pid = item.get("place_id")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            det = cached_place_details(pid, db_file, mode="search")
            website = det.get("website")
            if not website:
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
                    "types":    item.get("types", []),
                }
            )

        nxt = data.get("next_page_token")
        if not nxt:
            break
        time.sleep(2)
        params = {"pagetoken": nxt, "key": GOOGLE_API_KEY}

    return results


def place_details(place_id: str, db_file: str) -> Dict:
    return cached_place_details(place_id, db_file, mode="details")

# ────────────────── CACHING LAYER ────────────────────────────────────────────
def cached_place_details(pid: str, db_file: str, mode="search") -> Dict:
    now = int(time.time())
    ttl = 60 * 60 * 24 * 7  # 7 days

    try:
        with sqlite3.connect(db_file) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT details_json, timestamp FROM place_cache WHERE place_id=?",
                (pid,),
            ).fetchone()

            if row and now - row["timestamp"] < ttl:
                print(f"[CACHE HIT] place_id={pid}")
                return json.loads(row["details_json"])
    except Exception as e:
        print(f"[CACHE ERROR] Could not read cache: {e}")

    # Choose minimal field set per usage
    if mode == "details":
        fields = "reviews,types"
    else:
        fields = "name,vicinity,website,rating,photos"

    try:
        data = _get_json(
            DETAIL_URL,
            {"place_id": pid, "fields": fields, "key": GOOGLE_API_KEY},
        ).get("result", {})
        print(f"[CACHE MISS] Fetched from Google API: {pid}")
    except Exception as e:
        print(f"[API ERROR] Failed to fetch from Google: {e}")
        return {}

    try:
        with sqlite3.connect(db_file) as db:
            db.execute(
                "INSERT OR REPLACE INTO place_cache (place_id, details_json, timestamp) VALUES (?, ?, ?)",
                (pid, json.dumps(data), now),
            )
    except Exception as e:
        print(f"[CACHE ERROR] Failed to write to cache: {e}")

    return data

# ────────────────── REQUEST HELPER ───────────────────────────────────────────
def _get_json(url: str, params: Dict) -> Dict:
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}