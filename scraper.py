
import requests
from bs4 import BeautifulSoup

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True).lower()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe(text):
    keywords = ['prix fixe', 'fixed menu', 'set menu', '3-course', 'three-course', 'tasting menu']
    return any(keyword in text for keyword in keywords)
