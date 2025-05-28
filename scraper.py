"""
Crawler / classifier with JavaScript render fallback.

Flow
────
1. Static crawl (root page → slug HTMLs → ≤3 PDFs).
2. If nothing matches any PATTERN, launch headless Chromium with Playwright,
   render the root page, extract text, and run the regex pass once more.

Public API remains:  fetch_website_text(url)  &  detect_prix_fixe_detailed(text)
"""

import re, warnings, contextlib, asyncio
from urllib.parse import urljoin, urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import fitz  # PyMuPDF

# ── optional JS renderer (only used if static pass fails) ────────────────────
with contextlib.suppress(ImportError):
    from playwright.sync_api import sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
else:
    _PLAYWRIGHT_AVAILABLE = False


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

# ────────────────── regex helpers ────────────────────────────────────────────
def _match_label(text: str):
    for lbl, pattern in PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return lbl
    return None


# ────────────────── content fetchers ─────────────────────────────────────────
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
        return text, _match_label(text)

    parser = "xml" if ("xml" in ctype or src_url.lower().endswith(".xml")) else "html.parser"
    soup = BeautifulSoup(resp.text, parser)

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


# ────────────────── WordPress PDF guess ──────────────────────────────────────
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


# ────────────────── slug heuristics ──────────────────────────────────────────
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


# ────────────────── JavaScript render fallback ───────────────────────────────
def _render_page_text(url: str, timeout: int = 15000) -> str:
    if not _PLAYWRIGHT_AVAILABLE:
        return ""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=timeout, wait_until="networkidle")
            html = page.content()
            browser.close()
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(" ", strip=True).lower()
        except Exception:
            browser.close()
            return ""


# ────────────────── public API ───────────────────────────────────────────────
def fetch_website_text(url: str) -> str:
    """
    Crawl *url* plus discovered HTML/PDF links (≤3 PDFs).
    If no pattern matches, render root page with Playwright (one shot) and
    check again.
    """
    visited, collected = set(), ""
    label_found = None

    try:
        base = requests.get(url, headers=HEADERS, timeout=10)
        base.raise_for_status()
    except Exception:
        return collected

    base_text, hit = _extract_text_and_match(base, url)
    collected += base_text
    label_found = hit or label_found

    soup = BeautifulSoup(base.text, "html.parser")
    base_dom = urlparse(url).netloc

    html_links, pdf_links = [], []
    for a in soup.find_all("a", href=True):
        link = urljoin(url, a["href"])
        if urlparse(link).netloc != base_dom or link in visited:
            continue
        visited.add(link)
        (pdf_links if link.lower().endswith(".pdf") else html_links).append(link)

    if not html_links and not pdf_links:
        html_links.extend(_heuristic_slug_urls(url))

    if not html_links and not pdf_links and "wp-content" not in url:
        pdf_links.extend(_wordpress_guess_pdfs(url))

    pdf_links = pdf_links[:3]
    link_queue = pdf_links + html_links

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_safe_fetch_and_match, l): l for l in link_queue}
        for fut in as_completed(futures):
            sub_text, hit = fut.result()
            if sub_text:
                collected += " " + sub_text
            if hit and label_found is None:
                label_found = hit

    # ── JS render fallback (only if we still have no label) ──────────────────
    if label_found is None and _PLAYWRIGHT_AVAILABLE:
        rendered = _render_page_text(url)
        if rendered:
            collected += " " + rendered
            label_found = _match_label(rendered)

    return collected.strip()


def detect_prix_fixe_detailed(text: str):
    lbl = _match_label(text)
    return (lbl is not None, lbl or "")