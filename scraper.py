# scraper.py
import re
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF

# ────────────────── keyword patterns ─────────────────────────────────────────
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

# ────────────────── core helpers ─────────────────────────────────────────────
def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(page.get_text() for page in doc).lower()
    except Exception:
        return ""

def _extract_text_and_match(resp, src_url):
    """Return (text, label‑hit | None)."""
    ctype = resp.headers.get("content-type", "").lower()
    if "pdf" in ctype or src_url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = " ".join(
            tag.get_text(" ", strip=True).lower()
            for tag in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        )

    for lbl, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return text, lbl
    return text, None

def _safe_fetch_and_match(url):
    """Thread‑pool wrapper."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return _extract_text_and_match(r, url)
    except Exception:
        return "", None

# ────────────────── public API ───────────────────────────────────────────────
def fetch_website_text(url: str) -> str:
    """
    Crawl the start page plus internal links; include text from
    up to 3 linked PDFs.  Return **all** collected text.  Stop early
    if any page (HTML or PDF) matches a target pattern.
    """
    visited, collected = set(), ""

    try:
        base = requests.get(url, headers=HEADERS, timeout=10)
        base.raise_for_status()
    except Exception:
        return collected

    base_text, hit = _extract_text_and_match(base, url)
    collected += base_text
    if hit:
        return collected.strip()  # early success

    soup = BeautifulSoup(base.text, "html.parser")
    base_dom = urlparse(url).netloc

    # gather html & pdf links (pdf‑only limited to 3)
    html_links, pdf_links = [], []
    for a in soup.find_all("a", href=True):
        link = urljoin(url, a["href"])
        if urlparse(link).netloc != base_dom or link in visited:
            continue
        visited.add(link)
        (pdf_links if link.lower().endswith(".pdf") else html_links).append(link)

    pdf_links = pdf_links[:3]  # cap to avoid long queues
    link_queue = pdf_links + html_links  # pdfs first – higher hit chance

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_safe_fetch_and_match, link): link for link in link_queue}
        for fut in as_completed(futures):
            sub_text, hit = fut.result()
            collected += " " + sub_text
            if hit:
                break  # stop early – we found a match

    return collected.strip()


def detect_prix_fixe_detailed(text: str):
    for label, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""