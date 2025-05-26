import requests
from typing import List, Dict
from settings import GOOGLE_API_KEY

TEXT_URL   = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def text_search_restaurants(location_name: str) -> List[Dict]:
    query  = f"restaurants in {location_name}"
    params = {"query": query, "key": GOOGLE_API_KEY}

    seen, results = set(), []

    while True:
        data = _get(TEXT_URL, params)
        for r in data.get("results", []):
            pid = r.get("place_id")
            if not pid or pid in seen:
                continue
            seen.add(pid)

            details = _get(
                DETAIL_URL,
                {
                    "place_id": pid,
                    "fields": (
                        "name,vicinity,website,rating,types,price_level,"
                        "opening_hours,geometry,photos"
                    ),
                    "key": GOOGLE_API_KEY,
                },
            ).get("result", {})

            if not details.get("website"):
                continue

            loc = details["geometry"]["location"]
            photos = details.get("photos", [])
            results.append(
                {
                    "name": details["name"],
                    "address": details.get("vicinity", ""),
                    "website": details["website"],
                    "rating": details.get("rating"),
                    "types": details.get("types", []),
                    "price_level": details.get("price_level"),
                    "open_now": details.get("opening_hours", {}).get("open_now"),
                    "lat": loc["lat"],
                    "lng": loc["lng"],
                    "photo_ref": photos[0]["photo_reference"] if photos else None,
                }
            )

        nxt = data.get("next_page_token")
        if not nxt:
            break
        import time

        time.sleep(2)
        params = {"pagetoken": nxt, "key": GOOGLE_API_KEY}

    return results


def _get(url: str, params: Dict) -> Dict:
    try:
        return requests.get(url, params=params, timeout=8).json()
    except Exception:
        return {}