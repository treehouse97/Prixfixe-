import requests
from settings import GOOGLE_API_KEY

def find_restaurants(location, radius):
    endpoint = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": location,
        "radius": radius,
        "type": "restaurant",
        "key": GOOGLE_API_KEY
    }

    response = requests.get(endpoint, params=params)
    try:
        data = response.json()
    except Exception as e:
        print("Failed to parse response:", e)
        return []

    if "results" not in data:
        print("Google API error:", data)
        return []

    print(f"Google returned {len(data['results'])} places")
    return data['results']