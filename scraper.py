import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

from playwright.sync_api import sync_playwright

def fetch_website_text(url):
    def extract_text_from_soup(soup):
        return " ".join(s.get_text(" ", strip=True).lower()
                        for s in soup.find_all(["h1", "h2", "h3", "p", "li", "div"]))

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        base_resp = requests.get(url, headers=headers, timeout=10)
        base_resp.raise_for_status()
        soup = BeautifulSoup(base_resp.text, 'html.parser')

        base_text = extract_text_from_soup(soup)
        visited = set()
        visited.add(url)

        base_domain = urlparse(url).netloc
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
                base_text += " " + extract_text_from_soup(sub_soup)
                visited.add(full_url)
            except Exception as e:
                print(f"Skipped {full_url}: {e}")

        if not base_text.strip() or "prix" not in base_text:
            print(f"Static scrape weak, retrying with Playwright for {url}")
            base_text = fetch_with_playwright(url)

        print(f"--- Combined Text for {url} ---")
        print(base_text[:1000])
        return base_text

    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def fetch_with_playwright(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=20000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        return " ".join(s.get_text(" ", strip=True).lower()
                        for s in soup.find_all(["h1", "h2", "h3", "p", "li", "div"]))

    except Exception as e:
        print(f"Playwright failed for {url}: {e}")
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