import requests
import streamlit as st
from settings import GOOGLE_API_KEY

def find_restaurants(location, radius):
    nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    details_url = "https://maps.googleapis.com/maps/api/place/details/json"

    params = {
        "location": location,
        "radius": radius,
        "type": "restaurant",
        "key": GOOGLE_API_KEY
    }

    final_results = []
    seen_place_ids = set()

    while True:
        response = requests.get(nearby_url, params=params)
        try:
            data = response.json()
        except Exception as e:
            st.error(f"Failed to parse JSON: {e}")
            break

        for place in data.get("results", []):
            place_id = place.get("place_id")
            if not place_id or place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            detail_params = {
                "place_id": place_id,
                "fields": "name,vicinity,website",
                "key": GOOGLE_API_KEY
            }

            try:
                detail_response = requests.get(details_url, params=detail_params)
                details = detail_response.json().get("result", {})
            except Exception as e:
                st.warning(f"Details failed for {place_id}: {e}")
                continue

            website = details.get("website", "")
            if website:
                final_results.append({
                    "name": details.get("name", ""),
                    "vicinity": details.get("vicinity", ""),
                    "website": website
                })
            else:
                st.warning(f"[INFO] No website listed for: {details.get('name', 'Unknown')} ({details.get('vicinity', '')})")

        # Pagination support
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
        import time
        time.sleep(2)  # Required delay for token activation
        params["pagetoken"] = next_page_token

    return final_results
