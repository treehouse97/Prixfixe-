import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import mimetypes
from io import BytesIO
import fitz  # PyMuPDF

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        base_resp = requests.get(url, headers=headers, timeout=10)
        base_resp.raise_for_status()

        content_type = base_resp.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            # Handle direct PDF link
            doc = fitz.open(stream=base_resp.content, filetype="pdf")
            pdf_text = ""
            for page in doc:
                pdf_text += page.get_text()
            return pdf_text.lower()

        soup = BeautifulSoup(base_resp.text, 'html.parser')
        sections = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
        all_text = " ".join(s.get_text(" ", strip=True).lower() for s in sections)

        base_domain = urlparse(url).netloc
        visited = {url}

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(url, href)
            domain = urlparse(full_url).netloc
            if domain != base_domain or full_url in visited:
                continue

            try:
                sub_resp = requests.get(full_url, headers=headers, timeout=10)
                sub_resp.raise_for_status()

                content_type = sub_resp.headers.get("Content-Type", "").lower()
                if "pdf" in content_type or full_url.lower().endswith(".pdf"):
                    # Handle linked PDF
                    doc = fitz.open(stream=sub_resp.content, filetype="pdf")
                    for page in doc:
                        all_text += " " + page.get_text().lower()
                else:
                    sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                    sub_text = " ".join(
                        s.get_text(" ", strip=True).lower()
                        for s in sub_soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
                    )
                    all_text += " " + sub_text

                visited.add(full_url)
            except Exception:
                continue

        return all_text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def detect_prix_fixe_detailed(text):
    patterns = {
        "prix fixe": r"prix[\s\-]*fixe",
        "pre fixe": r"pre[\s\-]*fixe",
        "price fixed": r"price[\s\-]*fixed",
        "3-course": r"(three|3)[\s\-]*(course|courses)",
        "multi-course": r"\d+\s*course\s*meal",
        "fixed menu": r"(fixed|set)[\s\-]*(menu|meal)",
        "tasting menu": r"tasting\s*menu",
        "special menu": r"special\s*(menu|offer|deal)",
        "complete lunch": r"complete\s*(lunch|dinner)\s*special",
        "lunch special": r"(lunch|dinner)\s*special\s*(menu|offer)?",
        "specials": r"(today'?s|weekday|weekend)?\s*specials",
        "weekly special": r"(weekly|weeknight|weekend)\s*(specials?|menu)",
        "combo deal": r"(combo|combination)\s*(deal|meal|menu)",
        "value menu": r"value\s*(menu|deal|offer)",
        "deals": r"\bdeals?\b"
    }

    for label, pattern in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""