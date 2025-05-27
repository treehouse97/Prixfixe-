# scraper.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed


PATTERNS = {
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


def _extract_text_and_match(resp, source_url):
    content_type = resp.headers.get("Content-Type", "").lower()
    if "pdf" in content_type or source_url.lower().endswith(".pdf"):
        try:
            doc = fitz.open(stream=resp.content, filetype="pdf")
            text = " ".join(page.get_text() for page in doc).lower()
        except Exception:
            return "", None
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = " ".join(
            s.get_text(" ", strip=True).lower()
            for s in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        )

    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return text, label
    return text, None


def fetch_website_text(url: str) -> str:
    headers = {'User-Agent': 'Mozilla/5.0'}
    visited = set()
    collected_text = ""

    try:
        base_resp = requests.get(url, headers=headers, timeout=10)
        base_resp.raise_for_status()

        base_text, match_label = _extract_text_and_match(base_resp, url)
        collected_text += base_text
        if match_label:
            return collected_text.strip()

        soup = BeautifulSoup(base_resp.text, "html.parser")
        base_domain = urlparse(url).netloc

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for a in soup.find_all("a", href=True):
                full_url = urljoin(url, a["href"])
                if urlparse(full_url).netloc != base_domain or full_url in visited:
                    continue
                visited.add(full_url)
                futures.append(executor.submit(_safe_fetch_and_match, full_url, headers))

            for future in as_completed(futures):
                sub_text, match_label = future.result()
                collected_text += " " + sub_text
                if match_label:
                    return collected_text.strip()
    except Exception:
        pass

    return collected_text.strip()


def _safe_fetch_and_match(link_url, headers):
    try:
        sub_resp = requests.get(link_url, headers=headers, timeout=10)
        sub_resp.raise_for_status()
        return _extract_text_and_match(sub_resp, link_url)
    except Exception:
        return "", None


def detect_prix_fixe_detailed(text: str):
    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""