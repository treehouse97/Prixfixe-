import re
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from io import BytesIO
import pytesseract
import fitz  # PyMuPDF

# ──────────────── Keyword patterns ───────────────────────
PATTERNS = {
    "prix fixe":      r"p[\W_]*r[\W_]*i[\W_]*x[\W_]*[\s\-]*f[\W_]*i[\W_]*x[\W_]*e?",
    "pre fixe":       r"p[\W_]*r[\W_]*e[\W_]*[\s\-]*f[\W_]*i[\W_]*x[\W_]*e?",
    "price fixed":    r"p[\W_]*r[\W_]*i[\W_]*c[\W_]*e[\W_]*[\s\-]*f[\W_]*i[\W_]*x[\W_]*e[\W_]*d",
    "3-course":       r"(three|3)[\W_]*[\s\-]*c[\W_]*o[\W_]*u[\W_]*r[\W_]*s[\W_]*e[\W_]*s?",
    "multi-course":   r"\d+[\W_]*[\s\-]*c[\W_]*o[\W_]*u[\W_]*r[\W_]*s[\W_]*e[\W_]*[\s\-]*m[\W_]*e[\W_]*a[\W_]*l",
    "fixed menu":     r"(f[\W_]*i[\W_]*x[\W_]*e[\W_]*d|s[\W_]*e[\W_]*t)[\s\-]*m[\W_]*e[\W_]*n[\W_]*u",
    "tasting menu":   r"t[\W_]*a[\W_]*s[\W_]*t[\W_]*i[\W_]*n[\W_]*g[\s\-]*m[\W_]*e[\W_]*n[\W_]*u",
    "special menu":   r"s[\W_]*p[\W_]*e[\W_]*c[\W_]*i[\W_]*a[\W_]*l[\s\-]*(menu|offer|deal)",
    "complete lunch": r"c[\W_]*o[\W_]*m[\W_]*p[\W_]*l[\W_]*e[\W_]*t[\W_]*e[\s\-]*(lunch|dinner)[\s\-]*special",
    "lunch special":  r"(lunch|dinner)[\s\-]*special[\s\-]*(menu|offer)?",
    "specials":       r"(today'?s|weekday|weekend)?[\s\-]*specials",
    "weekly special": r"(weekly|weeknight|weekend)[\s\-]*(specials?|menu)",
    "combo deal":     r"(combo|combination)[\s\-]*(deal|meal|menu)",
    "value menu":     r"value[\s\-]*(menu|deal|offer)",
    "deals":          r"\bdeals?\b"
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
    elif "image" in ctype or src_url.lower().endswith((".jpg", ".jpeg", ".png")):
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