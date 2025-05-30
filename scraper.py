"""
Core crawler / classifier – rev 3 (May‑2025)

Key enhancements
────────────────
• Broader text extraction: +<span>, <section>, <article>, <a>
• Generic fallback:
    – Tries a small set of deal‑heavy sub‑pages: /events, /specials, /menu, …
    – Probes typical PDF locations (/images, /pdf, /menus) for menu*.pdf & specials*.pdf
• Existing public API and PATTERNS remain intact – Streamlit code needs **zero**
  changes; layout, DB schema and display logic are unaffected.
"""

import re, warnings
from urllib.parse import urljoin, urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import fitz  # PyMuPDF

# ─── silence Soup’s XMLParsedAsHTMLWarning ───────────────────────────────────
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

# ────────────────── fallback candidates ──────────────────────────────────────
_COMMON_HTML_SLUGS = [
    "events", "specials", "wednesday-specials", "weekly-specials",
    "menu", "menus", "lunch-specials", "deals", "offers",
]

_PDF_CANDIDATES = [
    "menu.pdf", "fullmenu.pdf", "specials.pdf", "lunch-specials.pdf",
    "weekly-specials.pdf", "dinner-specials.pdf", "value-menu.pdf",
]

_PDF_DIRS = ["", "images", "pdf", "menus"]

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

    # choose parser type
    soup = BeautifulSoup(
        resp.text,
        "xml" if ("xml" in ctype or src_url.lower().endswith(".xml")) else "html.parser",
    )

    # broader tag set to capture deals buried in spans & sections
    TAGS = ["h1", "h2", "h3", "p", "li", "div", "span", "section", "article", "a"]
    text = " ".join(
        t.get_text(" ", strip=True).lower()
        for t in soup.find_all(TAGS)
    )
    return text, _match_label(text)

def _safe_fetch_and_match(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return _extract_text_and_match(r, url)
    except Exception:
        return "", None

# ────────────────── fallback URL generators ─────────────────────────────────
def _guess_common_html(root_url: str):
    base = urlunparse(urlparse(root_url)._replace(path="", params="", query="", fragment=""))
    return [urljoin(base, f"/{slug}") for slug in _COMMON_HTML_SLUGS]

def _guess_generic_pdfs(root_url: str):
    base = urlunparse(urlparse(root_url)._replace(path="", params="", query="", fragment=""))
    out = []
    for d in _PDF_DIRS:
        for name in _PDF_CANDIDATES:
            path = f"/{d}/{name}" if d else f"/{name}"
            out.append(urljoin(base, path))
    return out

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
    ]

# ────────────────── public API ───────────────────────────────────────────────
def fetch_website_text(url: str) -> str:
    """
    Crawl *url*, its internal links (HTML + ≤3 PDFs) and,
    if needed, probe typical deal pages & PDF locations.
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

    # ───── synthetic guesses ────────────────────────────────────────────────
    html_links.extend([l for l in _guess_common_html(url) if l not in visited])
    visited.update(html_links)

    if not pdf_links:
        # WordPress → pdf links first, else generic dirs
        pdf_links.extend(_wordpress_guess_pdfs(url) or _guess_generic_pdfs(url))
    pdf_links = pdf_links[:3]  # safety cap

    link_queue = pdf_links + html_links

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