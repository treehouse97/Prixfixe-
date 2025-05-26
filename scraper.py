import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed
from ai_analyze import analyze_text

HEADERS = {'User-Agent': 'Mozilla/5.0'}

def fetch_website_text(url):
    visited = set()
    all_text = ""

    def extract_text_and_match(resp, source_url):
        content_type = resp.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or source_url.lower().endswith(".pdf"):
            try:
                doc = fitz.open(stream=resp.content, filetype="pdf")
                text = " ".join(page.get_text() for page in doc).lower()
            except:
                return "", ""
        else:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = " ".join(
                s.get_text(" ", strip=True).lower()
                for s in soup.find_all(["h1", "h2", "h3", "p", "li", "div"])
            )

        return text, source_url

    try:
        base_resp = requests.get(url, headers=HEADERS, timeout=10)
        base_resp.raise_for_status()
        base_text, _ = extract_text_and_match(base_resp, url)
        all_text += base_text

        soup = BeautifulSoup(base_resp.text, "html.parser")
        base_domain = urlparse(url).netloc

        futures = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for a in soup.find_all("a", href=True):
                full_url = urljoin(url, a["href"])
                if urlparse(full_url).netloc != base_domain or full_url in visited:
                    continue
                visited.add(full_url)

                def fetch_and_check(link_url):
                    try:
                        sub_resp = requests.get(link_url, headers=HEADERS, timeout=10)
                        sub_resp.raise_for_status()
                        return extract_text_and_match(sub_resp, link_url)
                    except:
                        return "", ""

                futures.append(executor.submit(fetch_and_check, full_url))

            for future in as_completed(futures):
                sub_text, _ = future.result()
                all_text += " " + sub_text

    except Exception as e:
        print(f"Error fetching {url}: {e}")

    return all_text.strip()


def detect_prix_fixe_detailed(text):
    """
    Uses analyzer to detect prix fixe–related patterns and confidence.
    Returns: match_found (bool), label string, confidence score (float)
    """
    result = analyze_text(text)

    # Always return matches—even partial ones
    matched = bool(result["labels"])
    label_string = ", ".join(result["labels"]) if matched else ""
    confidence = result["confidence"]

    # Print results for debug log (can remove later)
    print("Detected:", matched, "| Confidence:", confidence, "| Labels:", label_string)

    return matched, label_string, confidence