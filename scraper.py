import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from collections import Counter

# ----------------------------
def _extract_visible_text(soup):
    """Extracts visible text from meaningful tags only."""
    return " ".join(
        el.get_text(" ", strip=True).lower()
        for el in soup.find_all(["h1", "h2", "h3", "p", "li", "section", "article"])
        if el.get_text(strip=True)
    )

def _deduplicate_noise(text, min_repeats=3):
    tokens = text.split()
    common = {tok for tok, count in Counter(tokens).items() if count >= min_repeats}
    return " ".join(tok for tok in tokens if tok not in common)

def _strip_known_noise(text):
    noise_phrases = [
        r"toggle navigation",
        r"tab start navigating",
        r"content starts here",
        r"meet team",
        r"press to (pause|play)",
        r"slide \d+ of \d+",
    ]
    for pattern in noise_phrases:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text

def text_preview(text, chars=600):
    return text[:chars] + ("..." if len(text) > chars else "")

# ----------------------------
def fetch_website_text(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    visited, combined = set(), ""

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return ""

    base_domain = urlparse(url).netloc
    visited.add(url)
    combined += _extract_visible_text(soup)

    # follow menu-related internal links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "menu" not in href.lower():
            continue
        full_url = urljoin(url, href)
        if urlparse(full_url).netloc != base_domain or full_url in visited:
            continue

        try:
            sub_resp = requests.get(full_url, headers=headers, timeout=10)
            sub_resp.raise_for_status()
            sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
            combined += " " + _extract_visible_text(sub_soup)
            visited.add(full_url)
        except Exception as sub_e:
            print(f"[SKIP] {full_url[:60]}... ({sub_e})")

    cleaned = _deduplicate_noise(combined, min_repeats=3)
    cleaned = _strip_known_noise(cleaned)
    print(f"[SCRAPED] {url}\n{text_preview(cleaned)}")
    return cleaned

# ----------------------------
def detect_prix_fixe(text, log=False):
    patterns = [
        r"prix\s*fixe",
        r"\$\s*\d+\s*(prix\s*fixe)?",
        r"(three|3)\s*[- ]\s*course",
        r"(fixed|set)\s*[- ]?\s*menu",
        r"tasting\s+menu",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            if log:
                print(f"[MATCH] Pattern matched: {p}")
            return True
    if log:
        print("[NO MATCH] No prix fixe keywords found.")
    return False