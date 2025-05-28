# scraper.py
import re
from urllib.parse import urljoin, urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF


# ────────────────── keyword patterns (priority order) ───────────────────────
PATTERNS = {
    "prix fixe":      r"prix[\s\-]*fixe",
    "pre fixe":       r"pre[\s\-]*fixe",
    "price fixed":    r"price[\s\-]*fixed",
    "set menu":       r"set[\s\-]*menu",
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
LABEL_ORDER = list(PATTERNS.keys())           # stable priority list

HEADERS = {"User-Agent": "Mozilla/5.0"}


# ────────────────── helpers ──────────────────────────────────────────────────
def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(page.get_text() for page in doc).lower()
    except Exception:
        return ""


def _extract_text_and_match(resp, src_url):
    """Return (text, matched_label | None)."""
    ctype = resp.headers.get("content-type", "").lower()
    if "pdf" in ctype or src_url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = " ".join(
            t.get_text(" ", strip=True).lower()
            for t in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        )

    for lbl, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return text, lbl
    return text, None


def _safe_fetch_and_match(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return _extract_text_and_match(r, url)
    except Exception:
        return "", None


# ────────────────── WordPress fallback (blank home‑page case) ────────────────
_PDF_CANDIDATES = [
    "menu.pdf", "fullmenu.pdf", "fullmenu-1.pdf",
    "menu-1.pdf", "specials.pdf", "lunch-specials.pdf",
]

def _wordpress_guess_pdfs(root_url: str):
    scheme, netloc = urlparse(root_url)[:2]
    if not netloc:
        return []                                   # malformed

    base = urlunparse((scheme, netloc, "", "", "", ""))
    year_now = datetime.now().year
    pdf_urls = []

    for yr in range(year_now, year_now - 5, -1):
        for name in _PDF_CANDIDATES:
            pdf_urls.append(f"{base}/wp-content/uploads/{yr}/{name}")
    return pdf_urls[:20]                            # safety cap


# ────────────────── public API ───────────────────────────────────────────────
def fetch_website_text(url: str) -> str:
    """
    Crawl *url*, its internal links (HTML + ≤3 PDFs) and,
    if the page is blank WordPress, probe common “uploads/*menu*.pdf” paths.
    Returns all collected text.
    """
    visited, collected = set(), ""

    try:
        base = requests.get(url, headers=HEADERS, timeout=10)
        base.raise_for_status()
    except Exception:
        return collected

    base_text, _ = _extract_text_and_match(base, url)
    collected += base_text

    soup = BeautifulSoup(base.text, "html.parser")
    base_dom = urlparse(url).netloc

    html_links, pdf_links = [], []
    for a in soup.find_all("a", href=True):
        link = urljoin(url, a["href"])
        if urlparse(link).netloc != base_dom or link in visited:
            continue
        visited.add(link)
        (pdf_links if link.lower().endswith(".pdf") else html_links).append(link)

    # ── WordPress blank‑site probe ───────────────────────────────────────────
    if not html_links and not pdf_links and "wp-content" not in url:
        pdf_links.extend(_wordpress_guess_pdfs(url))

    pdf_links = pdf_links[:3]                       # limit for speed
    link_queue = pdf_links + html_links            # PDFs first

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_safe_fetch_and_match, l): l for l in link_queue}
        for fut in as_completed(futures):
            sub_text, _ = fut.result()
            if sub_text:
                collected += " " + sub_text

    return collected.strip()


def detect_prix_fixe_detailed(text: str):
    for lbl, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, lbl
    return False, ""