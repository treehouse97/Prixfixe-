import re
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from io import BytesIO
import pytesseract
import fitz  # PyMuPDF
# scraper.py
import re
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
from io import BytesIO
import fitz  # PyMuPDF

HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_MEDIA_LINKS = 5
MAX_HTML_LINKS = 25
MAX_DEPTH = 2

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

url_cache = {}

# ──────────────── Helpers ──────────────────────────────
def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(page.get_text() for page in doc).lower()
    except Exception:
        return ""

def _image_bytes_to_text(data: bytes) -> str:
    try:
        img = Image.open(BytesIO(data))
        return pytesseract.image_to_string(img).lower()
    except Exception:
        return ""

def _extract_text_and_match(resp, url):
    ctype = resp.headers.get("content-type", "").lower()

    if "pdf" in ctype or url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
    elif "image" in ctype or url.lower().endswith((".jpg", ".jpeg", ".png")):
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

def _safe_fetch(url):
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

# ──────────────── Main recursive crawler ───────────────
def fetch_website_text(start_url: str) -> str:
    visited = set()
    collected = []

    def crawl(url, depth):
        if depth > MAX_DEPTH or url in visited:
            return False
        visited.add(url)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except Exception:
            return False

        text, hit = _extract_text_and_match(resp, url)
        collected.append(text)
        if hit:
            return True

        if depth == MAX_DEPTH:
            return False

        soup = BeautifulSoup(resp.text, "html.parser")
        domain = urlparse(start_url).netloc
        links = []

        for tag in soup.find_all(["a", "img"]):
            attr = "href" if tag.name == "a" else "src"
            if not tag.has_attr(attr):
                continue
            link = urljoin(url, tag[attr])
            if urlparse(link).netloc != domain:
                continue
            links.append(link)

        media_links = [l for l in links if l.lower().endswith((
        ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"
        ))][:MAX_MEDIA_LINKS]
        html_links = [l for l in links if l not in media_links][:MAX_HTML_LINKS]

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_safe_fetch, l): l for l in media_links + html_links}
            for fut in as_completed(futures):
                sub_text, sub_hit = fut.result()
                collected.append(sub_text)
                if sub_hit:
                    return True

        for link in html_links:
            if crawl(link, depth + 1):
                return True

        return False

    crawl(start_url, depth=0)
    return " ".join(collected).strip()

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

# ──────────────── Core utilities ─────────────────────────
def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(page.get_text() for page in doc).lower()
    except Exception:
        return ""

def _image_bytes_to_text(data: bytes) -> str:
    try:
        img = Image.open(BytesIO(data))
        return pytesseract.image_to_string(img).lower()
    except Exception:
        return ""

def _extract_text_and_match(resp, src_url):
    ctype = resp.headers.get("content-type", "").lower()
    if "pdf" in ctype or src_url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
    elif "image" in ctype or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif")):
        text = _image_bytes_to_text(resp.content)
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = " ".join(tag.get_text(" ", strip=True).lower()
                        for tag in soup.find_all(["h1", "h2", "h3", "p", "li", "div"]))

    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return text, label
    return text, None

def _safe_fetch_and_match(url):
    if url in url_cache:
        return url_cache[url]
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        result = _extract_text_and_match(r, url)
        url_cache[url] = result
        return result
    except Exception:
        url_cache[url] = ("", None)
        return "", None

# ──────────────── Main function ──────────────────────────
def fetch_website_text(url: str) -> str:
    visited, collected = set(), ""

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
        attr = "href" if tag.name == "a" else "src"
        if not tag.has_attr(attr):
            continue
        link = urljoin(url, tag[attr])
        if urlparse(link).netloc != base_domain or link in visited:
            continue
        visited.add(link)
        if link.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            media_links.append(link)
        elif tag.name == "a":
            html_links.append(link)

    link_queue = media_links[:5] + html_links  # prioritize images/PDFs

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