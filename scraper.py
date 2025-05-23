from bs4 import BeautifulSoup
import re

def detect_prix_fixe(text):
    patterns = [
        r'prix\s*fixe',
        r'fixed\s+menu',
        r'set\s+menu',
        r'\d+\s*(course|courses)',  # e.g., "3-course"
        r'tasting\s+menu'
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)