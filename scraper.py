import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

try:
    from playwright.sync_api import sync_playwright
    JS_ENABLED = True
except ImportError:
    JS_ENABLED = False
    print("[Warning] Playwright not available. JS-rendered content will be skipped.")

def fetch_website_text(url):
    try:
        if JS_ENABLED:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=20000)
                page.wait_for_timeout(3000)
                html = page.content()
                browser.close()
        else:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        text = " ".join(s.get_text(" ", strip=True).lower() for s in sections)
        return text

    except Exception as e:
        print(f"Failed to fetch or parse {url}: {e}")
        return ""

def detect_prix_fixe(text):
    patterns = [
        r"prix\\s*fixe",
        r"\\$\\s*\\d+\\s*(prix\\s*fixe)?",
        r"(three|3)[ -]course",
        r"(fixed|set)[ -]?menu",
        r"tasting\\s+menu"
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            print(f"[Detection] Matched pattern: {pattern}")
            return True
    print("[Detection] No patterns matched.")
    print(text[:1000])  # Optional for debugging
    return False