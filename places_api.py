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

    response = requests.get(nearby_url, params=params)
    try:
        data = response.json()
    except Exception as e:
        st.error(f"Failed to parse JSON: {e}")
        return []

    if "results" not in data or not data["results"]:
        st.warning("Google returned no restaurant results.")
        return []

    final_results = []
    for place in data["results"]:
        name = place.get("name", "")
        vicinity = place.get("vicinity", "")
        place_id = place.get("place_id")
        if not place_id:
            continue

        detail_params = {
            "place_id": place_id,
            "fields": "name,vicinity,website",
            "key": GOOGLE_API_KEY
        }

        try:
            detail_response = requests.get(details_url, params=detail_params)
            details = detail_response.json().get("result", {})
        except Exception as e:
            st.warning(f"Failed to fetch details for {name}: {e}")
            continue

        website = details.get("website", "")
        if website:
            final_results.append({
                "name": name,
                "vicinity": vicinity,
                "website": website
            })
        else:
            st.warning(f"[INFO] No website listed for: {name} ({vicinity})")

    return final_results
