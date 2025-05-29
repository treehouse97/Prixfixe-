# scraper.py
import re, warnings
from urllib.parse import urljoin, urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import fitz  # PyMuPDF

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

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
HEADERS = {"User-Agent": "Mozilla/5.0"}

_HTML_GUESS_PATHS = [
    "events", "specials", "menu", "menus",
    "deals", "offers", "wednesday-specials", "lunch-specials",
]

_PDF_DIRS = ["", "images", "pdf", "menus"]
_PDF_NAMES = [
    "menu.pdf", "specials.pdf", "lunch-specials.pdf",
    "value-menu.pdf", "weekly-specials.pdf", "dinner-specials.pdf",
]

def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return " ".join(p.get_text() for p in doc).lower()
    except Exception:
        return ""

def _match_label(text: str):
    for label, pat in PATTERNS.items():
        if re.search(pat, text, re.IGNORECASE):
            return label
    return None

def _extract_text_and_match(resp, src_url):
    ctype = resp.headers.get("content-type", "").lower()
    if "pdf" in ctype or src_url.lower().endswith(".pdf"):
        text = _pdf_bytes_to_text(resp.content)
    else:
        parser = "xml" if "xml" in ctype or src_url.endswith(".xml") else "html.parser"
        soup = BeautifulSoup(resp.text, parser)
        text = " ".join(
            el.get_text(" ", strip=True).lower()
            for el in soup.find_all(["h1", "h2", "h3", "p", "li", "div", "span", "section", "article", "a"])
        )
    return text, _match_label(text)

def _safe_fetch_and_match(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return _extract_text_and_match(r, url)
    except Exception:
        return "", None

def _guess_html_pages(base_url):
    root = urlunparse(urlparse(base_url)._replace(path="", params="", query="", fragment=""))
    return [urljoin(root, f"/{slug}") for slug in _HTML_GUESS_PATHS]

def _guess_pdfs(base_url):
    root = urlunparse(urlparse(base_url)._replace(path="", params="", query="", fragment=""))
    out = []
    for d in _PDF_DIRS:
        for n in _PDF_NAMES:
            path = f"/{d}/{n}" if d else f"/{n}"
            out.append(urljoin(root, path))
    return out

def _wordpress_pdfs(base_url):
    scheme, netloc = urlparse(base_url)[:2]
    root = f"{scheme}://{netloc}"
    year = datetime.now().year
    return [
        f"{root}/wp-content/uploads/{y}/{n}"
        for y in range(year, year - 5, -1)
        for n in _PDF_NAMES
    ]

def fetch_website_text(url: str) -> str:
    visited, collected = set(), ""

    try:
        base = requests.get(url, headers=HEADERS, timeout=10)
        base.raise_for_status()
    except Exception:
        return ""

    base_text, _ = _extract_text_and_match(base, url)
    collected += base_text
    visited.add(url)

    soup = BeautifulSoup(base.text, "html.parser")
    base_dom = urlparse(url).netloc

    html_links, pdf_links = [], []
    for a in soup.find_all("a", href=True):
        link = urljoin(url, a["href"])
        if urlparse(link).netloc != base_dom or link in visited:
            continue
        visited.add(link)
        (pdf_links if link.lower().endswith(".pdf") else html_links).append(link)

    # Add synthetic fallback links
    html_links += [l for l in _guess_html_pages(url) if l not in visited]
    pdf_links += _wordpress_pdfs(url) + _guess_pdfs(url)
    pdf_links = list(dict.fromkeys(pdf_links))[:3]  # dedupe + cap

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