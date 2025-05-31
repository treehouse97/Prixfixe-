# scraper.py
import re
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from io import BytesIO
# scraper.py

import re
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from io import BytesIO

# ──────────────── Keyword patterns ───────────────────────
PATTERNS = {
    "prix fixe":      r"prix[\s\-]*fixe",
    "pre fixe":       r"pre[\s\-]*fixe",
    "price fixed":    r"price[\s\-]*fixed",
    "3-course":       r"(three|3)[\s\-]*(course|courses)",
    "multi-course":   r"\d+\s*course\s*meal",
    "fixed menu":     r"(fixed|set)[\s\-]*(menu|meal)",
    "tasting menu":   r"tasting\s*menu",
    "special menu":   r"special\s*(menu|offer|deal)",
    "complete lunch": r"complete\s*(lunch|dinner)\s*special",
    "lunch special":  r"(lunch|dinner)\s*special\s*(menu|offer)?",
    "specials":       r"(today'?s|weekday|weekend)?\s*specials",
    "weekly special": r"(weekly|weeknight|weekend)\s*(specials?|menu)",
    "combo deal":     r"(combo|combination)\s*(deal|meal|menu)",
    "value menu":     r"value\s*(menu|deal|offer)",
    "deals":          r"\bdeals?\b",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}
url_cache = {}

# ──────────────── Internal utilities ─────────────────────
def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(page.get_text() for page in doc).lower()
    except Exception:
        return ""

def _image_bytes_to_text(data: bytes) -> str:
    try:
        img = Image.open(BytesIO(data))
        text = pytesseract.image_to_string(img).lower()
        print("OCR TEXT:", text)
        return text
    except Exception:
        return ""

def _extract_text_and_match(resp, src_url):
    """Return (text, pattern_label | None)"""
    ctype = resp.headers.get("content-type", "").lower()

    if "pdf" in ctype or src_url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
    elif "image" in ctype or src_url.lower().endswith((".jpg", ".jpeg", ".png")):
        text = _image_bytes_to_text(resp.content)
    elif "html" in ctype or src_url.lower().endswith((".html", "/")):
        soup = BeautifulSoup(resp.text, "html.parser")
        text = " ".join(
            tag.get_text(" ", strip=True).lower()
            for tag in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        )
    else:
        text = ""

    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return text, label
    return text, None

def _safe_fetch_and_match(url):
    """Download + match (with caching)."""
    if url in url_cache:
        return url_cache[url]

    try:
        print("FETCHING:", url)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        result = _extract_text_and_match(resp, url)
        url_cache[url] = result
        return result
    except Exception:
        url_cache[url] = ("", None)
        return "", None

# ──────────────── Public interface ───────────────────────
def fetch_website_text(url: str) -> str:
    """
    Crawl the base page, run OCR on embedded <img> tags,
    and crawl linked pages and media (PDF/JPG/PNG). Return all text.
    """
    visited = set()
    collected = ""

    try:
        base_resp = requests.get(url, headers=HEADERS, timeout=10)
        base_resp.raise_for_status()
    except Exception:
        return collected

    # Extract base HTML text
    base_text, hit = _extract_text_and_match(base_resp, url)
    collected += base_text
    if hit:
        return collected.strip()

    # Parse HTML and process embedded images directly
    soup = BeautifulSoup(base_resp.text, "html.parser")
    base_domain = urlparse(url).netloc

    print("[DEBUG] Running OCR on <img> elements in main page...")

    for img_tag in soup.find_all("img"):
        img_url = None
        for attr in ["src", "data-src", "data-original"]:
            if img_tag.has_attr(attr):
                img_url = urljoin(url, img_tag[attr])
                break
        if not img_url or img_url in visited:
            continue
        visited.add(img_url)

        try:
            img_resp = requests.get(img_url, headers=HEADERS, timeout=10)
            img_resp.raise_for_status()
            if "image" in img_resp.headers.get("content-type", ""):
                text = _image_bytes_to_text(img_resp.content)
                print("[OCR TEXT]", text)
                collected += " " + text
                for label, pattern in PATTERNS.items():
                    if re.search(pattern, text, re.IGNORECASE):
                        return collected.strip()
        except Exception:
            continue

    # Process <a> and additional media links
    html_links, media_links = [], []

    for tag in soup.find_all(["a"]):
        link = tag.get("href")
        if not link:
            continue
        full_url = urljoin(url, link)
        if urlparse(full_url).netloc != base_domain or full_url in visited:
            continue
        visited.add(full_url)
        if full_url.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            media_links.append(full_url)
        else:
            html_links.append(full_url)

    link_queue = media_links[:5] + html_links

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_safe_fetch_and_match, link): link for link in link_queue}
        for future in as_completed(futures):
            sub_text, hit = future.result()
            collected += " " + sub_text
            if hit:
                break

    return collected.strip()

