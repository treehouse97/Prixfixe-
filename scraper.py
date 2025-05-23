import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Base page content
        sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        text_content = " ".join(s.get_text(" ", strip=True).lower() for s in sections)

        # Look for menu-related subpages
        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"]
            if any(kw in href.lower() for kw in ["menu", "prix", "lunch", "dinner"]):
                sub_url = href if href.startswith("http") else urljoin(url, href)
                try:
                    sub_resp = requests.get(sub_url, headers=headers, timeout=10)
                    sub_resp.raise_for_status()
                    sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                    sub_text = " ".join(s.get_text(" ", strip=True).lower()
                                        for s in sub_soup.find_all(["h1", "h2", "h3", "p", "li", "div"]))
                    text_content += " " + sub_text
                except Exception as e:
                    print(f"Failed to fetch subpage {sub_url}: {e}")

        print(f"--- Final Text for {url} ---")
        print(text_content[:1000])
        return text_content
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe(text):
    patterns = [
        r"prix\s*fixe",
        r"\$\s*\d+\s*(prix\s*fixe)?",
        r"(three|3)[ -]course",
        r"(fixed|set)[ -]?menu",
        r"tasting\s+menu"
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)