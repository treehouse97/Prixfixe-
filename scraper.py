import requests
from bs4 import BeautifulSoup
import re

# Try importing OCR tools
try:
    import pytesseract
    from PIL import Image
    from io import BytesIO
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

def fetch_website_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True).lower()

        if not OCR_AVAILABLE:
            return text

        # OCR fallback if available
        links = [a['href'] for a in soup.find_all('a', href=True)]
        pdf_links = [l for l in links if l.lower().endswith('.pdf')]
        img_tags = soup.find_all('img', src=True)
        img_links = [tag['src'] for tag in img_tags if tag['src'].lower().endswith(('.png', '.jpg', '.jpeg'))]

        for link in pdf_links:
            ocr_text = extract_text_from_pdf(link, base_url=url)
            text += " " + ocr_text

        for link in img_links:
            ocr_text = extract_text_from_image(link, base_url=url)
            text += " " + ocr_text

        return text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def extract_text_from_image(img_url, base_url=""):
    if not OCR_AVAILABLE:
        return ""
    try:
        if not img_url.startswith("http"):
            img_url = requests.compat.urljoin(base_url, img_url)
        response = requests.get(img_url, stream=True, timeout=10)
        img = Image.open(BytesIO(response.content))
        return pytesseract.image_to_string(img).lower()
    except Exception as e:
        print(f"[OCR IMG ERROR] {img_url}: {e}")
        return ""

def extract_text_from_pdf(pdf_url, base_url=""):
    if not OCR_AVAILABLE:
        return ""
    try:
        if not pdf_url.startswith("http"):
            pdf_url = requests.compat.urljoin(base_url, pdf_url)
        response = requests.get(pdf_url, stream=True, timeout=10)
        images = convert_from_bytes(response.content)
        text = ""
        for image in images:
            text += pytesseract.image_to_string(image).lower() + " "
        return text
    except Exception as e:
        print(f"[OCR PDF ERROR] {pdf_url}: {e}")
        return ""

def detect_prix_fixe(text):
    patterns = [
        r'prix\s*fixe',
        r'fixed\s+menu',
        r'set\s+menu',
        r'\d+\s*(course|courses)',
        r'tasting\s+menu'
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)