def detect_prix_fixe_detailed(text: str):
    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""
# ──────────────── Keyword patterns ───────────────────────
PATTERNS = {
    "prix fixe":      r"prix[\s\-]*fixe",
    "pre fixe":       r"pre[\s\-]*fixe",
    "price fixed":    r"price[\s\-]*fixed",
    "3-course":       r"(three|3)[\s\-]*(course|courses)",
    "multi-course":   r"\d+\s*course\s*meal",
    "fixed menu":     r"(fixed|set)[\s\-]*(menu|meal)",
    "tasting menu":   r"tasting\s*menu",
    "special menu":   r"special\s*(menu|offer|deal)",
    "complete lunch": r"complete\s*(lunch|dinner)\s*special",
    "lunch special":  r"(lunch|dinner)\s*special\s*(menu|offer)?",
    "specials":       r"(today'?s|weekday|weekend)?\s*specials",
    "weekly special": r"(weekly|weeknight|weekend)\s*(specials?|menu)",
    "combo deal":     r"(combo|combination)\s*(deal|meal|menu)",
    "value menu":     r"value\s*(menu|deal|offer)",
    "deals":          r"\bdeals?\b",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}
url_cache = {}

# ──────────────── Internal utilities ─────────────────────
def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(page.get_text() for page in doc).lower()
    except Exception:
        return ""

def _image_bytes_to_text(data: bytes) -> str:
    try:
        img = Image.open(BytesIO(data))
        text = pytesseract.image_to_string(img).lower()
        print("OCR TEXT:\n", text)  # TEMP DEBUG: View what OCR sees
        return text
    except Exception:
        return ""

def _extract_text_and_match(resp, src_url):
    ctype = resp.headers.get("content-type", "").lower()
    if "pdf" in ctype or src_url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
    elif "image" in ctype or src_url.lower().endswith((".jpg", ".jpeg", ".png")):
        text = _image_bytes_to_text(resp.content)
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = " ".join(
            tag.get_text(" ", strip=True).lower()
            for tag in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        )

    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return text, label
    return text, None

def _safe_fetch_and_match(url):
    if url in url_cache:
        return url_cache[url]
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        result = _extract_text_and_match(resp, url)
        url_cache[url] = result
        return result
    except Exception:
        url_cache[url] = ("", None)
        return "", None

# ──────────────── Public entry point ─────────────────────
def fetch_website_text(url: str) -> str:
    visited = set()
    collected = ""

    try:
        base_resp = requests.get(url, headers=HEADERS, timeout=10)
        base_resp.raise_for_status()
    except Exception:
        return collected

    base_text, hit = _extract_text_and_match(base_resp, url)
    collected += base_text
    if hit:
        return collected.strip()

    soup = BeautifulSoup(base_resp.text, "html.parser")
    base_domain = urlparse(url).netloc
    html_links, media_links = [], []

    for tag in soup.find_all(["a", "img"]):
        attr = "href" if tag.name == "a" else None
        if tag.name == "img":
            for fallback in ["src", "data-src", "data-original"]:
                if tag.has_attr(fallback):
                    attr = fallback
                    break

        if not attr or not tag.has_attr(attr):
            continue

        link = urljoin(url, tag[attr])
        if urlparse(link).netloc != base_domain or link in visited:
            continue
        visited.add(link)

        if link.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            media_links.append(link)
        elif tag.name == "a":
            html_links.append(link)

    link_queue = media_links[:5] + html_links

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_safe_fetch_and_match, link): link for link in link_queue}
        for fut in as_completed(futures):
            sub_text, hit = fut.result()
            collected += " " + sub_text
            if hit:
                break

    return collected.strip()

def detect_prix_fixe_detailed(text: str):
    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""