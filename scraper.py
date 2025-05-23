# scraper.py  ── improved static crawler with menu-link focus and noise filter
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from collections import Counter

# ---------- helpers ---------------------------------------------------------
def _extract_visible_text(soup) -> str:
    """Return visible lowercase text from common content tags."""
    return " ".join(
        el.get_text(" ", strip=True).lower()
        for el in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
    )

def _deduplicate_noise(text: str, min_repeats: int = 4) -> str:
    """Remove words/lines that appear too frequently (boiler-plate)."""
    tokens = text.split()
    common = {tok for tok, cnt in Counter(tokens).items() if cnt >= min_repeats}
    return " ".join(tok for tok in tokens if tok not in common)

# ---------- main fetch ------------------------------------------------------
def fetch_website_text(url: str) -> str:
    """
    Crawl `url` plus internal pages whose <a href> contains 'menu'
    and return a cleaned, deduplicated text blob suitable for keyword search.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    visited, aggregate_text = set(), ""

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    aggregate_text += _extract_visible_text(soup)
    visited.add(url)

    base_domain = urlparse(url).netloc

    # follow only menu-related internal links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "menu" not in href.lower():          # focus crawl
            continue

        full = urljoin(url, href)
        if urlparse(full).netloc != base_domain or full in visited:
            continue

        try:
            sub = requests.get(full, headers=headers, timeout=10)
            sub.raise_for_status()
            sub_soup = BeautifulSoup(sub.text, "html.parser")
            aggregate_text += " " + _extract_visible_text(sub_soup)
            visited.add(full)
        except Exception as sub_e:
            print(f"   ├─ skipped {full[:60]}…  ({sub_e})")

    cleaned = _deduplicate_noise(aggregate_text)
    return cleaned

# ---------- prix-fixe detector ---------------------------------------------
def detect_prix_fixe(text: str) -> bool:
    patterns = [
        r"prix\s*fixe",
        r"\$\s*\d+\s*(prix\s*fixe)?",
        r"(three|3)\s*[- ]\s*course",
        r"(fixed|set)\s*[- ]?\s*menu",
        r"tasting\s+menu",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)