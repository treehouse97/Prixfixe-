import requests
from bs4 import BeautifulSoup
import re

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract and normalize text from visible content areas
        menu_sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        menu_text = " ".join(s.get_text(" ", strip=True).lower() for s in menu_sections)

        # Preview first 1000 characters for debugging
        print(f"--- Website Text for {url} ---")
        print(menu_text[:1000])

        return menu_text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe(text):
    patterns = [
        r"prix\s*fixe",
        r"\$\s*\d+\s*(prix\s*fixe)?",  # "$25 prix fixe" or "$25"
        r"(three|3)[ -]course",
        r"(fixed|set)[ -]?menu",
        r"tasting\s+menu"
    ]
    return any(re.search(p, text) for p in patterns)
