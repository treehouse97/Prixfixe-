import requests
from settings import GOOGLE_API_KEY

def text_search_restaurants(location_name):
    base_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
    query = f"restaurants in {location_name}"

    params = {
        "query": query,
        "key": GOOGLE_API_KEY
    }

    final_results = []
    seen_place_ids = set()

    while True:
        response = requests.get(base_url, params=params)
        try:
            data = response.json()
        except Exception:
            break

        for result in data.get("results", []):
            place_id = result.get("place_id")
            if not place_id or place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            details_params = {
                "place_id": place_id,
                "fields": "name,vicinity,website",
                "key": GOOGLE_API_KEY
            }

            try:
                detail_response = requests.get(detail_url, params=details_params)
                details = detail_response.json().get("result", {})
            except Exception:
                continue

            website = details.get("website", "")
            if website:
                final_results.append({
                    "name": details.get("name", ""),
                    "vicinity": details.get("vicinity", ""),
                    "website": website
                })
            # No else — silent skip

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
        import time
        time.sleep(2)
        params["pagetoken"] = next_page_token

    return final_results