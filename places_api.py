
import requests
from config.settings import GOOGLE_API_KEY

PLACES_ENDPOINT = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
GEOCODE_ENDPOINT = 'https://maps.googleapis.com/maps/api/geocode/json'

def find_restaurants(location='New York, NY', radius=5000, keyword='restaurant'):
    geo_response = requests.get(GEOCODE_ENDPOINT, params={'address': location, 'key': GOOGLE_API_KEY}).json()
    if geo_response['status'] != 'OK':
        print('Geocoding failed:', geo_response)
        return []

    latlng = geo_response['results'][0]['geometry']['location']
    params = {
        'location': f"{latlng['lat']},{latlng['lng']}",
        'radius': radius,
        'keyword': keyword,
        'type': 'restaurant',
        'key': GOOGLE_API_KEY
    }

    response = requests.get(PLACES_ENDPOINT, params=params).json()
    return response.get('results', [])
