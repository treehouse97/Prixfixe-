"""
Crawl helper + pattern detection.

New in this revision
────────────────────
1.  Suppress BeautifulSoup XMLParsedAsHTMLWarning (unchanged from last push).
2.  When the start page doesn’t expose internal <a> links (common on
    single‑page sites using JS routing), probe a short list of *well‑known*
    slugs such as  /events, /specials, /weekly‑specials, /wednesday‑specials,
    /lunch‑specials.  This brings in Popei’s ‘/events’ and similar pages
    without changing any public API.
"""

import re, warnings
from urllib.parse import urljoin, urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from bs4 import (
    BeautifulSoup,
    XMLParsedAsHTMLWarning,
)
import fitz  # PyMuPDF

# ─── silence noisy parser warning ────────────────────────────────────────────
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


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
LABEL_ORDER = list(PATTERNS.keys())

HEADERS = {"User-Agent": "Mozilla/5.0"}


# ────────────────── helpers ──────────────────────────────────────────────────
def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(page.get_text() for page in doc).lower()
    except Exception:
        return ""


def _match_label(text: str):
    for lbl, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return lbl
    return None


def _extract_text_and_match(resp, src_url):
    """Return (text, matched_label | None)."""
    ctype = resp.headers.get("content-type", "").lower()

    if "pdf" in ctype or src_url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
        return text, _match_label(text)

    soup = BeautifulSoup(
        resp.text,
        "xml" if ("xml" in ctype or src_url.lower().endswith(".xml")) else "html.parser",
    )

    text = " ".join(
        t.get_text(" ", strip=True).lower()
        for t in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
    )
    return text, _match_label(text)


def _safe_fetch_and_match(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return _extract_text_and_match(r, url)
    except Exception:
        return "", None


# ────────────────── WordPress PDF fallback ───────────────────────────────────
_PDF_CANDIDATES = [
    "menu.pdf", "fullmenu.pdf", "fullmenu-1.pdf",
    "menu-1.pdf", "specials.pdf", "lunch-specials.pdf",
]

def _wordpress_guess_pdfs(root_url: str):
    scheme, netloc = urlparse(root_url)[:2]
    if not netloc:
        return []
    base = urlunparse((scheme, netloc, "", "", "", ""))
    year_now = datetime.now().year
    return [
        f"{base}/wp-content/uploads/{yr}/{name}"
        for yr in range(year_now, year_now - 5, -1)
        for name in _PDF_CANDIDATES
    ][:20]


# ────────────────── NEW  –  slug heuristics  ────────────────────────────────
COMMON_HTML_SLUGS = [
    "events", "events/", "specials", "specials/",
    "weekly-specials", "daily-specials", "wednesday-specials",
    "lunch-specials", "dinner-specials",
]

def _heuristic_slug_urls(base_url: str):
    scheme, netloc = urlparse(base_url)[:2]
    if not netloc:
        return []
    root = urlunparse((scheme, netloc, "", "", "", ""))
    return [f"{root}/{slug}" for slug in COMMON_HTML_SLUGS]


# ────────────────── public API ───────────────────────────────────────────────
def fetch_website_text(url: str) -> str:
    """
    Crawl *url* plus internal HTML/PDF links (≤3 PDFs).  
    If initial HTML exposes no internal <a> links (JS nav), probe a short
    list of common slug pages ( /events, /specials,… ).  
    WordPress “uploads/*menu*.pdf” probing is retained.
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

    # no traditional links? – try heuristic slug pages
    if not html_links and not pdf_links:
        html_links.extend(_heuristic_slug_urls(url))

    # WordPress blank‑site PDF probe
    if not html_links and not pdf_links and "wp-content" not in url:
        pdf_links.extend(_wordpress_guess_pdfs(url))

    pdf_links = pdf_links[:3]                         # speed cap
    link_queue = pdf_links + html_links               # PDFs first

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_safe_fetch_and_match, l): l for l in link_queue}
        for fut in as_completed(futures):
            sub_text, _ = fut.result()
            if sub_text:
                collected += " " + sub_text

    return collected.strip()


def detect_prix_fixe_detailed(text: str):
    lbl = _match_label(text)
    return (lbl is not None, lbl or "")