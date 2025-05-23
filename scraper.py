import requests
from bs4 import BeautifulSoup
import re

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Focus scraping on sections likely to contain menu information
        menu_sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        menu_text = " ".join(s.get_text(" ", strip=True).lower() for s in menu_sections)
        return menu_text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe(text):
    patterns = [
        r"prix\s*fixe",
        r"\$\d+\s*prix\s*fixe",         # e.g. $25 Prix Fixe
        r"(3|three)[ -]course",
        r"(fixed|set)[ -]?menu",
        r"tasting\s+menu"
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)
