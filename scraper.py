import requests
from bs4 import BeautifulSoup
import re

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True).lower()
        print(f"[INFO] Scraped content from {url}")
        return text
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return ""

def detect_prix_fixe(text):
    patterns = [
        r'prix\s*fixe',
        r'fixed\s+menu',
        r'set\s+menu',
        r'\d+\s*(course|courses)',
        r'tasting\s+menu'
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)
