# places_api.py
import requests
from typing import List, Dict
from settings import GOOGLE_API_KEY


TEXT_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def text_search_restaurants(location_name: str) -> List[Dict]:
    query = f"restaurants in {location_name}"
    params = {"query": query, "key": GOOGLE_API_KEY}

    final_results, seen_place_ids = [], set()

    while True:
        data = _get_json(TEXT_URL, params)
        for result in data.get("results", []):
            place_id = result.get("place_id")
            if not place_id or place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            details = _fetch_details(place_id)
            website = details.get("website")
            if not website:
                continue

            photo_ref = None
            photos = details.get("photos", [])
            if photos:
                photo_ref = photos[0].get("photo_reference")

            final_results.append(
                {
                    "name": details.get("name", ""),
                    "vicinity": details.get("vicinity", ""),
                    "website": website,
                    "rating": details.get("rating", None),
                    "photo_ref": photo_ref,
                }
            )

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
        import time

        time.sleep(2)
        params = {"pagetoken": next_page_token, "key": GOOGLE_API_KEY}

    return final_results


def _fetch_details(place_id: str) -> Dict:
    detail_params = {
        "place_id": place_id,
        "fields": "name,vicinity,website,rating,photos",
        "key": GOOGLE_API_KEY,
    }
    return _get_json(DETAIL_URL, detail_params).get("result", {})


def _get_json(url: str, params: Dict) -> Dict:
    try:
        resp = requests.get(url, params=params, timeout=10)
        return resp.json()
    except Exception:
        return {}