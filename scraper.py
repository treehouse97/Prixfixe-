# scraper.py
import re, io, requests
from typing import Tuple, Dict, List
from bs4 import BeautifulSoup, Comment
from PyPDF2 import PdfReader

# ────────────────────────────────────────────────────────────────────────────
# Patterns you already maintain
PATTERNS: Dict[str, List[re.Pattern]] = {
    "prix fixe":   [re.compile(r"\bprix\s*f(i|í)x(e)?",  re.I)],
    "pre fixe":    [re.compile(r"\bpre\s*f(i|í)xe?",     re.I)],
    "specials":    [re.compile(r"\bspecials?\b",         re.I)],
    "lunch special":[re.compile(r"\blunch\s+specials?\b",re.I)],
}

# ────────────────── public helpers ──────────────────────────────────────────
def fetch_website_text(url: str, timeout: int = 10) -> str:
    """
    Return plain‑text from `url`.
    • If the target (or redirected target) is a PDF, extract its text.
    • Else strip HTML *and* merge text from up to 3 linked PDFs.
    """
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
        r.raise_for_status()
    except Exception:
        return ""

    ctype = r.headers.get("content-type", "")
    if _looks_like_pdf(url, ctype):
        return _pdf_bytes_to_text(r.content)

    # HTML path
    html_text = _html_to_text(r.text)
    pdf_texts = []

    soup = BeautifulSoup(r.text, "html.parser")
    pdf_links = [a["href"] for a in soup.find_all("a", href=True)
                 if a["href"].lower().endswith(".pdf")][:3]
    for href in pdf_links:
        abs_url = requests.compat.urljoin(r.url, href)
        try:
            p = requests.get(abs_url, timeout=timeout, headers={"User-Agent": _UA})
            p.raise_for_status()
            if _looks_like_pdf(abs_url, p.headers.get("content-type", "")):
                pdf_texts.append(_pdf_bytes_to_text(p.content))
        except Exception:
            continue

    return html_text + "\n".join(pdf_texts)


def detect_prix_fixe_detailed(text: str) -> Tuple[bool, str]:
    text_low = text.lower()
    for label, regs in PATTERNS.items():
        for rx in regs:
            if rx.search(text_low):
                return True, label
    return False, ""


# ────────────────── internal utilities ──────────────────────────────────────
_UA = ("Mozilla/5.0 (compatible; TheFixeBot/1.0; "
       "+https://github.com/yourproject)")

def _looks_like_pdf(url: str, ctype: str) -> bool:
    return url.lower().endswith(".pdf") or "application/pdf" in ctype.lower()

def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for c in soup.find_all(text=lambda t: isinstance(t, Comment)):
        c.extract()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text

def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return " ".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""