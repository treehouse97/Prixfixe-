# places_api.py
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
        data = _get_json(TEXT_URL, params)
        for item in data.get("results", []):
            pid = item.get("place_id")
            if not pid or pid in seen: continue
            seen.add(pid)

            det = _fetch_details(pid)
            if not det.get("website"): continue

            photos = det.get("photos", [])
            results.append(
                {
                    "name": det.get("name",""),
                    "vicinity": det.get("vicinity",""),
                    "website": det["website"],
                    "rating": det.get("rating"),
                    "photo_ref": photos[0]["photo_reference"] if photos else None,
                }
            )
        nxt = data.get("next_page_token")
        if not nxt: break
        import time; time.sleep(2)
        params = {"pagetoken": nxt, "key": GOOGLE_API_KEY}
    return results

def _fetch_details(pid:str)->Dict:
    return _get_json(
        DETAIL_URL,
        {"place_id":pid,"fields":"name,vicinity,website,rating,photos","key":GOOGLE_API_KEY},
    ).get("result",{})

def _get_json(url:str,params:Dict)->Dict:
    try: return requests.get(url,params=params,timeout=10).json()
    except Exception: return {}