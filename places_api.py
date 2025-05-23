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

    # DEBUGGING: show Google's full response
    st.write("Nearby Search Raw Response:", data)

    if "results" not in data or not data["results"]:
        st.warning("Google returned no restaurant results.")
        return []

    final_results = []
    for place in data["results"]:
        place_id = place.get("place_id")
        if not place_id:
            continue

        detail_params = {
            "place_id": place_id,
            "fields": "name,vicinity,website",
            "key": GOOGLE_API_KEY
        }

        detail_response = requests.get(details_url, params=detail_params)
        try:
            details = detail_response.json().get("result", {})
        except Exception:
            continue

        if "website" in details:
            final_results.append({
                "name": details.get("name", ""),
                "vicinity": details.get("vicinity", ""),
                "website": details["website"]
            })

    return final_results