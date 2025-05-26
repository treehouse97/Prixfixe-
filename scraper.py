import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {'User-Agent': 'Mozilla/5.0'}

def fetch_website_text(url):
    visited = set()
    all_text = ""

    def extract_text(resp, url):
        content_type = resp.headers.get("Content-Type", "").lower()

        if "pdf" in content_type or url.lower().endswith(".pdf"):
            try:
                doc = fitz.open(stream=resp.content, filetype="pdf")
                return " ".join(page.get_text() for page in doc).lower()
            except:
                return ""
        else:
            soup = BeautifulSoup(resp.text, "html.parser")
            return " ".join(
                s.get_text(" ", strip=True).lower()
                for s in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
            )

    try:
        base_resp = requests.get(url, headers=HEADERS, timeout=10)
        base_resp.raise_for_status()
        all_text += extract_text(base_resp, url)

        soup = BeautifulSoup(base_resp.text, "html.parser")
        base_domain = urlparse(url).netloc

        futures = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for a in soup.find_all("a", href=True):
                full_url = urljoin(url, a["href"])
                if urlparse(full_url).netloc != base_domain:
                    continue
                if full_url in visited:
                    continue
                visited.add(full_url)

                def crawl_subpage(link):
                    try:
                        sub_resp = requests.get(link, headers=HEADERS, timeout=10)
                        sub_resp.raise_for_status()
                        return extract_text(sub_resp, link)
                    except:
                        return ""

                futures.append(executor.submit(crawl_subpage, full_url))

            for future in as_completed(futures):
                all_text += " " + future.result()

    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")

    return all_text.strip()

def detect_prix_fixe_detailed(text):
    patterns = {
        "prix fixe": r"prix[\s\-]*fixe",
        "pre fixe": r"pre[\s\-]*fixe",
        "price fixed": r"price[\s\-]*fixed",
        "3-course": r"(three|3)[\s\-]*(course|courses)",
        "multi-course": r"\d+\s*course\s*meal",
        "fixed menu": r"(fixed|set)[\s\-]*(menu|meal)",
        "tasting menu": r"tasting\s*menu",
        "special menu": r"special\s*(menu|offer|deal)",
        "complete lunch": r"complete\s*(lunch|dinner)\s*special",
        "lunch special": r"(lunch|dinner)\s*special\s*(menu|offer)?",
        "specials": r"(today'?s|weekday|weekend)?\s*specials",
        "weekly special": r"(weekly|weeknight|weekend)\s*(specials?|menu)",
        "combo deal": r"(combo|combination)\s*(deal|meal|menu)",
        "value menu": r"value\s*(menu|deal|offer)",
        "deals": r"\bdeals?\b"
    }

    for label, pattern in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            print(f"[MATCH] Triggered on: {label}")
            return True, label
    return False, ""