import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from io import BytesIO
import pytesseract
import fitz  # PyMuPDF

# ──────────────── Constants ───────────────────────

HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_DEPTH = 2  # Controls recursion depth
url_cache = {}

PATTERNS = {
    "prix fixe":         r"prix[\s\-]*fixe",
    "pre fixe":          r"pre[\s\-]*fixe",
    "price fixed":       r"price[\s\-]*fixed",
    "3-course":          r"(three|3)[\s\-]*(course|courses)",
    "4-course":          r"(four|4)[\s\-]*(course|courses)",
    "multi-course":      r"\d+\s*[\-]?\s*(course|courses)\s*(meal|dinner|lunch)?",
    "fixed menu":        r"(fixed|set)[\s\-]*(menu|meal)",
    "tasting menu":      r"tasting\s*menu",
    "chef's menu":       r"chef'?s\s*(menu|selection)",
    "special menu":      r"special\s*(menu|offer|deal)",
    "complete lunch":    r"complete\s*(lunch|dinner)\s*special",
    "lunch special":     r"(lunch|dinner)\s*special\s*(menu|offer)?",
    "specials":          r"(today'?s|weekday|weekend)?\s*specials",
    "weekly special":    r"(weekly|weeknight|weekend)\s*(specials?|menu)",
    "combo deal":        r"(combo|combination)\s*(deal|meal|menu)",
    "value menu":        r"value\s*(menu|deal|offer)",
    "deals":             r"\bdeals?\b",
}

# ──────────────── Utilities ───────────────────────

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
    elif "image" in ctype or src_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        text = _image_bytes_to_text(resp.content)
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        visible_text = " ".join(
            tag.get_text(" ", strip=True).lower()
            for tag in soup.find_all(["h1", "h2", "h3", "p", "li", "div", "span"])
        )
        text = visible_text

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

# ──────────────── Recursive Crawl Core ───────────────────────

def _crawl_recursive(url, base_domain, visited, depth=0):
    if url in visited or depth > MAX_DEPTH:
        return "", None
    visited.add(url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception:
        return "", None

    page_text, hit = _extract_text_and_match(resp, url)
    if hit:
        return page_text, hit

    soup = BeautifulSoup(resp.text, "html.parser")
    links = set()

    for tag in soup.find_all(["a", "img"]):
        attr = "href" if tag.name == "a" else "src"
        if not tag.has_attr(attr):
            continue
        link = urljoin(url, tag[attr])
        if urlparse(link).netloc != base_domain:
            continue
        if link in visited:
            continue
        if any(link.lower().endswith(ext) for ext in (".pdf", ".jpg", ".jpeg", ".png", ".webp")):
            links.add(link)
        elif tag.name == "a":
            links.add(link)

    collected = page_text
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_crawl_recursive, link, base_domain, visited, depth + 1): link
            for link in links
        }
        for future in as_completed(futures):
            sub_text, sub_hit = future.result()
            collected += " " + sub_text
            if sub_hit:
                return collected, sub_hit

    return collected, None

# ──────────────── Public API ───────────────────────

def fetch_website_text(url: str) -> str:
    visited = set()
    base_domain = urlparse(url).netloc
    text, _ = _crawl_recursive(url, base_domain, visited, 0)
    return text.strip()

def detect_prix_fixe_detailed(text: str):
    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""