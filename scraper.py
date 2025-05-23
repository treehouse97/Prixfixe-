import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        base_resp = requests.get(url, headers=headers, timeout=10)
        base_resp.raise_for_status()
        soup = BeautifulSoup(base_resp.text, 'html.parser')

        # Start with homepage content
        sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        all_text = " ".join(s.get_text(" ", strip=True).lower() for s in sections)

        # Extract base domain to validate internal links
        base_domain = urlparse(url).netloc
        visited = set()
        visited.add(url)

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(url, href)
            domain = urlparse(full_url).netloc

            if domain != base_domain or full_url in visited:
                continue  # skip external or already-visited links

            try:
                sub_resp = requests.get(full_url, headers=headers, timeout=10)
                sub_resp.raise_for_status()
                sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                sub_text = " ".join(
                    s.get_text(" ", strip=True).lower()
                    for s in sub_soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
                )
                all_text += " " + sub_text
                visited.add(full_url)
            except Exception as e:
                print(f"Skipped {full_url}: {e}")

        print(f"--- Combined Text for {url} ---")
        print(all_text[:1000])
        return all_text

    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe(text, log=False):
    patterns = [
        r"prix\s*fixe",
        r"\$\s*\d+\s*(prix\s*fixe)?",
        r"(three|3)[ -]course",
        r"(fixed|set)[ -]?menu",
        r"tasting\s+menu"
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            if log:
                print(f"[Pattern Match] Found with pattern: {p}")
            return True
    if log:
        print("[Pattern Match] No match found.")
    return False