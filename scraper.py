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
        visited = set()
        visited.add(url)

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
            except Exception as e:
                print(f"Skipped {full_url}: {e}")

        return all_text

    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe_detailed(text):
    patterns = {
        r"\bprix\s*fixe\b": "prix fixe",
        r"\$\s*\d+\s*(prix\s*fixe)?": "dollar prix fixe",
        r"(three|3)[ -]course": "three-course",
        r"(four|4)[ -]course": "four-course",
        r"(five|5)[ -]course": "five-course",
        r"(set|fixed)[ -]menu": "set/fixed menu",
        r"\btasting\s+menu\b": "tasting menu",
        r"\bchef'?s\s+tasting\b": "chef's tasting",
        r"pre\s*fix(?:ed)?": "pre fix",
        r"\b(lunch|dinner)\s+special\b": "meal special",
        r"\bmenu\s+du\s+jour\b": "menu du jour",
        r"\bprix\s+menu\b": "prix menu",
        r"\bdegustation\b": "degustation"
    }

    for pattern, label in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, None