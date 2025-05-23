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
        r"prix[\s\-]*fixe",                   # prix fixe, prix-fixe
        r"prix[\s\-]*fixe\s+menu",            # prix fixe menu
        r"prix[\s\-]*fixe\s+meal",            # prix fixe meal
        r"(three|3)[\s\-]*(course|courses)",  # three-course, 3 course
        r"\d+\s*course\s*meal",               # 2 course meal, 3 course meal, etc.
        r"(set|fixed)[\s\-]*(menu|meal)",     # fixed menu, set menu
        r"tasting\s*menu",                    # tasting menu
        r"special\s*menu",                    # special menu
        r"complete\s*(lunch|dinner)\s*special",  # complete lunch special
        r"(lunch|dinner)\s*special\s*(menu|offer)?",  # lunch special, dinner special
        r"(multi[\s\-]*course\s*(meal|menu))", # multi-course meal/menu
        r"(pre[\s\-]*fix(e)?)"                # pre-fix, pre fixe
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)