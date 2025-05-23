from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

def fetch_website_text_js(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=20000)
            page.wait_for_timeout(3000)  # wait for JS to render
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        text = " ".join(s.get_text(" ", strip=True).lower() for s in sections)

        return text
    except Exception as e:
        print(f"Playwright failed for {url}: {e}")
        return ""

def detect_prix_fixe(text):
    patterns = [
    r"prix\s*fixe",
    r"pre\s*fix",
    r"\$\s*\d+\s*(prix\s*fixe|special|menu)",
    r"(three|3)[ -]course",
    r"(four|4)[ -]course",
    r"(five|5)[ -]course",
    r"tasting\s*menu",
    r"set\s*menu",
    r"fixed\s*menu",
    r"complete lunch special",
    r"includes (soup|salad).*(main course|entrée)",
    r"(soup|salad).*entrée.*dessert",
    r"lunch special.*(includes|comes with)",
    r"dinner special.*(includes|comes with)",
    r"menu special.*(includes|comes with)"
]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)