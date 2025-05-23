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

        sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        all_text = " ".join(s.get_text(" ", strip=True).lower() for s in sections)

        base_domain = urlparse(url).netloc
        visited = {url}

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(url, href)
            domain = urlparse(full_url).netloc

            if domain != base_domain or full_url in visited:
                continue

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
            except Exception:
                continue

        return all_text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe_detailed(text):
    patterns = {
        "prix fixe": r"prix\s*fixe",
        "pre fixe": r"pre\s*fixe",
        "3-course": r"(three|3)[ -]course",
        "special menu": r"special\s+menu",
        "fixed menu": r"(fixed|set)[ -]?menu",
        "tasting menu": r"tasting\s+menu"
    }

    for label, pattern in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""